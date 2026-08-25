from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_DAY_OFFSET = re.compile(r"^[+-]?\d+d$")


def is_relative_date_default(value: Any) -> bool:
    return isinstance(value, dict) and value.get("mode") == "relative"


def normalize_relative_date_default(value: Any, control_type: str) -> dict[str, str]:
    """Validate and canonicalize the public relative-date DSL."""

    if not is_relative_date_default(value):
        raise ValueError("relative date default must declare mode: relative")
    if control_type == "date":
        allowed = {"mode", "anchor", "offset"}
        required = allowed
    elif control_type == "date_range":
        allowed = {"mode", "anchor", "start_offset", "end_offset"}
        required = allowed
    else:
        raise ValueError("relative defaults are only valid for date or date_range")
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
    offset_fields = (
        ("offset",)
        if control_type == "date"
        else ("start_offset", "end_offset")
    )
    normalized = {key: str(item) for key, item in value.items()}
    for field in offset_fields:
        offset = value.get(field)
        if not isinstance(offset, str) or not _DAY_OFFSET.fullmatch(offset.strip()):
            raise ValueError(
                f"relative date {field} must use an integer day offset such as -3d, 0d, or +2d"
            )
        normalized[field] = offset.strip()
    if control_type == "date_range" and (
        _offset_days(normalized["start_offset"])
        > _offset_days(normalized["end_offset"])
    ):
        raise ValueError(
            "relative date_range start_offset cannot be after end_offset"
        )
    return normalized


def _offset_days(value: str) -> int:
    return int(value[:-1])


def resolve_relative_date_default(
    value: dict[str, str],
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
    if control_type == "date":
        return (anchor + timedelta(days=_offset_days(normalized["offset"]))).isoformat()
    return [
        (anchor + timedelta(days=_offset_days(normalized["start_offset"]))).isoformat(),
        (anchor + timedelta(days=_offset_days(normalized["end_offset"]))).isoformat(),
    ]
