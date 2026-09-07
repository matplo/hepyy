"""
Detect and fix broken rpath/dependency entries in the cppyy backend's libCling.

cppyy wheels are sometimes built against non-standard paths (e.g. MacPorts
/opt/local on macOS, or a build-time conda env on Linux). This module
rewrites the embedded library paths so the wheel works without manual
intervention.

macOS: uses otool + install_name_tool
Linux: uses ldd + patchelf (patchelf must be installed)
"""

import pathlib
import re
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple


def _find_libcling() -> Optional[pathlib.Path]:
    try:
        import cppyy_backend
        lib_dir = pathlib.Path(cppyy_backend.__file__).parent / "lib"
        for name in ("libCling.so", "libCling.dylib"):
            candidate = lib_dir / name
            if candidate.exists():
                return candidate
    except ImportError:
        pass
    return None


# ---------------------------------------------------------------------------
# macOS helpers
# ---------------------------------------------------------------------------

_MACOS_SKIP_PREFIXES = (
    "@rpath/",
    "@loader_path/",
    "@executable_path/",
    "/usr/lib/",       # macOS dyld shared cache — no file on disk but valid
    "/System/",
)

_MACOS_SEARCH_DIRS = [
    "/opt/homebrew/lib",
    "/usr/local/lib",
    "/opt/local/lib",
]


def _macos_broken_deps(lib: pathlib.Path) -> List[str]:
    """Return absolute third-party dependency paths that don't exist on disk."""
    result = subprocess.run(
        ["otool", "-L", str(lib)], capture_output=True, text=True
    )
    broken = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.endswith(":"):
            continue
        embedded = line.split()[0]
        if any(embedded.startswith(p) for p in _MACOS_SKIP_PREFIXES):
            continue
        if not pathlib.Path(embedded).exists():
            broken.append(embedded)
    return broken


def _macos_find_replacement(embedded: str) -> Optional[str]:
    lib_name = pathlib.Path(embedded).name
    for d in _MACOS_SEARCH_DIRS:
        candidate = pathlib.Path(d) / lib_name
        if candidate.exists():
            return str(candidate)
    return None


def _macos_fix(lib: pathlib.Path, verbose: bool) -> List[Tuple[str, str]]:
    if not shutil.which("install_name_tool"):
        print("Warning: install_name_tool not found — cannot auto-fix cppyy on macOS.")
        return []
    broken = _macos_broken_deps(lib)
    fixed = []
    for embedded in broken:
        replacement = _macos_find_replacement(embedded)
        if replacement is None:
            print(f"  Warning: no replacement found for {embedded}")
            continue
        subprocess.check_call(
            ["install_name_tool", "-change", embedded, replacement, str(lib)]
        )
        fixed.append((embedded, replacement))
        print(f"  Patched: {embedded}")
        print(f"       -> {replacement}")
    return fixed


def _macos_is_healthy(lib: pathlib.Path) -> bool:
    return len(_macos_broken_deps(lib)) == 0


# ---------------------------------------------------------------------------
# Linux helpers
# ---------------------------------------------------------------------------

_LINUX_SEARCH_DIRS = [
    "/usr/lib",
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib/aarch64-linux-gnu",
    "/usr/local/lib",
    "/opt/local/lib",
]


def _linux_broken_deps(lib: pathlib.Path) -> List[Tuple[str, str]]:
    """Return list of (soname, 'not found') pairs from ldd output."""
    result = subprocess.run(
        ["ldd", str(lib)], capture_output=True, text=True
    )
    broken = []
    # ldd output: "    libzstd.so.1 => not found"
    for line in result.stdout.splitlines():
        m = re.search(r"(\S+\.so[\d.]*)\s+=>\s+not found", line)
        if m:
            broken.append(m.group(1))
    return broken


