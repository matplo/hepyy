# Running the hepyy demos

Install the [pip hepbundle](../NATIVE_WHEELS.md) in an activated environment,
then run a script from a checkout of this repository:

```sh
python demos/demo_fastjet.py
python demos/demo_pythia_fastjet.py
```

To download the current demos using an installed hepyy:

```sh
heyy demos --overwrite
python hepyy_demos/demo_fastjet.py
```

## Initialize before importing

Each script explicitly loads its required packages before importing their Python
proxies. This works with both pip wheels and source installations:

```python
import hepyy
hepyy.load("fastjet")
import fastjet
```

For the full pip bundle use `hepyy.load("hepbundle")`. Installing a wheel does
not create the `fastjet` Python proxy in a fresh process; a bare `import fastjet`
can raise `ModuleNotFoundError` until the load call runs. Calls are safe to repeat
when the shell module system has already initialized a package.

In Jupyter, run the notebook's initial load cell before the import cells and
rerun it after a kernel restart. Use the environment containing the bundle as
the notebook kernel.

## Optional dependencies

- `demo_fastjet.py` and `demo_pythia_fastjet.py` use the installed native packages.
- `demo_fjcontrib.py` and the plotting notebooks additionally use `matplotlib`
  and `numpy`: `python -m pip install matplotlib numpy`.
- `demo_pythia_fastjet_root.py` writes ROOT-format files through `uproot` and
  `numpy`: `python -m pip install uproot numpy`.
- `demo_pythia_fastjet_root_cppyy.py` and `demo_pythia_fastjet_root.ipynb`
  additionally require ROOT, which is separate from the pip hepbundle. ROOT
  must initialize its cppyy runtime before FastJet/Pythia are loaded. The Python
  script uses importable system/conda ROOT when present, otherwise
  `hepyy.load("root")` exposes a ROOT installation managed by hepyy. The notebook
  setup cell includes the corresponding instructions.

Source users can prepare packages with `heyy install fastjet pythia8 fjcontrib`.
The same explicit load calls apply. Plot images and ROOT-format output files are
written to the current working directory; run from a writable directory.
