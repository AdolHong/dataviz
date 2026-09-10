"""Bounded, explicitly invoked trusted Python; never called by the read DAG."""

from __future__ import annotations

import hashlib
from contextlib import redirect_stderr, redirect_stdout
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
from typing import Any

from dataviz.actions import ActionContext, ActionResources, ServerActionDefinition, json_object
from dataviz.execution.action_journal import ActionJournal
from dataviz.execution.imports import load_entrypoint
from dataviz.execution.python_process import _terminate_process
from dataviz.redaction import adapter_secret_values, redact_text, redact_value


class _BoundResources:
    """Credential resolution is snapshotted before process start, not read twice."""

    def __init__(self, configs: dict[str, dict[str, object]]):
        self._configs = configs

    def config(self, alias: str) -> dict[str, object]:
        if alias not in self._configs:
            raise ValueError(f"Undeclared Action resource: {alias}")
        return json.loads(json.dumps(self._configs[alias]))

    def path(self, alias: str, relative_path: str) -> Path:
        config = self.config(alias)
        if config["type"] != "file":
            raise ValueError(f"Action resource {alias} is not a file Adapter")
        configured_root = config.get("root")
        if not isinstance(configured_root, str) or not Path(configured_root).is_absolute():
            raise ValueError(f"Action file resource requires a resolved absolute root: {alias}")
        root = Path(configured_root).resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"File path escapes Action resource root: {alias}")
        return path


