# hepyy — workflow examples

Quick-reference for the most common setups. Jump to the section that matches your situation.

---

## Prerequisites

### hepyy

Install into any Python virtual environment:

```bash
pip install git+https://github.com/matplo/hepyy.git
```

### henv (recommended)

[henv](https://github.com/matplo/henv) is a single-script virtual environment manager
designed for hepyy workflows. It creates and activates venvs, installs hepyy
on first use, wires up tab completion, regenerates modulefiles, and handles
`HEPYY_PACKAGES_DIR` / `HEPYY_SYSTEM_PACKAGES_DIR` automatically.

Install once (requires `curl`):

```bash
curl -fsSL https://raw.githubusercontent.com/matplo/henv/main/henv | bash -s -- --install
```

This places `henv` in `~/.local/bin/`. Make sure that directory is in your `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.bashrc or ~/.zshrc
```

Verify:
```bash
henv --version
```

henv is optional — all hepyy commands work in any plain venv. The workflows below
use `henv .` for convenience, but any `henv` call can be replaced with:

```bash
python -m venv .venv && source .venv/bin/activate
pip install git+https://github.com/matplo/hepyy.git
heyy init
```

---

## 1. Local development (macOS / Linux laptop)

The default setup — packages live inside your venv, nothing shared.

```bash
# One-time: create a venv and install hepyy
pip install henv        # or: curl … ~/.local/bin/henv
henv .                  # create .venv in current dir, install hepyy, drop in

# Build packages (inside the henv subshell):
heyy install fastjet hepmc3 lhapdf pythia8 fjcontrib

# Use in Python:
python my_analysis.py   # if you used 'module load' in the subshell
# or explicitly:
python -c "
import hepyy
hepyy.load('fastjet')
hepyy.load('pythia8')
import fastjet, pythia8
print(fastjet.PseudoJet(1,0,1,1.4).pt())
"

exit                    # leave the henv subshell
```

Re-entering later (no rebuild):
```bash
henv .                  # existing env — activates immediately, no prompts
```

---

## 2. Google Colab (ephemeral runtime + Google Drive cache)

Colab runtimes reset on disconnect. The two-tier package system maps naturally
to Colab: persistent Drive storage acts as the package store, and anything
installed in the current session stays local to `/content/`.

### 2a. Personal Drive (single user)

You own the Drive folder — read and write go to the same place.

```python
# ── Cell 1: always run ─────────────────────────────────────────────────────
!pip install git+https://github.com/matplo/hepyy.git -q

from google.colab import drive
drive.mount('/content/drive')

import os
os.environ["HEPYY_PACKAGES_DIR"] = "/content/drive/MyDrive/hep_packages"

# ── Cell 2: build once, then comment out for future sessions ───────────────
# !heyy init
# !heyy install fastjet hepmc3 lhapdf pythia8 fjcontrib --verbose

# ── Cell 3: every session ──────────────────────────────────────────────────
import hepyy
hepyy.load("fastjet")
hepyy.load("pythia8")
import fastjet, pythia8
```

### 2b. Shared folder (course / team)

An instructor or admin pre-builds packages to a Google Drive folder and shares
it. `HEPYY_SYSTEM_PACKAGES_DIR` is just a filesystem path — it can point at:

- A folder shared with you (add a shortcut so it appears under `MyDrive/`)
- A Team Drive / Shared Drive
- Any other readable path on the Colab instance

Students set the shared folder as the read-only system base and write any
personal additions to a local (session-only) path.

> **Important:** mount Google Drive **before** calling `hepyy.load()`.
> The package registry and C++ headers are read from Drive at load time — if
> Drive isn't mounted yet, headers can't be included and the proxy module will
> be created but attribute access will fail silently.

```python
# ── Cell 1: always run ─────────────────────────────────────────────────────
# Use pip (not uv pip) — uv installs headers to a non-standard path that
# breaks cppyy's CPyCppyy API lookup, silently corrupting C++ namespace bindings.
!pip install git+https://github.com/matplo/hepyy.git -q

# Mount Drive FIRST — hepyy reads headers and registry from Drive at load time.
# If Drive isn't mounted before hepyy.load(), C++ headers can't be included
# and the proxy module will be created but every attribute access will fail.
from google.colab import drive
drive.mount('/content/drive')

import os
# Shared pre-built packages — adjust path to wherever the instructor shared the folder
os.environ["HEPYY_SYSTEM_PACKAGES_DIR"] = \
    "/content/drive/MyDrive/HEPcourse_packages"   # shared folder shortcut in My Drive
# Personal writable store — local to this session (lost on runtime reset, that's fine)
os.environ["HEPYY_PACKAGES_DIR"] = "/content/hep_packages_user"

# ── Cell 2: instructor only — build once and share ─────────────────────────
# Run this cell once from the instructor's account, then comment it out.
# cppyy does NOT need to be in the shared prefix — students pip-install it above.
# import os
# os.environ["HEPYY_PACKAGES_DIR"] = "/content/drive/MyDrive/HEPcourse_packages"
# !heyy upgrade && heyy recipe update
# !heyy install fastjet hepmc3 lhapdf pythia8 fjcontrib --verbose
# !heyy generate-modules

# ── Cell 3: every session (students) ───────────────────────────────────────
import hepyy
hepyy.load("fastjet")
hepyy.load("pythia8")
import fastjet, pythia8
```

> **Compatibility note:** compiled packages (ELF binaries) are platform-specific.
> Colab-built packages work on Colab; NERSC-built packages work on NERSC.
> Do not mix across incompatible systems.

---

## 3. HPC — single user (NERSC, Perlmutter, etc.)

Packages in your own directory; no sharing, no special flags.

```bash
# Set a persistent location (add to ~/.bashrc):
export HEPYY_PACKAGES_DIR=$HOME/.hepyy_packages

# Create and enter a venv (henv auto-detects HEPYY_PACKAGES_DIR):
henv .

# Build packages (first time; cppyy may take 30-90 min on NERSC):
heyy recipe update
heyy install fastjet hepmc3 lhapdf pythia8 fjcontrib
heyy install cppyy --force        # builds cling from source with system g++ (GCC 13)

# Generate Lmod/TCL modulefiles:
heyy generate-modules
# henv already ran 'eval "$(heyy modules)"' on subshell entry — module load works immediately

# Load and use:
module load fastjet pythia8
python analysis.py
```

> **NERSC / SUSE Linux note:** the binary pip-cppyy wheel is incompatible with
> SUSE GCC headers. `heyy install cppyy --force` builds cling from source with
> the system `g++` (GCC 13) and resolves the issue permanently.

---

## 4. HPC — admin builds, users share (read-only shared filesystem)

An admin builds the packages once; all users on the system can load them
without any compilation.

### Admin (once):
```bash
export HEPYY_PACKAGES_DIR=/global/cfs/cdirs/myproject/hep_packages
henv --packages-dir $HEPYY_PACKAGES_DIR .
heyy install fastjet hepmc3 lhapdf pythia8 fjcontrib
heyy install cppyy --force       # source build with system GCC
heyy generate-modules            # write modulefiles into the same tree
```

### Each user (no compilation):
```bash
# HEPYY_SYSTEM_PACKAGES_DIR = shared read-only base (admin's packages)
# HEPYY_PACKAGES_DIR        = user's own writable store (default: inside venv)

# First time — specify the shared dir explicitly.
# --no-cppyy removes the binary pip-cppyy wheel; the system source-built cppyy
# is picked up automatically via HEPYY_SYSTEM_PACKAGES_DIR.
# If the admin has already built cppyy with 'heyy install cppyy --force',
# --no-cppyy is applied automatically (no flag needed).
henv --system-packages-dir /global/cfs/cdirs/myproject/hep_packages --no-cppyy .
# heyy list         shows shared packages
# heyy install pkg  writes to .venv/hepyy_packages/ — never touches the shared dir
module load fastjet pythia8
python analysis.py
```

To avoid repeating the flag on every `henv .`, persist it in one of these ways:

```bash
# Option A — per-project (.hepyy.toml in the analysis directory):
echo 'system_packages_dir = "/global/cfs/cdirs/myproject/hep_packages"' >> .hepyy.toml
henv .   # picks it up automatically from the TOML file

# Option B — per-user (add to ~/.bashrc or site module system):
echo 'export HEPYY_SYSTEM_PACKAGES_DIR=/global/cfs/cdirs/myproject/hep_packages' >> ~/.bashrc
# henv inherits the env var from the parent shell — no flag needed
henv .
```

# Register a personal Jupyter kernel pointing at the shared packages:
export HEPYY_SYSTEM_PACKAGES_DIR=/global/cfs/cdirs/myproject/hep_packages
heyy kernel install

# Without henv (plain venv activation):
source .venv/bin/activate
export HEPYY_SYSTEM_PACKAGES_DIR=/global/cfs/cdirs/myproject/hep_packages
eval "$(heyy modules)"
module load fastjet pythia8
python analysis.py
```

---

## 5. HPC — two-tier: shared base + personal installs

Admin provides a read-only base; users can install additional packages to
their own directory without affecting anyone else.

### Admin (once):
```bash
export HEPYY_PACKAGES_DIR=/shared/hep/packages
heyy install fastjet hepmc3 lhapdf pythia8 fjcontrib cppyy --force
heyy generate-modules
```

### User B:
```bash
# My own writable dir (default: inside venv)
# Shared read-only base from admin
export HEPYY_SYSTEM_PACKAGES_DIR=/shared/hep/packages

henv --system-packages-dir /shared/hep/packages .
# Inside the subshell:
#   HEPYY_PACKAGES_DIR  = .venv/hepyy_packages/  (writable, user-local)
#   HEPYY_SYSTEM_PACKAGES_DIR = /shared/hep/packages  (read-only)

heyy list               # shows shared packages as if they were locally installed
heyy install myprivatelib   # goes to .venv/hepyy_packages/ only
python -c "import hepyy; hepyy.load('fastjet')"  # resolves from shared
```

Or configure permanently in `.hepyy.toml` at the project root:
```toml
# .hepyy.toml
system_packages_dir = "/shared/hep/packages"
```
`henv .` will then pick this up automatically on every activation.

---

## 6. Jupyter / JupyterHub

Register a kernel so notebooks can use all installed packages without any
`module load` in the terminal first.

```bash
pip install ipykernel
heyy kernel install                     # default name: hepyy-<venv>
heyy kernel install --display-name "HEP 2026"   # custom label in JupyterHub UI
heyy kernel install --sys-prefix        # install for all users on a JupyterHub
```

The kernel spec embeds `PATH`, `LD_LIBRARY_PATH`, `PYTHONPATH`, and
`HEPYY_PACKAGES_DIR` for every installed package. In a notebook cell:

```python
import hepyy
hepyy.load("fastjet")
hepyy.load("pythia8")
import fastjet, pythia8, cppyy
jet = fastjet.PseudoJet(1.0, 0.0, 1.0, 1.414)
print(jet.pt())
```

After installing new packages, refresh the kernel spec:
```bash
heyy kernel install          # same --name replaces the existing spec in place
```

For a shared JupyterHub pointing at the admin-built packages (workflow 4/5):
```bash
export HEPYY_PACKAGES_DIR=/shared/hep/packages
heyy kernel install --display-name "HEP shared" --sys-prefix
```

---

## 7. ROOT sessions

ROOT builds its own cling — preferred on HPC systems where pip-cppyy is
incompatible with the system GCC.

```bash
heyy recipe update
heyy install root           # ~30 min; builds ROOT with system compiler
```

```python
import hepyy
hepyy.load("root")      # ROOT's cling is now the active interpreter
hepyy.load("fastjet")   # uses ROOT's cling — no pip-cppyy conflict
hepyy.load("pythia8")
import ROOT, fastjet, pythia8
```

With `module load` the autoload hook loads ROOT first automatically:
```bash
module load root fastjet pythia8
python analysis.py          # all packages share ROOT's cling
```

---

## 8. Using packages registered from another build system

If packages were built by [yasp](https://github.com/matplo/yasp) or any other
tool, register the existing prefix without rebuilding:

```bash
heyy register fastjet --prefix /path/to/fastjet/3.5.1 --version 3.5.1
heyy register pythia8 --prefix /path/to/pythia8/8.317  --version 8.317
heyy kernel install
```

---

## Quick reference

| Goal | Command |
|------|---------|
| Create local venv + hepyy | `henv .` |
| Build all core packages | `heyy install fastjet hepmc3 lhapdf pythia8 fjcontrib` |
| Build cppyy from source (HPC) | `heyy install cppyy --force` |
| Share packages (admin) | `export HEPYY_PACKAGES_DIR=/shared/…; heyy install …` |
| Use shared packages (user, read-only) | `henv --system-packages-dir /shared/… .` |
| Add personal packages on top of shared | `heyy install mypkg` (writes to venv, not shared dir) |
| Register Jupyter kernel | `heyy kernel install` |
| Refresh modulefiles | `heyy generate-modules` |
| Update hepyy + recipes | `heyy upgrade && heyy recipe update` |
