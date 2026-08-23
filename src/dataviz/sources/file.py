from __future__ import annotations

from pathlib import Path

import pandas as pd

from dataviz.errors import SourceFailure
from dataviz.sources.base import SourceRequest


class FileSourceRunner:
    def execute(self, request: SourceRequest) -> pd.DataFrame:
        definition = request.definition
        if not definition.path:
            raise SourceFailure("File source requires path", file=request.definition_path)
        if definition.adapter:
            path = request.adapters.resolve_path(
                definition.adapter, definition.path, request.adapter_bindings
            )
        else:
            path = (request.definition_path.parent / definition.path).resolve()
        if not path.exists():
            raise SourceFailure("Data file does not exist", file=path)
        format_name = (definition.format or path.suffix.lstrip(".")).lower()
        options = definition.options.copy()
        try:
            if format_name in {"csv", "txt"}:
                return pd.read_csv(path, **options)
            if format_name in {"parquet", "pq"}:
                return pd.read_parquet(path, **options)
            if format_name in {"json", "jsonl"}:
                if format_name == "jsonl":
                    options.setdefault("lines", True)
                return pd.read_json(path, **options)
            if format_name in {"xlsx", "xls", "excel"}:
                return pd.read_excel(path, **options)
        except Exception as exc:
            raise SourceFailure(f"Failed to read {format_name} file: {exc}", file=path) from exc
        raise SourceFailure(f"Unsupported file format: {format_name}", file=path)
