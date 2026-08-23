from __future__ import annotations

from datetime import date, datetime, time as datetime_time
from decimal import Decimal
import math
import re
from typing import Any


def _sql_literal(value: Any) -> str:
    """Render a readable literal for inspection; query execution stays parameterized."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float, Decimal)):
        if isinstance(value, float) and not math.isfinite(value):
            return "NULL"
        return str(value)
    if isinstance(value, (datetime, date, datetime_time)):
        value = value.isoformat()
    if isinstance(value, bytes):
        return f"X'{value.hex()}'"
    if isinstance(value, (list, tuple, set)):
        return "(" + ", ".join(_sql_literal(item) for item in value) + ")"
    return "'" + str(value).replace("'", "''") + "'"


def _inspect_named_parameters(
    query: str,
    replacements: dict[str, Any] | None,
) -> tuple[str, set[str]]:
    """Scan named placeholders without interpreting strings or SQL comments."""
    output: list[str] = []
    names: set[str] = set()
    index = 0
    state = "code"
    quote = ""
    while index < len(query):
        char = query[index]
        following = query[index + 1] if index + 1 < len(query) else ""
        if state == "line_comment":
            output.append(char)
            index += 1
            if char == "\n":
                state = "code"
            continue
        if state == "block_comment":
            output.append(char)
            index += 1
            if char == "*" and following == "/":
                output.append(following)
                index += 1
                state = "code"
            continue
        if state == "dollar_quoted":
            if query.startswith(quote, index):
                output.append(quote)
                index += len(quote)
                state = "code"
            else:
                output.append(char)
                index += 1
            continue
        if state == "quoted":
            output.append(char)
            index += 1
            if char == quote:
                if following == quote:
                    output.append(following)
                    index += 1
                else:
                    state = "code"
            elif char == "\\" and following:
                output.append(following)
                index += 1
            continue
        if char == "-" and following == "-":
            output.extend((char, following))
            index += 2
            state = "line_comment"
            continue
        if char == "/" and following == "*":
            output.extend((char, following))
            index += 2
            state = "block_comment"
            continue
        if char == "$":
            dollar_quote = re.match(r"\$(?:[A-Za-z_]\w*)?\$", query[index:])
            if dollar_quote:
                quote = dollar_quote.group(0)
                output.append(quote)
                index += len(quote)
                state = "dollar_quoted"
                continue
        if char in {"'", '"', "`"}:
            output.append(char)
            index += 1
            state = "quoted"
            quote = char
            continue
        if char in {":", "$"} and not (char == ":" and following == ":"):
            match = re.match(r"[A-Za-z_]\w*", query[index + 1 :])
            if match:
                name = match.group(0)
                names.add(name)
                if replacements is not None and name in replacements:
                    output.append(_sql_literal(replacements[name]))
                else:
                    output.append(query[index : index + len(name) + 1])
                index += len(name) + 1
                continue
        output.append(char)
        index += 1
    return "".join(output), names


def sql_parameter_names(query: str) -> set[str]:
    """Return named ``:parameter`` and ``$parameter`` placeholders in SQL code."""
    return _inspect_named_parameters(query, None)[1]


def resolve_sql_preview(query: str, parameters: dict[str, Any]) -> str:
    """Literalize known named parameters for human inspection only."""
    return _inspect_named_parameters(query, parameters)[0]


__all__ = ["resolve_sql_preview", "sql_parameter_names"]
