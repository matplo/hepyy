"""Auto-loaded via hepyy_autoload.pth at Python startup.

Installs a lazy MetaPathFinder for every package whose HEPYY_LOADED_*
env var is set (populated by 'module load <pkg>' via Lmod/Environment Modules).

The finder defers the actual hepyy.load() call — which imports cppyy and
triggers its PCH build — to the moment user code first does `import <name>`.
This keeps Python startup instant even when modules are loaded, which matters
on HPC systems where the cppyy PCH build on a network filesystem can hang.
"""
import os as _os
import sys as _sys

if any(k.startswith("HEPYY_LOADED_") for k in _os.environ):
    # Set CPPYY_API_PATH before the MetaPathFinder is installed so that user
    # code which does a bare `import cppyy` (before `import fastjet`) picks up
    # the correct CPyCppyy C-level API directory.  Without this, cppyy's
    # string_meta is initialised without npos and calling any C++ function that
    # returns std::string raises AttributeError at runtime.
    # pip '--target' installs put the headers at:
    #   {cppyy_prefix}/include/site/python<ver>/CPyCppyy/
    if 'CPPYY_API_PATH' not in _os.environ and 'cppyy' not in _sys.modules:
        try:
            import glob as _glob
            import pathlib as _pathlib
            from hepyy.registry import get_registry as _gr_early
            _rec_early = _gr_early().get('cppyy')
            if _rec_early:
                _prefix_early = _pathlib.Path(_rec_early['prefix'])
                _cands_early = _glob.glob(
                    str(_prefix_early / 'include' / 'site' / 'python*' / 'CPyCppyy')
                )
                if _cands_early:
                    _os.environ['CPPYY_API_PATH'] = _cands_early[0]
        except Exception:
            pass

    try:
        import importlib.abc as _abc
        import importlib.machinery as _machinery
        import hepyy as _h
        from hepyy.registry import get_registry as _gr

        _names = [n for n in _gr().all_packages()
                  if _os.environ.get("HEPYY_LOADED_" + n.upper().replace("-", "_"))]
        # ROOT must go first so its lib/ lands in sys.path before any
        # `import cppyy` — that way ROOT's bundled cppyy wins over pip-cppyy.
        if "root" in _names:
            _names.remove("root")
            _names.insert(0, "root")

        # Only intercept imports for packages without a real Python module.
        # If a package IS a real Python module (cppyy, lhapdf SWIG bindings,
        # etc.), intercepting its import causes hepyy.load() to run while
        # that module is still being initialised by Python's import machinery.
        # The nested `import cppyy` inside _setup_cppyy() then gets a
        # partially-initialised module back, breaking string_meta (npos) and
        # all cppyy C++ type wrappers.  Let real Python packages load normally.
        import importlib.util as _ilu
        _pending = [n for n in _names if _ilu.find_spec(n) is None]

        class _HeppyyierLazyLoader(_abc.Loader):
            def __init__(self, mod):
                self._mod = mod

            def create_module(self, spec):
                return self._mod  # reuse the proxy _h.load() already placed in sys.modules

            def exec_module(self, module):
                pass  # nothing to execute; module is already fully set up

        class _HeppyyierFinder(_abc.MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                if fullname not in _pending or fullname in _sys.modules:
                    return None
                # One-shot: load all pending packages in order, then uninstall.
                to_load = list(_pending)
                _pending.clear()
                _sys.meta_path[:] = [f for f in _sys.meta_path
                                     if not isinstance(f, _HeppyyierFinder)]
                for _name in to_load:
                    try:
                        _h.load(_name)
                    except Exception as _e:
                        print(f"[hepyy] lazy load failed for {_name!r}: {_e}",
                              file=_sys.stderr)
                if fullname in _sys.modules:
                    return _machinery.ModuleSpec(
                        fullname,
                        _HeppyyierLazyLoader(_sys.modules[fullname]),
                        origin="hepyy",
                    )
                return None

        _sys.meta_path.insert(0, _HeppyyierFinder())

    except Exception:
        pass
