#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_IMAGE_NAME=dev-env
CONTAINER_PACKAGES_DIR=/opt/hep/packages
CONTAINER_WORKSPACE_DIR=/workspace

# Where this script stores state it manages itself: a downloaded Dockerfile
# (when run standalone, e.g. from ~/bin or ~/.local/bin), the generated CUDA
# Dockerfile, and default hepyy-packages directories. Deliberately NOT
# $SCRIPT_DIR and NOT $PWD -- the script may live in a bin dir that shouldn't
# get build artifacts dumped into it, and $PWD varies per invocation.
# Override with --home <dir> or $HEPYY_POD_HOME.
HEPYY_POD_HOME="${HEPYY_POD_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/hepyy-pod}"

# Pinned to a tag, not a branch, so `curl`-ing this script alone always
# fetches the matching Dockerfile -- update HEPYY_POD_REF on release.
HEPYY_POD_REPO_RAW_BASE="https://raw.githubusercontent.com/matplo/hepyy"
HEPYY_POD_REF="${HEPYY_POD_REF:-v0.2.28}"
HEPYY_POD_DOCKERFILE_PATH="contrib/podman/Dockerfile"
HEPYY_POD_SCRIPT_PATH="contrib/podman/hepyy-pod.sh"

# PROFILE_STORAGE_ROOT / PROFILE_HEPYY_PACKAGES are set by a profile (see
# cmd_profile / the profile dispatch below) and act as a layer of defaults
# beneath explicit flags but above $HEPYY_POD_STORAGE_ROOT/$SCRATCH.
PROFILE_STORAGE_ROOT=""
PROFILE_HEPYY_PACKAGES=""

# Resolves the storage root for podman's image/container store AND the
# default hepyy-packages parent dir -- precedence (highest first):
#   1. explicit $1 (an --storage-root flag value), if non-empty
#   2. a loaded profile's STORAGE_ROOT
#   3. $HEPYY_POD_STORAGE_ROOT
#   4. $SCRATCH/hepyy-pod-storage, if $SCRATCH is set (common HPC convention)
#   5. fallback: ~/.local/share/hepyy-pod-storage, WARNING printed
resolve_storage_root() {
    local explicit="${1:-}"
    if [[ -n "$explicit" ]]; then
        echo "$explicit"
        return 0
    fi
    if [[ -n "$PROFILE_STORAGE_ROOT" ]]; then
        echo "$PROFILE_STORAGE_ROOT"
        return 0
    fi
    if [[ -n "${HEPYY_POD_STORAGE_ROOT:-}" ]]; then
        echo "$HEPYY_POD_STORAGE_ROOT"
        return 0
    fi
    if [[ -n "${SCRATCH:-}" ]]; then
        echo "$SCRATCH/hepyy-pod-storage"
        return 0
    fi
    echo "WARNING: no --storage-root, \$HEPYY_POD_STORAGE_ROOT, or \$SCRATCH set." >&2
    echo "         Falling back to \$HOME/.local/share/hepyy-pod-storage -- podman" >&2
    echo "         image layers and hepyy-built packages will count against your" >&2
    echo "         \$HOME quota. Override with --storage-root <dir> or" >&2
    echo "         \$HEPYY_POD_STORAGE_ROOT=<dir> if that matters on this host." >&2
    echo "$HOME/.local/share/hepyy-pod-storage"
}

# Echoes the podman --root flag for a given storage root, to be passed
# explicitly to every podman build/run call that touches the image store --
# per-invocation, no global containers.conf changes.
#
# Deliberately NOT also redirecting --runroot: it only holds ephemeral
# runtime state (container locks, sockets) under a path with a strict length
# limit (podman errors past ~50 chars, which $SCRATCH-style paths blow
# through), and podman's own default already lives under
# /run/user/<uid>/containers (tmpfs, not $HOME disk, so it isn't actually
# part of the quota problem this is solving).
storage_flags() {
    local storage_root="$1"
    printf '%s\0%s\0' "--root" "$storage_root/containers-storage"
}

# Echoes the podman binary to use: podman-hpc if present (NERSC's wrapper,
# needed for its --jupyter integration and HPC-specific GPU/filesystem
# handling), else plain podman. Override with $HEPYY_POD_PODMAN_BIN.
podman_bin() {
    if [[ -n "${HEPYY_POD_PODMAN_BIN:-}" ]]; then
        echo "$HEPYY_POD_PODMAN_BIN"
    elif command -v podman-hpc >/dev/null 2>&1; then
        echo "podman-hpc"
    else
        echo "podman"
    fi
}

