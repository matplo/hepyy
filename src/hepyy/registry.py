import json
import pathlib
from datetime import datetime, timezone
from typing import Optional

from .config import get_registry_path


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
                        self._system_pkgs.append(pkgs)
                except (json.JSONDecodeError, OSError):
                    pass

    def _load(self) -> dict:
        if self._path.exists():
            return json.loads(self._path.read_text())
        return {"schema_version": 1, "packages": {}}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    def register(self, name: str, record: dict) -> None:
        record["installed_at"] = datetime.now(timezone.utc).isoformat()
        self._data["packages"][name] = record
        self.save()

    def get(self, name: str) -> Optional[dict]:
        result = self._data["packages"].get(name)
        if result is not None:
            return result
        for sys_pkgs in self._system_pkgs:
            result = sys_pkgs.get(name)
            if result is not None:
                return result
        return None

    def is_installed(self, name: str) -> bool:
        if name in self._data["packages"]:
            return True
        return any(name in sys_pkgs for sys_pkgs in self._system_pkgs)

    def all_packages(self) -> dict:
        merged: dict = {}
        for sys_pkgs in reversed(self._system_pkgs):
            merged.update(sys_pkgs)
        merged.update(self._data["packages"])
        return merged

    def remove(self, name: str) -> None:
        self._data["packages"].pop(name, None)
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
