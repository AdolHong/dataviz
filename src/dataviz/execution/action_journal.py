"""Durable invocation receipts. A receipt is never a queue for replaying writes."""

from __future__ import annotations

from contextlib import contextmanager
import json
import hashlib
from pathlib import Path
import sqlite3
import time
from typing import Any


class ActionConflict(ValueError):
    """A request ID was reused for a different invocation."""


def action_journal_path(workspace_root: Path) -> Path:
    metadata = workspace_root / ".dataviz" / "standalone.json"
    if metadata.is_file():
        source = Path(json.loads(metadata.read_text())["source"]).resolve()
        identity = hashlib.sha256(str(source).encode()).hexdigest()
        return source.parent / ".dataviz" / "actions" / identity / "receipts.sqlite"
    return workspace_root / ".dataviz" / "actions" / "receipts.sqlite"


def source_mutation_epoch(workspace_root: Path, dashboard_id: str, source: str) -> int:
    """Read-only cache fence shared by tab sessions and standalone snapshots."""
    path = action_journal_path(workspace_root)
    if not path.is_file():
        return 0
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    try:
        row = connection.execute(
            "SELECT version FROM source_epochs WHERE dashboard=? AND source=?", (dashboard_id, source)
        ).fetchone()
        return row[0] if row else 0
    finally:
        connection.close()


class ActionJournal:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS action_receipts (
                    scope TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    deadline REAL NOT NULL,
                    receipt TEXT NOT NULL,
                    PRIMARY KEY (scope, request_id)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS source_epochs (
                    dashboard TEXT NOT NULL, source TEXT NOT NULL, version INTEGER NOT NULL,
                    PRIMARY KEY (dashboard, source)
                )
            """)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _expired(receipt: dict[str, Any], deadline: float) -> dict[str, Any]:
        if receipt["status"] == "running" and deadline < time.time():
            return {**receipt, "status": "unknown", "finished_at": time.time(),
                    "error": {"code": "action_outcome_unknown",
                              "message": "Execution receipt expired; writes may have occurred. Do not retry automatically."}}
        return receipt

    def claim(self, scope: str, request_id: str, fingerprint: str, *,
              deadline: float, invocation: dict[str, Any] | None = None) -> tuple[dict[str, Any], bool]:
        """Atomically reserve execution or return an existing receipt."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT fingerprint, deadline, receipt FROM action_receipts WHERE scope=? AND request_id=?",
                (scope, request_id),
            ).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise ActionConflict("Action request ID already belongs to a different invocation")
                receipt = self._expired(json.loads(row[2]), row[1])
                connection.execute(
                    "UPDATE action_receipts SET receipt=? WHERE scope=? AND request_id=?",
                    (json.dumps(receipt), scope, request_id),
                )
                return receipt, False
            receipt = {"schema": "dataviz/action-receipt/v1", "request_id": request_id,
                       "status": "running", "created_at": time.time(),
                       "invocation": invocation or {},
                       "refresh": {"status": "not_requested"}}
            connection.execute(
                "INSERT INTO action_receipts VALUES (?, ?, ?, ?, ?)",
                (scope, request_id, fingerprint, deadline, json.dumps(receipt)),
            )
            return receipt, True

    def get(self, scope: str, request_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT deadline, receipt FROM action_receipts WHERE scope=? AND request_id=?",
                (scope, request_id),
            ).fetchone()
            if row is None:
                return None
            receipt = self._expired(json.loads(row[1]), row[0])
            connection.execute(
                "UPDATE action_receipts SET receipt=? WHERE scope=? AND request_id=?",
                (json.dumps(receipt), scope, request_id),
            )
            return receipt

    def lookup(self, scope: str, request_id: str, fingerprint: str) -> dict[str, Any] | None:
        """Allow receipt replay even if code or credentials are no longer present."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT fingerprint FROM action_receipts WHERE scope=? AND request_id=?",
                (scope, request_id),
            ).fetchone()
            if row is None:
                return None
            if row[0] != fingerprint:
                raise ActionConflict("Action request ID already belongs to a different invocation")
        return self.get(scope, request_id)

    def finish(self, scope: str, request_id: str, outcome: dict[str, Any], *,
               dashboard_id: str | None = None) -> dict[str, Any]:
        if outcome.get("status") not in {"succeeded", "failed", "unknown"}:
            raise ValueError("Action completion requires a terminal outcome")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT deadline, receipt FROM action_receipts WHERE scope=? AND request_id=?",
                (scope, request_id),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            previous = self._expired(json.loads(row[1]), row[0])
            if previous["status"] != "running":
                return previous
            receipt = {**previous, **outcome, "request_id": request_id, "finished_at": time.time()}
            if outcome["status"] == "succeeded" and outcome.get("invalidations"):
                receipt["refresh"] = {"status": "pending"}
            if dashboard_id is not None and outcome["status"] == "succeeded":
                for reference in set(outcome.get("invalidations", [])):
                    if reference.startswith("source:"):
                        connection.execute(
                            "INSERT INTO source_epochs VALUES (?, ?, 1) "
                            "ON CONFLICT(dashboard, source) DO UPDATE SET version=version+1",
                            (dashboard_id, reference),
                        )
            connection.execute(
                "UPDATE action_receipts SET receipt=? WHERE scope=? AND request_id=?",
                (json.dumps(receipt, allow_nan=False), scope, request_id),
            )
            return receipt

    def set_refresh(self, scope: str, request_id: str, refresh: dict[str, Any], *,
                    expected: dict[str, Any] | None = None) -> dict[str, Any]:
        """Update refresh feedback without changing or replaying the write outcome."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT receipt FROM action_receipts WHERE scope=? AND request_id=?",
                (scope, request_id),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            receipt = json.loads(row[0])
            if receipt["status"] != "succeeded":
                raise ValueError("Only a successful Action can schedule refresh")
            if expected is not None and any(receipt["refresh"].get(key) != value
                                            for key, value in expected.items()):
                return receipt
            receipt["refresh"] = refresh
            connection.execute(
                "UPDATE action_receipts SET receipt=? WHERE scope=? AND request_id=?",
                (json.dumps(receipt, allow_nan=False), scope, request_id),
            )
            return receipt

    def claim_refresh(self, scope: str, request_id: str, *, retry: bool = False):
        """Only one caller may schedule refresh; polling never repeats scheduling."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT receipt FROM action_receipts WHERE scope=? AND request_id=?",
                (scope, request_id),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            receipt = json.loads(row[0])
            allowed = {"pending", "failed"} if retry else {"pending"}
            if receipt["status"] != "succeeded" or receipt["refresh"]["status"] not in allowed:
                return receipt, False
            previous = receipt["refresh"]
            receipt["refresh"] = {"status": "scheduling", "started_at": time.time(),
                                  "previous_run_id": previous.get("run_id")}
            connection.execute(
                "UPDATE action_receipts SET receipt=? WHERE scope=? AND request_id=?",
                (json.dumps(receipt), scope, request_id),
            )
            return receipt, True
