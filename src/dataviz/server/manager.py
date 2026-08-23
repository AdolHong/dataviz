from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from dataviz.execution import Executor, RunResult
from dataviz.execution.events import ExecutionEvent
from dataviz.errors import DatavizError
from dataviz.maintenance import cleanup_workspace_storage
from dataviz.workspace.loader import LoadedWorkspace


@dataclass
class RunRecord:
    run_id: str
    session_id: str
    dashboard_id: str
    requested_parameters: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    events: list[ExecutionEvent] = field(default_factory=list)
    snapshot: RunResult | None = None
    result: RunResult | None = None
    error: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    condition: threading.Condition = field(default_factory=threading.Condition)


class RunManager:
    def __init__(self, workspace: LoadedWorkspace):
        self.workspace = workspace
        self.executors: dict[str, Executor] = {}
        self.records: dict[str, RunRecord] = {}
        self.latest: dict[tuple[str, str], str] = {}
        self.lock = threading.Lock()
        self.maintenance_lock = threading.Lock()
        self.run_slots = threading.BoundedSemaphore(
            workspace.definition.runtime.max_concurrent_runs
        )
        self.cleanup()

    def cleanup(self) -> dict[str, Any]:
        """Bound in-memory Run state and its matching Workspace storage."""
        runtime = self.workspace.definition.runtime
        current = time.time()
        with self.maintenance_lock:
            with self.lock:
                completed = sorted(
                    (
                        record
                        for record in self.records.values()
                        if record.status not in {"queued", "running"}
                    ),
                    key=lambda record: record.finished_at or record.created_at,
                    reverse=True,
                )
                expired: set[str] = set()
                for index, record in enumerate(completed):
                    finished_at = record.finished_at or record.created_at
                    if index >= runtime.max_retained_runs:
                        expired.add(record.run_id)
                    if (
                        runtime.run_retention_seconds is not None
                        and current - finished_at > runtime.run_retention_seconds
                    ):
                        expired.add(record.run_id)
                for run_id in expired:
                    self.records.pop(run_id, None)
                for key, run_id in list(self.latest.items()):
                    if run_id not in self.records:
                        self.latest.pop(key, None)

                retained_sessions = {
                    record.session_id for record in self.records.values()
                }
                discarded_executors = [
                    self.executors.pop(session_id)
                    for session_id in list(self.executors)
                    if session_id not in retained_sessions
                ]
                executors = [*self.executors.values(), *discarded_executors]
                protected_run_ids = set(self.records)
                has_active_runs = any(
                    record.status in {"queued", "running"}
                    for record in self.records.values()
                )

            for executor in executors:
                executor.cache.prune_memory(
                    max_entries=runtime.max_retained_cache_entries,
                    max_age_seconds=runtime.cache_retention_seconds,
                    now=current,
                )
            return cleanup_workspace_storage(
                self.workspace.root,
                max_runs=runtime.max_retained_runs,
                run_max_age_seconds=runtime.run_retention_seconds,
                max_cache_entries=runtime.max_retained_cache_entries,
                cache_max_age_seconds=runtime.cache_retention_seconds,
                include_cache=not has_active_runs,
                apply=True,
                protected_run_ids=protected_run_ids,
                now=current,
            )

    def executor_for(self, session_id: str) -> Executor:
        """Return a cache-isolated executor for one browser-tab session."""
        with self.lock:
            return self.executors.setdefault(
                session_id,
                Executor(self.workspace, cache_namespace=session_id),
            )

    def start(
        self,
        dashboard_id: str,
        params: dict[str, Any],
        session_id: str,
        selections: dict[str, Any] | None = None,
        refresh: bool = False,
    ) -> RunRecord:
        self.cleanup()
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        record = RunRecord(
            run_id=run_id,
            session_id=session_id,
            dashboard_id=dashboard_id,
            requested_parameters=dict(params),
        )
        with self.lock:
            self.records[run_id] = record
            self.latest[(session_id, dashboard_id)] = run_id
        executor = self.executor_for(session_id)

        def observer(event: ExecutionEvent) -> None:
            with record.condition:
                record.events.append(event)
                record.condition.notify_all()

        def snapshot_observer(snapshot: RunResult) -> None:
            with record.condition:
                record.snapshot = snapshot
                record.condition.notify_all()

        def worker() -> None:
            try:
                observer(ExecutionEvent(event="run_queued", run_id=run_id))
                with self.run_slots:
                    record.status = "running"
                    result = executor.run(
                        dashboard_id,
                        params=params,
                        selections=selections,
                        refresh=refresh,
                        observer=observer,
                        snapshot_observer=snapshot_observer,
                        run_id=run_id,
                    )
                with record.condition:
                    record.snapshot = result
                    record.result = result
                    record.status = result.status
                    record.condition.notify_all()
                observer(
                    ExecutionEvent(
                        event="run_ready",
                        run_id=run_id,
                        data={"status": result.status},
                    )
                )
            except Exception as exc:
                record.status = "failed"
                record.error = (
                    exc.as_dict()
                    if isinstance(exc, DatavizError)
                    else {"type": type(exc).__name__, "message": str(exc)}
                )
                observer(
                    ExecutionEvent(
                        event="run_failed",
                        run_id=run_id,
                        error=record.error,
                        data={"status": "failed"},
                    )
                )
            finally:
                record.finished_at = time.time()
                with record.condition:
                    record.condition.notify_all()
                self.cleanup()

        threading.Thread(target=worker, name=f"dataviz-{run_id}", daemon=True).start()
        return record

    def get(self, run_id: str, session_id: str) -> RunRecord | None:
        with self.lock:
            record = self.records.get(run_id)
        return record if record and record.session_id == session_id else None

    def latest_for(self, session_id: str, dashboard_id: str) -> RunRecord | None:
        with self.lock:
            run_id = self.latest.get((session_id, dashboard_id))
            return self.records.get(run_id) if run_id else None

    def latest_for_session(self, session_id: str) -> list[RunRecord]:
        with self.lock:
            run_ids = [
                run_id
                for (owner_session, _), run_id in self.latest.items()
                if owner_session == session_id
            ]
            return [self.records[run_id] for run_id in run_ids if run_id in self.records]
