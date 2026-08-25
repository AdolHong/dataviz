from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from dataviz.errors import ExecutionFailure
from dataviz.relative_dates import is_relative_date_default, resolve_relative_date_default
from dataviz.value_contract import ValueContractViolation, normalize_control_value


def query_input_parameter(binding: Any) -> str:
    return str(query_input_contract(binding)["parameter"])


def query_input_contract(binding: Any) -> dict[str, Any]:
    if isinstance(binding, str):
        return {"parameter": binding}
    if isinstance(binding, Mapping):
        return {
            "parameter": str(binding["parameter"]),
            **({"part": str(binding["part"])} if binding.get("part") else {}),
        }
    return binding.model_dump(mode="json", exclude_none=True)


def resolve_parameter_default(
    definition: Any,
    *,
    timezone_name: str,
    current_time: datetime | None = None,
    enforce_required: bool = False,
) -> Any:
    value = definition.default
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
) -> dict[str, Any]:
    """Project canonical Query Parameters into one node's local input names."""

    projected: dict[str, Any] = {}
    for alias, raw_binding in bindings.items():
        binding = query_input_contract(raw_binding)
        parameter = binding["parameter"]
        value = parameters.get(parameter)
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
