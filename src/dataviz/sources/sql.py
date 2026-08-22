from __future__ import annotations

import re

import pandas as pd
from sqlalchemy import create_engine, text

from dataviz.errors import SourceFailure
from dataviz.sources.base import SourceRequest


class SqlSourceAdapter:
    def execute(self, request: SourceRequest) -> pd.DataFrame:
        definition = request.definition
        adapter_name = definition.adapter or definition.connection
        if not definition.code or not adapter_name:
            raise SourceFailure("SQL source requires code and adapter", file=request.definition_path)
        code_path = (request.definition_path.parent / definition.code).resolve()
        if not code_path.exists():
            raise SourceFailure("SQL file does not exist", file=code_path)
        query = code_path.read_text(encoding="utf-8")
        parameters = {name: request.context.params.get(name) for name in definition.params}
        try:
            _, adapter = request.connections.resolve(adapter_name, request.adapter_bindings)
            if adapter.type == "duckdb":
                import duckdb

                database = adapter.database or ":memory:"
                if database != ":memory:" and not __import__("pathlib").Path(database).is_absolute():
                    database = str((request.context.workspace_root / database).resolve())
                duck_query = re.sub(r":([A-Za-z_]\w*)", r"$\1", query)
                connection = duckdb.connect(database, read_only=bool(adapter.options.get("read_only", False)))
                try:
                    return connection.execute(duck_query, parameters).fetchdf()
                finally:
                    connection.close()
            engine = create_engine(
                request.connections.resolve_url(adapter_name, request.adapter_bindings),
                **({"connect_args": adapter.options} if adapter.type == "sqlalchemy" else {}),
            )
            with engine.connect() as connection:
                return pd.read_sql_query(text(query), connection, params=parameters)
        except Exception as exc:
            raise SourceFailure(f"SQL query failed: {exc}", file=code_path) from exc
