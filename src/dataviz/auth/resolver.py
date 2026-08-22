from __future__ import annotations

import os
from pathlib import Path

import yaml
from sqlalchemy import URL

from dataviz.errors import SourceFailure
from dataviz.workspace.models import AdapterDefinition, AdaptersFile, ConnectionsFile


class ConnectionResolver:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.adapters = self._load()
        self.connections = self.adapters

    def _load(self) -> dict[str, AdapterDefinition]:
        result: dict[str, AdapterDefinition] = {}
        adapter_paths = (
            self.workspace_root / "adapters.yaml",
            self.workspace_root / "adapters.local.yaml",
            self.workspace_root / "auth" / "adapters.example.yaml",
            self.workspace_root / "auth" / "adapters.local.yaml",
        )
        for path in adapter_paths:
            if not path.exists():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            result.update(AdaptersFile.model_validate(data).adapters)
        for name in ("connections.example.yaml", "connections.local.yaml"):
            path = self.workspace_root / "auth" / name
            if not path.exists():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            parsed = ConnectionsFile.model_validate(data)
            result.update(parsed.connections)
        return result

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
        value = os.environ.get(adapter.env) if adapter.env else adapter.url
        if not value:
            if adapter.type not in {"mysql", "starrocks"}:
                raise SourceFailure(
                    f"Adapter {actual_name} has no URL; configure {adapter.env or 'url'}"
                )
            username = os.environ.get(adapter.username_env) if adapter.username_env else adapter.username
            password = os.environ.get(adapter.password_env) if adapter.password_env else adapter.password
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

    def resolve_path(
        self, name: str, value: str, bindings: dict[str, str] | None = None
    ) -> Path:
        actual_name, adapter = self.resolve(name, bindings)
        if adapter.type not in {"file", "files", "local_files"}:
            raise SourceFailure(f"Adapter {actual_name} is not a file adapter")
        root = Path(adapter.root or ".")
        if not root.is_absolute():
            root = self.workspace_root / root
        root = root.resolve()
        path = (root / value).resolve()
        if path != root and root not in path.parents:
            raise SourceFailure(f"File path escapes adapter root: {value}")
        return path
