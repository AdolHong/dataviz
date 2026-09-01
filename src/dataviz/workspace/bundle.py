"""Portable Dashboard source bundles with explicit Workspace asset closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import yaml

from dataviz.auth import AdapterResolver
from dataviz.errors import WorkspaceError
from dataviz.filesystem import atomic_copy_file, atomic_write_bytes, atomic_write_text
from dataviz.protocols import DASHBOARD_BUNDLE_SCHEMA
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


_IGNORED_PARTS = {".dataviz", "__pycache__"}
_IGNORED_NAMES = {".DS_Store"}


def _portable_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in _IGNORED_PARTS for part in path.relative_to(root).parts)
        and path.name not in _IGNORED_NAMES
        and not path.name.endswith((".pyc", ".pyo"))
    )


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _portable_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _file_record(source: Path, relative: Path) -> dict[str, Any]:
    return {
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "bytes": source.stat().st_size,
    }


def _workspace_document(workspace: LoadedWorkspace) -> str:
    payload = yaml.safe_load(workspace.definition_path.read_text(encoding="utf-8")) or {}
    payload.pop("folders", None)
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _dashboard_id(path: Path) -> str | None:
    definition = path / "dashboard.yaml"
    if not definition.is_file():
        return None
    try:
        payload = yaml.safe_load(definition.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError):
        return None
    value = payload.get("id") if isinstance(payload, dict) else None
    return str(value) if value else None


def _existing_dashboard(destination: Path, dashboard_id: str) -> Path | None:
    dashboards = destination / "dashboards"
    if not dashboards.is_dir():
        return None
    matches = [
        path.parent
        for path in dashboards.rglob("dashboard.yaml")
        if _dashboard_id(path.parent) == dashboard_id
    ]
    if len(matches) > 1:
        raise WorkspaceError(
            f"Destination contains duplicate Dashboard id: {dashboard_id}",
            file=dashboards,
            details={"code": "dashboard_bundle_duplicate_destination"},
        )
    return matches[0] if matches else None


def _workspace_domain_files(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
) -> list[tuple[Path, Path]]:
    files: dict[Path, Path] = {}
    for definition_path, definition in dashboard.parameter_domains.values():
        if definition_path == dashboard.definition_path or definition_path.is_relative_to(dashboard.root):
            continue
        try:
            definition_relative = definition_path.relative_to(workspace.root)
            code_path = (definition_path.parent / definition.code).resolve()
            code_relative = code_path.relative_to(workspace.root)
        except ValueError as error:
            raise WorkspaceError(
                "Workspace Parameter Domain dependency escapes the Workspace",
                file=definition_path,
                details={"code": "dashboard_bundle_dependency_escape"},
            ) from error
        files[definition_relative] = definition_path
        files[code_relative] = code_path
    return sorted((source, relative) for relative, source in files.items())


def _binding_manifest(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
) -> list[dict[str, Any]]:
    resolver = AdapterResolver(workspace.root)
    bindings = []
    for logical in sorted(dashboard.definition.adapters):
        actual_name, definition = resolver.resolve(logical, dashboard.definition.adapters)
        bindings.append(
            {
                "logical": logical,
                "actual": actual_name,
                "type": definition.type,
                "visibility_scope": definition.visibility_scope,
                "description": definition.description,
                "configured": False,
            }
        )
    return bindings


def _preflight_copy(
    pairs: Iterable[tuple[Path, Path]],
    destination: Path,
) -> tuple[list[tuple[Path, Path]], list[str]]:
    pending: list[tuple[Path, Path]] = []
    reused: list[str] = []
    for source, relative in pairs:
        target = (destination / relative).resolve()
        if not target.is_relative_to(destination):
            raise WorkspaceError(
                f"Bundle target escapes destination: {relative}",
                details={"code": "dashboard_bundle_target_escape"},
            )
        if target.exists():
            source_hash = hashlib.sha256(source.read_bytes()).digest()
            target_hash = hashlib.sha256(target.read_bytes()).digest() if target.is_file() else b""
            if source_hash != target_hash:
                raise WorkspaceError(
                    f"Bundle target conflicts with different content: {relative.as_posix()}",
                    file=target,
                    details={
                        "code": "dashboard_bundle_content_conflict",
                        "path": relative.as_posix(),
                    },
                )
            reused.append(relative.as_posix())
        else:
            pending.append((source, relative))
    return pending, reused


def bundle_dashboard(
    workspace: LoadedWorkspace,
    dashboard_id: str,
    destination: Path,
) -> dict[str, Any]:
    """Copy one Dashboard and shared Domain closure into a portable Workspace."""

    dashboard = workspace.dashboard(dashboard_id)
    destination = destination.resolve()
    if destination.exists() and not destination.is_dir():
        raise WorkspaceError("Bundle destination is not a directory", file=destination)

    source_dashboard_hash = _tree_hash(dashboard.root)
    existing = _existing_dashboard(destination, dashboard_id) if destination.exists() else None
    if existing is not None:
        existing_hash = _tree_hash(existing)
        if existing_hash != source_dashboard_hash:
            raise WorkspaceError(
                f"Dashboard {dashboard_id} already exists with different content",
                file=existing,
                details={
                    "code": "dashboard_bundle_dashboard_conflict",
                    "dashboard": dashboard_id,
                    "source_hash": source_dashboard_hash,
                    "destination_hash": existing_hash,
                },
            )

    target_dashboard_root = existing or destination / "dashboards" / dashboard.root.name
    dashboard_pairs = [] if existing else [
        (
            path,
            target_dashboard_root.relative_to(destination) / path.relative_to(dashboard.root),
        )
        for path in _portable_files(dashboard.root)
    ]
    domain_pairs = _workspace_domain_files(workspace, dashboard)
    pending, reused = _preflight_copy([*dashboard_pairs, *domain_pairs], destination)

    workspace_path = destination / "workspace.yaml"
    create_workspace = not workspace_path.exists()
    if workspace_path.exists():
        try:
            existing_workspace = yaml.safe_load(workspace_path.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise WorkspaceError(
                "Destination workspace.yaml cannot be parsed", file=workspace_path
            ) from error
        if not isinstance(existing_workspace, dict) or existing_workspace.get("kind") != "workspace":
            raise WorkspaceError(
                "Destination workspace.yaml is not a Workspace definition", file=workspace_path
            )

    manifest_path = destination / "dataviz-bundle.json"
    previous_manifest = manifest_path.read_bytes() if manifest_path.is_file() else None
    manifest = json.loads(previous_manifest) if previous_manifest else {
        "schema": DASHBOARD_BUNDLE_SCHEMA,
        "source_workspace": workspace.definition.id,
        "dashboards": [],
    }
    if manifest.get("schema") != DASHBOARD_BUNDLE_SCHEMA:
        raise WorkspaceError(
            "Destination dataviz-bundle.json uses an unsupported schema",
            file=manifest_path,
            details={"code": "dashboard_bundle_manifest_schema"},
        )
    entry = {
        "id": dashboard_id,
        "path": target_dashboard_root.relative_to(destination).as_posix(),
        "content_hash": source_dashboard_hash,
        "parameter_domains": [
            _file_record(source, relative) for source, relative in domain_pairs
        ],
        "adapter_bindings": _binding_manifest(workspace, dashboard),
    }
    entries = [item for item in manifest.get("dashboards", []) if item.get("id") != dashboard_id]
    entries.append(entry)
    manifest["dashboards"] = sorted(entries, key=lambda item: item["id"])

    created: list[Path] = []
    try:
        if create_workspace:
            atomic_write_text(workspace_path, _workspace_document(workspace))
            created.append(workspace_path)
        for source, relative in pending:
            target = destination / relative
            atomic_copy_file(source, target)
            created.append(target)
        atomic_write_text(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        if previous_manifest is None:
            created.append(manifest_path)
    except BaseException:
        if previous_manifest is not None:
            atomic_write_bytes(manifest_path, previous_manifest)
        for path in reversed(created):
            path.unlink(missing_ok=True)
        directories = {
            parent
            for item in created
            for parent in item.parents
            if parent.is_relative_to(destination) and parent != destination
        }
        for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass
        raise

    return {
        "schema": DASHBOARD_BUNDLE_SCHEMA,
        "status": "ready",
        "dashboard": dashboard_id,
        "destination": str(destination),
        "dashboard_hash": source_dashboard_hash,
        "copied": [relative.as_posix() for _, relative in pending],
        "reused": sorted(reused),
        "manifest": str(manifest_path),
        "materializations_copied": False,
        "credentials_copied": False,
    }
