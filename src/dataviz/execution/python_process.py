from __future__ import annotations

import multiprocessing
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.errors import DatavizError, ExecutionFailure
from dataviz.execution.context import ExecutionContext
from dataviz.execution.imports import load_entrypoint
from dataviz.execution.outputs import OutputBundle, normalize_outputs
from dataviz.redaction import adapter_secret_values, redact_text, redact_value


def _terminate_process(process: multiprocessing.Process) -> None:
    """Stop a Python worker and escalate if graceful termination is ignored."""
    if not process.is_alive():
        process.join(timeout=0.1)
        return
    process.terminate()
    process.join(timeout=1)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=1)


def _run_python_node(
    connection,
    *,
    workspace_root: str,
    dashboard_root: str,
    run_id: str,
    query_parameter_state: dict[str, dict[str, Any]],
    query_inputs: dict[str, Any],
    control_inputs: dict[str, Any],
    control_state: dict[str, dict[str, Any]],
    control_filters: tuple[dict[str, Any], ...],
    inputs: dict[str, dict[str, Any]],
    adapter: dict[str, Any] | None,
    definition: Any,
    definition_path: str,
    node_id: str,
    node_kind: str,
) -> None:
    """Child-process entrypoint. It writes outputs into the run Artifact Store."""
    bytecode_cache = tempfile.TemporaryDirectory(prefix="dataviz-python-")
    previous_cache_prefix = sys.pycache_prefix
    sys.pycache_prefix = bytecode_cache.name
    context: ExecutionContext | None = None
    try:
        store = ArtifactStore(Path(workspace_root), run_id)
        context = ExecutionContext(
            workspace_root=Path(workspace_root),
            dashboard_root=Path(dashboard_root),
            run_id=run_id,
            query_parameter_state=query_parameter_state,
            query_inputs=query_inputs,
            control_inputs=control_inputs,
            control_state=control_state,
            control_filters=control_filters,
            inputs={
                name: ArtifactDescriptor.model_validate(descriptor)
                for name, descriptor in inputs.items()
            },
            store=store,
            adapter=adapter,
            _progress_callback=lambda value, message: connection.send(
                {
                    "ok": None,
                    "event": "progress",
                    "value": value,
                    "message": message,
                }
            ),
            _log_callback=lambda record: connection.send(
                {
                    "ok": None,
                    "event": "log",
                    "record": record,
                }
            ),
        )
        code_path = (Path(definition_path).parent / definition.code).resolve()
        value = load_entrypoint(code_path, definition.entrypoint)(context)
        named = isinstance(value, dict) and (
            node_kind in {"dataset_transform", "interactive_transform"}
            or bool(definition.outputs)
        )
        outputs = normalize_outputs(
            value,
            store=store,
            node_id=node_id,
            declared=definition.outputs,
            named=named,
            metadata={"title": definition.name or node_id.split(":", 1)[-1]},
        )
        connection.send(
            {
                "ok": True,
                "outputs": {
                    name: descriptor.model_dump(mode="json", by_alias=True)
                    for name, descriptor in outputs.items()
                },
            }
        )
    except BaseException as exc:  # child boundary must serialize every failure
        error = (
            exc.as_dict()
            if isinstance(exc, DatavizError)
            else {"type": type(exc).__name__, "message": str(exc)}
        )
        error["remote_class"] = type(exc).__name__
        error["traceback"] = traceback.format_exc()
        connection.send(
            {
                "ok": False,
                "error": error,
            }
        )
    finally:
        if context is not None:
            context.dispose()
        sys.pycache_prefix = previous_cache_prefix
        bytecode_cache.cleanup()
        connection.close()


