from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.errors import ExecutionFailure
from dataviz.execution.selection_filter import apply_selection_filters


@dataclass(slots=True)
class ExecutionContext:
    workspace_root: Path
    dashboard_root: Path
    run_id: str
    query_inputs: dict[str, Any]
    compute_params: dict[str, Any]
    selections: dict[str, Any]
    selection_state: dict[str, dict[str, Any]]
    inputs: dict[str, ArtifactDescriptor]
    store: ArtifactStore
    selection_filters: tuple[dict[str, Any], ...] = ()
    adapter: dict[str, Any] | None = None
    _progress_callback: Callable[[float | None, str], None] | None = None
    _log_callback: Callable[[dict[str, Any]], None] | None = None

    def table(self, name: str):
        descriptor = self.inputs[name]
        if descriptor.kind != "table":
            raise ExecutionFailure(f"Input {name} is {descriptor.kind}, not table")
        return apply_selection_filters(
            self.store.read_table(descriptor),
            self.selection_filters,
        )

    def input(self, name: str) -> Any:
        """Read one explicitly named Source/Transform input."""
        descriptor = self.inputs[name]
        if descriptor.kind == "table":
            return self.table(name)
        return self.store.read_value(descriptor)

    def artifact(self, name: str) -> ArtifactDescriptor:
        return self.inputs[name]

    def progress(self, value: float | None = None, message: str = "") -> None:
        """Publish cooperative progress from trusted Python code."""
        if value is not None and not 0 <= value <= 1:
            raise ValueError("progress value must be between 0 and 1")
        if self._progress_callback:
            self._progress_callback(value, message)

    def log(self, message: str, *, level: str = "info", **fields: Any) -> None:
        """Publish one JSON-safe structured execution-log record."""
        if level not in {"debug", "info", "warning", "error"}:
            raise ValueError("log level must be debug, info, warning, or error")
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": str(message),
            "fields": json.loads(json.dumps(fields, ensure_ascii=False, default=str)),
        }
        if self._log_callback:
            self._log_callback(record)

    def dispose(self) -> None:
        """Drop references held by a completed runtime context."""
        self.inputs.clear()
        self._progress_callback = None
        self._log_callback = None
