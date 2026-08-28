from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_DAY_OFFSET = re.compile(r"^[+-]?\d+d$")


def is_relative_date_expression(value: Any) -> bool:
    """Return whether one Date Atom is relative to Workspace-local today."""

    return isinstance(value, dict) and value.get("mode") == "relative"


def is_relative_date_default(value: Any) -> bool:
    """Return whether a scalar or range default contains a relative Date Atom."""

    return is_relative_date_expression(value) or (
        isinstance(value, (list, tuple))
        and any(is_relative_date_expression(item) for item in value)
    )


def normalize_relative_date_expression(value: Any) -> dict[str, str]:
    """Validate one public ``today + N days`` Date Atom."""

    if not is_relative_date_expression(value):
        raise ValueError("relative date expression must declare mode: relative")
    allowed = {"mode", "anchor", "offset"}
    required = allowed
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise ValueError(
            "relative date default contains unknown fields: " + ", ".join(unknown)
        )
    if missing:
        raise ValueError(
            "relative date default is missing fields: " + ", ".join(missing)
        )
    if value.get("anchor") != "today":
        raise ValueError("relative date default anchor must be today")
    normalized = {key: str(item) for key, item in value.items()}
    offset = value.get("offset")
    if not isinstance(offset, str) or not _DAY_OFFSET.fullmatch(offset.strip()):
        raise ValueError(
            "relative date offset must use an integer day offset such as -3d, 0d, or +2d"
        )
    normalized["offset"] = offset.strip()
    return normalized


def normalize_relative_date_default(value: Any, control_type: str) -> Any:
    """Canonicalize relative Date Atoms without erasing fixed ISO endpoints."""

    if control_type == "single_input":
        return normalize_relative_date_expression(value)
    if control_type != "range_input":
        raise ValueError(
            "relative defaults are only valid for single_input/date or range_input/date"
        )
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(
            "range_input/date default must contain exactly two fixed or relative Date Atoms"
        )
    normalized = [
        normalize_relative_date_expression(item)
        if is_relative_date_expression(item)
        else item
        for item in value
    ]
    if all(is_relative_date_expression(item) for item in normalized) and (
        _offset_days(normalized[0]["offset"])
        > _offset_days(normalized[1]["offset"])
    ):
        raise ValueError("relative range_input start offset cannot be after end offset")
    return normalized


def _offset_days(value: str) -> int:
    return int(value[:-1])


def resolve_relative_date_default(
    value: Any,
    control_type: str,
    *,
    timezone_name: str,
    current_time: datetime | None = None,
) -> str | list[str]:
    """Resolve one relative expression to immutable ISO dates in Workspace time."""

    normalized = normalize_relative_date_default(value, control_type)
    try:
        workspace_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"unknown Workspace timezone: {timezone_name}") from error
    instant = current_time or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    anchor: date = instant.astimezone(workspace_timezone).date()

    def resolve_atom(atom: Any) -> Any:
        if not is_relative_date_expression(atom):
            return atom
        return (anchor + timedelta(days=_offset_days(atom["offset"]))).isoformat()

    if control_type == "single_input":
        return resolve_atom(normalized)
    return [resolve_atom(normalized[0]), resolve_atom(normalized[1])]
