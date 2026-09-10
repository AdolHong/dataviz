"""Server orchestration for explicit writes and independently retryable refresh."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Callable

from dataviz.actions import ActionResources, json_object
from dataviz.auth import AdapterResolver
from dataviz.errors import ExecutionFailure
from dataviz.execution.action_journal import ActionConflict, ActionJournal, action_journal_path
from dataviz.execution.action_process import action_invocation_fingerprint, execute_action
from dataviz.execution.fingerprint import ensure_query_run_compatible
from dataviz.execution.plan import compile_plan
from dataviz.redaction import redact_text
from dataviz.server.manager import RunManager
from dataviz.workspace.loader import LoadedWorkspace


class ActionBusy(ExecutionFailure):
    pass


def action_signature(dashboard, action_id: str) -> str:
    path, definition = dashboard.server_actions[action_id]
    digest = hashlib.sha256(definition.model_dump_json(by_alias=True).encode())
    for name in [definition.code, *definition.code_dependencies]:
        digest.update(name.encode())
        digest.update((path.parent / name).read_bytes())
    return digest.hexdigest()


class ActionService:
    def __init__(self, manager: RunManager, workspace_provider: Callable[[], LoadedWorkspace] | None = None):
        self.manager = manager
        self.workspace_provider = workspace_provider or manager.workspace_snapshot
        self.journal = ActionJournal(action_journal_path(manager.workspace.root))
        self.slots = threading.BoundedSemaphore(manager.workspace.definition.runtime.max_concurrent_runs)

    @staticmethod
    def scope(session_id: str, dashboard_id: str, action_id: str) -> str:
        return json.dumps([session_id, dashboard_id, action_id], separators=(",", ":"))

    def invoke(self, *, dashboard_id: str, action_id: str, session_id: str,
               run_id: str, request_id: str, payload: dict):
        payload = json_object(payload, label="Action payload")
        scope = self.scope(session_id, dashboard_id, action_id)
        existing = self.journal.get(scope, request_id)
        if existing is not None:
            context = existing["invocation"]
            if context.get("run_id") != run_id:
                raise ActionConflict("Action request ID belongs to a different applied Run")
            fingerprint = action_invocation_fingerprint(dashboard_id, action_id, payload, context)
            self.journal.lookup(scope, request_id, fingerprint)
            return self.refresh(dashboard_id, action_id, session_id, request_id)
        if not self.slots.acquire(blocking=False):
            raise ActionBusy("Server Action capacity is full; this request was not executed")
        try:
            workspace = self.workspace_provider()
            with self.manager.pin_action_run(run_id, session_id) as record:
                if record.dashboard_id != dashboard_id or record.result is None:
                    raise ExecutionFailure("Action requires an applied Query Run for this Dashboard")
                dashboard = workspace.dashboard(dashboard_id, record.page_id)
                if action_id not in dashboard.server_actions:
                    raise KeyError(action_id)
                definition_path, definition = dashboard.server_actions[action_id]
                if record.status not in {"ready", "partial"}:
                    raise ExecutionFailure("Action requires a completed Query Run")
                ensure_query_run_compatible(dashboard, record.result)
                latest = self.manager.latest_for(session_id, dashboard_id, record.page_id)
                if latest is None or latest.run_id != run_id:
                    raise ExecutionFailure("Action was submitted for a superseded Query Run")
                receipt = execute_action(
                    journal=self.journal, scope=scope, request_id=request_id, definition=definition,
                    definition_path=definition_path,
                    resources=ActionResources(AdapterResolver(workspace.root), definition.resources,
                                              dashboard.definition.adapters),
                    payload=payload, dashboard_id=dashboard_id,
                    dashboard_root=dashboard.root,
                    invocation_context={"run_id": run_id, "page_id": record.page_id,
                                        "action_signature": action_signature(dashboard, action_id)},
                )
                if receipt["status"] == "succeeded":
                    return self.refresh(dashboard_id, action_id, session_id, request_id)
                return receipt
        finally:
            self.slots.release()

    def refresh(self, dashboard_id: str, action_id: str, session_id: str,
                request_id: str, *, retry: bool = False):
        scope = self.scope(session_id, dashboard_id, action_id)
        receipt, claimed = self.journal.claim_refresh(scope, request_id, retry=retry)
        if not claimed:
            return self.poll(dashboard_id, action_id, session_id, request_id)
        claim = {"status": "scheduling", "started_at": receipt["refresh"]["started_at"]}
        scheduling_started = time.monotonic()
        base_run_id = receipt["invocation"]["run_id"]
        expected_run_id = receipt["refresh"].get("previous_run_id") or base_run_id
        resources = None
        try:
            workspace = self.workspace_provider()
            page_id = receipt["invocation"].get("page_id")
            dashboard = workspace.dashboard(dashboard_id, page_id)
            resources = AdapterResolver(workspace.root)
            if action_signature(dashboard, action_id) != receipt["invocation"]["action_signature"]:
                raise ExecutionFailure("Action definition changed; run the query again before refreshing")
            with self.manager.pin_action_run(base_run_id, session_id) as original:
                if original.result is None:
                    raise ExecutionFailure("Applied Query Run is no longer available")
                ensure_query_run_compatible(dashboard, original.result)
                latest = self.manager.latest_for(session_id, dashboard_id, page_id)
                if latest is None or latest.run_id != expected_run_id:
                    return self.journal.set_refresh(scope, request_id, {
                        "status": "superseded", "message": "A newer query is active; the write remains saved.",
                        "base_run_id": base_run_id,
                    }, expected=claim)
                plan = compile_plan(dashboard)
                sources = {reference for reference in receipt["invalidations"]
                           if reference.startswith("source:")}
                views = [reference.removeprefix("view:") for reference in receipt["invalidations"]
                         if reference.startswith("view:")]
                affected = sources & set(plan.nodes)
                while True:
                    expanded = affected | {name for name, node in plan.nodes.items()
                                           if node.dependencies & affected}
                    if expanded == affected:
                        break
                    affected = expanded
                if not affected:
                    return self.journal.set_refresh(scope, request_id, {
                        "status": "ready", "query_executed": False, "views": views,
                        "base_run_id": base_run_id, "run_id": base_run_id,
                        "timings": {"scheduling_ms": (time.monotonic() - scheduling_started) * 1000},
                    }, expected=claim)
                refreshed = self.manager.start(
                    dashboard_id, original.result.query_parameter_state, session_id,
                    _workspace=workspace, _reuse_run=original.result,
                    page_id=page_id,
                    _refresh_sources=sources, _expected_run_id=expected_run_id,
                )
                return self.journal.set_refresh(scope, request_id, {
                    "status": "running", "query_executed": True, "run_id": refreshed.run_id,
                    "base_run_id": base_run_id, "views": views, "affected_nodes": sorted(affected),
                    "timings": {"scheduling_ms": (time.monotonic() - scheduling_started) * 1000},
                }, expected=claim)
        except Exception as error:
            secrets = resources.all_redaction_values() if resources is not None else ()
            superseded = getattr(error, "details", {}).get("code") == "action_refresh_superseded"
            return self.journal.set_refresh(scope, request_id, {
                "status": "superseded" if superseded else "failed",
                "message": redact_text(error, secrets)[:4096],
                "base_run_id": base_run_id,
                "run_id": expected_run_id if expected_run_id != base_run_id else None,
            }, expected=claim)

    def poll(self, dashboard_id: str, action_id: str, session_id: str, request_id: str):
        scope = self.scope(session_id, dashboard_id, action_id)
        receipt = self.journal.get(scope, request_id)
        if receipt is None:
            raise KeyError(request_id)
        refresh = receipt["refresh"]
        if refresh["status"] == "scheduling" and time.time() - refresh["started_at"] > 30:
            return self.journal.set_refresh(scope, request_id, {
                "status": "failed", "message": "Refresh scheduling was interrupted; the write remains saved.",
            }, expected={"status": "scheduling", "started_at": refresh["started_at"]})
        if refresh["status"] != "running":
            return receipt
        record = self.manager.get(refresh["run_id"], session_id)
        if record is not None and record.status in {"queued", "loading"}:
            return receipt
        latest = self.manager.latest_for(session_id, dashboard_id, receipt["invocation"].get("page_id"))
        if latest is not None and latest.run_id != refresh["run_id"]:
            status = "superseded"
        elif record is None or record.result is None:
            status = "failed"
        else:
            status = "ready" if all(
                record.result.nodes[node].status in {"ready", "empty"}
                for node in refresh["affected_nodes"]
            ) and record.status in {"ready", "partial"} else "failed"
        timings = dict(refresh.get("timings", {}))
        if record is not None and record.result is not None:
            timings["nodes"] = {
                name: {"duration_ms": node.duration_ms, "status": node.status,
                       "result_origin": node.result_origin}
                for name, node in record.result.nodes.items()
            }
        return self.journal.set_refresh(scope, request_id, {
            **refresh, "status": status,
            "timings": timings,
            "message": "Refresh completed" if status == "ready" else "Write saved; refresh did not become current.",
        }, expected={"status": "running", "run_id": refresh["run_id"]})
