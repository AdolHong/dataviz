from __future__ import annotations

import math
from numbers import Real
from typing import Any, Iterable

import pandas as pd


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


def _text_series(series: pd.Series) -> pd.Series:
    return series.map(_text)


def _fields(item: dict[str, Any]) -> list[str]:
    binding = item.get("consumer_binding") or item
    raw = binding.get("field") or []
    return [str(field) for field in (raw if isinstance(raw, list) else [raw])]


def _can_apply(frame: pd.DataFrame, item: dict[str, Any]) -> bool:
    return all(field in frame.columns for field in _fields(item))


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
        paths = value if isinstance(value, list) and value and isinstance(value[0], list) else [value]
        matched = pd.Series(False, index=frame.index, dtype=bool)
        for path in paths:
            if not isinstance(path, (list, tuple)) or len(path) != len(path_fields):
                continue
            candidate = pd.Series(True, index=frame.index, dtype=bool)
            for field, expected in zip(path_fields, path, strict=True):
                candidate &= _text_series(frame[field]) == _text(expected)
            matched |= candidate
        return matched

    field = fields[0]
    operator = binding.get("operator") or "auto"
    if operator == "auto":
        if definition.get("type") in {"multiple_input", "multiple_select"}:
            operator = "in"
        elif definition.get("type") == "range_input":
            operator = "between"
        else:
            operator = "equals"

    actual = frame[field]
    if operator == "in":
        expected = value if isinstance(value, (list, tuple)) else [value]
        allowed = {_text(item) for item in expected}
        return _text_series(actual).isin(allowed)
    if operator == "between":
        bounds = value if isinstance(value, (list, tuple)) else []
        start = bounds[0] if len(bounds) > 0 else None
        end = bounds[1] if len(bounds) > 1 else None
        comparable = _text_series(actual)
        matched = pd.Series(True, index=frame.index, dtype=bool)
        if start not in {None, ""}:
            matched &= comparable >= _text(start)
        if end not in {None, ""}:
            matched &= comparable <= _text(end)
        return matched
    if operator == "contains":
        return _text_series(actual).str.contains(
            _text(value), regex=False, na=False
        )
    if operator in {"gte", "lte", "gt", "lt"}:
        numeric = pd.to_numeric(actual, errors="coerce")
        expected = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(expected):
            return pd.Series(False, index=frame.index, dtype=bool)
        if operator == "gte":
            return numeric >= expected
        if operator == "lte":
            return numeric <= expected
        if operator == "gt":
            return numeric > expected
        return numeric < expected
    return _text_series(actual) == _text(value)


def apply_control_filters(
    frame: pd.DataFrame,
    filters: Iterable[dict[str, Any]],
) -> pd.DataFrame:
    """Apply explicit consumer-side Control filters to one table input."""

    selected = frame
    for item in filters:
        if not _can_apply(selected, item):
            continue
        selected = selected.loc[_mask(selected, item, item.get("value"))]
    return selected.reset_index(drop=True)
