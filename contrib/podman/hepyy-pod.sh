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
HEPYY_POD_REF="${HEPYY_POD_REF:-v0.2.22}"
HEPYY_POD_DOCKERFILE_PATH="contrib/podman/Dockerfile"

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

Autodetects whether this node has a usable NVIDIA/CUDA setup (via nvidia-smi)
and builds/runs a plain or CUDA-enabled variant of the $BASE_IMAGE_NAME image
accordingly. CUDA builds are tagged and stored separately per CUDA version so
mismatched builds never collide.

Subcommands:
  build [--home <dir>]
                                   Build the image (CUDA variant if detected)
  run [--workspace <dir>] [--hepyy-packages <dir>] [--home <dir>] [-- <cmd> [args...]]
                                   Run a container from the matching image

Options for 'run':
  --workspace <dir>        Host directory mounted to $CONTAINER_WORKSPACE_DIR
                            (external code / results live here). Defaults to \$PWD.
  --hepyy-packages <dir>   Host directory mounted to $CONTAINER_PACKAGES_DIR
                            (hepyy-installed packages persist here). Defaults to
                            <home>/hepyy-packages-<image-tag> (see --home below).

  Anything after '--' (or any trailing positional args) is passed through as the
  command to run inside the container. Defaults to an interactive bash shell.

Options for 'build' and 'run':
  --home <dir>             Where this script keeps state it manages itself: a
                            downloaded Dockerfile (only needed if this script
                            was fetched standalone, e.g. into ~/bin or
                            ~/.local/bin, rather than cloned alongside its
                            Dockerfile), the generated CUDA Dockerfile, and
                            default hepyy-packages directories. Defaults to
                            \$HEPYY_POD_HOME, or \$XDG_DATA_HOME/hepyy-pod, or
                            ~/.local/share/hepyy-pod.
                            Deliberately not \$PWD or this script's own
                            directory (which may be a shared bin dir).

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

If a CUDA driver is detected but GPU passthrough isn't actually working inside
the container (e.g. nvidia-smi missing in-container), the NVIDIA Container
Toolkit is likely not set up on this host. Fix with (needs sudo):
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
            echo "ERROR: no known base image mapping for CUDA $cuda_ver." >&2
            echo "       Override with CUDA_BASE_IMAGE=<image:tag>." >&2
            return 1
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

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --home)
                HEPYY_POD_HOME="$2"
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

    if [[ -z "$cuda_ver" ]]; then
        echo "INFO: no CUDA detected, building plain image -> tag $image_tag" >&2
        exec podman build -t "$image_tag" -f "$dir/Dockerfile" "$dir"
    fi

    local base_image generated
    base_image="$(resolve_base_image "$cuda_ver")" || exit 1
    echo "INFO: detected CUDA $cuda_ver -> base image $base_image -> tag $image_tag" >&2
    generated="$(generate_cuda_dockerfile "$base_image")"
    exec podman build -t "$image_tag" -f "$generated" "$dir"
}

# If the host packages dir is empty, seed it from whatever hepyy packages
# were baked into the image at build time (e.g. hepyy-utils/main), since a
# bind mount onto /opt/hep/packages otherwise hides the image's own copy.
seed_packages_dir() {
    local image_tag="$1"
    local packages_dir="$2"
    if [[ -z "$(ls -A "$packages_dir" 2>/dev/null)" ]]; then
        echo "INFO: seeding empty $packages_dir from image's $CONTAINER_PACKAGES_DIR" >&2
        podman run --rm \
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

         To fix, run on the HOST (needs sudo):
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
    local packages_dir=""
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

    if [[ -z "$workspace_dir" ]]; then
        workspace_dir="$(pwd)"
        echo "WARNING: --workspace not given, defaulting to \$PWD ($workspace_dir)" >&2
    fi

    if [[ -z "$packages_dir" ]]; then
        packages_dir="$HEPYY_POD_HOME/hepyy-packages-$image_tag"
        echo "WARNING: --hepyy-packages not given, defaulting to $packages_dir" >&2
    fi

    mkdir -p "$workspace_dir" "$packages_dir"
    workspace_dir="$(cd "$workspace_dir" && pwd)"
    packages_dir="$(cd "$packages_dir" && pwd)"

    seed_packages_dir "$image_tag" "$packages_dir"

    local -a run_cmd=()
    if [[ ${#passthrough[@]} -eq 0 ]]; then
        run_cmd=(bash)
    else
        run_cmd=("${passthrough[@]}")
    fi

    local -a gpu_flags=()
    if [[ -n "$cuda_ver" ]]; then
        if command -v nvidia-ctk >/dev/null 2>&1 && podman_supports_cdi; then
            gpu_flags=(--device nvidia.com/gpu=all)
        elif command -v nvidia-container-runtime >/dev/null 2>&1; then
            # podman is too old for CDI (--device nvidia.com/gpu=all needs
            # podman >= 4.1-ish); fall back to the legacy OCI runtime wrapper.
            gpu_flags=(--runtime="$(command -v nvidia-container-runtime)"
                       -e NVIDIA_VISIBLE_DEVICES=all
                       -e NVIDIA_DRIVER_CAPABILITIES=all)
        else
            warn_missing_nvidia_ctk
        fi
    fi

    echo "INFO: running image $image_tag${cuda_ver:+ (CUDA $cuda_ver)}" >&2
    exec podman run -it --rm \
        --userns=keep-id \
        "${gpu_flags[@]}" \
        -e HEPYY_PACKAGES_DIR="$CONTAINER_PACKAGES_DIR" \
        -v "$packages_dir:$CONTAINER_PACKAGES_DIR:Z" \
        -v "$workspace_dir:$CONTAINER_WORKSPACE_DIR:Z" \
        "$image_tag" "${run_cmd[@]}"
}

if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

subcommand="$1"
shift

case "$subcommand" in
    build)
        cmd_build "$@"
        ;;
    run)
        cmd_run "$@"
        ;;
    -h|--help)
        usage
        ;;
    *)
        echo "Unknown subcommand: $subcommand" >&2
        usage
        exit 1
        ;;
esac
