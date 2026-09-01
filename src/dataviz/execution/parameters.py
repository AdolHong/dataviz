from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from dataviz.errors import ExecutionFailure
from dataviz.relative_dates import is_relative_date_default, resolve_relative_date_default
from dataviz.value_contract import (
    ValueContractViolation,
    initial_control_value,
    is_empty_control_value,
    json_value_signature,
    normalize_control_value,
    query_select_default_contract,
)


def query_input_parameter(binding: Any) -> str:
    return str(query_input_contract(binding)["parameter"])


def query_input_contract(binding: Any) -> dict[str, Any]:
    if isinstance(binding, str):
        return {"parameter": binding}
    raw = (
        dict(binding)
        if isinstance(binding, Mapping)
        else binding.model_dump(mode="json", exclude_none=True)
    )
    projection = str(raw.get("projection") or "value")
    return {
        "parameter": str(raw["parameter"]),
        **({"projection": projection} if projection != "value" else {}),
        **({"part": str(raw["part"])} if raw.get("part") else {}),
    }


def control_input_control(binding: Any) -> str:
    return str(control_input_contract(binding)["control"])


def control_input_contract(binding: Any) -> dict[str, Any]:
    """Return the canonical consumer binding for one scoped Control."""

    if isinstance(binding, str):
        return {"control": binding, "mode": "value", "projection": "value"}
    raw = (
        dict(binding)
        if isinstance(binding, Mapping)
        else binding.model_dump(mode="json", exclude_none=True)
    )
    mode = str(raw.get("mode") or "value")
    payload: dict[str, Any] = {
        "control": str(raw["control"]),
        "mode": mode,
    }
    if mode == "value":
        payload["projection"] = str(raw.get("projection") or "value")
        return payload
    field = raw.get("field")
    payload.update(
        {
            "field": list(field) if isinstance(field, list) else str(field),
            "inputs": [str(value) for value in raw.get("inputs") or ()],
            "empty": str(raw["empty"]),
            "operator": str(raw.get("operator") or "auto"),
        }
    )
    return payload


QueryParameterSelection = Literal["all", "include", "exclude", "none"]


def _selection_operands(definition: Any, value: Any) -> list[Any]:
    normalized = normalize_control_value(
        definition,
        value,
        enforce_required=False,
        deduplicate=True,
    )
    signatures: set[str] = set()
    result: list[Any] = []
    for item in normalized:
        signature = json_value_signature(item)
        if signature in signatures:
            continue
        signatures.add(signature)
        result.append(item)
    if len(result) > definition.max_explicit_values:
        raise ValueContractViolation(
            "too_many_explicit_values",
            f"at most {definition.max_explicit_values} explicit values are allowed",
        )
    return result


def _query_parameter_default_state(
    definition: Any,
    *,
    timezone_name: str,
    current_time: datetime | None,
) -> dict[str, Any]:
    if definition.type == "multiple_select":
        policy = query_select_default_contract(definition)
        mode = str(policy["mode"])
        if mode in {"all", "none"}:
            return {"selection": mode, "value": []}
        return {
            "selection": mode,
            "value": _selection_operands(definition, policy.get("values") or []),
        }
    if definition.type == "single_select":
        policy = query_select_default_contract(definition)
        mode = str(policy["mode"])
        if mode == "none":
            value = None
        elif mode == "value":
            value = normalize_control_value(definition, policy.get("value"))
        else:
            options = getattr(definition, "options", None)
            choices = list(getattr(options, "choices", ()) or ())
            if getattr(options, "mode", None) != "static":
                raise ExecutionFailure(
                    f"Query Parameter {definition.id} default=first requires Parameter Lookup",
                    details={
                        "code": "query_parameter_default_requires_lookup",
                        "id": definition.id,
                    },
                )
            value = choices[0].value if choices else None
        return {"value": normalize_control_value(definition, value, enforce_required=True)}
    return {
        "value": resolve_parameter_default(
            definition,
            timezone_name=timezone_name,
            current_time=current_time,
            enforce_required=True,
        )
    }


