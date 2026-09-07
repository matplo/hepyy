import pathlib
from dataclasses import dataclass, field
from typing import List, Optional

import yaml

from .exceptions import RecipeNotFoundError

_BUILTIN_RECIPES_DIR = pathlib.Path(__file__).parent / "recipes"


def _recipe_sort_key(p: pathlib.Path) -> str:
    stem = p.stem
    return stem if any(c.isdigit() for c in stem) else ""


@dataclass
class Recipe:
    name: str
    version: str
    url: Optional[str]
    build_system: str
    configure_args: List[str] = field(default_factory=list)
    make_jobs: int = 4
    verify_binary: Optional[str] = None
    build_script: Optional[str] = None
    build_script_is_jinja: bool = False  # True when loaded from an external .sh file
    cppyy_namespace: str = ""
    cppyy_headers: List[str] = field(default_factory=list)
    cppyy_libraries: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    python_paths: List[str] = field(default_factory=list)
    generate_modulefile: bool = True  # set False for pure-pip installs that need no env setup
    source_path: Optional[pathlib.Path] = None  # set by load_recipe; None = unknown

    def resolved_url(self, version: Optional[str] = None) -> str:
        v = version or self.version
        return self.url.format(
            version=v,
            version_nodot=v.replace(".", ""),
            version_major=v.split(".")[0],
            version_minor=v.split(".")[1] if "." in v else "",
        )


def load_recipe(path: pathlib.Path) -> Recipe:
    with open(path) as f:
        data = yaml.safe_load(f)

    cppyy = data.get("cppyy", {})
    name = data["name"]
    namespace = cppyy.get("namespace", name)

    # Resolve build_script: if the value is a single-line .sh filename, load
    # the file from the same directory as the YAML and mark it for Jinja2.
    _bs_raw = data.get("build_script")
    _bs_is_jinja = False
    if _bs_raw and isinstance(_bs_raw, str) and "\n" not in _bs_raw.strip():
        _bs_name = _bs_raw.strip()
        if _bs_name.endswith((".sh", ".bash")):
            _script_file = path.parent / _bs_name
            if not _script_file.exists():
                raise RecipeNotFoundError(
                    f"build_script file not found: {_script_file} (referenced from {path})"
                )
            _bs_raw = _script_file.read_text()
            _bs_is_jinja = True

    return Recipe(
        name=name,
        version=str(data["version"]),
        url=data.get("url"),
        build_system=data.get("build_system", "autotools"),
        configure_args=data.get("configure_args", []),
        make_jobs=data.get("make_jobs", 4),
        verify_binary=data.get("verify_binary"),
        build_script=_bs_raw,
        build_script_is_jinja=_bs_is_jinja,
        cppyy_namespace=namespace,
        cppyy_headers=cppyy.get("headers", []),
        cppyy_libraries=cppyy.get("libraries", []),
        depends_on=data.get("depends_on", []),
        python_paths=data.get("python_paths", []),
        generate_modulefile=data.get("generate_modulefile", True),
        source_path=path,
    )


def find_builtin_recipe(name: str, version: Optional[str] = None) -> pathlib.Path:
    pkg_dir = _BUILTIN_RECIPES_DIR / name
    if not pkg_dir.is_dir():
        raise RecipeNotFoundError(f"No built-in recipe for '{name}'")

    yamls = sorted(pkg_dir.glob("*.yaml"), key=_recipe_sort_key, reverse=True)
    if not yamls:
        raise RecipeNotFoundError(f"No recipe files found in {pkg_dir}")

    if version:
        for y in yamls:
            if y.stem == version:
                return y
        raise RecipeNotFoundError(f"No recipe for '{name}' version '{version}'")

    return yamls[0]


def list_builtin_recipes() -> list:
    results = []
    if not _BUILTIN_RECIPES_DIR.is_dir():
        return results
    for pkg_dir in sorted(_BUILTIN_RECIPES_DIR.iterdir()):
        if pkg_dir.is_dir():
            for yaml_file in sorted(pkg_dir.glob("*.yaml"), key=_recipe_sort_key, reverse=True):
                results.append((pkg_dir.name, yaml_file.stem))
    return results


def find_recipe(
    name_or_path: str,
    version: Optional[str] = None,
    recipe_path: Optional[str] = None,
) -> Recipe:
    # Explicit recipe file takes priority
    if recipe_path:
        p = pathlib.Path(recipe_path)
        if not p.exists():
            raise RecipeNotFoundError(f"Recipe file not found: {recipe_path}")
        return load_recipe(p)

    # Check if name_or_path is an existing file path
    candidate = pathlib.Path(name_or_path)
    if candidate.exists() and candidate.suffix in (".yaml", ".yml"):
        return load_recipe(candidate)

    # Support "name/version" shorthand (e.g. heyy install cppyy/3.5.0)
    name = name_or_path
    if "/" in name and version is None:
        parts = name.split("/", 1)
        name, version = parts[0], parts[1]

    from .recipe_sources import search_sources
    found = search_sources(name, version)
    if found:
        return load_recipe(found)

    try:
        path = find_builtin_recipe(name, version)
        return load_recipe(path)
    except RecipeNotFoundError:
        pass

    raise RecipeNotFoundError(
        f"No recipe found for '{name}'"
        + (f" version '{version}'" if version else "")
        + ". Run 'hepyy avail' to see available recipes, "
        + "or 'hepyy recipe update' to refresh from GitHub."
    )
