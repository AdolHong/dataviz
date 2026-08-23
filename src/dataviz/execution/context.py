from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.errors import ExecutionFailure


@dataclass(slots=True)
class ExecutionContext:
    workspace_root: Path
    dashboard_root: Path
    run_id: str
    params: dict[str, Any]
    inputs: dict[str, ArtifactDescriptor]
    store: ArtifactStore
    adapter: dict[str, Any] | None = None

    def table(self, name: str):
        descriptor = self.inputs[name]
        if descriptor.kind != "table":
            raise ExecutionFailure(f"Input {name} is {descriptor.kind}, not table")
        return self.store.read_table(descriptor)

    def input(self, name: str) -> Any:
        """Read one explicitly named Source/Transform input."""
        descriptor = self.inputs[name]
        return self.store.read_value(descriptor)

    def artifact(self, name: str) -> ArtifactDescriptor:
        return self.inputs[name]