def normalize_query_parameter_state(
    definition: Any,
    raw_state: Any,
    *,
    enforce_required: bool = True,
) -> dict[str, Any]:
    """Normalize one public Query Parameter state without consulting candidates."""

    if not isinstance(raw_state, Mapping):
        raise ValueContractViolation(
            "invalid_state", "Query Parameter state must be an object containing value"
        )
    unknown = sorted(set(raw_state) - {"value", "selection"})
    if unknown:
        raise ValueContractViolation(
            "invalid_state", "unknown Query Parameter state fields: " + ", ".join(unknown)
        )
    if definition.type != "multiple_select":
        if "selection" in raw_state:
            raise ValueContractViolation(
                "invalid_selection", "selection is only valid for multiple_select"
            )
        if "value" not in raw_state:
            raise ValueContractViolation("invalid_state", "Query Parameter state requires value")
        return {
            "value": normalize_control_value(
                definition,
                raw_state.get("value"),
                enforce_required=enforce_required,
            )
        }
    selection = raw_state.get("selection")
    if selection not in {"all", "include", "exclude", "none"}:
        raise ValueContractViolation(
            "invalid_selection",
            "multiple_select selection must be all, include, exclude, or none",
        )
    raw_value = raw_state.get("value", [])
    if selection in {"all", "none"}:
        if raw_value not in (None, [], ()):
            raise ValueContractViolation(
                "invalid_selection_operands", f"selection={selection} requires empty value"
            )
        if selection == "none" and enforce_required and definition.required:
            raise ValueContractViolation("required", "a non-empty selection is required")
        return {"selection": selection, "value": []}
    operands = _selection_operands(definition, raw_value)
    if not operands:
        raise ValueContractViolation(
            "invalid_selection_operands", f"selection={selection} requires finite operands"
        )
    return {"selection": selection, "value": operands}


def resolve_query_parameter_states(
    definitions: list[Any],
    states: Mapping[str, Any] | None,
    *,
    timezone_name: str,
    current_time: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve the only canonical Query Parameter snapshot used by a Run."""

    provided = dict(states or {})
    registry = {item.id: item for item in definitions}
    unknown = sorted(set(provided) - set(registry))
    if unknown:
        raise ExecutionFailure(
            "Unknown Query Parameters",
            details={"code": "query_parameter_unknown", "ids": unknown},
        )
    result: dict[str, dict[str, Any]] = {}
    for definition in definitions:
        try:
            result[definition.id] = (
                normalize_query_parameter_state(definition, provided[definition.id])
                if definition.id in provided
                else _query_parameter_default_state(
                    definition,
                    timezone_name=timezone_name,
                    current_time=current_time,
                )
            )
        except ExecutionFailure:
            raise
        except (ValueContractViolation, ValueError) as error:
            reason = getattr(error, "message", str(error))
            code = getattr(error, "code", "invalid_state")
            raise ExecutionFailure(
                f"Invalid Query Parameter {definition.id}: {reason}",
                details={
                    "code": f"query_parameter_{code}",
                    "id": definition.id,
                    "reason": reason,
                },
            ) from error
    return result


def resolve_parameter_default(
    definition: Any,
    *,
    timezone_name: str,
    current_time: datetime | None = None,
    enforce_required: bool = False,
) -> Any:
    value = initial_control_value(definition)
    if is_relative_date_default(value):
        value = resolve_relative_date_default(
            value,
            definition.type,
            timezone_name=timezone_name,
            current_time=current_time,
        )
    return normalize_control_value(
        definition, value, enforce_required=enforce_required
    )


def project_query_inputs(
    bindings: Mapping[str, Any],
    states: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Project canonical Query Parameters into one node's local input names."""

    projected: dict[str, Any] = {}
    for alias, raw_binding in bindings.items():
        binding = query_input_contract(raw_binding)
        parameter = binding["parameter"]
        state = dict(states.get(parameter) or {"value": None})
        projection = binding.get("projection") or "value"
        if projection == "state":
            projected[alias] = state
            continue
        if projection == "selection":
            if "selection" not in state:
                raise ExecutionFailure(
                    f"Query input {alias} cannot read selection from {parameter}",
                    details={"code": "query_input_projection_failed", "alias": alias, "parameter": parameter},
                )
            projected[alias] = state["selection"]
            continue
        if projection == "active":
            projected[alias] = (
                state.get("selection") != "all"
                if "selection" in state
                else not is_empty_control_value(state.get("value"))
            )
            continue
        value = state.get("value")
        part = binding.get("part")
        if part is not None:
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ExecutionFailure(
                    f"Query input {alias} cannot read {part} from {parameter}",
                    details={
                        "code": "query_input_projection_failed",
                        "alias": alias,
                        "parameter": parameter,
                        "part": part,
                    },
                )
            value = value[0 if part == "start" else 1]
        projected[alias] = value
    return projected