def _linux_find_replacement(soname: str) -> Optional[str]:
    # First try ldconfig cache
    if shutil.which("ldconfig"):
        result = subprocess.run(
            ["ldconfig", "-p"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if soname in line and "=>" in line:
                path = line.split("=>")[-1].strip()
                if pathlib.Path(path).exists():
                    return str(pathlib.Path(path).parent)
    # Fall back to known search dirs
    for d in _LINUX_SEARCH_DIRS:
        candidate = pathlib.Path(d) / soname
        if candidate.exists():
            return d
    return None


def _linux_fix(lib: pathlib.Path, verbose: bool) -> List[Tuple[str, str]]:
    if not shutil.which("patchelf"):
        print(
            "Warning: patchelf not found — cannot auto-fix cppyy on Linux.\n"
            "Install it with: apt install patchelf  OR  pip install patchelf"
        )
        return []
    broken = _linux_broken_deps(lib)
    dirs_to_add = set()
    fixed = []
    for soname in broken:
        lib_dir = _linux_find_replacement(soname)
        if lib_dir is None:
            print(f"  Warning: no replacement found for {soname}")
            continue
        dirs_to_add.add(lib_dir)
        fixed.append((soname, lib_dir))
        print(f"  Found {soname} -> {lib_dir}")

    if dirs_to_add:
        # Get current rpath and extend it
        result = subprocess.run(
            ["patchelf", "--print-rpath", str(lib)],
            capture_output=True, text=True
        )
        current_rpath = result.stdout.strip()
        existing = set(current_rpath.split(":")) if current_rpath else set()
        new_rpath = ":".join(existing | dirs_to_add)
        subprocess.check_call(["patchelf", "--set-rpath", new_rpath, str(lib)])
        print(f"  Set rpath: {new_rpath}")
    return fixed


def _linux_is_healthy(lib: pathlib.Path) -> bool:
    return len(_linux_broken_deps(lib)) == 0


# ---------------------------------------------------------------------------
# Venv safety helpers
# ---------------------------------------------------------------------------

def is_in_venv() -> bool:
    """Return True if running inside a virtual environment."""
    return (
        sys.prefix != sys.base_prefix
        or hasattr(sys, "real_prefix")  # older virtualenv sets this
        or bool(sys.exec_prefix != sys.base_exec_prefix)
    )


def libcling_in_venv(lib: Optional[pathlib.Path] = None) -> bool:
    """Return True if libCling lives inside the active venv (safe to patch)."""
    lib = lib or _find_libcling()
    if lib is None:
        return False
    try:
        lib.resolve().relative_to(pathlib.Path(sys.prefix).resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fix_cppyy(verbose: bool = False) -> List[Tuple[str, str]]:
    """
    Patch broken library paths in libCling using platform-appropriate tools.
    Returns list of (old, new) pairs that were fixed.
    """
    lib = _find_libcling()
    if lib is None:
        if verbose:
            print("cppyy fix: libCling not found (cppyy not installed?).")
        return []

    if sys.platform == "darwin":
        return _macos_fix(lib, verbose)
    elif sys.platform.startswith("linux"):
        return _linux_fix(lib, verbose)
    else:
        if verbose:
            print(f"cppyy fix: unsupported platform '{sys.platform}'.")
        return []


def check_cppyy() -> bool:
    """Return True if libCling has no detectable broken dependencies."""
    lib = _find_libcling()
    if lib is None:
        return False
    if sys.platform == "darwin":
        return _macos_is_healthy(lib)
    elif sys.platform.startswith("linux"):
        return _linux_is_healthy(lib)
    return True  # assume OK on other platforms


def get_broken_deps(lib: Optional[pathlib.Path] = None) -> list:
    """Return broken dependency names for the cppyy backend library."""
    lib = lib or _find_libcling()
    if lib is None:
        return []
    if sys.platform == "darwin":
        return _macos_broken_deps(lib)
    elif sys.platform.startswith("linux"):
        return _linux_broken_deps(lib)
    return []
