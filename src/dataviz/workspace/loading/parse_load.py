"""YAML/schema parsing and one-Dashboard loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import ValidationError

from dataviz.errors import Diagnostic, WorkspaceError
from dataviz.workspace.models import (
    DashboardDefinition,
    DatasetTransformDefinition,
    DeclarativeViewDefinition,
    InteractiveTransformDefinition,
    ParameterDomainDefinition,
    PresentationDefinition,
    SOURCE_DEFINITION_ADAPTER,
    SourceDefinition,
)
from dataviz.workspace.controls import compile_control_contract
from dataviz.workspace.control_components import resolve_control_component
from dataviz.view_contracts import validate_view_contract

from dataviz.workspace.loading.asset_validation import _is_within
from dataviz.workspace.loading.loaded_types import LoadedDashboard


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
                "expected": "dataviz/source/v3",
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
    parameter_domains: dict[str, tuple[Path, ParameterDomainDefinition]] = {}
    dataset_transforms: dict[str, tuple[Path, DatasetTransformDefinition]] = {}
    interactive_transforms: dict[str, tuple[Path, InteractiveTransformDefinition]] = {}

    for domain_entry in definition.parameter_domains:
        if isinstance(domain_entry, str):
            domain_path = _require_dashboard_asset(
                root, root, domain_entry, "Parameter Domain definition"
            )
            domain = parse_model(ParameterDomainDefinition, domain_path)
        else:
            domain_path = definition_path
            try:
                domain = ParameterDomainDefinition.model_validate(
                    {"schema": "dataviz/parameter-domain/v1", **domain_entry}
                )
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline Parameter Domain schema validation failed",
                    file=definition_path,
                    details=_validation_errors(exc),
                ) from exc
        if domain.id in parameter_domains:
            raise WorkspaceError(
                f"Duplicate Parameter Domain id: {domain.id}", file=domain_path
            )
        _require_dashboard_asset(
            root, domain_path.parent, domain.code, "Parameter Domain SQL"
        )
        parameter_domains[domain.id] = (domain_path, domain)

    for source_entry in definition.sources:
        if isinstance(source_entry, str):
            source_path = _require_dashboard_asset(root, root, source_entry, "Source definition")
            source = parse_source_definition(source_path)
        else:
            source_path = definition_path
            try:
                source = SOURCE_DEFINITION_ADAPTER.validate_python(
                    {"schema": "dataviz/source/v3", **source_entry}
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
            _require_dashboard_asset(root, source_path.parent, source_data_path, "Source path")
        if source_code_path:
            _require_dashboard_asset(root, source_path.parent, source_code_path, "Source code")
        for dependency in getattr(source, "code_dependencies", []):
            _require_dashboard_asset(root, source_path.parent, dependency, "Source code dependency")
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
                    {"schema": "dataviz/dataset-transform/v3", **transform_entry}
                )
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline Dataset Transform schema validation failed",
                    file=definition_path,
                    details=_validation_errors(exc),
                ) from exc
        if transform.id in dataset_transforms:
            raise WorkspaceError(
                f"Duplicate Dataset Transform id: {transform.id}", file=transform_path
            )
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
                    {"schema": "dataviz/interactive-transform/v4", **transform_entry}
                )
            except ValidationError as exc:
                raise WorkspaceError(
                    "Inline Interactive Transform schema validation failed",
                    file=definition_path,
                    details=_validation_errors(exc),
                ) from exc
        if transform.id in interactive_transforms:
            raise WorkspaceError(
                f"Duplicate Interactive Transform id: {transform.id}", file=transform_path
            )
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
        parameter_domains=parameter_domains,
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
    return " ".join(
        dict.fromkeys(part for value in (current, *values) for part in value.split() if part)
    )


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

    control_definitions = {f"query:{item.id}": item for item in logic.query_parameters}
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
        if "css_class" in override.model_fields_set:
            replacement = section.model_copy(
                update={
                    "css_class": _append_css_class(
                        section.css_class,
                        override.css_class,
                    )
                }
            )
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
        canvas_update["styles"] = list(dict.fromkeys([*effective.canvas.styles, *safe_css]))
    if safe_js:
        canvas_update["scripts"] = list(dict.fromkeys([*effective.canvas.scripts, *safe_js]))
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
