import json
import pathlib
from datetime import datetime, timezone
from typing import Optional

from .config import get_registry_path


def _latest_version(versions: dict) -> Optional[str]:
    """Return the key of the highest-version record in a {version: record} dict."""
    if not versions:
        return None
    try:
        from packaging.version import Version
        return max(versions, key=lambda v: Version(v))
    except Exception:
        return max(versions)


def _migrate_v1(data: dict) -> dict:
    """Upgrade a schema_version=1 registry to v2 (name → {version: record})."""
    migrated: dict = {}
    for name, rec in data.get("packages", {}).items():
        ver = rec.get("version", "unknown")
        migrated[name] = {ver: rec}
    return {"schema_version": 2, "packages": migrated}


def _flatten_system_pkgs(raw_pkgs: dict) -> dict:
    """Convert a system registry's packages dict (v1 or v2) to {name: latest_record}."""
    result: dict = {}
    for name, val in raw_pkgs.items():
        if isinstance(val, dict) and not val.get("version"):
            # v2: {version: record, ...}
            latest = _latest_version(val)
            if latest:
                result[name] = val[latest]
        else:
            # v1: plain record
            result[name] = val
    return result


class Registry:
    def __init__(self, path: Optional[pathlib.Path] = None, system_paths: Optional[list] = None):
        self._path = path or get_registry_path()
        self._data = self._load()
        self._system_pkgs: list[dict] = []
        for sp in (system_paths or []):
            reg_file = pathlib.Path(sp) / "registry.json"
            if reg_file.exists():
                try:
                    data = json.loads(reg_file.read_text())
                    pkgs = data.get("packages", {})
                    if pkgs:
                        self._system_pkgs.append(_flatten_system_pkgs(pkgs))
                except (json.JSONDecodeError, OSError):
                    pass

    def _load(self) -> dict:
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            if raw.get("schema_version", 1) == 1:
                raw = _migrate_v1(raw)
            return raw
        return {"schema_version": 2, "packages": {}}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    def register(self, name: str, version: str, record: dict) -> None:
        record["installed_at"] = datetime.now(timezone.utc).isoformat()
        if name not in self._data["packages"]:
            self._data["packages"][name] = {}
        self._data["packages"][name][version] = record
        self.save()

    def get(self, name: str, version: Optional[str] = None) -> Optional[dict]:
        versions = self._data["packages"].get(name)
        if versions:
            if version is not None:
                rec = versions.get(version)
                if rec is not None:
                    return rec
            else:
                latest = _latest_version(versions)
                if latest:
                    return versions[latest]
        # Fall through to system packages (already flattened to {name: latest_record})
        for sys_pkgs in self._system_pkgs:
            rec = sys_pkgs.get(name)
            if rec is not None:
                if version is None or rec.get("version") == version:
                    return rec
        return None

    def is_installed(self, name: str, version: Optional[str] = None) -> bool:
        versions = self._data["packages"].get(name)
        if versions:
            if version is None:
                return True
            return version in versions
        for sys_pkgs in self._system_pkgs:
            rec = sys_pkgs.get(name)
            if rec is not None:
                if version is None or rec.get("version") == version:
                    return True
        return False

    def all_packages(self) -> dict:
        """Return {name: latest_record} merged across system and user registries."""
        merged: dict = {}
        for sys_pkgs in reversed(self._system_pkgs):
            merged.update(sys_pkgs)
        for name, versions in self._data["packages"].items():
            latest = _latest_version(versions)
            if latest:
                merged[name] = versions[latest]
        return merged

    def all_versions(self, name: str) -> dict:
        """Return {version: record} for all installed versions of name."""
        result: dict = {}
        # System packages (already flattened to latest only)
        for sys_pkgs in self._system_pkgs:
            rec = sys_pkgs.get(name)
            if rec is not None:
                ver = rec.get("version", "unknown")
                result[ver] = rec
        # User registry (all versions)
        versions = self._data["packages"].get(name, {})
        result.update(versions)
        return result

    def remove(self, name: str, version: Optional[str] = None) -> None:
        if name in self._data["packages"]:
            if version is None:
                del self._data["packages"][name]
            else:
                self._data["packages"][name].pop(version, None)
                if not self._data["packages"][name]:
                    del self._data["packages"][name]
        self.save()


_registry: Optional[Registry] = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        from .config import get_system_packages_dirs
        _registry = Registry(system_paths=get_system_packages_dirs())
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = None
