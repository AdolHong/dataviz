from __future__ import annotations

from typing import Any


# Known Runtime adapters are strict. Any other type is intentionally a custom
# adapter passed to a trusted Python Source, which may consume the full generic
# configuration envelope.
ADAPTER_CONTRACTS: dict[str, dict[str, Any]] = {
    "file": {
        "purpose": "Resolve files beneath one local root",
        "optional": ["root"],
    },
    "duckdb": {
        "purpose": "Run SQL against a DuckDB database or :memory:",
        "optional": ["database"],
    },
    "mysql": {
        "purpose": "Run SQL through the MySQL SQLAlchemy driver",
        "optional": [
            "url", "env", "database", "host", "port", "username", "password",
            "username_env", "password_env",
        ],
        "connection": "url/env or host+database+username/username_env",
    },
    "starrocks": {
        "purpose": "Run SQL through the StarRocks MySQL protocol",
        "optional": [
            "url", "env", "database", "host", "port", "username", "password",
            "username_env", "password_env",
        ],
        "connection": "url/env or host+database+username/username_env",
    },
    "sqlalchemy": {
        "purpose": "Run SQL through an explicit SQLAlchemy URL",
        "optional": ["url", "env"],
        "connection": "url or env",
    },
}


ADAPTER_COMMON_FIELDS = {
    "type",
    "description",
    "options",
    "config",
    "secrets",
}


def canonical_adapter_type(value: str) -> str | None:
    return value if value in ADAPTER_CONTRACTS else None


def validate_adapter_contract(name: str, adapter: Any) -> Any:
    adapter_type = canonical_adapter_type(adapter.type)
    if adapter_type is None:
        return adapter
    contract = ADAPTER_CONTRACTS[adapter_type]
    allowed = ADAPTER_COMMON_FIELDS | set(contract["optional"])
    ignored = sorted(set(adapter.model_fields_set) - allowed)
    if ignored:
        raise ValueError(
            f"Adapter {name} type {adapter.type} does not use fields: "
            f"{', '.join(ignored)}"
        )
    if adapter_type == "sqlalchemy" and not (adapter.url or adapter.env):
        raise ValueError(
            f"Adapter {name} type sqlalchemy requires url or env"
        )
    if adapter_type in {"mysql", "starrocks"}:
        has_url = bool(adapter.url or adapter.env)
        has_parts = bool(
            adapter.host
            and adapter.database
            and (adapter.username or adapter.username_env)
        )
        if not (has_url or has_parts):
            raise ValueError(
                f"Adapter {name} type {adapter_type} requires url/env or "
                "host+database+username/username_env"
            )
    return adapter
