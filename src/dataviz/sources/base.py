from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from dataviz.auth import AdapterResolver
from dataviz.execution.context import ExecutionContext
from dataviz.workspace.models import SourceDefinition


@dataclass(slots=True)
class SourceRequest:
    definition_path: Path
    definition: SourceDefinition
    context: ExecutionContext
    adapters: AdapterResolver
    adapter_bindings: dict[str, str]
    node_id: str
    on_retry: Callable[[dict[str, Any]], None] | None = None
    cancel_event: Any | None = None


class SourceRunner(Protocol):
    def execute(self, request: SourceRequest): ...
