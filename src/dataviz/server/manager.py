from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from dataviz.execution import Executor, InteractionExecutor, InteractionResult, RunResult
from dataviz.execution.interactive import (
    compile_interactive_plan,
    normalize_interactive_target,
)
from dataviz.execution.fingerprint import (
    ensure_query_run_compatible,
    query_contract_fingerprint,
)
from dataviz.execution.plan import compile_plan, server_interactive_base_references
from dataviz.execution.events import ExecutionEvent
from dataviz.errors import DatavizError, ExecutionFailure
from dataviz.maintenance import cleanup_workspace_storage
from dataviz.workspace.loader import LoadedWorkspace
from dataviz.workspace.controls import resolve_compute_values, resolve_selection_values


@dataclass
class RunRecord:
    run_id: str
    session_id: str
    dashboard_id: str
    requested_parameters: dict[str, Any] = field(default_factory=dict)
    query_scope: str = "dashboard"
    query_targets: list[str] = field(default_factory=list)
    query_nodes: list[str] = field(default_factory=list)
    server_interactive_inputs: list[str] = field(default_factory=list)
    query_contract_hash: str = ""
    status: str = "queued"
    events: list[ExecutionEvent] = field(default_factory=list)
    event_offset: int = 0
    snapshot: RunResult | None = None
    result: RunResult | None = None
    error: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    condition: threading.Condition = field(default_factory=threading.Condition)


@dataclass
class InteractionRecord:
    interaction_id: str
    generation: int
    run_id: str
    session_id: str
    dashboard_id: str
    target: str
    compute_parameters: dict[str, Any] = field(default_factory=dict)
    selections: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    events: list[dict[str, Any]] = field(default_factory=list)
    event_offset: int = 0
    result: InteractionResult | None = None
    error: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    condition: threading.Condition = field(default_factory=threading.Condition)


