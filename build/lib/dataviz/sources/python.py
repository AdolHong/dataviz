from __future__ import annotations

import pandas as pd
import pyarrow as pa

from dataviz.errors import SourceFailure
from dataviz.execution.imports import load_entrypoint
from dataviz.sources.base import SourceRequest


class PythonSourceAdapter:
    def execute(self, request: SourceRequest) -> pd.DataFrame:
        definition = request.definition
        if not definition.code:
            raise SourceFailure("Python source requires code", file=request.definition_path)
        code_path = (request.definition_path.parent / definition.code).resolve()
        function = load_entrypoint(code_path, definition.entrypoint)
        try:
            value = function(request.context)
        except Exception as exc:
            raise SourceFailure(f"Python source failed: {exc}", file=code_path) from exc
        if isinstance(value, pd.DataFrame):
            return value
        if isinstance(value, pa.Table):
            return value.to_pandas()
        try:
            return pd.DataFrame(value)
        except Exception as exc:
            raise SourceFailure("Python source must return tabular data", file=code_path) from exc

