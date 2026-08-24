from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit


SENSITIVE_KEYS = frozenset({
    "api_key",
    "apikey",
    "access_key",
    "access_token",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
})


def adapter_secret_values(adapter: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Collect credential values that must not cross the execution boundary."""
    if not adapter:
        return ()
    values: set[str] = set()

    def add(value: object) -> None:
        if isinstance(value, str) and value:
            values.add(value)

    def visit(value: object, *, parent_sensitive: bool = False) -> None:
        if isinstance(value, Mapping):
            for raw_key, item in value.items():
                key = str(raw_key).casefold().replace("-", "_")
                sensitive = parent_sensitive or key in SENSITIVE_KEYS or key == "secrets"
                if sensitive and not isinstance(item, (Mapping, list, tuple, set)):
                    add(item)
                visit(item, parent_sensitive=sensitive)
        elif parent_sensitive and isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)

    visit(adapter)
    raw_url = adapter.get("url")
    if isinstance(raw_url, str) and raw_url:
        try:
            parsed_url = urlsplit(raw_url)
            password = parsed_url.password
        except ValueError:
            password = None
            parsed_url = None
        if password:
            add(password)
            add(unquote(password))
        if parsed_url is not None:
            for raw_key, raw_value in parse_qsl(
                parsed_url.query,
                keep_blank_values=False,
            ):
                key = raw_key.casefold().replace("-", "_")
                if key in SENSITIVE_KEYS:
                    add(raw_value)
                    add(unquote(raw_value))
    return tuple(sorted(values, key=len, reverse=True))


def redact_text(value: object, secrets: tuple[str, ...]) -> str:
    text = str(value)
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    return text


def redact_value(value: Any, secrets: tuple[str, ...]) -> Any:
    """Recursively redact strings while preserving a serializable payload shape."""
    if isinstance(value, str):
        return redact_text(value, secrets)
    if isinstance(value, dict):
        return {key: redact_value(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, secrets) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item, secrets) for item in value]
    return value
