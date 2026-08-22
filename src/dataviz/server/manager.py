from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from dataviz.execution import Executor, RunResult
from dataviz.execution.events import ExecutionEvent
from dataviz.workspace.loader import LoadedWorkspace


@dataclass
class RunRecord:
    run_id: str
    session_id: str
    dashboard_id: str
    status: str = "running"
    events: list[ExecutionEvent] = field(default_factory=list)
    result: RunResult | None = None
    error: dict[str, Any] | None = None
    condition: threading.Condition = field(default_factory=threading.Condition)


class RunManager:
    def __init__(self, workspace: LoadedWorkspace):
        self.workspace = workspace
        self.executors: dict[str, Executor] = {}
        self.records: dict[str, RunRecord] = {}
        self.latest: dict[tuple[str, str], str] = {}
        self.lock = threading.Lock()

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
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        record = RunRecord(run_id=run_id, session_id=session_id, dashboard_id=dashboard_id)
        with self.lock:
            self.records[run_id] = record
            self.latest[(session_id, dashboard_id)] = run_id
        executor = self.executor_for(session_id)

        def observer(event: ExecutionEvent) -> None:
            with record.condition:
                record.events.append(event)
                record.condition.notify_all()

        def worker() -> None:
            try:
                result = executor.run(
                    dashboard_id,
                    params=params,
                    selections=selections,
                    source_targets=list(self.workspace.dashboard(dashboard_id).sources),
                    refresh=refresh,
                    observer=observer,
                    run_id=run_id,
                )
                record.result = result
                record.status = result.status
                observer(
                    ExecutionEvent(
                        event="run_ready",
                        run_id=run_id,
                        data={"status": result.status},
                    )
                )
            except Exception as exc:
                record.status = "failed"
                record.error = {"type": type(exc).__name__, "message": str(exc)}
                observer(
                    ExecutionEvent(
                        event="run_failed",
                        run_id=run_id,
                        error=record.error,
                        data={"status": "failed"},
                    )
                )
            finally:
                with record.condition:
                    record.condition.notify_all()

        threading.Thread(target=worker, name=f"dataviz-{run_id}", daemon=True).start()
        return record

    def get(self, run_id: str, session_id: str) -> RunRecord | None:
        record = self.records.get(run_id)
        return record if record and record.session_id == session_id else None

    def latest_for(self, session_id: str, dashboard_id: str) -> RunRecord | None:
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