def execute_python_node(
    *,
    definition: Any,
    definition_path: Path,
    context: ExecutionContext,
    node_id: str,
    node_kind: str,
    cancel_event: Any | None = None,
    progress_callback: Callable[[float | None, str], None] | None = None,
    log_callback: Callable[[dict[str, Any]], None] | None = None,
    redaction_values: tuple[str, ...] = (),
) -> OutputBundle:
    """Execute trusted workspace Python in an isolated process with a hard timeout."""
    secrets = tuple(
        sorted(
            {*adapter_secret_values(context.adapter), *redaction_values},
            key=len,
            reverse=True,
        )
    )
    process_context = multiprocessing.get_context("spawn")
    parent, child = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_run_python_node,
        kwargs={
            "connection": child,
            "workspace_root": str(context.workspace_root),
            "dashboard_root": str(context.dashboard_root),
            "run_id": context.run_id,
            "query_parameter_state": context.query_parameter_state,
            "query_inputs": context.query_inputs,
            "control_inputs": context.control_inputs,
            "control_state": context.control_state,
            "control_filters": context.control_filters,
            "inputs": {
                name: descriptor.model_dump(mode="json", by_alias=True)
                for name, descriptor in context.inputs.items()
            },
            "adapter": context.adapter,
            "definition": definition,
            "definition_path": str(definition_path),
            "node_id": node_id,
            "node_kind": node_kind,
        },
        name=f"dataviz-{node_id.replace(':', '-')}",
    )
    timeout = definition.timeout_seconds
    deadline = time.monotonic() + timeout if timeout else None
    payload: dict[str, Any] | None = None
    process_started = False
    try:
        try:
            process.start()
            process_started = True
        except Exception as exc:
            raise ExecutionFailure(
                f"Python {node_kind} process could not start",
                file=definition_path,
                details={
                    "code": "python_process_start_failed",
                    "node_id": node_id,
                    "remote_type": type(exc).__name__,
                },
            ) from exc
        finally:
            child.close()

        while payload is None:
            if parent.poll(0.05):
                try:
                    candidate = parent.recv()
                except EOFError:
                    candidate = None
                if candidate is None:
                    if not process.is_alive():
                        raise ExecutionFailure(
                            f"Python {node_kind} process exited without a result",
                            file=definition_path,
                            details={
                                "code": "python_process_exited",
                                "exit_code": process.exitcode,
                                "node_id": node_id,
                            },
                        )
                    continue
                if candidate.get("event") == "progress":
                    if progress_callback:
                        progress_callback(
                            candidate.get("value"),
                            redact_text(candidate.get("message", ""), secrets),
                        )
                    continue
                if candidate.get("event") == "log":
                    if log_callback:
                        log_callback(redact_value(candidate.get("record", {}), secrets))
                    continue
                payload = candidate
                break
            if cancel_event is not None and cancel_event.is_set():
                _terminate_process(process)
                raise ExecutionFailure(
                    f"Python {node_kind} was cancelled",
                    file=definition_path,
                    details={"code": "cancelled", "node_id": node_id},
                )
            if deadline is not None and time.monotonic() >= deadline:
                _terminate_process(process)
                raise ExecutionFailure(
                    f"Python {node_kind} exceeded {timeout:g} seconds",
                    file=definition_path,
                    details={
                        "code": "python_node_timeout",
                        "timeout_seconds": timeout,
                        "node_id": node_id,
                    },
                )
            if not process.is_alive():
                raise ExecutionFailure(
                    f"Python {node_kind} process exited without a result",
                    file=definition_path,
                    details={
                        "code": "python_process_exited",
                        "exit_code": process.exitcode,
                        "node_id": node_id,
                    },
                )
    finally:
        parent.close()
        if process_started:
            # A successful child has already published complete Artifacts, but it
            # still needs a brief chance to run context/module cleanup and close
            # its pipe. Timeout and cancellation paths terminate it earlier.
            if payload is not None:
                process.join(timeout=1)
            _terminate_process(process)

    if not payload["ok"]:
        remote = redact_value(payload["error"], secrets)
        details = dict(remote.get("details") or {})
        details.update(
            {
                "remote_type": remote.get("remote_class", remote.get("type", "RemoteError")),
                "traceback": remote.get("traceback", ""),
            }
        )
        raise ExecutionFailure(
            f"Python {node_kind} failed: {remote['message']}",
            file=definition_path,
            details=details,
        )
    return {
        name: ArtifactDescriptor.model_validate(descriptor)
        for name, descriptor in payload["outputs"].items()
    }
