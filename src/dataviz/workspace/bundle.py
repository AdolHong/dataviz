"""Portable Dashboard source bundles with explicit Workspace asset closure."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

import yaml

from dataviz.auth import AdapterResolver
from dataviz.errors import WorkspaceError
from dataviz.filesystem import atomic_copy_file, atomic_write_text
from dataviz.protocols import DASHBOARD_BUNDLE_SCHEMA
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace
from dataviz.workspace.assets import dashboard_workspace_asset_ids


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


def _workspace_payload(
    workspace: LoadedWorkspace,
    asset_ids: Iterable[str],
) -> dict[str, Any]:
    payload = yaml.safe_load(workspace.definition_path.read_text(encoding="utf-8")) or {}
    payload.pop("folders", None)
    definitions = payload.get("assets", {})
    selected = {
        identifier: definitions[identifier]
        for identifier in sorted(asset_ids)
        if identifier in definitions
    }
    if selected:
        payload["assets"] = selected
    else:
        payload.pop("assets", None)
    return payload


def _workspace_asset_files(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
) -> list[tuple[str, Path, Path]]:
    files = []
    for identifier in dashboard_workspace_asset_ids(dashboard):
        asset = workspace.asset(identifier)
        files.append((identifier, asset.path, asset.path.relative_to(workspace.root)))
    return files


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


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _require_empty_destination(destination: Path) -> bool:
    """Return whether an existing empty directory must be replaced at publish time."""

    if not destination.exists():
        return False
    if not destination.is_dir():
        raise WorkspaceError(
            "Bundle destination must be a new path or an empty directory",
            file=destination,
            details={"code": "dashboard_bundle_destination_not_directory"},
        )
    if next(destination.iterdir(), None) is not None:
        raise WorkspaceError(
            "Bundle destination is not empty; Bundle never merges or overwrites",
            file=destination,
            details={"code": "dashboard_bundle_destination_not_empty"},
        )
    return True


def _snapshot_pairs(
    pairs: Iterable[tuple[Path, Path]],
    staging: Path,
) -> dict[Path, dict[str, Any]]:
    """Copy one immutable source snapshot and reject source changes during copying."""

    unique: dict[Path, Path] = {}
    for source, relative in pairs:
        if relative.is_absolute() or ".." in relative.parts:
            raise WorkspaceError(
                f"Bundle target escapes destination: {relative}",
                details={"code": "dashboard_bundle_target_escape"},
            )
        source = source.resolve()
        current = unique.get(relative)
        if current is not None and current != source:
            raise WorkspaceError(
                f"Multiple Bundle inputs target {relative.as_posix()}",
                details={
                    "code": "dashboard_bundle_target_collision",
                    "path": relative.as_posix(),
                },
            )
        unique[relative] = source

    expected = {
        relative: {"source": source, "sha256": digest, "bytes": size}
        for relative, source in unique.items()
        for digest, size in [_hash_file(source)]
    }
    for relative, record in expected.items():
        atomic_copy_file(record["source"], staging / relative)

    for relative, record in expected.items():
        target_digest, target_size = _hash_file(staging / relative)
        source_digest, source_size = _hash_file(record["source"])
        if (
            target_digest != record["sha256"]
            or target_size != record["bytes"]
            or source_digest != record["sha256"]
            or source_size != record["bytes"]
        ):
            raise WorkspaceError(
                f"Bundle source changed while copying: {relative.as_posix()}",
                file=record["source"],
                details={
                    "code": "dashboard_bundle_source_changed",
                    "path": relative.as_posix(),
                },
            )
    return expected


def _snapshot_record(
    records: dict[Path, dict[str, Any]],
    relative: Path,
) -> dict[str, Any]:
    record = records[relative]
    return {
        "path": relative.as_posix(),
        "sha256": record["sha256"],
        "bytes": record["bytes"],
    }


def bundle_dashboard(
    workspace: LoadedWorkspace,
    dashboard_id: str,
    destination: Path,
) -> dict[str, Any]:
    """Publish one Dashboard closure as a new, standalone Workspace snapshot."""

    dashboard = workspace.dashboard(dashboard_id)
    destination = destination.resolve()
    if destination == workspace.root or destination.is_relative_to(dashboard.root):
        raise WorkspaceError(
            "Bundle destination cannot be the source Workspace or Dashboard directory",
            file=destination,
            details={"code": "dashboard_bundle_destination_overlaps_source"},
        )
    replace_empty_destination = _require_empty_destination(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    target_dashboard_relative = Path("dashboards") / dashboard.root.name
    dashboard_pairs = [
        (
            path,
            target_dashboard_relative / path.relative_to(dashboard.root),
        )
        for path in _portable_files(dashboard.root)
    ]
    asset_files = _workspace_asset_files(workspace, dashboard)
    asset_pairs = [(source, relative) for _identifier, source, relative in asset_files]
    source_pairs = [*dashboard_pairs, *asset_pairs]
    workspace_content = yaml.safe_dump(
        _workspace_payload(workspace, dashboard_workspace_asset_ids(dashboard)),
        allow_unicode=True,
        sort_keys=False,
    )
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.bundle-",
            dir=destination.parent,
        )
    ).resolve()
    published = False
    try:
        records = _snapshot_pairs(source_pairs, staging)
        workspace_path = staging / "workspace.yaml"
        atomic_write_text(workspace_path, workspace_content)

        target_dashboard_root = staging / target_dashboard_relative
        source_dashboard_hash = _tree_hash(target_dashboard_root)
        entry = {
            "id": dashboard_id,
            "path": target_dashboard_relative.as_posix(),
            "content_hash": source_dashboard_hash,
            # Parameter Domain definitions and SQL are Dashboard-owned and are
            # already included in the Dashboard directory snapshot.
            "parameter_domains": [],
            "assets": [
                {"id": identifier, **_snapshot_record(records, relative)}
                for identifier, _source, relative in asset_files
            ],
            "adapter_bindings": _binding_manifest(workspace, dashboard),
        }
        manifest = {
            "schema": DASHBOARD_BUNDLE_SCHEMA,
            "source_workspace": workspace.definition.id,
            "dashboards": [entry],
        }
        manifest_path = staging / "dataviz-bundle.json"
        atomic_write_text(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

        # Recheck immediately before publication so a concurrent writer can never
        # turn an empty destination into an implicit merge target.
        if destination.exists():
            _require_empty_destination(destination)
            destination.rmdir()
        staging.rename(destination)
        published = True
    except BaseException:
        if replace_empty_destination and not destination.exists():
            destination.mkdir(parents=False, exist_ok=True)
        raise
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)

    return {
        "schema": DASHBOARD_BUNDLE_SCHEMA,
        "status": "ready",
        "dashboard": dashboard_id,
        "destination": str(destination),
        "dashboard_hash": source_dashboard_hash,
        "copied": sorted({relative.as_posix() for _, relative in source_pairs}),
        "reused": [],
        "manifest": str(destination / "dataviz-bundle.json"),
        "materializations_copied": False,
        "credentials_copied": False,
    }
