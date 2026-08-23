from __future__ import annotations

import multiprocessing
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.errors import ExecutionFailure
from dataviz.execution.context import ExecutionContext
from dataviz.execution.imports import load_entrypoint
from dataviz.execution.outputs import OutputBundle, normalize_outputs


def _run_python_node(
    connection,
    *,
    workspace_root: str,
    dashboard_root: str,
    run_id: str,
    params: dict[str, Any],
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
    try:
        store = ArtifactStore(Path(workspace_root), run_id)
        context = ExecutionContext(
            workspace_root=Path(workspace_root),
            dashboard_root=Path(dashboard_root),
            run_id=run_id,
            params=params,
            inputs={
                name: ArtifactDescriptor.model_validate(descriptor)
                for name, descriptor in inputs.items()
            },
            store=store,
            adapter=adapter,
        )
        code_path = (Path(definition_path).parent / definition.code).resolve()
        value = load_entrypoint(code_path, definition.entrypoint)(context)
        named = isinstance(value, dict) and (
            node_kind == "transform" or bool(definition.outputs)
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
        connection.send(
            {
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            }
        )
    finally:
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
) -> OutputBundle:
    """Execute trusted workspace Python in an isolated process with a hard timeout."""
    process_context = multiprocessing.get_context("spawn")
    parent, child = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_run_python_node,
        kwargs={
            "connection": child,
            "workspace_root": str(context.workspace_root),
            "dashboard_root": str(context.dashboard_root),
            "run_id": context.run_id,
            "params": context.params,
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
    process.start()
    child.close()
    timeout = definition.timeout_seconds
    deadline = time.monotonic() + timeout if timeout else None
    payload: dict[str, Any] | None = None
    try:
        while payload is None:
            if parent.poll(0.05):
                payload = parent.recv()
                break
            if deadline is not None and time.monotonic() >= deadline:
                process.terminate()
                process.join(timeout=1)
                raise ExecutionFailure(
                    f"Python {node_kind} exceeded {timeout:g} seconds",
                    file=definition_path,
                    details={"timeout_seconds": timeout, "node_id": node_id},
                )
            if not process.is_alive():
                raise ExecutionFailure(
                    f"Python {node_kind} process exited without a result",
                    file=definition_path,
                    details={"exit_code": process.exitcode, "node_id": node_id},
                )
    finally:
        parent.close()
        if process.is_alive():
            process.join(timeout=1)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)

    if not payload["ok"]:
        remote = payload["error"]
        raise ExecutionFailure(
            f"Python {node_kind} failed: {remote['message']}",
            file=definition_path,
            details={"remote_type": remote["type"], "traceback": remote["traceback"]},
        )
    return {
        name: ArtifactDescriptor.model_validate(descriptor)
        for name, descriptor in payload["outputs"].items()
    }
