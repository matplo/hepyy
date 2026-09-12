import os
import pathlib
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


def _load_project_config() -> dict:
    candidate = pathlib.Path.cwd() / ".hepyy.toml"
    if candidate.exists():
        with open(candidate, "rb") as f:
            return tomllib.load(f)
    return {}


def _is_conda_env() -> bool:
    """True when sys.prefix is a conda/mamba environment (not a venv).

    "conda-meta" is the reliable signal — it's always present in a real
    conda/mamba env root regardless of activation state. CONDA_PREFIX is
    checked too, as a fallback for the rare env missing that directory.
    """
    if (pathlib.Path(sys.prefix) / "conda-meta").is_dir():
        return True
    return os.environ.get("CONDA_PREFIX") == sys.prefix


def _default_packages_dir() -> pathlib.Path:
    # Inside a virtual environment → keep packages alongside the venv itself
    if sys.prefix != sys.base_prefix:
        return pathlib.Path(sys.prefix) / "hepyy_packages"
    # Inside a conda/mamba env (no venv layered on top) → keep packages under
    # the env's own share/ dir, next to where hepyy itself is installed
    if _is_conda_env():
        return pathlib.Path(sys.prefix) / "share" / "hepyy_packages"
    return pathlib.Path.cwd() / "packages"


def get_packages_dir() -> pathlib.Path:
    """Root of the permanent package store: <packages_dir>/<name>/<version>/.

    Resolution order:
      1. HEPYY_PACKAGES_DIR env var  (preferred)
      2. HEPYY_BUILD_DIR env var      (legacy alias)
      3. .hepyy.toml  packages_dir key
      4. .hepyy.toml  build_dir key   (legacy alias)
      5. <venv>/hepyy_packages/  when running inside a venv
      6. <conda env>/share/hepyy_packages/  when running inside a conda/mamba env
      7. ./packages/  otherwise
    """
    for key in ("HEPYY_PACKAGES_DIR", "HEPYY_BUILD_DIR"):
        if key in os.environ:
            return pathlib.Path(os.environ[key]).resolve()
    cfg = _load_project_config()
    for key in ("packages_dir", "build_dir"):
        if key in cfg:
            return pathlib.Path(cfg[key]).resolve()
    return _default_packages_dir().resolve()


def get_build_dir() -> pathlib.Path:
    """Alias for get_packages_dir() — kept for call-site compatibility."""
    return get_packages_dir()


def get_system_packages_dirs() -> list:
    """Return read-only shared package directories (empty list = no overlay).

    Resolution order:
      1. HEPYY_SYSTEM_PACKAGES_DIR env var (colon-separated)
      2. .hepyy.toml  system_packages_dir key

    When unset, returns [] and behaviour is identical to before this feature.
    """
    val = os.environ.get("HEPYY_SYSTEM_PACKAGES_DIR", "")
    if not val:
        cfg = _load_project_config()
        val = cfg.get("system_packages_dir", "")
    return [pathlib.Path(p).resolve() for p in val.split(":") if p.strip()]


def get_registry_path() -> pathlib.Path:
    return get_packages_dir() / "registry.json"


def get_log_dir() -> pathlib.Path:
    return get_packages_dir() / "logs"


def get_recipe_cache_dir() -> pathlib.Path:
    if "HEPYY_RECIPE_CACHE_DIR" in os.environ:
        return pathlib.Path(os.environ["HEPYY_RECIPE_CACHE_DIR"]).resolve()
    return get_packages_dir() / "recipe-cache"


def get_recipe_sources_path() -> pathlib.Path:
    return get_packages_dir() / "recipe-sources.json"
