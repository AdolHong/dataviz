from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from dataviz.auth import ConnectionResolver
from dataviz.execution.context import ExecutionContext
from dataviz.workspace.models import SourceDefinition


@dataclass(slots=True)
class SourceRequest:
    definition_path: Path
    definition: SourceDefinition
    context: ExecutionContext
    connections: ConnectionResolver


class SourceAdapter(Protocol):
    def execute(self, request: SourceRequest) -> pd.DataFrame: ...