# Echoes the --device/--runtime GPU flags for cmd_run/cmd_kernel, given a
# detected CUDA version (empty = no GPU flags). Mirrors the detection used
# inline before this was extracted: CDI on podman >= 4.1, else the legacy
# nvidia-container-runtime wrapper, else a warning and no GPU flags.
gpu_run_flags() {
    local cuda_ver="$1"
    [[ -z "$cuda_ver" ]] && return 0
    if command -v nvidia-ctk >/dev/null 2>&1 && podman_supports_cdi; then
        printf '%s\0%s\0' "--device" "nvidia.com/gpu=all"
    elif command -v nvidia-container-runtime >/dev/null 2>&1; then
        printf '%s\0%s\0' "--runtime" "$(command -v nvidia-container-runtime)"
        printf '%s\0%s\0' "-e" "NVIDIA_VISIBLE_DEVICES=all"
        printf '%s\0%s\0' "-e" "NVIDIA_DRIVER_CAPABILITIES=all"
    else
        warn_missing_nvidia_ctk
    fi
}

# Echoes the directory holding the Dockerfile to build from: next to this
# script if it was cloned alongside one (repo checkout), else HEPYY_POD_HOME
# (where ensure_dockerfile fetches one for a standalone-downloaded script).
dockerfile_dir() {
    if [[ -f "$SCRIPT_DIR/Dockerfile" ]]; then
        echo "$SCRIPT_DIR"
    else
        echo "$HEPYY_POD_HOME"
    fi
}

# Ensures a Dockerfile exists in dockerfile_dir(), fetching the pinned-ref
# copy from GitHub into HEPYY_POD_HOME if this script was downloaded
# standalone (e.g. via the one-liner) with no Dockerfile alongside it.
ensure_dockerfile() {
    local dir
    dir="$(dockerfile_dir)"
    if [[ -f "$dir/Dockerfile" ]]; then
        return 0
    fi
    mkdir -p "$dir"
    local url="$HEPYY_POD_REPO_RAW_BASE/$HEPYY_POD_REF/$HEPYY_POD_DOCKERFILE_PATH"
    echo "INFO: no Dockerfile found; fetching $url -> $dir/Dockerfile" >&2
    if ! curl -fsSL "$url" -o "$dir/Dockerfile"; then
        echo "ERROR: failed to fetch Dockerfile from $url" >&2
        echo "       Place a Dockerfile next to this script, or set HEPYY_POD_REF" >&2
        echo "       to a valid tag/branch of matplo/hepyy." >&2
        exit 1
    fi
}

