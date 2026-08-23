from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from packaging.requirements import Requirement

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.errors import DatavizError, ExecutionFailure, ValidationFailure
from dataviz.execution.cache import NodeCache
from dataviz.execution.context import ExecutionContext
from dataviz.execution.outputs import validate_table_schema
from dataviz.execution.python_process import execute_python_node
from dataviz.execution.references import OutputReference, parse_output_reference
from dataviz.execution.results import InteractionResult, NodeResult, RunResult
from dataviz.value_contract import ValueContractViolation, normalize_control_value
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace
from dataviz.workspace.selections import resolve_selection_values


InteractionObserver = Callable[[dict[str, Any]], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_value(definition, value: Any) -> Any:
    try:
        return normalize_control_value(definition, value)
    except ValueContractViolation as error:
        raise ExecutionFailure(
            f"Invalid Compute Parameter {definition.id}: {error.message}",
            details={
                "code": f"compute_parameter_{error.code}",
                "id": definition.id,
                "reason": error.message,
            },
        ) from error


def resolve_compute_parameters(
    dashboard: LoadedDashboard, values: dict[str, Any] | None
) -> dict[str, Any]:
    """Resolve the Compute namespace without accepting Query Parameter keys."""
    supplied = values or {}
    definitions = {
        item.id: item for item in dashboard.definition.compute_parameters
    }
    unknown = sorted(set(supplied) - set(definitions))
    if unknown:
        raise ExecutionFailure(
            "Unknown Compute Parameters",
            details={"code": "compute_parameter_unknown", "ids": unknown},
        )
    return {
        identifier: _coerce_value(definition, supplied.get(identifier, definition.default))
        for identifier, definition in definitions.items()
    }


@dataclass(slots=True)
class InteractivePlanNode:
    id: str
    local_id: str
    definition_path: Path
    definition: Any
    inputs: dict[str, OutputReference]
    dependencies: set[str]


def _target_id(value: str) -> str:
    raw = value.strip()
    if raw.startswith("interactive:"):
        return raw.split("/", 1)[0].split(":", 1)[1]
    if ":" in raw or "/" in raw:
        raise ValidationFailure(
            "Interactive target must be an Interactive Transform id or interactive:<id>"
        )
    return raw


def compile_interactive_plan(
    dashboard: LoadedDashboard, target: str
) -> list[InteractivePlanNode]:
    target_id = _target_id(target)
    if target_id not in dashboard.interactive_transforms:
        raise ValidationFailure(
            f"Unknown Interactive Transform: {target_id}",
            details={"code": "interactive_transform_unknown", "id": target_id},
        )

    selected: set[str] = set()
    visiting: set[str] = set()
    ordered: list[str] = []

    def include(identifier: str) -> None:
        if identifier in selected:
            return
        if identifier in visiting:
            raise ValidationFailure(
                "Interactive Transform dependency graph contains a cycle",
                details={"code": "interactive_cycle", "node": identifier},
            )
        visiting.add(identifier)
        definition = dashboard.interactive_transforms[identifier][1]
        for value in definition.inputs.values():
            reference = parse_output_reference(value)
            if reference.node_id.startswith("interactive:"):
                dependency_id = reference.node_id.split(":", 1)[1]
                if dependency_id not in dashboard.interactive_transforms:
                    raise ValidationFailure(
                        f"Unknown Interactive dependency: {dependency_id}"
                    )
                include(dependency_id)
        visiting.remove(identifier)
        selected.add(identifier)
        ordered.append(identifier)

    include(target_id)
    return [
        InteractivePlanNode(
            id=f"interactive:{identifier}",
            local_id=identifier,
            definition_path=dashboard.interactive_transforms[identifier][0],
            definition=dashboard.interactive_transforms[identifier][1],
            inputs={
                name: parse_output_reference(value)
                for name, value in dashboard.interactive_transforms[
                    identifier
                ][1].inputs.items()
            },
            dependencies={
                reference.node_id
                for reference in (
                    parse_output_reference(value)
                    for value in dashboard.interactive_transforms[
                        identifier
                    ][1].inputs.values()
                )
                if reference.node_id.startswith("interactive:")
            },
        )
        for identifier in ordered
    ]


def _hash_path(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for child in sorted(
        item
        for item in path.rglob("*")
        if item.is_file()
        and "__pycache__" not in item.parts
        and item.suffix not in {".pyc", ".pyo"}
        and ".git" not in item.parts
    ):
        digest.update(str(child.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _package_fingerprint(requirements: list[str]) -> dict[str, str]:
    values: dict[str, str] = {"python": ".".join(map(str, sys.version_info[:3]))}
    for raw in requirements:
        try:
            name = Requirement(raw).name
        except Exception:
            name = raw
        try:
            values[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            values[name] = "missing"
    return values


def _output_status(outputs: dict[str, ArtifactDescriptor]) -> str:
    row_counts = [
        int(item.metadata.get("row_count", 0))
        for item in outputs.values()
        if item.kind == "table"
    ]
    return "empty" if row_counts and all(value == 0 for value in row_counts) else "ready"


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

    def execute(
        self,
        run: RunResult,
        target: str,
        *,
        compute_parameters: dict[str, Any] | None = None,
        selections: dict[str, Any] | None = None,
        generation: int = 1,
        interaction_id: str | None = None,
        refresh: bool = False,
        cancel_event: threading.Event | None = None,
        observer: InteractionObserver | None = None,
        reusable_nodes: dict[str, NodeResult] | None = None,
    ) -> InteractionResult:
        dashboard = self.workspace.dashboard(run.dashboard)
        if run.status not in {"ready", "partial"}:
            raise ExecutionFailure(
                "Interactive computation requires a completed Query Run",
                details={"code": "query_run_not_ready", "status": run.status},
            )
        plan = compile_interactive_plan(dashboard, target)
        target_id = _target_id(target)
        interaction_id = interaction_id or f"ix_{uuid.uuid4().hex[:16]}"
        compute_values = resolve_compute_parameters(dashboard, compute_parameters)
        selection_values, _ = resolve_selection_values(
            dashboard.definition, selections
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
            selections=selection_values,
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
            max_workers = max(1, self.workspace.definition.runtime.max_workers)
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
        result_path = store.run_root / f"interaction-{interaction_id}.json"
        result_path.write_text(
            result.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
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
            normalized = {**record, "node_id": node.id, "generation": interaction.generation}
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
            context = ExecutionContext(
                workspace_root=self.workspace.root,
                dashboard_root=dashboard.root,
                run_id=run.run_id,
                query_params={
                    key: run.query_parameters.get(key)
                    for key in node.definition.query_params
                },
                compute_params={
                    key: interaction.compute_parameters.get(key)
                    for key in node.definition.compute_params
                },
                selections={
                    key: interaction.selections.get(key)
                    for key in node.definition.selections
                },
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
                "query_parameters": context.query_params,
                "compute_parameters": context.compute_params,
                "selections": context.selections,
                "inputs": {
                    name: {
                        "reference": node.inputs[name].canonical,
                        "content_hash": descriptor.content_hash,
                    }
                    for name, descriptor in inputs.items()
                },
            }
            reusable_files_exist = reusable is not None and all(
                not descriptor.path
                or (self.workspace.root / descriptor.path).is_file()
                for descriptor in reusable.outputs.values()
            )
            if (
                not refresh
                and allow_generation_reuse
                and reusable is not None
                and reusable.status in {"ready", "empty"}
                and reusable.diagnostics.get("cache_key") == cache_key
                and reusable_files_exist
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
                    status=_output_status(cached),
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
                status=_output_status(outputs),
                result_origin="executed",
                started_at=started_at,
                finished_at=_now(),
                duration_ms=duration_ms,
                outputs=outputs,
                diagnostics=evidence,
                log=log,
            )
        except Exception as error:
            full_traceback = (
                error.details.get("traceback")
                if isinstance(error, DatavizError)
                and isinstance(error.details, dict)
                and error.details.get("traceback")
                else traceback.format_exc()
            )
            payload = (
                error.as_dict()
                if isinstance(error, DatavizError)
                else {"type": type(error).__name__, "message": str(error)}
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
                    str(error),
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
            files["code"] = _hash_path(code_path)
        for dependency in node.definition.code_dependencies:
            path = (node.definition_path.parent / dependency).resolve()
            if path.exists():
                files[f"dependency:{dependency}"] = _hash_path(path)
        payload = {
            "protocol": "dataviz/interactive-transform/v1",
            "definition": node.definition.model_dump(mode="json", by_alias=True),
            "files": files,
            "inputs": {
                name: descriptor.content_hash
                for name, descriptor in context.inputs.items()
            },
            "query_parameters": context.query_params,
            "compute_parameters": context.compute_params,
            "selections": context.selections,
            "runtime": _package_fingerprint(node.definition.python_dependencies),
        }
        return self.cache.key(payload)


def load_run_result(workspace_root: Path, run_id: str) -> RunResult:
    path = workspace_root / ".dataviz" / "runs" / run_id / "result.json"
    if not path.is_file():
        raise ExecutionFailure(
            f"Query Run does not exist: {run_id}",
            details={"code": "query_run_not_found", "run_id": run_id},
        )
    return RunResult.model_validate_json(path.read_text(encoding="utf-8"))
