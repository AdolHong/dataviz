from __future__ import annotations

import re
import threading
import time
import traceback
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.auth import AdapterResolver
from dataviz.errors import DatavizError, ExecutionFailure, SourceFailure, ValidationFailure
from dataviz.identifiers import is_stable_id
from dataviz.execution.cache import NodeCache
from dataviz.execution.context import ExecutionContext
from dataviz.execution.fingerprint import ensure_query_run_compatible
from dataviz.execution.node_support import hash_path, output_status, package_fingerprint
from dataviz.execution.outputs import validate_table_schema
from dataviz.execution.parameters import project_query_inputs
from dataviz.execution.python_process import execute_python_node
from dataviz.execution.references import OutputReference, parse_output_reference
from dataviz.execution.results import InteractionResult, NodeResult, RunResult
from dataviz.redaction import redact_text, redact_value
from dataviz.workspace.loader import (
    LoadedDashboard,
    LoadedWorkspace,
    dashboard_validation_diagnostics,
)
from dataviz.workspace.controls import (
    project_selection_values,
    resolve_compute_values,
    resolve_selection_states,
    scoped_control_registry,
)


InteractionObserver = Callable[[dict[str, Any]], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class InteractivePlanNode:
    id: str
    local_id: str
    definition_path: Path
    definition: Any
    inputs: dict[str, OutputReference]
    dependencies: set[str]
    query_inputs: dict[str, Any]
    selection_inputs: dict[str, str]
    compute_inputs: dict[str, str]


def normalize_interactive_target(value: str) -> str:
    raw = value.strip()
    if not is_stable_id(raw):
        raise ValidationFailure(
            "Interactive target must be a stable Interactive Transform id",
            details={"code": "interactive_target_invalid", "target": value},
        )
    return raw


def compile_interactive_plan(
    dashboard: LoadedDashboard, target: str
) -> list[InteractivePlanNode]:
    target_id = normalize_interactive_target(target)
    if target_id not in dashboard.interactive_transforms:
        raise ValidationFailure(
            f"Unknown Interactive Transform: {target_id}",
            details={"code": "interactive_transform_unknown", "id": target_id},
        )

    contract = dashboard.dependency_contract
    ordered = contract.interactive_closure(target_id)
    return [
        InteractivePlanNode(
            id=f"interactive:{identifier}",
            local_id=identifier,
            definition_path=dashboard.interactive_transforms[identifier][0],
            definition=dashboard.interactive_transforms[identifier][1],
            inputs={
                name: parse_output_reference(value)
                for name, value in contract.interactive_inputs[identifier].items()
            },
            dependencies={
                f"interactive:{dependency}"
                for dependency in contract.interactive_dependencies[identifier]
            },
            query_inputs=dict(contract.interactive_parameter_inputs[identifier]),
            selection_inputs=dict(contract.interactive_selection_inputs[identifier]),
            compute_inputs=dict(contract.interactive_compute_inputs[identifier]),
        )
        for identifier in ordered
    ]


def _structured_log_record(
    level: str, event: str, message: str, **fields: Any
) -> dict[str, Any]:
    return {
        "timestamp": _now(),
        "level": level,
        "event": event,
        "message": message,
        "fields": fields,
    }


def _write_interaction_log(
    store: ArtifactStore,
    artifact_id: str,
    records: list[dict[str, Any]],
    *,
    node_id: str,
    generation: int,
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
            "generation": generation,
            "record_count": len(records),
        },
    )


