from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from dataviz.errors import Diagnostic, WorkspaceError
from dataviz.workspace.models import (
    DashboardDefinition,
    LayoutItem,
    NavigationItem,
    PresentationDefinition,
    SourceDefinition,
    TrashItemDefinition,
    WidgetOutputDefinition,
    WidgetDefinition,
    WorkspaceDefinition,
)
from dataviz.workspace.naming import (
    TRASH_SEGMENT,
    DashboardLocation,
    dashboard_trash_id,
    decode_dashboard_name,
    decode_dashboard_path,
    folder_id,
    folder_trash_id,
    normalize_logical_path,
)
from dataviz.workspace.selections import compile_selection_contract, view_definition
from dataviz.templates import VIEW_TEMPLATES


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise WorkspaceError("Required YAML file does not exist", file=path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorkspaceError(f"Invalid YAML: {exc}", file=path) from exc
    if not isinstance(data, dict):
        raise WorkspaceError("YAML document must be an object", file=path)
    return data


def parse_model(model_type, path: Path):
    try:
        return model_type.model_validate(read_yaml(path))
    except ValidationError as exc:
        raise WorkspaceError("Schema validation failed", file=path, details=exc.errors()) from exc


@dataclass(slots=True)
class LoadedDashboard:
    root: Path
    definition_path: Path
    definition: DashboardDefinition
    logic_definition: DashboardDefinition
    sources: dict[str, tuple[Path, SourceDefinition]]
    widgets: dict[str, tuple[Path, WidgetDefinition]]
    presentation_path: Path | None = None
    presentation: PresentationDefinition | None = None
    presentation_diagnostics: list[Diagnostic] | None = None
    readme: str = ""

    def resolve(self, relative: str | None) -> Path | None:
        return (self.root / relative).resolve() if relative else None

    @property
    def canvas_name(self) -> str:
        """Filesystem-owned display name used by navigation and sharing."""
        try:
            return decode_dashboard_name(self.root.name).leaf
        except WorkspaceError:
            return self.root.name

    @property
    def title(self) -> str:
        """Page title, falling back to the filesystem Canvas Name."""
        return self.definition.title.strip() or self.canvas_name


@dataclass(slots=True)
class DashboardCatalogEntry:
    """One runtime navigation entry, including unavailable workspace references."""

    id: str
    canvas_name: str
    title: str
    path: Path
    relative_path: str
    status: str
    dashboard: LoadedDashboard | None = None
    navigation: NavigationItem | None = None
    discovered: bool = False
    message: str | None = None
    parent_id: str | None = None
    logical_path: str = ""

    @property
    def runnable(self) -> bool:
        return self.dashboard is not None


@dataclass(slots=True)
class LoadedWorkspace:
    root: Path
    definition_path: Path
    definition: WorkspaceDefinition
    dashboards: dict[str, LoadedDashboard]
    catalog: list[DashboardCatalogEntry]
    load_diagnostics: list[Diagnostic]
    readme: str = ""

    @property
    def state_dir(self) -> Path:
        return self.root / ".dataviz"

    def dashboard(self, identifier: str) -> LoadedDashboard:
        if identifier in self.dashboards:
            return self.dashboards[identifier]
        normalized = identifier.rstrip("/")
        for dashboard in self.dashboards.values():
            if str(dashboard.root.relative_to(self.root)) == normalized:
                return dashboard
        raise WorkspaceError(f"Unknown dashboard: {identifier}")

    def catalog_entry(self, identifier: str) -> DashboardCatalogEntry:
        for entry in self.catalog:
            if entry.id == identifier:
                return entry
        raise WorkspaceError(f"Unknown dashboard: {identifier}")


def load_dashboard(path: Path) -> LoadedDashboard:
    root = path.resolve()
    definition_path = root / "dashboard.yaml"
    logic_definition = parse_model(DashboardDefinition, definition_path)
    definition = logic_definition.model_copy(deep=True)
    presentation_path = root / "presentation.yaml"
    presentation: PresentationDefinition | None = None
    presentation_diagnostics: list[Diagnostic] = []
    if presentation_path.exists():
        try:
            candidate = parse_model(PresentationDefinition, presentation_path)
        except WorkspaceError as error:
            presentation_diagnostics.append(
                Diagnostic(
                    "warning",
                    f"Presentation ignored: {error.message}",
                    str(presentation_path),
                    code="presentation_invalid",
                )
            )
        else:
            if candidate.dashboard != logic_definition.id:
                presentation_diagnostics.append(
                    Diagnostic(
                        "warning",
                        f"Presentation targets {candidate.dashboard}, expected {logic_definition.id}; ignored",
                        str(presentation_path),
                        "dashboard",
                        "presentation_dashboard_mismatch",
                    )
                )
            else:
                presentation = candidate
    sources: dict[str, tuple[Path, SourceDefinition]] = {}
    widgets: dict[str, tuple[Path, WidgetDefinition]] = {}

    for source_entry in definition.sources:
        if isinstance(source_entry, str):
            source_path = (root / source_entry).resolve()
            source = parse_model(SourceDefinition, source_path)
        else:
            source_path = definition_path
            try:
                source = SourceDefinition.model_validate(source_entry)
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline source schema validation failed",
                    file=definition_path,
                    details=exc.errors(),
                ) from exc
        if source.id in sources:
            raise WorkspaceError(f"Duplicate source id: {source.id}", file=source_path)
        sources[source.id] = (source_path, source)

    for relative in definition.widgets:
        widget_path = (root / relative).resolve()
        widget = parse_model(WidgetDefinition, widget_path)
        if widget.id in widgets:
            raise WorkspaceError(f"Duplicate widget id: {widget.id}", file=widget_path)
        widgets[widget.id] = (widget_path, widget)

    output_types = {
        "table": "table",
        "perspective": "perspective",
        "markdown": "text",
        "image": "image",
    }
    for view in definition.views:
        if view.id in widgets:
            raise WorkspaceError(f"Duplicate view id: {view.id}", file=definition_path)
        widgets[view.id] = (
            definition_path,
            WidgetDefinition(
                id=view.id,
                title=view.title or view.id,
                description=view.description,
                depends_on=view.source_ids,
                output=WidgetOutputDefinition(type=output_types.get(view.template, "auto")),
            ),
        )

    if presentation is not None:
        definition = _apply_presentation(
            logic_definition,
            presentation,
            presentation_path,
            presentation_diagnostics,
            view_ids=set(widgets),
        )

    readme_path = root / "README.md"
    return LoadedDashboard(
        root=root,
        definition_path=definition_path,
        definition=definition,
        logic_definition=logic_definition,
        sources=sources,
        widgets=widgets,
        presentation_path=presentation_path if presentation_path.exists() else None,
        presentation=presentation,
        presentation_diagnostics=presentation_diagnostics,
        readme=readme_path.read_text(encoding="utf-8") if readme_path.exists() else "",
    )


