"""Read pip-owned native payloads without writing to the source-build registry."""
import json
from importlib import metadata
from pathlib import Path


PACKAGES = {name: f"hepyy-{name}" for name in ("fastjet", "fjcontrib", "hepmc3", "lhapdf", "pythia8")}


def wheel_record(name, version=None):
    # Native providers follow the hepyy-<package> distribution and
    # hepyy_<package>/manifest.json payload convention. Discover only the
    # requested distribution, without importing it or scanning the registry.
    distribution = f"hepyy-{name.replace('_', '-')}"
    try:
        dist = metadata.distribution(distribution)
    except metadata.PackageNotFoundError:
        return None
    prefix = Path(dist.locate_file(distribution.replace("-", "_"))).resolve()
    manifest_path = prefix / "manifest.json"
    if not manifest_path.is_file() and name not in PACKAGES:
        return None
    manifest = json.loads(manifest_path.read_text())
    manifest_name = manifest.get("name", "")
    if (manifest.get("schema_version") != 1 or not isinstance(manifest_name, str)
            or manifest_name.replace("_", "-") != name.replace("_", "-")):
        raise RuntimeError(f"Invalid native wheel manifest: {prefix}")
    if manifest.get("distribution_version") != dist.version:
        raise RuntimeError(f"Native wheel metadata/version mismatch: {distribution}")
    if version is not None and version != manifest["version"]:
        return None
    record = dict(manifest)
    record.update(prefix=str(prefix), include_dir=str(prefix / "include"),
                  lib_dir=str(prefix / "lib"), provider="wheel")
    return record


def validate_dependencies(record, dependencies):
    """Reject incompatible native providers before loading dependent C++ code."""
    for name, abi in record.get("requires_native", {}).items():
        dep = dependencies.get(name)
        if not dep or dep.get("provider") != "wheel" or dep.get("abi") != abi:
            raise RuntimeError(
                f"{record['name']} wheel requires {name} wheel ABI {abi}. "
                "A source/shell installation or incompatible wheel was selected. "
                "Use a clean environment with matching native wheels, or build "
                "both packages with 'heyy install'."
            )
