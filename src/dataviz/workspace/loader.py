from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata
from pathlib import Path
from typing import Any

import yaml
from packaging.requirements import InvalidRequirement, Requirement
from pydantic import ValidationError

from dataviz.errors import Diagnostic, WorkspaceError
from dataviz.execution.references import parse_output_reference
from dataviz.workspace.models import (
    BrowserTransformDefinition,
    DashboardDefinition,
    DeclarativeViewDefinition,
    NavigationItem,
    PresentationDefinition,
    ServerTransformDefinition,
    SourceDefinition,
    TrashItemDefinition,
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
from dataviz.workspace.selections import compile_selection_contract
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
    value = read_yaml(path)
    schema_field = model_type.model_fields.get("schema_")
    if schema_field is not None and "schema" not in value:
        expected_schema = (
            model_type.model_json_schema(by_alias=True)
            .get("properties", {})
            .get("schema", {})
            .get("const")
        )
        raise WorkspaceError(
            "Schema header is required for a standalone definition",
            file=path,
            details={
                "expected": expected_schema,
                "migration": "dataviz migrate <workspace> --apply",
            },
        )
    try:
        return model_type.model_validate(value)
    except ValidationError as exc:
        raise WorkspaceError("Schema validation failed", file=path, details=exc.errors()) from exc


@dataclass(slots=True)
class LoadedDashboard:
    root: Path
    definition_path: Path
    definition: DashboardDefinition
    logic_definition: DashboardDefinition
    sources: dict[str, tuple[Path, SourceDefinition]]
    transforms: dict[str, tuple[Path, ServerTransformDefinition]]
    browser_transforms: dict[str, tuple[Path, BrowserTransformDefinition]]
    views: dict[str, DeclarativeViewDefinition]
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
    navigation: list[NavigationItem]
    trash: list[TrashItemDefinition]
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
    transforms: dict[str, tuple[Path, ServerTransformDefinition]] = {}
    browser_transforms: dict[str, tuple[Path, BrowserTransformDefinition]] = {}

    for source_entry in definition.sources:
        if isinstance(source_entry, str):
            source_path = (root / source_entry).resolve()
            source = parse_model(SourceDefinition, source_path)
        else:
            source_path = definition_path
            try:
                source = SourceDefinition.model_validate(
                    {"schema": "dataviz/source/v1", **source_entry}
                )
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline source schema validation failed",
                    file=definition_path,
                    details=exc.errors(),
                ) from exc
        if source.id in sources:
            raise WorkspaceError(f"Duplicate source id: {source.id}", file=source_path)
        sources[source.id] = (source_path, source)

    for transform_entry in definition.server_transforms:
        if isinstance(transform_entry, str):
            transform_path = (root / transform_entry).resolve()
            transform = parse_model(ServerTransformDefinition, transform_path)
        else:
            transform_path = definition_path
            try:
                transform = ServerTransformDefinition.model_validate(
                    {"schema": "dataviz/server-transform/v1", **transform_entry}
                )
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline server transform schema validation failed",
                    file=definition_path,
                    details=exc.errors(),
                ) from exc
        if transform.id in transforms:
            raise WorkspaceError(f"Duplicate server transform id: {transform.id}", file=transform_path)
        transforms[transform.id] = (transform_path, transform)

    for transform_entry in definition.browser_transforms:
        if isinstance(transform_entry, str):
            transform_path = (root / transform_entry).resolve()
            transform = parse_model(BrowserTransformDefinition, transform_path)
        else:
            transform_path = definition_path
            try:
                transform = BrowserTransformDefinition.model_validate(
                    {"schema": "dataviz/browser-transform/v1", **transform_entry}
                )
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline browser transform schema validation failed",
                    file=definition_path,
                    details=exc.errors(),
                ) from exc
        if transform.id in browser_transforms:
            raise WorkspaceError(f"Duplicate browser transform id: {transform.id}", file=transform_path)
        browser_transforms[transform.id] = (transform_path, transform)

    views: dict[str, DeclarativeViewDefinition] = {}
    for view in definition.views:
        if view.id in views:
            raise WorkspaceError(f"Duplicate view id: {view.id}", file=definition_path)
        views[view.id] = view

    if presentation is not None:
        definition = _apply_presentation(
            logic_definition,
            presentation,
            presentation_path,
            presentation_diagnostics,
            view_ids=set(views),
        )
        views = {view.id: view for view in definition.views}

    readme_path = root / "README.md"
    return LoadedDashboard(
        root=root,
        definition_path=definition_path,
        definition=definition,
        logic_definition=logic_definition,
        sources=sources,
        transforms=transforms,
        browser_transforms=browser_transforms,
        views=views,
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
        definition = WorkspaceDefinition(
            schema="dataviz/workspace/v1", id=root.name, title=root.name
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
            locations_by_path[dashboard_path] = decode_dashboard_path(dashboards_root, dashboard_path)
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

    navigation = _folder_navigation(active_folders)

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
        )
        synthetic_trash.append(
            {
                "trash_id": dashboard_trash_id(selected.name),
                "original_parent_id": folder_id(location.folder_segments) if location.folder_segments else None,
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
        navigation=navigation,
        trash=trash,
        readme=readme_path.read_text(encoding="utf-8") if readme_path.exists() else "",
    )


def _is_logical_prefix(prefix: tuple[str, ...], value: tuple[str, ...]) -> bool:
    return len(value) >= len(prefix) and value[: len(prefix)] == prefix


def _modified_at(path: Path) -> str:
    timestamp = path.stat().st_mtime if path.exists() else datetime.now(timezone.utc).timestamp()
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _code_path(definition_path: Path, value: str) -> Path:
    return (definition_path.parent / value).resolve()


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


def _reference_error(
    reference: str,
    *,
    sources: dict[str, tuple[Path, SourceDefinition]],
    transforms: dict[str, tuple[Path, ServerTransformDefinition]],
    browser_transforms: dict[str, tuple[Path, BrowserTransformDefinition]],
    allow_browser: bool,
) -> str | None:
    try:
        parsed = parse_output_reference(reference)
    except Exception as error:
        return str(error)
    kind, _, node_id = parsed.node_id.partition(":")
    collections = {
        "source": sources,
        "transform": transforms,
        "browser": browser_transforms,
    }
    if kind == "browser" and not allow_browser:
        return "Server nodes cannot depend on browser outputs"
    collection = collections.get(kind)
    if collection is None or node_id not in collection:
        return f"Unknown output node: {parsed.node_id}"
    definition = collection[node_id][1]
    outputs = definition.outputs
    if outputs and parsed.output not in outputs:
        return f"Unknown output {parsed.output!r} on {parsed.node_id}"
    if not outputs and parsed.output != "main":
        return f"{parsed.node_id} only has implicit output 'main'"
    return None


def _reference_kind(reference: str, dashboard: LoadedDashboard) -> str | None:
    parsed = parse_output_reference(reference)
    kind, _, node_id = parsed.node_id.partition(":")
    collection = {
        "source": dashboard.sources,
        "transform": dashboard.transforms,
        "browser": dashboard.browser_transforms,
    }[kind]
    definition = collection[node_id][1]
    if definition.outputs:
        output = definition.outputs.get(parsed.output)
        return output.kind if output else None
    return "table" if kind == "source" else None


def validate_workspace(workspace: LoadedWorkspace) -> list[Diagnostic]:
    """Validate the strict v1 contract and all cross-file references."""
    diagnostics: list[Diagnostic] = list(workspace.load_diagnostics)
    if not workspace.dashboards:
        diagnostics.append(
            Diagnostic("warning", "Workspace has no dashboards", str(workspace.definition_path))
        )

    try:
        from dataviz.auth import AdapterResolver

        adapter_resolver = AdapterResolver(workspace.root)
    except Exception as error:
        adapter_resolver = None
        diagnostics.append(
            Diagnostic(
                "error",
                f"Adapter configuration is invalid: {error}",
                str(workspace.root),
                code="adapter_configuration_invalid",
            )
        )

    for dashboard in workspace.dashboards.values():
        diagnostics.extend(dashboard.presentation_diagnostics or [])
        definition_path = str(dashboard.definition_path)
        parameter_ids = {item.id for item in dashboard.definition.query_parameters}
        view_ids = set(dashboard.views)

        for source_path, source in dashboard.sources.values():
            if source.type == "file" and not source.path:
                diagnostics.append(
                    Diagnostic("error", "File source requires path", str(source_path), "path")
                )
            if source.type in {"sql", "python"} and not source.code:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"{source.type} source requires code",
                        str(source_path),
                        "code",
                    )
                )
            if source.type == "sql" and not source.adapter:
                diagnostics.append(
                    Diagnostic("error", "SQL source requires adapter", str(source_path), "adapter")
                )
            if source.adapter and adapter_resolver:
                try:
                    _, adapter = adapter_resolver.resolve(
                        source.adapter, dashboard.definition.adapters
                    )
                except Exception as error:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            str(error),
                            str(source_path),
                            "adapter",
                            "adapter_not_configured",
                        )
                    )
                else:
                    allowed = (
                        {"file", "files", "local_files"}
                        if source.type == "file"
                        else {"duckdb", "mysql", "starrocks", "sqlalchemy"}
                    )
                    if source.type in {"file", "sql"} and adapter.type not in allowed:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Adapter type {adapter.type!r} cannot be used by a {source.type} Source",
                                str(source_path),
                                "adapter",
                                "adapter_type_mismatch",
                            )
                        )
            if source.type != "python" and (
                source.code_dependencies or source.python_dependencies
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "code_dependencies and python_dependencies are only valid for Python sources",
                        str(source_path),
                        "type",
                    )
                )
            if source.type == "file" and source.timeout_seconds is not None:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "timeout_seconds is only valid for SQL and Python sources",
                        str(source_path),
                        "timeout_seconds",
                    )
                )
            if source.type != "sql" and source.timeout_retries is not None:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "timeout_retries is only valid for SQL sources",
                        str(source_path),
                        "timeout_retries",
                    )
                )
            for parameter in source.params:
                if parameter not in parameter_ids:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown query parameter: {parameter}",
                            str(source_path),
                            "params",
                        )
                    )
            for field in ("path", "code"):
                value = getattr(source, field)
                if not value:
                    continue
                if field == "path" and source.adapter:
                    continue
                path = _code_path(source_path, value)
                if not path.exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Source {field} does not exist",
                            str(path),
                            field,
                        )
                    )
            for dependency in source.code_dependencies:
                dependency_path = _code_path(source_path, dependency)
                if not dependency_path.exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Python Source code dependency does not exist",
                            str(dependency_path),
                            "code_dependencies",
                        )
                    )
            for dependency in source.python_dependencies:
                if message := _python_dependency_error(dependency):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            message,
                            str(source_path),
                            "python_dependencies",
                        )
                    )

        for transform_path, transform in dashboard.transforms.values():
            code_path = _code_path(transform_path, transform.code)
            if not code_path.exists():
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Server Transform code does not exist",
                        str(code_path),
                        "code",
                    )
                )
            for dependency in transform.code_dependencies:
                dependency_path = _code_path(transform_path, dependency)
                if not dependency_path.exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Server Transform code dependency does not exist",
                            str(dependency_path),
                            "code_dependencies",
                        )
                    )
            for dependency in transform.python_dependencies:
                if message := _python_dependency_error(dependency):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            message,
                            str(transform_path),
                            "python_dependencies",
                        )
                    )
            for parameter in transform.params:
                if parameter not in parameter_ids:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown query parameter: {parameter}",
                            str(transform_path),
                            "params",
                        )
                    )
            for name, reference in transform.inputs.items():
                message = _reference_error(
                    reference,
                    sources=dashboard.sources,
                    transforms=dashboard.transforms,
                    browser_transforms=dashboard.browser_transforms,
                    allow_browser=False,
                )
                if message:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Input {name}: {message}",
                            str(transform_path),
                            f"inputs.{name}",
                        )
                    )
            for name in transform.input_schemas:
                if name not in transform.inputs:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Input schema references undeclared input: {name}",
                            str(transform_path),
                            f"input_schemas.{name}",
                        )
                    )

        selection_contract = compile_selection_contract(dashboard.definition)
        selection_keys = {
            item.key
            for selections in selection_contract.values()
            for item in selections
        }
        for transform_path, transform in dashboard.browser_transforms.values():
            code_path = _code_path(transform_path, transform.code)
            if not code_path.exists():
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Browser Transform code does not exist",
                        str(code_path),
                        "code",
                    )
                )
            for parameter in transform.params:
                if parameter not in parameter_ids:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown query parameter: {parameter}",
                            str(transform_path),
                            "params",
                        )
                    )
            for selection in transform.selections:
                if selection not in selection_keys:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown canonical Selection key: {selection}",
                            str(transform_path),
                            "selections",
                        )
                    )
            for name, reference in transform.inputs.items():
                message = _reference_error(
                    reference,
                    sources=dashboard.sources,
                    transforms=dashboard.transforms,
                    browser_transforms=dashboard.browser_transforms,
                    allow_browser=True,
                )
                if message:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Input {name}: {message}",
                            str(transform_path),
                            f"inputs.{name}",
                        )
                    )

        for view in dashboard.definition.views:
            template = VIEW_TEMPLATES[view.template]
            missing = [
                field
                for field in template["fields"]
                if not getattr(view, field, None)
            ]
            if missing:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"View {view.id} template {view.template} requires: {', '.join(missing)}",
                        definition_path,
                        "views",
                    )
                )
            if view.template == "markdown" and not view.text and not view.input_ref:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"View {view.id} markdown requires text or input",
                        definition_path,
                        "views",
                    )
                )
            for name, reference in view.input_refs.items():
                message = _reference_error(
                    reference,
                    sources=dashboard.sources,
                    transforms=dashboard.transforms,
                    browser_transforms=dashboard.browser_transforms,
                    allow_browser=True,
                )
                if message:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"View {view.id} input {name}: {message}",
                            definition_path,
                            "views.inputs",
                        )
                    )
                elif name == "main":
                    output_kind = _reference_kind(reference, dashboard)
                    table_templates = {
                        "line", "bar", "stacked-bar", "pie", "scatter", "heatmap",
                        "radar", "table", "perspective",
                    }
                    if view.template in table_templates and output_kind not in {None, "table"}:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"View {view.id} template {view.template} requires a table input, got {output_kind}",
                                definition_path,
                                "views.input",
                            )
                        )
                    if view.template == "metric" and output_kind == "table" and not view.value:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"View {view.id} metric requires value for a table input",
                                definition_path,
                                "views.value",
                            )
                        )

        for reference in dashboard.definition.canvas.inputs:
            message = _reference_error(
                reference,
                sources=dashboard.sources,
                transforms=dashboard.transforms,
                browser_transforms=dashboard.browser_transforms,
                allow_browser=True,
            )
            if message:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Canvas input: {message}",
                        definition_path,
                        "canvas.inputs",
                    )
                )

        section_ids: set[str] = set()
        assigned_views: set[str] = set()
        repeat_templates = {"small-multiples", "selection-gallery"}
        for section in dashboard.definition.sections:
            if section.id in section_ids:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Duplicate section id: {section.id}",
                        definition_path,
                        "sections",
                    )
                )
            section_ids.add(section.id)
            if section.template in repeat_templates and not section.repeat:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Section {section.id} template {section.template} requires repeat",
                        definition_path,
                        "sections.repeat",
                    )
                )
            if section.repeat and section.template not in repeat_templates:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Section {section.id} repeat requires a repeat Section template",
                        definition_path,
                        "sections.template",
                    )
                )
            for view_id in section.views:
                if view_id not in view_ids:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Section references unknown View: {view_id}",
                            definition_path,
                            "sections.views",
                        )
                    )
                if view_id in assigned_views:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"View belongs to more than one Section: {view_id}",
                            definition_path,
                            "sections.views",
                        )
                    )
                assigned_views.add(view_id)
            if section.repeat:
                repeat_view = section.repeat.view or (section.views[0] if section.views else None)
                if repeat_view not in section.views:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Section {section.id} repeat View must appear in sections.views",
                            definition_path,
                            "sections.repeat.view",
                        )
                    )
                if len(section.views) != 1:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Section {section.id} repeat supports exactly one View blueprint",
                            definition_path,
                            "sections.views",
                        )
                    )
                if section.repeat.input:
                    message = _reference_error(
                        section.repeat.input,
                        sources=dashboard.sources,
                        transforms=dashboard.transforms,
                        browser_transforms=dashboard.browser_transforms,
                        allow_browser=True,
                    )
                    if message:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Section {section.id} repeat input: {message}",
                                definition_path,
                                "sections.repeat.input",
                            )
                        )
                if section.template == "selection-gallery":
                    selection_ids = {item.id for item in section.selections}
                    if not selection_ids:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Section {section.id} selection-gallery requires a Section Selection",
                                definition_path,
                                "sections.selections",
                            )
                        )
                    elif section.repeat.selection and section.repeat.selection not in selection_ids:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Section {section.id} repeat references unknown Section Selection",
                                definition_path,
                                "sections.repeat.selection",
                            )
                        )

        for view_id, selections in selection_contract.items():
            ids = [item.id for item in selections]
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            if duplicates:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Selection ids shadow each other for View {view_id}: {', '.join(duplicates)}",
                        definition_path,
                        "selections",
                    )
                )
            view = dashboard.views[view_id]
            for selection_id in sorted(set(view.selection_bindings) - set(ids)):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"View {view_id} binds unknown Selection: {selection_id}",
                        definition_path,
                        "selection_bindings",
                    )
                )

        canvas = dashboard.definition.canvas
        for field in ("template", "style", "script"):
            value = getattr(canvas, field)
            if value and not (dashboard.root / value).exists():
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Canvas {field} does not exist",
                        str(dashboard.root / value),
                        f"canvas.{field}",
                    )
                )
        for field, values in (("styles", canvas.styles), ("scripts", canvas.scripts)):
            for value in values:
                if not (dashboard.root / value).exists():
                    diagnostics.append(
                        Diagnostic(
                            "warning",
                            f"Presentation asset does not exist: {value}",
                            str(dashboard.root / value),
                            f"canvas.{field}",
                            "presentation_asset_missing",
                        )
                    )
    return diagnostics
