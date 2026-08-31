"""Local code, Python dependency, and browser asset validation."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement


def _code_path(definition_path: Path, value: str) -> Path:
    return (definition_path.parent / value).resolve()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _python_dependency_error(value: str) -> str | None:
    try:
        requirement = Requirement(value)
    except InvalidRequirement as error:
        return f"Invalid Python dependency {value!r}: {error}"
    if requirement.marker and not requirement.marker.evaluate():
        return None
    try:
        version = importlib.metadata.version(requirement.name)
    except importlib.metadata.PackageNotFoundError:
        return f"Python dependency is not installed: {requirement.name}"
    if requirement.specifier and version not in requirement.specifier:
        return (
            f"Python dependency {requirement.name} has version {version}; "
            f"expected {requirement.specifier}"
        )
    return None
