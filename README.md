# hepyy

A local HEP C++ package manager that downloads, compiles, and exposes packages as Python
modules via [cppyy](https://cppyy.readthedocs.io/) — no ROOT, no conda, no system-wide
installs required.

Supported packages out of the box: **FastJet**, **Pythia8**, **HepMC3**, **fjcontrib**, **LHAPDF6**.

> **Step-by-step examples for common setups** (local, Colab, HPC, Jupyter, ROOT, shared packages):
> [WORKFLOW-EXAMPLE.md](WORKFLOW-EXAMPLE.md)

---

## Requirements

- Python 3.9+ in a virtual environment (strongly recommended)
- A C++ compiler: `clang++` (macOS) or `g++` (Linux)
- `cmake` (for HepMC3)
- `swig` (for LHAPDF Python bindings — optional but recommended)
- Internet access for first-time package downloads

On macOS with Homebrew:
```bash
brew install cmake swig
```

---

## Installation

Create and activate a virtual environment, then install hepyy:

> **Short aliases:** `heyy` and `her` are registered as identical entry points alongside
> `hepyy` — use whichever you prefer.
> ```bash
> heyy install fastjet
> her list
> hepyy config   # all three are the same CLI
> ```

```bash
python -m venv myenv
source myenv/bin/activate

# From PyPI (once published):
pip install hepyy

# Or directly from GitHub (no clone needed):
pip install git+https://github.com/matplo/hepyy.git

# To update to the latest version (once inside an activated venv):
heyy upgrade

# Or manually with pip / uv:
pip install --force-reinstall git+https://github.com/matplo/hepyy.git
uv pip install --reinstall git+https://github.com/matplo/hepyy.git

# Or from a local clone (editable install for development):
git clone https://github.com/matplo/hepyy
cd hepyy
pip install -e .
```

---

## Google Colab

hepyy works in [Google Colab](https://colab.research.google.com) without any local setup.
Use `!` to run shell commands from a notebook cell:

```python
# Cell 1 — install hepyy
!pip install git+https://github.com/matplo/hepyy.git

# Cell 2 — initialise (creates package store, patches cppyy)
!hepyy init

# Cell 3 — build HEP packages (~10–20 min first time; Colab has 2+ cores)
!hepyy install fastjet hepmc3 lhapdf pythia8 fjcontrib --verbose

# Cell 4 — use them
import hepyy
hepyy.load('fastjet')
hepyy.load('fjcontrib')
hepyy.load('pythia8')

import cppyy, pythia8, fastjet, fjcontrib
# → ready to use
```

**Notes:**
- Each Colab runtime is ephemeral — packages must be reinstalled when the runtime resets.
  The build takes ~10–20 min; consider saving the compiled packages to Google Drive and
  registering them with `hepyy register` to avoid rebuilding every session.
- `--verbose` shows live build output, which is useful in Colab to confirm progress.
- After `hepyy init`, download the latest demo notebooks with:
  ```
  !hepyy demos
  ```
  This fetches all demo files from GitHub into `./hepyy_demos/`. Re-run after
  `heyy upgrade` to pick up new or updated demos.
- See `demos/demo_softdrop_splitting.ipynb` for a complete worked example you can open
  directly in Colab.

---

## Initialise

Run once after installation to create the package store, fetch recipes, and check cppyy:

```bash
hepyy init
```

This creates the package store under your active venv and automatically clones the
[hepyy-recipes](https://github.com/matplo/hepyy-recipes) repository so the
latest recipes are always available:

```
<venv>/hepyy_packages/
  registry.json       ← installed package index
  src/                ← cached tarballs (safe to delete to free space)
  logs/               ← build logs
  recipe-cache/       ← cloned recipe repos
  recipe-sources.json ← registered recipe sources
```

`init` also checks whether the cppyy backend (`libCling`) has broken library references
(common on macOS when the cppyy wheel was built against a different package manager).
When running inside a virtual environment, broken paths are **patched automatically** —
only files inside the venv are ever modified.

If the auto-fix cannot run (e.g. outside a venv, or `install_name_tool` / `patchelf`
is missing), inspect and patch manually:

```bash
# Inspect only:
hepyy fix-cppyy --check

# Patch:
hepyy fix-cppyy
```

To upgrade hepyy itself to the latest GitHub version from inside an active venv:
```bash
hepyy upgrade
```
This uses `uv pip install --reinstall` (or `pip --force-reinstall`) to bypass the
package cache. Re-enter the subshell after upgrading to pick up new entry points.

To refresh recipes at any time (e.g. after a new recipe is added upstream):
```bash
hepyy recipe update
```

Check where your packages will be installed:
```bash
hepyy config
```

Override the location at any time:
```bash
# Environment variable (shell session)
export HEPYY_PACKAGES_DIR=/opt/hep/packages

# Or permanently in .hepyy.toml at your project root:
# packages_dir = "/opt/hep/packages"
```

---

## Installing packages

### Recommended install order

Install order matters for Pythia8: it is built with optional support for FastJet, HepMC3,
and LHAPDF6 **only if those packages are already present in the registry at configure time**.
No explicit dependency is declared — if a package is installed, Pythia8 picks it up
automatically; if not, that interface is simply omitted.

You can pass multiple package names to `install` and they are built **sequentially in the
order given** — which is all that is needed to satisfy the implicit Pythia8 dependencies:

```bash
hepyy install fastjet hepmc3 lhapdf pythia8 fjcontrib
```

Or one at a time:

```bash
hepyy install fastjet           # (1) jet finding
hepyy install hepmc3            # (2) event record I/O
hepyy install lhapdf            # (3) PDF sets
hepyy install pythia8           # (4) sees fastjet + hepmc3 + lhapdf → adds --with-* flags
hepyy install fjcontrib         # (5) jet substructure (hard-requires fastjet)
```

During the Pythia8 build you will see which packages were detected:
```
[pythia8] FastJet : .../hepyy_packages/fastjet/3.5.1
[pythia8] HepMC3  : .../hepyy_packages/hepmc3/3.3.1
[pythia8] LHAPDF6 : .../hepyy_packages/lhapdf/6.5.4
[pythia8] configure: --with-fastjet3=... --with-hepmc3=... --with-lhapdf6=...
```

### Version precedence

The registry stores **one active entry per package name** — the last-installed version.
If you install fastjet 3.4 and then fastjet 3.5, only 3.5 is visible to subsequent builds.
To control which version Pythia8 sees, install (or `register`) the desired fastjet version
**before** running `hepyy install pythia8`.

### Useful flags

```bash
hepyy install fastjet --verbose          # show build output live
hepyy install fastjet --force            # re-extract and rebuild (keeps cached tarball)
hepyy install fastjet --redownload       # delete tarball and start completely fresh
hepyy install fastjet --clean            # wipe only build artifacts, keep extracted source
hepyy install fastjet -j 8              # use 8 parallel make jobs (overrides recipe default of 4)

# Flags apply to all packages when multiple names are given:
hepyy install fastjet hepmc3 lhapdf pythia8 fjcontrib --verbose
hepyy install fastjet hepmc3 lhapdf pythia8 fjcontrib -j 8

# --version and --recipe only take effect for a single-package install:
hepyy install fastjet --version 3.4.2
hepyy install mypackage --recipe /path/to/mypackage/1.0.yaml
```

`--clean` is useful on slow network mounts (e.g. Google Drive) where re-extracting
a large tarball is expensive: it removes cmake build dirs or runs `make clean` for
autotools packages, without touching the already-extracted source tree.

### Inspecting what is installed

```bash
hepyy list               # all installed packages with versions and prefixes
hepyy info fastjet       # full details for one package
```

---

## Using packages in Python

### Loading with hepyy

```python
# With the module system (recommended):
#   module load fastjet pythia8 fjcontrib
#   python myscript.py
# then in myscript.py just:
import fastjet, pythia8, fjcontrib   # autoload hook has already set everything up

# Without the module system (Colab, bare venv):
import hepyy
hepyy.load("fastjet")
hepyy.load("pythia8")
hepyy.load("fjcontrib")   # hepyy.load() is a no-op if already loaded

# Or pass a list — packages are loaded in order:
hepyy.load(["fastjet", "pythia8", "fjcontrib"])

import fastjet, pythia8, fjcontrib

# Either way, packages are available as cppyy proxies:
import cppyy
jet = fastjet.PseudoJet(1.0, 0.0, 1.0, 1.414)
print(jet.pt())
```

### ROOT — PyROOT via native Python bindings

ROOT is available via the [hepyy-recipes](https://github.com/matplo/hepyy-recipes)
repository (not built-in). Install and use it with:

```bash
heyy recipe update          # pull latest recipes including root
heyy install root           # builds ROOT 6.40.00 (~30 min first time)
```

```python
import hepyy
hepyy.load("root")      # adds ROOT's lib/ to sys.path; does NOT import pip-cppyy
import ROOT
h = ROOT.TH1F("h", "h", 100, 0, 100)
h.Fill(42)
```

**ROOT ships its own cppyy and cling** — a different build from the pip-installed cppyy
that hepyy uses for FastJet, Pythia8, etc. Because of this:

- `hepyy.load("root")` only adds ROOT's `lib/` directory to `sys.path`; it does
  **not** import pip-cppyy. ROOT's `_facade.py` then finds ROOT's own `cppyy` package
  (also in `lib/`) and initialises correctly.
- **Mixing ROOT and pip-cppyy packages in the same session works for typical HEP
  workflows** (generate/cluster with fastjet or pythia8, fill ROOT histograms) in
  ROOT 6.28+. The risk arises when passing C++ objects *across* the two cling contexts —
  e.g. handing a `fastjet::PseudoJet*` directly to a ROOT-compiled function.
- With `module load`, the auto-load hook handles `hepyy.load()` automatically so
  your script can go straight to `import fastjet; import ROOT`.
- Recommended patterns:

  ```python
  # Pattern A — ROOT only session
  import ROOT   # module load root handles hepyy.load('root') automatically

  # Pattern B — cppyy packages only session (module load fastjet pythia8)
  import fastjet, pythia8

  # Pattern B+ROOT — typical mixed session (module load root fastjet pythia8)
  # autoload loads root FIRST → ROOT's cppyy wins → all packages share ROOT's cling
  import fastjet, pythia8   # loaded via ROOT's cppyy/cling
  import ROOT               # same cling — works cleanly
  # fill histograms, write ROOT files — just avoid passing C++ objects between clings

  # Pattern C — ROOT owns cling, other libs loaded via ROOT's own interface
  import ROOT
  hepyy.gSystem_load('fastjet')   # no pip-cppyy involved at all
  hepyy.gSystem_load('pythia8')
  p = ROOT.Pythia8.Pythia()
  j = ROOT.fastjet.PseudoJet(1, 0, 1, 1.4)
  ```

`hepyy.gSystem_load(name)` looks up the installed library path from the registry
and calls `ROOT.gSystem.Load()` for you — no hardcoded paths needed.

hepyy emits a `UserWarning` when ROOT and cppyy packages are loaded in the same
session so the potential conflict is visible at runtime.

> **`module load root` with the auto-load hook:** when ROOT is among the module-loaded
> packages, hepyy loads it first so ROOT's `lib/` is in `sys.path` before the first
> `import cppyy`. ROOT's bundled cppyy is then used for all packages — one cling for
> everything. If ROOT is *not* module-loaded, hepyy strips ROOT's `lib/` from
> `DYLD_LIBRARY_PATH` before loading pip-cppyy to prevent ROOT's `libcling.dylib` from
> shadowing cppyy_backend's own cling.

> **HPC systems with GCC 14+ (NERSC Perlmutter, etc.):** pip-cppyy ships a
> pre-built cling 16 that is incompatible with GCC 14 system headers — the PCH
> build fails and cppyy crashes. **Installing ROOT via hepyy is the recommended
> fix**: ROOT builds its own cling with the system's compiler, so on a GCC 14 system
> ROOT's cling is GCC 14 compatible. Loading ROOT first makes fastjet, pythia8, and
> all other packages share ROOT's cling instead of pip-cppyy's broken one.
>
> ```bash
> heyy recipe update
> heyy install root              # ~30 min first time; builds ROOT with system GCC 14
> ```
>
> ```python
> import hepyy
> hepyy.load('root')         # ROOT's cling — GCC 14 compatible, no PCH issues
> hepyy.load('fastjet')
> hepyy.load('pythia8')
> import ROOT, fastjet, pythia8  # all share ROOT's cling
> ```
>
> With `module load`, listing `root` is enough — hepyy loads it first automatically:
> ```bash
> module load root fastjet pythia8
> python script.py               # fastjet and pythia8 use ROOT's cling
> ```

> **macOS with a current SDK:** the same class of problem as above, different
> cause — pip-cppyy's `cling` (LLVM 16) can't parse the C++ headers in
> current macOS SDKs, so the first `import cppyy` crashes building its PCH
> cache. hepyy warns about this before it happens (pointing here) instead of
> leaving you to decode the crash. Fix:
> ```bash
> heyy recipe update
> heyy install cppyy --force   # ~10-30 min, one-time; builds cling pinned to
>                               # an older, compatible SDK — no runtime workaround
>                               # needed afterward
> ```
> Build it once into a shared `HEPYY_PACKAGES_DIR` and every `henv`-created env
> can reuse it via `--system-packages-dir` instead of rebuilding per env — see
> henv's [Fixing a broken binary cppyy wheel](https://github.com/matplo/henv#fixing-a-broken-binary-cppyy-wheel).
> `heyy install root` (above) is also a valid alternative here, for the same
> reason: ROOT bundles its own, newer `cling`.

### LHAPDF — native Python bindings

LHAPDF is built with SWIG Python bindings. After `hepyy install lhapdf` the module
is installed directly into your venv — **no `hepyy.load()` needed**:

```python
import lhapdf                          # works straight away
pdf = lhapdf.mkPDF("CT10nlo", 0)
xg  = pdf.xfxQ(21, 0.01, 91.2)        # gluon PDF at x=0.01, Q=91.2 GeV
print(f"xg(x=0.01, Q=Mz) = {xg:.4f}")
```

For C++ interop (passing `LHAPDF::PDF*` to other cppyy-loaded code):

```python
hepyy.load("lhapdf")               # loads the C++ library via cppyy
import cppyy
pdf = cppyy.gbl.LHAPDF.mkPDF("CT10nlo", 0)
```

---

## Installing LHAPDF PDF sets

LHAPDF ships no PDF sets by default. Load the package first so `lhapdf` is on
your PATH, then install sets by name:

```bash
module load lhapdf

lhapdf install CT10nlo
lhapdf install NNPDF31_nnlo_as_0118
lhapdf install CT18NLO

lhapdf list --installed   # what is already downloaded
```

PDF data files are stored under:
```
<packages_dir>/lhapdf/6.5.4/share/LHAPDF/<SetName>/
```

Add that directory to `LHAPDF_DATA_PATH` if you keep PDF sets elsewhere:
```bash
export LHAPDF_DATA_PATH=/data/pdfsets:$LHAPDF_DATA_PATH
```

> **Without `module load`:** use the full path directly:
> ```bash
> $(hepyy info lhapdf | awk '/^prefix/{print $2}')/bin/lhapdf install CT10nlo
> ```

---

## Shell completion

Enable tab completion for `heyy`, `her`, and `hepyy` in one line.

**Zsh** — add to `~/.zshrc`:
```zsh
eval "$(heyy completion)"
```

**Bash** — add to `~/.bashrc`:
```bash
eval "$(heyy completion)"
```

The bash script uses `complete -F` / `compgen -W` and works with bash 3.2+,
including the macOS system bash. No version upgrade required.

**Fish** — add to `~/.config/fish/config.fish`:
```fish
heyy completion --shell fish | source
```

After reloading your shell, pressing `<Tab>` completes commands, subcommands, and options:
```
heyy <Tab>               # install  list  avail  info  env  kernel  recipe  …
heyy install <Tab>       # (available package names from recipes)
heyy kernel <Tab>        # install  list  update  uninstall
heyy kernel install --<Tab>  # --name  --display-name  --sys-prefix
```

The `--shell` flag forces a specific shell if auto-detection is wrong:
```bash
heyy completion --shell bash
```

---

## Shell module system

### TCL modulefiles (Lmod / Environment Modules)

If your site uses Lmod or Environment Modules, hepyy can generate standard TCL
modulefiles for all installed packages:

```bash
hepyy generate-modules        # write/refresh modulefiles for all installed packages
```

Modulefiles are written to `<packages_dir>/modulefiles/<name>/<version>` and include
`PATH`, `LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH`, `PYTHONPATH` (for packages with Python
bindings), and `CPATH`. Re-run after installing new packages to keep them up to date.

To add the directory to your active module search path:

```bash
eval "$(hepyy modules)"       # runs: module use <packages_dir>/modulefiles
hepyy modules-path            # print the modulefiles path only (no 'module use' prefix)
```

After that, standard `module` commands work as usual:

```bash
module load lhapdf/6.5.5
module load jewel/2.4.0
module list
```

> **Tip:** add `eval "$(hepyy modules)"` to your `~/.bashrc` / `~/.zshrc` so the
> modulefiles directory is always in the search path.

### Python auto-load via `module load`

`heyy generate-modules` installs a `hepyy_autoload.pth` file into the venv's
`site-packages`. Python processes `.pth` files at startup, so any package loaded
with `module load` before starting Python is available to import directly — no
`hepyy.load()` call needed:

```bash
eval "$(heyy modules)"            # register modulefiles dir (once, or in ~/.bashrc)
heyy generate-modules             # write modulefiles + install autoload hook

module load fastjet
module load pythia8

python -c "import fastjet, pythia8; print(fastjet.PseudoJet)"
```

For Jupyter notebooks or scripts that run without `module load`, the explicit call
still works as before:

```python
import hepyy
hepyy.load("fastjet")
import fastjet
```

> **Note:** the `.pth` hook imports `hepyy` at Python startup when any
> `HEPYY_LOADED_*` env var is set. When no modules are loaded the check is
> a single `any()` scan of `os.environ` — effectively free.

---

## Examples

Demo scripts live in the `demos/` directory:

| Script | What it shows |
|--------|---------------|
| `demos/demo_fastjet.py` | Basic FastJet jet finding |
| `demos/demo_pythia_fastjet.py` | Pythia8 + FastJet: event generation and jet clustering |
| `demos/demo_pythia_fastjet.ipynb` | Same as above in a Jupyter notebook |
| `demos/demo_pythia_fastjet_root.py` | Pythia8 + FastJet → ROOT TTree ntuple written to a .root file (requires root) |
| `demos/demo_fjcontrib.py` | SoftDrop, Nsubjettiness τ₂₁, EnergyCorrelator C₂ on Pythia8 dijets |
| `demos/demo_fjcontrib.ipynb` | Same as above in a Jupyter notebook with per-jet inspector table |
| `demos/demo_softdrop_splitting.ipynb` | SoftDrop splitting function: $z_g$ and $\theta_g$ distributions ([open in Colab](https://colab.research.google.com/github/matplo/hepyy/blob/main/demos/demo_softdrop_splitting.ipynb)) |

Run:
```bash
hepyy install fastjet pythia8 fjcontrib   # first time only
python demos/demo_fjcontrib.py
```

To get the latest demos after an upgrade (demos are not part of the installed package):
```bash
heyy demos                # downloads all demos into ./hepyy_demos/
heyy demos --overwrite    # re-download even if files already exist
```

For Jupyter / JupyterHub:
```bash
pip install jupyter matplotlib numpy ipykernel
heyy kernel install               # register the venv as a selectable kernel
jupyter notebook demos/demo_fjcontrib.ipynb
```

Select the `HEP (...)` kernel when prompted, or use `--kernel hepyy-<venv>` on the
command line. After installing more packages, run `heyy kernel update` to refresh the
kernel spec. See the [Jupyter kernel](#jupyter-kernel) section for full options.

---

## Jupyter kernel

Register the current venv as a Jupyter kernel so it can be selected in JupyterHub or
JupyterLab:

```bash
pip install ipykernel          # once, if not already installed
heyy kernel install
```

The kernel spec embeds `PATH`, `DYLD_LIBRARY_PATH`/`LD_LIBRARY_PATH`, `PYTHONPATH`, and
`HEPYY_PACKAGES_DIR` for every installed package, so notebooks can immediately do:

```python
import hepyy
hepyy.load("fastjet")

import lhapdf          # works directly — PYTHONPATH is already set
```

### Kernel naming and multiple environments

Each venv gets an automatically distinct kernel name: **`hepyy-<venv-name>`**. If you
maintain separate environments for different projects — say `henv-fastjet` and
`henv-pythia` — running `heyy kernel install` from inside each one produces
`hepyy-henv-fastjet` and `hepyy-henv-pythia` as separate kernels with no extra
flags. You only need `--name` if you want something more descriptive than the venv
directory name.

The display name shown in JupyterLab defaults to `HEP (<package list>)` so you can
immediately tell what is available in each kernel without opening it.

### Install options

```bash
heyy kernel install --name my-hep-env          # custom kernel slug
heyy kernel install --display-name "HEP 2026"  # custom label in JupyterHub/Lab
heyy kernel install --sys-prefix               # install into sys.prefix (shared JupyterHub)
```

### Updating after new package installs

After `heyy install <pkg>`, refresh the kernel to pick up the new paths:

```bash
heyy kernel update              # refresh current venv's kernel
heyy kernel update hepyy-henv-dev   # refresh a named kernel
```

`kernel update` is equivalent to re-running `kernel install` with the same name, but
it fails with a clear error (and a hint to run `kernel install`) if no kernel exists yet,
rather than silently creating one.

### Listing and removing kernels

```bash
heyy kernel list                         # show all hepyy-managed kernels
heyy kernel uninstall hepyy-henv-dev # remove one (name from 'kernel list')
```

`kernel list` shows only kernels created by hepyy (identified by metadata written at
install time). `kernel uninstall` refuses to touch kernels not managed by hepyy.

---

## Shared packages on a cluster

On an HPC cluster a single set of precompiled packages can be shared across
user accounts. No one else needs to rebuild — they just point hepyy at the
shared directory and generate their own kernel spec.

### Option 1 — shared filesystem (NFS, GPFS, Lustre, …)

**Admin / package builder** (once):
```bash
export HEPYY_PACKAGES_DIR=/shared/hep/packages
heyy init
heyy install fastjet hepmc3 lhapdf pythia8 fjcontrib
heyy generate-modules   # optional: write Lmod/TCL modulefiles into the same tree
```

**Each user** (no compilation needed):
```bash
export HEPYY_PACKAGES_DIR=/shared/hep/packages
heyy kernel install          # writes a personal kernel.json pointing at the shared packages
```

Then in a notebook or script:
```python
import hepyy
hepyy.load('fastjet')
hepyy.load('pythia8')
import fastjet, pythia8   # ready — no build, no wait
```

> **Tip:** add `export HEPYY_PACKAGES_DIR=/shared/hep/packages` to
> `~/.bashrc` / `~/.bash_profile`, or set it from your site's module system,
> so it is always active.

Each user's `heyy kernel install` creates a `kernel.json` in their own
`~/.local/share/jupyter/kernels/` that references the shared packages. The
packages themselves are never copied. To manage kernels:
```bash
heyy kernel list                         # show hepyy-managed kernels
heyy kernel update                       # refresh after the admin installs new packages
heyy kernel uninstall hepyy-myenv    # remove (name from 'kernel list')
```

### Option 2 — packages built by another tool

If your packages were compiled by [yasp](https://github.com/matplo/yasp) or
another build system, register them without rebuilding:
```bash
export HEPYY_PACKAGES_DIR=/shared/hep/packages
heyy register fastjet --prefix /path/to/fastjet/3.5.1 --version 3.5.1
heyy register pythia8 --prefix /path/to/pythia8/8.317  --version 8.317
heyy kernel install   # now embeds the registered prefixes
```

### Option 3 — portable tarball (no shared filesystem)

Pack on the source machine:
```bash
tar -czf hep-packages.tar.gz -C /shared/hep/packages .
```

Unpack on the target machine (OS and Python version must be compatible):
```bash
mkdir -p ~/.henvs/default
tar -xzf hep-packages.tar.gz -C ~/.henvs/default
export HEPYY_PACKAGES_DIR=~/.henvs/default
heyy kernel install
```

---

## Registering externally-built packages

If you already have a package built by another tool (e.g. [yasp](https://github.com/matplo/yasp)):

```bash
hepyy register fastjet --prefix /path/to/fastjet/3.5.1
hepyy register fastjet --prefix /path/to/fastjet/3.5.1 --version 3.5.1
```

---

## External recipe sources

hepyy ships built-in recipes for FastJet, HepMC3, LHAPDF6, Pythia8, and fjcontrib.
You can extend this with recipes from a GitHub repository or use a one-off recipe file
from anywhere on disk.

### GitHub recipe source

The [matplo/hepyy-recipes](https://github.com/matplo/hepyy-recipes) repository
is registered automatically by `hepyy init`. You can add further repos the same way:

Point hepyy at a GitHub repo and it will clone it locally and search it automatically
on every `install` and `avail` call:

```bash
# Whole repo (recipes expected at <name>/<version>.yaml under the root)
hepyy recipe add https://github.com/user/my-hep-recipes

# Subdirectory of a repo
hepyy recipe add https://github.com/matplo/yasp/tree/main/recipes
```

Manage sources:
```bash
hepyy recipe list-sources    # show all registered sources
hepyy recipe update          # git pull on all sources (refresh)
hepyy recipe remove https://github.com/user/my-hep-recipes
```

Once added, packages from that source appear in `hepyy avail` and can be installed
by name like any built-in:
```bash
hepyy avail                  # shows built-in + remote recipes
hepyy install mypackage      # finds recipe in remote source automatically
```

### One-off recipe file

To use a single recipe file without registering a source:

```bash
hepyy install mypackage --recipe /path/to/mypackage/1.0.yaml
```

The `--recipe` flag accepts any absolute or relative path and overrides the built-in
and remote source search for that invocation.

### Recipe format

Recipes are YAML files named `<version>.yaml` inside a `<name>/` directory:

```
my-recipes/
  fastjet/
    3.5.1.yaml
  mycustomlib/
    2.0.yaml
```

See the built-in recipes under `src/hepyy/recipes/` for the full format reference.

### VCS-based recipes (git / svn)

If a package has no tarball (e.g. SVN-only like POWHEG, or a rolling git branch), omit
the `url` field. hepyy will skip the download step and run `build_script` directly
from an empty working directory — the script is responsible for fetching its own source:

```yaml
name: powheg
version: "v2"
# no url — build_script fetches via SVN
build_system: script
build_script: |
  svn co svn://powhegbox.mib.infn.it/trunk/POWHEG-BOX-V2 powheg-box
  cd powheg-box
  make -j{n_cores} pwhg_main
  ...
```

### Recipe scripting gotchas

Build scripts are processed by Python's `str.format_map()` before being passed to bash.
This means **any `{...}` in the script is treated as a template variable**, including:

| Pattern | Problem | Fix |
|---------|---------|-----|
| `${VAR:-default}` | `{VAR:-default}` consumed by format_map | Use `if [ -z "$VAR" ]; then VAR=default; fi` |
| `find -exec cp {} \;` | `{}` is a positional field | Escape as `{{}}` |
| Comments containing `{...}` | Also substituted | Remove or reword the comment |

Heppyyier template variables available in every script:
`{prefix}`, `{version}`, `{n_cores}`, `{srcdir}`, `{builddir}`, `{CXX}`, `{CC}`,
and `{<name>_prefix}` for every package currently in the registry.

---

## Configuration reference

| Method | Key | Example |
|--------|-----|---------|
| Env var | `HEPYY_PACKAGES_DIR` | `export HEPYY_PACKAGES_DIR=/opt/hep` |
| `.hepyy.toml` | `packages_dir` | `packages_dir = "/opt/hep"` |
| Default (venv) | — | `<venv>/hepyy_packages/` |
| Default (no venv) | — | `./packages/` |

Legacy env var `HEPYY_BUILD_DIR` and toml key `build_dir` are still accepted.
