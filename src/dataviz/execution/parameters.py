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
    normalize_control_value,
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


QueryParameterIntent = Literal["all_available", "explicit"]


def resolve_query_parameter_intents(
    definitions: list[Any],
    values: Mapping[str, Any] | None,
    intents: Mapping[str, str] | None,
) -> dict[str, QueryParameterIntent]:
    """Resolve the minimal Query selection intent independently from values."""

    provided_values = dict(values or {})
    provided_intents = dict(intents or {})
    registry = {item.id: item for item in definitions}
    unknown = sorted(set(provided_intents) - set(registry))
    if unknown:
        raise ExecutionFailure(
            "Unknown Query Parameter intents",
            details={"code": "query_parameter_intent_unknown", "ids": unknown},
        )
    resolved: dict[str, QueryParameterIntent] = {}
    for parameter_id, definition in registry.items():
        intent = provided_intents.get(parameter_id)
        if intent is None:
            initial = getattr(definition, "initial", None)
            intent = (
                "all_available"
                if parameter_id not in provided_values
                and definition.type == "multiple_select"
                and getattr(initial, "mode", None) == "all"
                else "explicit"
            )
        if intent not in {"all_available", "explicit"}:
            raise ExecutionFailure(
                f"Invalid Query Parameter intent for {parameter_id}: {intent}",
                details={
                    "code": "query_parameter_intent_invalid",
                    "id": parameter_id,
                    "intent": intent,
                },
            )
        if intent == "all_available" and definition.type != "multiple_select":
            raise ExecutionFailure(
                f"Query Parameter {parameter_id} cannot use all_available",
                details={
                    "code": "query_parameter_intent_cardinality_invalid",
                    "id": parameter_id,
                },
            )
        resolved[parameter_id] = intent
    return resolved


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


def resolve_query_parameter_values(
    definitions: list[Any],
    values: Mapping[str, Any] | None,
    *,
    timezone_name: str,
    current_time: datetime | None = None,
) -> dict[str, Any]:
    provided = dict(values or {})
    registry = {item.id: item for item in definitions}
    unknown = sorted(set(provided) - set(registry))
    if unknown:
        raise ExecutionFailure(
            "Unknown Query Parameters",
            details={"code": "query_parameter_unknown", "ids": unknown},
        )
    result: dict[str, Any] = {}
    for definition in definitions:
        try:
            if definition.id in provided:
                value = normalize_control_value(definition, provided[definition.id])
            else:
                value = resolve_parameter_default(
                    definition,
                    timezone_name=timezone_name,
                    current_time=current_time,
                    enforce_required=True,
                )
        except (ValueContractViolation, ValueError) as error:
            reason = getattr(error, "message", str(error))
            code = getattr(error, "code", "invalid_default")
            raise ExecutionFailure(
                f"Invalid Query Parameter {definition.id}: {reason}",
                details={
                    "code": f"query_parameter_{code}",
                    "id": definition.id,
                    "reason": reason,
                },
            ) from error
        result[definition.id] = value
    return result


def project_query_inputs(
    bindings: Mapping[str, Any],
    parameters: Mapping[str, Any],
    intents: Mapping[str, QueryParameterIntent] | None = None,
) -> dict[str, Any]:
    """Project canonical Query Parameters into one node's local input names."""

    projected: dict[str, Any] = {}
    for alias, raw_binding in bindings.items():
        binding = query_input_contract(raw_binding)
        parameter = binding["parameter"]
        if binding.get("projection") == "intent":
            projected[alias] = (intents or {}).get(parameter, "explicit")
            continue
        value = parameters.get(parameter)
        if binding.get("projection") == "present":
            projected[alias] = not is_empty_control_value(value)
            continue
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
