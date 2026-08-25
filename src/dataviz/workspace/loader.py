from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import yaml
from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from pydantic import ValidationError

from dataviz.content_templates import (
    allowed_content_controls,
    content_control_contract,
    content_template_fields,
    inspect_content_template,
)
from dataviz.errors import DatavizError, Diagnostic, WorkspaceError
from dataviz.identifiers import fallback_stable_id
from dataviz.execution.references import parse_output_reference
from dataviz.execution.dependencies import (
    DashboardDependencyContract,
    compile_dashboard_dependencies,
)
from dataviz.sql_contract import sql_parameter_names
from dataviz.workspace.models import (
    DashboardDefinition,
    DatasetTransformDefinition,
    DeclarativeViewDefinition,
    InteractiveTransformDefinition,
    InferredOptionDomainDefinition,
    NavigationItem,
    PresentationDefinition,
    SOURCE_DEFINITION_ADAPTER,
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
from dataviz.workspace.controls import compile_control_contract, scoped_control_registry
from dataviz.workspace.control_components import resolve_control_component
from dataviz.view_contracts import referenced_view_fields, validate_view_contract


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise WorkspaceError("Required YAML file does not exist", file=path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        details = {
            "problem": getattr(exc, "problem", None) or "YAML syntax error",
            "line": mark.line + 1 if mark is not None else None,
            "column": mark.column + 1 if mark is not None else None,
        }
        raise WorkspaceError("Invalid YAML", file=path, details=details) from exc
    except (OSError, UnicodeError) as exc:
        raise WorkspaceError(
            "YAML file cannot be read as UTF-8",
            file=path,
            details={"error_type": type(exc).__name__},
        ) from exc
    if not isinstance(data, dict):
        raise WorkspaceError("YAML document must be an object", file=path)
    return data


def _validation_errors(error: ValidationError) -> list[dict[str, Any]]:
    """Keep model diagnostics useful without echoing complete user input values."""
    return error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    )


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
                "docs": "dataviz docs dashboard",
            },
        )
    try:
        return model_type.model_validate(value)
    except ValidationError as exc:
        raise WorkspaceError(
            "Schema validation failed",
            file=path,
            details=_validation_errors(exc),
        ) from exc


def parse_source_definition(path: Path) -> SourceDefinition:
    value = read_yaml(path)
    if "schema" not in value:
        raise WorkspaceError(
            "Schema header is required for a standalone definition",
            file=path,
            details={
                "expected": "dataviz/source/v1",
                "docs": "dataviz schemas source --full --format json",
            },
        )
    try:
        return SOURCE_DEFINITION_ADAPTER.validate_python(value)
    except ValidationError as exc:
        raise WorkspaceError(
            "Source schema validation failed",
            file=path,
            details=_validation_errors(exc),
        ) from exc


