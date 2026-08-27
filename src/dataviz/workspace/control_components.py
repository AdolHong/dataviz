from __future__ import annotations

from typing import Any

from dataviz.value_contract import static_control_choices
from dataviz.workspace.models import PresentationControlComponentDefinition


CONTROL_COMPONENT_TYPES: dict[str, frozenset[str]] = {
    "input": frozenset({"string"}),
    "input-number": frozenset({"number", "integer"}),
    "auto-complete": frozenset({"string"}),
    "checkbox": frozenset({"boolean"}),
    "switch": frozenset({"boolean"}),
    "radio-group": frozenset({"single_select"}),
    "select": frozenset({"single_select", "multi_select"}),
    "checkbox-group": frozenset({"multi_select"}),
    "cascader": frozenset({"single_select", "multi_select"}),
    "date-picker": frozenset({"date"}),
    "range-picker": frozenset({"date_range"}),
    "slider": frozenset({"number", "integer"}),
    "tree-select": frozenset({"single_select", "multi_select"}),
}


def _auto_component(definition: Any) -> tuple[str, str]:
    value_type = getattr(definition, "type", "string")
    path_fields = getattr(definition, "path_fields", []) or []
    choices = static_control_choices(definition)
    suggestions = getattr(definition, "suggestions", []) or []
    if path_fields:
        return "cascader", "hierarchical_path"
    if value_type == "date_range":
        return "range-picker", "date_range"
    if value_type == "date":
        return "date-picker", "date"
    if value_type in {"number", "integer"}:
        return "input-number", "numeric"
    if value_type == "boolean":
        return "checkbox", "boolean"
    if value_type == "string":
        return ("auto-complete", "suggestions") if suggestions else ("input", "free_text")
    # A radio group has no honest empty-state interaction. Optional clearable
    # singles therefore resolve to Select even for a tiny static domain.
    if (
        value_type == "single_select"
        and not bool(getattr(definition, "clearable", False))
        and 0 < len(choices) <= 4
    ):
        return "radio-group", "small_single_select"
    if value_type == "multi_select" and 0 < len(choices) <= 8:
        return "checkbox-group", "small_multi_select"
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
    value_type = getattr(definition, "type", "string")
    if value_type not in CONTROL_COMPONENT_TYPES[component]:
        supported = ", ".join(sorted(CONTROL_COMPONENT_TYPES[component]))
        raise ValueError(
            f"{component} cannot render control type {value_type}; supported types: {supported}"
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
