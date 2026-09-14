"""Explicit JSON cell values for browser table transport (not Python artifacts)."""
from datetime import date, datetime, timezone
from decimal import Decimal
import math

import pyarrow as pa


def browser_cell(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) <= 9_007_199_254_740_991 else str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        # A timezone-naive timestamp is represented on the UTC timeline without
        # applying the machine's local timezone. Browser consumers get one form.
        normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return normalized.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, 'f') if value.is_finite() else None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return list(value)
    if isinstance(value, (list, tuple)):
        return [browser_cell(item) for item in value]
    if isinstance(value, dict):
        return {key: browser_cell(item) for key, item in value.items()}
    if isinstance(value, str):
        return value
    raise TypeError(f'Unsupported browser table cell: {type(value).__name__}')


def browser_table_rows(table: pa.Table) -> list[dict]:
    return [browser_cell(row) for row in table.to_pylist()]
