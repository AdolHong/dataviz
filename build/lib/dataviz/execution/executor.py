from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.auth import ConnectionResolver
from dataviz.errors import DatavizError, ExecutionFailure
from dataviz.execution.cache import NodeCache
from dataviz.execution.context import ExecutionContext
from dataviz.execution.events import EventObserver, ExecutionEvent
from dataviz.execution.plan import ExecutionPlan, PlanNode, compile_plan
from dataviz.execution.results import NodeResult, RunResult
from dataviz.sources import SOURCE_ADAPTERS
from dataviz.sources.base import SourceRequest
from dataviz.widgets import execute_widget
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace
from dataviz.workspace.filters import resolve_filter_values


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_parameters(dashboard: LoadedDashboard, values: dict[str, Any] | None) -> dict[str, Any]:
    provided = values or {}
    result: dict[str, Any] = {}
    for definition in dashboard.definition.query_parameters:
        value = provided.get(definition.id, definition.default)
        if definition.required and (value is None or value == "" or value == []):
            raise ExecutionFailure(f"Required parameter is missing: {definition.id}")
        if definition.type == "boolean" and isinstance(value, str):
            value = value.lower() in {"true", "1", "yes", "on"}
        elif definition.type == "number" and isinstance(value, str):
            value = float(value) if "." in value else int(value)
        elif definition.type == "multi_select" and isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        elif definition.type == "date_range" and isinstance(value, str):
            value = [item.strip() for item in value.split(",", 1)]
        result[definition.id] = value
    result.update({key: value for key, value in provided.items() if key not in result})
    return result


