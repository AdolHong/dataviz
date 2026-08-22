from __future__ import annotations

import os
from pathlib import Path

import yaml

from dataviz.errors import SourceFailure
from dataviz.workspace.models import ConnectionDefinition, ConnectionsFile


class ConnectionResolver:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.connections = self._load()

    def _load(self) -> dict[str, ConnectionDefinition]:
        result: dict[str, ConnectionDefinition] = {}
        for name in ("connections.example.yaml", "connections.local.yaml"):
            path = self.workspace_root / "auth" / name
            if not path.exists():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            parsed = ConnectionsFile.model_validate(data)
            result.update(parsed.connections)
        return result

    def resolve_url(self, name: str) -> str:
        if name not in self.connections:
            raise SourceFailure(f"Connection is not configured: {name}")
        connection = self.connections[name]
        value = os.environ.get(connection.env) if connection.env else connection.url
        if not value:
            raise SourceFailure(f"Connection {name} has no URL; configure {connection.env or 'url'}")
        if value.startswith("sqlite:///"):
            relative = value.removeprefix("sqlite:///")
            if relative != ":memory:" and not Path(relative).is_absolute():
                return f"sqlite:///{(self.workspace_root / relative).resolve()}"
        return value

