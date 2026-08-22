from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore


@dataclass(slots=True)
class ExecutionContext:
    workspace_root: Path
    dashboard_root: Path
    run_id: str
    params: dict[str, Any]
    selections: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    artifacts: dict[str, list[ArtifactDescriptor]] = field(default_factory=dict)
    store: ArtifactStore | None = None

    def table(self, source_id: str) -> pd.DataFrame:
        return self.tables[source_id]

    def selected_table(self, source_id: str, bindings: dict[str, str] | None = None) -> pd.DataFrame:
        """Return rows included by the current view's effective selections."""
        frame = self.table(source_id).copy()
        fields = bindings or {}
        for selection_id, value in self.selections.items():
            if value is None or value == "" or value == []:
                continue
            field_name = fields.get(selection_id, selection_id)
            if field_name not in frame.columns:
                continue
            if isinstance(value, list):
                if len(value) == 2 and selection_id.endswith(("period", "range")):
                    frame = frame[frame[field_name].between(value[0], value[1])]
                else:
                    frame = frame[frame[field_name].isin(value)]
            else:
                frame = frame[frame[field_name] == value]
        return frame

    @property
    def filters(self) -> dict[str, Any]:
        """Deprecated compatibility alias."""
        return self.selections

    def filtered_table(self, source_id: str, bindings: dict[str, str] | None = None) -> pd.DataFrame:
        """Deprecated compatibility alias for :meth:`selected_table`."""
        return self.selected_table(source_id, bindings)
