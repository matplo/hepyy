import json
import os
import pathlib
import sys
import tempfile
from typing import Optional


def _check_deps() -> None:
    missing = []
    try:
        import ipykernel  # noqa: F401
    except ImportError:
        missing.append("ipykernel")
    try:
        import jupyter_client  # noqa: F401
    except ImportError:
        missing.append("jupyter_client")
    if missing:
        raise RuntimeError(
            f"Missing: {', '.join(missing)}. Run: pip install {' '.join(missing)}"
        )


def _build_env(packages_dir: pathlib.Path, packages: dict) -> dict:
    path_parts: list = []
    lib_parts: list = []
    pythonpath_parts: list = []

    _cling_names = ("libcling.dylib", "libcling.so", "libCling.dylib", "libCling.so")

    for rec in packages.values():
        prefix = pathlib.Path(rec["prefix"])
        if (prefix / "bin").is_dir():
            path_parts.append(str(prefix / "bin"))
        # lib/ preferred; fall back to lib64/ (common on Linux distros / HPC)
        _lib_candidates = [prefix / "lib", prefix / "lib64"]
        lib_dir = next((d for d in _lib_candidates if d.is_dir()), None)
        if lib_dir is not None:
            # Don't add a lib dir that ships libcling to DYLD/LD_LIBRARY_PATH.
            # dyld caches the env at process start, so a kernel with ROOT's lib
            # in DYLD_LIBRARY_PATH will have its libCling picked up by pip-cppyy
            # before any runtime stripping can happen → crash. ROOT's own libs
            # use @loader_path rpaths and don't need the env var.
            has_cling = any((lib_dir / n).exists() for n in _cling_names)
            if not has_cling:
                lib_parts.append(str(lib_dir))
            for sp in sorted(lib_dir.glob("python*/site-packages")):
                pythonpath_parts.append(str(sp))

        # Respect python_paths from the registry record (mirrors what loader.py
        # does in _setup_python_paths). This is the authoritative source —
        # filesystem heuristics can miss non-standard layouts.
        for rel in rec.get("python_paths", []):
            full = str(prefix / rel)
            if full not in pythonpath_parts:
                pythonpath_parts.append(full)

    def _prepend(parts: list, current: str) -> Optional[str]:
        if not parts:
            return None
        s = os.pathsep.join(parts)
        return s + os.pathsep + current if current else s

    env: dict = {"HEPYY_PACKAGES_DIR": str(packages_dir)}

    v = _prepend(path_parts, os.environ.get("PATH", ""))
    if v:
        env["PATH"] = v

    # Both vars; kernel picks up whichever the OS honours
    v = _prepend(lib_parts, os.environ.get("DYLD_LIBRARY_PATH", ""))
    if v:
        env["DYLD_LIBRARY_PATH"] = v

    v = _prepend(lib_parts, os.environ.get("LD_LIBRARY_PATH", ""))
    if v:
        env["LD_LIBRARY_PATH"] = v

    v = _prepend(pythonpath_parts, os.environ.get("PYTHONPATH", ""))
    if v:
        env["PYTHONPATH"] = v

    return env


