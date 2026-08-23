from __future__ import annotations

from collections.abc import Iterable
import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dataviz.workspace.models import DashboardDefinition, ParameterDefinition


_TOKEN = re.compile(r"{{\s*(.*?)\s*}}", re.DOTALL)
_PARAMETER_EXPRESSION = re.compile(r"parameters\.([A-Za-z0-9_][A-Za-z0-9_.-]*)")


def content_template_fields(
    definition: DashboardDefinition,
) -> Iterable[tuple[str, str]]:
    """Yield declarative content fields that support Query Parameter interpolation."""
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


def inspect_parameter_template(value: str) -> tuple[set[str], list[str]]:
    """Return referenced IDs and syntax errors without evaluating content."""
    references: set[str] = set()
    errors: list[str] = []
    matches = list(_TOKEN.finditer(value))
    remainder = _TOKEN.sub("", value)
    if "{{" in remainder or "}}" in remainder:
        errors.append("Unclosed parameter interpolation")
    for match in matches:
        expression = match.group(1).strip()
        parsed = _PARAMETER_EXPRESSION.fullmatch(expression)
        if not parsed:
            errors.append(
                f"Unsupported interpolation expression: {expression or '<empty>'}; "
                "use {{ parameters.<id> }}"
            )
            continue
        references.add(parsed.group(1))
    return references, errors


def _choice_label(definition: ParameterDefinition, value: Any) -> str | None:
    for choice in definition.choices:
        if choice.value == value:
            return choice.label
    return None


def format_parameter_value(value: Any, definition: ParameterDefinition) -> str:
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
        return "、".join(
            _choice_label(definition, item) or str(item)
            for item in value
        )
    label = _choice_label(definition, value)
    if label is not None:
        return label
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return str(value)


def render_parameter_template(
    value: str,
    parameters: dict[str, Any],
    definitions: dict[str, ParameterDefinition],
) -> str:
    """Render the intentionally small ``{{ parameters.<id> }}`` content DSL."""
    references, errors = inspect_parameter_template(value)
    unknown = sorted(references - set(definitions))
    if unknown:
        errors.append(f"Unknown Query Parameter: {', '.join(unknown)}")
    if errors:
        raise ValueError("; ".join(errors))

    def replace(match: re.Match[str]) -> str:
        parameter_id = _PARAMETER_EXPRESSION.fullmatch(match.group(1).strip()).group(1)
        definition = definitions[parameter_id]
        resolved = parameters.get(parameter_id, definition.default)
        return format_parameter_value(resolved, definition)

    return _TOKEN.sub(replace, value)


def interpolate_dashboard_content(
    definition: DashboardDefinition,
    parameters: dict[str, Any] | None,
    *,
    fallback_title: str | None = None,
) -> DashboardDefinition:
    """Return a copy with only human-facing content fields interpolated."""
    definitions = {item.id: item for item in definition.query_parameters}
    values = parameters or {}

    def render(value: str) -> str:
        return render_parameter_template(value, values, definitions)

    sections = [
        section.model_copy(
            update={
                "title": render(section.title),
                "description": render(section.description),
            }
        )
        for section in definition.sections
    ]
    views = [
        view.model_copy(
            update={
                "title": render(view.title) if view.title is not None else None,
                "description": render(view.description),
                "text": render(view.text) if view.text is not None else None,
            }
        )
        for view in definition.views
    ]
    title = render(definition.title)
    return definition.model_copy(
        update={
            "title": title.strip() or fallback_title or "",
            "subtitle": render(definition.subtitle),
            "description": render(definition.description),
            "assumptions": [render(value) for value in definition.assumptions],
            "sections": sections,
            "views": views,
        }
    )


def default_parameter_values(definition: DashboardDefinition) -> dict[str, Any]:
    return {item.id: item.default for item in definition.query_parameters}
