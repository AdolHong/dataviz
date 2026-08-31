from __future__ import annotations

import math
from datetime import date, datetime
from numbers import Real
from typing import Any, Iterable

import pandas as pd

from dataviz.errors import ExecutionFailure


ORDERED_OPERATORS = frozenset({"between", "gte", "lte", "gt", "lt"})
OPERATORS_BY_VALUE_TYPE = {
    "text": frozenset({"equals", "in", "contains"}),
    "integer": frozenset({"equals", "in", *ORDERED_OPERATORS}),
    "number": frozenset({"equals", "in", *ORDERED_OPERATORS}),
    "date": frozenset({"equals", "in", *ORDERED_OPERATORS}),
    "boolean": frozenset({"equals", "in"}),
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    missing = pd.isna(value)
    if isinstance(missing, bool) and missing:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Real):
        numeric = float(value)
        if math.isfinite(numeric) and numeric.is_integer():
            return str(int(numeric))
    return str(value)


def _fields(item: dict[str, Any]) -> list[str]:
    binding = item.get("consumer_binding") or item
    raw = binding.get("field") or []
    return [str(field) for field in (raw if isinstance(raw, list) else [raw])]


def _can_apply(frame: pd.DataFrame, item: dict[str, Any]) -> bool:
    return all(field in frame.columns for field in _fields(item))


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(missing, bool) and missing


def resolve_control_filter_operator(item: dict[str, Any]) -> str:
    binding = item.get("consumer_binding") or item
    definition = item.get("definition") or {}
    operator = binding.get("operator") or "auto"
    if operator != "auto":
        return operator
    if definition.get("type") in {"multiple_input", "multiple_select"}:
        return "in"
    if definition.get("type") == "range_input":
        return "between"
    return "equals"


def validate_control_filter_operator(*, operator: str, value_type: str) -> None:
    allowed = OPERATORS_BY_VALUE_TYPE.get(value_type)
    if allowed is None or operator not in allowed:
        raise ExecutionFailure(
            f"Control filter operator {operator} is not valid for {value_type}",
            details={
                "code": "control_filter_operator_incompatible",
                "operator": operator,
                "value_type": value_type,
            },
        )


def _invalid_value(*, value_type: str, value: Any, role: str) -> ExecutionFailure:
    return ExecutionFailure(
        f"Control filter {role} cannot be converted to {value_type}",
        details={
            "code": "control_filter_value_invalid",
            "value_type": value_type,
            "role": role,
            "value": value,
        },
    )


def _coerce(value: Any, *, value_type: str, role: str) -> Any:
    if _is_missing(value):
        return None
    if value_type == "text":
        return _text(value)
    if value_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().casefold() in {"true", "false"}:
            return value.strip().casefold() == "true"
        raise _invalid_value(value_type=value_type, value=value, role=role)
    if value_type in {"integer", "number"}:
        if isinstance(value, bool):
            raise _invalid_value(value_type=value_type, value=value, role=role)
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise _invalid_value(
                value_type=value_type, value=value, role=role
            ) from error
        if not math.isfinite(numeric) or (
            value_type == "integer" and not numeric.is_integer()
        ):
            raise _invalid_value(value_type=value_type, value=value, role=role)
        return int(numeric) if value_type == "integer" else numeric
    if value_type == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise _invalid_value(value_type=value_type, value=value, role=role)
        try:
            return date.fromisoformat(value.strip())
        except ValueError as error:
            raise _invalid_value(
                value_type=value_type, value=value, role=role
            ) from error
    raise _invalid_value(value_type=value_type, value=value, role=role)


def control_filter_matches(
    actual: Any,
    *,
    value: Any,
    operator: str,
    value_type: str,
) -> bool:
    """Apply the declared typed comparator to one non-path field value."""

    validate_control_filter_operator(operator=operator, value_type=value_type)
    if _is_missing(actual):
        return False
    comparable = _coerce(actual, value_type=value_type, role="field")
    if operator == "in":
        raw_values = value if isinstance(value, (list, tuple)) else [value]
        expected = {
            _coerce(item, value_type=value_type, role="bound")
            for item in raw_values
        }
        return comparable in expected
    if operator == "between":
        bounds = value if isinstance(value, (list, tuple)) else []
        start = bounds[0] if len(bounds) > 0 else None
        end = bounds[1] if len(bounds) > 1 else None
        lower = (
            None
            if _is_missing(start) or start == ""
            else _coerce(start, value_type=value_type, role="bound")
        )
        upper = (
            None
            if _is_missing(end) or end == ""
            else _coerce(end, value_type=value_type, role="bound")
        )
        return (lower is None or comparable >= lower) and (
            upper is None or comparable <= upper
        )
    if operator == "contains":
        expected = _coerce(value, value_type=value_type, role="bound")
        return expected in comparable
    expected = _coerce(value, value_type=value_type, role="bound")
    if operator == "gte":
        return comparable >= expected
    if operator == "lte":
        return comparable <= expected
    if operator == "gt":
        return comparable > expected
    if operator == "lt":
        return comparable < expected
    return comparable == expected


def _mask(
    frame: pd.DataFrame,
    item: dict[str, Any],
    value: Any,
) -> pd.Series:
    if not _can_apply(frame, item):
        return pd.Series(True, index=frame.index, dtype=bool)
    binding = item.get("consumer_binding") or item
    if value is None or value == "" or (
        isinstance(value, (list, tuple)) and len(value) == 0
    ):
        return pd.Series(
            binding.get("empty", "passthrough") == "passthrough",
            index=frame.index,
            dtype=bool,
        )

    definition = item.get("definition") or {}
    fields = _fields(item)
    path_fields = fields if len(fields) > 1 else []
    if path_fields:
        paths = (
            value
            if isinstance(value, list) and value and isinstance(value[0], list)
            else [value]
        )
        matched = pd.Series(False, index=frame.index, dtype=bool)
        for path in paths:
            if not isinstance(path, (list, tuple)) or len(path) != len(path_fields):
                continue
            candidate = pd.Series(True, index=frame.index, dtype=bool)
            for field, expected in zip(path_fields, path, strict=True):
                candidate &= frame[field].map(_text) == _text(expected)
            matched |= candidate
        return matched

    operator = resolve_control_filter_operator(item)
    value_type = str(definition.get("value_type") or "text")
    field = fields[0]
    return frame[field].map(
        lambda actual: control_filter_matches(
            actual,
            value=value,
            operator=operator,
            value_type=value_type,
        )
    )


def apply_control_filters(
    frame: pd.DataFrame,
    filters: Iterable[dict[str, Any]],
) -> pd.DataFrame:
    """Apply explicit, declared-type Control filters to one table input."""

    selected = frame
    for item in filters:
        if not _can_apply(selected, item):
            continue
        selected = selected.loc[_mask(selected, item, item.get("value"))]
    return selected.reset_index(drop=True)
