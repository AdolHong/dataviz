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
    filters: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    artifacts: dict[str, list[ArtifactDescriptor]] = field(default_factory=dict)
    store: ArtifactStore | None = None

    def table(self, source_id: str) -> pd.DataFrame:
        return self.tables[source_id]

    def filtered_table(self, source_id: str, bindings: dict[str, str] | None = None) -> pd.DataFrame:
        """Return a copy filtered with the current view's effective filters."""
        frame = self.table(source_id).copy()
        fields = bindings or {}
        for filter_id, value in self.filters.items():
            if value is None or value == "" or value == []:
                continue
            field_name = fields.get(filter_id, filter_id)
            if field_name not in frame.columns:
                continue
            if isinstance(value, list):
                if len(value) == 2 and filter_id.endswith(("period", "range")):
                    frame = frame[frame[field_name].between(value[0], value[1])]
                else:
                    frame = frame[frame[field_name].isin(value)]
            else:
                frame = frame[frame[field_name] == value]
        return frame