usage() {
    cat <<EOF
Usage: $(basename "$0") <subcommand> [options]
       $(basename "$0") --update [ref]

Autodetects whether this node has a usable NVIDIA/CUDA setup (via nvidia-smi)
and builds/runs a plain or CUDA-enabled variant of the $BASE_IMAGE_NAME image
accordingly. CUDA builds are tagged and stored separately per CUDA version so
mismatched builds never collide.

Subcommands:
  build [--home <dir>] [--storage-root <dir>]
                                   Build the image (CUDA variant if detected)
  run [--workspace <dir>] [--hepyy-packages <dir>] [--home <dir>]
      [--storage-root <dir>] [-- <cmd> [args...]]
                                   Run a container from the matching image
  profile add <name> --storage-root <dir> --hepyy-packages <dir>
                                   Register a named (storage-root, hepyy-packages)
                                   pair, usable as: $(basename "$0") <name> build|run ...
  profile list                    List registered profiles
  profile rm <name>                Remove a registered profile
  kernel install [--name <name>] [--display-name <name>] [--net <mode>]
      [--workspace <dir>] [--hepyy-packages <dir>] [--storage-root <dir>] [--home <dir>]
                                   Generate a Jupyter kernelspec (kernel.json +
                                   kernel-helper.sh) that launches ipykernel
                                   inside this image via podman/podman-hpc run.
                                   A TEMPLATE: bakes in whatever mounts/image
                                   are resolved on THIS host (or profile) at
                                   install time -- not Perlmutter-specific.
                                   --net defaults to "host" (required for the
                                   Jupyter server on the host to reach the
                                   kernel's ZMQ ports through podman's network
                                   namespace); pass --net "" to disable if it
                                   conflicts with a GPU-specific network mode.
                                   Each kernel start launches a fresh
                                   container (a few seconds of latency); a
                                   kernel restart picks up a newer image tag
                                   if one was rebuilt meanwhile.
  kernel list                     List installed Jupyter kernels
  kernel remove <name>            Remove a kernel installed by this script

--update [ref]             Self-update THIS script file in place from GitHub.
                            Defaults to the "main" branch (latest, possibly
                            unreleased); pass a tag to pin, e.g. --update
                            v0.2.28. Verifies the download looks like this
                            script and passes a syntax check before
                            replacing it, and keeps the previous copy as
                            <script>.bak.

Options for 'run':
  --workspace <dir>        Host directory mounted to $CONTAINER_WORKSPACE_DIR
                            (external code / results live here). Defaults to \$PWD.
  --hepyy-packages <dir>   Host directory mounted to $CONTAINER_PACKAGES_DIR
                            (hepyy-installed packages persist here). Defaults to
                            <storage-root>/hepyy-packages-<image-tag> (see
                            --storage-root below), unless a profile sets it.

  Anything after '--' (or any trailing positional args) is passed through as the
  command to run inside the container. Defaults to an interactive bash shell.

Options for 'build' and 'run':
  --home <dir>             Where this script keeps state it manages itself: a
                            downloaded Dockerfile (only needed if this script
                            was fetched standalone, e.g. into ~/bin or
                            ~/.local/bin, rather than cloned alongside its
                            Dockerfile) and the generated CUDA Dockerfile.
                            Defaults to \$HEPYY_POD_HOME, or
                            \$XDG_DATA_HOME/hepyy-pod, or ~/.local/share/hepyy-pod.
                            Deliberately not \$PWD or this script's own
                            directory (which may be a shared bin dir). This is
                            also where registered profiles are stored.
  --storage-root <dir>     Where podman's own image/container storage AND the
                            default hepyy-packages dir live -- these can be
                            large (multi-GB images, compiled HEP packages), so
                            this is kept separate from --home. Precedence:
                            --storage-root flag > a loaded profile's stored
                            value > \$HEPYY_POD_STORAGE_ROOT > \$SCRATCH/hepyy-pod-storage
                            (if \$SCRATCH is set, e.g. on NERSC/Perlmutter) >
                            fallback ~/.local/share/hepyy-pod-storage (WARNING
                            printed, since this counts against \$HOME quota).

Named profiles: register a (storage-root, hepyy-packages) pair once, then
invoke it by name as the first argument, before the subcommand:
  $(basename "$0") profile add blue --storage-root /scratch/hepyy-blue --hepyy-packages /scratch/pkgs-blue
  $(basename "$0") blue run -- hepyy install sherpa/2.2.15
An explicit --storage-root/--hepyy-packages flag after the profile name still
overrides that profile's stored value for that one invocation.

CUDA detection can be overridden:
  NO_CUDA=1                        force plain (no-GPU) build/run
  CUDA_VERSION=<major.minor>       skip nvidia-smi detection, use this version
  CUDA_BASE_IMAGE=<image:tag>      use this exact base image instead of a lookup

Examples:
  $(basename "$0") build
  $(basename "$0") run
  $(basename "$0") run --workspace /data/myproj --hepyy-packages /data/podman-dev/hepyy-packages-$BASE_IMAGE_NAME
  $(basename "$0") run -- hepyy install sherpa/2.2.15
  NO_CUDA=1 $(basename "$0") build
  $(basename "$0") build --home ~/.local/hepyy-pod   # e.g. when installed into ~/bin
  $(basename "$0") build --storage-root \$SCRATCH/hepyy-pod-storage   # e.g. on Perlmutter
  $(basename "$0") profile add blue --storage-root /scratch/hepyy-blue --hepyy-packages /scratch/pkgs-blue
  $(basename "$0") blue run -- hepyy install jewel/2.6.0-custom
  $(basename "$0") kernel install --name hep --display-name "HEP (podman)"
  $(basename "$0") main kernel install --name hep   # using a profile's mounts/storage
  $(basename "$0") --update            # self-update to latest "main"
  $(basename "$0") --update v0.2.28    # self-update to a specific tag

If a CUDA driver is detected but GPU passthrough isn't actually working inside
the container (e.g. nvidia-smi missing in-container), the NVIDIA Container
Toolkit is likely not set up on this host. Fix with (needs sudo). If your
distro's repos don't have the package, add NVIDIA's own repo first:
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \\
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \\
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
Then, either way:
  sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
  nvidia-ctk cdi list
EOF
}

# Echoes "<major.minor>" if a usable CUDA setup is detected, else nothing.
# Never exits non-zero -- absence of CUDA is a normal, expected outcome here.
detect_cuda_version() {
    if [[ "${NO_CUDA:-0}" == "1" ]]; then
        return 0
    fi
    if [[ -n "${CUDA_VERSION:-}" ]]; then
        echo "$CUDA_VERSION"
        return 0
    fi
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        return 0
    fi
    nvidia-smi 2>/dev/null | grep -oP 'CUDA Version:\s*\K[0-9]+\.[0-9]+' | head -1 || true
}

