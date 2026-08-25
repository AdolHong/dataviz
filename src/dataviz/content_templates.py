from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
import re
from typing import TYPE_CHECKING, Any, Literal

from dataviz.value_contract import static_control_choices
from dataviz.workspace.controls import canonical_control_key

if TYPE_CHECKING:
    from dataviz.workspace.models import (
        DashboardDefinition,
        QueryParameterDefinition,
        ScopedControlDefinition,
        SelectionControlDefinition,
    )


_TOKEN = re.compile(r"{{\s*(.*?)\s*}}", re.DOTALL)
_PARAMETER_EXPRESSION = re.compile(r"parameters\.([A-Za-z0-9_][A-Za-z0-9_.-]*)")
_CONTENT_ID = r"[A-Za-z0-9_][A-Za-z0-9_-]*"
_DASHBOARD_CONTROL_EXPRESSION = re.compile(
    rf"controls\.(dashboard)\.({_CONTENT_ID})"
)
_SCOPED_CONTROL_EXPRESSION = re.compile(
    rf"controls\.(section|view)\.({_CONTENT_ID})\.({_CONTENT_ID})"
)

SelectionOrigin = Literal["dashboard", "section", "view"]


@dataclass(frozen=True, slots=True)
class ContentTemplateInspection:
    query_parameters: frozenset[str]
    controls: frozenset[str]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContentControl:
    expression: str
    key: str
    origin: SelectionOrigin
    owner_id: str
    control_id: str
    definition: ScopedControlDefinition


def content_template_fields(
    definition: DashboardDefinition,
) -> Iterable[tuple[str, str]]:
    """Yield declarative human-facing fields supported by the content DSL."""
    for field in ("title", "subtitle", "description"):
        yield field, getattr(definition, field)
    for index, value in enumerate(definition.assumptions):
        yield f"assumptions[{index}]", value
    for section in definition.sections:
        yield f"sections.{section.id}.title", section.title
        yield f"sections.{section.id}.description", section.description
    for view in definition.views:
        if view.title is not None:
            yield f"views.{view.id}.title", view.title
        yield f"views.{view.id}.description", view.description
        if view.text is not None:
            yield f"views.{view.id}.text", view.text


def inspect_content_template(value: str) -> ContentTemplateInspection:
    """Inspect the deliberately small content DSL without evaluating it."""
    query_parameters: set[str] = set()
    controls: set[str] = set()
    errors: list[str] = []
    matches = list(_TOKEN.finditer(value))
    remainder = _TOKEN.sub("", value)
    if "{{" in remainder or "}}" in remainder:
        errors.append("Unclosed content interpolation")
    for match in matches:
        expression = match.group(1).strip()
        parameter = _PARAMETER_EXPRESSION.fullmatch(expression)
        if parameter:
            query_parameters.add(parameter.group(1))
            continue
        if _parse_control_expression(expression):
            controls.add(expression)
            continue
        errors.append(
            f"Unsupported interpolation expression: {expression or '<empty>'}; "
            "use {{ parameters.<id> }}, {{ controls.dashboard.<id> }}, "
            "{{ controls.section.<section-id>.<id> }}, or "
            "{{ controls.view.<view-id>.<id> }}"
        )
    return ContentTemplateInspection(
        query_parameters=frozenset(query_parameters),
        controls=frozenset(controls),
        errors=tuple(errors),
    )


def _parse_control_expression(
    expression: str,
) -> tuple[SelectionOrigin, str | None, str] | None:
    dashboard = _DASHBOARD_CONTROL_EXPRESSION.fullmatch(expression)
    if dashboard:
        return "dashboard", None, dashboard.group(2)
    scoped = _SCOPED_CONTROL_EXPRESSION.fullmatch(expression)
    if scoped:
        return scoped.group(1), scoped.group(2), scoped.group(3)
    return None


def content_control_contract(
    definition: DashboardDefinition,
) -> dict[str, ContentControl]:
    """Return stable content expressions and canonical scoped Control keys."""
    contract: dict[str, ContentControl] = {}
    for control in definition.controls:
        expression = f"controls.dashboard.{control.id}"
        contract[expression] = ContentControl(
            expression=expression,
            key=canonical_control_key("dashboard", definition.id, control.id),
            origin="dashboard",
            owner_id=definition.id,
            control_id=control.id,
            definition=control,
        )
    for section in definition.sections:
        for control in section.controls:
            expression = f"controls.section.{section.id}.{control.id}"
            contract[expression] = ContentControl(
                expression=expression,
                key=canonical_control_key("section", section.id, control.id),
                origin="section",
                owner_id=section.id,
                control_id=control.id,
                definition=control,
            )
    for view in definition.views:
        for control in view.controls:
            expression = f"controls.view.{view.id}.{control.id}"
            contract[expression] = ContentControl(
                expression=expression,
                key=canonical_control_key("view", view.id, control.id),
                origin="view",
                owner_id=view.id,
                control_id=control.id,
                definition=control,
            )
    return contract