def _present_fields(model) -> dict[str, Any]:
    return {
        key: value
        for key, value in model.model_dump(mode="python", exclude_none=True).items()
        if key in model.model_fields_set
    }


def _append_css_class(current: str, *values: str | None) -> str:
    return " ".join(dict.fromkeys(part for value in (current, *values) for part in value.split() if part))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _apply_presentation(
    logic: DashboardDefinition,
    presentation: PresentationDefinition,
    presentation_path: Path,
    diagnostics: list[Diagnostic],
    *,
    view_ids: set[str],
) -> DashboardDefinition:
    """Create an effective definition without allowing presentation to alter data semantics."""
    effective = logic.model_copy(deep=True)

    theme_update = _present_fields(presentation.theme)
    if theme_update:
        effective.theme = effective.theme.model_copy(update=theme_update)

    layout_update = _present_fields(presentation.layout)
    if layout_update:
        effective.layout = effective.layout.model_copy(update=layout_update)

    selection_keys = {
        item.key
        for selections in compile_selection_contract(logic).values()
        for item in selections
    }
    for selector_key in presentation.selectors:
        if selector_key not in selection_keys:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    f"Presentation references unknown selector: {selector_key}",
                    str(presentation_path),
                    f"selectors.{selector_key}",
                    "presentation_unknown_selector",
                )
            )

    sections = {section.id: section for section in effective.sections}
    for section_id, override in presentation.sections.items():
        section = sections.get(section_id)
        if section is None:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    f"Presentation references unknown section: {section_id}",
                    str(presentation_path),
                    f"sections.{section_id}",
                    "presentation_unknown_section",
                )
            )
            continue
        update = _present_fields(override)
        if "css_class" in update:
            update["css_class"] = _append_css_class(section.css_class, update["css_class"])
        replacement = section.model_copy(update=update)
        effective.sections[effective.sections.index(section)] = replacement
        sections[section_id] = replacement

    declarative_views = {view.id: view for view in effective.views}
    layout_items = {item.widget: item for item in effective.layout.items}
    for view_id, override in presentation.views.items():
        view = declarative_views.get(view_id)
        if view_id not in view_ids:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    f"Presentation references unknown view: {view_id}",
                    str(presentation_path),
                    f"views.{view_id}",
                    "presentation_unknown_view",
                )
            )
            continue

        view_update: dict[str, Any] = {}
        if view is not None and override.engine is not None:
            view_update["engine"] = override.engine
        if view is not None and override.options:
            view_update["options"] = _deep_merge(view.options, override.options)
        if view is not None and override.config:
            view_update["config"] = _deep_merge(view.config, override.config)
        if view is not None and view_update:
            replacement = view.model_copy(update=view_update)
            effective.views[effective.views.index(view)] = replacement
            declarative_views[view_id] = replacement

        layout_item = layout_items.get(view_id)
        presentation_class = _append_css_class(
            "",
            f"dv-view--{override.container}" if override.container else None,
            override.css_class,
        )
        if override.width is not None or override.height is not None or presentation_class:
            if layout_item is None:
                layout_item = LayoutItem(widget=view_id)
                effective.layout.items.append(layout_item)
            update = {}
            if override.width is not None:
                update["width"] = override.width
            if override.height is not None:
                update["min_height"] = override.height
            if presentation_class:
                update["css_class"] = _append_css_class(layout_item.css_class, presentation_class)
            replacement = layout_item.model_copy(update=update)
            effective.layout.items[effective.layout.items.index(layout_item)] = replacement
            layout_items[view_id] = replacement

    canvas_update = _present_fields(presentation.canvas)
    template = canvas_update.get("template")
    if template and not (presentation_path.parent / template).exists():
        diagnostics.append(
            Diagnostic(
                "warning",
                f"Presentation canvas template does not exist and will be ignored: {template}",
                str(presentation_path.parent / template),
                "canvas.template",
                "presentation_asset_missing",
            )
        )
        canvas_update.pop("template")
    libraries = canvas_update.pop("client_libraries", [])
    if libraries:
        canvas_update["client_libraries"] = list(
            dict.fromkeys([*effective.canvas.client_libraries, *libraries])
        )
    if presentation.assets.css:
        canvas_update["styles"] = list(
            dict.fromkeys([*effective.canvas.styles, *presentation.assets.css])
        )
    if presentation.assets.js:
        canvas_update["scripts"] = list(
            dict.fromkeys([*effective.canvas.scripts, *presentation.assets.js])
        )
    if canvas_update:
        effective.canvas = effective.canvas.model_copy(update=canvas_update)
    return effective


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _diagnostic_from_error(error: WorkspaceError, *, code: str) -> Diagnostic:
    return Diagnostic("error", error.message, error.file, code=code)


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


