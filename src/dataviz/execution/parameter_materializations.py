"""Workspace-shared immutable materializations for SQL Parameter Domains."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, TYPE_CHECKING

import pandas as pd
import duckdb

from dataviz.auth import AdapterResolver
from dataviz.errors import ExecutionFailure, QueryTimeoutFailure
from dataviz.execution.parameters import normalize_query_parameter_state
from dataviz.sources.sql import execute_sql_query
from dataviz.value_contract import (
    ValueContractViolation,
    json_compatible_value,
    json_value_signature,
    normalize_control_value,
)
from dataviz.workspace.models import ParameterDomainOptionDefinition

if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


LOOKUP_DEFAULT_LIMIT = 50
LOOKUP_MAX_LIMIT = 100
_LEASE_SECONDS = 900
_READER_PIN_SECONDS = 120


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frame_hash(frame: pd.DataFrame) -> str:
    payload = frame.to_json(orient="split", date_format="iso", force_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_scalar(value: Any) -> Any:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    elif hasattr(value, "item") and callable(value.item):
        value = value.item()
    return json_compatible_value(value)


def _is_null(value: Any) -> bool:
    if isinstance(value, (list, tuple, set, dict)):
        return False
    result = pd.isna(value)
    return bool(result) if not hasattr(result, "__len__") else False


def _normalized_search(value: Any) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", str(value or "")).casefold().split()
    )


def _encode_cursor(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> dict[str, Any]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception as error:
        raise ExecutionFailure(
            "Parameter Lookup cursor is invalid",
            details={"code": "parameter_lookup_cursor_invalid"},
        ) from error
    if not isinstance(payload, dict):
        raise ExecutionFailure(
            "Parameter Lookup cursor is invalid",
            details={"code": "parameter_lookup_cursor_invalid"},
        )
    return payload


@dataclass(frozen=True, slots=True)
class MaterializationRecord:
    key: str
    domain: str
    generation: str | None
    data_path: Path | None
    status: str
    rows: int
    content_hash: str | None
    created_at: float | None
    refresh_due_at: float | None
    expires_at: float | None
    last_error: dict[str, Any] | None = None

    def freshness(self, now: float | None = None) -> str:
        current = time.time() if now is None else now
        if self.generation is None:
            return "building" if self.status == "building" else "missing"
        if self.expires_at is not None and current >= self.expires_at:
            return "expired"
        if self.refresh_due_at is not None and current >= self.refresh_due_at:
            return "stale"
        return "fresh"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "domain": self.domain,
            "generation": self.generation,
            "status": self.status,
            "freshness": self.freshness(),
            "rows": self.rows,
            "content_hash": self.content_hash,
            "created_at": (
                datetime.fromtimestamp(self.created_at, timezone.utc).isoformat()
                if self.created_at is not None
                else None
            ),
            "refresh_due_at": (
                datetime.fromtimestamp(self.refresh_due_at, timezone.utc).isoformat()
                if self.refresh_due_at is not None
                else None
            ),
            "expires_at": (
                datetime.fromtimestamp(self.expires_at, timezone.utc).isoformat()
                if self.expires_at is not None
                else None
            ),
            "last_error": self.last_error,
        }


class ParameterMaterializationStore:
    """One Workspace-local registry shared by every Dashboard, user and tab."""

    def __init__(self, workspace: LoadedWorkspace):
        self.workspace = workspace
        self.root = workspace.root / ".dataviz" / "parameter-materializations"
        self.objects = self.root / "objects"
        self.index_path = self.root / "index.sqlite"
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects.mkdir(parents=True, exist_ok=True)
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._frames_guard = threading.Lock()
        self._frames: dict[str, pd.DataFrame] = {}
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.index_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS materializations (
                    materialization_key TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    definition_hash TEXT NOT NULL,
                    generation TEXT,
                    data_path TEXT,
                    status TEXT NOT NULL,
                    rows INTEGER NOT NULL DEFAULT 0,
                    content_hash TEXT,
                    created_at REAL,
                    refresh_due_at REAL,
                    expires_at REAL,
                    lease_until REAL,
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reader_pins (
                    pin_id TEXT PRIMARY KEY,
                    generation TEXT NOT NULL,
                    data_path TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())

    def identity(
        self, dashboard: LoadedDashboard, domain_id: str
    ) -> tuple[str, str, Path, dict[str, Any]]:
        definition_path, definition = dashboard.parameter_domains[domain_id]
        code_path = (definition_path.parent / definition.code).resolve()
        resolver = AdapterResolver(self.workspace.root)
        actual_name, adapter_definition = resolver.resolve(
            definition.adapter, dashboard.definition.adapters
        )
        definition_payload = definition.model_dump(mode="json", by_alias=True)
        definition_hash = hashlib.sha256(
            json.dumps(
                {
                    "definition": definition_payload,
                    "code_hash": hashlib.sha256(code_path.read_bytes()).hexdigest(),
                    "definition_path": str(definition_path.relative_to(self.workspace.root)),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        payload = {
            "workspace": self.workspace.definition.id,
            "definition_hash": definition_hash,
            "adapter": actual_name,
            "adapter_fingerprint": resolver.fingerprint(
                definition.adapter, dashboard.definition.adapters
            ),
            "visibility_scope": adapter_definition.visibility_scope,
        }
        key = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return key, definition_hash, code_path, resolver.runtime_config(
            definition.adapter, dashboard.definition.adapters
        )

    @staticmethod
    def _record(row: sqlite3.Row | None, *, key: str, domain_id: str) -> MaterializationRecord:
        if row is None:
            return MaterializationRecord(key, domain_id, None, None, "missing", 0, None, None, None, None)
        error = json.loads(row["last_error"]) if row["last_error"] else None
        return MaterializationRecord(
            key=key,
            domain=domain_id,
            generation=row["generation"],
            data_path=Path(row["data_path"]) if row["data_path"] else None,
            status=row["status"],
            rows=int(row["rows"] or 0),
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            refresh_due_at=row["refresh_due_at"],
            expires_at=row["expires_at"],
            last_error=error,
        )

    def status(self, dashboard: LoadedDashboard, domain_id: str) -> MaterializationRecord:
        key, _, _, _ = self.identity(dashboard, domain_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM materializations WHERE materialization_key=?", (key,)
            ).fetchone()
        record = self._record(row, key=key, domain_id=domain_id)
        if record.data_path is not None and not record.data_path.is_file():
            return MaterializationRecord(key, domain_id, None, None, "missing", 0, None, None, None, None)
        return record

    def _claim(self, key: str, domain_id: str, definition_hash: str, *, force: bool) -> bool:
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, lease_until FROM materializations WHERE materialization_key=?",
                (key,),
            ).fetchone()
            if (
                row is not None
                and row["status"] == "building"
                and float(row["lease_until"] or 0) > now
            ):
                connection.rollback()
                return False
            connection.execute(
                """
                INSERT INTO materializations (
                    materialization_key, domain_id, definition_hash, status,
                    rows, lease_until, updated_at
                ) VALUES (?, ?, ?, 'building', 0, ?, ?)
                ON CONFLICT(materialization_key) DO UPDATE SET
                    status='building', lease_until=excluded.lease_until,
                    definition_hash=excluded.definition_hash, updated_at=excluded.updated_at
                """,
                (key, domain_id, definition_hash, now + _LEASE_SECONDS, _utc_now()),
            )
        return True

    def build(self, dashboard: LoadedDashboard, domain_id: str, *, force: bool = False) -> MaterializationRecord:
        key, definition_hash, code_path, adapter = self.identity(dashboard, domain_id)
        definition = dashboard.parameter_domains[domain_id][1]
        with self._lock_for(key):
            current = self.status(dashboard, domain_id)
            if not force and current.freshness() == "fresh":
                return current
            if not self._claim(key, domain_id, definition_hash, force=force):
                return self.status(dashboard, domain_id)
            temporary: Path | None = None
            try:
                query = code_path.read_text(encoding="utf-8")
                frame: pd.DataFrame | None = None
                for attempt in range(definition.timeout_retries + 1):
                    run_id = f"parameter_materialization_{uuid.uuid4().hex[:16]}"
                    try:
                        frame = execute_sql_query(
                            adapter=adapter,
                            query=query,
                            parameters={},
                            timeout_seconds=definition.timeout_seconds,
                            workspace_root=self.workspace.root,
                            run_id=run_id,
                            node_id=f"parameter-domain:{domain_id}",
                            definition_path=code_path,
                        )
                        break
                    except QueryTimeoutFailure:
                        if attempt >= definition.timeout_retries:
                            raise
                assert frame is not None
                if len(frame) > definition.max_rows:
                    raise ExecutionFailure(
                        f"Parameter Domain {domain_id} returned {len(frame)} rows; max_rows is {definition.max_rows}",
                        file=code_path,
                        details={
                            "code": "parameter_materialization_row_limit",
                            "domain": domain_id,
                            "rows": len(frame),
                            "max_rows": definition.max_rows,
                        },
                    )
                content_hash = _frame_hash(frame)
                generation = f"pm_{time.time_ns()}_{content_hash[:12]}"
                key_root = self.objects / key
                temporary = key_root / f".{generation}.{uuid.uuid4().hex}.tmp"
                final = key_root / generation
                temporary.mkdir(parents=True, exist_ok=False)
                data_path = temporary / "data.parquet"
                frame.to_parquet(data_path, index=False)
                byte_size = data_path.stat().st_size
                if byte_size > definition.max_bytes:
                    raise ExecutionFailure(
                        f"Parameter Domain {domain_id} materialization exceeds max_bytes",
                        file=code_path,
                        details={
                            "code": "parameter_materialization_byte_limit",
                            "domain": domain_id,
                            "bytes": byte_size,
                            "max_bytes": definition.max_bytes,
                        },
                    )
                created = time.time()
                manifest = {
                    "schema": "dataviz/parameter-materialization/v1",
                    "key": key,
                    "domain": domain_id,
                    "generation": generation,
                    "definition_hash": definition_hash,
                    "content_hash": content_hash,
                    "rows": len(frame),
                    "bytes": byte_size,
                    "columns": [str(value) for value in frame.columns],
                    "created_at": datetime.fromtimestamp(created, timezone.utc).isoformat(),
                    "refresh_due_at": datetime.fromtimestamp(
                        created + definition.materialization.refresh_after_seconds,
                        timezone.utc,
                    ).isoformat(),
                    "expires_at": datetime.fromtimestamp(
                        created + definition.materialization.expire_after_seconds,
                        timezone.utc,
                    ).isoformat(),
                }
                (temporary / "manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                key_root.mkdir(parents=True, exist_ok=True)
                os.replace(temporary, final)
                final_data = final / "data.parquet"
                with self._connect() as connection:
                    connection.execute(
                        """
                        UPDATE materializations SET generation=?, data_path=?, status='ready',
                            rows=?, content_hash=?, created_at=?, refresh_due_at=?, expires_at=?,
                            lease_until=NULL, last_error=NULL, updated_at=?
                        WHERE materialization_key=?
                        """,
                        (
                            generation,
                            str(final_data),
                            len(frame),
                            content_hash,
                            created,
                            created + definition.materialization.refresh_after_seconds,
                            created + definition.materialization.expire_after_seconds,
                            _utc_now(),
                            key,
                        ),
                    )
                with self._frames_guard:
                    self._frames[generation] = frame.copy(deep=True)
                return self.status(dashboard, domain_id)
            except Exception as error:
                if temporary is not None:
                    shutil.rmtree(temporary, ignore_errors=True)
                payload = {
                    "code": getattr(error, "details", {}).get(
                        "code", "parameter_materialization_failed"
                    ),
                    "type": type(error).__name__,
                    "message": str(error),
                }
                with self._connect() as connection:
                    connection.execute(
                        """
                        UPDATE materializations SET status='refresh_failed', lease_until=NULL,
                            last_error=?, updated_at=? WHERE materialization_key=?
                        """,
                        (json.dumps(payload, ensure_ascii=False), _utc_now(), key),
                    )
                raise

    def ensure(
        self,
        dashboard: LoadedDashboard,
        domain_id: str,
        *,
        refresh: bool = False,
        background: bool = True,
    ) -> MaterializationRecord:
        record = self.status(dashboard, domain_id)
        freshness = record.freshness()
        if refresh or freshness in {"stale", "missing", "expired"}:
            if background:
                thread = threading.Thread(
                    target=self._background_build,
                    args=(dashboard, domain_id, refresh),
                    daemon=True,
                    name=f"dataviz-parameter-{domain_id}",
                )
                thread.start()
                if record.generation and freshness != "expired":
                    return record
                claimed = self.status(dashboard, domain_id)
                return claimed if claimed.status != "missing" else replace(record, status="building")
            return self.build(dashboard, domain_id, force=refresh or freshness != "fresh")
        return record

    def _background_build(self, dashboard: LoadedDashboard, domain_id: str, force: bool) -> None:
        try:
            self.build(dashboard, domain_id, force=force)
        except Exception:
            return

    @contextmanager
    def _reader_pin(self, record: MaterializationRecord):
        """Protect one immutable generation while a reader opens its Parquet file."""

        if record.generation is None or record.data_path is None:
            yield
            return
        pin_id = f"pin_{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute("DELETE FROM reader_pins WHERE expires_at <= ?", (time.time(),))
            connection.execute(
                "INSERT INTO reader_pins(pin_id, generation, data_path, expires_at) VALUES (?, ?, ?, ?)",
                (
                    pin_id,
                    record.generation,
                    str(record.data_path),
                    time.time() + _READER_PIN_SECONDS,
                ),
            )
        try:
            yield
        finally:
            with self._connect() as connection:
                connection.execute("DELETE FROM reader_pins WHERE pin_id=?", (pin_id,))

    def _frame(self, record: MaterializationRecord) -> pd.DataFrame:
        if record.generation is None or record.data_path is None:
            raise ExecutionFailure(
                f"Parameter Domain {record.domain} has no materialization",
                details={"code": "parameter_materialization_unavailable", "domain": record.domain},
            )
        if record.freshness() == "expired":
            raise ExecutionFailure(
                f"Parameter Domain {record.domain} materialization has expired",
                details={"code": "parameter_materialization_expired", "domain": record.domain},
            )
        with self._frames_guard:
            cached = self._frames.get(record.generation)
            if cached is not None:
                return cached.copy(deep=True)
        with self._reader_pin(record):
            frame = pd.read_parquet(record.data_path)
        with self._frames_guard:
            self._frames[record.generation] = frame.copy(deep=True)
        return frame

    @staticmethod
    def _predicate(frame: pd.DataFrame, field: str, state: Mapping[str, Any]) -> pd.DataFrame:
        selection = state.get("selection")
        if selection == "all":
            return frame
        if selection == "none":
            return frame.iloc[0:0]
        values = list(state.get("value") or ())
        signatures = {json_value_signature(item) for item in values}
        matches = frame[field].map(
            lambda item: False
            if _is_null(item)
            else json_value_signature(_json_scalar(item)) in signatures
        )
        if selection == "exclude":
            matches = ~matches
        return frame[matches]

    @staticmethod
    def _choice(definition: Any, row: Any) -> dict[str, Any] | None:
        options = definition.options
        assert isinstance(options, ParameterDomainOptionDefinition)
        raw = row[options.value_field]
        if _is_null(raw):
            return None
        candidate = _json_scalar(raw)
        try:
            if definition.type == "multiple_select":
                value = normalize_control_value(definition, [candidate], enforce_required=False)[0]
            else:
                value = normalize_control_value(definition, candidate, enforce_required=False)
        except (ValueContractViolation, ValueError) as error:
            raise ExecutionFailure(
                f"Parameter Domain value for {definition.id} violates value_type: {error}",
                details={"code": "parameter_domain_value_invalid", "parameter": definition.id},
            ) from error
        label_raw = row[options.label_field] if options.label_field else value
        choice: dict[str, Any] = {
            "value": value,
            "label": str(value if _is_null(label_raw) else label_raw),
        }
        for output, field in (
            ("description", options.description_field),
            ("group", options.group_field),
        ):
            if field and not _is_null(row[field]):
                choice[output] = str(row[field])
        if options.keywords_field and not _is_null(row[options.keywords_field]):
            raw_keywords = row[options.keywords_field]
            choice["keywords"] = (
                [str(item) for item in raw_keywords]
                if isinstance(raw_keywords, (list, tuple, set))
                else [item.strip() for item in str(raw_keywords).split(",") if item.strip()]
            )
        if options.disabled_field:
            choice["disabled"] = bool(row[options.disabled_field])
        if options.sort_field and not _is_null(row[options.sort_field]):
            choice["_sort"] = _json_scalar(row[options.sort_field])
        return choice

    @staticmethod
    def _quoted_field(field: str) -> str:
        return '"' + field.replace('"', '""') + '"'

    @staticmethod
    def _lookup_parent_predicate(
        options: ParameterDomainOptionDefinition,
        parent_states: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[str], list[Any]]:
        predicates: list[str] = []
        parameters: list[Any] = []
        for parent, binding in options.depends_on.items():
            state = dict(parent_states.get(parent) or {"selection": "all", "value": []})
            selection = state.get("selection")
            raw_value = state.get("value")
            if selection is None:
                # Only multiple_select owns all/include/exclude/none. Scalar
                # parents use {value: scalar}; list-valued free inputs use
                # {value: [...]}. Both mean an inclusive parent predicate.
                # Keep 0 and false as real operands and treat only null/empty
                # collections as no matching parent value.
                selection = "none" if raw_value is None else "include"
                values = (
                    list(raw_value)
                    if isinstance(raw_value, (list, tuple))
                    else [raw_value]
                )
            else:
                values = list(raw_value or ())
            if selection == "all":
                continue
            if selection == "none" or not values:
                predicates.append("FALSE")
                continue
            field = ParameterMaterializationStore._quoted_field(binding.field)
            placeholders = ", ".join("?" for _ in values)
            if selection == "include":
                predicates.append(f"{field} IN ({placeholders})")
            else:
                # pandas' previous exclude semantics retained null rows because
                # null never matched an excluded operand.
                predicates.append(f"({field} IS NULL OR {field} NOT IN ({placeholders}))")
            parameters.extend(values)
        return predicates, parameters

    def _lookup_projected(
        self,
        record: MaterializationRecord,
        definition: Any,
        *,
        parent_states: Mapping[str, Mapping[str, Any]],
        search: str,
        limit: int,
        position: int,
        selected: list[Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        """Query one immutable Parquet generation without scanning it in Python."""

        options = definition.options
        assert isinstance(options, ParameterDomainOptionDefinition)
        assert record.data_path is not None
        fields = list(dict.fromkeys([
            options.value_field,
            *(field for field in (
                options.label_field,
                options.description_field,
                options.group_field,
                options.keywords_field,
                options.sort_field,
                options.disabled_field,
            ) if field),
        ]))
        quoted_fields = ", ".join(self._quoted_field(field) for field in fields)
        parent_predicates, parent_parameters = self._lookup_parent_predicate(
            options, parent_states
        )
        value_field = self._quoted_field(options.value_field)
        label_field = self._quoted_field(options.label_field or options.value_field)
        keywords_field = (
            self._quoted_field(options.keywords_field)
            if options.keywords_field
            else "''"
        )
        sort_field = (
            self._quoted_field(options.sort_field)
            if options.sort_field
            else value_field
        )
        normalized_value = f"dv_norm(COALESCE(CAST({value_field} AS VARCHAR), ''))"
        normalized_label = f"dv_norm(COALESCE(CAST({label_field} AS VARCHAR), ''))"
        normalized_keywords = f"dv_norm(COALESCE(CAST({keywords_field} AS VARCHAR), ''))"
        haystack = f"CONCAT_WS(' ', {normalized_value}, {normalized_label}, {normalized_keywords})"
        query = _normalized_search(search)
        tokens = query.split() if query else []
        search_predicates = [f"CONTAINS({haystack}, ?)" for _ in tokens]
        where = [f"{value_field} IS NOT NULL", *parent_predicates, *search_predicates]
        where_sql = " AND ".join(where) if where else "TRUE"
        base_parameters = [str(record.data_path), *parent_parameters, *tokens]

        parent_where = [f"{value_field} IS NOT NULL", *parent_predicates]
        parent_where_sql = " AND ".join(parent_where) if parent_where else "TRUE"
        parent_projection = (
            f"SELECT DISTINCT {quoted_fields} FROM read_parquet(?) "
            f"WHERE {parent_where_sql}"
        )
        projection = (
            f"SELECT DISTINCT {quoted_fields} FROM read_parquet(?) WHERE {where_sql}"
        )
        conflict_fields = list(dict.fromkeys([
            options.value_field,
            *(field for field in (
                options.label_field,
                options.description_field,
                options.group_field,
                options.keywords_field,
                options.disabled_field,
            ) if field),
        ]))
        conflict_projection = ", ".join(
            self._quoted_field(field) for field in conflict_fields
        )
        conflict_query = (
            "WITH projected AS ("
            f"SELECT DISTINCT {conflict_projection} FROM read_parquet(?) "
            f"WHERE {parent_where_sql}"
            ") "
            f"SELECT {value_field} FROM projected GROUP BY {value_field} "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )

        with self._reader_pin(record):
            connection = duckdb.connect()
            try:
                connection.create_function(
                    "dv_norm",
                    _normalized_search,
                    parameters=["VARCHAR"],
                    return_type="VARCHAR",
                )
                conflict = connection.execute(
                    conflict_query,
                    [str(record.data_path), *parent_parameters],
                ).fetchone()
                if conflict is not None:
                    raise ExecutionFailure(
                        f"Parameter Domain {options.source} maps one value to conflicting metadata",
                        details={
                            "code": "parameter_domain_metadata_conflict",
                            "domain": options.source,
                            "parameter": definition.id,
                            "value": _json_scalar(conflict[0]),
                        },
                    )
                total = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM ({projection}) projected",
                        base_parameters,
                    ).fetchone()[0]
                )
                if query:
                    rank_sql = (
                        f"CASE WHEN {normalized_value} = ? THEN 0 "
                        f"WHEN {normalized_label} = ? THEN 1 "
                        f"WHEN STARTS_WITH({normalized_value}, ?) OR "
                        f"STARTS_WITH({normalized_label}, ?) THEN 2 "
                        f"WHEN CONTAINS({normalized_keywords}, ?) THEN 3 ELSE 4 END"
                    )
                    rank_parameters = [query, query, query, query, query]
                else:
                    rank_sql = "4"
                    rank_parameters = []
                page_frame = connection.execute(
                    "WITH projected AS (" + projection + ") "
                    f"SELECT {quoted_fields} FROM projected "
                    f"ORDER BY {rank_sql}, COALESCE(CAST({sort_field} AS VARCHAR), ''), "
                    f"{normalized_label}, COALESCE(CAST({value_field} AS VARCHAR), '') "
                    "LIMIT ? OFFSET ?",
                    [*base_parameters, *rank_parameters, limit, position],
                ).fetchdf()
                selected_frame = pd.DataFrame(columns=fields)
                if selected:
                    placeholders = ", ".join("?" for _ in selected)
                    selected_frame = connection.execute(
                        "WITH projected AS (" + parent_projection + ") "
                        f"SELECT {quoted_fields} FROM projected "
                        f"WHERE {value_field} IN ({placeholders})",
                        [str(record.data_path), *parent_parameters, *selected],
                    ).fetchdf()
            finally:
                connection.close()

        page = [
            choice
            for row in page_frame.to_dict(orient="records")
            if (choice := self._choice(definition, row)) is not None
        ]
        selected_by_signature = {}
        for row in selected_frame.to_dict(orient="records"):
            choice = self._choice(definition, row)
            if choice is not None:
                selected_by_signature[json_value_signature(choice["value"])] = choice
        selected_items = []
        for value in selected:
            choice = selected_by_signature.get(json_value_signature(value))
            selected_items.append(
                {
                    **(
                        {key: item for key, item in choice.items() if key != "_sort"}
                        if choice
                        else {"value": value, "label": str(value)}
                    ),
                    "available": choice is not None,
                }
            )
        return page, selected_items, total

    def lookup(
        self,
        dashboard: LoadedDashboard,
        parameter_id: str,
        *,
        parent_states: Mapping[str, Mapping[str, Any]] | None = None,
        search: str = "",
        limit: int = LOOKUP_DEFAULT_LIMIT,
        cursor: str | None = None,
        selected: list[Any] | None = None,
    ) -> dict[str, Any]:
        definitions = {item.id: item for item in dashboard.definition.query_parameters}
        if parameter_id not in definitions:
            raise ExecutionFailure(
                f"Unknown Query Parameter: {parameter_id}",
                details={"code": "query_parameter_unknown", "id": parameter_id},
            )
        definition = definitions[parameter_id]
        options = definition.options
        if not isinstance(options, ParameterDomainOptionDefinition):
            raise ExecutionFailure(
                f"Query Parameter {parameter_id} does not use a SQL Parameter Domain",
                details={"code": "parameter_lookup_not_domain", "parameter": parameter_id},
            )
        raw_parent_states = dict(parent_states or {})
        unknown_parents = sorted(set(raw_parent_states) - set(options.depends_on))
        if unknown_parents:
            raise ExecutionFailure(
                f"Parameter Lookup for {parameter_id} received unrelated parent states: "
                + ", ".join(unknown_parents),
                details={
                    "code": "parameter_lookup_parent_unknown",
                    "parameter": parameter_id,
                    "parents": unknown_parents,
                },
            )
        normalized_parent_states: dict[str, dict[str, Any]] = {}
        for parent, raw_state in raw_parent_states.items():
            try:
                normalized_parent_states[parent] = normalize_query_parameter_state(
                    definitions[parent], raw_state, enforce_required=False
                )
            except (ValueContractViolation, ValueError) as error:
                reason = getattr(error, "message", str(error))
                raise ExecutionFailure(
                    f"Invalid parent Query Parameter {parent}: {reason}",
                    details={
                        "code": "parameter_lookup_parent_state_invalid",
                        "parameter": parameter_id,
                        "parent": parent,
                        "reason": reason,
                    },
                ) from error
        limit = min(max(1, int(limit)), LOOKUP_MAX_LIMIT)
        record = self.ensure(dashboard, options.source, background=True)
        if record.generation is None or record.freshness() == "expired":
            return {
                "schema": "dataviz/parameter-lookup/v1",
                "status": "building" if record.status == "building" else "unavailable",
                "parameter": parameter_id,
                "generation": None,
                "items": [],
                "selected_items": [
                    {"value": value, "label": str(value), "available": False}
                    for value in selected or ()
                ],
                "total": 0,
                "next_cursor": None,
                "freshness": record.freshness(),
                "last_error": record.last_error,
            }
        frame_columns = set(pd.read_parquet(record.data_path, columns=[]).columns)
        if not frame_columns:
            import pyarrow.parquet as parquet

            frame_columns = set(parquet.read_schema(record.data_path).names)
        required_fields = {
            options.value_field,
            *(field for field in (
                options.label_field,
                options.description_field,
                options.group_field,
                options.keywords_field,
                options.sort_field,
                options.disabled_field,
            ) if field),
            *(binding.field for binding in options.depends_on.values()),
        }
        missing = sorted(required_fields - frame_columns)
        if missing:
            raise ExecutionFailure(
                f"Parameter Domain {options.source} is missing fields: " + ", ".join(missing),
                details={
                    "code": "parameter_domain_field_missing",
                    "domain": options.source,
                    "parameter": parameter_id,
                    "fields": missing,
                },
            )
        query = _normalized_search(search)
        signature_payload = {
            "generation": record.generation,
            "parameter": parameter_id,
            "search": query,
            "parents": normalized_parent_states,
        }
        request_signature = hashlib.sha256(
            json.dumps(signature_payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
        position = 0
        if cursor:
            decoded = _decode_cursor(cursor)
            if decoded.get("generation") != record.generation or decoded.get("signature") != request_signature:
                raise ExecutionFailure(
                    "Parameter Lookup cursor belongs to another generation or query",
                    details={
                        "code": "parameter_lookup_cursor_stale",
                        "generation": record.generation,
                    },
                )
            position = int(decoded.get("position") or 0)
        page, selected_items, total = self._lookup_projected(
            record,
            definition,
            parent_states=normalized_parent_states,
            search=query,
            limit=limit,
            position=position,
            selected=list(selected or ()),
        )
        next_position = position + len(page)
        next_cursor = (
            _encode_cursor(
                {
                    "generation": record.generation,
                    "signature": request_signature,
                    "position": next_position,
                }
            )
            if next_position < total
            else None
        )
        return {
            "schema": "dataviz/parameter-lookup/v1",
            "status": "ready",
            "parameter": parameter_id,
            "generation": record.generation,
            "items": [
                {key: value for key, value in choice.items() if key != "_sort"}
                for choice in page
            ],
            "selected_items": selected_items,
            "total": total,
            "next_cursor": next_cursor,
            "freshness": record.freshness(),
            "last_error": record.last_error,
        }

    def list_records(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM materializations ORDER BY domain_id, materialization_key"
            ).fetchall()
        return [
            self._record(row, key=row["materialization_key"], domain_id=row["domain_id"]).as_dict()
            for row in rows
        ]

    def prune_generations(self, *, apply: bool = False) -> dict[str, Any]:
        """Preview or remove superseded immutable generations, never active or pinned ones."""

        now = time.time()
        with self._connect() as connection:
            connection.execute("DELETE FROM reader_pins WHERE expires_at <= ?", (now,))
            active = {
                Path(row["data_path"]).parent.resolve()
                for row in connection.execute(
                    "SELECT data_path FROM materializations WHERE data_path IS NOT NULL"
                ).fetchall()
            }
            pinned = {
                Path(row["data_path"]).parent.resolve()
                for row in connection.execute(
                    "SELECT data_path FROM reader_pins WHERE expires_at > ?", (now,)
                ).fetchall()
            }
        candidates = []
        if self.objects.exists():
            for key_root in sorted(path for path in self.objects.iterdir() if path.is_dir()):
                for generation_root in sorted(path for path in key_root.iterdir() if path.is_dir()):
                    resolved = generation_root.resolve()
                    if resolved in active or resolved in pinned or generation_root.name.startswith("."):
                        continue
                    size = sum(
                        path.stat().st_size
                        for path in generation_root.rglob("*")
                        if path.is_file()
                    )
                    candidates.append(
                        {
                            "generation": generation_root.name,
                            "path": str(generation_root),
                            "bytes": size,
                        }
                    )
        deleted: list[str] = []
        errors: list[dict[str, str]] = []
        if apply:
            for item in candidates:
                path = Path(item["path"])
                if path.parent.parent != self.objects.resolve():
                    errors.append({"path": str(path), "message": "unsafe materialization path"})
                    continue
                try:
                    shutil.rmtree(path)
                    deleted.append(str(path))
                    with self._frames_guard:
                        self._frames.pop(item["generation"], None)
                except OSError as error:
                    errors.append({"path": str(path), "message": str(error)})
        return {
            "mode": "apply" if apply else "dry-run",
            "generations": candidates,
            "candidate_count": len(candidates),
            "candidate_bytes": sum(item["bytes"] for item in candidates),
            "deleted_count": len(deleted),
            "deleted": deleted,
            "errors": errors,
        }
