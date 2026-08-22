from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text

from dataviz.errors import SourceFailure
from dataviz.sources.base import SourceRequest


class SqlSourceAdapter:
    def execute(self, request: SourceRequest) -> pd.DataFrame:
        definition = request.definition
        if not definition.code or not definition.connection:
            raise SourceFailure("SQL source requires code and connection", file=request.definition_path)
        code_path = (request.definition_path.parent / definition.code).resolve()
        if not code_path.exists():
            raise SourceFailure("SQL file does not exist", file=code_path)
        query = code_path.read_text(encoding="utf-8")
        parameters = {name: request.context.params.get(name) for name in definition.params}
        try:
            engine = create_engine(request.connections.resolve_url(definition.connection))
            with engine.connect() as connection:
                return pd.read_sql_query(text(query), connection, params=parameters)
        except Exception as exc:
            raise SourceFailure(f"SQL query failed: {exc}", file=code_path) from exc