class InteractionExecutor:
    """Execute server-python Interactive Transforms against one immutable Query Run."""

    def __init__(
        self,
        workspace: LoadedWorkspace,
        *,
        cache: NodeCache | None = None,
        cache_namespace: str | None = None,
    ):
        self.workspace = workspace
        self.cache = cache or NodeCache(workspace.root, namespace=cache_namespace)
        try:
            self.redaction_values = AdapterResolver(
                workspace.root
            ).all_redaction_values()
        except SourceFailure:
            # Static preflight reports invalid Adapter files. Interactive computation
            # may still inspect an existing Run that does not consume that Adapter.
            self.redaction_values = ()

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

    def execute(
        self,
        run: RunResult,
        target: str,
        *,
        compute_parameters: dict[str, Any] | None = None,
        selection_state: dict[str, dict[str, Any]] | None = None,
        generation: int = 1,
        interaction_id: str | None = None,
        refresh: bool = False,
        cancel_event: threading.Event | None = None,
        observer: InteractionObserver | None = None,
        reusable_nodes: dict[str, NodeResult] | None = None,
        _dashboard: LoadedDashboard | None = None,
    ) -> InteractionResult:
        dashboard = _dashboard or self.ensure_valid(run.dashboard)
        if dashboard.definition.id != run.dashboard:
            raise ValueError("Prevalidated Dashboard does not match the Query Run")
        runtime = self.workspace.definition.runtime.model_copy(deep=True)
        ensure_query_run_compatible(dashboard, run)
        target_id = normalize_interactive_target(target)
        plan = compile_interactive_plan(dashboard, target_id)
        if run.status not in {"loading", "ready", "partial"}:
            raise ExecutionFailure(
                "Interactive computation requires an active or completed Query Run",
                details={"code": "query_run_not_ready", "status": run.status},
            )
        missing_inputs = sorted(
            {
                reference.canonical
                for node in plan
                for reference in node.inputs.values()
                if not reference.node_id.startswith("interactive:")
                and reference.canonical not in run.outputs
            }
        )
        if missing_inputs:
            loading = run.status == "loading"
            raise ExecutionFailure(
                (
                    "Interactive computation inputs are not ready"
                    if loading
                    else "Query Run does not contain the Interactive Transform inputs"
                ),
                details={
                    "code": (
                        "interactive_input_not_ready"
                        if loading
                        else "query_run_missing_interactive_inputs"
                    ),
                    "references": missing_inputs,
                    "required_targets": sorted(
                        {
                            parse_output_reference(reference).node_id
                            for reference in missing_inputs
                        }
                    ),
                    "status": run.status,
                    "action": (
                        "Wait for this Query Run branch"
                        if loading
                        else "Run query again with the required targets"
                    ),
                },
            )
        interaction_id = interaction_id or f"ix_{uuid.uuid4().hex[:16]}"
        compute_values = resolve_compute_values(
            dashboard.definition,
            compute_parameters,
        )
        resolved_selection_state = resolve_selection_states(
            dashboard.definition, selection_state
        )
        result = InteractionResult(
            interaction_id=interaction_id,
            generation=generation,
            run_id=run.run_id,
            workspace=run.workspace,
            dashboard=run.dashboard,
            target=target_id,
            status="loading",
            query_parameters=dict(run.query_parameters),
            compute_parameters=compute_values,
            selection_state=resolved_selection_state,
            nodes={
                node.id: NodeResult(
                    node_id=node.id,
                    node_type="interactive_transform",
                    status="not_run",
                )
                for node in plan
            },
        )
        store = ArtifactStore(self.workspace.root, run.run_id)

        def emit(event: str, **data: Any) -> None:
            if observer:
                observer(
                    {
                        "event": event,
                        "interaction_id": interaction_id,
                        "generation": generation,
                        **data,
                    }
                )

        emit("interaction_started", target=target_id)
        browser_nodes = [
            node for node in plan if node.definition.runtime != "server-python"
        ]
        if browser_nodes:
            for node in browser_nodes:
                result.nodes[node.id] = NodeResult(
                    node_id=node.id,
                    node_type="interactive_transform",
                    status="unavailable",
                    finished_at=_now(),
                    error={
                        "type": "runtime_unavailable",
                        "message": (
                            f"{node.definition.runtime} executes in a browser Worker, "
                            "not through the Server Compute API"
                        ),
                    },
                )
            result.status = "unavailable"
        else:
            nodes = {node.id: node for node in plan}
            pending = set(nodes)
            running: dict[Future, str] = {}
            max_workers = max(1, runtime.max_workers)
            with ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix=f"dataviz-{interaction_id}",
            ) as pool:
                while pending or running:
                    if cancel_event is not None and cancel_event.is_set():
                        for node_id in pending:
                            result.nodes[node_id].status = "cancelled"
                        pending.clear()
                    progressed = False
                    for node_id in list(pending):
                        node = nodes[node_id]
                        dependencies = [result.nodes[value] for value in node.dependencies]
                        if any(
                            item.status in {"error", "cancelled", "unavailable"}
                            for item in dependencies
                        ):
                            result.nodes[node_id] = NodeResult(
                                node_id=node_id,
                                node_type="interactive_transform",
                                status="unavailable",
                                finished_at=_now(),
                                error={
                                    "type": "dependency_unavailable",
                                    "message": "An upstream Interactive Transform is unavailable",
                                },
                            )
                            pending.remove(node_id)
                            progressed = True
                        elif all(
                            item.status in {"ready", "empty"}
                            for item in dependencies
                        ):
                            result.nodes[node_id].status = "queued"
                            emit("node_queued", node_id=node_id)
                            result.nodes[node_id].status = "loading"
                            future = pool.submit(
                                self._execute_node,
                                dashboard,
                                run,
                                result,
                                node,
                                store,
                                refresh=refresh,
                                cancel_event=cancel_event,
                                emit=emit,
                                reusable=(reusable_nodes or {}).get(node.id),
                                allow_generation_reuse=node.local_id != target_id,
                            )
                            running[future] = node_id
                            pending.remove(node_id)
                            progressed = True
                    if running:
                        completed, _ = wait(running, return_when=FIRST_COMPLETED)
                        for future in completed:
                            node_id = running.pop(future)
                            node = nodes[node_id]
                            node_result = future.result()
                            result.nodes[node_id] = node_result
                            if node_result.status in {"ready", "empty"}:
                                for name, descriptor in node_result.outputs.items():
                                    result.outputs[f"{node.id}/{name}"] = descriptor
                                emit(
                                    "node_ready",
                                    node_id=node.id,
                                    origin=node_result.result_origin,
                                    outputs=sorted(
                                        f"{node.id}/{name}"
                                        for name in node_result.outputs
                                    ),
                                )
                            else:
                                emit(
                                    "node_error",
                                    node_id=node.id,
                                    error=node_result.error,
                                )
                            progressed = True
                    if not progressed and pending:
                        raise ExecutionFailure(
                            "Interactive execution deadlock detected",
                            details={"nodes": sorted(pending)},
                        )

        if result.status == "loading":
            target_node = result.nodes[f"interactive:{target_id}"]
            result.status = {
                "ready": "ready",
                "empty": "ready",
                "cancelled": "cancelled",
                "unavailable": "unavailable",
            }.get(target_node.status, "error")
        result.finished_at = _now()
        store.write_run_document(
            f"interaction-{interaction_id}.json",
            result.model_dump_json(indent=2, by_alias=True),
        )
        emit("interaction_finished", status=result.status)
        return result

    def _execute_node(
        self,
        dashboard: LoadedDashboard,
        run: RunResult,
        interaction: InteractionResult,
        node: InteractivePlanNode,
        store: ArtifactStore,
        *,
        refresh: bool,
        cancel_event: threading.Event | None,
        emit: Callable[..., None],
        reusable: NodeResult | None = None,
        allow_generation_reuse: bool = False,
    ) -> NodeResult:
        started = time.perf_counter()
        started_at = _now()
        context: ExecutionContext | None = None
        evidence: dict[str, Any] = {"generation": interaction.generation}
        execution_logs: list[dict[str, Any]] = []

        def collect_log(record: dict[str, Any]) -> None:
            normalized = redact_value(
                {**record, "node_id": node.id, "generation": interaction.generation},
                self.redaction_values,
            )
            execution_logs.append(normalized)
            emit(
                "node_log",
                node_id=node.id,
                level=normalized.get("level", "info"),
                message=normalized.get("message", ""),
                fields=normalized.get("fields", {}),
            )

        try:
            inputs: dict[str, ArtifactDescriptor] = {}
            for name, reference in node.inputs.items():
                if reference.node_id.startswith("interactive:"):
                    descriptor = interaction.outputs.get(reference.canonical)
                else:
                    descriptor = run.outputs.get(reference.canonical)
                if descriptor is None:
                    raise ExecutionFailure(
                        f"Input {name} is not ready: {reference.canonical}",
                        details={
                            "code": "interactive_input_not_ready",
                            "input": name,
                            "reference": reference.canonical,
                        },
                    )
                inputs[name] = descriptor
            selection_registry = scoped_control_registry(
                dashboard.definition,
                kind="selection",
            )
            selection_value_map = project_selection_values(
                dashboard.definition,
                interaction.selection_state,
            )
            selection_filters = tuple(
                {
                    **selection_registry[control_key].as_dict(),
                    "alias": alias,
                    "state": interaction.selection_state.get(control_key),
                    "value": selection_value_map.get(control_key),
                }
                for alias, control_key in node.selection_inputs.items()
            )
            context = ExecutionContext(
                workspace_root=self.workspace.root,
                dashboard_root=dashboard.root,
                run_id=run.run_id,
                query_inputs=project_query_inputs(
                    node.query_inputs, run.query_parameters
                ),
                compute_params={
                    alias: interaction.compute_parameters.get(control_key)
                    for alias, control_key in node.compute_inputs.items()
                },
                selections={
                    alias: selection_value_map.get(control_key)
                    for alias, control_key in node.selection_inputs.items()
                },
                selection_state={
                    alias: interaction.selection_state.get(control_key, {})
                    for alias, control_key in node.selection_inputs.items()
                },
                selection_filters=selection_filters,
                inputs=inputs,
                store=store,
                adapter=None,
            )
            for name, schema in node.definition.input_schemas.items():
                descriptor = inputs[name]
                if descriptor.kind != "table":
                    raise ExecutionFailure(
                        f"Input {name} is {descriptor.kind}, but its schema requires a table"
                    )
                validate_table_schema(
                    store.read_table(descriptor),
                    schema,
                    label=f"Input {name}",
                    code="input_schema_mismatch",
                )
            cache_key = self._cache_key(node, context)
            evidence = {
                "generation": interaction.generation,
                "cache_key": cache_key,
                "query_inputs": context.query_inputs,
                "compute_parameters": context.compute_params,
                "selection_state": context.selection_state,
                "selections": context.selections,
                "inputs": {
                    name: {
                        "reference": node.inputs[name].canonical,
                        "content_hash": descriptor.content_hash,
                    }
                    for name, descriptor in inputs.items()
                },
            }
            reusable_artifacts_valid = False
            if reusable is not None:
                descriptors = list(reusable.outputs.values())
                if reusable.log is not None:
                    descriptors.append(reusable.log)
                try:
                    for descriptor in descriptors:
                        store.verify_owned(descriptor)
                except (OSError, ValueError):
                    pass
                else:
                    reusable_artifacts_valid = True
            if (
                not refresh
                and allow_generation_reuse
                and reusable is not None
                and reusable.status in {"ready", "empty"}
                and reusable.diagnostics.get("cache_key") == cache_key
                and reusable_artifacts_valid
            ):
                return reusable.model_copy(
                    deep=True,
                    update={
                        "result_origin": "generation",
                        "started_at": started_at,
                        "finished_at": _now(),
                        "duration_ms": int((time.perf_counter() - started) * 1000),
                        "diagnostics": {
                            **reusable.diagnostics,
                            "generation": interaction.generation,
                            "reused_from_generation": reusable.diagnostics.get("generation"),
                        },
                    },
                )
            cached = None if refresh else self.cache.load(
                cache_key, node.definition.cache, store
            )
            if cached is not None:
                return NodeResult(
                    node_id=node.id,
                    node_type="interactive_transform",
                    status=output_status(cached),
                    result_origin="cache",
                    started_at=started_at,
                    finished_at=_now(),
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    outputs=cached,
                    diagnostics=evidence,
                )

            artifact_node_id = (
                f"{node.id}__{interaction.interaction_id}__g{interaction.generation}"
            )
            execution_logs.append(
                _structured_log_record(
                    "info",
                    "runtime_started",
                    "Interactive Transform started",
                    node_id=node.id,
                    generation=interaction.generation,
                )
            )
            outputs = execute_python_node(
                definition=node.definition,
                definition_path=node.definition_path,
                context=context,
                node_id=artifact_node_id,
                node_kind="interactive_transform",
                cancel_event=cancel_event,
                progress_callback=lambda value, message: emit(
                    "node_progress",
                    node_id=node.id,
                    value=value,
                    message=message,
                ),
                log_callback=collect_log,
                redaction_values=self.redaction_values,
            )
            self.cache.save(cache_key, node.definition.cache, outputs, store)
            duration_ms = int((time.perf_counter() - started) * 1000)
            execution_logs.append(
                _structured_log_record(
                    "info",
                    "runtime_completed",
                    "Interactive Transform completed",
                    node_id=node.id,
                    generation=interaction.generation,
                    duration_ms=duration_ms,
                )
            )
            log = _write_interaction_log(
                store,
                f"{artifact_node_id}__execution",
                execution_logs,
                node_id=node.id,
                generation=interaction.generation,
            )
            evidence["log_records"] = len(execution_logs)
            return NodeResult(
                node_id=node.id,
                node_type="interactive_transform",
                status=output_status(outputs),
                result_origin="executed",
                started_at=started_at,
                finished_at=_now(),
                duration_ms=duration_ms,
                outputs=outputs,
                diagnostics=evidence,
                log=log,
            )
        except Exception as error:
            raw_traceback = (
                error.details.get("traceback")
                if isinstance(error, DatavizError)
                and isinstance(error.details, dict)
                and error.details.get("traceback")
                else traceback.format_exc()
            )
            full_traceback = redact_text(raw_traceback, self.redaction_values)
            payload = redact_value(
                (
                    error.as_dict()
                    if isinstance(error, DatavizError)
                    else {"type": type(error).__name__, "message": str(error)}
                ),
                self.redaction_values,
            )
            payload["traceback"] = full_traceback
            cancelled = (
                isinstance(error, DatavizError)
                and isinstance(error.details, dict)
                and error.details.get("code") == "cancelled"
            )
            execution_logs.append(
                _structured_log_record(
                    "error",
                    "runtime_failed",
                    redact_text(error, self.redaction_values),
                    node_id=node.id,
                    generation=interaction.generation,
                    error_type=type(error).__name__,
                    traceback=full_traceback,
                )
            )
            log = _write_interaction_log(
                store,
                f"{node.id}__{interaction.interaction_id}__error",
                execution_logs,
                node_id=node.id,
                generation=interaction.generation,
            )
            payload["log"] = log.model_dump(mode="json", by_alias=True)
            evidence["log_records"] = len(execution_logs)
            return NodeResult(
                node_id=node.id,
                node_type="interactive_transform",
                status="cancelled" if cancelled else "error",
                started_at=started_at,
                finished_at=_now(),
                duration_ms=int((time.perf_counter() - started) * 1000),
                log=log,
                error=payload,
                diagnostics=evidence,
            )
        finally:
            if context is not None:
                context.dispose()

    def _cache_key(
        self, node: InteractivePlanNode, context: ExecutionContext
    ) -> str:
        files: dict[str, str] = {}
        code_path = (node.definition_path.parent / node.definition.code).resolve()
        if code_path.exists():
            files["code"] = hash_path(code_path)
        for dependency in node.definition.code_dependencies:
            path = (node.definition_path.parent / dependency).resolve()
            if path.exists():
                files[f"dependency:{dependency}"] = hash_path(path)
        payload = {
            "protocol": "dataviz/interactive-transform/v2",
            "definition": node.definition.model_dump(mode="json", by_alias=True),
            "files": files,
            "inputs": {
                name: descriptor.content_hash
                for name, descriptor in context.inputs.items()
            },
            "query_inputs": context.query_inputs,
            "compute_parameters": context.compute_params,
            "selections": context.selections,
            "runtime": package_fingerprint(node.definition.python_dependencies),
        }
        return self.cache.key(payload)


