"""Bounded, read-only discovery of explicitly supplied local analysis inputs."""
from __future__ import annotations

import csv
from contextlib import closing
import io
import re
import sqlite3
import time
import tempfile
from pathlib import Path

from dataviz.errors import WorkspaceError

MAX_SAMPLE_BYTES = 256 * 1024
MAX_COLUMNS = 100
MAX_TABLES = 50
MAX_CELL_CHARS = 256


def parse_data_bindings(values: list[str] | None) -> dict[str, Path]:
    bindings = {}
    for value in values or []:
        name, separator, filename = value.partition("=")
        if not separator or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", name) or not filename:
            raise WorkspaceError("--data requires name=path with a stable input name")
        if name in bindings:
            raise WorkspaceError(f"Duplicate --data binding: {name}")
        path = Path(filename).expanduser().resolve()
        local_data_kind(path)
        bindings[name] = path
    return bindings


def snapshot_local_data(path: Path) -> bytes:
    if local_data_kind(path) == "csv":
        return path.read_bytes()
    # SQLite backup includes committed WAL data; copying just the .db file does not.
    with tempfile.TemporaryDirectory(prefix="dataviz-sqlite-input-") as directory:
        target = Path(directory) / "snapshot.sqlite"
        deadline = time.monotonic() + 10
        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise WorkspaceError("SQLite input snapshot exceeded 10 seconds", file=path)
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as source:
            with closing(sqlite3.connect(target)) as destination:
                source.backup(destination, pages=256, progress=progress)
        return target.read_bytes()


def enforce_sqlite_read_only(connection) -> None:
    """Protect named local SQL inputs, including ATTACH and write-returning SQL."""
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
               sqlite3.SQLITE_RECURSIVE, sqlite3.SQLITE_TRANSACTION}
    def authorize(action, first, second, database, trigger):
        if action == sqlite3.SQLITE_FUNCTION and second == "load_extension":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
    connection.set_authorizer(authorize)


def local_data_kind(path: Path) -> str:
    if not path.is_file():
        raise WorkspaceError("Local data must be an existing file", file=path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        with path.open("rb") as stream:
            if stream.read(16) != b"SQLite format 3\x00":
                raise WorkspaceError("Not a SQLite database", file=path)
        return "sqlite"
    raise WorkspaceError("Local data currently supports CSV and SQLite", file=path)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sample_type(values: list[str]) -> str:
    present = [value for value in values if value != ""]
    if not present:
        return "unknown"
    if all(re.fullmatch(r"-?(0|[1-9][0-9]*)", value) for value in present):
        return "integer"
    if all(re.fullmatch(r"-?(0|[1-9][0-9]*)\.[0-9]+", value) for value in present):
        return "decimal"
    return "text"


def inspect_local_data(path: Path, *, rows: int = 5, table: str | None = None) -> dict:
    """Inspect samples, never COUNT(*) or load all rows. Values may be sensitive."""
    if not 0 <= rows <= 20:
        raise WorkspaceError("Sample rows must be between 0 and 20")
    path = path.expanduser().resolve()
    kind = local_data_kind(path)
    result = {
        "schema": "dataviz/local-data-inspection/v1", "kind": kind,
        "name": path.name, "bytes": path.stat().st_size,
        "read_only": True, "total_rows": None,
        "limits": {"sample_rows": rows, "columns": MAX_COLUMNS,
                   "tables": MAX_TABLES, "cell_chars": MAX_CELL_CHARS},
    }
    if kind == "csv":
        if table is not None:
            raise WorkspaceError("--table applies only to SQLite", file=path)
        # Bounded input as well as output: no full read, dtype inference or count.
        with path.open("rb") as stream:
            raw = stream.read(MAX_SAMPLE_BYTES)
        result["limits"]["sample_bytes"] = MAX_SAMPLE_BYTES
        truncated = len(raw) < path.stat().st_size
        if truncated:
            raw = raw[:raw.rfind(b"\n") + 1]
        try:
            reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
            columns = next(reader)
            if not columns or len(columns) > MAX_COLUMNS or len(set(columns)) != len(columns):
                raise ValueError("CSV requires unique headers and at most 100 columns")
            if any(not name or len(name) > MAX_CELL_CHARS for name in columns):
                raise ValueError("CSV headers must be nonempty and at most 256 characters")
            sample = []
            for _ in range(rows):
                row = next(reader, None)
                if row is None:
                    break
                if len(row) != len(columns):
                    raise ValueError("CSV sample row does not match its header")
                sample.append(row)
        except (UnicodeError, csv.Error, ValueError, StopIteration) as exc:
            raise WorkspaceError("Cannot inspect CSV within UTF-8/comma/sample limits", file=path,
                                 details={"reason": str(exc)}) from exc
        result.update({
            "columns": [{"name": name, "sample_type": _sample_type([r[i] for r in sample])}
                        for i, name in enumerate(columns)],
            "rows": [[cell[:MAX_CELL_CHARS] for cell in row] for row in sample],
            "sample_only": True, "input_truncated": truncated,
            "cells_truncated": any(len(cell) > MAX_CELL_CHARS for row in sample for cell in row),
        })
        return result

    # mode=ro neither creates a missing database nor permits SQL writes.
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_SAMPLE_BYTES)
            deadline = time.monotonic() + 2
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            names = connection.execute(
                "SELECT name, type FROM sqlite_schema WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT ?", (MAX_TABLES + 1,)
            ).fetchall()
            result["tables"] = [{"name": n[:MAX_CELL_CHARS], "type": t} for n, t in names[:MAX_TABLES]]
            result["tables_truncated"] = len(names) > MAX_TABLES
            if table is None:
                result["hint"] = "Use --table <name> to inspect columns and preview rows; --rows 0 omits values."
                return result
            selected = connection.execute(
                "SELECT type FROM sqlite_schema WHERE name=? AND type='table'", (table,)
            ).fetchone()
            if selected is None:
                raise WorkspaceError("Choose an existing SQLite table (views are not previewed)", file=path)
            if len(table) > MAX_CELL_CHARS:
                raise WorkspaceError("Table name exceeds inspection limits", file=path)
            columns = connection.execute("SELECT name, type FROM pragma_table_info(?) LIMIT ?",
                                         (table, MAX_COLUMNS + 1)).fetchall()
            if len(columns) > MAX_COLUMNS or any(len(n) > MAX_CELL_CHARS for n, _ in columns):
                raise WorkspaceError("Table exceeds inspection column limits", file=path)
            sample = connection.execute(f"SELECT * FROM {_quote_identifier(table)} LIMIT ?", (rows,)).fetchall()
            def cell(value):
                if isinstance(value, bytes):
                    return {"type": "blob", "bytes": len(value)}
                return value[:MAX_CELL_CHARS] if isinstance(value, str) else value
            result.update({"table": table, "columns": [{"name": n, "declared_type": t[:MAX_CELL_CHARS]}
                                                       for n, t in columns],
                           "rows": [[cell(value) for value in row] for row in sample],
                           "sample_only": True,
                           "cells_truncated": any(isinstance(v, str) and len(v) > MAX_CELL_CHARS
                                                  for row in sample for v in row)})
            return result
    except sqlite3.Error as exc:
        raise WorkspaceError("Cannot inspect SQLite within read-only/sample limits", file=path,
                             details={"reason": str(exc)}) from exc
