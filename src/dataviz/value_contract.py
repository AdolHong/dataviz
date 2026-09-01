from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Any

from dataviz.relative_dates import (
    is_relative_date_default,
    is_relative_date_expression,
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


def select_initial_contract(definition: Any) -> dict[str, Any]:
    """Return the explicit initial policy for any Select control."""

    if definition.type not in {"single_select", "multiple_select"}:
        raise ValueError("initial policies are only valid for select controls")
    initial = getattr(definition, "initial", None)
    if initial is None:
        return {
            "mode": "all" if definition.type == "multiple_select" else "first"
        }
    return initial.model_dump(mode="json", exclude_none=True)


def query_select_default_contract(definition: Any) -> dict[str, Any]:
    """Return the single public default policy for a Query select."""

    if definition.type not in {"single_select", "multiple_select"}:
        raise ValueError("select default policies are only valid for select Query Parameters")
    default = getattr(definition, "default", None)
    if default is None:
        return {"mode": "all" if definition.type == "multiple_select" else "first"}
    if hasattr(default, "model_dump"):
        return default.model_dump(mode="json", exclude_none=True)
    if isinstance(default, dict):
        return dict(default)
    raise ValueError("select Query Parameter default must be a structured policy")


def select_initial_value(
    definition: Any,
    available_values: list[Any] | None = None,
) -> Any:
    """Materialize one Select initial policy against the available domain."""

    policy = select_initial_contract(definition)
    values = (
        list(available_values)
        if available_values is not None
        else [choice.value for choice in static_control_choices(definition)]
    )
    mode = policy["mode"]
    if mode == "all":
        return values
    if mode == "empty":
        return [] if definition.type == "multiple_select" else None
    if mode == "values":
        return list(policy["values"])
    if mode == "first":
        return values[0] if values else None
    return policy["value"]


def initial_control_value(definition: Any) -> Any:
    """Return the canonical initial value for Query/Compute/non-dynamic controls."""

    if definition.type in {"single_select", "multiple_select"}:
        return select_initial_value(definition)
    return definition.default


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


def _scalar_value(definition: Any, value: Any, *, label: str = "value") -> Any:
    """Normalize one atom independently from the Control's input shape."""

    value_type = definition.value_type
    if value_type == "text":
        if not isinstance(value, str):
            raise ValueContractViolation("invalid_type", f"{label} must be text")
        maximum = getattr(definition, "max_length", None)
        if maximum is not None and len(value) > maximum:
            raise ValueContractViolation(
                "too_long", f"{label} cannot be longer than {maximum} characters"
            )
        return value
    if value_type == "integer":
        return _number(definition, value, integer=True)
    if value_type == "number":
        return _number(definition, value, integer=False)
    if value_type == "boolean":
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
        raise ValueContractViolation("invalid_type", f"{label} must be a boolean")
    if value_type == "date":
        normalized = _date_string(value, label=label)
        minimum = getattr(definition, "min_date", None)
        maximum = getattr(definition, "max_date", None)
        if minimum and normalized < minimum:
            raise ValueContractViolation(
                "before_minimum_date", f"{label} cannot be before {minimum}"
            )
        if maximum and normalized > maximum:
            raise ValueContractViolation(
                "after_maximum_date", f"{label} cannot be after {maximum}"
            )
        return normalized
    raise ValueContractViolation(
        "unknown_value_type", f"unsupported value_type: {value_type}"
    )


def _typed_choice_value(definition: Any, value: Any, *, label: str = "value") -> Any:
    normalized = _scalar_value(definition, value, label=label)
    return _choice_value(definition, normalized)


def normalize_control_value(
    definition: Any,
    value: Any,
    *,
    enforce_required: bool = True,
    deduplicate: bool = False,
) -> Any:
    """Normalize one Query/Compute/Selection value using the shared DSL contract."""

    kind = definition.type
    if is_empty_control_value(value):
        if enforce_required and getattr(definition, "required", False):
            raise ValueContractViolation("required", "a value is required")
        return [] if kind in {"multiple_input", "multiple_select", "range_input"} else None

    if kind == "single_input":
        return _scalar_value(definition, value)
    if kind == "multiple_input":
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if not isinstance(value, (list, tuple)):
            raise ValueContractViolation(
                "invalid_type", "multiple_input requires a list"
            )
        normalized = [
            _scalar_value(definition, item, label=f"item {index + 1}")
            for index, item in enumerate(value)
        ]
        maximum = getattr(definition, "max_items", None)
        if maximum is not None and len(normalized) > maximum:
            raise ValueContractViolation(
                "too_many_values", f"at most {maximum} values may be entered"
            )
        signatures = [json_value_signature(item) for item in normalized]
        if len(signatures) != len(set(signatures)):
            raise ValueContractViolation(
                "duplicate_value", "multiple_input values must be unique"
            )
        return normalized
    if kind == "range_input":
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",", 1)]
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueContractViolation(
                "invalid_shape", "range_input must contain exactly [start, end]"
            )
        start = _scalar_value(definition, value[0], label="range start") if value[0] not in (None, "") else ""
        end = _scalar_value(definition, value[1], label="range end") if value[1] not in (None, "") else ""
        if start == "" and end == "":
            return []
        allow_start, allow_end = getattr(definition, "allow_empty", (False, False))
        if start == "" and not allow_start:
            raise ValueContractViolation(
                "missing_range_start", "range_input requires a start value"
            )
        if end == "" and not allow_end:
            raise ValueContractViolation(
                "missing_range_end", "range_input requires an end value"
            )
        if start != "" and end != "" and start > end:
            raise ValueContractViolation(
                "invalid_range", "range_input start cannot be after end"
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
            normalized_path = [
                _scalar_value(definition, item, label=path_fields[index])
                for index, item in enumerate(value)
            ]
            return _choice_value(definition, normalized_path)
        if isinstance(value, (list, tuple, set, dict)):
            raise ValueContractViolation("invalid_type", "single_select requires one value")
        return _typed_choice_value(definition, value)
    if kind == "multiple_select":
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if not isinstance(value, (list, tuple)):
            raise ValueContractViolation("invalid_type", "multiple_select requires a list")
        path_fields = list(getattr(definition, "path_fields", []) or [])
        if path_fields:
            normalized = []
            for item in value:
                if not isinstance(item, (list, tuple)) or len(item) != len(path_fields):
                    raise ValueContractViolation(
                        "invalid_path",
                        f"multiple_select hierarchy values require {len(path_fields)}-level paths",
                    )
                if any(child is None for child in item):
                    raise ValueContractViolation(
                        "invalid_path", "hierarchy paths cannot contain null values"
                    )
                normalized.append(
                    _choice_value(
                        definition,
                        [
                            _scalar_value(definition, child, label=path_fields[index])
                            for index, child in enumerate(item)
                        ],
                    )
                )
        else:
            normalized = [_typed_choice_value(definition, item) for item in value]
        signatures = [json_value_signature(item) for item in normalized]
        if len(signatures) != len(set(signatures)):
            if not deduplicate:
                raise ValueContractViolation(
                    "duplicate_value", "multiple_select values must be unique"
                )
            seen: set[str] = set()
            normalized = [
                item
                for item, signature in zip(normalized, signatures, strict=True)
                if not (signature in seen or seen.add(signature))
            ]
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
    if definition.min is not None and definition.max is not None and definition.min > definition.max:
        raise ValueError("min cannot be greater than max")
    if definition.step is not None and definition.step <= 0:
        raise ValueError("step must be greater than zero")
    if definition.value_type not in {"number", "integer"} and any(
        item is not None for item in (definition.min, definition.max, definition.step)
    ):
        raise ValueError("min, max and step are only valid for number or integer")
    if definition.value_type != "date" and any(
        item is not None for item in (definition.min_date, definition.max_date)
    ):
        raise ValueError("min_date and max_date are only valid for value_type=date")
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
    if definition.value_type != "text" and definition.max_length is not None:
        raise ValueError("max_length is only valid for value_type=text")
    if definition.type != "multiple_select" and definition.max_selected is not None:
        raise ValueError("max_selected is only valid for multiple_select")
    if definition.type != "multiple_input" and definition.max_items is not None:
        raise ValueError("max_items is only valid for multiple_input")
    if definition.type != "range_input" and definition.allow_empty != (False, False):
        raise ValueError("allow_empty is only valid for range_input")
    if definition.type not in {"single_select", "multiple_select"} and definition.options is not None:
        raise ValueError("options are only valid for single_select or multiple_select")
    if definition.type in {"single_select", "multiple_select"} and definition.options is None:
        raise ValueError("select controls require options.mode=static or options.mode=infer")
    is_select = definition.type in {"single_select", "multiple_select"}
    is_query_parameter = bool(getattr(definition, "_is_query_parameter", False))
    if not is_select and definition.initial is not None:
        raise ValueError("initial is only valid for single_select or multiple_select")
    if is_select and not is_query_parameter and "default" in definition.model_fields_set:
        raise ValueError("select controls use initial instead of default")
    if is_query_parameter and definition.initial is not None:
        raise ValueError("Query Parameters use default instead of initial")
    if definition.suggestions and not (
        definition.type == "single_input" and definition.value_type == "text"
    ):
        raise ValueError("suggestions are only valid for single_input/text")
    if definition.type == "range_input" and definition.value_type not in {
        "date", "integer", "number"
    }:
        raise ValueError(
            "range_input only supports value_type=date, integer, or number"
        )
    if definition.type == "multiple_input" and definition.value_type == "boolean":
        raise ValueError("multiple_input does not support value_type=boolean")
    choices = static_control_choices(definition)
    for choice in choices:
        if getattr(definition, "path_fields", []):
            if not isinstance(choice.value, (list, tuple)) or len(choice.value) != len(definition.path_fields):
                raise ValueError("hierarchical choice values must match path_fields")
            choice.value = [
                _scalar_value(definition, item, label=definition.path_fields[index])
                for index, item in enumerate(choice.value)
            ]
        else:
            choice.value = _scalar_value(definition, choice.value, label="choice value")
    signatures = [json_value_signature(choice.value) for choice in choices]
    if len(signatures) != len(set(signatures)):
        raise ValueError("choice values must be unique")
    if is_select:
        policy = (
            query_select_default_contract(definition)
            if is_query_parameter
            else select_initial_contract(definition)
        )
        mode = policy["mode"]
        if is_query_parameter:
            allowed = (
                {"all", "include", "exclude", "none"}
                if definition.type == "multiple_select"
                else {"first", "value", "none"}
            )
        else:
            allowed = (
                {"all", "empty", "values"}
                if definition.type == "multiple_select"
                else {"first", "empty", "value"}
            )
        if mode not in allowed:
            choices_label = ", ".join(sorted(allowed))
            raise ValueError(
                f"{definition.type} {'default' if is_query_parameter else 'initial'} mode "
                f"must be one of: {choices_label}"
            )
        if definition.required and mode in {"empty", "none"}:
            raise ValueError("required select controls cannot use an empty default")
        try:
            if mode in {"values", "include", "exclude"}:
                normalized_values = normalize_control_value(
                    definition,
                    policy["values"],
                    enforce_required=True,
                )
                if len(normalized_values) > getattr(definition, "max_explicit_values", 10_000):
                    raise ValueError("default operands exceed max_explicit_values")
                if is_query_parameter:
                    definition.default.values = normalized_values
                else:
                    definition.initial.values = normalized_values
            elif mode == "value":
                normalized_value = normalize_control_value(
                    definition,
                    policy["value"],
                    enforce_required=True,
                )
                if is_query_parameter:
                    definition.default.value = normalized_value
                else:
                    definition.initial.value = normalized_value
            elif mode == "all" and not is_query_parameter and definition.max_selected is not None:
                if not choices or len(choices) > definition.max_selected:
                    raise ValueError(
                        "initial mode=all is incompatible with max_selected when the "
                        "complete option domain may exceed that limit"
                    )
        except ValueContractViolation as error:
            raise ValueError(f"invalid select initial value: {error.message}") from error
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
    if is_select and not is_query_parameter:
        definition.default = None
    elif is_select and is_query_parameter:
        pass
    elif is_relative_date_default(definition.default):
        if not (
            definition.value_type == "date"
            and definition.type in {"single_input", "range_input"}
        ):
            raise ValueError(
                "relative defaults require single_input/date or range_input/date"
            )
        definition.default = normalize_relative_date_default(
            definition.default, definition.type
        )
        if definition.type == "range_input":
            definition.default = [
                item
                if is_relative_date_expression(item)
                else _scalar_value(
                    definition,
                    item,
                    label=f"range {'start' if index == 0 else 'end'}",
                )
                for index, item in enumerate(definition.default)
            ]
    elif not is_empty_control_value(definition.default):
        definition.default = normalize_control_value(
            definition, definition.default, enforce_required=False
        )
    elif definition.type in {"multiple_input", "range_input"} and definition.default in ([], ()):
        definition.default = []
    return definition