class Executor:
    def __init__(self, workspace: LoadedWorkspace):
        self.workspace = workspace
        self.cache = NodeCache(workspace.root)
        self.connections = ConnectionResolver(workspace.root)
        self._event_lock = threading.Lock()

    def run(
        self,
        dashboard_id: str,
        *,
        params: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        source_targets: list[str] | None = None,
        widget_targets: list[str] | None = None,
        refresh: bool = False,
        observer: EventObserver | None = None,
        run_id: str | None = None,
    ) -> RunResult:
        dashboard = self.workspace.dashboard(dashboard_id)
        parameters = resolve_parameters(dashboard, params)
        filter_values, filters_by_widget = resolve_filter_values(dashboard.definition, filters)
        plan = compile_plan(dashboard, source_targets=source_targets, widget_targets=widget_targets)
        run_id = run_id or f"run_{uuid.uuid4().hex[:16]}"
        store = ArtifactStore(self.workspace.root, run_id)
        result = RunResult(
            run_id=run_id,
            status="running",
            workspace=self.workspace.definition.id,
            dashboard=dashboard.definition.id,
            parameters=parameters,
            filters=filter_values,
            nodes={
                node_id: NodeResult(node_id=node_id, node_type=node.kind, status="not_run")
                for node_id, node in plan.nodes.items()
            },
        )

        def emit(event_name: str, node: PlanNode | None = None, **kwargs: Any) -> None:
            event = ExecutionEvent(
                event=event_name,
                run_id=run_id,
                node_id=node.id if node else None,
                node_type=node.kind if node else None,
                **kwargs,
            )
            if observer:
                with self._event_lock:
                    observer(event)

        emit("run_started", data={"targets": sorted(plan.targets), "parameters": parameters, "filters": filter_values})
        pending = set(plan.nodes)
        running: dict[Future, str] = {}
        max_workers = max(1, self.workspace.definition.runtime.max_workers)

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dataviz") as pool:
            while pending or running:
                progressed = False
                for node_id in list(pending):
                    node = plan.nodes[node_id]
                    dependency_results = [result.nodes[value] for value in node.dependencies]
                    if any(item.status in {"failed", "blocked", "cancelled"} for item in dependency_results):
                        result.nodes[node_id] = NodeResult(
                            node_id=node_id,
                            node_type=node.kind,
                            status="blocked",
                            finished_at=now(),
                            error={"type": "dependency_failed", "message": "An upstream node failed"},
                        )
                        pending.remove(node_id)
                        emit("node_blocked", node, error=result.nodes[node_id].error)
                        progressed = True
                    elif all(item.status == "succeeded" for item in dependency_results):
                        result.nodes[node_id].status = "queued"
                        emit("node_queued", node)
                        future = pool.submit(
                            self._execute_node,
                            node,
                            dashboard,
                            parameters,
                            filters_by_widget,
                            result,
                            store,
                            refresh,
                            emit,
                        )
                        running[future] = node_id
                        pending.remove(node_id)
                        progressed = True

                if running:
                    completed, _ = wait(running, return_when=FIRST_COMPLETED)
                    for future in completed:
                        node_id = running.pop(future)
                        try:
                            result.nodes[node_id] = future.result()
                        except Exception as exc:
                            error = exc.as_dict() if isinstance(exc, DatavizError) else {
                                "type": type(exc).__name__, "message": str(exc)
                            }
                            node = plan.nodes[node_id]
                            result.nodes[node_id] = NodeResult(
                                node_id=node_id,
                                node_type=node.kind,
                                status="failed",
                                finished_at=now(),
                                error=error,
                            )
                            emit("node_failed", node, error=error)
                        progressed = True
                if not progressed and pending:
                    raise ExecutionFailure("Execution deadlock detected", details=sorted(pending))

        succeeded_targets = [result.nodes[node_id].status == "succeeded" for node_id in plan.targets]
        failures = [item for item in result.nodes.values() if item.status in {"failed", "blocked"}]
        if all(succeeded_targets) and not failures:
            result.status = "success"
        elif any(succeeded_targets):
            result.status = "partial"
        else:
            result.status = "failed"
        result.finished_at = now()
        for widget_id in dashboard.widgets:
            node_id = f"widget:{widget_id}"
            node_result = result.nodes.get(node_id)
            if node_result and node_result.status == "succeeded":
                result.outputs[widget_id] = node_result.artifacts
        (store.run_root / "result.json").write_text(
            result.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
        )
        emit(f"run_{'completed' if result.status in {'success', 'partial'} else 'failed'}", data={"status": result.status})
        return result

    def _execute_node(
        self,
        node: PlanNode,
        dashboard: LoadedDashboard,
        parameters: dict[str, Any],
        filters_by_widget: dict[str, dict[str, Any]],
        run_result: RunResult,
        store: ArtifactStore,
        refresh: bool,
        emit,
    ) -> NodeResult:
        started = time.perf_counter()
        started_at = now()
        emit("node_started", node)
        context = self._context_for_node(node, dashboard, parameters, filters_by_widget, run_result, store)

        try:
            if node.kind == "source":
                definition = node.definition
                cache_key = self._cache_key(node, parameters, run_result)
                cached = None if refresh else self.cache.load(cache_key, definition.cache, store)
                if cached is not None:
                    duration = int((time.perf_counter() - started) * 1000)
                    emit("node_succeeded", node, duration_ms=duration, data={"origin": "cache"})
                    return NodeResult(
                        node_id=node.id,
                        node_type=node.kind,
                        status="succeeded",
                        result_origin="cache",
                        started_at=started_at,
                        finished_at=now(),
                        duration_ms=duration,
                        artifacts=cached,
                    )
                adapter = SOURCE_ADAPTERS[definition.type]
                dataframe = adapter.execute(SourceRequest(node.definition_path, definition, context, self.connections))
                artifacts = [store.write_table(node.local_id, dataframe, metadata={"title": definition.name or node.local_id})]
                self.cache.save(cache_key, definition.cache, artifacts, store)
            else:
                artifacts = execute_widget(node.definition_path, node.definition, context)

            duration = int((time.perf_counter() - started) * 1000)
            emit("node_succeeded", node, duration_ms=duration, data={"origin": "executed"})
            return NodeResult(
                node_id=node.id,
                node_type=node.kind,
                status="succeeded",
                result_origin="executed",
                started_at=started_at,
                finished_at=now(),
                duration_ms=duration,
                artifacts=artifacts,
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            error = exc.as_dict() if isinstance(exc, DatavizError) else {
                "type": type(exc).__name__, "message": str(exc)
            }
            emit("node_failed", node, duration_ms=duration, error=error)
            return NodeResult(
                node_id=node.id,
                node_type=node.kind,
                status="failed",
                started_at=started_at,
                finished_at=now(),
                duration_ms=duration,
                error=error,
            )

    def _context_for_node(
        self,
        node: PlanNode,
        dashboard: LoadedDashboard,
        parameters: dict[str, Any],
        filters_by_widget: dict[str, dict[str, Any]],
        run_result: RunResult,
        store: ArtifactStore,
    ) -> ExecutionContext:
        tables = {}
        artifacts = {}
        for dependency_id in node.dependencies:
            dependency = run_result.nodes[dependency_id]
            local_id = dependency_id.split(":", 1)[1]
            artifacts[local_id] = dependency.artifacts
            table_artifact = next((item for item in dependency.artifacts if item.kind == "table"), None)
            if table_artifact:
                tables[local_id] = store.read_table(table_artifact)
        return ExecutionContext(
            workspace_root=self.workspace.root,
            dashboard_root=dashboard.root,
            run_id=run_result.run_id,
            params=parameters,
            filters=filters_by_widget.get(node.local_id, {}) if node.kind == "widget" else {},
            tables=tables,
            artifacts=artifacts,
            store=store,
        )

    def _cache_key(self, node: PlanNode, parameters: dict[str, Any], result: RunResult) -> str:
        definition = node.definition
        files: dict[str, str] = {}
        for field in ("path", "code"):
            value = getattr(definition, field, None)
            if value:
                path = (node.definition_path.parent / value).resolve()
                if path.exists():
                    files[field] = hashlib.sha256(path.read_bytes()).hexdigest()
        upstream = {
            dependency: [item.content_hash for item in result.nodes[dependency].artifacts]
            for dependency in node.dependencies
        }
        payload = {
            "definition": definition.model_dump(mode="json", by_alias=True),
            "parameters": {name: parameters.get(name) for name in definition.params},
            "files": files,
            "upstream": upstream,
            "runtime": "0.1.0",
        }
        return self.cache.key(payload)
