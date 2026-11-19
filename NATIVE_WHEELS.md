# Pip-installable hepbundle candidate

The expanded candidate follows hepbundle: FastJet 3.5.3, fjcontrib 1.105, HepMC3
3.3.1, LHAPDF 6.5.5, and Pythia 8.317 built with all three external interfaces.
Wheel packaging revisions are pinned in pyproject.toml and the native lock.
These expanded candidates have not been published or merged as part of this work.

In a fresh, activated conda-forge cppyy environment, install the candidate from
its local wheelhouse and this checkout:

```sh
python -m pip install --find-links /path/to/wheelhouse '.[hepbundle]'
```

On tested Linux pip hosts use `'.[cppyy,hepbundle]'`. cppyy stays optional so the
conda-managed runtime remains untouched. Use CPython >=3.10 for the complete
bundle. The base hepyy package and FastJet-only paths retain their own metadata.

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
loading. Wheel discovery writes no registry entries. Use pip to uninstall wheel
payloads; registry CLI listings continue to describe source installations.
Use fresh environments for this stack rather than combining unrelated native
FastJet, Pythia, LHAPDF or HepMC distributions that own the same modules/libraries.

The companion hepyy-recipes wheels/UPGRADING.md documents the recipe-driven
upgrade command. It updates both repositories' lock/metadata, builds a candidate
and keeps index promotion separately protected. Build profiles and recipe/source
hashes determine a fresh packaging revision; repeated unchanged syncs are stable.

The pre-change snapshot remains pre-pip-wheels-2026-11-18 at
 e43a9dc871402ae070d36717ba93997607d1ec18. It must never be moved.