def allowed_content_controls(
    definition: DashboardDefinition,
    field: str,
) -> set[str]:
    """Limit content dependencies to Control scopes visible at that field."""
    contract = content_control_contract(definition)
    allowed = {
        expression
        for expression, control in contract.items()
        if control.origin == "dashboard"
    }
    section = next(
        (
            item
            for item in definition.sections
            if field in {
                f"sections.{item.id}.title",
                f"sections.{item.id}.description",
            }
        ),
        None,
    )
    if section:
        allowed.update(
            expression
            for expression, control in contract.items()
            if control.origin == "section" and control.owner_id == section.id
        )
        return allowed
    view = next(
        (
            item
            for item in definition.views
            if field in {
                f"views.{item.id}.title",
                f"views.{item.id}.description",
                f"views.{item.id}.text",
            }
        ),
        None,
    )
    if not view:
        return allowed
    allowed.update(
        expression
        for expression, control in contract.items()
        if control.origin == "view" and control.owner_id == view.id
    )
    owner = next(
        (item for item in definition.sections if view.id in item.views),
        None,
    )
    if owner:
        allowed.update(
            expression
            for expression, control in contract.items()
            if control.origin == "section" and control.owner_id == owner.id
        )
    return allowed


def content_binding_target(
    definition: DashboardDefinition,
    field: str,
) -> dict[str, Any]:
    """Describe the semantic content node without making the browser parse IDs."""
    if field in {"title", "subtitle", "description"}:
        return {"scope": "dashboard", "property": field}
    assumption = re.fullmatch(r"assumptions\[(\d+)]", field)
    if assumption:
        return {
            "scope": "dashboard",
            "property": "assumption",
            "index": int(assumption.group(1)),
        }
    for section in definition.sections:
        for property_name in ("title", "description"):
            if field == f"sections.{section.id}.{property_name}":
                return {
                    "scope": "section",
                    "owner_id": section.id,
                    "property": property_name,
                }
    for view in definition.views:
        for property_name in ("title", "description", "text"):
            if field == f"views.{view.id}.{property_name}":
                return {
                    "scope": "view",
                    "owner_id": view.id,
                    "property": property_name,
                }
    raise ValueError(f"Unsupported content field: {field}")


def _choice_label(
    definition: QueryParameterDefinition | ScopedControlDefinition,
    value: Any,
) -> str | None:
    for choice in static_control_choices(definition):
        if choice.value == value or str(choice.value) == str(value):
            return choice.label
    return None


def _format_sequence(
    value: Iterable[Any],
    definition: QueryParameterDefinition | ScopedControlDefinition,
) -> str:
    return "、".join(
        _choice_label(definition, item) or str(item)
        for item in value
    )


