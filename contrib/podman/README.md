# hepyy + podman

A rootless, GPU-aware podman/container setup for building and running
`hepyy`-managed packages (Python 3.11, C++, Fortran toolchain included).

## Quick start

Download the script, inspect it, then run it (recommended over piping
`curl | bash` blindly):

```bash
curl -fsSL https://raw.githubusercontent.com/matplo/hepyy/v0.2.29/contrib/podman/hepyy-pod.sh -o hepyy-pod.sh
chmod +x hepyy-pod.sh
less hepyy-pod.sh   # read it before running, especially the first time
./hepyy-pod.sh build
./hepyy-pod.sh run
```

If you only downloaded `hepyy-pod.sh` (no `Dockerfile` next to it), `build`
automatically fetches the matching `Dockerfile` from the same pinned repo tag.

If you'd rather clone the whole thing:

```bash
git clone --branch v0.2.29 https://github.com/matplo/hepyy
cd hepyy/contrib/podman
./hepyy-pod.sh build
./hepyy-pod.sh run
```

### Install into `~/.local/bin`

To have `hepyy-pod` available as a regular command (inspect it first, same
as above):

```bash
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/matplo/hepyy/v0.2.29/contrib/podman/hepyy-pod.sh -o ~/.local/bin/hepyy-pod
chmod +x ~/.local/bin/hepyy-pod
hepyy-pod build   # make sure ~/.local/bin is on $PATH first
```