def _execute(connection, code_path: str, code_files: dict[str, bytes], original_root: str,
             definition: ServerActionDefinition,
             request_id: str, payload: dict[str, Any], configs: dict[str, dict[str, object]],
             secrets: tuple[str, ...], dispatched_at: float) -> None:
    snapshot_root = None
    timings = {"worker_startup_ms": (time.monotonic() - dispatched_at) * 1000}
    load_started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="dataviz-action-") as bytecode, \
                tempfile.TemporaryDirectory(prefix="dataviz-action-code-") as code_directory, \
                open(os.devnull, "w") as discarded, \
                redirect_stdout(discarded), redirect_stderr(discarded):
            sys.pycache_prefix = bytecode
            snapshot_root = code_directory
            for relative, content in code_files.items():
                destination = Path(code_directory) / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            context = ActionContext(request_id, payload, _BoundResources(configs),
                                    frozenset(definition.invalidates))
            entrypoint = load_entrypoint(Path(code_directory) / code_path, definition.entrypoint)
            timings["code_load_ms"] = (time.monotonic() - load_started) * 1000
            execution_started = time.monotonic()
            try:
                result = entrypoint(context)
            finally:
                timings["python_execute_ms"] = (time.monotonic() - execution_started) * 1000
            result = json_object(result, label="Action result")
            # Redact keys too: credentials must not cross the process boundary even
            # if author code accidentally uses one as a result dictionary key.
            def safe(value):
                if isinstance(value, dict):
                    return {redact_text(key, secrets): safe(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [safe(item) for item in value]
                return redact_value(value, secrets)
            connection.send({"status": "succeeded", "result": safe(result),
                             "invalidations": list(context.invalidations), "timings": timings})
    except BaseException as error:
        connection.send({"status": "failed", "timings": timings, "error": {
            "code": "action_python_failed", "type": type(error).__name__,
            "message": redact_text(error, secrets)[:4096],
            "traceback": redact_text(
                traceback.format_exc().replace(snapshot_root, original_root)
                if snapshot_root else traceback.format_exc(), secrets
            )[-16384:],
            "writes_may_have_occurred": True,
        }})
    finally:
        connection.close()


def action_invocation_fingerprint(dashboard_id: str | None, action_id: str,
                                  payload: dict[str, Any], context: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        {"dashboard": dashboard_id, "action": action_id, "payload": payload, "context": context},
        sort_keys=True, ensure_ascii=False, allow_nan=False,
    ).encode()).hexdigest()


def execute_action(*, journal: ActionJournal, scope: str, request_id: str,
                   definition: ServerActionDefinition, definition_path: Path,
                   resources: ActionResources, payload: dict[str, Any],
                   invocation_context: dict[str, Any] | None = None,
                   dashboard_id: str | None = None,
                   dashboard_root: Path | None = None) -> dict[str, Any]:
    """Run once and return a durable receipt. This function does not refresh data.

    Callers own authorization, loaded-code validation, scheduling limits and the
    applied Run/revision fence. Repeating a receipt never repeats Python.
    """
    if not request_id or len(request_id) > 128:
        raise ValueError("Action request_id must contain 1–128 characters")
    payload = json_object(payload, label="Action payload")
    invocation_context = json_object(invocation_context or {}, label="Action invocation context")
    fingerprint = action_invocation_fingerprint(dashboard_id, definition.id, payload, invocation_context)
    existing = journal.lookup(scope, request_id, fingerprint)
    if existing is not None:
        return existing
    preparation_started = time.monotonic()
    # Resolve every declared resource before dispatch, even if Python would only
    # discover an absent resource after committing an earlier write.
    configs = {alias: resources.config(alias) for alias in definition.resources}
    secrets = tuple(sorted({secret for config in configs.values()
                            for secret in adapter_secret_values(config)}, key=len, reverse=True))
    code_path = (definition_path.parent / definition.code).resolve()
    if not code_path.is_file():
        raise ValueError("Action code file does not exist")
    root = (dashboard_root or definition_path.parent).resolve()
    code_files = {}
    digest = hashlib.sha256(definition.model_dump_json(by_alias=True).encode())
    for name in [definition.code, *definition.code_dependencies]:
        path = (definition_path.parent / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Action code dependency escapes Dashboard root")
        content = path.read_bytes()
        code_files[path.relative_to(root).as_posix()] = content
        digest.update(name.encode())
        digest.update(content)
    if invocation_context.get("action_signature", digest.hexdigest()) != digest.hexdigest():
        raise ValueError("Action code changed before dispatch; no write was started")
    receipt, claimed = journal.claim(scope, request_id, fingerprint,
                                     deadline=time.time() + definition.timeout_seconds + 30,
                                     invocation=invocation_context)
    if not claimed:
        return receipt
    runtime = multiprocessing.get_context("spawn")
    receiver, sender = runtime.Pipe(duplex=False)
    dispatched_at = time.monotonic()
    preparation_ms = (dispatched_at - preparation_started) * 1000
    process = runtime.Process(target=_execute, args=(sender, code_path.relative_to(root).as_posix(),
                              code_files, str(root), definition,
                              request_id, payload, configs, secrets, dispatched_at), daemon=True)
    started = False
    try:
        process.start()
        started = True
        sender.close()
        deadline = time.monotonic() + definition.timeout_seconds
        outcome = None
        while time.monotonic() < deadline:
            if receiver.poll(min(0.05, max(0, deadline - time.monotonic()))):
                try:
                    outcome = receiver.recv()
                except EOFError:
                    pass
                break
            if not process.is_alive():
                if receiver.poll(0):
                    continue
                break
        if outcome is None:
            outcome = {"status": "unknown", "error": {
                "code": "action_outcome_unknown",
                "message": "Action timed out or exited without a result; writes may have occurred.",
                "writes_may_have_occurred": True,
            }}
        outcome.setdefault("timings", {}).update({
            "preparation_ms": preparation_ms,
            "dispatch_to_outcome_ms": (time.monotonic() - dispatched_at) * 1000,
        })
        return journal.finish(scope, request_id, outcome, dashboard_id=dashboard_id)
    except Exception as error:
        return journal.finish(scope, request_id, {"status": "unknown" if started else "failed",
            "error": {"code": "action_worker_failed", "message": redact_text(error, secrets),
                      "writes_may_have_occurred": started}})
    finally:
        sender.close()
        receiver.close()
        if started:
            _terminate_process(process)
        process.close()