# Maps a detected driver-supported CUDA version to a concrete nvidia/cuda
# devel image tag. The toolkit baked into the image must be <= the host
# driver's max supported CUDA version, so round down to a known-good tag.
resolve_base_image() {
    local cuda_ver="$1"
    if [[ -n "${CUDA_BASE_IMAGE:-}" ]]; then
        echo "$CUDA_BASE_IMAGE"
        return 0
    fi
    local major="${cuda_ver%%.*}"
    local minor="${cuda_ver#*.}"
    local tag
    case "$major" in
        13)
            tag="13.0.3"
            ;;
        12)
            if   (( minor >= 6 )); then tag="12.6.3"
            elif (( minor >= 4 )); then tag="12.4.1"
            elif (( minor >= 2 )); then tag="12.2.2"
            elif (( minor >= 1 )); then tag="12.1.1"
            else                        tag="12.0.1"
            fi
            ;;
        11)
            if   (( minor >= 8 )); then tag="11.8.0"
            else                        tag="11.7.1"
            fi
            ;;
        *)
            # Unmapped major version (e.g. a newer driver than this table has
            # seen) -- guess rather than hard-fail, so a future CUDA 14/15
            # doesn't need another emergency patch here. The guess may not
            # exist on the registry; podman build will then fail clearly at
            # the pull step instead of this function blocking before trying.
            tag="${major}.0.0"
            echo "WARNING: no known base image mapping for CUDA $cuda_ver." >&2
            echo "         Guessing docker.io/nvidia/cuda:${tag}-devel-ubuntu22.04 --" >&2
            echo "         this is unverified. Override with CUDA_BASE_IMAGE=<image:tag>" >&2
            echo "         if this guess is wrong or doesn't exist." >&2
            ;;
    esac
    echo "docker.io/nvidia/cuda:${tag}-devel-ubuntu22.04"
}

# Echoes the image tag to use, given whatever detect_cuda_version() returned.
image_tag_for() {
    local cuda_ver="$1"
    if [[ -z "$cuda_ver" ]]; then
        echo "$BASE_IMAGE_NAME"
    else
        echo "${BASE_IMAGE_NAME}-cuda-${cuda_ver}"
    fi
}

generate_cuda_dockerfile() {
    local base_image="$1"
    local dir generated
    dir="$(dockerfile_dir)"
    generated="$dir/Dockerfile.cuda.generated"
    {
        echo "FROM $base_image"
        tail -n +2 "$dir/Dockerfile"
    } > "$generated"
    echo "$generated"
}

cmd_build() {
    local cuda_ver image_tag dir
    local storage_root_flag=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --home)
                HEPYY_POD_HOME="$2"
                shift 2
                ;;
            --storage-root)
                storage_root_flag="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option for 'build': $1" >&2
                usage
                exit 1
                ;;
        esac
    done

    ensure_dockerfile
    dir="$(dockerfile_dir)"
    cuda_ver="$(detect_cuda_version)"
    image_tag="$(image_tag_for "$cuda_ver")"

    local storage_root
    storage_root="$(resolve_storage_root "$storage_root_flag")"
    mkdir -p "$storage_root"
    local -a storage_args=()
    while IFS= read -r -d '' arg; do storage_args+=("$arg"); done < <(storage_flags "$storage_root")

    if [[ -z "$cuda_ver" ]]; then
        echo "INFO: no CUDA detected, building plain image -> tag $image_tag" >&2
        exec podman "${storage_args[@]}" build -t "$image_tag" -f "$dir/Dockerfile" "$dir"
    fi

    local base_image generated
    base_image="$(resolve_base_image "$cuda_ver")" || exit 1
    echo "INFO: detected CUDA $cuda_ver -> base image $base_image -> tag $image_tag" >&2
    generated="$(generate_cuda_dockerfile "$base_image")"
    exec podman "${storage_args[@]}" build -t "$image_tag" -f "$generated" "$dir"
}

