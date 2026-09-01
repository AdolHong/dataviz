"""Workspace-owned reusable files and their canonical references."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dataviz.errors import WorkspaceError
from dataviz.workspace.models import WorkspaceAssetDefinition


ASSET_REFERENCE_PREFIX = "asset:"


@dataclass(frozen=True, slots=True)
class ResolvedWorkspaceAsset:
    id: str
    path: Path
    media_type: str
    byte_count: int
    content_hash: str

    def metadata(self) -> dict[str, object]:
        return {
            "id": self.id,
            "media_type": self.media_type,
            "byte_count": self.byte_count,
            "content_hash": self.content_hash,
        }


def workspace_asset_reference(identifier: str) -> str:
    return f"{ASSET_REFERENCE_PREFIX}{identifier}"


def workspace_asset_id(value: str) -> str | None:
    if not value.startswith(ASSET_REFERENCE_PREFIX):
        return None
    identifier = value.removeprefix(ASSET_REFERENCE_PREFIX).strip()
    if not identifier or "/" in identifier or "\\" in identifier:
        raise WorkspaceError(
            f"Invalid Workspace Asset reference: {value}",
            details={"code": "workspace_asset_reference_invalid", "reference": value},
        )
    return identifier


def resolve_workspace_asset_reference(
    workspace_root: Path,
    definitions: Mapping[str, WorkspaceAssetDefinition],
    value: str,
    *,
    hash_content: bool = True,
) -> ResolvedWorkspaceAsset | None:
    identifier = workspace_asset_id(value)
    if identifier is None:
        return None
    return resolve_workspace_asset(
        workspace_root,
        definitions,
        identifier,
        hash_content=hash_content,
    )


def resolve_workspace_asset(
    workspace_root: Path,
    definitions: Mapping[str, WorkspaceAssetDefinition],
    identifier: str,
    *,
    hash_content: bool = True,
) -> ResolvedWorkspaceAsset:
    definition = definitions.get(identifier)
    if definition is None:
        raise WorkspaceError(
            f"Unknown Workspace Asset: {identifier}",
            file=workspace_root / "workspace.yaml",
            details={"code": "workspace_asset_unknown", "asset": identifier},
        )
    root = workspace_root.resolve()
    path = (root / definition.path).resolve()
    if not path.is_relative_to(root):
        raise WorkspaceError(
            f"Workspace Asset must stay inside its Workspace: {identifier}",
            file=workspace_root / "workspace.yaml",
            details={
                "code": "workspace_asset_outside",
                "asset": identifier,
                "path": definition.path,
                "resolved_path": str(path),
            },
        )
    if not path.is_file():
        raise WorkspaceError(
            f"Workspace Asset file does not exist: {identifier}",
            file=path,
            details={
                "code": "workspace_asset_missing",
                "asset": identifier,
                "path": definition.path,
            },
        )
    digest = hashlib.sha256()
    if hash_content:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return ResolvedWorkspaceAsset(
        id=identifier,
        path=path,
        media_type=(
            definition.media_type
            or mimetypes.guess_type(path.name)[0]
            or "application/octet-stream"
        ),
        byte_count=path.stat().st_size,
        content_hash=digest.hexdigest() if hash_content else "",
    )


def dashboard_workspace_asset_ids(dashboard) -> tuple[str, ...]:
    identifiers = set(dashboard.definition.assets)
    for _definition_path, source in dashboard.sources.values():
        if getattr(source, "type", None) != "file":
            continue
        identifier = workspace_asset_id(source.path)
        if identifier is not None:
            identifiers.add(identifier)
    return tuple(sorted(identifiers))
