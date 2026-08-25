from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Any

from dataviz.relative_dates import (
    is_relative_date_default,
    normalize_relative_date_default,
)


_DECIMAL_NUMBER = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class ValueContractViolation(ValueError):
    """A stable failure raised when a control value violates its DSL contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def is_empty_control_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == ()


def json_compatible_value(value: Any) -> Any:
    """Normalize the small set of YAML-native values allowed in browser state."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [json_compatible_value(item) for item in value]
    if isinstance(value, list):
        return [json_compatible_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_compatible_value(item) for key, item in value.items()}
    return value


def json_value_signature(value: Any) -> str:
    def validate_numbers(item: Any) -> None:
        if isinstance(item, bool) or item is None:
            return
        if isinstance(item, int) and abs(item) > _MAX_SAFE_INTEGER:
            raise ValueContractViolation(
                "unsafe_integer",
                "integer exceeds the exact JavaScript range; model identifiers as strings",
            )
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueContractViolation(
                "invalid_number", "numeric value must be finite"
            )
        if isinstance(item, (list, tuple)):
            for child in item:
                validate_numbers(child)
        elif isinstance(item, dict):
            for child in item.values():
                validate_numbers(child)

    validate_numbers(value)
    try:
        return json.dumps(
            json_compatible_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueContractViolation(
            "not_json_serializable",
            f"value must be JSON-serializable: {error}",
        ) from error


def static_control_choices(definition: Any) -> list[Any]:
    """Return the closed option domain without treating inferred data as static."""

    options = getattr(definition, "options", None)
    if getattr(options, "mode", None) != "static":
        return []
    return list(getattr(options, "choices", []) or [])


def _date_string(value: Any, *, label: str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise ValueContractViolation("invalid_type", f"{label} must be an ISO date string")
    normalized = value.strip()
    if not _ISO_DATE.fullmatch(normalized):
        raise ValueContractViolation(
            "invalid_date", f"{label} must use YYYY-MM-DD, received {value!r}"
        )
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError as error:
        raise ValueContractViolation(
            "invalid_date", f"{label} must use YYYY-MM-DD, received {value!r}"
        ) from error


def _choice_value(definition: Any, value: Any) -> Any:
    choices = static_control_choices(definition)
    if not choices:
        return value
    signature = json_value_signature(value)
    exact = [item.value for item in choices if json_value_signature(item.value) == signature]
    if len(exact) == 1:
        return exact[0]
    # CLI flags and native form controls begin as strings. Resolve them back to
    # the declared JSON value only when the representation is unambiguous.
    if isinstance(value, str):
        comparable = [item.value for item in choices if str(item.value) == value]
        if len(comparable) == 1:
            return comparable[0]
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded_matches = []
        else:
            decoded_signature = json_value_signature(decoded)
            decoded_matches = [
                item.value
                for item in choices
                if json_value_signature(item.value) == decoded_signature
            ]
        if len(decoded_matches) == 1:
            return decoded_matches[0]
    raise ValueContractViolation(
        "unknown_choice", f"value {value!r} is not one of the declared choices"
    )


def _number(definition: Any, value: Any, *, integer: bool) -> int | float:
    if isinstance(value, bool):
        raise ValueContractViolation("invalid_type", "boolean is not a numeric value")
    if isinstance(value, str):
        raw = value.strip()
        try:
            if integer:
                if not re.fullmatch(r"[+-]?\d+", raw):
                    raise ValueError
                value = int(raw)
            else:
                if not _DECIMAL_NUMBER.fullmatch(raw):
                    raise ValueError
                value = float(raw)
        except ValueError as error:
            kind = "integer" if integer else "number"
            raise ValueContractViolation("invalid_type", f"value must be a {kind}") from error
    if isinstance(value, int) and abs(value) > _MAX_SAFE_INTEGER:
        raise ValueContractViolation(
            "unsafe_integer",
            "integer exceeds the exact JavaScript range; model identifiers as strings",
        )
    if integer:
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if not isinstance(value, int):
            raise ValueContractViolation("invalid_type", "value must be an integer")
    elif not isinstance(value, (int, float)):
        raise ValueContractViolation("invalid_type", "value must be a number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueContractViolation("invalid_number", "numeric value must be finite")
    minimum = getattr(definition, "min", None)
    maximum = getattr(definition, "max", None)
    step = getattr(definition, "step", None)
    if minimum is not None and numeric < float(minimum):
        raise ValueContractViolation("below_minimum", f"value must be at least {minimum}")
    if maximum is not None and numeric > float(maximum):
        raise ValueContractViolation("above_maximum", f"value must be at most {maximum}")
    if step is not None:
        base = float(minimum or 0)
        quotient = (numeric - base) / float(step)
        if not math.isclose(quotient, round(quotient), rel_tol=0, abs_tol=1e-9):
            raise ValueContractViolation(
                "invalid_step", f"value must follow step {step} from {minimum or 0}"
            )
    # JavaScript has one Number type, but JSON.stringify() emits integral safe
    # numbers without a trailing decimal. Preserve that portable wire shape in
    # Python as well: it keeps SQL integer parameters usable while decimals
    # remain floats.
    if integer or (numeric.is_integer() and abs(numeric) <= _MAX_SAFE_INTEGER):
        return int(numeric)
    return numeric


def normalize_control_value(
    definition: Any,
    value: Any,
    *,
    enforce_required: bool = True,
) -> Any:
    """Normalize one Query/Compute/Selection value using the shared DSL contract."""

    kind = definition.type
    if is_empty_control_value(value):
        if enforce_required and getattr(definition, "required", False):
            raise ValueContractViolation("required", "a value is required")
        return [] if kind in {"multi_select", "date_range"} else None

    if kind == "string":
        if not isinstance(value, str):
            raise ValueContractViolation("invalid_type", "value must be a string")
        maximum = getattr(definition, "max_length", None)
        if maximum is not None and len(value) > maximum:
            raise ValueContractViolation(
                "too_long", f"value cannot be longer than {maximum} characters"
            )
        return value
    if kind == "number":
        return _number(definition, value, integer=False)
    if kind == "integer":
        return _number(definition, value, integer=True)
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise ValueContractViolation("invalid_type", "value must be a boolean")
    if kind == "date":
        normalized = _date_string(value, label="value")
        minimum = getattr(definition, "min_date", None)
        maximum = getattr(definition, "max_date", None)
        if minimum and normalized < minimum:
            raise ValueContractViolation(
                "before_minimum_date", f"value cannot be before {minimum}"
            )
        if maximum and normalized > maximum:
            raise ValueContractViolation(
                "after_maximum_date", f"value cannot be after {maximum}"
            )
        return normalized
    if kind == "date_range":
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",", 1)]
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueContractViolation(
                "invalid_shape", "date_range must contain exactly [start, end]"
            )
        start = _date_string(value[0], label="date_range start") if value[0] else ""
        end = _date_string(value[1], label="date_range end") if value[1] else ""
        if not start and not end:
            return []
        allow_start, allow_end = getattr(definition, "allow_empty", (False, False))
        if not start and not allow_start:
            raise ValueContractViolation(
                "missing_range_start", "date_range requires a start date"
            )
        if not end and not allow_end:
            raise ValueContractViolation(
                "missing_range_end", "date_range requires an end date"
            )
        if start and end and start > end:
            raise ValueContractViolation(
                "invalid_range", "date_range start cannot be after end"
            )
        minimum = getattr(definition, "min_date", None)
        maximum = getattr(definition, "max_date", None)
        for label, item in (("start", start), ("end", end)):
            if item and minimum and item < minimum:
                raise ValueContractViolation(
                    "before_minimum_date",
                    f"date_range {label} cannot be before {minimum}",
                )
            if item and maximum and item > maximum:
                raise ValueContractViolation(
                    "after_maximum_date",
                    f"date_range {label} cannot be after {maximum}",
                )
        return [start, end]
    if kind == "single_select":
        path_fields = list(getattr(definition, "path_fields", []) or [])
        if path_fields:
            if not isinstance(value, (list, tuple)) or len(value) != len(path_fields):
                raise ValueContractViolation(
                    "invalid_path",
                    f"single_select hierarchy requires one {len(path_fields)}-level path",
                )
            if any(item is None for item in value):
                raise ValueContractViolation(
                    "invalid_path", "hierarchy paths cannot contain null values"
                )
            return json_compatible_value(list(value))
        if isinstance(value, (list, tuple, set, dict)):
            raise ValueContractViolation("invalid_type", "single_select requires one value")
        return _choice_value(definition, value)
    if kind == "multi_select":
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if not isinstance(value, (list, tuple)):
            raise ValueContractViolation("invalid_type", "multi_select requires a list")
        path_fields = list(getattr(definition, "path_fields", []) or [])
        if path_fields:
            normalized = []
            for item in value:
                if not isinstance(item, (list, tuple)) or len(item) != len(path_fields):
                    raise ValueContractViolation(
                        "invalid_path",
                        f"multi_select hierarchy values require {len(path_fields)}-level paths",
                    )
                if any(child is None for child in item):
                    raise ValueContractViolation(
                        "invalid_path", "hierarchy paths cannot contain null values"
                    )
                normalized.append(json_compatible_value(list(item)))
        else:
            normalized = [_choice_value(definition, item) for item in value]
        signatures = [json_value_signature(item) for item in normalized]
        if len(signatures) != len(set(signatures)):
            raise ValueContractViolation("duplicate_value", "multi_select values must be unique")
        if enforce_required and getattr(definition, "required", False) and not normalized:
            raise ValueContractViolation("required", "at least one value is required")
        maximum = getattr(definition, "max_selected", None)
        if maximum is not None and len(normalized) > maximum:
            raise ValueContractViolation(
                "too_many_values", f"at most {maximum} values may be selected"
            )
        return normalized
    raise ValueContractViolation("unknown_type", f"unsupported control type: {kind}")


def validate_control_definition(definition: Any) -> Any:
    """Validate and canonicalize defaults while Pydantic builds the DSL model."""

    if definition.required and definition.clearable is True:
        raise ValueError("required controls cannot be clearable")
    if definition.type == "single_select" and definition.clearable is True:
        raise ValueError(
            "single_select does not expose a clear action; use required: false for an initially empty value"
        )
    if definition.min is not None and definition.max is not None and definition.min > definition.max:
        raise ValueError("min cannot be greater than max")
    if definition.step is not None and definition.step <= 0:
        raise ValueError("step must be greater than zero")
    if definition.type not in {"number", "integer"} and any(
        item is not None for item in (definition.min, definition.max, definition.step)
    ):
        raise ValueError("min, max and step are only valid for number or integer")
    if definition.type not in {"date", "date_range"} and any(
        item is not None for item in (definition.min_date, definition.max_date)
    ):
        raise ValueError("min_date and max_date are only valid for date or date_range")
    if definition.min_date is not None:
        definition.min_date = _date_string(definition.min_date, label="min_date")
    if definition.max_date is not None:
        definition.max_date = _date_string(definition.max_date, label="max_date")
    if (
        definition.min_date is not None
        and definition.max_date is not None
        and definition.min_date > definition.max_date
    ):
        raise ValueError("min_date cannot be after max_date")
    if definition.type != "string" and definition.max_length is not None:
        raise ValueError("max_length is only valid for string")
    if definition.type != "multi_select" and definition.max_selected is not None:
        raise ValueError("max_selected is only valid for multi_select")
    if definition.type != "date_range" and definition.allow_empty != (False, False):
        raise ValueError("allow_empty is only valid for date_range")
    if definition.type not in {"single_select", "multi_select"} and definition.options is not None:
        raise ValueError("options are only valid for single_select or multi_select")
    if definition.type in {"single_select", "multi_select"} and definition.options is None:
        raise ValueError("select controls require options.mode=static or options.mode=infer")
    if definition.type != "string" and definition.suggestions:
        raise ValueError("suggestions are only valid for string")
    choices = static_control_choices(definition)
    for choice in choices:
        choice.value = json_compatible_value(choice.value)
    signatures = [json_value_signature(choice.value) for choice in choices]
    if len(signatures) != len(set(signatures)):
        raise ValueError("choice values must be unique")
    for suggestion in definition.suggestions:
        suggestion.value = json_compatible_value(suggestion.value)
        if not isinstance(suggestion.value, str):
            raise ValueError("suggestion values must be strings")
    suggestion_signatures = [
        json_value_signature(suggestion.value)
        for suggestion in definition.suggestions
    ]
    if len(suggestion_signatures) != len(set(suggestion_signatures)):
        raise ValueError("suggestion values must be unique")
    if is_relative_date_default(definition.default):
        definition.default = normalize_relative_date_default(
            definition.default, definition.type
        )
    elif not is_empty_control_value(definition.default):
        definition.default = normalize_control_value(
            definition, definition.default, enforce_required=False
        )
    elif definition.type in {"multi_select", "date_range"} and definition.default in ([], ()):
        definition.default = []
    return definition