# If the host packages dir is empty, seed it from whatever hepyy packages
# were baked into the image at build time (e.g. hepyy-utils/main), since a
# bind mount onto /opt/hep/packages otherwise hides the image's own copy.
seed_packages_dir() {
    local image_tag="$1"
    local packages_dir="$2"
    shift 2
    local -a storage_args=("$@")
    if [[ -z "$(ls -A "$packages_dir" 2>/dev/null)" ]]; then
        echo "INFO: seeding empty $packages_dir from image's $CONTAINER_PACKAGES_DIR" >&2
        podman "${storage_args[@]}" run --rm \
            -v "$packages_dir:/seed-target:Z" \
            "$image_tag" \
            sh -c "cp -a $CONTAINER_PACKAGES_DIR/. /seed-target/ 2>/dev/null || true"
    fi
}

# CDI device syntax (--device nvidia.com/gpu=all) requires podman >= 4.1.
podman_supports_cdi() {
    local ver major minor
    ver="$(podman --version | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
    major="${ver%%.*}"
    minor="$(echo "$ver" | cut -d. -f2)"
    if (( major > 4 )); then return 0; fi
    if (( major == 4 && minor >= 1 )); then return 0; fi
    return 1
}

warn_missing_nvidia_ctk() {
    cat >&2 <<'EOF'
WARNING: CUDA detected on this host, but no NVIDIA Container Toolkit (nvidia-ctk)
         or CDI spec was found. GPU passthrough into the container will likely
         NOT work (nvidia-smi etc. won't be visible inside the container), even
         though --gpus all is being passed.

         To fix, run on the HOST (needs sudo). If your distro's default repos
         don't have the package (plain `apt-get install` errors with
         "Unable to locate package"), add NVIDIA's own repo first:
           curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
           curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
             sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
             sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
         Then, either way:
           sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
           sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
           nvidia-ctk cdi list

         After that, this script will automatically switch to
         --device nvidia.com/gpu=all for proper CDI-based GPU passthrough.
EOF
}

cmd_run() {
    local cuda_ver image_tag
    cuda_ver="$(detect_cuda_version)"
    image_tag="$(image_tag_for "$cuda_ver")"

    local workspace_dir=""
    local packages_dir="$PROFILE_HEPYY_PACKAGES"
    local storage_root_flag=""
    local -a passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --workspace)
                workspace_dir="$2"
                shift 2
                ;;
            --hepyy-packages)
                packages_dir="$2"
                shift 2
                ;;
            --storage-root)
                storage_root_flag="$2"
                shift 2
                ;;
            --home)
                HEPYY_POD_HOME="$2"
                shift 2
                ;;
            --)
                shift
                passthrough=("$@")
                break
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                passthrough=("$@")
                break
                ;;
        esac
    done

    local storage_root
    storage_root="$(resolve_storage_root "$storage_root_flag")"
    local -a storage_args=()
    while IFS= read -r -d '' arg; do storage_args+=("$arg"); done < <(storage_flags "$storage_root")

    if [[ -z "$workspace_dir" ]]; then
        workspace_dir="$(pwd)"
        echo "WARNING: --workspace not given, defaulting to \$PWD ($workspace_dir)" >&2
    fi

    if [[ -z "$packages_dir" ]]; then
        packages_dir="$storage_root/hepyy-packages-$image_tag"
        echo "WARNING: --hepyy-packages not given, defaulting to $packages_dir" >&2
    fi

    mkdir -p "$workspace_dir" "$packages_dir" "$storage_root"
    workspace_dir="$(cd "$workspace_dir" && pwd)"
    packages_dir="$(cd "$packages_dir" && pwd)"

    seed_packages_dir "$image_tag" "$packages_dir" "${storage_args[@]}"

    local -a run_cmd=()
    if [[ ${#passthrough[@]} -eq 0 ]]; then
        run_cmd=(bash)
    else
        run_cmd=("${passthrough[@]}")
    fi

    local -a gpu_flags=()
    while IFS= read -r -d '' arg; do gpu_flags+=("$arg"); done < <(gpu_run_flags "$cuda_ver")

    echo "INFO: running image $image_tag${cuda_ver:+ (CUDA $cuda_ver)}" >&2
    exec podman "${storage_args[@]}" run -it --rm \
        --userns=keep-id \
        "${gpu_flags[@]}" \
        -e HEPYY_PACKAGES_DIR="$CONTAINER_PACKAGES_DIR" \
        -v "$packages_dir:$CONTAINER_PACKAGES_DIR:Z" \
        -v "$workspace_dir:$CONTAINER_WORKSPACE_DIR:Z" \
        "$image_tag" "${run_cmd[@]}"
}

# Minimal JSON string escaping (backslash and double-quote) -- good enough
# for the paths/names this script deals with; not a general JSON encoder.
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    printf '%s' "$s"
}

# Echoes a JSON array string from argv, e.g. '["a", "b"]'.
json_array() {
    local out="[" first=1 a
    for a in "$@"; do
        [[ $first -eq 1 ]] && first=0 || out+=", "
        out+="\"$(json_escape "$a")\""
    done
    out+="]"
    printf '%s' "$out"
}

# Jupyter's default kernelspec data dir on Linux, used if `jupyter` isn't
# on PATH to ask directly via `jupyter --data-dir`.
default_jupyter_data_dir() {
    echo "${XDG_DATA_HOME:-$HOME/.local/share}/jupyter"
}

jupyter_data_dir() {
    if command -v jupyter >/dev/null 2>&1; then
        jupyter --data-dir 2>/dev/null || default_jupyter_data_dir
    else
        default_jupyter_data_dir
    fi
}

# Jupyter's runtime dir holds the connection file whose path gets substituted
# into {connection_file} in argv -- that dir must be mounted into the
# container at the SAME path so the launcher can actually open it.
jupyter_runtime_dir() {
    if command -v jupyter >/dev/null 2>&1; then
        jupyter --runtime-dir 2>/dev/null || echo "$(default_jupyter_data_dir)/runtime"
    else
        echo "$(default_jupyter_data_dir)/runtime"
    fi
}

cmd_kernel() {
    local action="${1:-}"
    shift || true
    case "$action" in
        install)
            cmd_kernel_install "$@"
            ;;
        remove)
            local name="${1:-}"
            if [[ -z "$name" ]]; then
                echo "ERROR: kernel remove requires a name" >&2
                exit 1
            fi
            local dir="$(jupyter_data_dir)/kernels/$name"
            if [[ ! -d "$dir" ]]; then
                echo "ERROR: no such kernel '$name' (expected $dir)" >&2
                exit 1
            fi
            rm -rf "$dir"
            echo "INFO: removed kernel '$name' ($dir)" >&2
            ;;
        list)
            if command -v jupyter >/dev/null 2>&1 && jupyter kernelspec list 2>/dev/null; then
                :
            else
                ls "$(jupyter_data_dir)/kernels" 2>/dev/null || echo "No kernels found."
            fi
            ;;
        *)
            echo "Usage: $(basename "$0") kernel install [--name <name>] [--display-name <name>]" >&2
            echo "                                    [--workspace <dir>] [--hepyy-packages <dir>]" >&2
            echo "                                    [--storage-root <dir>] [--home <dir>]" >&2
            echo "       $(basename "$0") kernel list" >&2
            echo "       $(basename "$0") kernel remove <name>" >&2
            exit 1
            ;;
    esac
}

