from __future__ import annotations

import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Iterable

import yaml

from dataviz.errors import WorkspaceError
from dataviz.workspace.loader import DashboardCatalogEntry, read_yaml
from dataviz.workspace.naming import (
    DASHBOARD_TRASH_PREFIX,
    FOLDER_TRASH_PREFIX,
    TRASH_SEGMENT,
    DashboardLocation,
    dashboard_trash_id,
    dashboard_trash_name,
    decode_dashboard_name,
    decode_dashboard_path,
    encode_dashboard_name,
    folder_id,
    folder_segments,
    folder_trash_id,
    folder_trash_segments,
    normalize_logical_path,
    validate_segment,
)


_LOCK = threading.RLock()


def _is_prefix(prefix: tuple[str, ...], value: tuple[str, ...]) -> bool:
    return len(value) >= len(prefix) and value[: len(prefix)] == prefix


def _path_key(parts: Iterable[str]) -> tuple[str, ...]:
    return tuple(part.casefold() for part in parts)


class NavigationEditor:
    """Edit logical navigation by renaming physical dashboard directories.

    Dashboard placement is encoded in ``dashboards/<folder>##<dashboard>``.
    ``workspace.yaml`` stores only folders that must exist independently of a
    dashboard (plus ordering and unrelated workspace settings).
    """

    def __init__(self, workspace_root: Path):
        self.root = workspace_root.resolve()
        self.workspace_path = self.root / "workspace.yaml"
        self.dashboards_root = self.root / "dashboards"

    def _read(self) -> dict[str, Any]:
        try:
            document = read_yaml(self.workspace_path)
        except WorkspaceError:
            document = {
                "schema": "dataviz/workspace/v1",
                "kind": "workspace",
                "id": self.root.name,
                "title": self.root.name,
            }
        return document

    def _legacy_folders(
        self, items: list[dict[str, Any]], parent: tuple[str, ...] = ()
    ) -> list[dict[str, Any]]:
        folders: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict) or item.get("kind", "dashboard") != "folder":
                continue
            title = validate_segment(str(item.get("title") or item.get("id") or ""))
            current = (*parent, title)
            folders.append({"path": "/".join(current), "order": int(item.get("order", 0))})
            folders.extend(self._legacy_folders(item.get("children") or [], current))
        return folders

    def _folder_records(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        configured = document.get("folders")
        if isinstance(configured, list):
            records = [dict(item) for item in configured if isinstance(item, dict)]
        else:
            records = self._legacy_folders(document.get("navigation") or [])
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[bool, tuple[str, ...]]] = set()
        for record in records:
            raw = str(record.get("path", "")).replace("\\", "/").strip("/")
            trashed = raw == TRASH_SEGMENT or raw.startswith(f"{TRASH_SEGMENT}/")
            logical = raw[len(TRASH_SEGMENT) :].strip("/") if trashed else raw
            segments = normalize_logical_path(logical)
            key = (trashed, _path_key(segments))
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "path": self._record_path(segments, trashed=trashed),
                    "order": int(record.get("order", 0)),
                }
            )
        return normalized

    @staticmethod
    def _record_path(segments: tuple[str, ...], *, trashed: bool = False) -> str:
        logical = "/".join(segments)
        return f"{TRASH_SEGMENT}/{logical}" if trashed else logical

    def _write(self, document: dict[str, Any], records: list[dict[str, Any]]) -> None:
        document = dict(document)
        document["folders"] = sorted(
            records,
            key=lambda item: (
                str(item["path"]).casefold(),
                int(item.get("order", 0)),
            ),
        )
        document.pop("navigation", None)
        document.pop("trash", None)
        self.workspace_path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix=".workspace-", suffix=".yaml", dir=self.workspace_path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                yaml.safe_dump(document, stream, allow_unicode=True, sort_keys=False)
            os.replace(temporary, self.workspace_path)
        except Exception:
            try:
                Path(temporary).unlink(missing_ok=True)
            finally:
                raise

    def _dashboard_locations(self) -> dict[Path, DashboardLocation]:
        result: dict[Path, DashboardLocation] = {}
        if not self.dashboards_root.is_dir():
            return result
        for definition in self.dashboards_root.rglob("dashboard.yaml"):
            relative = definition.relative_to(self.dashboards_root)
            if any(part.startswith(".") for part in relative.parts):
                continue
            dashboard_root = definition.parent.resolve()
            try:
                result[dashboard_root] = decode_dashboard_path(
                    self.dashboards_root.resolve(), dashboard_root
                )
            except WorkspaceError:
                # An unrelated hand-created invalid directory must not disable
                # navigation management for the rest of the workspace.
                continue
        return result

    def _known_active_folders(
        self, records: list[dict[str, Any]], locations: dict[Path, DashboardLocation]
    ) -> set[tuple[str, ...]]:
        folders: set[tuple[str, ...]] = set()
        for record in records:
            raw = str(record["path"])
            if raw.startswith(f"{TRASH_SEGMENT}/"):
                continue
            segments = normalize_logical_path(raw)
            folders.update(segments[:index] for index in range(1, len(segments) + 1))
        for location in locations.values():
            if location.trashed:
                continue
            folders.update(
                location.folder_segments[:index]
                for index in range(1, len(location.folder_segments) + 1)
            )
        return folders

    def _ensure_folder_available(
        self,
        candidate: tuple[str, ...],
        folders: Iterable[tuple[str, ...]],
        *,
        ignore_prefix: tuple[str, ...] | None = None,
    ) -> None:
        key = _path_key(candidate)
        for existing in folders:
            if ignore_prefix and _is_prefix(ignore_prefix, existing):
                continue
            if _path_key(existing) == key:
                raise WorkspaceError(f"Folder already exists: {'/'.join(candidate)}")

    def _rename_dashboards(self, mappings: dict[Path, Path]) -> None:
        mappings = {
            source.resolve(): target.resolve()
            for source, target in mappings.items()
            if source.resolve() != target.resolve()
        }
        if not mappings:
            return
        sources = set(mappings)
        for source in sources:
            for other in sources:
                if source != other and source in other.parents:
                    raise WorkspaceError(
                        "Nested physical dashboard directories must be flattened before moving them",
                        file=source,
                    )
        target_keys: dict[str, Path] = {}
        existing_keys = {
            child.name.casefold(): child.resolve()
            for child in self.dashboards_root.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        }
        for source, target in mappings.items():
            if target.parent != self.dashboards_root.resolve():
                raise WorkspaceError("Dashboard target must be directly under dashboards/", file=target)
            key = target.name.casefold()
            if key in target_keys and target_keys[key] != target:
                raise WorkspaceError(f"Dashboard directory collision: {target.name}")
            target_keys[key] = target
            occupied = existing_keys.get(key)
            if occupied is not None and occupied not in sources:
                raise WorkspaceError(f"Dashboard directory already exists: {target.name}", file=occupied)

        staged: list[tuple[Path, Path, Path]] = []
        self.dashboards_root.mkdir(parents=True, exist_ok=True)
        try:
            for source, target in mappings.items():
                temporary = self.dashboards_root / f".dataviz-move-{uuid.uuid4().hex}"
                source.rename(temporary)
                staged.append((source, temporary, target))
            completed: list[tuple[Path, Path, Path]] = []
            for source, temporary, target in staged:
                temporary.rename(target)
                completed.append((source, temporary, target))
        except Exception as error:
            for source, temporary, target in reversed(staged):
                try:
                    if target.exists() and not source.exists():
                        target.rename(source)
                    elif temporary.exists() and not source.exists():
                        temporary.rename(source)
                except OSError:
                    pass
            if isinstance(error, WorkspaceError):
                raise
            raise WorkspaceError(f"Could not rename dashboard directory: {error}") from error

    def _folder_target(
        self,
        old: tuple[str, ...],
        parent_id: str | None,
        *,
        new_title: str | None = None,
    ) -> tuple[str, ...]:
        parent = folder_segments(parent_id) if parent_id else ()
        title = validate_segment(new_title) if new_title is not None else old[-1]
        target = (*parent, title)
        if _is_prefix(old, parent):
            raise WorkspaceError("A folder cannot be moved inside itself")
        return target

    def _rewrite_folder_prefix(
        self,
        records: list[dict[str, Any]],
        old: tuple[str, ...],
        new: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        rewritten: list[dict[str, Any]] = []
        for record in records:
            raw = str(record["path"])
            trashed = raw.startswith(f"{TRASH_SEGMENT}/")
            logical = raw[len(TRASH_SEGMENT) :].strip("/") if trashed else raw
            segments = normalize_logical_path(logical)
            if not trashed and _is_prefix(old, segments):
                segments = (*new, *segments[len(old) :])
            rewritten.append(
                {"path": self._record_path(segments, trashed=trashed), "order": record["order"]}
            )
        return rewritten

    def _move_folder(
        self, old: tuple[str, ...], target: tuple[str, ...]
    ) -> dict[str, str]:
        document = self._read()
        records = self._folder_records(document)
        locations = self._dashboard_locations()
        known = self._known_active_folders(records, locations)
        if old not in known:
            raise WorkspaceError(f"Unknown folder: {'/'.join(old)}")
        self._ensure_folder_available(target, known, ignore_prefix=old)
        mappings: dict[Path, Path] = {}
        for source, location in locations.items():
            if location.trashed or not _is_prefix(old, location.folder_segments):
                continue
            segments = (*target, *location.segments[len(old) :])
            mappings[source] = self.dashboards_root / encode_dashboard_name(segments)
        rewritten = self._rewrite_folder_prefix(records, old, target)
        self._rename_dashboards(mappings)
        self._write(document, rewritten)
        return {"folder_id": folder_id(target), "path": "/".join(target)}

    def create_folder(self, title: str, parent_id: str | None = None) -> str:
        with _LOCK:
            document = self._read()
            records = self._folder_records(document)
            locations = self._dashboard_locations()
            parent = folder_segments(parent_id) if parent_id else ()
            if parent and parent not in self._known_active_folders(records, locations):
                raise WorkspaceError(f"Unknown parent folder: {'/'.join(parent)}")
            target = (*parent, validate_segment(title))
            self._ensure_folder_available(target, self._known_active_folders(records, locations))
            sibling_orders = []
            for record in records:
                raw = str(record["path"])
                if raw.startswith(f"{TRASH_SEGMENT}/"):
                    continue
                segments = normalize_logical_path(raw)
                if segments[:-1] == parent:
                    sibling_orders.append(int(record.get("order", 0)))
            records.append({"path": "/".join(target), "order": max(sibling_orders, default=0) + 10})
            self._write(document, records)
            return folder_id(target)

    def rename_folder(self, identifier: str, title: str) -> dict[str, str]:
        with _LOCK:
            old = folder_segments(identifier)
            return self._move_folder(old, (*old[:-1], validate_segment(title)))

    def place_folder(self, identifier: str, parent_id: str | None) -> dict[str, str]:
        with _LOCK:
            old = folder_segments(identifier)
            return self._move_folder(old, self._folder_target(old, parent_id))

    def place_dashboard(
        self, entry: DashboardCatalogEntry, parent_id: str | None
    ) -> dict[str, str]:
        with _LOCK:
            if not entry.path.exists():
                raise WorkspaceError("Dashboard directory no longer exists", file=entry.path)
            location = decode_dashboard_path(self.dashboards_root.resolve(), entry.path.resolve())
            if location.trashed:
                raise WorkspaceError("A trashed dashboard must be restored before moving it")
            parent = folder_segments(parent_id) if parent_id else ()
            document = self._read()
            records = self._folder_records(document)
            locations = self._dashboard_locations()
            if parent and parent not in self._known_active_folders(records, locations):
                raise WorkspaceError(f"Unknown parent folder: {'/'.join(parent)}")
            target_segments = (*parent, location.leaf)
            target = self.dashboards_root / encode_dashboard_name(target_segments)
            self._rename_dashboards({entry.path: target})
            return {"path": target.relative_to(self.root).as_posix()}

    def trash_dashboard(self, entry: DashboardCatalogEntry) -> str:
        with _LOCK:
            location = decode_dashboard_path(self.dashboards_root.resolve(), entry.path.resolve())
            if location.trashed:
                raise WorkspaceError("Dashboard is already in the trash")
            target = self.dashboards_root / encode_dashboard_name(location.segments, trashed=True)
            self._rename_dashboards({entry.path: target})
            return dashboard_trash_id(target.name)

    def trash_folder(self, identifier: str) -> str:
        with _LOCK:
            old = folder_segments(identifier)
            document = self._read()
            records = self._folder_records(document)
            locations = self._dashboard_locations()
            if old not in self._known_active_folders(records, locations):
                raise WorkspaceError(f"Unknown folder: {'/'.join(old)}")
            mappings: dict[Path, Path] = {}
            for source, location in locations.items():
                if not location.trashed and _is_prefix(old, location.folder_segments):
                    mappings[source] = self.dashboards_root / encode_dashboard_name(
                        location.segments, trashed=True
                    )
            rewritten: list[dict[str, Any]] = []
            represented = False
            for record in records:
                raw = str(record["path"])
                trashed = raw.startswith(f"{TRASH_SEGMENT}/")
                logical = raw[len(TRASH_SEGMENT) :].strip("/") if trashed else raw
                segments = normalize_logical_path(logical)
                if not trashed and _is_prefix(old, segments):
                    trashed = True
                    represented = represented or segments == old
                rewritten.append(
                    {"path": self._record_path(segments, trashed=trashed), "order": record["order"]}
                )
            if not represented:
                rewritten.append({"path": self._record_path(old, trashed=True), "order": 0})
            self._rename_dashboards(mappings)
            self._write(document, rewritten)
            return folder_trash_id(old)

    def restore(self, trash_identifier: str) -> dict[str, str]:
        with _LOCK:
            if trash_identifier.startswith(DASHBOARD_TRASH_PREFIX):
                encoded = dashboard_trash_name(trash_identifier)
                location = decode_dashboard_name(encoded)
                if not location.trashed:
                    raise WorkspaceError("Invalid dashboard trash id")
                source = self.dashboards_root / encoded
                if not source.exists():
                    raise WorkspaceError("Trashed dashboard directory no longer exists", file=source)
                target = self.dashboards_root / encode_dashboard_name(location.segments)
                self._rename_dashboards({source: target})
                return {"path": target.relative_to(self.root).as_posix()}

            if trash_identifier.startswith(FOLDER_TRASH_PREFIX):
                old = folder_trash_segments(trash_identifier)
                document = self._read()
                records = self._folder_records(document)
                locations = self._dashboard_locations()
                active_folders = self._known_active_folders(records, locations)
                self._ensure_folder_available(old, active_folders)
                mappings: dict[Path, Path] = {}
                for source, location in locations.items():
                    if location.trashed and _is_prefix(old, location.folder_segments):
                        mappings[source] = self.dashboards_root / encode_dashboard_name(location.segments)
                rewritten: list[dict[str, Any]] = []
                found = False
                for record in records:
                    raw = str(record["path"])
                    trashed = raw.startswith(f"{TRASH_SEGMENT}/")
                    logical = raw[len(TRASH_SEGMENT) :].strip("/") if trashed else raw
                    segments = normalize_logical_path(logical)
                    if trashed and _is_prefix(old, segments):
                        trashed = False
                        found = True
                    rewritten.append(
                        {"path": self._record_path(segments, trashed=trashed), "order": record["order"]}
                    )
                if not found and not mappings:
                    raise WorkspaceError("Unknown folder trash item")
                self._rename_dashboards(mappings)
                self._write(document, rewritten)
                return {"folder_id": folder_id(old), "path": "/".join(old)}

            raise WorkspaceError(f"Unknown trash id: {trash_identifier}")