@dataclass(slots=True)
class LoadedDashboard:
    root: Path
    definition_path: Path
    definition: DashboardDefinition
    logic_definition: DashboardDefinition
    sources: dict[str, tuple[Path, SourceDefinition]]
    dataset_transforms: dict[str, tuple[Path, DatasetTransformDefinition]]
    interactive_transforms: dict[str, tuple[Path, InteractiveTransformDefinition]]
    views: dict[str, DeclarativeViewDefinition]
    presentation_path: Path | None = None
    presentation: PresentationDefinition | None = None
    presentation_diagnostics: list[Diagnostic] | None = None
    readme: str = ""
    _dependency_contract: DashboardDependencyContract | None = dataclass_field(
        default=None,
        init=False,
        repr=False,
    )
    _dependency_contract_lock: Lock = dataclass_field(
        default_factory=Lock,
        init=False,
        repr=False,
    )

    @property
    def dependency_contract(self) -> DashboardDependencyContract:
        """Return the one compiled graph owned by this immutable load snapshot.

        Workspace hot reload creates a new ``LoadedDashboard``. Every consumer
        inside one snapshot therefore observes the exact same Query, Control,
        Interactive and View dependency graph instead of independently deriving
        relationships from the mutable DSL model.
        """

        if self._dependency_contract is None:
            with self._dependency_contract_lock:
                if self._dependency_contract is None:
                    self._dependency_contract = compile_dashboard_dependencies(self)
        return self._dependency_contract

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
                    "error",
                    f"Presentation ignored: {error.message}",
                    str(presentation_path),
                    code="presentation_invalid",
                )
            )
        else:
            if candidate.dashboard != logic_definition.id:
                presentation_diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Presentation targets {candidate.dashboard}, expected {logic_definition.id}; ignored",
                        str(presentation_path),
                        "dashboard",
                        "presentation_dashboard_mismatch",
                    )
                )
            else:
                presentation = candidate
    sources: dict[str, tuple[Path, SourceDefinition]] = {}
    dataset_transforms: dict[str, tuple[Path, DatasetTransformDefinition]] = {}
    interactive_transforms: dict[str, tuple[Path, InteractiveTransformDefinition]] = {}

    for source_entry in definition.sources:
        if isinstance(source_entry, str):
            source_path = _require_dashboard_asset(
                root, root, source_entry, "Source definition"
            )
            source = parse_source_definition(source_path)
        else:
            source_path = definition_path
            try:
                source = SOURCE_DEFINITION_ADAPTER.validate_python(
                    {"schema": "dataviz/source/v1", **source_entry}
                )
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline source schema validation failed",
                    file=definition_path,
                    details=_validation_errors(exc),
                ) from exc
        if source.id in sources:
            raise WorkspaceError(f"Duplicate source id: {source.id}", file=source_path)
        source_data_path = getattr(source, "path", None)
        source_code_path = getattr(source, "code", None)
        if source_data_path and not getattr(source, "adapter", None):
            _require_dashboard_asset(
                root, source_path.parent, source_data_path, "Source path"
            )
        if source_code_path:
            _require_dashboard_asset(
                root, source_path.parent, source_code_path, "Source code"
            )
        for dependency in getattr(source, "code_dependencies", []):
            _require_dashboard_asset(
                root, source_path.parent, dependency, "Source code dependency"
            )
        sources[source.id] = (source_path, source)

    for transform_entry in definition.dataset_transforms:
        if isinstance(transform_entry, str):
            transform_path = _require_dashboard_asset(
                root, root, transform_entry, "Dataset Transform definition"
            )
            transform = parse_model(DatasetTransformDefinition, transform_path)
        else:
            transform_path = definition_path
            try:
                transform = DatasetTransformDefinition.model_validate(
                    {"schema": "dataviz/dataset-transform/v1", **transform_entry}
                )
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline Dataset Transform schema validation failed",
                    file=definition_path,
                    details=_validation_errors(exc),
                ) from exc
        if transform.id in dataset_transforms:
            raise WorkspaceError(f"Duplicate Dataset Transform id: {transform.id}", file=transform_path)
        _require_dashboard_asset(
            root, transform_path.parent, transform.code, "Dataset Transform code"
        )
        for dependency in transform.code_dependencies:
            _require_dashboard_asset(
                root,
                transform_path.parent,
                dependency,
                "Dataset Transform code dependency",
            )
        dataset_transforms[transform.id] = (transform_path, transform)

    for transform_entry in definition.interactive_transforms:
        if isinstance(transform_entry, str):
            transform_path = _require_dashboard_asset(
                root, root, transform_entry, "Interactive Transform definition"
            )
            transform = parse_model(InteractiveTransformDefinition, transform_path)
        else:
            transform_path = definition_path
            try:
                transform = InteractiveTransformDefinition.model_validate(
                    {"schema": "dataviz/interactive-transform/v1", **transform_entry}
                )
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline Interactive Transform schema validation failed",
                    file=definition_path,
                    details=_validation_errors(exc),
                ) from exc
        if transform.id in interactive_transforms:
            raise WorkspaceError(f"Duplicate Interactive Transform id: {transform.id}", file=transform_path)
        _require_dashboard_asset(
            root, transform_path.parent, transform.code, "Interactive Transform code"
        )
        for dependency in transform.code_dependencies:
            _require_dashboard_asset(
                root,
                transform_path.parent,
                dependency,
                "Interactive Transform code dependency",
            )
        interactive_transforms[transform.id] = (transform_path, transform)

    canvas = logic_definition.canvas
    for value in [canvas.template, *canvas.styles, *canvas.scripts]:
        if value:
            _require_dashboard_asset(root, root, value, "Canvas asset")

    views: dict[str, DeclarativeViewDefinition] = {}
    for view in definition.views:
        if view.id in views:
            raise WorkspaceError(f"Duplicate view id: {view.id}", file=definition_path)
        if view.template == "image" and view.url:
            parsed_url = urlparse(view.url)
            if not parsed_url.scheme and not parsed_url.netloc:
                asset_path = _require_dashboard_asset(
                    root,
                    root,
                    parsed_url.path,
                    "Image View asset",
                )
                if not asset_path.is_file():
                    raise WorkspaceError(
                        f"Image View asset does not exist: {view.url}",
                        file=definition_path,
                        details={
                            "code": "view_image_asset_missing",
                            "view": view.id,
                            "url": view.url,
                        },
                    )
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
        dataset_transforms=dataset_transforms,
        interactive_transforms=interactive_transforms,
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


def _require_dashboard_asset(
    dashboard_root: Path,
    base: Path,
    value: str,
    label: str,
) -> Path:
    path = (base / value).resolve()
    if not _is_within(path, dashboard_root):
        raise WorkspaceError(
            f"{label} must stay inside its Dashboard folder",
            file=dashboard_root / "dashboard.yaml",
            details={
                "code": "dashboard_asset_outside",
                "value": value,
                "resolved_path": str(path),
            },
        )
    return path


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

    control_definitions = {
        f"query:{item.id}": item for item in logic.query_parameters
    }
    for controls in compile_control_contract(logic).values():
        for item in controls:
            control_definitions.setdefault(item.key, item.definition)
    for control_key, component in presentation.control_components.items():
        definition = control_definitions.get(control_key)
        if definition is None:
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Presentation references unknown control: {control_key}",
                    str(presentation_path),
                    f"control_components.{control_key}",
                    "presentation_unknown_control",
                )
            )
            continue
        try:
            resolve_control_component(definition, component)
        except ValueError as error:
            diagnostics.append(
                Diagnostic(
                    "error",
                    str(error),
                    str(presentation_path),
                    f"control_components.{control_key}",
                    "presentation_control_component_incompatible",
                    {"control": control_key, "component": component.component},
                )
            )

    sections = {section.id: section for section in effective.sections}
    for section_id, override in presentation.sections.items():
        section = sections.get(section_id)
        if section is None:
            diagnostics.append(
                Diagnostic(
                    "error",
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
                    "error",
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
            try:
                validate_view_contract(replacement)
            except ValueError as exc:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Presentation override is invalid for View {view_id}: {exc}",
                        str(presentation_path),
                        f"views.{view_id}",
                        "presentation_view_contract_invalid",
                    )
                )
                continue
            effective.views[effective.views.index(view)] = replacement
            declarative_views[view_id] = replacement

    canvas_update = _present_fields(presentation.canvas)
    template = canvas_update.get("template")
    if template:
        template_path = (presentation_path.parent / template).resolve()
        if not _is_within(template_path, presentation_path.parent):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Presentation canvas template escapes its Dashboard folder: {template}",
                    str(presentation_path),
                    "canvas.template",
                    "presentation_asset_outside_dashboard",
                    {"resolved_path": str(template_path)},
                )
            )
            canvas_update.pop("template")
        elif not template_path.is_file():
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Presentation canvas template does not exist and will be ignored: {template}",
                    str(template_path),
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
    safe_css = _presentation_assets(
        presentation.assets.css,
        presentation_path,
        diagnostics,
        field="assets.css",
    )
    safe_js = _presentation_assets(
        presentation.assets.js,
        presentation_path,
        diagnostics,
        field="assets.js",
    )
    if safe_css:
        canvas_update["styles"] = list(
            dict.fromkeys([*effective.canvas.styles, *safe_css])
        )
    if safe_js:
        canvas_update["scripts"] = list(
            dict.fromkeys([*effective.canvas.scripts, *safe_js])
        )
    if canvas_update:
        effective.canvas = effective.canvas.model_copy(update=canvas_update)
    return effective


