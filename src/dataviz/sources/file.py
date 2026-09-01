from __future__ import annotations

import pandas as pd

from dataviz.errors import SourceFailure
from dataviz.sources.base import SourceRequest
from dataviz.workspace.assets import resolve_workspace_asset_reference


class FileSourceRunner:
    def execute(self, request: SourceRequest) -> pd.DataFrame:
        definition = request.definition
        if definition.adapter:
            path = request.adapters.resolve_path(
                definition.adapter, definition.path, request.adapter_bindings
            )
        else:
            asset = (
                resolve_workspace_asset_reference(
                    request.workspace_root,
                    request.workspace_assets or {},
                    definition.path,
                    hash_content=False,
                )
                if request.workspace_root is not None
                else None
            )
            path = asset.path if asset is not None else (
                request.definition_path.parent / definition.path
            ).resolve()
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
            if format_name in {"xlsx", "xls"}:
                return pd.read_excel(path, **options)
        except Exception as exc:
            raise SourceFailure(f"Failed to read {format_name} file: {exc}", file=path) from exc
        raise SourceFailure(f"Unsupported file format: {format_name}", file=path)