def load_run_result(workspace_root: Path, run_id: str) -> RunResult:
    if not is_stable_id(run_id):
        raise ExecutionFailure(
            f"Invalid Query Run id: {run_id}",
            details={"code": "query_run_id_invalid", "run_id": run_id},
        )
    path = workspace_root.resolve() / ".dataviz" / "runs" / run_id / "result.json"
    if not path.is_file():
        raise ExecutionFailure(
            f"Query Run does not exist: {run_id}",
            details={"code": "query_run_not_found", "run_id": run_id},
        )
    try:
        result = RunResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as error:
        raise ExecutionFailure(
            f"Query Run metadata is corrupt: {run_id}",
            details={
                "code": "query_run_corrupt",
                "run_id": run_id,
                "path": str(path),
            },
        ) from error
    store = ArtifactStore(workspace_root, run_id)
    artifacts = {
        descriptor.artifact_id: descriptor
        for node in result.nodes.values()
        for descriptor in [*node.outputs.values(), *([node.log] if node.log else [])]
    }
    artifacts.update(
        {descriptor.artifact_id: descriptor for descriptor in result.outputs.values()}
    )
    try:
        for descriptor in artifacts.values():
            store.verify_owned(descriptor)
    except (OSError, ValueError) as error:
        raise ExecutionFailure(
            f"Query Run Artifact is corrupt: {run_id}",
            details={
                "code": "query_run_artifact_corrupt",
                "run_id": run_id,
                "artifact_id": descriptor.artifact_id,
                "message": str(error),
            },
        ) from error
    return result