# Generates a Jupyter kernelspec (kernel.json + a kernel-helper.sh hook) that
# launches ipykernel inside this image via podman run, using the same
# storage-root/profile/workspace/hepyy-packages resolution as `run`. This is
# a TEMPLATE: it bakes in whatever podman binary, mounts, and image tag are
# resolved on THIS host at install time -- it is not Perlmutter-specific,
# though podman-hpc (if present, e.g. on NERSC) is preferred automatically.
cmd_kernel_install() {
    local cuda_ver image_tag
    cuda_ver="$(detect_cuda_version)"
    image_tag="$(image_tag_for "$cuda_ver")"

    local name="$image_tag"
    local display_name="HEP (podman $image_tag)"
    local workspace_dir="" packages_dir="$PROFILE_HEPYY_PACKAGES" storage_root_flag=""
    # Rootless podman's default network namespace isolates the container's
    # loopback from the host's, so ipykernel's ZMQ sockets (bound to
    # 127.0.0.1 per the connection file written by the Jupyter server on the
    # HOST) are unreachable and the kernel hangs on "connecting". --net=host
    # fixes this by sharing the host's network namespace. Override with
    # --net <mode> (e.g. "" to disable) if this conflicts with a GPU-specific
    # network mode on your setup.
    local net_mode="host"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name) name="$2"; shift 2 ;;
            --display-name) display_name="$2"; shift 2 ;;
            --workspace) workspace_dir="$2"; shift 2 ;;
            --hepyy-packages) packages_dir="$2"; shift 2 ;;
            --storage-root) storage_root_flag="$2"; shift 2 ;;
            --home) HEPYY_POD_HOME="$2"; shift 2 ;;
            --net) net_mode="$2"; shift 2 ;;
            -h|--help) cmd_kernel; exit 0 ;;
            *) echo "Unknown option for 'kernel install': $1" >&2; exit 1 ;;
        esac
    done

    local storage_root
    storage_root="$(resolve_storage_root "$storage_root_flag")"
    local -a storage_args=()
    while IFS= read -r -d '' arg; do storage_args+=("$arg"); done < <(storage_flags "$storage_root")

    if [[ -z "$workspace_dir" ]]; then
        workspace_dir="$(pwd)"
        echo "WARNING: --workspace not given, defaulting to \$PWD ($workspace_dir)" >&2
    fi
    if [[ -z "$packages_dir" ]]; then
        packages_dir="$storage_root/hepyy-packages-$image_tag"
        echo "WARNING: --hepyy-packages not given, defaulting to $packages_dir" >&2
    fi
    mkdir -p "$workspace_dir" "$packages_dir" "$storage_root"
    workspace_dir="$(cd "$workspace_dir" && pwd)"
    packages_dir="$(cd "$packages_dir" && pwd)"

    local runtime_dir
    runtime_dir="$(jupyter_runtime_dir)"
    mkdir -p "$runtime_dir"

    local -a gpu_flags=()
    while IFS= read -r -d '' arg; do gpu_flags+=("$arg"); done < <(gpu_run_flags "$cuda_ver")

    local bin
    bin="$(podman_bin)"
    local -a extra_flags=()
    [[ "$(basename "$bin")" == "podman-hpc" ]] && extra_flags+=(--jupyter)

    local kernel_dir="$(jupyter_data_dir)/kernels/$name"
    mkdir -p "$kernel_dir"
    local helper="$kernel_dir/kernel-helper.sh"
    cat > "$helper" <<'HELPER'
