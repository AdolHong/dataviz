from __future__ import annotations

import hashlib
import importlib.metadata
import re
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from packaging.requirements import Requirement

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.auth import AdapterResolver
from dataviz.errors import DatavizError, ExecutionFailure
from dataviz.execution.cache import NodeCache
from dataviz.execution.context import ExecutionContext
from dataviz.execution.events import EventObserver, ExecutionEvent
from dataviz.execution.outputs import normalize_outputs, validate_table_schema
from dataviz.execution.plan import PlanNode, compile_plan
from dataviz.execution.python_process import execute_python_node
from dataviz.execution.results import NodeResult, RunResult
from dataviz.sources import SOURCE_RUNNERS
from dataviz.sources.base import SourceRequest
from dataviz.value_contract import ValueContractViolation, normalize_control_value
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


SnapshotObserver = Callable[[RunResult], None]


def _hash_path(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for child in sorted(
        value
        for value in path.rglob("*")
        if value.is_file()
        and "__pycache__" not in value.parts
        and value.suffix not in {".pyc", ".pyo"}
        and ".git" not in value.parts
    ):
        digest.update(str(child.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _package_fingerprint(requirements: list[str]) -> dict[str, str]:
    names = {"workspace-dataviz", "pandas", "pyarrow", "pydantic"}
    for value in requirements:
        try:
            names.add(Requirement(value).name)
        except Exception:
            names.add(value)
    versions: dict[str, str] = {}
    for name in sorted(names):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "missing"
    versions["python"] = ".".join(map(str, sys.version_info[:3]))
    return versions


def _output_status(outputs: dict[str, Any]) -> str:
    """Use empty only when a node produced tables and every table is empty."""
    row_counts = [
        int(item.metadata.get("row_count", 0))
        for item in outputs.values()
        if item.kind == "table"
    ]
    return "empty" if row_counts and all(value == 0 for value in row_counts) else "ready"


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
    dashboard: LoadedDashboard, values: dict[str, Any] | None
) -> dict[str, Any]:
    provided = values or {}
    definitions = {item.id: item for item in dashboard.definition.query_parameters}
    unknown = sorted(set(provided) - set(definitions))
    if unknown:
        raise ExecutionFailure(
            "Unknown Query Parameters",
            details={"code": "query_parameter_unknown", "ids": unknown},
        )
    result: dict[str, Any] = {}
    for definition in dashboard.definition.query_parameters:
        value = provided.get(definition.id, definition.default)
        try:
            result[definition.id] = normalize_control_value(definition, value)
        except ValueContractViolation as error:
            raise ExecutionFailure(
                f"Invalid Query Parameter {definition.id}: {error.message}",
                details={
                    "code": f"query_parameter_{error.code}",
                    "id": definition.id,
                    "reason": error.message,
                },
            ) from error
    return result


class Executor:
    def __init__(self, workspace: LoadedWorkspace, *, cache_namespace: str | None = None):
        self.workspace = workspace
        self.cache = NodeCache(workspace.root, namespace=cache_namespace)
        self.adapters = AdapterResolver(workspace.root)
        self._event_lock = threading.Lock()

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
    ) -> RunResult:
        dashboard = self.workspace.dashboard(dashboard_id)
        parameters = resolve_query_parameters(dashboard, query_parameters)
        plan = compile_plan(dashboard, targets=targets)
        run_id = run_id or f"run_{uuid.uuid4().hex[:16]}"
        store = ArtifactStore(self.workspace.root, run_id)
        result = RunResult(
            run_id=run_id,
            status="loading",
            workspace=self.workspace.definition.id,
            dashboard=dashboard.definition.id,
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
        max_workers = max(1, self.workspace.definition.runtime.max_workers)

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
        publish_snapshot()
        (store.run_root / "result.json").write_text(
            result.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
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
    ) -> NodeResult:
        started = time.perf_counter()
        started_at = now()
        diagnostics = dict(run_result.nodes[node.id].diagnostics)
        emit("node_started", node)
        context: ExecutionContext | None = None
        execution_logs: list[dict[str, Any]] = []
        is_python_node = node.kind == "dataset_transform" or (
            node.kind == "source" and node.definition.type == "python"
        )

        def collect_log(record: dict[str, Any]) -> None:
            normalized = {**record, "node_id": node.id}
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
            context = self._context_for_node(node, dashboard, parameters, run_result, store)
            definition = node.definition
            cache_key = self._cache_key(node, dashboard, parameters, run_result)
            cached = None if refresh else self.cache.load(cache_key, definition.cache, store)
            if cached is not None:
                duration = int((time.perf_counter() - started) * 1000)
                return NodeResult(
                    node_id=node.id,
                    node_type=node.kind,
                    status=_output_status(cached),
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
                        adapters=self.adapters,
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
                status=_output_status(outputs),
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
            local_traceback = traceback.format_exc()
            remote_traceback = (
                exc.details.get("traceback")
                if isinstance(exc, DatavizError) and isinstance(exc.details, dict)
                else None
            )
            full_traceback = remote_traceback or local_traceback
            error = (
                exc.as_dict()
                if isinstance(exc, DatavizError)
                else {"type": type(exc).__name__, "message": str(exc)}
            )
            error["traceback"] = full_traceback
            if is_python_node:
                execution_logs.append(
                    _system_log(
                        "error",
                        "runtime_failed",
                        str(exc),
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
            )
            request = SourceRequest(
                definition_path=node.definition_path,
                definition=node.definition,
                context=context,
                adapters=self.adapters,
                adapter_bindings=dashboard.definition.adapters,
                node_id=node.id,
            )
            return SOURCE_RUNNERS["sql"].diagnostics(request)
        except Exception as error:
            return {
                "inspection_error": {
                    "type": type(error).__name__,
                    "message": str(error),
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
            adapter = self.adapters.runtime_config(
                node.definition.adapter,
                dashboard.definition.adapters,
            )
        context = ExecutionContext(
            workspace_root=self.workspace.root,
            dashboard_root=dashboard.root,
            run_id=run_result.run_id,
            query_params=parameters,
            compute_params={},
            selections={},
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
    ) -> str:
        definition = node.definition
        files: dict[str, str] = {}
        for field in ("path", "code"):
            value = getattr(definition, field, None)
            if value:
                if field == "path" and getattr(definition, "adapter", None):
                    path = self.adapters.resolve_path(
                        definition.adapter,
                        value,
                        dashboard.definition.adapters,
                    )
                else:
                    path = (node.definition_path.parent / value).resolve()
                if path.exists():
                    files[field] = _hash_path(path)
        for dependency in getattr(definition, "code_dependencies", []):
            path = (node.definition_path.parent / dependency).resolve()
            if path.exists():
                files[f"dependency:{dependency}"] = _hash_path(path)
        upstream = {
            dependency: {
                name: item.content_hash
                for name, item in result.nodes[dependency].outputs.items()
            }
            for dependency in node.dependencies
        }
        payload = {
            "definition": definition.model_dump(mode="json", by_alias=True),
            "query_parameters": {
                name: parameters.get(name)
                for name in definition.query_params
            },
            "files": files,
            "upstream": upstream,
            "adapter": (
                self.adapters.fingerprint(
                    definition.adapter,
                    dashboard.definition.adapters,
                )
                if getattr(definition, "adapter", None)
                else None
            ),
            "runtime": _package_fingerprint(
                getattr(definition, "python_dependencies", [])
            ),
        }
        return self.cache.key(payload)