Since this puts the script somewhere with no `Dockerfile` alongside it,
`build` automatically fetches one into `$HEPYY_POD_HOME` (default
`~/.local/share/hepyy-pod`) the first time it's needed -- see
[Keeping podman images and built packages off `$HOME`](#keeping-podman-images-and-built-packages-off-home)
below for why that's a small text file, not the actual image storage.

## What `build`/`run` do

- **`build`**: builds the image. Autodetects CUDA via `nvidia-smi` on the
  host; if found, generates a CUDA-flavored Dockerfile on the fly (matching
  `nvidia/cuda:<version>-devel-ubuntu22.04`) and tags the image
  `dev-env-cuda-<version>` instead of plain `dev-env`.
- **`run [--workspace <dir>] [--hepyy-packages <dir>] [-- <cmd> ...]`**: runs
  a container from the matching image.
  - `--workspace` mounts a host directory to `/workspace` (your code and
    results). Defaults to `$PWD` if omitted (with a warning).
  - `--hepyy-packages` mounts a host directory to `/opt/hep/packages`, so
    `hepyy install <pkg>/<version>` run inside a container persists on the
    host and never needs an image rebuild to add/update a package. Defaults
    to `<storage-root>/hepyy-packages-<image-tag>` if omitted (see
    `--storage-root` below).
  - GPU passthrough is handled automatically: CDI (`--device
    nvidia.com/gpu=all`) on podman >= 4.1, or the legacy
    `nvidia-container-runtime` wrapper on older podman (e.g. the podman 3.4.x
    that ships with Ubuntu 22.04).

## Keeping podman images and built packages off `$HOME`

Podman's own image/container storage defaults to `~/.local/share/containers`
for rootless podman, and (as above) the default `hepyy-packages` dir also
used to live under `~/.local`. On systems with a small `$HOME` quota (e.g.
NERSC/Perlmutter), a handful of multi-GB images and compiled HEP packages
will blow through it fast.

`--storage-root <dir>` (on both `build` and `run`) redirects *both* of
those to a location of your choosing. Resolution order:

1. `--storage-root <dir>` flag
2. a loaded profile's stored value (see below)
3. `$HEPYY_POD_STORAGE_ROOT` env var
4. `$SCRATCH/hepyy-pod-storage`, automatically, if `$SCRATCH` is set (true on
   Perlmutter and most HPC sites)
5. fallback: `~/.local/share/hepyy-pod-storage` -- a WARNING is printed when
   this fallback is used, since it does count against `$HOME` quota.

```bash
# on Perlmutter, $SCRATCH is already set, so this just works with no flags:
./hepyy-pod.sh build
./hepyy-pod.sh run

# or be explicit anywhere:
./hepyy-pod.sh build --storage-root /scratch/hepyy-pod-storage
```

Note: switching storage roots points podman at a brand-new, empty image
store -- images built under one root aren't visible under another, so the
first build after switching starts from scratch.

## Named profiles

Register a `(storage-root, hepyy-packages)` pair under a short name, then
invoke it by putting the name before the subcommand:

```bash
./hepyy-pod.sh profile add blue --storage-root /scratch/hepyy-blue --hepyy-packages /scratch/pkgs-blue
./hepyy-pod.sh profile add red  --storage-root /scratch/hepyy-red  --hepyy-packages /scratch/pkgs-red

./hepyy-pod.sh blue build
./hepyy-pod.sh blue run -- hepyy install sherpa/2.2.15

./hepyy-pod.sh red build
./hepyy-pod.sh red run -- hepyy install jewel/2.6.0-custom
```

Each profile is a fully independent podman image store and package set --
`blue` and `red` above never see each other's images or packages, so this is
a clean way to keep e.g. different CUDA builds or different package sets
side by side without them interfering.

An explicit `--storage-root`/`--hepyy-packages` flag on the command line
still overrides a profile's stored value for that one invocation:

```bash
./hepyy-pod.sh blue run --hepyy-packages /scratch/pkgs-experimental -- ...
```

`profile list` shows what's registered, `profile rm <name>` removes one.

## Jupyter kernel

`kernel install` generates a Jupyter kernelspec (`kernel.json` +
`kernel-helper.sh`) that launches `ipykernel` inside this image via
`podman`/`podman-hpc run`, reusing the same storage-root/profile/workspace/
hepyy-packages resolution as `run`:

```bash
./hepyy-pod.sh kernel install --name hep --display-name "HEP (podman)"
# or, using a profile's mounts/storage-root:
./hepyy-pod.sh main kernel install --name hep
```

This is a **template**, not Perlmutter-specific: it bakes in whatever
mounts/image are resolved on *this* host (or profile) at install time, and
prefers `podman-hpc` automatically if present (adding its `--jupyter` flag),
falling back to plain `podman` otherwise. The generated `kernel.json` lands
under `jupyter --data-dir`'s `kernels/<name>/` (or
`~/.local/share/jupyter/kernels/<name>/` if `jupyter` isn't on `PATH`).

`kernel-helper.sh`, alongside it, is a customization hook run *inside* the
container right before the kernel launches -- edit it to pin a package
version (e.g. `ipympl` to match your JupyterLab frontend's version) or source
an environment/module setup script:

```sh
#!/bin/sh
pip install --quiet 'ipympl==<version-matching-your-jupyterlab>'
exec "$@"
```

`kernel list` / `kernel remove <name>` list and remove installed kernels.

### Gotchas

- **Networking**: rootless podman's default network namespace isolates the
  container's loopback from the host's, so `ipykernel`'s ZMQ ports (bound to
  `127.0.0.1` per the connection file the Jupyter server writes on the host)
  are unreachable and the kernel hangs on "connecting". `kernel install`
  therefore defaults to `--net host`. If that conflicts with a GPU-specific
  network mode on your setup, override with `--net ""` (and find a different
  fix for reachability if the hang comes back).
- **Startup latency**: each kernel start launches a fresh container -- a few
  seconds, not instant. Restarting a kernel picks up a newer image tag if one
  was rebuilt meanwhile.
- **Don't generate kernel.json by hand on the host** instead of through this
  script: a hand-written kernelspec that points `argv`'s `python` at the
  host's own interpreter (e.g. a venv symlinking into the image) runs the
  *wrong* Python entirely, and an `env` block in `kernel.json` only reaches
  the `podman`/`podman-hpc` process on the host, never the container.
  `kernel install`'s `argv` always invokes `python` by name, resolved inside
  the container via `kernel-helper.sh`'s `exec "$@"` -- never a host path --
  and nothing is put in an `env` block, so this doesn't apply to kernels
  generated by this script; it's only a risk if you edit `kernel.json` by
  hand afterward.

Run `./hepyy-pod.sh --help` for the full option/override list (including
`NO_CUDA=1`, `CUDA_VERSION=`, `CUDA_BASE_IMAGE=` env overrides, and the
`nvidia-container-toolkit` setup commands if GPU detection finds a driver but
no working passthrough mechanism).

If `nvidia-smi` reports a CUDA version newer than this script's known base
image table (e.g. a fresh driver bump), it guesses a tag instead of failing
outright and prints a WARNING -- override with `CUDA_BASE_IMAGE=<image:tag>`
if that guess doesn't exist on the registry.

## No sudo required

Everything here runs rootless (`podman` with `--userns=keep-id`). The only
exception is a one-time host setup if you want GPU passthrough and don't
already have `nvidia-container-toolkit` installed. On a Debian/Ubuntu host:

```bash
./hepyy-pod.sh gpu-setup-deb
```

This adds NVIDIA's apt repo (if needed), installs `nvidia-container-toolkit`,
and generates the CDI spec -- idempotent, safe to re-run. It does require
`sudo` (prompted interactively). `--help` also prints the equivalent manual
commands if you'd rather run them yourself or you're on a different distro.

## Self-updating

```bash
hepyy-pod --update            # overwrite this script with the latest "main"
hepyy-pod --update v0.2.29    # pin to a specific tag instead
```

Fetches `contrib/podman/hepyy-pod.sh` from the given ref, checks it looks
like a shell script and passes a syntax check, then replaces the running
script file in place -- keeping the previous copy as `<script>.bak` next to
it. Does not touch the `Dockerfile` or any built images/packages.

## Versioning

This directory is versioned together with the rest of `hepyy`. Pin the
`HEPYY_POD_REF` env var (or the tag in your clone/curl command) to a specific
release tag for reproducible builds; `main` may change the Dockerfile's
package set over time.