#!/bin/sh
# Customization hook run INSIDE the container before the kernel launches.
# Edit this to e.g. pin a package version to match your Jupyter frontend
# (NERSC JupyterLab's ipympl/ipywidgets versions must match the kernel's):
#   pip install --quiet 'ipympl==<version-matching-your-jupyterlab>'
# or source an environment/module setup script, then exec the real command:
exec "$@"
HELPER
    chmod +x "$helper"

    local -a net_flags=()
    [[ -n "$net_mode" ]] && net_flags=(--net "$net_mode")

    local -a argv=(
        "$bin" run --rm -i --userns=keep-id
        "${storage_args[@]}"
        "${net_flags[@]}"
        "${extra_flags[@]}"
        "${gpu_flags[@]}"
        -e HEPYY_PACKAGES_DIR="$CONTAINER_PACKAGES_DIR"
        -v "$packages_dir:$CONTAINER_PACKAGES_DIR:Z"
        -v "$workspace_dir:$CONTAINER_WORKSPACE_DIR:Z"
        -v "$runtime_dir:$runtime_dir:Z"
        -v "$kernel_dir:$kernel_dir:Z"
        "$image_tag"
        "$helper" python -m ipykernel_launcher -f "{connection_file}"
    )

    {
        echo "{"
        echo "  \"argv\": $(json_array "${argv[@]}"),"
        echo "  \"display_name\": \"$(json_escape "$display_name")\","
        echo "  \"language\": \"python\""
        echo "}"
    } > "$kernel_dir/kernel.json"

    echo "INFO: installed Jupyter kernel '$name' -> $kernel_dir/kernel.json" >&2
    echo "INFO: edit $helper to customize the in-container launch (env setup, package pins)" >&2
}

PROFILES_DIR="$HEPYY_POD_HOME/profiles"
RESERVED_NAMES=(build run profile kernel -h --help)

is_reserved_name() {
    local name="$1" r
    for r in "${RESERVED_NAMES[@]}"; do
        [[ "$name" == "$r" ]] && return 0
    done
    return 1
}

