# Pip-installable hepbundle

The pip bundle follows hepbundle: FastJet 3.5.3, fjcontrib 1.105, HepMC3
3.3.1, LHAPDF 6.5.5, and Pythia 8.317 built with all three external interfaces.
Wheel packaging revisions are pinned in pyproject.toml and the native lock.
On Linux x86_64, install into a fresh virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "hepyy[cppyy,hepbundle]>=0.2.31"
```

On macOS arm64 or Intel, use an activated conda-forge cppyy environment:

```sh
conda create -n hepbundle -c conda-forge python=3.12 cppyy pip
conda activate hepbundle
python -m pip install "hepyy[hepbundle]>=0.2.31"
```

If the activated environment already has compatible conda-forge cppyy, use just
the final pip command. cppyy stays optional so the conda-managed runtime remains
untouched. Use CPython >=3.10 for the complete bundle. Release CI covers Linux
Python 3.10/3.12 and both Mac architectures with conda-forge cppyy/Python 3.12;
local Apple Silicon checks also cover Python 3.14. Windows and Linux arm64 are
not included in this wheel matrix. cppyy's JIT needs a compatible C++ toolchain.
The base hepyy package and FastJet-only paths retain their own metadata.

## JEWEL C++ wheel

With cppyy available in the active environment, install the JEWEL C++ wheel
and the hepbundle dependencies together:

```sh
python -m pip install 'hepyy[hepbundle,jewel-cpp]>=0.2.33'
python -c 'import hepyy; hepyy.load("jewel_cpp"); import jewel_cpp'
```

The wheel reuses the pinned Pythia8 and LHAPDF wheels. Release builds test
the installed FastJet script and notebook on Linux x86_64 and macOS arm64
and Intel.

### Build and install a local wheel

From a jewel-cpp checkout in the build environment, run:

```sh
python -m pip install 'hepyy[hepbundle]' wheel
python tools/build_hepyy_wheel.py --output dist
```

From the hepyy checkout in the runtime environment, use the directory
containing the built wheel:

```sh
python -m pip install --find-links /path/to/jewel-cpp/dist '.[hepbundle,jewel-cpp]'
python -c 'import hepyy; hepyy.load("jewel_cpp"); import jewel_cpp'
```

## Local Glauber CLI wheel

From a `glauber-cpp` checkout, build the standalone command as a wheel:

```sh
python -m pip wheel . --no-deps --wheel-dir dist
```

From the hepyy checkout, install the extra using the local wheel directory:

```sh
python -m pip install --find-links /path/to/glauber-cpp/dist '.[glauber-cpp]'
glauber-pbpb pbpb-5020 6000 72913
```

The extra installs `glauber-pbpb` into the environment’s command directory.
The CLI needs only the platform’s C++ runtime. In the JEWEL C++ runner, use
`--centrality 0 10 --glauber-events pbpb-5020/events.csv` for a central Pb–Pb run.

## Import order

The native wheels provide libraries and headers. Call `hepyy.load()` once in
each Python process or notebook kernel before importing their cppyy proxy
modules:

```python
import hepyy
hepyy.load("fastjet")
import fastjet
```

For the whole bundle, use `hepyy.load("hepbundle")` before importing `fastjet`,
`fjcontrib`, `hepmc3` or `pythia8`. A bare `import fastjet` before initialization
can raise `ModuleNotFoundError`; rerun the load cell after a kernel restart.
The upstream `lhapdf` Python module and `lhapdf` command work directly.
Source module users may already have these proxies initialized by the shell
startup hook; explicit load calls remain safe in that case.

Install PDF data before the example below:

```sh
lhapdf install CT14lo
```

```python
import hepyy
hepyy.load('hepbundle')
import fastjet, fjcontrib, hepmc3, pythia8, lhapdf
pdf = lhapdf.mkPDF('CT14lo', 0)  # install this data set first
print(pdf.xfxQ(21, 0.1, 100.))
```

LHAPDF provides its upstream Python interface and data-management command:

```sh
lhapdf --version
lhapdf list CT14lo
lhapdf install CT14lo
lhapdf show CT14lo
```

PDF sets are external data; they are not all included in the wheel. Use
LHAPDF_DATA_PATH and the command's --pdfdir/--listdir options for custom data
locations. User data paths are preserved and packaged configuration is appended.
The command's default source uses HTTPS. Its --source override is tried first.

All native libraries use one cppyy interpreter. LHAPDF's Cython Python module
also links to the same LHAPDF core used by Pythia. Its extension uses the CPython
3.10 stable ABI and is checked with abi3audit and runtime tests. No cppyy, Cling,
Python interpreter, or second FastJet/LHAPDF core is bundled.

Shell-selected source packages and the source registry retain precedence.
Wheel plugins reject incompatible selected source/shell dependencies before
loading. When no source install is selected, the loader checks for an installed
distribution named `hepyy-<package>` and reads its
`hepyy_<package>/manifest.json` on demand. Use underscores in the payload path
and set the manifest's `name` to the Python import name. Wheel discovery writes
no registry entries. Use pip to uninstall wheel
payloads; registry CLI listings continue to describe source installations.
Use fresh environments for this stack rather than combining unrelated native
FastJet, Pythia, LHAPDF or HepMC distributions that own the same modules/libraries.

The companion hepyy-recipes wheels/UPGRADING.md documents the recipe-driven
upgrade command. It updates both repositories' lock/metadata, builds a candidate
and keeps index promotion separately protected. Build profiles and recipe/source
hashes determine a fresh packaging revision; repeated unchanged syncs are stable.

The pre-change snapshot remains pre-pip-wheels-2026-11-18 at
 e43a9dc871402ae070d36717ba93997607d1ec18. It must never be moved.
