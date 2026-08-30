"""Workspace discovery, navigation, trash projection, and load assembly."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


from dataviz.errors import Diagnostic, WorkspaceError
from dataviz.identifiers import fallback_stable_id
from dataviz.workspace.models import (
    NavigationItem,
    TrashItemDefinition,
    WorkspaceDefinition,
)
from dataviz.workspace.naming import (
    TRASH_SEGMENT,
    DashboardLocation,
    dashboard_trash_id,
    decode_dashboard_path,
    encode_dashboard_name,
    folder_id,
    folder_trash_id,
    normalize_logical_path,
)

from dataviz.workspace.loading.loaded_types import (
    DashboardCatalogEntry,
    LoadedDashboard,
    LoadedWorkspace,
)
from dataviz.workspace.loading.parse_load import load_dashboard, parse_model


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _diagnostic_from_error(error: WorkspaceError, *, code: str) -> Diagnostic:
    field = None
    if isinstance(error.details, list) and error.details:
        location = error.details[0].get("loc")
        if location:
            field = ".".join(str(item) for item in location)
    return Diagnostic(
        "error",
        error.message,
        error.file,
        field,
        code,
        error.details,
    )


def _runtime_id(preferred: str, path: Path, root: Path, used: set[str]) -> str:
    if preferred not in used:
        used.add(preferred)
        return preferred
    suffix = _relative_path(root, path).replace("/", "~")
    candidate = f"{preferred}@{suffix}"
    serial = 2
    while candidate in used:
        candidate = f"{preferred}@{suffix}-{serial}"
        serial += 1
    used.add(candidate)
    return candidate


def _folder_navigation(folder_orders: dict[tuple[str, ...], int]) -> list[NavigationItem]:
    all_paths = set(folder_orders)
    for path in list(all_paths):
        all_paths.update(path[:index] for index in range(1, len(path)))
    children: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
    for path in all_paths:
        children.setdefault(path[:-1], []).append(path)

    def build(parent: tuple[str, ...]) -> list[NavigationItem]:
        values = sorted(
            children.get(parent, []),
            key=lambda value: (
                folder_orders.get(value, 0),
                tuple(part.casefold() for part in value),
            ),
        )
        return [
            NavigationItem(
                kind="folder",
                id=folder_id(path),
                title=path[-1],
                order=folder_orders.get(path, 0),
                children=build(path),
            )
            for path in values
        ]

    return build(())


def _configured_folder_paths(
    definition: WorkspaceDefinition,
    definition_path: Path,
    diagnostics: list[Diagnostic],
) -> tuple[dict[tuple[str, ...], int], dict[tuple[str, ...], int]]:
    active: dict[tuple[str, ...], int] = {}
    trashed: dict[tuple[str, ...], int] = {}
    for folder in definition.folders:
        raw = folder.path.replace("\\", "/").strip("/")
        is_trashed = raw == TRASH_SEGMENT or raw.startswith(f"{TRASH_SEGMENT}/")
        logical = raw[len(TRASH_SEGMENT) :].strip("/") if is_trashed else raw
        try:
            segments = normalize_logical_path(logical)
        except WorkspaceError as error:
            diagnostics.append(
                Diagnostic(
                    "warning", error.message, str(definition_path), "folders", "folder_name_invalid"
                )
            )
            continue
        (trashed if is_trashed else active)[segments] = folder.order
    return active, trashed


def load_workspace(path: Path | str) -> LoadedWorkspace:
    """Load dashboards from encoded directory names.

    Dashboard placement and trash state come exclusively from the filesystem.
    ``workspace.yaml`` contributes empty logical folders, ordering and runtime
    settings. Removed workspace fields are diagnosed and never converted.
    """
    root = Path(path).expanduser().resolve()
    definition_path = root / "workspace.yaml"
    load_diagnostics: list[Diagnostic] = []
    try:
        definition = parse_model(WorkspaceDefinition, definition_path)
    except WorkspaceError as error:
        load_diagnostics.append(_diagnostic_from_error(error, code="workspace_definition_invalid"))
        fallback_id = fallback_stable_id(str(root), prefix="workspace")
        definition = WorkspaceDefinition(
            schema="dataviz/workspace/v1", id=fallback_id, title=root.name
        )

    dashboards_root = root / "dashboards"
    discovered_paths: set[Path] = set()
    if dashboards_root.is_dir():
        for definition_file in dashboards_root.rglob("dashboard.yaml"):
            relative_parts = definition_file.relative_to(root).parts
            if not any(part.startswith(".") for part in relative_parts):
                discovered_paths.add(definition_file.parent.resolve())

    loaded_by_path: dict[Path, LoadedDashboard] = {}
    errors_by_path: dict[Path, WorkspaceError] = {}
    directory_errors_by_path: dict[Path, WorkspaceError] = {}
    locations_by_path: dict[Path, DashboardLocation] = {}
    for dashboard_path in sorted(discovered_paths, key=lambda value: _relative_path(root, value)):
        try:
            locations_by_path[dashboard_path] = decode_dashboard_path(
                dashboards_root, dashboard_path
            )
        except WorkspaceError as error:
            locations_by_path[dashboard_path] = DashboardLocation((dashboard_path.name,), False)
            directory_errors_by_path[dashboard_path] = error
            load_diagnostics.append(
                Diagnostic(
                    "warning",
                    error.message,
                    str(dashboard_path),
                    code="dashboard_directory_name_invalid",
                )
            )
        try:
            loaded_by_path[dashboard_path] = load_dashboard(dashboard_path)
        except WorkspaceError as error:
            errors_by_path[dashboard_path] = error

    dashboards: dict[str, LoadedDashboard] = {}
    catalog: list[DashboardCatalogEntry] = []
    used_runtime_ids: set[str] = set()
    active_folders, trashed_folders = _configured_folder_paths(
        definition, definition_path, load_diagnostics
    )

    active_paths = [path for path in discovered_paths if not locations_by_path[path].trashed]
    trashed_paths = [path for path in discovered_paths if locations_by_path[path].trashed]
    for selected in sorted(
        active_paths,
        key=lambda value: tuple(part.casefold() for part in locations_by_path[value].segments),
    ):
        location = locations_by_path[selected]
        for index in range(1, len(location.segments)):
            active_folders.setdefault(location.segments[:index], 0)
        dashboard = loaded_by_path.get(selected)
        directory_error = directory_errors_by_path.get(selected)
        if dashboard is None or directory_error is not None:
            error = directory_error or errors_by_path[selected]
            preferred = location.leaf
            runtime_id = _runtime_id(preferred, selected, root, used_runtime_ids)
            catalog.append(
                DashboardCatalogEntry(
                    id=runtime_id,
                    canvas_name=location.leaf,
                    title=location.leaf,
                    path=selected,
                    relative_path=_relative_path(root, selected),
                    status="invalid",
                    discovered=True,
                    message=error.message,
                    parent_id=folder_id(location.folder_segments)
                    if location.folder_segments
                    else None,
                    logical_path=location.logical_path,
                )
            )
            load_diagnostics.append(_diagnostic_from_error(error, code="dashboard_invalid"))
            continue
        runtime_id = _runtime_id(dashboard.definition.id, selected, root, used_runtime_ids)
        dashboards[runtime_id] = dashboard
        catalog.append(
            DashboardCatalogEntry(
                id=runtime_id,
                canvas_name=location.leaf,
                title=dashboard.title,
                path=selected,
                relative_path=_relative_path(root, selected),
                status="ready",
                dashboard=dashboard,
                discovered=True,
                parent_id=folder_id(location.folder_segments) if location.folder_segments else None,
                logical_path=location.logical_path,
            )
        )

    navigation = _folder_navigation(active_folders)

    # Trash is derived from encoded directory names and trashed empty-folder metadata.
    synthetic_trash = []
    covered_trashed_paths: set[Path] = set()
    trash_roots = [
        segments
        for segments in trashed_folders
        if any(
            _is_logical_prefix(
                segments,
                locations_by_path[dashboard_path].folder_segments,
            )
            for dashboard_path in trashed_paths
        )
        if not any(
            other != segments and _is_logical_prefix(other, segments) for other in trashed_folders
        )
    ]

    def trash_folder_item(
        path: tuple[str, ...],
        folder_paths: set[tuple[str, ...]],
        grouped_dashboard_paths: list[Path],
    ) -> NavigationItem:
        child_folders = sorted(
            candidate
            for candidate in folder_paths
            if len(candidate) == len(path) + 1 and candidate[:-1] == path
            if any(
                _is_logical_prefix(
                    candidate,
                    locations_by_path[dashboard_path].folder_segments,
                )
                for dashboard_path in grouped_dashboard_paths
            )
        )
        dashboard_items = []
        for dashboard_path in grouped_dashboard_paths:
            location = locations_by_path[dashboard_path]
            if location.folder_segments != path:
                continue
            dashboard = loaded_by_path.get(dashboard_path)
            dashboard_items.append(
                NavigationItem(
                    kind="dashboard",
                    id=dashboard.definition.id if dashboard else location.leaf,
                    title=encode_dashboard_name(location.segments),
                )
            )
        return NavigationItem(
            kind="folder",
            id=folder_id(path),
            title=path[-1],
            order=trashed_folders.get(path, 0),
            children=[
                trash_folder_item(child, folder_paths, grouped_dashboard_paths)
                for child in child_folders
            ]
            + dashboard_items,
        )

    for segments in sorted(trash_roots):
        folder_paths = {path for path in trashed_folders if _is_logical_prefix(segments, path)}
        grouped_dashboards = [
            dashboard_path
            for dashboard_path in trashed_paths
            if _is_logical_prefix(segments, locations_by_path[dashboard_path].folder_segments)
        ]
        for dashboard_path in grouped_dashboards:
            location = locations_by_path[dashboard_path]
            folder_paths.update(
                location.folder_segments[:index]
                for index in range(len(segments), len(location.folder_segments) + 1)
            )

        item = trash_folder_item(segments, folder_paths, grouped_dashboards)
        synthetic_trash.append(
            {
                "trash_id": folder_trash_id(segments),
                "original_parent_id": folder_id(segments[:-1]) if len(segments) > 1 else None,
                "trashed_at": _modified_at(definition_path),
                "item": item.model_dump(mode="json"),
            }
        )
        covered_trashed_paths.update(grouped_dashboards)

    for selected in sorted(set(trashed_paths) - covered_trashed_paths):
        location = locations_by_path[selected]
        dashboard = loaded_by_path.get(selected)
        title = encode_dashboard_name(location.segments)
        item = NavigationItem(
            kind="dashboard",
            id=dashboard.definition.id if dashboard else location.leaf,
            title=title,
        )
        synthetic_trash.append(
            {
                "trash_id": dashboard_trash_id(selected.name),
                "original_parent_id": folder_id(location.folder_segments)
                if location.folder_segments
                else None,
                "trashed_at": _modified_at(selected),
                "item": item.model_dump(mode="json"),
            }
        )
    trash = [TrashItemDefinition.model_validate(item) for item in synthetic_trash]

    id_counts: dict[str, int] = {}
    for entry in catalog:
        if entry.dashboard:
            dashboard_id = entry.dashboard.definition.id
            id_counts[dashboard_id] = id_counts.get(dashboard_id, 0) + 1
    for entry in catalog:
        if entry.dashboard and id_counts[entry.dashboard.definition.id] > 1:
            entry.status = "conflict"
            entry.message = f"Duplicate dashboard id: {entry.dashboard.definition.id}"
            load_diagnostics.append(
                Diagnostic(
                    "error",
                    entry.message,
                    str(entry.dashboard.definition_path),
                    code="dashboard_id_conflict",
                )
            )
            entry.dashboard = None
    conflicting_ids = {dashboard_id for dashboard_id, count in id_counts.items() if count > 1}
    dashboards = {
        runtime_id: dashboard
        for runtime_id, dashboard in dashboards.items()
        if dashboard.definition.id not in conflicting_ids
    }

    readme_path = root / "README.md"
    return LoadedWorkspace(
        root=root,
        definition_path=definition_path,
        definition=definition,
        dashboards=dashboards,
        catalog=catalog,
        load_diagnostics=load_diagnostics,
        navigation=navigation,
        trash=trash,
        readme=readme_path.read_text(encoding="utf-8") if readme_path.exists() else "",
    )


def _is_logical_prefix(prefix: tuple[str, ...], value: tuple[str, ...]) -> bool:
    return len(value) >= len(prefix) and value[: len(prefix)] == prefix


def _modified_at(path: Path) -> str:
    timestamp = path.stat().st_mtime if path.exists() else datetime.now(timezone.utc).timestamp()
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