def walk_navigation(
    items: list[NavigationItem], parent_id: str | None = None
) -> list[tuple[NavigationItem, str | None]]:
    result: list[tuple[NavigationItem, str | None]] = []
    for item in sorted(items, key=lambda value: value.order):
        if item.kind == "folder":
            result.extend(walk_navigation(item.children, item.id))
        else:
            result.append((item, parent_id))
    return result


def dashboard_paths(items: list[NavigationItem]) -> list[str]:
    paths: list[str] = []
    for item in items:
        if item.kind == "folder":
            paths.extend(dashboard_paths(item.children))
        elif item.dashboard:
            paths.append(item.dashboard)
    return paths


def _legacy_folder_paths(
    items: list[NavigationItem], parent: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], int]]:
    paths: list[tuple[tuple[str, ...], int]] = []
    for item in items:
        if item.kind != "folder":
            continue
        current = (*parent, item.title)
        paths.append((current, item.order))
        paths.extend(_legacy_folder_paths(item.children, current))
    return paths


def _folder_navigation(
    folder_orders: dict[tuple[str, ...], int]
) -> list[NavigationItem]:
    all_paths = set(folder_orders)
    for path in list(all_paths):
        all_paths.update(path[:index] for index in range(1, len(path)))
    children: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
    for path in all_paths:
        children.setdefault(path[:-1], []).append(path)

    def build(parent: tuple[str, ...]) -> list[NavigationItem]:
        values = sorted(
            children.get(parent, []),
            key=lambda value: (folder_orders.get(value, 0), tuple(part.casefold() for part in value)),
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
        logical = raw[len(TRASH_SEGMENT):].strip("/") if is_trashed else raw
        try:
            segments = normalize_logical_path(logical)
        except WorkspaceError as error:
            diagnostics.append(
                Diagnostic("warning", error.message, str(definition_path), "folders", "folder_name_invalid")
            )
            continue
        (trashed if is_trashed else active)[segments] = folder.order
    if not definition.folders:
        for segments, order in _legacy_folder_paths(definition.navigation):
            try:
                normalized = tuple(normalize_logical_path("/".join(segments)))
            except WorkspaceError:
                continue
            active[normalized] = order
    return active, trashed


def load_workspace(path: Path | str) -> LoadedWorkspace:
    """Load dashboards from encoded directory names.

    Dashboard placement and trash state come exclusively from the filesystem.
    ``workspace.yaml`` contributes empty logical folders, ordering and runtime
    settings. Legacy navigation folders are accepted as folder metadata, but
    legacy dashboard references no longer override what exists on disk.
    """
    root = Path(path).expanduser().resolve()
    definition_path = root / "workspace.yaml"
    load_diagnostics: list[Diagnostic] = []
    try:
        definition = parse_model(WorkspaceDefinition, definition_path)
    except WorkspaceError as error:
        load_diagnostics.append(_diagnostic_from_error(error, code="workspace_definition_invalid"))
        definition = WorkspaceDefinition(id=root.name, title=root.name)

    dashboards_root = root / "dashboards"
    discovered_paths: set[Path] = set()
    if dashboards_root.is_dir():
        for definition_file in dashboards_root.rglob("dashboard.yaml"):
            relative_parts = definition_file.relative_to(root).parts
            if not any(part.startswith(".") for part in relative_parts):
                discovered_paths.add(definition_file.parent.resolve())

    loaded_by_path: dict[Path, LoadedDashboard] = {}
    errors_by_path: dict[Path, WorkspaceError] = {}
    locations_by_path: dict[Path, DashboardLocation] = {}
    for dashboard_path in sorted(discovered_paths, key=lambda value: _relative_path(root, value)):
        try:
            locations_by_path[dashboard_path] = decode_dashboard_path(dashboards_root, dashboard_path)
        except WorkspaceError as error:
            locations_by_path[dashboard_path] = DashboardLocation((dashboard_path.name,), False)
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
        if dashboard is None:
            error = errors_by_path[selected]
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
                    parent_id=folder_id(location.folder_segments) if location.folder_segments else None,
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

    definition.navigation = _folder_navigation(active_folders)

    # Trash is derived from encoded directory names and trashed empty-folder metadata.
    synthetic_trash = []
    covered_trashed_paths: set[Path] = set()
    trash_roots = [
        segments
        for segments in trashed_folders
        if not any(
            other != segments and _is_logical_prefix(other, segments)
            for other in trashed_folders
        )
    ]
    for segments in sorted(trash_roots):
        folder_paths = {
            path
            for path in trashed_folders
            if _is_logical_prefix(segments, path)
        }
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

        def trash_folder_item(path: tuple[str, ...]) -> NavigationItem:
            child_folders = sorted(
                candidate
                for candidate in folder_paths
                if len(candidate) == len(path) + 1 and candidate[:-1] == path
            )
            dashboard_items = []
            for dashboard_path in grouped_dashboards:
                location = locations_by_path[dashboard_path]
                if location.folder_segments != path:
                    continue
                dashboard = loaded_by_path.get(dashboard_path)
                dashboard_items.append(
                    NavigationItem(
                        kind="dashboard",
                        id=dashboard.definition.id if dashboard else location.leaf,
                        title=location.leaf,
                        dashboard=_relative_path(root, dashboard_path),
                    )
                )
            return NavigationItem(
                kind="folder",
                id=folder_id(path),
                title=path[-1],
                order=trashed_folders.get(path, 0),
                children=[trash_folder_item(child) for child in child_folders] + dashboard_items,
            )

        item = trash_folder_item(segments)
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
        title = location.leaf
        item = NavigationItem(
            kind="dashboard",
            id=dashboard.definition.id if dashboard else location.leaf,
            title=title,
            dashboard=_relative_path(root, selected),
        )
        synthetic_trash.append(
            {
                "trash_id": dashboard_trash_id(selected.name),
                "original_parent_id": folder_id(location.folder_segments) if location.folder_segments else None,
                "trashed_at": _modified_at(selected),
                "item": item.model_dump(mode="json"),
            }
        )
    definition.trash = [TrashItemDefinition.model_validate(item) for item in synthetic_trash]

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
                Diagnostic("warning", entry.message, str(entry.dashboard.definition_path), code="dashboard_id_conflict")
            )

    readme_path = root / "README.md"
    return LoadedWorkspace(
        root=root,
        definition_path=definition_path,
        definition=definition,
        dashboards=dashboards,
        catalog=catalog,
        load_diagnostics=load_diagnostics,
        readme=readme_path.read_text(encoding="utf-8") if readme_path.exists() else "",
    )


