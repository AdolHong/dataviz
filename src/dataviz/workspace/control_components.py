from __future__ import annotations

from typing import Any

from dataviz.value_contract import static_control_choices
from dataviz.workspace.models import PresentationControlComponentDefinition


CONTROL_COMPONENT_CONTRACTS: dict[str, frozenset[tuple[str, str]]] = {
    "input": frozenset({("single_input", "text")}),
    "multiple-input": frozenset(
        ("multiple_input", value_type)
        for value_type in {"text", "integer", "number", "date"}
    ),
    "input-number": frozenset(
        ("single_input", value_type) for value_type in {"number", "integer"}
    ),
    "auto-complete": frozenset({("single_input", "text")}),
    "checkbox": frozenset({("single_input", "boolean")}),
    "switch": frozenset({("single_input", "boolean")}),
    "radio-group": frozenset(
        ("single_select", value_type)
        for value_type in {"text", "integer", "number", "boolean", "date"}
    ),
    "select": frozenset(
        (shape, value_type)
        for shape in {"single_select", "multiple_select"}
        for value_type in {"text", "integer", "number", "boolean", "date"}
    ),
    "checkbox-group": frozenset(
        ("multiple_select", value_type)
        for value_type in {"text", "integer", "number", "boolean", "date"}
    ),
    "cascader": frozenset(
        (shape, value_type)
        for shape in {"single_select", "multiple_select"}
        for value_type in {"text", "integer", "number", "boolean", "date"}
    ),
    "date-picker": frozenset({("single_input", "date")}),
    "range-picker": frozenset({("range_input", "date")}),
    "slider": frozenset(
        (shape, value_type)
        for shape in {"single_input", "range_input"}
        for value_type in {"number", "integer"}
    ),
    "tree-select": frozenset(
        (shape, value_type)
        for shape in {"single_select", "multiple_select"}
        for value_type in {"text", "integer", "number", "boolean", "date"}
    ),
}


def _auto_component(definition: Any) -> tuple[str, str]:
    control_type = definition.type
    value_type = definition.value_type
    path_fields = getattr(definition, "path_fields", []) or []
    choices = static_control_choices(definition)
    suggestions = getattr(definition, "suggestions", []) or []
    if path_fields:
        return "cascader", "hierarchical_path"
    if control_type == "range_input" and value_type == "date":
        return "range-picker", "date_range_input"
    if control_type == "range_input":
        return "slider", "numeric_range"
    if control_type == "single_input" and value_type == "date":
        return "date-picker", "date"
    if control_type == "multiple_input":
        return "multiple-input", "multiple_values"
    if control_type == "single_input" and value_type in {"number", "integer"}:
        return "input-number", "numeric"
    if control_type == "single_input" and value_type == "boolean":
        return "checkbox", "boolean"
    if control_type == "single_input" and value_type == "text":
        return ("auto-complete", "suggestions") if suggestions else ("input", "free_text")
    # A radio group has no honest empty-state interaction. Optional clearable
    # singles therefore resolve to Select even for a tiny static domain.
    if (
        control_type == "single_select"
        and not bool(getattr(definition, "clearable", False))
        and 0 < len(choices) <= 4
    ):
        return "radio-group", "small_single_select"
    if control_type == "multiple_select" and 2 <= len(choices) <= 5:
        return "checkbox-group", "small_multiple_select"
    return "select", "flat_select"


def resolve_control_component(
    definition: Any,
    configured: PresentationControlComponentDefinition | None = None,
) -> dict[str, Any]:
    """Resolve one component without changing the control's value semantics."""

    presentation = configured or PresentationControlComponentDefinition()
    result = presentation.model_dump(mode="json")
    requested = result.pop("component")
    if requested == "auto":
        component, reason = _auto_component(definition)
    else:
        component, reason = requested, "explicit"
    contract = (definition.type, definition.value_type)
    if contract not in CONTROL_COMPONENT_CONTRACTS[component]:
        supported = ", ".join(
            f"{shape}/{value_type}"
            for shape, value_type in sorted(CONTROL_COMPONENT_CONTRACTS[component])
        )
        raise ValueError(
            f"{component} cannot render control contract "
            f"{definition.type}/{definition.value_type}; supported contracts: {supported}"
        )
    path_fields = getattr(definition, "path_fields", []) or []
    if component in {"cascader", "tree-select"} and not path_fields:
        raise ValueError(f"{component} requires path_fields")
    if component not in {"cascader", "tree-select"} and path_fields:
        raise ValueError(
            f"controls with path_fields require cascader or tree-select, received {component}"
        )
    if component == "auto-complete" and not getattr(definition, "suggestions", []):
        raise ValueError("auto-complete requires suggestions")
    if component == "radio-group" and bool(getattr(definition, "clearable", False)):
        raise ValueError(
            "radio-group cannot render clearable single_select; use component=select"
        )
    result.update(
        {
            "component": component,
            "requested_component": requested,
            "auto_reason": reason,
        }
    )
    return result
