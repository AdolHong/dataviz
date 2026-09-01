from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from dataviz.auth import AdapterResolver
from dataviz.execution.context import ExecutionContext
from dataviz.workspace.models import SourceDefinition, WorkspaceAssetDefinition


@dataclass(slots=True)
class SourceRequest:
    definition_path: Path
    definition: SourceDefinition
    context: ExecutionContext
    adapters: AdapterResolver
    adapter_bindings: dict[str, str]
    node_id: str
    workspace_root: Path | None = None
    workspace_assets: Mapping[str, WorkspaceAssetDefinition] | None = None
    on_retry: Callable[[dict[str, Any]], None] | None = None
    cancel_event: Any | None = None


class SourceRunner(Protocol):
    def execute(self, request: SourceRequest): ...
