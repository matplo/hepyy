# Native wheels (pre-publication)

The companion `matplo/hepyy-recipes/wheels` builder produces `hepyy-fastjet`
3.5.1.0, `hepyy-fjcontrib` 1.102.0, and `hepyy-pythia8` 8.317.0. These are
platform wheels containing C++ headers, shared libraries, license notices,
and (for Pythia) XML/data files. They contain no Python C++ bindings and no
cppyy/Cling runtime. No native distributions have been published by this work.

## Install artifacts

On macOS, use an **activated** conda-forge environment. Activation supplies the
matching compiler and SDK configuration; calling its Python without activation
is not equivalent. For example:

```sh
conda create -n hepyy-wheels -c conda-forge python=3.12 cppyy pip
conda activate hepyy-wheels
# wheelhouse contains the matching native wheel artifacts for your platform
python -m pip install --find-links wheelhouse '.[fjcontrib,pythia8]'
```

Run the final command from this hepyy feature checkout. Do not add the `cppyy`
extra when using conda's runtime. On a tested Linux pip environment, use
`'.[cppyy,fjcontrib,pythia8]'` instead. FastJet alone uses `'.[fastjet]'`.
After publication, `hepyy` can replace `.`; that is not currently a released
installation promise. Windows, universal2 and Linux arm64 are not covered yet.

```python
import hepyy
hepyy.load(['fastjet', 'fjcontrib', 'pythia8'])
import cppyy, fastjet, fjcontrib, pythia8
assert fastjet.PseudoJet is cppyy.gbl.fastjet.PseudoJet
```

The `hepyy_*` modules are data containers. Use `hepyy.load`, followed by the
existing proxy imports or `cppyy.gbl`; do not import a separate SWIG FastJet
binding for objects you intend to pass to cppyy fjcontrib.

## Selection and interoperability

Shell-selected packages take precedence, followed by the existing user/system
registry, followed by installed wheels. Wheels are discovered through Python
package metadata; loading them never writes a registry entry. Uninstall with
pip, not `heyy uninstall`. Registry-oriented CLI listings remain source-install
listings; wheel discovery is currently in the Python loader only.

Wheel manifests are authoritative for their actual headers and libraries. A
recipe cache cannot change the libraries a wheel loads. A missing library or
header fails the load instead of registering a broken proxy. Pythia's packaged
XML directory is used unless `PYTHIA8DATA` is explicitly set.

The fjcontrib wheel pins FastJet 3.5.1.0 and an explicit ABI generation. It
links to the sibling FastJet payload using relative loader paths, and never
bundles another FastJet. A selected source/shell FastJet or a mismatched wheel
is rejected before loading fjcontrib. Use a fresh process and matching wheels,
or build both with `heyy install`. Loading another FastJet independently through
ROOT or third-party bindings is outside this provider check.

The existing source builders and `heyy install cppyy` fallback remain available.
A discoverable conda cppyy is not shadowed by a registered heyy cppyy prefix.
No runtime backend replacement or custom cppyy build is introduced.

## Tests and scope

`python -m pytest tests -q` checks provider selection, ABI rejection, metadata,
load failures and conda runtime preservation. The recipes CI builds all payloads,
checks wheel contents, relocates the build trees, and runs `wheels/smoke.py`:
STL JIT and std::string crossing the ABI boundary, anti-kt clustering and momentum
conservation, SoftDrop and N-subjettiness on the same PseudoJets, and three seeded
Pythia events through FastJet and fjcontrib. Builds upload artifacts only.

The pre-change snapshot is annotated tag `pre-pip-wheels-2026-11-18`, resolving
to `e43a9dc871402ae070d36717ba93997607d1ec18`. It must never be moved or reused.
