import ctypes
import os
import pathlib
import sys
import types
import warnings
from typing import List, Optional

from .builder import _resolve_lib_dir
from .exceptions import PackageNotInstalledError
from .registry import get_registry


def _topo_sort(names: list, registry: dict) -> list:
    visited = set()
    order = []

    def visit(n):
        if n in visited:
            return
        visited.add(n)
        record = registry.get(n)
        if record:
            for dep in record.get("depends_on", []):
                visit(dep)
        order.append(n)

    for n in names:
        visit(n)
    return order


class Loader:
    _loaded: set = set()

    def load(
        self,
        name: str,
        version: Optional[str] = None,
        install_if_missing: bool = False,
        verbose: bool = False,
    ) -> None:
        # Normalize hyphens/underscores early so dedup works regardless of which
        # form the caller uses ("hepyy-utils" and "hepyy_utils" are one package).
        alt = name.replace("_", "-") if "_" in name else name.replace("-", "_")
        if name in self._loaded or alt in self._loaded:
            return

        reg = get_registry()

        # Check if shell-loaded version should take precedence
        shell_version = self._shell_loaded_version(name)
        record = None

        if shell_version:
            shell_prefix = os.environ.get(
                f"HEPYY_LOADED_{name.upper().replace('-','_')}_PREFIX"
            )
            if shell_prefix:
                # Build a synthetic record from env vars
                prefix = pathlib.Path(shell_prefix)
                record = self._record_from_prefix(name, shell_version, prefix, reg)

        if record is None:
            record = reg.get(name)

        # PyPI/pip normalizes hyphens and underscores as equivalent.  Let users
        # pass either form ("hepyy_utils" or "hepyy-utils") and resolve
        # to whichever variant the registry actually has.
        if record is None:
            alt = name.replace("_", "-") if "_" in name else name.replace("-", "_")
            alt_record = reg.get(alt)
            if alt_record is not None:
                record = alt_record
                name = alt  # use the canonical registry name going forward

        if record is None:
            if install_if_missing:
                from .builder import build_package
                build_package(name, version=version, verbose=verbose)
                record = get_registry().get(name)
            else:
                raise PackageNotInstalledError(
                    f"Package '{name}' is not installed. "
                    f"Run: hepyy install {name}"
                )

        # Resolve cppyy metadata from recipe (source of truth); fall back to
        # registry fields for old entries that predate Option-B migration.
        from .recipe import find_recipe
        from .exceptions import RecipeNotFoundError
        try:
            recipe = find_recipe(
                name,
                version=record["version"],
                recipe_path=record.get("recipe_path"),
            )
            headers      = recipe.cppyy_headers
            libraries    = recipe.cppyy_libraries
            namespace    = recipe.cppyy_namespace
            deps         = recipe.depends_on
            python_paths = recipe.python_paths
        except RecipeNotFoundError:
            headers      = record.get("headers", [])
            libraries    = record.get("libraries", [])
            namespace    = record.get("cppyy_namespace") or name
            deps         = record.get("depends_on", [])
            python_paths = []

        # Load dependencies first
        if deps:
            all_packages = reg.all_packages()
            order = _topo_sort(deps, all_packages)
            for dep in order:
                if dep not in self._loaded:
                    self.load(dep, verbose=verbose)

        self._setup_python_paths(record, python_paths, verbose)
        self._setup_cppyy(record, headers, libraries, verbose)
        # Don't shadow a real Python module (e.g. lhapdf SWIG bindings) with a
        # cppyy proxy. If a proper importable module exists for this name, leave
        # sys.modules alone — the C++ library has already been loaded above.
        if name not in sys.modules:
            import importlib.util
            if importlib.util.find_spec(name) is None:
                self._inject_proxy_module(name, namespace)
        self._loaded.add(name)

    def _shell_loaded_version(self, name: str) -> Optional[str]:
        key = f"HEPYY_LOADED_{name.upper().replace('-', '_')}"
        return os.environ.get(key)

    def _record_from_prefix(
        self, name: str, version: str, prefix: pathlib.Path, reg
    ) -> Optional[dict]:
        existing = reg.get(name)
        if existing and existing.get("version") == version:
            return existing
        # Minimal record from the prefix path; cppyy details may be missing
        return {
            "version": version,
            "prefix": str(prefix),
            "include_dir": str(prefix / "include"),
            "lib_dir": str(_resolve_lib_dir(prefix)),
            "cppyy_namespace": name,
            "headers": [],
            "libraries": [],
            "depends_on": [],
        }

    # cling 16 (LLVM 16, shipped with cppyy ≤ 3.x) is compatible with GCC 7–13.
    # GCC 14 headers use C++23-era attributes and C library assumptions that
    # cling 16 cannot parse (fenv_t not in global namespace, _GLIBCXX_NODISCARD
    # on operator new, etc.). Injecting GCC 14 headers breaks the PCH build.
    _CLING_MAX_COMPATIBLE_GCC = 13

    def _ensure_cxx17_headers(self) -> None:
        """On Linux, set CXX to a compatible compiler before cppyy's PCH build.

        The binary pip-cppyy wheel ships cling 16 built on manylinux2014. On
        SUSE/RHEL systems with an old default 'c++' (GCC 7.5) and a newer 'g++'
        (GCC 13), setting CXX=g++ ensures cling/rootcling uses the right compiler.

        CPATH manipulation is intentionally NOT done here. On SUSE Linux, adding
        GCC 13 C++ headers to CPATH breaks cling's #include_next chain for C
        compatibility headers (cfenv, fenv.h etc.) — the binary cling wheel does
        not know the GCC 13 toolchain layout. The only reliable fix for the
        binary wheel on SUSE is 'heyy install cppyy --force' (builds cling from
        source with GCC 13, which teaches cling the exact toolchain layout).
        """
        if not sys.platform.startswith("linux"):
            return
        import glob as _glob
        import shutil
        import subprocess
        import warnings

        # Set CXX=g++ if it's a newer compatible version than the default c++.
        # This helps both the source build recipe and any system where rootcling
        # respects the CXX env var.
        if "CXX" not in os.environ:
            for cxx_candidate in ("g++", "c++"):
                cxx = shutil.which(cxx_candidate)
                if not cxx:
                    continue
                try:
                    ver = subprocess.run(
                        [cxx, "-dumpversion"], capture_output=True, text=True, timeout=5,
                    )
                    cxx_major = int(ver.stdout.strip().split(".")[0])
                except Exception:
                    continue
                if cxx_major <= self._CLING_MAX_COMPATIBLE_GCC:
                    os.environ["CXX"] = cxx
                    break

        # Check whether the binary wheel PCH is likely to fail and warn.
        # We do NOT inject CPATH — on SUSE/RHEL that breaks more than it fixes.
        has_filesystem = bool(
            _glob.glob("/usr/include/c++/*/filesystem")
            or _glob.glob("/usr/local/include/c++/*/filesystem")
            or any(
                (pathlib.Path(p) / "filesystem").exists()
                for p in os.environ.get("CPATH", "").split(":")
                if p
            )
        )
        if not has_filesystem:
            warnings.warn(
                "[hepyy] pip-cppyy's PCH build will likely fail on this system. "
                "The binary cling wheel is incompatible with the system GCC include layout. "
                "Fix: 'heyy install cppyy --force' builds cling from source with the "
                f"system g++ (GCC ≤ {self._CLING_MAX_COMPATIBLE_GCC}), which resolves the "
                "include chain. Alternative: 'heyy install root' (ROOT's native cling).",
                UserWarning, stacklevel=4,
            )

    def _ensure_cppyy_on_syspath(self) -> None:
        """Add cppyy's hepyy prefix to sys.path when it was installed via
        'heyy install cppyy' (pip --target {prefix}).

        With --target installs the cppyy/* packages live directly in the
        hepyy-managed prefix (user or system registry), not in any venv's
        site-packages.  Without this, 'import cppyy' falls back to the binary
        pip wheel — which crashes on NERSC/SUSE (<filesystem> not found) and
        silently fails on Colab when the venv has no cppyy at all.
        """
        if 'cppyy' in sys.modules:
            return
        from .registry import get_registry
        rec = get_registry().get('cppyy')
        if rec is None:
            return
        prefix = pathlib.Path(rec['prefix'])
        # --target installs have the cppyy/ package dir directly in the prefix.
        # Old-style installs only have a .cppyy_install marker — skip those.
        if (prefix / 'cppyy').is_dir():
            p = str(prefix)
            if p not in sys.path:
                sys.path.insert(0, p)

    def _ensure_cppyy_api_path(self) -> None:
        """Set CPPYY_API_PATH from the CPyCppyy C-level API headers.

        cppyy checks CPPYY_API_PATH at import time to find the CPyCppyy C-level
        API headers. When they are missing (common with 'uv pip install' on Colab
        or non-standard prefix installs), cppyy can parse headers with cling but
        cannot expose C++ namespaces as Python objects — std::string's string_meta
        loses its npos attribute and cppyy.gbl.<ns> is None even after a successful
        cppyy.include(). Must be called BEFORE 'import cppyy'.

        pip '--target {prefix}' installs place the headers at:
            {prefix}/include/site/python<ver>/CPyCppyy/
        Standard site-packages installs place them at:
            {cppyy_backend.parent}/include/CPyCppyy/  (or .../include/)
        """
        if 'CPPYY_API_PATH' in os.environ:
            return
        if 'cppyy' in sys.modules:
            return  # too late to help, but don't clobber
        try:
            import glob
            import cppyy_backend as _cb
            # pip --target layout: {prefix}/include/site/python*/CPyCppyy/
            prefix = pathlib.Path(_cb.__file__).parent.parent
            candidates = glob.glob(
                str(prefix / 'include' / 'site' / 'python*' / 'CPyCppyy')
            )
            if candidates:
                os.environ['CPPYY_API_PATH'] = candidates[0]
                return
            # Standard layout: include/CPyCppyy/ or just include/ next to cppyy_backend
            for probe in (
                pathlib.Path(_cb.__file__).parent / 'include' / 'CPyCppyy',
                pathlib.Path(_cb.__file__).parent / 'include',
            ):
                if probe.is_dir():
                    os.environ['CPPYY_API_PATH'] = str(probe)
                    return
        except ImportError:
            pass

    def _preload_cppyy_deps(self) -> None:
        """Pre-load cppyy backend dependencies that may be missing from rpath."""
        self._ensure_cxx17_headers()
        self._ensure_cppyy_api_path()
        self._ensure_cppyy_on_syspath()
        import sys
        _search = []
        if sys.platform == "darwin":
            _search = [
                "/opt/homebrew/lib",
                "/usr/local/lib",
                "/opt/local/lib",
            ]
        for lib_name in ("libzstd.1", "libzstd"):
            for search_dir in _search:
                candidate = pathlib.Path(search_dir) / f"{lib_name}.dylib"
                if candidate.exists():
                    try:
                        ctypes.CDLL(str(candidate), ctypes.RTLD_GLOBAL)
                    except OSError:
                        pass
                    break

    def _setup_cppyy(
        self,
        record: dict,
        headers: List[str],
        libraries: List[str],
        verbose: bool,
    ) -> None:
        if not headers and not libraries:
            return
        self._preload_cppyy_deps()
        if "cppyy" not in sys.modules and "ROOT" not in sys.modules:
            # Strip any DYLD/LD_LIBRARY_PATH entry that contains libcling.
            # ROOT's lib dir ends up in DYLD_LIBRARY_PATH via both `module load`
            # and the heyy Jupyter kernel spec. If pip-cppyy loads its own cling
            # while ROOT's cling is also visible, cppyy_backend crashes in
            # TThread::Init. Safe to strip here because ROOT is not yet imported.
            _cling_names = ("libcling.dylib", "libcling.so", "libCling.dylib", "libCling.so")
            for _var in ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH"):
                _val = os.environ.get(_var, "")
                _parts = [p for p in _val.split(":") if p]
                _safe = [
                    p for p in _parts
                    if not any((pathlib.Path(p) / n).exists() for n in _cling_names)
                ]
                if len(_safe) != len(_parts):
                    os.environ[_var] = ":".join(_safe)
        try:
            import cppyy
        except ImportError:
            raise ImportError(
                "cppyy is not installed. Install it with: pip install cppyy"
            )

        cppyy.add_include_path(record["include_dir"])

        lib_path = pathlib.Path(record["lib_dir"])
        for lib_name in libraries:
            loaded = False
            for ext in (".dylib", ".so"):
                candidate = lib_path / f"lib{lib_name}{ext}"
                if candidate.exists():
                    if verbose:
                        print(f"Loading {candidate}")
                    try:
                        ctypes.CDLL(str(candidate), ctypes.RTLD_GLOBAL)
                        loaded = True
                        break
                    except OSError as e:
                        warnings.warn(f"ctypes.CDLL failed for {candidate}: {e}")
            if not loaded:
                try:
                    cppyy.load_library(lib_name)
                except Exception as e:
                    warnings.warn(f"Could not load library '{lib_name}': {e}")

        for header in headers:
            try:
                cppyy.include(header)
            except Exception as e:
                warnings.warn(
                    f"[hepyy] Could not include '{header}': {e}\n"
                    "  The proxy module will be created but attribute access will fail.\n"
                    "  Check that the include directory is readable and cppyy is working.",
                    stacklevel=3,
                )

    def _setup_python_paths(
        self,
        record: dict,
        python_paths: List[str],
        verbose: bool,
    ) -> None:
        if not python_paths:
            return
        prefix = pathlib.Path(record["prefix"])
        for rel in python_paths:
            full = str(prefix / rel)
            if full not in sys.path:
                sys.path.insert(0, full)
                if verbose:
                    print(f"[hepyy] Added to sys.path: {full}")

    def _inject_proxy_module(self, name: str, ns_name: str) -> None:
        ns_name = ns_name or name

        proxy = types.ModuleType(name)
        proxy.__doc__ = f"hepyy cppyy proxy for {name} (namespace: {ns_name})"
        proxy.__path__ = []  # type: ignore[assignment]
        proxy.__package__ = name

        def __getattr__(attr: str):
            import cppyy
            # Support nested namespaces like "fastjet::contrib"
            ns = cppyy.gbl
            for part in ns_name.split("::"):
                ns = getattr(ns, part, None)
                if ns is None:
                    raise AttributeError(
                        f"cppyy namespace '{ns_name}' not found. "
                        f"Ensure '{name}' loaded correctly."
                    )
            return getattr(ns, attr)

        proxy.__getattr__ = __getattr__  # type: ignore[attr-defined]

        # Convenience: expose gbl directly on the proxy
        import cppyy
        proxy.gbl = cppyy.gbl  # type: ignore[attr-defined]
        proxy.cppyy = cppyy  # type: ignore[attr-defined]

        sys.modules[name] = proxy

    def loaded_names(self) -> List[str]:
        return list(self._loaded)

    def unload(self, name: str) -> None:
        warnings.warn(
            f"cppyy cannot unload shared libraries at runtime. "
            f"'{name}' will remain active for this Python session. "
            "Use shell-level 'module unload' before starting a new Python session.",
            stacklevel=2,
        )


_loader = Loader()


def get_loader() -> Loader:
    return _loader