def format_parameter_value(
    value: Any,
    definition: QueryParameterDefinition | ScopedControlDefinition,
) -> str:
    """Format committed Query Parameter values for human-facing content."""
    if value is None:
        return ""
    if definition.type == "date_range":
        items = value.split(",", 1) if isinstance(value, str) else value
        if isinstance(items, (list, tuple)):
            return " 至 ".join(
                str(item) for item in items if item is not None and item != ""
            )
    if definition.type == "multi_select" and isinstance(value, str):
        value = [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return _format_sequence(value, definition)
    label = _choice_label(definition, value)
    if label is not None:
        return label
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return str(value)


def format_selection_value(value: Any, definition: SelectionControlDefinition) -> str:
    """Format browser Selection state as compact human-facing context."""
    if value is None or value == "" or value == []:
        return "全部"
    if definition.type == "date_range":
        items = value.split(",", 1) if isinstance(value, str) else value
        if isinstance(items, (list, tuple)):
            return " 至 ".join(
                str(item) for item in items if item is not None and item != ""
            )
    if definition.path_fields:
        paths = (
            value
            if isinstance(value, list) and value and isinstance(value[0], list)
            else [value]
        )
        return "、".join(
            " / ".join(str(item) for item in path)
            for path in paths
            if isinstance(path, (list, tuple))
        )
    if definition.type == "multi_select" and isinstance(value, str):
        value = [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        choices = static_control_choices(definition)
        if choices and len(items) == len(choices) and all(
            any(
                choice.value == item or str(choice.value) == str(item)
                for choice in choices
            )
            for item in items
        ):
            return "全部"
        return _format_sequence(items, definition)
    return format_parameter_value(value, definition)


def render_content_template(
    value: str,
    definition: DashboardDefinition,
    query_parameters: dict[str, Any] | None = None,
    compute_parameters: dict[str, Any] | None = None,
    selections: dict[str, Any] | None = None,
    *,
    field: str | None = None,
    preserve_dynamic: bool = False,
) -> str:
    """Render the safe Parameter and Selection content DSL."""
    inspection = inspect_content_template(value)
    parameter_definitions = {item.id: item for item in definition.query_parameters}
    control_contract = content_control_contract(definition)
    errors = list(inspection.errors)
    unknown_parameters = sorted(
        inspection.query_parameters - set(parameter_definitions)
    )
    if unknown_parameters:
        errors.append(f"Unknown Query Parameter: {', '.join(unknown_parameters)}")
    unknown_controls = sorted(inspection.controls - set(control_contract))
    if unknown_controls:
        errors.append(f"Unknown Control: {', '.join(unknown_controls)}")
    if field:
        out_of_scope = sorted(
            (inspection.controls & set(control_contract))
            - allowed_content_controls(definition, field)
        )
        if out_of_scope:
            errors.append(
                f"Control is outside the content scope: {', '.join(out_of_scope)}"
            )
    if errors:
        raise ValueError("; ".join(errors))

    parameter_values = query_parameters or {}
    compute_values = compute_parameters or {}
    selection_values = selections or {}

    def replace(match: re.Match[str]) -> str:
        expression = match.group(1).strip()
        parameter = _PARAMETER_EXPRESSION.fullmatch(expression)
        if parameter:
            parameter_id = parameter.group(1)
            parameter_definition = parameter_definitions[parameter_id]
            resolved = parameter_values.get(parameter_id, parameter_definition.default)
            return format_parameter_value(resolved, parameter_definition)
        control = control_contract[expression]
        if preserve_dynamic:
            return f"{{{{ {expression} }}}}"
        values = (
            selection_values
            if control.definition.kind == "selection"
            else compute_values
        )
        resolved = values.get(control.key, control.definition.default)
        if control.definition.kind == "selection":
            return format_selection_value(resolved, control.definition)
        return format_parameter_value(resolved, control.definition)

    return _TOKEN.sub(replace, value)


def build_content_bindings(
    definition: DashboardDefinition,
    query_parameters: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Compile Selection/Compute-dependent content into a runtime manifest."""
    contract = content_control_contract(definition)
    bindings: dict[str, dict[str, Any]] = {}
    for field, value in content_template_fields(definition):
        inspection = inspect_content_template(value)
        if not inspection.controls:
            continue
        template = render_content_template(
            value,
            definition,
            query_parameters,
            field=field,
            preserve_dynamic=True,
        )
        references = []
        for expression in sorted(inspection.controls):
            control = contract[expression]
            references.append(
                {
                    "expression": expression,
                    "key": control.key,
                    "kind": control.definition.kind,
                    "origin": control.origin,
                    "owner_id": control.owner_id,
                    "control_id": control.control_id,
                    "definition": control.definition.model_dump(mode="json"),
                }
            )
        bindings[field] = {
            "template": template,
            "references": references,
            "target": content_binding_target(definition, field),
        }
    return bindings


def interpolate_dashboard_content(
    definition: DashboardDefinition,
    query_parameters: dict[str, Any] | None,
    compute_parameters: dict[str, Any] | None = None,
    selections: dict[str, Any] | None = None,
    *,
    fallback_title: str | None = None,
) -> DashboardDefinition:
    """Return a copy with safe human-facing content fields interpolated."""
    parameter_values = query_parameters or {}
    compute_values = compute_parameters or {}
    selection_values = selections or {}

    def render(value: str, field: str) -> str:
        return render_content_template(
            value,
            definition,
            parameter_values,
            compute_values,
            selection_values,
            field=field,
        )

    sections = [
        section.model_copy(
            update={
                "title": render(section.title, f"sections.{section.id}.title"),
                "description": render(
                    section.description, f"sections.{section.id}.description"
                ),
            }
        )
        for section in definition.sections
    ]
    views = [
        view.model_copy(
            update={
                "title": (
                    render(view.title, f"views.{view.id}.title")
                    if view.title is not None
                    else None
                ),
                "description": render(
                    view.description, f"views.{view.id}.description"
                ),
                "text": (
                    render(view.text, f"views.{view.id}.text")
                    if view.text is not None
                    else None
                ),
            }
        )
        for view in definition.views
    ]
    title = render(definition.title, "title")
    return definition.model_copy(
        update={
            "title": title.strip() or fallback_title or "",
            "subtitle": render(definition.subtitle, "subtitle"),
            "description": render(definition.description, "description"),
            "assumptions": [
                render(value, f"assumptions[{index}]")
                for index, value in enumerate(definition.assumptions)
            ],
            "sections": sections,
            "views": views,
        }
    )
