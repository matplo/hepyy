from .loader import get_loader
from .registry import get_registry

__version__ = "0.1.0"


class _ModuleProxy:
    """Mirrors the HPC `module` command for HEP C++ packages."""

    def load(
        self,
        name: str,
        version: str = None,
        install_if_missing: bool = False,
        verbose: bool = False,
    ) -> None:
        """Load a package and make it available via cppyy and `import <name>`."""
        get_loader().load(
            name,
            version=version,
            install_if_missing=install_if_missing,
            verbose=verbose,
        )

    def unload(self, name: str) -> None:
        """Warn that cppyy cannot unload at runtime; use shell `module unload` instead."""
        get_loader().unload(name)

    def list(self):
        """Return names of packages loaded in this Python session."""
        return get_loader().loaded_names()

    def avail(self):
        """Return names of packages registered in the registry."""
        return list(get_registry().all_packages().keys())


module = _ModuleProxy()


def load(name, **kwargs) -> None:
    """Shorthand for hepyy.module.load(name).

    Accepts a single package name or a list of names loaded in order.
    """
    if isinstance(name, (list, tuple)):
        for n in name:
            module.load(n, **kwargs)
    else:
        module.load(name, **kwargs)


def gSystem_load(name: str) -> None:
    """Load a hepyy-installed package into ROOT via ROOT.gSystem.Load().

    Use this in ROOT-first sessions (Pattern C) to make a package's C++ symbols
    available through ROOT's own cling, without invoking pip-cppyy.

    Example::

        import hepyy
        hepyy.load('root')
        import ROOT
        hepyy.gSystem_load('fastjet')
        hepyy.gSystem_load('pythia8')
        p = ROOT.Pythia8.Pythia()
        j = ROOT.fastjet.PseudoJet(1, 0, 1, 1.4)
    """
    try:
        import ROOT
    except ImportError:
        raise ImportError("ROOT is not importable — run hepyy.load('root') and import ROOT first")

    reg = get_registry()
    rec = reg.get(name)
    if rec is None:
        raise KeyError(f"Package '{name}' is not installed. Run: heyy install {name}")

    import pathlib
    lib_dir = pathlib.Path(rec["lib_dir"])
    loaded = []
    for lib in lib_dir.glob(f"lib{name}.*"):
        if lib.suffix in (".so", ".dylib") and ".so." not in lib.name:
            ret = ROOT.gSystem.Load(str(lib))
            if ret in (0, 1):   # 0 = loaded, 1 = already loaded
                loaded.append(lib.name)
                break
    if not loaded:
        raise FileNotFoundError(f"No shared library found for '{name}' in {lib_dir}")
