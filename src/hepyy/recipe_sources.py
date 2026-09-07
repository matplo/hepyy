import hashlib
import json
import pathlib
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

from urllib.parse import urlparse

from .config import get_recipe_cache_dir, get_recipe_sources_path
from .recipe import _recipe_sort_key
from .exceptions import HeppyyierError


def _sources_data() -> dict:
    path = get_recipe_sources_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"sources": []}


def _save_sources(data: dict) -> None:
    path = get_recipe_sources_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _parse_github_url(url: str) -> tuple:
    """Return (clone_url, subtree) from a GitHub URL.

    Handles:
      https://github.com/user/repo
      https://github.com/user/repo/tree/branch/subdir
    """
    m = re.match(
        r"https://github\.com/([^/]+/[^/]+?)(?:/tree/[^/]+(/.*)?)?$", url
    )
    if not m:
        raise HeppyyierError(
            f"Unsupported URL format: {url}\n"
            "Expected: https://github.com/user/repo[/tree/branch[/subdir]]"
        )
    repo_path = m.group(1)
    subtree = (m.group(2) or "").lstrip("/")
    clone_url = f"https://github.com/{repo_path}.git"
    return clone_url, subtree


def _url_hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def add_source(url: str) -> None:
    data = _sources_data()
    existing_urls = {s["url"] for s in data["sources"]}
    if url in existing_urls:
        print(f"Source already registered: {url}")
        return

    clone_url, subtree = _parse_github_url(url)
    cache_dir = get_recipe_cache_dir() / _url_hash(url)
    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    if cache_dir.exists():
        print(f"Updating existing clone at {cache_dir}")
        subprocess.check_call(["git", "-C", str(cache_dir), "pull", "--ff-only"])
    else:
        print(f"Cloning {clone_url} ...")
        subprocess.check_call(
            ["git", "clone", "--depth=1", clone_url, str(cache_dir)]
        )

    data["sources"].append(
        {
            "url": url,
            "clone_url": clone_url,
            "subtree": subtree,
            "local_path": str(cache_dir),
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_sources(data)
    print(f"Added recipe source: {url}")


def update_sources() -> None:
    data = _sources_data()
    for src in data["sources"]:
        local = pathlib.Path(src["local_path"])
        if local.exists():
            print(f"Updating {src['url']} ...")
            subprocess.check_call(["git", "-C", str(local), "pull", "--ff-only"])
        else:
            print(f"Re-cloning {src['url']} ...")
            subprocess.check_call(
                ["git", "clone", "--depth=1", src["clone_url"], str(local)]
            )


def remove_source(url: str) -> None:
    import shutil
    data = _sources_data()
    new_sources = []
    removed = False
    for src in data["sources"]:
        if src["url"] == url:
            local = pathlib.Path(src["local_path"])
            if local.exists():
                shutil.rmtree(local)
            removed = True
        else:
            new_sources.append(src)
    if not removed:
        raise HeppyyierError(f"Source not found: {url}")
    data["sources"] = new_sources
    _save_sources(data)
    print(f"Removed recipe source: {url}")


def list_sources() -> list:
    return _sources_data()["sources"]


def search_sources(name: str, version: Optional[str] = None) -> Optional[pathlib.Path]:
    for src in _sources_data()["sources"]:
        base = pathlib.Path(src["local_path"])
        if src.get("subtree"):
            base = base / src["subtree"]
        if not base.is_dir():
            continue

        pkg_dir = base / name
        if not pkg_dir.is_dir():
            continue

        yamls = sorted(pkg_dir.glob("*.yaml"), key=_recipe_sort_key, reverse=True)
        if not yamls:
            continue

        if version:
            for y in yamls:
                if y.stem == version:
                    return y
        else:
            return yamls[0]

    return None


def list_all_remote_recipes() -> list:
    results = []
    for src in _sources_data()["sources"]:
        base = pathlib.Path(src["local_path"])
        if src.get("subtree"):
            base = base / src["subtree"]
        if not base.is_dir():
            continue
        for pkg_dir in sorted(base.iterdir()):
            if pkg_dir.is_dir():
                for y in sorted(pkg_dir.glob("*.yaml"), key=_recipe_sort_key, reverse=True):
                    results.append((pkg_dir.name, y.stem, src["url"]))
    return results