class RunManager:
    def __init__(self, workspace: LoadedWorkspace):
        self.workspace = workspace
        self.executors: dict[str, Executor] = {}
        self.records: dict[str, RunRecord] = {}
        self.interactions: dict[str, InteractionRecord] = {}
        self.latest: dict[tuple[str, str], str] = {}
        self.latest_interactions: dict[tuple[str, str, str, str], str] = {}
        self.generations: dict[tuple[str, str, str, str], int] = {}
        self.latest_interactive_nodes: dict[tuple[str, str, str], Any] = {}
        self.lock = threading.Lock()
        self.maintenance_lock = threading.Lock()
        self.run_slots = threading.BoundedSemaphore(
            workspace.definition.runtime.max_concurrent_runs
        )
        self.interaction_slots = threading.BoundedSemaphore(
            workspace.definition.runtime.max_concurrent_interactions
        )
        self.cleanup()

    def install_workspace_snapshot(self, workspace: LoadedWorkspace) -> None:
        """Publish one fully loaded Workspace for subsequently created work.

        Active Runs keep the immutable Workspace/Executor they captured at start.
        Replacing the reference avoids exposing a partially refreshed Workspace to
        another request while still letting the development Server pick up edits.
        """
        if workspace.root.resolve() != self.workspace.root.resolve():
            raise ValueError("RunManager cannot switch to another Workspace root")
        with self.lock:
            self.workspace = workspace

    def workspace_snapshot(self) -> LoadedWorkspace:
        with self.lock:
            return self.workspace

    @staticmethod
    def _append_bounded_event(record: Any, event: Any, limit: int) -> None:
        record.events.append(event)
        overflow = len(record.events) - limit
        if overflow > 0:
            del record.events[:overflow]
            record.event_offset += overflow

    @staticmethod
    def _acquire_slot(
        slot: threading.BoundedSemaphore,
        cancel_event: threading.Event,
    ) -> bool:
        """Wait for a global execution slot without making queued work immortal."""
        while not cancel_event.is_set():
            if slot.acquire(timeout=0.05):
                return True
        return False

    def cleanup(self) -> dict[str, Any]:
        """Bound in-memory Run state and its matching Workspace storage."""
        workspace = self.workspace_snapshot()
        runtime = workspace.definition.runtime
        current = time.time()
        with self.maintenance_lock:
            with self.lock:
                active_interaction_run_ids = {
                    interaction.run_id
                    for interaction in self.interactions.values()
                    if interaction.status in {"queued", "loading"}
                }
                expired: set[str] = set()
                completed_by_session: dict[str, list[RunRecord]] = {}
                for record in self.records.values():
                    if record.status not in {"queued", "loading"}:
                        completed_by_session.setdefault(record.session_id, []).append(record)
                for completed in completed_by_session.values():
                    completed.sort(
                        key=lambda record: record.finished_at or record.created_at,
                        reverse=True,
                    )
                    for index, record in enumerate(completed):
                        if record.run_id in active_interaction_run_ids:
                            continue
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
                    for interaction_id, interaction in list(self.interactions.items()):
                        if interaction.run_id == run_id:
                            interaction.cancel_event.set()
                            self.interactions.pop(interaction_id, None)
                for key in list(self.latest_interactive_nodes):
                    if key[1] not in self.records:
                        self.latest_interactive_nodes.pop(key, None)
                for key in list(self.generations):
                    if key[2] not in self.records:
                        self.generations.pop(key, None)
                for key, run_id in list(self.latest.items()):
                    if run_id not in self.records:
                        self.latest.pop(key, None)
                for key, interaction_id in list(self.latest_interactions.items()):
                    if interaction_id not in self.interactions:
                        self.latest_interactions.pop(key, None)

                protected_interactions = set(self.latest_interactions.values())
                by_run: dict[str, list[InteractionRecord]] = {}
                for interaction in self.interactions.values():
                    if interaction.status not in {"queued", "loading"}:
                        by_run.setdefault(interaction.run_id, []).append(interaction)
                for interactions in by_run.values():
                    interactions.sort(
                        key=lambda item: item.finished_at or item.created_at,
                        reverse=True,
                    )
                    for interaction in interactions[
                        runtime.max_retained_interactions_per_run :
                    ]:
                        if interaction.interaction_id not in protected_interactions:
                            self.interactions.pop(interaction.interaction_id, None)

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
                has_active_work = bool(active_interaction_run_ids) or any(
                    record.status in {"queued", "loading"}
                    for record in self.records.values()
                )

            for executor in executors:
                executor.cache.prune_memory(
                    max_entries=runtime.max_retained_cache_entries,
                    max_age_seconds=runtime.cache_retention_seconds,
                    now=current,
                )
            return cleanup_workspace_storage(
                workspace.root,
                max_runs=runtime.max_retained_runs,
                run_max_age_seconds=runtime.run_retention_seconds,
                max_cache_entries=runtime.max_retained_cache_entries,
                cache_max_age_seconds=runtime.cache_retention_seconds,
                include_cache=not has_active_work,
                apply=True,
                protected_run_ids=protected_run_ids,
                now=current,
            )

    def executor_for(
        self,
        session_id: str,
        *,
        workspace: LoadedWorkspace | None = None,
    ) -> Executor:
        """Return a tab-cache executor bound to one immutable Workspace snapshot."""
        with self.lock:
            snapshot = workspace or self.workspace
            current = self.executors.get(session_id)
            if current is None or current.workspace is not snapshot:
                current = Executor(
                    snapshot,
                    cache=current.cache if current is not None else None,
                    cache_namespace=session_id,
                )
                self.executors[session_id] = current
            return current

    def start(
        self,
        dashboard_id: str,
        query_parameters: dict[str, Any],
        session_id: str,
        refresh: bool = False,
        *,
        _workspace: LoadedWorkspace | None = None,
    ) -> RunRecord:
        self.cleanup()
        workspace = _workspace or self.workspace_snapshot()
        runtime = workspace.definition.runtime.model_copy(deep=True)
        event_limit = runtime.max_retained_run_events
        executor = self.executor_for(session_id, workspace=workspace)
        dashboard = executor.ensure_valid(dashboard_id)
        plan = compile_plan(dashboard)
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        record = RunRecord(
            run_id=run_id,
            session_id=session_id,
            dashboard_id=dashboard_id,
            requested_parameters=dict(query_parameters),
            query_scope="dashboard",
            query_targets=sorted(plan.targets),
            query_nodes=sorted(plan.nodes),
            server_interactive_inputs=sorted(
                server_interactive_base_references(dashboard)
            ),
            query_contract_hash=query_contract_fingerprint(dashboard, plan.nodes),
        )
        with self.lock:
            previous_id = self.latest.get((session_id, dashboard_id))
            previous = self.records.get(previous_id) if previous_id else None
            if previous and previous.status in {"queued", "loading"}:
                previous.cancel_event.set()
            for key, interaction_id in list(self.latest_interactions.items()):
                if key[:2] == (session_id, dashboard_id):
                    interaction = self.interactions.get(interaction_id)
                    if interaction and interaction.status in {"queued", "loading"}:
                        interaction.cancel_event.set()
            self.records[run_id] = record
            self.latest[(session_id, dashboard_id)] = run_id
        terminal_event: ExecutionEvent | None = None

        def observer(event: ExecutionEvent) -> None:
            nonlocal terminal_event
            # Publish a terminal event only after RunRecord.result is readable.
            # Otherwise an SSE client can receive run_ready during the tiny gap
            # between Executor.run() emitting it and returning the result.
            if event.event in {"run_ready", "run_error", "run_cancelled"}:
                terminal_event = event
                return
            with record.condition:
                self._append_bounded_event(
                    record,
                    event,
                    event_limit,
                )
                record.condition.notify_all()

        def snapshot_observer(snapshot: RunResult) -> None:
            with record.condition:
                record.snapshot = snapshot
                record.condition.notify_all()

        def worker() -> None:
            acquired = False
            try:
                observer(ExecutionEvent(event="run_queued", run_id=run_id))
                acquired = self._acquire_slot(self.run_slots, record.cancel_event)
                if not acquired:
                    with record.condition:
                        record.status = "cancelled"
                        self._append_bounded_event(
                            record,
                            ExecutionEvent(
                                event="run_cancelled",
                                run_id=run_id,
                                data={"status": "cancelled", "phase": "queued"},
                            ),
                            event_limit,
                        )
                        record.condition.notify_all()
                    return
                with record.condition:
                    record.status = "loading"
                    record.condition.notify_all()
                result = executor.run(
                    dashboard_id,
                    query_parameters=query_parameters,
                    refresh=refresh,
                    observer=observer,
                    snapshot_observer=snapshot_observer,
                    run_id=run_id,
                    cancel_event=record.cancel_event,
                    _dashboard=dashboard,
                )
                with record.condition:
                    record.snapshot = result
                    record.result = result
                    record.status = result.status
                    self._append_bounded_event(
                        record,
                        terminal_event
                        or ExecutionEvent(
                            event=(
                                "run_ready"
                                if result.status in {"ready", "partial"}
                                else "run_cancelled"
                                if result.status == "cancelled"
                                else "run_error"
                            ),
                            run_id=run_id,
                            data={"status": result.status},
                        ),
                        event_limit,
                    )
                    record.condition.notify_all()
            except Exception as exc:
                with record.condition:
                    record.status = "error"
                    record.error = (
                        exc.as_dict()
                        if isinstance(exc, DatavizError)
                        else {"type": type(exc).__name__, "message": str(exc)}
                    )
                    terminal = ExecutionEvent(
                        event="run_error",
                        run_id=run_id,
                        error=record.error,
                        data={"status": "error"},
                    )
                    self._append_bounded_event(
                        record,
                        terminal,
                        event_limit,
                    )
                    record.condition.notify_all()
            finally:
                if acquired:
                    self.run_slots.release()
                with record.condition:
                    record.finished_at = time.time()
                    record.condition.notify_all()
                self.cleanup()

        threading.Thread(target=worker, name=f"dataviz-{run_id}", daemon=True).start()
        return record

    def cancel(self, run_id: str, session_id: str) -> RunRecord | None:
        record = self.get(run_id, session_id)
        if record and record.status in {"queued", "loading"}:
            record.cancel_event.set()
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

    def start_interaction(
        self,
        run_id: str,
        *,
        session_id: str,
        target: str,
        generation: int,
        compute_parameters: dict[str, Any],
        selections: dict[str, Any],
        refresh: bool = False,
        _workspace: LoadedWorkspace | None = None,
    ) -> InteractionRecord:
        run_record = self.get(run_id, session_id)
        if not run_record:
            raise ValueError("Query Run is not available in this browser-tab session")
        with run_record.condition:
            query_run = run_record.result or run_record.snapshot
            query_run = query_run.model_copy(deep=True) if query_run else None
        if not query_run:
            raise ValueError("Query Run is not ready in this browser-tab session")
        target_id = normalize_interactive_target(target)
        workspace = _workspace or self.workspace_snapshot()
        query_executor = self.executor_for(session_id, workspace=workspace)
        executor = InteractionExecutor(
            workspace,
            cache=query_executor.cache,
        )
        runtime = workspace.definition.runtime.model_copy(deep=True)
        event_limit = runtime.max_retained_interaction_events
        dashboard = executor.ensure_valid(query_run.dashboard)
        ensure_query_run_compatible(dashboard, query_run)
        compile_interactive_plan(dashboard, target_id)
        resolved_compute = resolve_compute_values(
            dashboard.definition,
            compute_parameters,
        )
        resolved_selections = resolve_selection_values(
            dashboard.definition,
            selections,
        )
        key = (session_id, run_record.dashboard_id, run_id, target_id)
        with self.lock:
            current_generation = self.generations.get(key, 0)
            if generation <= current_generation:
                raise ExecutionFailure(
                    "Interactive generation is stale",
                    details={
                        "code": "interaction_generation_stale",
                        "generation": generation,
                        "current_generation": current_generation,
                        "run_id": run_id,
                        "transform_id": target_id,
                    },
                )
            previous_id = self.latest_interactions.get(key)
            previous = self.interactions.get(previous_id) if previous_id else None
            if previous and previous.status in {"queued", "loading"}:
                previous.cancel_event.set()
            self.generations[key] = generation
            interaction_id = f"ix_{uuid.uuid4().hex[:16]}"
            record = InteractionRecord(
                interaction_id=interaction_id,
                generation=generation,
                run_id=run_id,
                session_id=session_id,
                dashboard_id=run_record.dashboard_id,
                target=target_id,
                compute_parameters=dict(resolved_compute),
                selections=dict(resolved_selections),
            )
            self.interactions[interaction_id] = record
            self.latest_interactions[key] = interaction_id

        with self.lock:
            reusable_nodes = {
                node_id: node
                for (owner_session, owner_run, node_id), node in self.latest_interactive_nodes.items()
                if owner_session == session_id and owner_run == run_id
            }

        def observer(event: dict[str, Any]) -> None:
            with record.condition:
                self._append_bounded_event(
                    record,
                    event,
                    event_limit,
                )
                record.condition.notify_all()

        def worker() -> None:
            acquired = False
            try:
                acquired = self._acquire_slot(
                    self.interaction_slots, record.cancel_event
                )
                if not acquired:
                    with record.condition:
                        record.status = "cancelled"
                        self._append_bounded_event(
                            record,
                            {
                                "event": "interaction_cancelled",
                                "interaction_id": interaction_id,
                                "generation": generation,
                                "phase": "queued",
                            },
                            event_limit,
                        )
                        record.condition.notify_all()
                    return
                with record.condition:
                    record.status = "loading"
                    record.condition.notify_all()
                result = executor.execute(
                    query_run,
                    target_id,
                    compute_parameters=resolved_compute,
                    selections=resolved_selections,
                    generation=generation,
                    interaction_id=interaction_id,
                    refresh=refresh,
                    cancel_event=record.cancel_event,
                    observer=observer,
                    reusable_nodes=reusable_nodes,
                    _dashboard=dashboard,
                )
                with self.lock:
                    for node_id, node in result.nodes.items():
                        if node.status in {"ready", "empty"}:
                            self.latest_interactive_nodes[(session_id, run_id, node_id)] = node
                with record.condition:
                    record.result = result
                    record.status = result.status
                    record.condition.notify_all()
            except Exception as exc:
                with record.condition:
                    record.status = "error"
                    record.error = (
                        exc.as_dict()
                        if isinstance(exc, DatavizError)
                        else {"type": type(exc).__name__, "message": str(exc)}
                    )
                    record.condition.notify_all()
            finally:
                if acquired:
                    self.interaction_slots.release()
                with record.condition:
                    record.finished_at = time.time()
                    record.condition.notify_all()
                self.cleanup()

        threading.Thread(
            target=worker,
            name=f"dataviz-{interaction_id}",
            daemon=True,
        ).start()
        return record

    def get_interaction(
        self, interaction_id: str, session_id: str
    ) -> InteractionRecord | None:
        with self.lock:
            record = self.interactions.get(interaction_id)
        return record if record and record.session_id == session_id else None

    def cancel_interaction(
        self, interaction_id: str, session_id: str
    ) -> InteractionRecord | None:
        record = self.get_interaction(interaction_id, session_id)
        if record and record.status in {"queued", "loading"}:
            record.cancel_event.set()
        return record