def _presentation_assets(
    values: list[str],
    presentation_path: Path,
    diagnostics: list[Diagnostic],
    *,
    field: str,
) -> list[str]:
    safe: list[str] = []
    for value in values:
        path = (presentation_path.parent / value).resolve()
        if not _is_within(path, presentation_path.parent):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Presentation asset escapes its Dashboard folder: {value}",
                    str(presentation_path),
                    field,
                    "presentation_asset_outside_dashboard",
                    {"resolved_path": str(path)},
                )
            )
        elif not path.is_file():
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Presentation asset does not exist and will be ignored: {value}",
                    str(path),
                    field,
                    "presentation_asset_missing",
                )
            )
        else:
            safe.append(value)
    return safe


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

    def trash_folder_item(
        path: tuple[str, ...],
        folder_paths: set[tuple[str, ...]],
        grouped_dashboard_paths: list[Path],
    ) -> NavigationItem:
        child_folders = sorted(
            candidate
            for candidate in folder_paths
            if len(candidate) == len(path) + 1 and candidate[:-1] == path
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
                    title=location.leaf,
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
                Diagnostic(
                    "error",
                    entry.message,
                    str(entry.dashboard.definition_path),
                    code="dashboard_id_conflict",
                )
            )
            entry.dashboard = None
    conflicting_ids = {
        dashboard_id for dashboard_id, count in id_counts.items() if count > 1
    }
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
                transform.export.mode == "interactive"
                and transform.export.assets == "bundle"
            )
            if not live_bundle and not exported_bundle:
                continue
            requirements.extend(
                (dependency, transform_path)
                for dependency in transform.python_dependencies
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
    missing_core = [
        name for name in _PYODIDE_CORE_ASSETS if not (bundle_path / name).is_file()
    ]
    if missing_core:
        return [
            Diagnostic(
                "error",
                "Pyodide bundle is missing required Runtime assets: "
                + ", ".join(missing_core),
                str(bundle_path),
                field,
                "pyodide_bundle_incomplete",
                {"missing": missing_core},
            )
        ]

    package_manifest_path = bundle_path / "package.json"
    try:
        package_manifest = json.loads(
            package_manifest_path.read_text(encoding="utf-8")
        )
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
    bundle_version = (
        package_manifest.get("version")
        if isinstance(package_manifest, dict)
        else None
    )
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
    python_full_version = (
        lock_info.get("python") if isinstance(lock_info, dict) else None
    )
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
        if requirement.marker and not requirement.marker.evaluate(
            environment=marker_environment
        ):
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
            pending.extend(
                dependency
                for dependency in dependencies
                if isinstance(dependency, str)
            )

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
        return "error", "pyodide_dependency_invalid", f"Invalid browser-python dependency {value!r}: {error}"
    normalized = requirement.name.lower().replace("_", "-")
    if requirement.url:
        filename = Path(urlparse(requirement.url).path).name.lower()
        if filename.endswith(".whl") and not (
            "none-any.whl" in filename
            or "emscripten" in filename
            or "wasm32" in filename
        ):
            return (
                "error",
                "pyodide_wheel_incompatible",
                f"browser-python wheel is not pure Python or Emscripten/WASM: {filename}",
            )
        if not filename.endswith((".whl", ".tar.gz", ".zip")):
            return "warning", "pyodide_dependency_unverified", f"Could not classify browser-python dependency URL: {requirement.url}"
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
            f"Pyodide {pyodide_version} bundles {requirement.name}=={available}, "
            f"not {pinned}",
        )
    if available is None:
        return (
            "warning",
            "pyodide_dependency_unverified",
            f"{requirement.name}=={pinned} is not in the bundled Pyodide "
            f"{pyodide_version} catalog; verify that a pure-Python or WASM wheel exists",
        )
    return None