def install_kernel(
    name: Optional[str] = None,
    display_name: Optional[str] = None,
    user: bool = True,
) -> pathlib.Path:
    """Write a Jupyter kernel spec for the current hepyy environment.

    Re-running overwrites the existing spec, refreshing env paths after new
    packages are installed.
    """
    _check_deps()

    from .config import get_packages_dir, get_system_packages_dirs
    from .registry import get_registry

    packages = get_registry().all_packages()
    packages_dir = get_packages_dir()

    if name is None:
        name = "hepyy-" + pathlib.Path(sys.prefix).name

    if display_name is None:
        pkg_list = ", ".join(sorted(packages.keys())) if packages else "no packages installed"
        display_name = f"HEP ({pkg_list})"

    env = _build_env(packages_dir, packages)

    # Preserve the system packages dir so the kernel's registry can find
    # shared/admin-installed packages at runtime (two-tier registry lookup).
    sys_dirs = get_system_packages_dirs()
    if sys_dirs:
        env["HEPYY_SYSTEM_PACKAGES_DIR"] = os.pathsep.join(str(d) for d in sys_dirs)

    # Propagate EXTRA_CLING_ARGS if set (e.g. by henv, to fix cppyy-cling's
    # frozen Clang not recognizing a newer host GCC's headers — see henv's
    # README). Jupyter launches the kernel in its own process and does not
    # inherit the shell's env, so without this the fix is silently lost and
    # `import cppyy` can crash inside the kernel even though it works in
    # the shell that ran `heyy kernel install`.
    if "EXTRA_CLING_ARGS" in os.environ:
        env["EXTRA_CLING_ARGS"] = os.environ["EXTRA_CLING_ARGS"]

    kernel_spec = {
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": display_name,
        "language": "python",
        "env": env,
        "metadata": {
            "hepyy": True,
            "packages_dir": str(packages_dir),
        },
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = pathlib.Path(tmpdir)
        (tmppath / "kernel.json").write_text(json.dumps(kernel_spec, indent=2))

        from jupyter_client.kernelspec import KernelSpecManager
        dest = KernelSpecManager().install_kernel_spec(
            str(tmppath), kernel_name=name, user=user, replace=True
        )

    return pathlib.Path(dest)


def list_kernels() -> list:
    """Return info dicts for every hepyy-managed Jupyter kernel."""
    _check_deps()
    from jupyter_client.kernelspec import KernelSpecManager
    mgr = KernelSpecManager()
    results = []
    for name, spec in mgr.get_all_specs().items():
        meta = spec.get("spec", {}).get("metadata", {}) if isinstance(spec, dict) else {}
        if not meta.get("hepyy"):
            continue
        results.append({
            "name": name,
            "display_name": spec.get("spec", {}).get("display_name", name) if isinstance(spec, dict) else name,
            "resource_dir": spec.get("resource_dir", "") if isinstance(spec, dict) else "",
            "packages_dir": meta.get("packages_dir", ""),
        })
    return results


def update_kernel(
    name: Optional[str] = None,
    display_name: Optional[str] = None,
    user: bool = True,
) -> pathlib.Path:
    """Refresh the env embedded in an existing hepyy kernel spec.

    If *name* is None the default name for the current venv is used.
    Warns when the kernel's recorded Python executable differs from the
    current one (the spec will be rewritten with the current Python).
    Raises KeyError if no kernel with that name exists yet.
    """
    _check_deps()
    from jupyter_client.kernelspec import KernelSpecManager, NoSuchKernel

    if name is None:
        name = "hepyy-" + pathlib.Path(sys.prefix).name

    mgr = KernelSpecManager()
    try:
        existing = mgr.get_kernel_spec(name)
    except NoSuchKernel:
        raise KeyError(
            f"No kernel named '{name}' found. "
            "Run 'heyy kernel install' to create it first."
        )

    if not existing.metadata.get("hepyy"):
        raise PermissionError(
            f"Kernel '{name}' was not installed by hepyy — refusing to update it."
        )

    # Warn when the stored Python differs from the current interpreter.
    stored_python = existing.argv[0] if existing.argv else None
    if stored_python and stored_python != sys.executable:
        import warnings
        warnings.warn(
            f"[hepyy] Kernel '{name}' was previously installed with\n"
            f"  {stored_python}\n"
            f"but is now being refreshed with\n"
            f"  {sys.executable}\n"
            "The kernel will use the current Python after this update.",
            UserWarning,
            stacklevel=2,
        )

    # Preserve display name from existing spec unless caller overrides.
    if display_name is None:
        display_name = existing.display_name

    return install_kernel(name=name, display_name=display_name, user=user)


def remove_kernel(name: str) -> pathlib.Path:
    """Remove a hepyy-managed kernel spec by name.

    Raises KeyError if the kernel doesn't exist.
    Raises PermissionError if it's not a hepyy-managed kernel.
    """
    _check_deps()
    from jupyter_client.kernelspec import KernelSpecManager, NoSuchKernel
    mgr = KernelSpecManager()
    try:
        spec = mgr.get_kernel_spec(name)
    except NoSuchKernel:
        raise KeyError(f"No kernel named '{name}' found.")

    if not spec.metadata.get("hepyy"):
        raise PermissionError(
            f"Kernel '{name}' was not installed by hepyy — refusing to remove it."
        )

    resource_dir = pathlib.Path(spec.resource_dir)
    import shutil
    shutil.rmtree(resource_dir)
    return resource_dir
