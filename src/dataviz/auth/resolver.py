from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path

import yaml
from pydantic import ValidationError
from sqlalchemy import URL, create_engine, make_url

from dataviz.adapter_contracts import validate_adapter_contract
from dataviz.errors import SourceFailure
from dataviz.redaction import SENSITIVE_KEYS, adapter_secret_values
from dataviz.workspace.models import AdapterDefinition, AdaptersFile


class AdapterResolver:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.adapters = self._load()

    def _load(self) -> dict[str, AdapterDefinition]:
        merged: dict[str, dict[str, object]] = {}
        adapter_paths = (
            self.workspace_root / "auth" / "adapters.yaml",
            self.workspace_root / "auth" / "adapters.local.yaml",
        )
        for path in adapter_paths:
            if not path.exists():
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, UnicodeError, yaml.YAMLError) as error:
                mark = getattr(error, "problem_mark", None)
                raise SourceFailure(
                    "Adapter configuration file cannot be parsed",
                    file=path,
                    details={
                        "code": "adapter_file_invalid",
                        "error_type": type(error).__name__,
                        "line": mark.line + 1 if mark is not None else None,
                        "column": mark.column + 1 if mark is not None else None,
                    },
                ) from error
            if path.name == "adapters.yaml":
                self._validate_committed_adapter_file(data)
            try:
                parsed = AdaptersFile.model_validate(data)
            except ValidationError as error:
                raise SourceFailure(
                    "Adapter configuration schema is invalid",
                    file=path,
                    details={
                        "code": "adapter_schema_invalid",
                        "errors": error.errors(
                            include_url=False,
                            include_context=False,
                            include_input=False,
                        ),
                    },
                ) from error
            for name, adapter in parsed.adapters.items():
                overlay = adapter.model_dump(exclude_unset=True)
                current = merged.setdefault(name, {})
                for field, value in overlay.items():
                    if field in {"options", "config", "secrets"}:
                        nested = dict(current.get(field) or {})
                        nested.update(value)
                        current[field] = nested
                    else:
                        current[field] = value
        try:
            adapters = AdaptersFile.model_validate({"adapters": merged}).adapters
        except ValidationError as error:
            raise SourceFailure(
                "Merged Adapter configuration schema is invalid",
                details={
                    "code": "adapter_schema_invalid",
                    "errors": error.errors(
                        include_url=False,
                        include_context=False,
                        include_input=False,
                    ),
                },
            ) from error
        for name, adapter in adapters.items():
            validate_adapter_contract(name, adapter)
        return adapters

    @staticmethod
    def _validate_committed_adapter_file(data: object) -> None:
        """Reject direct credentials in the Git-shareable Adapter definition."""
        if not isinstance(data, dict) or not isinstance(data.get("adapters"), dict):
            return
        def nested_secret_fields(value: object, prefix: str = "") -> list[str]:
            found: list[str] = []
            if not isinstance(value, dict):
                return found
            for raw_key, item in value.items():
                key = str(raw_key)
                field = f"{prefix}.{key}" if prefix else key
                normalized = key.casefold().replace("-", "_")
                if normalized in SENSITIVE_KEYS and item is not None and item != "":
                    found.append(field)
                elif isinstance(item, dict):
                    found.extend(nested_secret_fields(item, field))
            return found

        for name, raw in data["adapters"].items():
            if not isinstance(raw, dict):
                continue
            forbidden: list[str] = []
            for field in ("username", "password"):
                if raw.get(field) is not None and raw.get(field) != "":
                    forbidden.append(field)
            url = raw.get("url")
            if isinstance(url, str) and url:
                try:
                    parsed = make_url(url)
                except Exception:
                    parsed = None
                if parsed is not None and (parsed.username is not None or parsed.password is not None):
                    forbidden.append("url credentials")
                if parsed is not None:
                    for query_key, query_value in parsed.query.items():
                        normalized = str(query_key).casefold().replace("-", "_")
                        if (
                            normalized in SENSITIVE_KEYS
                            and query_value is not None
                            and query_value != ""
                        ):
                            forbidden.append(f"url query.{query_key}")
            for container in ("options", "config"):
                forbidden.extend(
                    nested_secret_fields(raw.get(container), container)
                )
            if forbidden:
                fields = ", ".join(sorted(set(forbidden)))
                raise ValueError(
                    f"Adapter {name} stores direct credentials in auth/adapters.yaml "
                    f"({fields}); move them to auth/adapters.local.yaml or environment variables"
                )

    def resolve(self, name: str, bindings: dict[str, str] | None = None) -> tuple[str, AdapterDefinition]:
        actual_name = (bindings or {}).get(name, name)
        if actual_name not in self.adapters:
            raise SourceFailure(
                f"Adapter is not configured: {actual_name}",
                details={"requested": name, "binding": actual_name},
            )
        return actual_name, self.adapters[actual_name]

    def resolve_url(self, name: str, bindings: dict[str, str] | None = None) -> str | URL:
        actual_name, adapter = self.resolve(name, bindings)
        value = self._environment_value(
            actual_name, "env", adapter.env
        ) if adapter.env else adapter.url
        if not value:
            if adapter.type not in {"mysql", "starrocks"}:
                raise SourceFailure(
                    f"Adapter {actual_name} has no URL; configure {adapter.env or 'url'}"
                )
            username = (
                self._environment_value(
                    actual_name, "username_env", adapter.username_env
                )
                if adapter.username_env
                else adapter.username
            )
            password = (
                self._environment_value(
                    actual_name, "password_env", adapter.password_env
                )
                if adapter.password_env
                else adapter.password
            )
            if not adapter.host or not adapter.database or not username:
                raise SourceFailure(
                    f"Adapter {actual_name} requires host, database and username"
                )
            value = URL.create(
                "mysql+pymysql",
                username=username,
                password=password,
                host=adapter.host,
                port=adapter.port or (9030 if adapter.type == "starrocks" else 3306),
                database=adapter.database,
                query={str(key): str(item) for key, item in adapter.options.items()},
            )
        if isinstance(value, str) and value.startswith("sqlite:///"):
            relative = value.removeprefix("sqlite:///")
            if relative != ":memory:" and not Path(relative).is_absolute():
                return f"sqlite:///{(self.workspace_root / relative).resolve()}"
        return value

    def validate_sql_driver(
        self,
        name: str,
        bindings: dict[str, str] | None = None,
    ) -> None:
        """Load the configured SQLAlchemy dialect/DBAPI without opening a connection."""
        actual_name, adapter = self.resolve(name, bindings)
        if adapter.type == "duckdb":
            return
        resolved = self.resolve_url(name, bindings)
        driver = (
            resolved.drivername
            if isinstance(resolved, URL)
            else make_url(resolved).drivername
        )
        engine = None
        try:
            options = (
                {"connect_args": dict(adapter.options)}
                if adapter.type == "sqlalchemy" and adapter.options
                else {}
            )
            engine = create_engine(resolved, **options)
        except Exception as error:
            raise SourceFailure(
                f"Adapter {actual_name} cannot initialize SQL driver {driver}",
                details={
                    "adapter": actual_name,
                    "adapter_type": adapter.type,
                    "driver": driver,
                    "error_type": type(error).__name__,
                },
            ) from error
        finally:
            if engine is not None:
                engine.dispose()

    @staticmethod
    def _environment_value(
        adapter_name: str,
        field: str,
        variable: str,
    ) -> str:
        value = os.environ.get(variable)
        if value is None:
            raise SourceFailure(
                f"Adapter {adapter_name} requires environment variable {variable}",
                details={
                    "adapter": adapter_name,
                    "field": field,
                    "env": variable,
                },
            )
        return value

    def fingerprint(self, name: str, bindings: dict[str, str] | None = None) -> str:
        """Hash the effective Adapter without exposing credentials in cache metadata."""
        actual_name, adapter = self.resolve(name, bindings)
        payload = adapter.model_dump(mode="json")
        if adapter.env:
            payload["resolved_env"] = os.environ.get(adapter.env)
        if adapter.username_env:
            payload["resolved_username"] = os.environ.get(adapter.username_env)
        if adapter.password_env:
            payload["resolved_password"] = os.environ.get(adapter.password_env)
        payload["resolved_secrets"] = {
            key: os.environ.get(variable)
            for key, variable in adapter.secrets.items()
        }
        payload["binding"] = actual_name
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def redaction_values(
        self,
        name: str,
        bindings: dict[str, str] | None = None,
    ) -> tuple[str, ...]:
        """Collect effective credentials without requiring every env var to exist."""
        try:
            actual_name, adapter = self.resolve(name, bindings)
        except SourceFailure:
            return ()
        payload = adapter.model_dump(mode="json")
        resolved_credentials: dict[str, str] = {}
        if adapter.username:
            resolved_credentials["username"] = adapter.username
        if adapter.env and (value := os.environ.get(adapter.env)):
            resolved_credentials["url"] = value
        if adapter.username_env and (value := os.environ.get(adapter.username_env)):
            resolved_credentials["username"] = value
        if adapter.password_env and (value := os.environ.get(adapter.password_env)):
            resolved_credentials["password"] = value
        for key, variable in adapter.secrets.items():
            if value := os.environ.get(variable):
                resolved_credentials[key] = value
        payload["credentials"] = resolved_credentials
        payload["adapter_name"] = actual_name
        return adapter_secret_values(payload)

    def all_redaction_values(self) -> tuple[str, ...]:
        """Collect every configured credential for process/log boundary redaction."""
        values = {
            value
            for name in self.adapters
            for value in self.redaction_values(name)
        }
        return tuple(sorted(values, key=len, reverse=True))

    def runtime_config(
        self, name: str, bindings: dict[str, str] | None = None
    ) -> dict[str, object]:
        """Resolve one Adapter for a trusted Python Source without persisting secrets."""
        actual_name, adapter = self.resolve(name, bindings)
        username = (
            self._environment_value(
                actual_name, "username_env", adapter.username_env
            )
            if adapter.username_env
            else adapter.username
        )
        password = (
            self._environment_value(
                actual_name, "password_env", adapter.password_env
            )
            if adapter.password_env
            else adapter.password
        )
        secrets: dict[str, str] = {}
        for key, variable in adapter.secrets.items():
            value = os.environ.get(variable)
            if value is None:
                raise SourceFailure(
                    f"Adapter {actual_name} requires environment variable {variable}",
                    details={"adapter": actual_name, "secret": key, "env": variable},
                )
            secrets[key] = value

        root: str | None = None
        if adapter.root:
            root_path = Path(adapter.root)
            if not root_path.is_absolute():
                root_path = self.workspace_root / root_path
            root = str(root_path.resolve())

        database = adapter.database
        if adapter.type == "duckdb" and database and database != ":memory:":
            database_path = Path(database)
            if not database_path.is_absolute():
                database_path = self.workspace_root / database_path
            database = str(database_path.resolve())

        url: str | None = None
        if adapter.env or adapter.url or adapter.type in {
            "mysql",
            "starrocks",
            "sqlalchemy",
        }:
            resolved = self.resolve_url(name, bindings)
            url = (
                resolved.render_as_string(hide_password=False)
                if isinstance(resolved, URL)
                else str(resolved)
            )

        return {
            "name": actual_name,
            "type": adapter.type,
            "description": adapter.description,
            "url": url,
            "database": database,
            "host": adapter.host,
            "port": adapter.port,
            "username": username,
            "password": password,
            "root": root,
            "options": dict(adapter.options),
            "config": dict(adapter.config),
            "secrets": secrets,
        }

    def resolve_path(
        self, name: str, value: str, bindings: dict[str, str] | None = None
    ) -> Path:
        actual_name, adapter = self.resolve(name, bindings)
        if adapter.type != "file":
            raise SourceFailure(f"Adapter {actual_name} is not a file adapter")
        root = Path(adapter.root or ".")
        if not root.is_absolute():
            root = self.workspace_root / root
        root = root.resolve()
        path = (root / value).resolve()
        if path != root and root not in path.parents:
            raise SourceFailure(f"File path escapes adapter root: {value}")
        return path
