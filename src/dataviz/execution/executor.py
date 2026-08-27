from __future__ import annotations

import re
import threading
import time
import traceback
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any, Callable

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.auth import AdapterResolver
from dataviz.errors import DatavizError, ExecutionFailure, ValidationFailure
from dataviz.execution.cache import NodeCache
from dataviz.execution.context import ExecutionContext
from dataviz.execution.events import EventObserver, ExecutionEvent
from dataviz.execution.fingerprint import query_contract_fingerprint
from dataviz.execution.node_support import hash_path, output_status, package_fingerprint
from dataviz.execution.outputs import normalize_outputs, validate_table_schema
from dataviz.execution.parameters import (
    project_query_inputs,
    resolve_query_parameter_values,
)
from dataviz.execution.plan import PlanNode, compile_plan
from dataviz.execution.python_process import execute_python_node
from dataviz.execution.results import NodeResult, RunResult
from dataviz.redaction import redact_text, redact_value
from dataviz.sources import SOURCE_RUNNERS
from dataviz.sources.base import SourceRequest
from dataviz.workspace.loader import (
    LoadedDashboard,
    LoadedWorkspace,
    dashboard_validation_diagnostics,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


SnapshotObserver = Callable[[RunResult], None]


def _system_log(level: str, event: str, message: str, **fields: Any) -> dict[str, Any]:
    return {
        "timestamp": now(),
        "level": level,
        "event": event,
        "message": message,
        "fields": fields,
    }


def _write_python_log(
    store: ArtifactStore,
    artifact_id: str,
    records: list[dict[str, Any]],
    *,
    node_id: str,
) -> ArtifactDescriptor:
    return store.write_json(
        re.sub(r"[^A-Za-z0-9_.-]+", "_", artifact_id),
        {"schema": "dataviz/execution-log/v1", "records": records},
        kind="object",
        format="json",
        metadata={
            "role": "execution_log",
            "structured": True,
            "node_id": node_id,
            "record_count": len(records),
        },
    )


def resolve_query_parameters(
    dashboard: LoadedDashboard,
    values: dict[str, Any] | None,
    *,
    timezone_name: str,
    current_time: datetime | None = None,
) -> dict[str, Any]:
    return resolve_query_parameter_values(
        dashboard.definition.query_parameters,
        values,
        timezone_name=timezone_name,
        current_time=current_time,
    )


class Executor:
    def __init__(
        self,
        workspace: LoadedWorkspace,
        *,
        cache: NodeCache | None = None,
        cache_namespace: str | None = None,
    ):
        self.workspace = workspace
        self.cache = cache or NodeCache(workspace.root, namespace=cache_namespace)
        self._event_lock = threading.Lock()

    def ensure_valid(self, dashboard_id: str) -> LoadedDashboard:
        dashboard = self.workspace.dashboard(dashboard_id)
        errors = [
            item
            for item in dashboard_validation_diagnostics(self.workspace, dashboard)
            if item.level == "error"
        ]
        if errors:
            raise ValidationFailure(
                f"Dashboard {dashboard.definition.id} failed static preflight",
                file=dashboard.definition_path,
                details={
                    "code": "dashboard_preflight_failed",
                    "dashboard": dashboard.definition.id,
                    "diagnostics": [item.as_dict() for item in errors],
                },
            )
        return dashboard

    def run(
        self,
        dashboard_id: str,
        *,
        query_parameters: dict[str, Any] | None = None,
        targets: list[str] | None = None,
        refresh: bool = False,
        observer: EventObserver | None = None,
        snapshot_observer: SnapshotObserver | None = None,
        run_id: str | None = None,
        cancel_event: threading.Event | None = None,
        _dashboard: LoadedDashboard | None = None,
    ) -> RunResult:
        dashboard = _dashboard or self.ensure_valid(dashboard_id)
        if dashboard.definition.id != dashboard_id:
            raise ValueError("Prevalidated Dashboard does not match the requested id")
        workspace_definition = self.workspace.definition.model_copy(deep=True)
        parameters = resolve_query_parameters(
            dashboard,
            query_parameters,
            timezone_name=workspace_definition.context.timezone,
        )
        # Adapter files are an editable Workspace boundary. Resolve one immutable
        # snapshot per Run instead of retaining the first values seen by a tab.
        # Keeping it local also prevents concurrent Dashboard Runs from replacing
        # each other's credentials/configuration mid-execution.
        adapters = AdapterResolver(self.workspace.root)
        plan = compile_plan(dashboard, targets=targets)
        run_id = run_id or f"run_{uuid.uuid4().hex[:16]}"
        store = ArtifactStore(self.workspace.root, run_id)
        result = RunResult(
            run_id=run_id,
            status="loading",
            workspace=workspace_definition.id,
            dashboard=dashboard.definition.id,
            query_scope="dashboard" if targets is None else "targets",
            query_targets=sorted(plan.targets),
            query_nodes=sorted(plan.nodes),
            query_contract_hash=query_contract_fingerprint(dashboard, plan.nodes),
            query_parameters=parameters,
            nodes={
                node_id: NodeResult(node_id=node_id, node_type=node.kind, status="not_run")
                for node_id, node in plan.nodes.items()
            },
        )
        for node_id, node in plan.nodes.items():
            result.nodes[node_id].diagnostics = self._inspect_node(
                node,
                dashboard,
                parameters,
                result,
                store,
                adapters,
            )

        def publish_snapshot() -> None:
            if snapshot_observer:
                snapshot_observer(result.model_copy(deep=True))

        def declared_output_references(node: PlanNode) -> list[str]:
            names = list(node.definition.outputs)
            return [f"{node.id}/{name}" for name in names]

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

        publish_snapshot()
        emit(
            "run_started",
            data={"targets": sorted(plan.targets), "query_parameters": parameters},
        )
        pending = set(plan.nodes)
        running: dict[Future, str] = {}
        max_workers = max(1, workspace_definition.runtime.max_workers)

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dataviz") as pool:
            while pending or running:
                progressed = False
                if cancel_event is not None and cancel_event.is_set() and pending:
                    for node_id in sorted(pending):
                        node = plan.nodes[node_id]
                        result.nodes[node_id] = NodeResult(
                            node_id=node_id,
                            node_type=node.kind,
                            status="cancelled",
                            finished_at=now(),
                            diagnostics=result.nodes[node_id].diagnostics,
                            error={
                                "type": "ExecutionCancelled",
                                "message": "Query Run was cancelled before this node started",
                                "code": "cancelled",
                            },
                        )
                        emit(
                            "node_cancelled",
                            node,
                            error=result.nodes[node_id].error,
                            data={"outputs": declared_output_references(node)},
                        )
                    pending.clear()
                    publish_snapshot()
                    progressed = True
                for node_id in list(pending):
                    node = plan.nodes[node_id]
                    dependency_results = [result.nodes[value] for value in node.dependencies]
                    if any(
                        item.status in {"error", "unavailable", "cancelled"}
                        for item in dependency_results
                    ):
                        result.nodes[node_id] = NodeResult(
                            node_id=node_id,
                            node_type=node.kind,
                            status="unavailable",
                            finished_at=now(),
                            diagnostics=result.nodes[node_id].diagnostics,
                            error={"type": "dependency_failed", "message": "An upstream node failed"},
                        )
                        pending.remove(node_id)
                        publish_snapshot()
                        emit(
                            "node_unavailable",
                            node,
                            error=result.nodes[node_id].error,
                            data={"outputs": declared_output_references(node)},
                        )
                        progressed = True
                    elif all(item.status in {"ready", "empty"} for item in dependency_results):
                        result.nodes[node_id].status = "queued"
                        emit("node_queued", node)
                        result.nodes[node_id].status = "loading"
                        publish_snapshot()
                        future = pool.submit(
                            self._execute_node,
                            node,
                            dashboard,
                            parameters,
                            result,
                            store,
                            refresh,
                            emit,
                            cancel_event,
                            adapters,
                        )
                        running[future] = node_id
                        pending.remove(node_id)
                        progressed = True

                if running:
                    completed, _ = wait(running, return_when=FIRST_COMPLETED)
                    for future in completed:
                        node_id = running.pop(future)
                        node = plan.nodes[node_id]
                        try:
                            node_result = future.result()
                        except Exception as exc:
                            error = exc.as_dict() if isinstance(exc, DatavizError) else {
                                "type": type(exc).__name__, "message": str(exc)
                            }
                            node_result = NodeResult(
                                node_id=node_id,
                                node_type=node.kind,
                                status="error",
                                finished_at=now(),
                                diagnostics=result.nodes[node_id].diagnostics,
                                error=error,
                            )
                        result.nodes[node_id] = node_result
                        if node_result.status in {"ready", "empty"}:
                            for name, descriptor in node_result.outputs.items():
                                result.outputs[f"{node_id}/{name}"] = descriptor
                        publish_snapshot()
                        declared_outputs = declared_output_references(node)
                        if node_result.status in {"ready", "empty"}:
                            emit(
                                "node_ready",
                                node,
                                duration_ms=node_result.duration_ms,
                                data={
                                    "origin": node_result.result_origin,
                                    "outputs": sorted(result.outputs.keys() & set(declared_outputs)),
                                },
                            )
                            for name, descriptor in node_result.outputs.items():
                                reference = f"{node_id}/{name}"
                                emit(
                                    "output_ready",
                                    node,
                                    data={
                                        "reference": reference,
                                        "artifact": descriptor.model_dump(mode="json", by_alias=True),
                                    },
                                )
                        elif node_result.status == "cancelled":
                            emit(
                                "node_cancelled",
                                node,
                                duration_ms=node_result.duration_ms,
                                error=node_result.error,
                                data={"outputs": declared_outputs},
                            )
                        else:
                            emit(
                                "node_error",
                                node,
                                duration_ms=node_result.duration_ms,
                                error=node_result.error,
                                data={"outputs": declared_outputs},
                            )
                        progressed = True
                if not progressed and pending:
                    raise ExecutionFailure("Execution deadlock detected", details=sorted(pending))

        succeeded_targets = [
            result.nodes[node_id].status in {"ready", "empty"}
            for node_id in plan.targets
        ]
        failures = [
            item
            for item in result.nodes.values()
            if item.status in {"error", "unavailable"}
        ]
        cancelled = any(
            result.nodes[node_id].status == "cancelled" for node_id in plan.targets
        ) or (cancel_event is not None and cancel_event.is_set())
        if cancelled:
            result.status = "cancelled"
        elif all(succeeded_targets) and not failures:
            result.status = "ready"
        elif any(succeeded_targets):
            result.status = "partial"
        else:
            result.status = "error"
        result.finished_at = now()
        result.outputs = {
            f"{node_id}/{name}": descriptor
            for node_id, node in result.nodes.items()
            if node.status in {"ready", "empty"}
            for name, descriptor in node.outputs.items()
        }
        if (
            query_contract_fingerprint(dashboard, result.query_nodes)
            != result.query_contract_hash
        ):
            raise ExecutionFailure(
                "Dashboard query code changed while the Query Run was executing",
                details={
                    "code": "dashboard_changed_during_query",
                    "run_id": result.run_id,
                    "dashboard": result.dashboard,
                    "action": "Run query again",
                },
            )
        publish_snapshot()
        store.write_run_document(
            "result.json",
            result.model_dump_json(indent=2, by_alias=True),
        )
        terminal_event = (
            "run_ready"
            if result.status in {"ready", "partial"}
            else "run_cancelled"
            if result.status == "cancelled"
            else "run_error"
        )
        emit(terminal_event, data={"status": result.status})
        return result

    def _execute_node(
        self,
        node: PlanNode,
        dashboard: LoadedDashboard,
        parameters: dict[str, Any],
        run_result: RunResult,
        store: ArtifactStore,
        refresh: bool,
        emit,
        cancel_event: threading.Event | None,
        adapters: AdapterResolver,
    ) -> NodeResult:
        started = time.perf_counter()
        started_at = now()
        diagnostics = dict(run_result.nodes[node.id].diagnostics)
        emit("node_started", node)
        context: ExecutionContext | None = None
        execution_logs: list[dict[str, Any]] = []
        secrets = adapters.all_redaction_values()
        is_python_node = node.kind == "dataset_transform" or (
            node.kind == "source" and node.definition.type == "python"
        )

        def collect_log(record: dict[str, Any]) -> None:
            normalized = redact_value(
                {**record, "node_id": node.id},
                secrets,
            )
            execution_logs.append(normalized)
            emit(
                "node_log",
                node,
                message=str(normalized.get("message", "")),
                data={
                    "level": normalized.get("level", "info"),
                    "fields": normalized.get("fields", {}),
                },
            )

        try:
            context = self._context_for_node(
                node, dashboard, parameters, run_result, store, adapters
            )
            definition = node.definition
            cache_key = self._cache_key(
                node, dashboard, parameters, run_result, adapters
            )
            cached = None if refresh else self.cache.load(cache_key, definition.cache, store)
            if cached is not None:
                duration = int((time.perf_counter() - started) * 1000)
                return NodeResult(
                    node_id=node.id,
                    node_type=node.kind,
                    status=output_status(cached),
                    result_origin="cache",
                    started_at=started_at,
                    finished_at=now(),
                    duration_ms=duration,
                    outputs=cached,
                    diagnostics=diagnostics,
                )
            if node.kind == "source" and definition.type == "python":
                execution_logs.append(
                    _system_log("info", "runtime_started", "Python Source started", node_id=node.id)
                )
                outputs = execute_python_node(
                    definition=definition,
                    definition_path=node.definition_path,
                    context=context,
                    node_id=node.id,
                    node_kind=node.kind,
                    cancel_event=cancel_event,
                    progress_callback=lambda value, message: emit(
                        "node_progress",
                        node,
                        message=message,
                        data={"value": value},
                    ),
                    log_callback=collect_log,
                    redaction_values=secrets,
                )
            elif node.kind == "source":
                runner = SOURCE_RUNNERS[definition.type]

                def on_retry(data: dict[str, Any]) -> None:
                    emit(
                        "node_retrying",
                        node,
                        message=(
                            f"{node.id} timed out; retrying immediately "
                            f"({data['next_attempt']}/{data['max_attempts']})"
                        ),
                        data=data,
                    )

                value = runner.execute(
                    SourceRequest(
                        definition_path=node.definition_path,
                        definition=definition,
                        context=context,
                        adapters=adapters,
                        adapter_bindings=dashboard.definition.adapters,
                        node_id=node.id,
                        on_retry=on_retry,
                        cancel_event=cancel_event,
                    )
                )
                if cancel_event is not None and cancel_event.is_set():
                    raise ExecutionFailure(
                        f"{node.id} was cancelled",
                        details={"code": "cancelled", "node_id": node.id},
                    )
                named = bool(definition.outputs) and isinstance(value, dict)
                outputs = normalize_outputs(
                    value,
                    store=store,
                    node_id=node.id,
                    declared=definition.outputs,
                    named=named,
                    metadata={"title": definition.name or node.local_id},
                )
            else:
                execution_logs.append(
                    _system_log(
                        "info",
                        "runtime_started",
                        "Dataset Transform started",
                        node_id=node.id,
                    )
                )
                outputs = execute_python_node(
                    definition=definition,
                    definition_path=node.definition_path,
                    context=context,
                    node_id=node.id,
                    node_kind=node.kind,
                    cancel_event=cancel_event,
                    progress_callback=lambda value, message: emit(
                        "node_progress",
                        node,
                        message=message,
                        data={"value": value},
                    ),
                    log_callback=collect_log,
                    redaction_values=secrets,
                )
            self.cache.save(cache_key, definition.cache, outputs, store)

            duration = int((time.perf_counter() - started) * 1000)
            log = None
            if is_python_node:
                execution_logs.append(
                    _system_log(
                        "info",
                        "runtime_completed",
                        "Python node completed",
                        node_id=node.id,
                        duration_ms=duration,
                    )
                )
                log = _write_python_log(
                    store,
                    f"{node.id}__execution",
                    execution_logs,
                    node_id=node.id,
                )
                diagnostics["log_records"] = len(execution_logs)
            return NodeResult(
                node_id=node.id,
                node_type=node.kind,
                status=output_status(outputs),
                result_origin="executed",
                started_at=started_at,
                finished_at=now(),
                duration_ms=duration,
                outputs=outputs,
                diagnostics=diagnostics,
                log=log,
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            local_traceback = redact_text(traceback.format_exc(), secrets)
            remote_traceback = (
                exc.details.get("traceback")
                if isinstance(exc, DatavizError) and isinstance(exc.details, dict)
                else None
            )
            full_traceback = redact_text(remote_traceback or local_traceback, secrets)
            error = redact_value(
                exc.as_dict()
                if isinstance(exc, DatavizError)
                else {"type": type(exc).__name__, "message": str(exc)},
                secrets,
            )
            error["traceback"] = full_traceback
            if is_python_node:
                execution_logs.append(
                    _system_log(
                        "error",
                        "runtime_failed",
                        redact_text(exc, secrets),
                        node_id=node.id,
                        error_type=type(exc).__name__,
                        traceback=full_traceback,
                    )
                )
                log = _write_python_log(
                    store,
                    f"{node.id}__error",
                    execution_logs,
                    node_id=node.id,
                )
                diagnostics["log_records"] = len(execution_logs)
            else:
                log = store.write_text(
                    re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{node.id}__error"),
                    full_traceback,
                    kind="text",
                    format="text",
                    metadata={"role": "execution_log", "node_id": node.id},
                )
            error["log"] = log.model_dump(mode="json", by_alias=True)
            cancelled = (
                isinstance(exc, DatavizError)
                and isinstance(exc.details, dict)
                and exc.details.get("code") == "cancelled"
            )
            return NodeResult(
                node_id=node.id,
                node_type=node.kind,
                status="cancelled" if cancelled else "error",
                started_at=started_at,
                finished_at=now(),
                duration_ms=duration,
                diagnostics=diagnostics,
                log=log,
                error=error,
            )
        finally:
            if context is not None:
                context.dispose()

    def _inspect_node(
        self,
        node: PlanNode,
        dashboard: LoadedDashboard,
        parameters: dict[str, Any],
        run_result: RunResult,
        store: ArtifactStore,
        adapters: AdapterResolver,
    ) -> dict[str, Any]:
        if node.kind != "source" or node.definition.type != "sql":
            return {}
        context: ExecutionContext | None = None
        try:
            context = self._context_for_node(
                node,
                dashboard,
                parameters,
                run_result,
                store,
                adapters,
            )
            request = SourceRequest(
                definition_path=node.definition_path,
                definition=node.definition,
                context=context,
                adapters=adapters,
                adapter_bindings=dashboard.definition.adapters,
                node_id=node.id,
            )
            return SOURCE_RUNNERS["sql"].diagnostics(request)
        except Exception as error:
            secrets = adapters.redaction_values(
                node.definition.adapter,
                dashboard.definition.adapters,
            )
            return {
                "inspection_error": {
                    "type": type(error).__name__,
                    "message": redact_text(error, secrets),
                }
            }
        finally:
            if context is not None:
                context.dispose()

    def _context_for_node(
        self,
        node: PlanNode,
        dashboard: LoadedDashboard,
        parameters: dict[str, Any],
        run_result: RunResult,
        store: ArtifactStore,
        adapters: AdapterResolver,
    ) -> ExecutionContext:
        inputs = {}
        for input_name, reference in node.inputs.items():
            dependency = run_result.nodes[reference.node_id]
            artifact = dependency.outputs.get(reference.output)
            if not artifact:
                raise ExecutionFailure(
                    f"Input {input_name} references missing output: {reference.canonical}"
                )
            inputs[input_name] = artifact
        adapter = None
        if (
            node.kind == "source"
            and node.definition.type == "python"
            and node.definition.adapter
        ):
            adapter = adapters.runtime_config(
                node.definition.adapter,
                dashboard.definition.adapters,
            )
        context = ExecutionContext(
            workspace_root=self.workspace.root,
            dashboard_root=dashboard.root,
            run_id=run_result.run_id,
            query_inputs=project_query_inputs(node.parameter_inputs, parameters),
            compute_params={},
            selections={},
            selection_state={},
            inputs=inputs,
            store=store,
            adapter=adapter,
        )
        input_schemas = getattr(node.definition, "input_schemas", {})
        for input_name, schema in input_schemas.items():
            if input_name not in inputs:
                raise ExecutionFailure(
                    f"Input schema references undeclared input: {input_name}"
                )
            descriptor = inputs[input_name]
            if descriptor.kind != "table":
                raise ExecutionFailure(
                    f"Input {input_name} is {descriptor.kind}, but its schema requires a table"
                )
            validate_table_schema(
                store.read_table(descriptor),
                schema,
                label=f"Input {input_name}",
                code="input_schema_mismatch",
            )
        return context

    def _cache_key(
        self,
        node: PlanNode,
        dashboard: LoadedDashboard,
        parameters: dict[str, Any],
        result: RunResult,
        adapters: AdapterResolver,
    ) -> str:
        definition = node.definition
        files: dict[str, str] = {}
        for field in ("path", "code"):
            value = getattr(definition, field, None)
            if value:
                if field == "path" and getattr(definition, "adapter", None):
                    path = adapters.resolve_path(
                        definition.adapter,
                        value,
                        dashboard.definition.adapters,
                    )
                else:
                    path = (node.definition_path.parent / value).resolve()
                if path.exists():
                    files[field] = hash_path(path)
        for dependency in getattr(definition, "code_dependencies", []):
            path = (node.definition_path.parent / dependency).resolve()
            if path.exists():
                files[f"dependency:{dependency}"] = hash_path(path)
        upstream = {
            dependency: {
                name: item.content_hash
                for name, item in result.nodes[dependency].outputs.items()
            }
            for dependency in node.dependencies
        }
        payload = {
            "dashboard": dashboard.definition.id,
            "node": node.id,
            "definition": definition.model_dump(mode="json", by_alias=True),
            "query_inputs": project_query_inputs(node.parameter_inputs, parameters),
            "files": files,
            "upstream": upstream,
            "adapter": (
                adapters.fingerprint(
                    definition.adapter,
                    dashboard.definition.adapters,
                )
                if getattr(definition, "adapter", None)
                else None
            ),
            "runtime": package_fingerprint(
                getattr(definition, "python_dependencies", [])
            ),
        }
        return self.cache.key(payload)
