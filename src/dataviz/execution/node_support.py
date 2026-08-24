from __future__ import annotations

import hashlib
import importlib.metadata
import sys
from pathlib import Path
from typing import Any, Mapping

from packaging.requirements import Requirement

from dataviz.filesystem import sha256_file


_CORE_RUNTIME_PACKAGES = {"workspace-dataviz", "pandas", "pyarrow", "pydantic"}


def hash_path(path: Path) -> str:
    """Hash one declared code/data dependency without transient bytecode state."""
    if not path.exists():
        raise FileNotFoundError(f"Declared dependency does not exist: {path}")
    if path.is_file():
        return sha256_file(path)
    if not path.is_dir():
        raise ValueError(f"Declared dependency is neither a file nor directory: {path}")
    digest = hashlib.sha256()
    for child in sorted(
        value
        for value in path.rglob("*")
        if value.is_file()
        and "__pycache__" not in value.parts
        and value.suffix not in {".pyc", ".pyo"}
        and ".git" not in value.parts
    ):
        digest.update(str(child.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        with child.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def package_fingerprint(requirements: list[str]) -> dict[str, str]:
    """Fingerprint the shared Python node ABI and declared extra packages."""
    names = set(_CORE_RUNTIME_PACKAGES)
    for value in requirements:
        try:
            names.add(Requirement(value).name)
        except Exception:
            # Validation reports malformed requirements. Keeping the raw value in
            # the fingerprint prevents an invalid declaration from sharing cache.
            names.add(value)
    versions: dict[str, str] = {}
    for name in sorted(names):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "missing"
    versions["python"] = ".".join(map(str, sys.version_info[:3]))
    return versions


def output_status(outputs: Mapping[str, Any]) -> str:
    """Use empty only when at least one table exists and every table is empty."""
    row_counts = [
        int(item.metadata.get("row_count", 0))
        for item in outputs.values()
        if item.kind == "table"
    ]
    return "empty" if row_counts and all(value == 0 for value in row_counts) else "ready"
