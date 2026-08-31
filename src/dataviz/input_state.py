from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from dataviz.errors import ExecutionFailure
from dataviz.value_contract import (
    ValueContractViolation,
    initial_control_value,
    is_empty_control_value,
    normalize_control_value,
    select_initial_contract,
)
from dataviz.workspace.models import ControlDefinition, InferredOptionDomainDefinition


CandidateIntent = Literal["all_available", "explicit"]
ControlStatePayload = dict[str, dict[str, Any]]


def candidate_backed_set(definition: Any) -> bool:
    return definition.type == "multiple_select"


@dataclass(frozen=True, slots=True)
class ResolvedInputState:
    value: Any
    revision: int = 0
    intent: CandidateIntent | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "revision": self.revision,
            **({"intent": self.intent} if self.intent is not None else {}),
        }


def _normalize_value(
    definition: ControlDefinition,
    value: Any,
    *,
    enforce_required: bool,
) -> Any:
    try:
        return normalize_control_value(
            definition,
            value,
            enforce_required=enforce_required,
        )
    except ValueContractViolation as error:
        raise ExecutionFailure(
            f"Invalid Control value: {error.message}",
            details={"code": f"control_state_{error.code}", "reason": error.message},
        ) from error


def initial_input_state(
    definition: ControlDefinition,
    *,
    allow_unresolved_inferred: bool = False,
) -> ResolvedInputState:
    unresolved = (
        allow_unresolved_inferred
        and isinstance(definition.options, InferredOptionDomainDefinition)
    )
    value = _normalize_value(
        definition,
        initial_control_value(definition),
        enforce_required=not unresolved,
    )
    intent: CandidateIntent | None = None
    if candidate_backed_set(definition):
        policy = select_initial_contract(definition)
        intent = "all_available" if policy["mode"] == "all" else "explicit"
    return ResolvedInputState(value=value, intent=intent)


def normalize_input_state_entry(
    definition: ControlDefinition,
    payload: Mapping[str, Any],
    *,
    allow_unresolved_inferred: bool = False,
) -> ResolvedInputState:
    allowed = {"value", "intent", "revision"}
    unknown = sorted(set(payload) - allowed)
    if unknown or "value" not in payload:
        raise ExecutionFailure(
            "Control state must contain value and optional intent/revision",
            details={
                "code": "control_state_shape_invalid",
                "unknown": unknown,
                "missing": [] if "value" in payload else ["value"],
            },
        )
    revision = payload.get("revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ExecutionFailure(
            "Control state revision must be a non-negative integer",
            details={"code": "control_state_revision_invalid", "revision": revision},
        )
    intent = payload.get("intent")
    if candidate_backed_set(definition):
        if intent is None:
            intent = "explicit"
        if intent not in {"all_available", "explicit"}:
            raise ExecutionFailure(
                "Candidate-backed Control intent must be all_available or explicit",
                details={"code": "control_state_intent_invalid", "intent": intent},
            )
    elif intent is not None:
        raise ExecutionFailure(
            "Only multiple_select Control state may declare intent",
            details={"code": "control_state_intent_not_applicable"},
        )
    unresolved = (
        allow_unresolved_inferred
        and isinstance(definition.options, InferredOptionDomainDefinition)
        and is_empty_control_value(payload.get("value"))
    )
    value = _normalize_value(
        definition,
        payload.get("value"),
        enforce_required=not unresolved,
    )
    return ResolvedInputState(value=value, intent=intent, revision=revision)


def resolve_control_state(
    dashboard: Any,
    provided: Mapping[str, Mapping[str, Any]] | None,
    *,
    phase: Literal["execution", "canvas-hydration"] = "execution",
) -> ControlStatePayload:
    from dataviz.workspace.controls import scoped_control_registry

    registry = scoped_control_registry(dashboard)
    supplied = dict(provided or {})
    unknown = sorted(set(supplied) - set(registry))
    if unknown:
        raise ExecutionFailure(
            "Unknown Control key",
            details={"code": "control_state_unknown", "keys": unknown},
        )
    allow_unresolved = phase == "canvas-hydration"
    resolved: ControlStatePayload = {}
    for key, control in registry.items():
        try:
            entry = (
                normalize_input_state_entry(
                    control.definition,
                    supplied[key],
                    allow_unresolved_inferred=allow_unresolved,
                )
                if key in supplied
                else initial_input_state(
                    control.definition,
                    allow_unresolved_inferred=allow_unresolved,
                )
            )
        except ExecutionFailure as error:
            details = dict(error.details or {}) if isinstance(error.details, dict) else {}
            details.setdefault("key", key)
            raise ExecutionFailure(
                f"Invalid Control {key}: {error.message}",
                details=details,
            ) from error
        resolved[key] = entry.as_dict()
    return resolved


def control_values(
    dashboard: Any,
    state: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    from dataviz.workspace.controls import scoped_control_registry

    registry = scoped_control_registry(dashboard)
    return {
        key: state[key].get("value")
        for key in registry
        if key in state
    }


def state_from_values(
    dashboard: Any,
    values: Mapping[str, Any],
    *,
    phase: Literal["execution", "canvas-hydration"] = "execution",
) -> ControlStatePayload:
    """Build canonical state from concise CLI key/value overrides."""

    from dataviz.workspace.controls import scoped_control_registry

    registry = scoped_control_registry(dashboard)
    unknown = sorted(set(values) - set(registry))
    if unknown:
        raise ExecutionFailure(
            "Unknown Control key",
            details={"code": "control_state_unknown", "keys": unknown},
        )
    payload: ControlStatePayload = {}
    for key, control in registry.items():
        if key not in values:
            continue
        payload[key] = {
            "value": values[key],
            "revision": 0,
            **(
                {"intent": "explicit"}
                if candidate_backed_set(control.definition)
                else {}
            ),
        }
    return resolve_control_state(dashboard, payload, phase=phase)


def project_control_state(
    entry: Mapping[str, Any],
    projection: Literal["value", "present", "intent"] = "value",
) -> Any:
    if projection == "present":
        return not is_empty_control_value(entry.get("value"))
    if projection == "intent":
        return entry.get("intent", "explicit")
    return entry.get("value")


__all__ = [
    "CandidateIntent",
    "ControlStatePayload",
    "ResolvedInputState",
    "candidate_backed_set",
    "control_values",
    "initial_input_state",
    "normalize_input_state_entry",
    "project_control_state",
    "resolve_control_state",
    "state_from_values",
]
