from __future__ import annotations

from typing import Any

from dataviz.workspace.models import PresentationSelectorDefinition


def resolve_selector_presentation(
    definition: Any,
    selector: PresentationSelectorDefinition | None = None,
) -> dict[str, Any]:
    """Resolve one deterministic presentation without changing Selection semantics."""

    configured = selector or PresentationSelectorDefinition()
    result = configured.model_dump(mode="json")
    requested = result["template"]
    reason = "explicit"
    if requested == "auto":
        selection_type = getattr(definition, "type", "string")
        path_fields = getattr(definition, "path_fields", []) or []
        choice_count = len(getattr(definition, "choices", []) or [])
        if selection_type == "date_range":
            template = "date-range"
            reason = "date_range"
        elif path_fields:
            template = "cascader"
            reason = "hierarchical_path"
        elif selection_type == "boolean":
            template = "segmented"
            reason = "boolean_three_state"
        elif selection_type == "single_select" and 0 < choice_count <= 4:
            template = "segmented"
            reason = "small_single_select"
        elif selection_type == "multi_select" and 0 < choice_count <= 8:
            template = "checkbox-group"
            reason = "small_multi_select"
        else:
            template = "select"
            reason = "flat_select"
        result["template"] = template
    result["requested_template"] = requested
    result["auto_reason"] = reason
    return result