def _is_logical_prefix(prefix: tuple[str, ...], value: tuple[str, ...]) -> bool:
    return len(value) >= len(prefix) and value[: len(prefix)] == prefix


def _modified_at(path: Path) -> str:
    timestamp = path.stat().st_mtime if path.exists() else datetime.now(timezone.utc).timestamp()
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def validate_workspace(workspace: LoadedWorkspace) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = list(workspace.load_diagnostics)
    if not workspace.dashboards:
        diagnostics.append(Diagnostic("warning", "Workspace has no dashboards", str(workspace.definition_path)))

    for dashboard in workspace.dashboards.values():
        diagnostics.extend(dashboard.presentation_diagnostics or [])
        parameter_ids = {item.id for item in dashboard.definition.query_parameters}
        node_ids = set(dashboard.sources) | set(dashboard.widgets)
        for source_path, source in dashboard.sources.values():
            if source.type == "file" and not source.path:
                diagnostics.append(Diagnostic("error", "File source requires path", str(source_path), "path"))
            if source.type in {"sql", "python"} and not source.code:
                diagnostics.append(Diagnostic("error", f"{source.type} source requires code", str(source_path), "code"))
            if source.type == "sql" and not (source.adapter or source.connection):
                diagnostics.append(Diagnostic("error", "SQL source requires adapter", str(source_path), "adapter"))
            for dependency in source.depends_on:
                if dependency not in dashboard.sources:
                    diagnostics.append(Diagnostic("error", f"Unknown source dependency: {dependency}", str(source_path), "depends_on"))
            for parameter in source.params:
                if parameter not in parameter_ids:
                    diagnostics.append(Diagnostic("error", f"Unknown parameter: {parameter}", str(source_path), "params"))

        for widget_path, widget in dashboard.widgets.values():
            code_path = widget_path.parent / widget.code if widget.code else None
            if code_path and not code_path.exists():
                diagnostics.append(Diagnostic("error", "View code does not exist", str(code_path), "code"))
            for dependency in widget.depends_on:
                if dependency not in dashboard.sources:
                    diagnostics.append(Diagnostic("error", f"Unknown view source: {dependency}", str(widget_path), "depends_on"))
            for parameter in widget.params:
                if parameter not in parameter_ids:
                    diagnostics.append(Diagnostic("error", f"Unknown parameter: {parameter}", str(widget_path), "params"))

        layout_widgets = {item.widget for item in dashboard.definition.layout.items}
        for widget_id in layout_widgets - set(dashboard.widgets):
            diagnostics.append(Diagnostic("error", f"Layout references unknown widget: {widget_id}", str(dashboard.definition_path), "layout.items"))

        for view in dashboard.definition.views:
            template = VIEW_TEMPLATES[view.template]
            missing = []
            for field in template["fields"]:
                value = view.source_ids if field == "source" else getattr(view, field, None)
                if value is None or value == "" or value == []:
                    missing.append(field)
            if missing:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"View {view.id} template {view.template} requires: {', '.join(missing)}",
                        str(dashboard.definition_path),
                        "views",
                    )
                )

        section_ids: set[str] = set()
        section_widgets: set[str] = set()
        for section in dashboard.definition.sections:
            if section.id in section_ids:
                diagnostics.append(Diagnostic("error", f"Duplicate section id: {section.id}", str(dashboard.definition_path), "sections"))
            section_ids.add(section.id)
            repeat_templates = {"small-multiples", "selection-gallery"}
            if section.template in repeat_templates and not section.repeat:
                diagnostics.append(Diagnostic("error", f"Section {section.id} template {section.template} requires repeat", str(dashboard.definition_path), "sections.repeat"))
            if section.repeat and section.template not in repeat_templates:
                diagnostics.append(Diagnostic("error", f"Section {section.id} repeat requires a repeat Section template", str(dashboard.definition_path), "sections.template"))
            repeated_view_ids = [view_definition(value).widget for value in section.views]
            if section.repeat:
                repeat_view = section.repeat.view or (repeated_view_ids[0] if repeated_view_ids else None)
                if not repeat_view:
                    diagnostics.append(Diagnostic("error", f"Section {section.id} repeat requires a View blueprint", str(dashboard.definition_path), "sections.repeat.view"))
                elif repeat_view not in repeated_view_ids:
                    diagnostics.append(Diagnostic("error", f"Section {section.id} repeat View must also appear in sections.views: {repeat_view}", str(dashboard.definition_path), "sections.repeat.view"))
                if len(repeated_view_ids) != 1:
                    diagnostics.append(Diagnostic("error", f"Section {section.id} repeat currently supports exactly one View blueprint", str(dashboard.definition_path), "sections.views"))
                if section.repeat.source and section.repeat.source not in dashboard.sources:
                    diagnostics.append(Diagnostic("error", f"Section {section.id} repeat references unknown source: {section.repeat.source}", str(dashboard.definition_path), "sections.repeat.source"))
                if section.template == "selection-gallery":
                    selection_ids = {item.id for item in section.selections}
                    if not section.selections:
                        diagnostics.append(Diagnostic("error", f"Section {section.id} selection-gallery requires a Section Selection", str(dashboard.definition_path), "sections.selections"))
                    elif section.repeat.selection and section.repeat.selection not in selection_ids:
                        diagnostics.append(Diagnostic("error", f"Section {section.id} repeat references unknown Section Selection: {section.repeat.selection}", str(dashboard.definition_path), "sections.repeat.selection"))
            for raw_view in section.views:
                view = view_definition(raw_view)
                if view.widget not in dashboard.widgets:
                    diagnostics.append(Diagnostic("error", f"Section references unknown widget: {view.widget}", str(dashboard.definition_path), "sections.views"))
                if view.widget in section_widgets:
                    diagnostics.append(Diagnostic("error", f"Widget belongs to more than one section: {view.widget}", str(dashboard.definition_path), "sections.views"))
                section_widgets.add(view.widget)

        contract = compile_selection_contract(dashboard.definition)
        for widget_id, selections in contract.items():
            ids = [item.id for item in selections]
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            if duplicates:
                diagnostics.append(Diagnostic("error", f"Selection ids shadow each other for view {widget_id}: {', '.join(duplicates)}", str(dashboard.definition_path), "sections"))
            raw_view = next(
                (
                    view_definition(value)
                    for section in dashboard.definition.sections
                    for value in section.views
                    if view_definition(value).widget == widget_id
                ),
                None,
            )
            if raw_view:
                unknown_bindings = set(raw_view.selection_bindings) - set(ids)
                for selection_id in sorted(unknown_bindings):
                    diagnostics.append(Diagnostic("error", f"View {widget_id} binds unknown selection: {selection_id}", str(dashboard.definition_path), "selection_bindings"))

        canvas = dashboard.definition.canvas
        declarative = bool(dashboard.definition.views)
        exposed_sources = set(canvas.client_sources)
        exposed_sources.update(
            source_id
            for view in dashboard.definition.views
            for source_id in view.source_ids
        )
        exposed_sources.update(
            section.repeat.source
            for section in dashboard.definition.sections
            if section.repeat and section.repeat.source
        )
        has_view_selections = bool(dashboard.definition.dashboard_selections) or any(
            section.selections
            or any(view_definition(value).selections for value in section.views)
            for section in dashboard.definition.sections
        ) or any(view.selections for view in dashboard.definition.views)
        if (
            has_view_selections
            and not canvas.client_selections
            and not declarative
        ):
            diagnostics.append(Diagnostic("warning", "HTML export selections are snapshot-only because canvas.client_selections is false", str(dashboard.definition_path), "canvas.client_selections"))
        if canvas.client_selections and not canvas.script and not declarative:
            diagnostics.append(Diagnostic("error", "canvas.client_selections requires a canvas script that registers window.datavizClient", str(dashboard.definition_path), "canvas.script"))
        if canvas.client_sources and not canvas.script and not declarative:
            diagnostics.append(Diagnostic("error", "canvas.client_sources requires a browser canvas script", str(dashboard.definition_path), "canvas.script"))
        if canvas.client_selections and not exposed_sources:
            diagnostics.append(Diagnostic("error", "canvas.client_selections requires an explicit canvas.client_sources allowlist", str(dashboard.definition_path), "canvas.client_sources"))
        for source_id in exposed_sources:
            if source_id not in dashboard.sources:
                diagnostics.append(Diagnostic("error", f"Canvas client_sources references unknown source: {source_id}", str(dashboard.definition_path), "canvas.client_sources"))
        for widget_path, widget in dashboard.widgets.values():
            for source_id in widget.depends_on:
                if source_id not in exposed_sources:
                    diagnostics.append(Diagnostic("error", f"View {widget.id} source is not exposed through canvas.client_sources: {source_id}", str(widget_path), "depends_on"))
        for field in ("template", "style", "script"):
            value = getattr(canvas, field)
            if value and not (dashboard.root / value).exists():
                diagnostics.append(Diagnostic("error", f"Canvas {field} does not exist", str(dashboard.root / value), f"canvas.{field}"))
        for field, values in (("styles", canvas.styles), ("scripts", canvas.scripts)):
            for value in values:
                if not (dashboard.root / value).exists():
                    diagnostics.append(
                        Diagnostic(
                            "warning",
                            f"Presentation asset does not exist and will be ignored: {value}",
                            str(dashboard.root / value),
                            f"canvas.{field}",
                            "presentation_asset_missing",
                        )
                    )
    return diagnostics