cmd_profile() {
    local action="${1:-}"
    shift || true
    case "$action" in
        add)
            local name="${1:-}"
            shift || true
            if [[ -z "$name" ]]; then
                echo "ERROR: profile add requires a name" >&2
                exit 1
            fi
            if is_reserved_name "$name"; then
                echo "ERROR: '$name' is a reserved name, pick another" >&2
                exit 1
            fi
            local p_storage="" p_packages=""
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --storage-root)
                        p_storage="$2"
                        shift 2
                        ;;
                    --hepyy-packages)
                        p_packages="$2"
                        shift 2
                        ;;
                    *)
                        echo "Unknown option for 'profile add': $1" >&2
                        exit 1
                        ;;
                esac
            done
            if [[ -z "$p_storage" || -z "$p_packages" ]]; then
                echo "ERROR: profile add requires both --storage-root <dir> and --hepyy-packages <dir>" >&2
                exit 1
            fi
            mkdir -p "$PROFILES_DIR"
            {
                echo "STORAGE_ROOT=$p_storage"
                echo "HEPYY_PACKAGES=$p_packages"
            } > "$PROFILES_DIR/$name.conf"
            echo "INFO: registered profile '$name' -> storage-root=$p_storage hepyy-packages=$p_packages" >&2
            ;;
        list)
            if [[ ! -d "$PROFILES_DIR" ]] || [[ -z "$(ls -A "$PROFILES_DIR" 2>/dev/null)" ]]; then
                echo "No profiles registered. Use: $(basename "$0") profile add <name> --storage-root <dir> --hepyy-packages <dir>"
                return 0
            fi
            local f name
            for f in "$PROFILES_DIR"/*.conf; do
                name="$(basename "$f" .conf)"
                echo "$name:"
                sed 's/^/  /' "$f"
            done
            ;;
        rm)
            local name="${1:-}"
            if [[ -z "$name" ]]; then
                echo "ERROR: profile rm requires a name" >&2
                exit 1
            fi
            if [[ ! -f "$PROFILES_DIR/$name.conf" ]]; then
                echo "ERROR: no such profile '$name'" >&2
                exit 1
            fi
            rm -f "$PROFILES_DIR/$name.conf"
            echo "INFO: removed profile '$name'" >&2
            ;;
        *)
            echo "Usage: $(basename "$0") profile add <name> --storage-root <dir> --hepyy-packages <dir>" >&2
            echo "       $(basename "$0") profile list" >&2
            echo "       $(basename "$0") profile rm <name>" >&2
            exit 1
            ;;
    esac
}

# Loads $PROFILES_DIR/<name>.conf into PROFILE_STORAGE_ROOT/PROFILE_HEPYY_PACKAGES,
# which act as defaults beneath explicit --storage-root/--hepyy-packages flags.
load_profile() {
    local name="$1"
    # shellcheck disable=SC1090
    source "$PROFILES_DIR/$name.conf"
    PROFILE_STORAGE_ROOT="$STORAGE_ROOT"
    PROFILE_HEPYY_PACKAGES="$HEPYY_PACKAGES"
}

# Self-updates THIS script file in place from GitHub. Defaults to the "main"
# branch (the latest, possibly-unreleased version) rather than the pinned
# HEPYY_POD_REF tag this running copy was built against -- that's the point
# of --update: pick up newer fixes/features. Pass a tag/branch explicitly to
# pin, e.g. --update v0.2.28.
cmd_update() {
    local ref="${1:-main}"
    local self
    self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

    local url="$HEPYY_POD_REPO_RAW_BASE/$ref/$HEPYY_POD_SCRIPT_PATH"
    local tmp
    tmp="$(mktemp)"
    echo "INFO: fetching $url" >&2
    if ! curl -fsSL "$url" -o "$tmp"; then
        rm -f "$tmp"
        echo "ERROR: failed to fetch $url" >&2
        echo "       Check the ref/network, or pass --update <tag> for a known-good tag." >&2
        exit 1
    fi
    if ! head -1 "$tmp" | grep -q '^#!/usr/bin/env bash'; then
        rm -f "$tmp"
        echo "ERROR: downloaded file doesn't look like this script -- aborting update." >&2
        exit 1
    fi
    if ! bash -n "$tmp" 2>/dev/null; then
        rm -f "$tmp"
        echo "ERROR: downloaded script failed a syntax check -- aborting update." >&2
        exit 1
    fi

    local backup="$self.bak"
    cp -p "$self" "$backup"
    chmod 755 "$tmp"
    mv "$tmp" "$self"
    echo "INFO: updated $self from ref '$ref' (previous copy saved to $backup)" >&2
}

if [[ "${1:-}" == "--update" ]]; then
    shift
    cmd_update "$@"
    exit 0
fi

if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

subcommand="$1"
shift

# A leading arg that isn't a known subcommand but matches a registered
# profile selects that profile's defaults, then the next arg is the actual
# subcommand, e.g. `hepyy-pod.sh blue run -- ...`.
if ! is_reserved_name "$subcommand" && [[ -f "$PROFILES_DIR/$subcommand.conf" ]]; then
    load_profile "$subcommand"
    if [[ $# -eq 0 ]]; then
        usage
        exit 1
    fi
    subcommand="$1"
    shift
fi

case "$subcommand" in
    build)
        cmd_build "$@"
        ;;
    run)
        cmd_run "$@"
        ;;
    profile)
        cmd_profile "$@"
        ;;
    kernel)
        cmd_kernel "$@"
        ;;
    -h|--help)
        usage
        ;;
    *)
        echo "Unknown subcommand or profile: $subcommand" >&2
        usage
        exit 1
        ;;
esac
