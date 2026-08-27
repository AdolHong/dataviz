from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from dataviz.errors import ExecutionFailure
from dataviz.value_contract import (
    ValueContractViolation,
    is_empty_control_value,
    normalize_control_value,
)
from dataviz.workspace.models import (
    InferredOptionDomainDefinition,
    SelectionControlDefinition,
)


SelectionIntent = Literal["all_available", "explicit"]
SelectionStatePayload = dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ResolvedSelection:
    """One canonical Selection value.

    ``values`` is always a collection of logical selections.  A scalar Control
    therefore has zero or one item; a date range has one two-item range; and a
    multi-select has zero or more items.  Keeping emptiness unambiguous is the
    reason this type exists: ``explicit + []`` means no rows, never "All".
    """

    intent: SelectionIntent
    values: tuple[Any, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"intent": self.intent, "values": list(self.values)}


def _logical_values(
    definition: SelectionControlDefinition,
    normalized: Any,
) -> list[Any]:
    if is_empty_control_value(normalized):
        return []
    if definition.type == "multi_select":
        return list(normalized)
    if definition.type == "date_range":
        return [list(normalized)]
    return [normalized]


def project_selection_value(
    definition: SelectionControlDefinition,
    state: Mapping[str, Any] | ResolvedSelection,
) -> Any:
    """Project canonical Selection state into the value exposed to user code."""

    values = list(state.values if isinstance(state, ResolvedSelection) else state.get("values", []))
    if definition.type == "multi_select":
        return values
    if definition.type == "date_range":
        return list(values[0]) if values else []
    return values[0] if values else None


def explicit_selection_state(
    definition: SelectionControlDefinition,
    value: Any,
    *,
    enforce_required: bool = True,
) -> ResolvedSelection:
    try:
        normalized = normalize_control_value(
            definition,
            value,
            enforce_required=enforce_required,
        )
    except ValueContractViolation as error:
        raise ExecutionFailure(
            f"Invalid Selection value: {error.message}",
            details={"code": f"selection_control_{error.code}", "reason": error.message},
        ) from error
    return ResolvedSelection("explicit", tuple(_logical_values(definition, normalized)))


def initial_selection_state(
    definition: SelectionControlDefinition,
    *,
    allow_unresolved_inferred: bool = False,
) -> ResolvedSelection:
    intent: SelectionIntent = (
        "all_available"
        if definition.type == "multi_select"
        and isinstance(definition.options, InferredOptionDomainDefinition)
        and definition.options.initial == "auto"
        else "explicit"
    )
    enforce_required = not (
        allow_unresolved_inferred
        and isinstance(definition.options, InferredOptionDomainDefinition)
    )
    state = explicit_selection_state(
        definition,
        definition.default,
        enforce_required=enforce_required,
    )
    return ResolvedSelection(intent, state.values)


def normalize_selection_state_entry(
    definition: SelectionControlDefinition,
    payload: Mapping[str, Any],
    *,
    allow_unresolved_inferred: bool = False,
) -> ResolvedSelection:
    if set(payload) != {"intent", "values"}:
        raise ExecutionFailure(
            "Selection state must contain exactly intent and values",
            details={
                "code": "selection_state_shape_invalid",
                "fields": sorted(str(value) for value in payload),
            },
        )
    intent = payload.get("intent")
    if intent not in {"all_available", "explicit"}:
        raise ExecutionFailure(
            "Selection intent must be all_available or explicit",
            details={"code": "selection_intent_invalid", "intent": intent},
        )
    if intent == "all_available" and definition.type != "multi_select":
        raise ExecutionFailure(
            "all_available is only valid for multi_select",
            details={"code": "selection_intent_cardinality_invalid"},
        )
    values = payload.get("values")
    if not isinstance(values, list):
        raise ExecutionFailure(
            "Selection state values must be a list",
            details={"code": "selection_state_values_invalid"},
        )

    if definition.type == "multi_select":
        projected = values
    elif definition.type == "date_range":
        if len(values) > 1:
            raise ExecutionFailure(
                "date_range Selection state contains more than one range",
                details={"code": "selection_state_cardinality_invalid"},
            )
        projected = values[0] if values else []
    else:
        if len(values) > 1:
            raise ExecutionFailure(
                "Single-value Selection state contains more than one value",
                details={"code": "selection_state_cardinality_invalid"},
            )
        projected = values[0] if values else None

    unresolved = (
        allow_unresolved_inferred
        and isinstance(definition.options, InferredOptionDomainDefinition)
        and not values
    )
    normalized = explicit_selection_state(
        definition,
        projected,
        enforce_required=not unresolved,
    )
    return ResolvedSelection(intent, normalized.values)


def resolve_selection_state(
    dashboard,
    provided: Mapping[str, Mapping[str, Any]] | None,
    *,
    phase: Literal["execution", "canvas-hydration"] = "execution",
) -> SelectionStatePayload:
    # Imported lazily to keep the model/control modules acyclic.
    from dataviz.workspace.controls import scoped_control_registry

    registry = scoped_control_registry(dashboard, kind="selection")
    supplied = dict(provided or {})
    unknown = sorted(set(supplied) - set(registry))
    if unknown:
        raise ExecutionFailure(
            "Unknown Selection Control key",
            details={"code": "selection_control_unknown", "keys": unknown},
        )
    allow_unresolved = phase == "canvas-hydration"
    resolved: SelectionStatePayload = {}
    for key, control in registry.items():
        definition = control.definition
        assert isinstance(definition, SelectionControlDefinition)
        try:
            state = (
                normalize_selection_state_entry(
                    definition,
                    supplied[key],
                    allow_unresolved_inferred=allow_unresolved,
                )
                if key in supplied
                else initial_selection_state(
                    definition,
                    allow_unresolved_inferred=allow_unresolved,
                )
            )
        except ExecutionFailure as error:
            details = dict(error.details or {}) if isinstance(error.details, dict) else {}
            details.setdefault("key", key)
            raise ExecutionFailure(
                f"Invalid Selection Control {key}: {error.message}",
                details=details,
            ) from error
        resolved[key] = state.as_dict()
    return resolved


def selection_values(
    dashboard,
    state: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    from dataviz.workspace.controls import scoped_control_registry

    registry = scoped_control_registry(dashboard, kind="selection")
    return {
        key: project_selection_value(control.definition, state[key])
        for key, control in registry.items()
        if key in state
    }


def state_from_explicit_values(
    dashboard,
    values: Mapping[str, Any] | None,
    *,
    phase: Literal["execution", "canvas-hydration"] = "execution",
) -> SelectionStatePayload:
    """CLI/authoring helper; external Runtime APIs use ``selection_state`` only."""

    from dataviz.workspace.controls import scoped_control_registry

    registry = scoped_control_registry(dashboard, kind="selection")
    unknown = sorted(set(values or {}) - set(registry))
    if unknown:
        raise ExecutionFailure(
            "Unknown Selection Control key",
            details={"code": "selection_control_unknown", "keys": unknown},
        )
    payload: SelectionStatePayload = {}
    for key, control in registry.items():
        definition = control.definition
        assert isinstance(definition, SelectionControlDefinition)
        if values is not None and key in values:
            payload[key] = explicit_selection_state(definition, values[key]).as_dict()
        else:
            payload[key] = initial_selection_state(
                definition,
                allow_unresolved_inferred=phase == "canvas-hydration",
            ).as_dict()
    return payload
