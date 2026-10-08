# hepyy + podman

A rootless, GPU-aware podman/container setup for building and running
`hepyy`-managed packages (Python 3.11, C++, Fortran toolchain included).

## Quick start

Download the script, inspect it, then run it (recommended over piping
`curl | bash` blindly):

```bash
curl -fsSL https://raw.githubusercontent.com/matplo/hepyy/v0.2.22/contrib/podman/hepyy-pod.sh -o hepyy-pod.sh
chmod +x hepyy-pod.sh
less hepyy-pod.sh   # read it before running, especially the first time
./hepyy-pod.sh build
./hepyy-pod.sh run
```

If you only downloaded `hepyy-pod.sh` (no `Dockerfile` next to it), `build`
automatically fetches the matching `Dockerfile` from the same pinned repo tag.

If you'd rather clone the whole thing:

```bash
git clone --branch v0.2.22 https://github.com/matplo/hepyy
cd hepyy/contrib/podman
./hepyy-pod.sh build
./hepyy-pod.sh run
```

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
    to `./hepyy-packages-<image-tag>` next to the script if omitted.
  - GPU passthrough is handled automatically: CDI (`--device
    nvidia.com/gpu=all`) on podman >= 4.1, or the legacy
    `nvidia-container-runtime` wrapper on older podman (e.g. the podman 3.4.x
    that ships with Ubuntu 22.04).

Run `./hepyy-pod.sh --help` for the full option/override list (including
`NO_CUDA=1`, `CUDA_VERSION=`, `CUDA_BASE_IMAGE=` env overrides, and the
`nvidia-container-toolkit` setup commands if GPU detection finds a driver but
no working passthrough mechanism).

## No sudo required

Everything here runs rootless (`podman` with `--userns=keep-id`). The only
exception is a one-time host setup if you want GPU passthrough and don't
already have `nvidia-container-toolkit` installed -- `--help` prints the
exact 3 commands needed, which do require `sudo`.

## Versioning

This directory is versioned together with the rest of `hepyy`. Pin the
`HEPYY_POD_REF` env var (or the tag in your clone/curl command) to a specific
release tag for reproducible builds; `main` may change the Dockerfile's
package set over time.