def _duplicates(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def _cycle_nodes(graph: dict[str, set[str]]) -> list[str]:
    incoming = {node: set(dependencies) for node, dependencies in graph.items()}
    ready = [node for node, dependencies in incoming.items() if not dependencies]
    visited: set[str] = set()
    while ready:
        current = ready.pop()
        if current in visited:
            continue
        visited.add(current)
        for node, dependencies in incoming.items():
            if current in dependencies:
                dependencies.remove(current)
                if not dependencies:
                    ready.append(node)
    return sorted(set(graph) - visited)


def _reference_error(
    reference: str,
    *,
    sources: dict[str, tuple[Path, SourceDefinition]],
    dataset_transforms: dict[str, tuple[Path, DatasetTransformDefinition]],
    interactive_transforms: dict[str, tuple[Path, InteractiveTransformDefinition]],
    allow_interactive: bool,
) -> str | None:
    try:
        parsed = parse_output_reference(reference)
    except Exception as error:
        return str(error)
    kind, _, node_id = parsed.node_id.partition(":")
    collections = {
        "source": sources,
        "dataset": dataset_transforms,
        "interactive": interactive_transforms,
    }
    if kind == "interactive" and not allow_interactive:
        return "Query DAG nodes cannot depend on Interactive Outputs"
    collection = collections.get(kind)
    if collection is None or node_id not in collection:
        return f"Unknown output node: {parsed.node_id}"
    definition = collection[node_id][1]
    outputs = definition.outputs
    if parsed.output not in outputs:
        return f"Unknown output {parsed.output!r} on {parsed.node_id}"
    return None


def _safe_output_reference(reference: str):
    try:
        return parse_output_reference(reference)
    except Exception:
        return None


def _reference_kind(reference: str, dashboard: LoadedDashboard) -> str | None:
    parsed = parse_output_reference(reference)
    kind, _, node_id = parsed.node_id.partition(":")
    collection = {
        "source": dashboard.sources,
        "dataset": dashboard.dataset_transforms,
        "interactive": dashboard.interactive_transforms,
    }[kind]
    definition = collection[node_id][1]
    output = definition.outputs.get(parsed.output)
    return output.kind if output else None


def _reference_output_definition(reference: str, dashboard: LoadedDashboard):
    parsed = parse_output_reference(reference)
    kind, _, node_id = parsed.node_id.partition(":")
    collection = {
        "source": dashboard.sources,
        "dataset": dashboard.dataset_transforms,
        "interactive": dashboard.interactive_transforms,
    }[kind]
    definition = collection[node_id][1]
    return definition.outputs.get(parsed.output)


def validate_workspace(workspace: LoadedWorkspace) -> list[Diagnostic]:
    """Validate the strict v2 contract and every cross-file/runtime reference."""
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

    runtime = workspace.definition.runtime
    for field in ("echarts_js", "arrow_js"):
        configured = getattr(runtime, field)
        parsed = urlparse(configured)
        if parsed.scheme in {"http", "https"}:
            continue
        asset_path = (workspace.root / configured).resolve()
        if not _is_within(asset_path, workspace.root):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Local Runtime asset must stay inside the Workspace: {configured}",
                    str(workspace.definition_path),
                    f"runtime.{field}",
                    "runtime_asset_outside_workspace",
                    {"asset": configured},
                )
            )
        elif not asset_path.is_file():
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Local Runtime asset does not exist: {configured}",
                    str(workspace.definition_path),
                    f"runtime.{field}",
                    "runtime_asset_missing",
                    {"asset": configured},
                )
            )
        else:
            try:
                asset_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Local Runtime asset is not readable UTF-8 JavaScript: {configured}",
                        str(workspace.definition_path),
                        f"runtime.{field}",
                        "runtime_asset_unreadable",
                        {"asset": configured, "error_type": type(error).__name__},
                    )
                )
    # A local bundle may be selected only by an exported browser-python branch
    # even when the live Server itself uses the CDN. Validate every configured
    # bundle path, not only the live Runtime policy.
    if runtime.pyodide_bundle_path:
        bundle_path = (workspace.root / runtime.pyodide_bundle_path).resolve()
        if not _is_within(bundle_path, workspace.root):
            diagnostics.append(
                Diagnostic(
                    "error",
                    "Pyodide bundle must stay inside the Workspace",
                    str(workspace.definition_path),
                    "runtime.pyodide_bundle_path",
                    "pyodide_bundle_outside_workspace",
                )
            )
        else:
            diagnostics.extend(_validate_pyodide_bundle(workspace, bundle_path))

    for dashboard in workspace.dashboards.values():
        diagnostics.extend(dashboard.presentation_diagnostics or [])
        definition_path = str(dashboard.definition_path)
        parameter_ids = {item.id for item in dashboard.definition.query_parameters}
        control_registry = scoped_control_registry(dashboard.definition)
        control_contract = compile_control_contract(dashboard.definition)
        compute_control_keys = {
            key for key, item in control_registry.items() if item.kind == "compute"
        }
        selection_control_keys = {
            key for key, item in control_registry.items() if item.kind == "selection"
        }
        control_content_contract = content_control_contract(dashboard.definition)
        dependency_contract = None
        view_ids = set(dashboard.views)

        duplicate_contracts = [
            (
                "query_parameters",
                _duplicates([item.id for item in dashboard.definition.query_parameters]),
            ),
            (
                "controls",
                _duplicates([item.id for item in dashboard.definition.controls]),
            ),
            *(
                (
                    f"sections.{section.id}.controls",
                    _duplicates([item.id for item in section.controls]),
                )
                for section in dashboard.definition.sections
            ),
            *(
                (
                    f"views.{view.id}.controls",
                    _duplicates([item.id for item in view.controls]),
                )
                for view in dashboard.definition.views
            ),
        ]
        for field, duplicate_ids in duplicate_contracts:
            if duplicate_ids:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Duplicate ids in {field}: {', '.join(duplicate_ids)}",
                        definition_path,
                        field,
                        "state_id_duplicate",
                        {"ids": duplicate_ids},
                    )
                )

        option_domain_contract_valid = True
        for control_key, item in control_registry.items():
            options = item.definition.options
            if (
                item.kind != "selection"
                or not isinstance(options, InferredOptionDomainDefinition)
                or not options.source
            ):
                continue
            reference = options.source
            message = _reference_error(
                reference,
                sources=dashboard.sources,
                dataset_transforms=dashboard.dataset_transforms,
                interactive_transforms=dashboard.interactive_transforms,
                allow_interactive=False,
            )
            if message:
                option_domain_contract_valid = False
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Selection {control_key} options.source: {message}",
                        definition_path,
                        f"controls.{control_key}.options.source",
                        "selection_option_domain_invalid",
                        {"control": control_key, "reference": reference},
                    )
                )
                continue
            if _reference_kind(reference, dashboard) != "table":
                option_domain_contract_valid = False
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Selection {control_key} options.source must reference a table Output",
                        definition_path,
                        f"controls.{control_key}.options.source",
                        "selection_option_domain_kind",
                        {"control": control_key, "reference": reference},
                    )
                )
                continue
            output = _reference_output_definition(reference, dashboard)
            if output is not None and output.schema_:
                declared = {column.name for column in output.schema_}
                required_fields = {
                    field
                    for effective_controls in control_contract.values()
                    for effective in effective_controls
                    if effective.key == control_key
                    for field in (
                        effective.definition.path_fields
                        or [effective.binding.field or effective.id]
                    )
                } or set(
                    item.definition.path_fields
                    or [item.definition.field or item.id]
                )
                unknown = sorted(required_fields - declared)
                if unknown:
                    option_domain_contract_valid = False
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Selection {control_key} option domain does not declare fields: "
                            + ", ".join(unknown),
                            definition_path,
                            f"controls.{control_key}.options.source",
                            "selection_option_domain_field_unknown",
                            {
                                "control": control_key,
                                "reference": reference,
                                "unknown": unknown,
                                "declared": sorted(declared),
                            },
                        )
                    )

        if option_domain_contract_valid:
            try:
                dependency_contract = dashboard.dependency_contract
                option_domains = {
                    key: list(references)
                    for key, references in dependency_contract.selection_option_domains.items()
                }
            except DatavizError as error:
                option_domains = {}
                payload = error.as_dict()
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Cannot compile Dashboard Dependency Contract: {error.message}",
                        definition_path,
                        "dependencies",
                        payload["code"],
                        payload.get("details"),
                    )
                )
            except Exception as error:
                option_domains = {}
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Cannot compile Dashboard Dependency Contract: {error}",
                        definition_path,
                        "dependencies",
                        "dependency_contract_invalid",
                    )
                )
            for control_key, item in control_registry.items():
                definition = item.definition
                dynamic_select = (
                    item.kind == "selection"
                    and definition.type in {"single_select", "multi_select"}
                    and isinstance(definition.options, InferredOptionDomainDefinition)
                )
                references = option_domains.get(control_key, [])
                if dynamic_select and not references:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Dynamic Selection {control_key} has no Base Output option domain",
                            definition_path,
                            f"controls.{control_key}",
                            "selection_option_domain_missing",
                            {"control": control_key},
                        )
                    )
                    continue
                if not dynamic_select:
                    continue
                field_sets = [
                    set(
                        effective.definition.path_fields
                        or [effective.binding.field or effective.id]
                    )
                    for effective_controls in control_contract.values()
                    for effective in effective_controls
                    if effective.key == control_key
                ] or [set(definition.path_fields or [definition.field or definition.id])]
                declared_domains: list[set[str]] = []
                has_dynamic_schema = False
                for reference in references:
                    if _reference_kind(reference, dashboard) != "table":
                        continue
                    output = _reference_output_definition(reference, dashboard)
                    if output is None or not output.schema_:
                        has_dynamic_schema = True
                        continue
                    declared_domains.append({column.name for column in output.schema_})
                if (
                    not has_dynamic_schema
                    and not all(
                        any(fields <= declared for declared in declared_domains)
                        for fields in field_sets
                    )
                ):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Dynamic Selection {control_key} cannot derive its fields from any Base Output",
                            definition_path,
                            f"controls.{control_key}",
                            "selection_option_domain_field_unknown",
                            {
                                "control": control_key,
                                "references": references,
                                "required_field_sets": [sorted(fields) for fields in field_sets],
                                "declared_domains": [sorted(fields) for fields in declared_domains],
                            },
                        )
                    )

        for field, value in content_template_fields(dashboard.definition):
            inspection = inspect_content_template(value)
            for message in inspection.errors:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        message,
                        definition_path,
                        field,
                        "content_template_invalid",
                    )
                )
            for parameter_id in sorted(
                inspection.query_parameters - parameter_ids
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Content references unknown Query Parameter: {parameter_id}",
                        definition_path,
                        field,
                        "content_parameter_unknown",
                    )
                )
            known_control_references = inspection.controls & set(control_content_contract)
            for expression in sorted(inspection.controls - set(control_content_contract)):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Content references unknown Control: {expression}",
                        definition_path,
                        field,
                        "content_control_unknown",
                    )
                )
            for expression in sorted(
                known_control_references
                - allowed_content_controls(dashboard.definition, field)
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Content references Control outside its visible scope: {expression}",
                        definition_path,
                        field,
                        "content_control_out_of_scope",
                    )
                )

        for source_path, source in dashboard.sources.values():
            if not _is_within(source_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Source definition must stay inside its Dashboard folder",
                        str(source_path),
                        "sources",
                        "source_definition_outside_dashboard",
                    )
                )
            source_adapter = getattr(source, "adapter", None)
            if source_adapter and adapter_resolver:
                try:
                    _, adapter = adapter_resolver.resolve(
                        source_adapter, dashboard.definition.adapters
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
                        {"file"}
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
                    elif source.type in {"sql", "python"}:
                        try:
                            adapter_resolver.runtime_config(
                                source_adapter,
                                dashboard.definition.adapters,
                            )
                        except Exception as error:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    f"Adapter runtime configuration is incomplete: {error}",
                                    str(source_path),
                                    "adapter",
                                    "adapter_runtime_configuration_invalid",
                                )
                            )
                        else:
                            if source.type == "sql":
                                try:
                                    adapter_resolver.validate_sql_driver(
                                        source_adapter,
                                        dashboard.definition.adapters,
                                    )
                                except Exception as error:
                                    diagnostics.append(
                                        Diagnostic(
                                            "error",
                                            str(error),
                                            str(source_path),
                                            "adapter",
                                            "adapter_sql_driver_invalid",
                                        )
                                    )
                    elif source.type == "file":
                        try:
                            data_path = adapter_resolver.resolve_path(
                                source_adapter,
                                source.path,
                                dashboard.definition.adapters,
                            )
                        except Exception as error:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    str(error),
                                    str(source_path),
                                    "path",
                                    "source_asset_invalid",
                                )
                            )
                        else:
                            if not data_path.is_file():
                                diagnostics.append(
                                    Diagnostic(
                                        "error",
                                        "File Source data file does not exist",
                                        str(data_path),
                                        "path",
                                        "source_asset_missing",
                                    )
                                )
            for parameter in getattr(source, "query_params", []):
                if parameter not in parameter_ids:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown query parameter: {parameter}",
                            str(source_path),
                            "query_params",
                        )
                        )
            if source.type == "file":
                file_format = (
                    source.format
                    or Path(source.path).suffix.removeprefix(".").lower()
                )
                reader_dependency = {
                    "xlsx": "openpyxl>=3.1",
                    "xls": "xlrd>=2.0",
                }.get(file_format)
                if reader_dependency and (
                    message := _python_dependency_error(reader_dependency)
                ):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Excel File Source reader dependency is unavailable: {message}",
                            str(source_path),
                            "format",
                            "file_reader_dependency_unavailable",
                            {
                                "format": file_format,
                                "dependency": reader_dependency,
                                "install": "pip install 'ai-dataviz[excel]'",
                            },
                        )
                    )
            for field in ("path", "code"):
                value = getattr(source, field, None)
                if not value:
                    continue
                if field == "path" and source_adapter:
                    continue
                path = _code_path(source_path, value)
                if not _is_within(path, dashboard.root):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Source {field} must stay inside its Dashboard folder",
                            str(path),
                            field,
                            "source_asset_outside_dashboard",
                        )
                    )
                    continue
                if not path.is_file():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Source {field} does not exist or is not a file",
                            str(path),
                            field,
                        )
                    )
            if source.type == "sql" and source.code:
                code_path = _code_path(source_path, source.code)
                if code_path.exists():
                    try:
                        sql = code_path.read_text(encoding="utf-8")
                    except (OSError, UnicodeError) as error:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"SQL source could not be read: {error}",
                                str(code_path),
                                "code",
                                "sql_file_unreadable",
                            )
                        )
                    else:
                        declared = set(source.query_params)
                        referenced = sql_parameter_names(sql)
                        undeclared = sorted(referenced - declared)
                        unused = sorted(declared - referenced)
                        if undeclared:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    "SQL uses named parameters not declared in Source query_params: "
                                    + ", ".join(undeclared),
                                    str(source_path),
                                    "query_params",
                                    "sql_parameter_undeclared",
                                    {"parameters": undeclared, "sql_file": str(code_path)},
                                )
                            )
                        if unused:
                            diagnostics.append(
                                Diagnostic(
                                    "warning",
                                    "Source query_params are not referenced by SQL: "
                                    + ", ".join(unused),
                                    str(source_path),
                                    "query_params",
                                    "sql_parameter_unused",
                                    {"parameters": unused, "sql_file": str(code_path)},
                                )
                            )
            for dependency in getattr(source, "code_dependencies", []):
                dependency_path = _code_path(source_path, dependency)
                if not _is_within(dependency_path, dashboard.root):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Python Source code dependency must stay inside its Dashboard folder",
                            str(dependency_path),
                            "code_dependencies",
                            "code_dependency_outside_dashboard",
                        )
                    )
                elif not dependency_path.exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Python Source code dependency does not exist",
                            str(dependency_path),
                            "code_dependencies",
                        )
                    )
            for dependency in getattr(source, "python_dependencies", []):
                if message := _python_dependency_error(dependency):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            message,
                            str(source_path),
                            "python_dependencies",
                        )
                    )

        for transform_path, transform in dashboard.dataset_transforms.values():
            code_path = _code_path(transform_path, transform.code)
            if not _is_within(transform_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Dataset Transform definition must stay inside its Dashboard folder",
                        str(transform_path),
                        "dataset_transforms",
                        "dataset_definition_outside_dashboard",
                    )
                )
            if not _is_within(code_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Dataset Transform code must stay inside its Dashboard folder",
                        str(code_path),
                        "code",
                        "dataset_code_outside_dashboard",
                    )
                )
            elif not code_path.exists():
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Dataset Transform code does not exist",
                        str(code_path),
                        "code",
                    )
                )
            for dependency in transform.code_dependencies:
                dependency_path = _code_path(transform_path, dependency)
                if not _is_within(dependency_path, dashboard.root):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Dataset Transform code dependency must stay inside its Dashboard folder",
                            str(dependency_path),
                            "code_dependencies",
                            "code_dependency_outside_dashboard",
                        )
                    )
                elif not dependency_path.exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Dataset Transform code dependency does not exist",
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
            for parameter in transform.query_params:
                if parameter not in parameter_ids:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown query parameter: {parameter}",
                            str(transform_path),
                            "query_params",
                        )
                    )
            for name, reference in transform.inputs.items():
                message = _reference_error(
                    reference,
                    sources=dashboard.sources,
                    dataset_transforms=dashboard.dataset_transforms,
                    interactive_transforms=dashboard.interactive_transforms,
                    allow_interactive=False,
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

        for transform_path, transform in dashboard.interactive_transforms.values():
            code_path = _code_path(transform_path, transform.code)
            if not _is_within(transform_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Interactive Transform definition must stay inside its Dashboard folder",
                        str(transform_path),
                        "interactive_transforms",
                        "interactive_definition_outside_dashboard",
                    )
                )
            if not _is_within(code_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Interactive Transform code must stay inside its Dashboard folder",
                        str(code_path),
                        "code",
                        "interactive_code_outside_dashboard",
                    )
                )
            elif not code_path.exists():
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Interactive Transform code does not exist",
                        str(code_path),
                        "code",
                    )
                )
            if (
                transform.runtime in {"browser-js", "browser-python"}
                and not _is_within(code_path, transform_path.parent)
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Browser Interactive Transform code must stay inside the "
                        "Transform definition folder",
                        str(code_path),
                        "code",
                        "browser_code_outside_transform_package",
                    )
                )
            for dependency in transform.code_dependencies:
                dependency_path = _code_path(transform_path, dependency)
                if not _is_within(dependency_path, dashboard.root):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Interactive Transform code dependency must stay inside its Dashboard folder",
                            str(dependency_path),
                            "code_dependencies",
                            "code_dependency_outside_dashboard",
                        )
                    )
                elif not dependency_path.exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Interactive Transform code dependency does not exist",
                            str(dependency_path),
                            "code_dependencies",
                            "interactive_code_dependency_missing",
                        )
                    )
                elif (
                    transform.runtime in {"browser-js", "browser-python"}
                    and not _is_within(dependency_path, transform_path.parent)
                ):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Browser code dependency must stay inside the Transform "
                            "definition folder",
                            str(dependency_path),
                            "code_dependencies",
                            "browser_dependency_outside_transform_package",
                        )
                    )
            if transform.runtime == "server-python":
                for dependency in transform.python_dependencies:
                    if message := _python_dependency_error(dependency):
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                message,
                                str(transform_path),
                                "python_dependencies",
                                "python_dependency_unavailable",
                            )
                        )
            elif transform.runtime == "browser-python":
                for dependency in transform.python_dependencies:
                    result = _browser_python_dependency_diagnostic(
                        dependency, workspace.definition.runtime.pyodide_version
                    )
                    if result:
                        level, code, message = result
                        diagnostics.append(
                            Diagnostic(
                                level,
                                message,
                                str(transform_path),
                                "python_dependencies",
                                code,
                                {"dependency": dependency},
                            )
                        )
            for parameter in transform.query_params:
                if parameter not in parameter_ids:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown query parameter: {parameter}",
                            str(transform_path),
                            "query_params",
                        )
                    )
            for alias, control_key in transform.compute_inputs.items():
                if control_key not in compute_control_keys:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown Compute Control: {control_key}",
                            str(transform_path),
                            f"compute_inputs.{alias}",
                            "interactive_compute_control_unknown",
                        )
                    )
            for alias, control_key in transform.selection_inputs.items():
                if control_key not in selection_control_keys:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown Selection Control: {control_key}",
                            str(transform_path),
                            f"selection_inputs.{alias}",
                            "interactive_selection_control_unknown",
                        )
                    )
            for name, reference in transform.inputs.items():
                message = _reference_error(
                    reference,
                    sources=dashboard.sources,
                    dataset_transforms=dashboard.dataset_transforms,
                    interactive_transforms=dashboard.interactive_transforms,
                    allow_interactive=True,
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
                            "interactive_input_schema_unknown",
                        )
                    )

        # Recovery-only diagnostics for a graph that could not be compiled. A
        # valid Dashboard never builds a second runtime DAG here.
        dataset_graph: dict[str, set[str]] = {} if dependency_contract else {
            transform_id: {
                parsed.node_id.split(":", 1)[1]
                for reference in transform.inputs.values()
                if (parsed := _safe_output_reference(reference)) is not None
                and parsed.node_id.startswith("dataset:")
                and parsed.node_id.split(":", 1)[1] in dashboard.dataset_transforms
            }
            for transform_id, (_, transform) in dashboard.dataset_transforms.items()
        }
        if cycle := _cycle_nodes(dataset_graph):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Dataset Transform dependency graph contains a cycle: {', '.join(cycle)}",
                    definition_path,
                    "dataset_transforms",
                    "dataset_cycle",
                    {"nodes": cycle},
                )
            )

        interactive_graph: dict[str, set[str]] = {} if dependency_contract else {
            transform_id: {
                parsed.node_id.split(":", 1)[1]
                for reference in transform.inputs.values()
                if (parsed := _safe_output_reference(reference)) is not None
                and parsed.node_id.startswith("interactive:")
                and parsed.node_id.split(":", 1)[1] in dashboard.interactive_transforms
            }
            for transform_id, (_, transform) in dashboard.interactive_transforms.items()
        }
        if cycle := _cycle_nodes(interactive_graph):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Interactive Transform dependency graph contains a cycle: {', '.join(cycle)}",
                    definition_path,
                    "interactive_transforms",
                    "interactive_cycle",
                    {"nodes": cycle},
                )
            )

        for transform_id, (transform_path, transform) in dashboard.interactive_transforms.items():
            ancestors = (
                dependency_contract.interactive_ancestors(transform_id)
                if dependency_contract is not None
                else set()
            )
            if transform.export.mode == "interactive":
                invalid_ancestors = []
                for ancestor in sorted(ancestors):
                    dependency = dashboard.interactive_transforms[ancestor][1]
                    stateful_snapshot = (
                        dependency.export.mode != "interactive"
                        and bool(
                            dependency.compute_inputs
                            or dependency.selection_inputs
                        )
                    )
                    unavailable = dependency.export.mode == "unavailable"
                    if stateful_snapshot or unavailable:
                        invalid_ancestors.append(ancestor)
                if invalid_ancestors:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "An interactive export cannot depend on stateful snapshot/unavailable "
                            "Interactive Transforms: " + ", ".join(invalid_ancestors),
                            str(transform_path),
                            "export.mode",
                            "interactive_export_dependency_not_portable",
                            {"dependency_chain": invalid_ancestors},
                        )
                    )

            if (
                transform.runtime == "browser-python"
                and transform.export.assets == "bundle"
                and not workspace.definition.runtime.pyodide_bundle_path
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "browser-python export.assets=bundle requires "
                        "workspace runtime.pyodide_bundle_path",
                        str(transform_path),
                        "export.assets",
                        "pyodide_bundle_not_configured",
                    )
                )

        browser_python_asset_modes = {
            transform.export.assets
            for _, transform in dashboard.interactive_transforms.values()
            if transform.runtime == "browser-python"
            and transform.export.mode != "unavailable"
            and transform.export.assets is not None
        }
        if len(browser_python_asset_modes) > 1:
            diagnostics.append(
                Diagnostic(
                    "error",
                    "All browser-python Interactive Transforms in one Dashboard must "
                    "use the same export.assets policy",
                    definition_path,
                    "interactive_transforms",
                    "pyodide_asset_policy_ambiguous",
                    {"policies": sorted(browser_python_asset_modes)},
                )
            )

        trigger_consumers: dict[str, list[tuple[str, str]]] = {
            control_key: [] for control_key in compute_control_keys
        }
        for transform_id, (_, transform) in dashboard.interactive_transforms.items():
            for control_key in transform.compute_inputs.values():
                trigger_consumers.setdefault(control_key, []).append(
                    (transform_id, transform.trigger)
                )
        for control_key, consumers in trigger_consumers.items():
            triggers = {trigger for _, trigger in consumers}
            if len(triggers) > 1:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Compute Control {control_key} has consumers with incompatible "
                        f"triggers: {', '.join(sorted(triggers))}",
                        definition_path,
                        "controls",
                        "compute_trigger_ambiguous",
                        {
                            "control": control_key,
                            "consumers": [
                                {"transform": identifier, "trigger": trigger}
                                for identifier, trigger in consumers
                            ],
                        },
                    )
                )

        for view in dashboard.definition.views:
            for name, reference in view.input_refs.items():
                message = _reference_error(
                    reference,
                    sources=dashboard.sources,
                    dataset_transforms=dashboard.dataset_transforms,
                    interactive_transforms=dashboard.interactive_transforms,
                    allow_interactive=True,
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
                    output_definition = _reference_output_definition(
                        reference, dashboard
                    )
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
                    if (
                        output_kind == "table"
                        and output_definition is not None
                        and output_definition.schema_
                    ):
                        declared_fields = {
                            column.name for column in output_definition.schema_
                        }
                        unknown_fields = sorted(
                            referenced_view_fields(view) - declared_fields
                        )
                        if unknown_fields:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    f"View {view.id} references undeclared table fields: "
                                    + ", ".join(unknown_fields),
                                    definition_path,
                                    "views",
                                    "view_field_unknown",
                                    {
                                        "view": view.id,
                                        "reference": reference,
                                        "unknown": unknown_fields,
                                        "declared": sorted(declared_fields),
                                    },
                                )
                            )
                        selection_fields = {
                            field
                            for item in control_contract.get(view.id, [])
                            if item.kind == "selection" and item.binding is not None
                            for field in (
                                item.definition.path_fields
                                or [item.binding.field or item.id]
                            )
                        }
                        unknown_selection_fields = sorted(
                            selection_fields - declared_fields
                        )
                        if unknown_selection_fields:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    f"View {view.id} Selection contract references "
                                    "undeclared table fields: "
                                    + ", ".join(unknown_selection_fields),
                                    definition_path,
                                    "views.selection_bindings",
                                    "selection_field_unknown",
                                    {
                                        "view": view.id,
                                        "reference": reference,
                                        "unknown": unknown_selection_fields,
                                        "declared": sorted(declared_fields),
                                    },
                                )
                            )

        for reference in dashboard.definition.canvas.inputs:
            message = _reference_error(
                reference,
                sources=dashboard.sources,
                dataset_transforms=dashboard.dataset_transforms,
                interactive_transforms=dashboard.interactive_transforms,
                allow_interactive=True,
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
                        dataset_transforms=dashboard.dataset_transforms,
                        interactive_transforms=dashboard.interactive_transforms,
                        allow_interactive=True,
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
                    selection_ids = {
                        item.id
                        for item in section.controls
                        if item.kind == "selection"
                    }
                    if not selection_ids:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Section {section.id} selection-gallery requires a Section Control with kind=selection",
                                definition_path,
                                "sections.controls",
                            )
                        )
                    elif section.repeat.selection and section.repeat.selection not in selection_ids:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Section {section.id} repeat references an unknown Section Control with kind=selection",
                                definition_path,
                                "sections.repeat.selection",
                            )
                        )

        for view_id, controls in control_contract.items():
            ids = [item.id for item in controls]
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            if duplicates:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Control ids shadow each other for View {view_id}: {', '.join(duplicates)}",
                        definition_path,
                        "controls",
                    )
                )
            view = dashboard.views[view_id]
            selection_ids = {
                item.id for item in controls if item.kind == "selection"
            }
            for selection_id in sorted(
                set(view.selection_bindings) - selection_ids
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"View {view_id} binds unknown Selection: {selection_id}",
                        definition_path,
                        "selection_bindings",
                    )
                )

        canvas = dashboard.definition.canvas
        for field in ("template",):
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
                            "error",
                            f"Presentation asset does not exist: {value}",
                            str(dashboard.root / value),
                            f"canvas.{field}",
                            "presentation_asset_missing",
                        )
                    )
    return diagnostics


def dashboard_validation_diagnostics(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
) -> list[Diagnostic]:
    """Return global and dashboard-local diagnostics without leaking sibling failures."""
    other_roots = [
        entry.path.resolve()
        for entry in workspace.catalog
        if entry.path.resolve() != dashboard.root.resolve()
    ]
    selected: list[Diagnostic] = []
    for diagnostic in validate_workspace(workspace):
        if not diagnostic.file:
            selected.append(diagnostic)
            continue
        raw = Path(diagnostic.file).expanduser()
        path = raw.resolve() if raw.is_absolute() else (workspace.root / raw).resolve()
        if _is_within(path, dashboard.root):
            selected.append(diagnostic)
        elif not any(_is_within(path, root) for root in other_roots):
            selected.append(diagnostic)
    return selected
