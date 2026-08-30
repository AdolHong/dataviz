"""Local code, Python dependency, and browser asset validation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from dataviz.errors import Diagnostic

from dataviz.workspace.loading.loaded_types import LoadedWorkspace


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


_PYODIDE_PACKAGE_VERSIONS: dict[str, dict[str, str]] = {
    # Generated from the official full/pyodide-lock.json for the Runtime pinned
    # by WorkspaceDefinition. Keeping this versioned prevents a stale global
    # native-package blacklist from rejecting packages that Pyodide later ships.
    "314.0.4": {
        "duckdb": "1.5.1",
        "jinja2": "3.1.6",
        "lightgbm": "4.6.0",
        "matplotlib": "3.10.8",
        "networkx": "3.6.1",
        "numpy": "2.4.3",
        "packaging": "26.1",
        "pandas": "3.0.2",
        "polars": "1.33.1",
        "pyarrow": "22.0.0",
        "pydantic": "2.12.5",
        "scikit-learn": "1.8.0",
        "scipy": "1.18.0",
        "statsmodels": "0.14.6",
        "sympy": "1.14.0",
        "xgboost": "2.1.4",
    }
}


_PYODIDE_CORE_ASSETS = (
    "pyodide.mjs",
    "pyodide.asm.mjs",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
    "package.json",
)


def _browser_python_bundle_requirements(
    workspace: LoadedWorkspace,
) -> list[tuple[str, Path]]:
    """Return dependencies that must be resolvable without a network request."""
    requirements: list[tuple[str, Path]] = []
    live_bundle = workspace.definition.runtime.pyodide_asset_policy == "bundle"
    for dashboard in workspace.dashboards.values():
        for transform_path, transform in dashboard.interactive_transforms.values():
            if transform.runtime != "browser-python":
                continue
            exported_bundle = (
                transform.export.mode == "interactive" and transform.export.assets == "bundle"
            )
            if not live_bundle and not exported_bundle:
                continue
            requirements.extend(
                (dependency, transform_path) for dependency in transform.python_dependencies
            )
    return requirements


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_pyodide_bundle(
    workspace: LoadedWorkspace,
    bundle_path: Path,
) -> list[Diagnostic]:
    """Validate the core Runtime and the offline wheel dependency closure."""
    field = "runtime.pyodide_bundle_path"
    symlinks = sorted(
        path.relative_to(bundle_path).as_posix()
        for path in bundle_path.rglob("*")
        if path.is_symlink()
    )
    if symlinks:
        return [
            Diagnostic(
                "error",
                "Pyodide bundle cannot contain symbolic links",
                str(bundle_path),
                field,
                "pyodide_bundle_symlink_unsupported",
                {"symlinks": symlinks},
            )
        ]
    missing_core = [name for name in _PYODIDE_CORE_ASSETS if not (bundle_path / name).is_file()]
    if missing_core:
        return [
            Diagnostic(
                "error",
                "Pyodide bundle is missing required Runtime assets: " + ", ".join(missing_core),
                str(bundle_path),
                field,
                "pyodide_bundle_incomplete",
                {"missing": missing_core},
            )
        ]

    package_manifest_path = bundle_path / "package.json"
    try:
        package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [
            Diagnostic(
                "error",
                f"Pyodide package manifest is invalid: {error}",
                str(package_manifest_path),
                field,
                "pyodide_bundle_manifest_invalid",
            )
        ]
    bundle_version = package_manifest.get("version") if isinstance(package_manifest, dict) else None
    expected_version = workspace.definition.runtime.pyodide_version
    if bundle_version != expected_version:
        return [
            Diagnostic(
                "error",
                f"Pyodide bundle version is {bundle_version!r}; expected {expected_version}",
                str(package_manifest_path),
                field,
                "pyodide_bundle_version_mismatch",
                {"expected": expected_version, "actual": bundle_version},
            )
        ]

    lock_path = bundle_path / "pyodide-lock.json"
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [
            Diagnostic(
                "error",
                f"Pyodide bundle lockfile is invalid: {error}",
                str(lock_path),
                field,
                "pyodide_bundle_lock_invalid",
            )
        ]
    raw_packages = lock.get("packages") if isinstance(lock, dict) else None
    if not isinstance(raw_packages, dict):
        return [
            Diagnostic(
                "error",
                "Pyodide bundle lockfile must contain a packages object",
                str(lock_path),
                field,
                "pyodide_bundle_lock_invalid",
            )
        ]

    marker_environment = default_environment()
    lock_info = lock.get("info", {}) if isinstance(lock, dict) else {}
    python_full_version = lock_info.get("python") if isinstance(lock_info, dict) else None
    if not isinstance(python_full_version, str) or not python_full_version:
        python_full_version = marker_environment["python_full_version"]
    python_version = ".".join(python_full_version.split(".")[:2])
    marker_environment.update(
        {
            "implementation_name": "cpython",
            "implementation_version": python_full_version,
            "os_name": "posix",
            "platform_machine": "wasm32",
            "platform_python_implementation": "CPython",
            "platform_system": "Emscripten",
            "python_full_version": python_full_version,
            "python_version": python_version,
            "sys_platform": "emscripten",
        }
    )

    packages: dict[str, dict[str, Any]] = {}
    for key, value in raw_packages.items():
        if not isinstance(value, dict):
            continue
        package_name = value.get("name") if isinstance(value.get("name"), str) else key
        packages[canonicalize_name(package_name)] = value

    diagnostics: list[Diagnostic] = []
    roots: set[str] = set()
    requirements = _browser_python_bundle_requirements(workspace)
    if requirements:
        # The Worker loads micropip before installing any declared dependency.
        roots.add("micropip")
    for value, transform_path in requirements:
        try:
            requirement = Requirement(value)
        except InvalidRequirement:
            # The normal dependency validator reports the authoring error.
            continue
        # Browser dependencies are resolved by Pyodide, so environment markers
        # must be evaluated for Emscripten rather than the host running validate.
        if requirement.marker and not requirement.marker.evaluate(environment=marker_environment):
            continue
        if requirement.url:
            diagnostics.append(
                Diagnostic(
                    "error",
                    "A bundled browser-python report cannot be offline while a Python "
                    f"dependency uses an external URL: {requirement}",
                    str(transform_path),
                    "python_dependencies",
                    "pyodide_bundle_external_dependency",
                    {"dependency": value},
                )
            )
            continue
        name = canonicalize_name(requirement.name)
        roots.add(name)
        package = packages.get(name)
        if package is None:
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Pyodide bundle lockfile does not contain {requirement.name}",
                    str(lock_path),
                    field,
                    "pyodide_bundle_dependency_missing",
                    {"dependency": value, "package": name},
                )
            )
            continue
        version = package.get("version")
        if (
            isinstance(version, str)
            and requirement.specifier
            and version not in requirement.specifier
        ):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Pyodide bundle contains {requirement.name}=={version}; "
                    f"expected {requirement.specifier}",
                    str(lock_path),
                    field,
                    "pyodide_bundle_dependency_version_mismatch",
                    {"dependency": value, "available": version},
                )
            )

    required_packages: set[str] = set()
    missing_lock_packages: set[str] = set()
    pending = list(roots)
    while pending:
        name = canonicalize_name(pending.pop())
        if name in required_packages or name in missing_lock_packages:
            continue
        package = packages.get(name)
        if package is None:
            missing_lock_packages.add(name)
            continue
        required_packages.add(name)
        dependencies = package.get("depends", [])
        if isinstance(dependencies, list):
            pending.extend(dependency for dependency in dependencies if isinstance(dependency, str))

    if missing_lock_packages:
        diagnostics.append(
            Diagnostic(
                "error",
                "Pyodide bundle lockfile is missing transitive packages: "
                + ", ".join(sorted(missing_lock_packages)),
                str(lock_path),
                field,
                "pyodide_bundle_dependency_closure_incomplete",
                {"missing_packages": sorted(missing_lock_packages)},
            )
        )

    missing_assets: list[dict[str, str]] = []
    unhashed_assets: list[dict[str, str]] = []
    corrupt_assets: list[dict[str, str]] = []
    for name in sorted(required_packages):
        package = packages[name]
        filename = package.get("file_name")
        if not isinstance(filename, str) or not filename.strip():
            missing_assets.append({"package": name, "file": "<missing file_name>"})
            continue
        asset = (bundle_path / filename).resolve()
        if not _is_within(asset, bundle_path) or not asset.is_file():
            missing_assets.append({"package": name, "file": filename})
            continue
        expected_hash = package.get("sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", expected_hash
        ):
            unhashed_assets.append({"package": name, "file": filename})
        elif _file_sha256(asset) != expected_hash.lower():
            corrupt_assets.append({"package": name, "file": filename})

    if missing_assets:
        diagnostics.append(
            Diagnostic(
                "error",
                "Pyodide bundle is missing wheels required by browser-python",
                str(bundle_path),
                field,
                "pyodide_bundle_wheels_missing",
                {"missing": missing_assets},
            )
        )
    if unhashed_assets:
        diagnostics.append(
            Diagnostic(
                "error",
                "Pyodide bundle lockfile lacks a valid SHA-256 for required package files",
                str(lock_path),
                field,
                "pyodide_bundle_wheel_hash_missing",
                {"unhashed": unhashed_assets},
            )
        )
    if corrupt_assets:
        diagnostics.append(
            Diagnostic(
                "error",
                "Pyodide bundle contains package files whose SHA-256 does not match the lockfile",
                str(bundle_path),
                field,
                "pyodide_bundle_wheel_hash_mismatch",
                {"corrupt": corrupt_assets},
            )
        )
    return diagnostics


def _browser_python_dependency_diagnostic(
    value: str, pyodide_version: str
) -> tuple[str, str, str] | None:
    """Return (level, code, message) for an offline, versioned Pyodide check."""
    try:
        requirement = Requirement(value)
    except InvalidRequirement as error:
        return (
            "error",
            "pyodide_dependency_invalid",
            f"Invalid browser-python dependency {value!r}: {error}",
        )
    normalized = requirement.name.lower().replace("_", "-")
    if requirement.url:
        filename = Path(urlparse(requirement.url).path).name.lower()
        if filename.endswith(".whl") and not (
            "none-any.whl" in filename or "emscripten" in filename or "wasm32" in filename
        ):
            return (
                "error",
                "pyodide_wheel_incompatible",
                f"browser-python wheel is not pure Python or Emscripten/WASM: {filename}",
            )
        if not filename.endswith((".whl", ".tar.gz", ".zip")):
            return (
                "warning",
                "pyodide_dependency_unverified",
                f"Could not classify browser-python dependency URL: {requirement.url}",
            )
        return None
    exact_versions = {
        spec.version
        for spec in requirement.specifier
        if spec.operator == "==" and "*" not in spec.version
    }
    if len(exact_versions) != 1 or len(list(requirement.specifier)) != 1:
        return (
            "error",
            "pyodide_dependency_unpinned",
            f"browser-python dependency {requirement.name} must use one exact == version",
        )
    pinned = next(iter(exact_versions))
    catalog = _PYODIDE_PACKAGE_VERSIONS.get(pyodide_version)
    if catalog is None:
        return (
            "warning",
            "pyodide_catalog_unavailable",
            f"Dataviz has no offline package catalog for Pyodide {pyodide_version}; "
            f"verify {requirement.name}=={pinned} against that Runtime's pyodide-lock.json",
        )
    available = catalog.get(normalized)
    if available is not None and available != pinned:
        return (
            "error",
            "pyodide_dependency_version_mismatch",
            f"Pyodide {pyodide_version} bundles {requirement.name}=={available}, not {pinned}",
        )
    if available is None:
        return (
            "warning",
            "pyodide_dependency_unverified",
            f"{requirement.name}=={pinned} is not in the bundled Pyodide "
            f"{pyodide_version} catalog; verify that a pure-Python or WASM wheel exists",
        )
    return None
