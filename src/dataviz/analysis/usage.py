from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
import time
from typing import Iterable


LOGGER = logging.getLogger(__name__)
USAGE_SCHEMA = "dataviz/analysis-usage/v1"
DEFAULT_BUSY_TIMEOUT_MS = 1_500


@dataclass(frozen=True)
class UsageKey:
    subject_kind: str
    subject_ref: str
    action_kind: str
    actor_kind: str


def _execute_with_busy_retry(
    connection: sqlite3.Connection,
    statement: str,
    *,
    busy_timeout_ms: int,
) -> sqlite3.Cursor:
    """Retry SQLite initialization locks within the caller's bounded budget."""

    timeout_seconds = max(0, busy_timeout_ms) / 1_000
    deadline = time.monotonic() + timeout_seconds
    delay = 0.005
    while True:
        remaining_ms = max(0, int((deadline - time.monotonic()) * 1_000))
        connection.execute(f"PRAGMA busy_timeout={remaining_ms}")
        try:
            return connection.execute(statement)
        except sqlite3.OperationalError as error:
            locked = "locked" in str(error).lower() or "busy" in str(error).lower()
            remaining = deadline - time.monotonic()
            if not locked or remaining <= 0:
                raise
            pause = min(delay, remaining)
            time.sleep(pause)
            delay = min(delay * 2, 0.05)


def _timestamp(value: datetime | str | None = None) -> str:
    if value is None:
        moment = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _connect(root: Path, *, busy_timeout_ms: int) -> sqlite3.Connection:
    path = root.resolve() / ".dataviz" / "usage.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        path,
        timeout=max(0, busy_timeout_ms) / 1_000,
        isolation_level=None,
    )
    connection.execute(f"PRAGMA busy_timeout={max(0, busy_timeout_ms)}")
    try:
        current_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        if current_mode != "wal":
            _execute_with_busy_retry(
                connection,
                "PRAGMA journal_mode=WAL",
                busy_timeout_ms=busy_timeout_ms,
            )
        connection.execute("PRAGMA synchronous=NORMAL")
        _execute_with_busy_retry(
            connection,
            """
        CREATE TABLE IF NOT EXISTS usage (
            subject_kind TEXT NOT NULL,
            subject_ref TEXT NOT NULL,
            action_kind TEXT NOT NULL,
            actor_kind TEXT NOT NULL,
            use_count INTEGER NOT NULL CHECK (use_count >= 0),
            last_used_at TEXT NOT NULL,
            PRIMARY KEY (subject_kind, subject_ref, action_kind, actor_kind)
        ) WITHOUT ROWID
        """,
            busy_timeout_ms=busy_timeout_ms,
        )
        connection.execute(f"PRAGMA busy_timeout={max(0, busy_timeout_ms)}")
    except Exception:
        connection.close()
        raise
    return connection


def record_usage(
    workspace: Path,
    key: UsageKey,
    *,
    used_at: datetime | str | None = None,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> None:
    """Atomically increment one generic usage aggregate."""

    connection = _connect(workspace, busy_timeout_ms=busy_timeout_ms)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO usage (
                subject_kind, subject_ref, action_kind, actor_kind,
                use_count, last_used_at
            ) VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(subject_kind, subject_ref, action_kind, actor_kind)
            DO UPDATE SET
                use_count = usage.use_count + 1,
                last_used_at = CASE
                    WHEN excluded.last_used_at > usage.last_used_at
                    THEN excluded.last_used_at
                    ELSE usage.last_used_at
                END
            """,
            (
                key.subject_kind,
                key.subject_ref,
                key.action_kind,
                key.actor_kind,
                _timestamp(used_at),
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def record_usage_best_effort(
    workspace: Path,
    key: UsageKey,
    *,
    used_at: datetime | str | None = None,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> bool:
    """Record usage without allowing telemetry to change a successful action."""

    try:
        record_usage(
            workspace,
            key,
            used_at=used_at,
            busy_timeout_ms=busy_timeout_ms,
        )
        return True
    except Exception as error:  # pragma: no cover - exact SQLite text is platform-owned.
        LOGGER.warning(
            "Dataviz usage aggregation failed; the successful action is unchanged",
            extra={
                "code": "analysis_usage_write_failed",
                "subject_kind": key.subject_kind,
                "subject_ref": key.subject_ref,
                "action_kind": key.action_kind,
                "actor_kind": key.actor_kind,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        return False


def read_usage(
    workspace: Path,
    *,
    keys: Iterable[UsageKey] | None = None,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> dict[UsageKey, dict[str, int | str]]:
    path = workspace.resolve() / ".dataviz" / "usage.sqlite"
    if not path.is_file():
        return {}
    connection = _connect(workspace, busy_timeout_ms=busy_timeout_ms)
    try:
        rows = connection.execute(
            """
            SELECT subject_kind, subject_ref, action_kind, actor_kind,
                   use_count, last_used_at
            FROM usage
            """
        ).fetchall()
    finally:
        connection.close()
    selected = set(keys) if keys is not None else None
    result = {}
    for subject_kind, subject_ref, action_kind, actor_kind, count, last_used in rows:
        key = UsageKey(subject_kind, subject_ref, action_kind, actor_kind)
        if selected is None or key in selected:
            result[key] = {"use_count": int(count), "last_used_at": str(last_used)}
    return result


def read_usage_best_effort(
    workspace: Path,
    *,
    keys: Iterable[UsageKey] | None = None,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> dict[UsageKey, dict[str, int | str]]:
    try:
        return read_usage(
            workspace,
            keys=keys,
            busy_timeout_ms=busy_timeout_ms,
        )
    except Exception as error:  # pragma: no cover - exact SQLite text is platform-owned.
        LOGGER.warning(
            "Dataviz usage overview is unavailable; Catalog order and results are unchanged",
            extra={
                "code": "analysis_usage_read_failed",
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        return {}


def dashboard_query_usage(dashboard_id: str) -> UsageKey:
    return UsageKey("dashboard", dashboard_id, "query_succeeded", "human")


def output_analysis_usage(reference: str) -> UsageKey:
    return UsageKey("output", reference, "analyze_run_succeeded", "ai")
