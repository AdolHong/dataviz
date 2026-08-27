from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.gzip import GZipMiddleware
from starlette.background import BackgroundTask

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.components import component_runtime_assets
from dataviz.content_templates import (
    interpolate_dashboard_content,
)
from dataviz.errors import DatavizError, WorkspaceError
from dataviz.execution.results import RunResult
from dataviz.execution.interactive import InteractionExecutor
from dataviz.execution.fingerprint import ensure_query_run_compatible
from dataviz.execution.outputs import normalize_outputs
from dataviz.execution.parameters import resolve_parameter_default
from dataviz.execution.references import parse_output_reference
from dataviz.rendering import CanvasRenderer
from dataviz.server.hot_reload import (
    WorkspaceChangeJournal,
    WorkspaceFileWatcher,
    WorkspaceSemanticSnapshot,
    classify_workspace_change,
)
from dataviz.server.manager import RunManager
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.selection_state import initial_selection_state
from dataviz.workspace.controls import (
    compile_control_contract,
    resolve_compute_values,
    resolve_selection_states,
)
from dataviz.workspace.control_components import resolve_control_component
from dataviz.workspace.navigation import NavigationEditor
from dataviz.workspace.models import PresentationControlPanelsDefinition


PACKAGE_ROOT = Path(__file__).resolve().parent


class ApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(ApiRequest):
    session_id: str = Field(min_length=8, max_length=128)
    query_parameters: dict[str, Any] = Field(default_factory=dict)
    refresh: bool = False


class InteractionRequest(ApiRequest):
    session_id: str = Field(min_length=8, max_length=128)
    transform_id: str
    generation: int = Field(ge=1)
    compute_parameters: dict[str, Any] = Field(default_factory=dict)
    selection_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    refresh: bool = False


class ReportRequest(ApiRequest):
    session_id: str = Field(min_length=8, max_length=128)
    run_id: str
    selection_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    compute_parameters: dict[str, Any] = Field(default_factory=dict)
    snapshot_outputs: dict[str, Any] = Field(default_factory=dict)


class FolderRequest(ApiRequest):
    title: str
    parent_id: str | None = None


class FolderRenameRequest(ApiRequest):
    title: str


class DashboardPlacementRequest(ApiRequest):
    parent_id: str | None = None


def create_app(workspace_path: str | Path, *, watch: bool = True) -> FastAPI:
    workspace = load_workspace(workspace_path)
    workspace_root = workspace.root
    manager = RunManager(workspace)
    navigation_editor = NavigationEditor(workspace_root)
    app = FastAPI(title=f"Dataviz · {workspace.definition.title}")
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)
    app.state.workspace = workspace
    app.state.manager = manager
    workspace_refresh_lock = threading.RLock()
    change_journal = WorkspaceChangeJournal()
    reload_semantics = WorkspaceSemanticSnapshot.from_workspace(workspace)
    allowed_reload_error_keys = {
        json.dumps(item.as_dict(), ensure_ascii=False, sort_keys=True, default=str)
        for item in validate_workspace(workspace)
        if item.level == "error"
    }
    app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")

    @app.middleware("http")
    async def disable_runtime_asset_cache(request: Request, call_next):
        response = await call_next(request)
        if (
            request.url.path == "/"
            or request.url.path.startswith("/static/")
            or request.url.path.startswith("/runtime/pyodide/")
            or request.url.path.endswith("/canvas")
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    def current_workspace():
        """Return one complete Workspace snapshot, never a partially refreshed object."""
        with workspace_refresh_lock:
            return workspace

    def refresh_workspace(*, preserve_on_error: bool = False):
        """Atomically publish a freshly loaded filesystem snapshot."""
        nonlocal workspace
        with workspace_refresh_lock:
            try:
                fresh = load_workspace(workspace_root)
            except WorkspaceError as error:
                if not preserve_on_error:
                    raise
                diagnostic = error.as_dict()
                latest = change_journal.latest
                latest_diagnostics = list(latest.diagnostics if latest else ())
                if (
                    latest is None
                    or latest.status != "invalid"
                    or latest_diagnostics != [diagnostic]
                ):
                    change_journal.publish(
                        status="invalid",
                        diagnostics=[diagnostic],
                        message=(
                            "Workspace update could not be loaded. "
                            "The previous Canvas remains active."
                        ),
                    )
                return workspace
            diagnostics = [item.as_dict() for item in validate_workspace(fresh)]
            error_diagnostics = [
                item for item in diagnostics if item.get("level") == "error"
            ]
            current_error_keys = {
                json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                for item in error_diagnostics
            }
            blocking_errors = current_error_keys - allowed_reload_error_keys
            if blocking_errors:
                if preserve_on_error:
                    latest = change_journal.latest
                    latest_diagnostics = {
                        json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                        for item in (latest.diagnostics if latest else ())
                    }
                    if latest is None or latest.status != "invalid" or latest_diagnostics != current_error_keys:
                        change_journal.publish(
                            status="invalid",
                            diagnostics=error_diagnostics,
                            message=(
                                "Workspace update has validation errors. "
                                "The previous Canvas remains active."
                            ),
                        )
                    return workspace
                # Execution endpoints may inspect/reject this complete candidate,
                # but it is not installed as the Server's current snapshot.
                return fresh
            workspace = fresh
            app.state.workspace = fresh
            manager.install_workspace_snapshot(fresh)
            return fresh

    def publish_workspace_change(changed_paths: set[str]) -> None:
        """Load, validate and atomically publish one debounced filesystem edit."""
        nonlocal workspace, reload_semantics
        with workspace_refresh_lock:
            try:
                fresh = load_workspace(workspace_root)
                diagnostics = [item.as_dict() for item in validate_workspace(fresh)]
                current_semantics = WorkspaceSemanticSnapshot.from_workspace(fresh)
            except WorkspaceError as error:
                change_journal.publish(
                    status="invalid",
                    changed_paths=changed_paths,
                    diagnostics=[error.as_dict()],
                    message=(
                        "Workspace update could not be loaded. "
                        "The previous Canvas remains active."
                    ),
                )
                return

            impacts, navigation_changed = classify_workspace_change(
                reload_semantics,
                current_semantics,
                changed_paths,
            )
            error_diagnostics = [
                item for item in diagnostics if item.get("level") == "error"
            ]
            current_error_keys = {
                json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                for item in error_diagnostics
            }
            blocking_errors = current_error_keys - allowed_reload_error_keys

            if blocking_errors:
                change_journal.publish(
                    status="invalid",
                    changes=impacts,
                    navigation_changed=navigation_changed,
                    changed_paths=changed_paths,
                    diagnostics=error_diagnostics,
                    message=(
                        "Workspace update has validation errors. "
                        "The current Canvas was not replaced."
                    ),
                )
                return

            # A complete snapshot is always published in one assignment. Active
            # Runs retain the immutable snapshot they captured at start.
            workspace = fresh
            app.state.workspace = fresh
            manager.install_workspace_snapshot(fresh)
            reload_semantics = current_semantics
            change_journal.publish(
                status="ready",
                changes=impacts,
                navigation_changed=navigation_changed,
                changed_paths=changed_paths,
                message="Workspace changes loaded.",
            )

    workspace_watcher = WorkspaceFileWatcher(workspace_root, publish_workspace_change)
    app.state.workspace_change_journal = change_journal
    app.state.workspace_watcher = workspace_watcher
    app.state.workspace_hot_reload_enabled = watch

    if watch:
        app.router.add_event_handler("startup", workspace_watcher.start)
        app.router.add_event_handler("shutdown", workspace_watcher.stop)

    def dashboard_from_disk(
        dashboard_id: str,
        *,
        preserve_on_error: bool = False,
    ):
        """Resolve the latest on-disk Dashboard definition for development."""
        snapshot = refresh_workspace(preserve_on_error=preserve_on_error)
        return snapshot, snapshot.dashboard(dashboard_id)

    def checked_session(value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value or ""):
            raise HTTPException(422, "Invalid or missing browser-tab session id")
        return value

    def find_node_artifact(
        nodes: dict[str, Any], artifact_id: str
    ) -> ArtifactDescriptor | None:
        """Resolve only Artifacts explicitly owned by the requested result."""
        for node in nodes.values():
            candidates = list(node.outputs.values())
            if node.log is not None:
                candidates.append(node.log)
            for artifact in candidates:
                if artifact.artifact_id == artifact_id:
                    return artifact
        return None

    def artifact_file_response(
        run_id: str, artifact: ArtifactDescriptor
    ) -> FileResponse:
        path = ArtifactStore(workspace_root, run_id).resolve(artifact)
        try:
            path.relative_to(workspace_root)
        except ValueError as error:
            raise HTTPException(404, "Artifact file not found") from error
        if not path.is_file():
            raise HTTPException(404, "Artifact file not found")
        return FileResponse(
            path,
            media_type=artifact.mime_type or "application/octet-stream",
            filename=path.name,
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (PACKAGE_ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    @app.get("/runtime/plotly.js")
    def plotly_runtime():
        from plotly.offline.offline import get_plotlyjs

        return Response(get_plotlyjs(), media_type="application/javascript")

    @app.get("/runtime/pyodide/{asset_path:path}")
    def pyodide_runtime_asset(asset_path: str):
        snapshot = current_workspace()
        configured = snapshot.definition.runtime.pyodide_bundle_path
        if not configured:
            raise HTTPException(404, "Workspace has no bundled Pyodide Runtime")
        root = (workspace_root / configured).resolve()
        if not root.is_relative_to(workspace_root):
            raise HTTPException(404, "Pyodide bundle is outside the Workspace")
        target = (root / asset_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise HTTPException(404, "Pyodide asset is outside the configured bundle") from error
        if not target.is_file():
            raise HTTPException(404, "Pyodide asset not found")
        return FileResponse(
            target,
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/runtime/components.css")
    def component_styles():
        return Response(
            component_runtime_assets()["style"],
            media_type="text/css",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runtime/components.js")
    def component_scripts():
        assets = component_runtime_assets()
        source = "\n".join(
            f"/* Component Package: {item['package']} · {item['kind']} */\n{item['source']}"
            for item in assets["scripts"]
        )
        return Response(
            source,
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runtime/web-component-adapter.js")
    def web_component_adapter():
        return Response(
            (PACKAGE_ROOT / "static" / "runtime-web-component-adapter.js").read_text(
                encoding="utf-8"
            ),
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/workspace")
    def workspace_summary():
        # Dashboard directory names are the navigation labels. Users and AI may
        # copy, rename or remove them without going through this server, so the
        # filesystem must be rescanned before publishing the tree.
        snapshot = refresh_workspace(preserve_on_error=True)
        diagnostics = [item.as_dict() for item in validate_workspace(snapshot)]
        dashboards = []
        for entry in snapshot.catalog:
            dashboard = entry.dashboard
            base = {
                "id": entry.id,
                "canvas_name": entry.canvas_name,
                "title": entry.title,
                "path": entry.relative_path,
                "status": entry.status,
                "runnable": entry.runnable,
                "discovered": entry.discovered,
                "message": entry.message,
                "parent_id": entry.parent_id,
                "logical_path": entry.logical_path,
            }
            if dashboard is None:
                dashboards.append(
                    {
                        **base,
                        "description": "",
                        "query_parameters": [],
                        "controls": [],
                        "control_contract": {},
                        "dependency_contract": None,
                        "nodes": [],
                        "views": [],
                    }
                )
                continue
            try:
                dependency_contract = dashboard.dependency_contract
            except DatavizError:
                # Invalid dashboards remain visible in Navigation; validate owns
                # the detailed diagnostic and the previous valid Canvas stays live.
                dependency_contract = None
            control_contract = (
                dependency_contract.view_control_contract
                if dependency_contract is not None
                else {
                    key: tuple(value)
                    for key, value in compile_control_contract(
                        dashboard.definition
                    ).items()
                }
            )
            section_titles = {item.id: item.title for item in dashboard.definition.sections}
            view_titles = {
                view_id: view.title or view_id
                for view_id, view in dashboard.views.items()
            }
            scoped_controls = {}
            for view_id, effective in control_contract.items():
                for item in effective:
                    dependency = (
                        dependency_contract.controls.get(item.key)
                        if dependency_contract is not None
                        else None
                    )
                    consumers = list(dependency.transform_consumers) if dependency else []
                    triggers = sorted(
                        {
                            dashboard.interactive_transforms[transform_id][1].trigger
                            for transform_id in consumers
                        }
                    )
                    control = scoped_controls.setdefault(
                        item.key,
                        {
                            "key": item.key,
                            "id": item.id,
                            "kind": item.kind,
                            "origin": item.origin,
                            "owner_id": item.owner_id,
                            "owner_title": (
                                dashboard.title
                                if item.origin == "dashboard"
                                else section_titles.get(item.owner_id, item.owner_id)
                                if item.origin == "section"
                                else view_titles.get(item.owner_id, item.owner_id)
                            ),
                            "definition": item.definition.model_dump(mode="json"),
                            "initial_state": (
                                initial_selection_state(
                                    item.definition,
                                    allow_unresolved_inferred=True,
                                ).as_dict()
                                if item.kind == "selection"
                                else None
                            ),
                            "presentation": _control_component_presentation(
                                dashboard, item.key, item.definition
                            ),
                            "consumers": consumers,
                            "trigger": triggers[0] if triggers else "manual",
                            "scope_views": (
                                list(dependency.scope_views) if dependency else []
                            ),
                            "direct_views": (
                                list(dependency.direct_views) if dependency else []
                            ),
                            "declared_direct_views": (
                                list(dependency.declared_direct_views) if dependency else []
                            ),
                            "runtime_checked_views": (
                                list(dependency.runtime_checked_views) if dependency else []
                            ),
                            "derived_views": (
                                list(dependency.derived_views) if dependency else []
                            ),
                            "affected_views": (
                                list(dependency.affected_views) if dependency else []
                            ),
                        },
                    )
                    if dependency is None:
                        control["scope_views"].append(view_id)
                        if item.kind == "selection":
                            control["direct_views"].append(view_id)
                            control["affected_views"].append(view_id)
            dashboards.append(
                {
                    **base,
                    "title": dashboard.title,
                    "subtitle": dashboard.definition.subtitle,
                    "description": dashboard.definition.description,
                    "presentation": {
                        "active": dashboard.presentation is not None,
                        "file": (
                            str(dashboard.presentation_path.relative_to(workspace_root))
                            if dashboard.presentation_path
                            else None
                        ),
                        "diagnostics": [
                            item.as_dict() for item in (dashboard.presentation_diagnostics or [])
                        ],
                        "control_panels": _control_panels_presentation(dashboard),
                    },
                    "query_parameters": [
                        {
                            **item.model_dump(mode="json"),
                            "resolved_default": resolve_parameter_default(
                                item,
                                timezone_name=snapshot.definition.context.timezone,
                            ),
                            "key": f"query:{item.id}",
                            "presentation": _control_component_presentation(
                                dashboard, f"query:{item.id}", item
                            ),
                        }
                        for item in dashboard.definition.query_parameters
                    ],
                    "controls": list(scoped_controls.values()),
                    "control_contract": {
                        view_id: [item.as_dict() for item in effective]
                        for view_id, effective in control_contract.items()
                    },
                    "dependency_contract": (
                        dependency_contract.as_dict()
                        if dependency_contract is not None
                        else None
                    ),
                    "layout_contract": dashboard.layout_contract.as_dict(),
                    "nodes": [
                        {
                            "id": f"source:{source_id}",
                            "local_id": source_id,
                            "type": "source",
                            "subtype": source.type,
                            "title": source.name or source_id,
                            "description": source.description,
                        }
                        for source_id, (_, source) in dashboard.sources.items()
                    ] + [
                        {
                            "id": f"dataset:{transform_id}",
                            "local_id": transform_id,
                            "type": "dataset_transform",
                            "subtype": transform.runtime,
                            "title": transform.name or transform_id,
                            "description": transform.description,
                        }
                        for transform_id, (_, transform) in dashboard.dataset_transforms.items()
                    ] + [
                        {
                            "id": f"interactive:{transform_id}",
                            "local_id": transform_id,
                            "type": "interactive_transform",
                            "subtype": transform.runtime,
                            "title": transform.name or transform_id,
                            "description": transform.description,
                            "trigger": transform.trigger,
                            "debounce_ms": transform.debounce_ms,
                            "query_inputs": {
                                alias: (
                                    {"parameter": binding}
                                    if isinstance(binding, str)
                                    else binding.model_dump(
                                        mode="json", exclude_none=True
                                    )
                                )
                                for alias, binding in transform.query_inputs.items()
                            },
                            "compute_inputs": dict(transform.compute_inputs),
                            "selection_inputs": dict(transform.selection_inputs),
                            "export": transform.export.model_dump(mode="json"),
                        }
                        for transform_id, (_, transform) in dashboard.interactive_transforms.items()
                    ],
                    "views": [
                        {
                            "id": view_id,
                            "local_id": view_id,
                            "type": "view",
                            "subtype": view.template,
                            "title": view.title or view_id,
                            "description": view.description,
                        }
                        for view_id, view in dashboard.views.items()
                    ],
                }
            )
        return {
            "workspace": snapshot.definition.model_dump(mode="json", by_alias=True),
            "folders": _folder_summary(snapshot.navigation),
            "trash": [item.model_dump(mode="json") for item in snapshot.trash],
            "dashboards": dashboards,
            "diagnostics": diagnostics,
            "hot_reload": {
                "enabled": watch,
                "revision": change_journal.revision,
                "last_event": (
                    change_journal.latest.as_dict()
                    if change_journal.latest is not None
                    else None
                ),
            },
        }

    @app.get("/api/workspace/events")
    async def workspace_events(
        request: Request,
        session_id: str,
        after: int = Query(0, ge=0),
    ):
        checked_session(session_id)
        try:
            last_event_id = int(request.headers.get("last-event-id", "0"))
        except ValueError:
            last_event_id = 0
        cursor = max(after, last_event_id)

        async def stream():
            nonlocal cursor
            keepalive_at = time.monotonic()
            while True:
                if await request.is_disconnected():
                    break
                events = change_journal.after(cursor)
                for event in events:
                    cursor = event.revision
                    payload = json.dumps(
                        event.as_dict(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    yield (
                        f"id: {event.revision}\n"
                        "event: workspace_changed\n"
                        f"data: {payload}\n\n"
                    )
                now = time.monotonic()
                if now - keepalive_at >= 10:
                    yield ": keepalive\n\n"
                    keepalive_at = now
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store",
                "X-Accel-Buffering": "no",
            },
        )

    def apply_navigation_change(action) -> dict[str, Any]:
        try:
            result = action()
            refresh_workspace()
            return {"status": "success", "result": result}
        except WorkspaceError as error:
            raise HTTPException(409, error.as_dict()) from error

    @app.post("/api/navigation/folders")
    def create_navigation_folder(request: FolderRequest):
        return apply_navigation_change(
            lambda: {"folder_id": navigation_editor.create_folder(request.title, request.parent_id)}
        )

    @app.patch("/api/navigation/folders/{folder_id}")
    def rename_navigation_folder(folder_id: str, request: FolderRenameRequest):
        return apply_navigation_change(lambda: navigation_editor.rename_folder(folder_id, request.title))

    @app.patch("/api/navigation/folders/{folder_id}/placement")
    def place_navigation_folder(folder_id: str, request: DashboardPlacementRequest):
        return apply_navigation_change(
            lambda: navigation_editor.place_folder(folder_id, request.parent_id)
        )

    @app.delete("/api/navigation/folders/{folder_id}")
    def delete_navigation_folder(folder_id: str):
        return apply_navigation_change(
            lambda: {"trash_id": navigation_editor.trash_folder(folder_id)}
        )

    @app.patch("/api/navigation/dashboards/{dashboard_id}")
    def place_navigation_dashboard(dashboard_id: str, request: DashboardPlacementRequest):
        try:
            entry = refresh_workspace().catalog_entry(dashboard_id)
        except WorkspaceError as error:
            raise HTTPException(404, error.message) from error
        return apply_navigation_change(lambda: navigation_editor.place_dashboard(entry, request.parent_id))

    @app.delete("/api/navigation/dashboards/{dashboard_id}")
    def trash_navigation_dashboard(dashboard_id: str):
        try:
            entry = refresh_workspace().catalog_entry(dashboard_id)
        except WorkspaceError as error:
            raise HTTPException(404, error.message) from error
        return apply_navigation_change(
            lambda: {"trash_id": navigation_editor.trash_dashboard(entry)}
        )

    @app.post("/api/navigation/trash/{trash_id}/restore")
    def restore_navigation_item(trash_id: str):
        return apply_navigation_change(lambda: navigation_editor.restore(trash_id))

    @app.post("/api/dashboards/{dashboard_id}/runs")
    def start_run(dashboard_id: str, request: RunRequest):
        # A user can save SQL and click Run before the polling loop reaches its
        # debounce boundary. Publish that filesystem generation first so the
        # returned revision describes the exact snapshot captured below.
        if watch:
            workspace_watcher.flush()
        try:
            snapshot, _ = dashboard_from_disk(dashboard_id)
        except WorkspaceError as error:
            raise HTTPException(409, error.message) from error
        try:
            record = manager.start(
                dashboard_id,
                request.query_parameters,
                session_id=checked_session(request.session_id),
                refresh=request.refresh,
                _workspace=snapshot,
            )
        except DatavizError as error:
            raise HTTPException(422, error.as_dict()) from error
        return {
            "run_id": record.run_id,
            "status": record.status,
            "workspace_revision": change_journal.revision,
        }

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, session_id: str):
        record = manager.get(run_id, checked_session(session_id))
        if not record:
            raise HTTPException(404, "Run not found")
        return {
            "run_id": run_id,
            "dashboard_id": record.dashboard_id,
            "status": record.status,
            "server_interactive_inputs": record.server_interactive_inputs,
            "snapshot": record.snapshot.model_dump(mode="json", by_alias=True) if record.snapshot else None,
            "result": record.result.model_dump(mode="json", by_alias=True) if record.result else None,
            "error": record.error,
            "event_offset": record.event_offset,
            "events": [event.model_dump(mode="json") for event in record.events],
        }

    @app.delete("/api/runs/{run_id}")
    def cancel_run(run_id: str, session_id: str):
        record = manager.cancel(run_id, checked_session(session_id))
        if not record:
            raise HTTPException(404, "Run not found")
        return {"run_id": run_id, "status": "cancelling" if record.status in {"queued", "loading"} else record.status}

    @app.get("/api/session/runs")
    def session_runs(session_id: str):
        records = manager.latest_for_session(checked_session(session_id))
        try:
            snapshot = refresh_workspace(preserve_on_error=True)
        except WorkspaceError:
            snapshot = current_workspace()
        payload = []
        for record in records:
            query_run = record.result or record.snapshot
            query_outdated = False
            if query_run is not None:
                try:
                    ensure_query_run_compatible(
                        snapshot.dashboard(record.dashboard_id),
                        query_run,
                    )
                except (DatavizError, WorkspaceError):
                    query_outdated = True
            payload.append(
                {
                    "run_id": record.run_id,
                    "dashboard_id": record.dashboard_id,
                    "status": record.status,
                    "server_interactive_inputs": record.server_interactive_inputs,
                    "query_parameters": (
                        record.snapshot.query_parameters
                        if record.snapshot
                        else record.requested_parameters
                    ),
                    "nodes": {
                        node_id: node.status
                        for node_id, node in (
                            record.snapshot.nodes.items() if record.snapshot else []
                        )
                    },
                    "ready": record.result is not None,
                    "query_outdated": query_outdated,
                }
            )
        return {"runs": payload}

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str, session_id: str):
        record = manager.get(run_id, checked_session(session_id))
        if not record:
            raise HTTPException(404, "Run not found")

        async def stream():
            cursor = 0
            while True:
                with record.condition:
                    offset = record.event_offset
                    events = list(record.events)
                    status = record.status
                if cursor < offset:
                    cursor = offset
                while cursor < offset + len(events):
                    event = events[cursor - offset]
                    cursor += 1
                    yield f"event: {event.event}\ndata: {event.model_dump_json()}\n\n"
                if status in {"ready", "partial", "error", "cancelled"} and cursor >= offset + len(events):
                    yield f"event: stream_end\ndata: {json.dumps({'status': status})}\n\n"
                    break
                yield ": keepalive\n\n"
                await asyncio.sleep(0.35)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/runs/{run_id}/interactions")
    def start_interaction(run_id: str, request: InteractionRequest):
        session_id = checked_session(request.session_id)
        snapshot = refresh_workspace()
        try:
            record = manager.start_interaction(
                run_id,
                session_id=session_id,
                target=request.transform_id,
                generation=request.generation,
                compute_parameters=request.compute_parameters,
                selection_state=request.selection_state,
                refresh=request.refresh,
                _workspace=snapshot,
            )
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        except DatavizError as error:
            payload = error.as_dict()
            status = 409 if payload["code"] == "interaction_generation_stale" else 422
            raise HTTPException(status, payload) from error
        except Exception as error:
            detail = error.as_dict() if hasattr(error, "as_dict") else str(error)
            raise HTTPException(422, detail) from error
        return {
            "interaction_id": record.interaction_id,
            "generation": record.generation,
            "status": record.status,
        }

    @app.get("/api/interactions/{interaction_id}")
    def get_interaction(interaction_id: str, session_id: str):
        record = manager.get_interaction(
            interaction_id, checked_session(session_id)
        )
        if not record:
            raise HTTPException(404, "Interaction not found")
        return {
            "interaction_id": interaction_id,
            "generation": record.generation,
            "run_id": record.run_id,
            "dashboard_id": record.dashboard_id,
            "target": record.target,
            "status": record.status,
            "result": (
                record.result.model_dump(mode="json", by_alias=True)
                if record.result
                else None
            ),
            "error": record.error,
            "event_offset": record.event_offset,
            "events": record.events,
        }

    @app.delete("/api/interactions/{interaction_id}")
    def cancel_interaction(interaction_id: str, session_id: str):
        record = manager.cancel_interaction(
            interaction_id, checked_session(session_id)
        )
        if not record:
            raise HTTPException(404, "Interaction not found")
        return {
            "interaction_id": interaction_id,
            "status": (
                "cancelling"
                if record.status in {"queued", "loading"}
                else record.status
            ),
        }

    @app.get("/api/interactions/{interaction_id}/artifacts/{artifact_id}")
    def get_interaction_artifact(
        interaction_id: str, artifact_id: str, session_id: str
    ):
        record = manager.get_interaction(
            interaction_id, checked_session(session_id)
        )
        if not record or not record.result:
            raise HTTPException(404, "Interaction result is not ready")
        artifact = find_node_artifact(record.result.nodes, artifact_id)
        if artifact is None:
            raise HTTPException(404, "Interaction Artifact not found")
        return artifact_file_response(record.run_id, artifact)

    @app.get("/api/interactions/{interaction_id}/outputs/{reference:path}")
    def get_interaction_output(
        interaction_id: str,
        reference: str,
        session_id: str,
        output_format: Literal["auto", "json", "arrow"] = Query("auto", alias="format"),
    ):
        record = manager.get_interaction(
            interaction_id, checked_session(session_id)
        )
        if not record or not record.result:
            raise HTTPException(404, "Interaction result is not ready")
        try:
            canonical = parse_output_reference(reference).canonical
        except Exception as error:
            raise HTTPException(422, str(error)) from error
        artifact = record.result.outputs.get(canonical)
        if artifact is None:
            raise HTTPException(404, "Interactive Output is not ready")
        store = ArtifactStore(workspace_root, record.run_id)
        runtime = current_workspace().definition.runtime
        if artifact.kind == "table":
            row_count = int(artifact.metadata.get("row_count", 0))
            if row_count > runtime.max_embedded_rows:
                raise HTTPException(
                    413,
                    f"Output has {row_count:,} rows; browser limit is "
                    f"{runtime.max_embedded_rows:,}",
                )
            use_arrow = output_format == "arrow" or (
                output_format == "auto"
                and runtime.browser_table_transport != "json"
                and (
                    runtime.browser_table_transport == "arrow"
                    or row_count >= runtime.arrow_min_rows
                )
            )
            if use_arrow and output_format == "arrow":
                arrow_value = store.read_arrow_ipc(artifact)
                if len(arrow_value) > runtime.max_embedded_bytes:
                    raise HTTPException(413, "Interactive Arrow Output exceeds the browser byte limit")
                return Response(
                    arrow_value,
                    media_type="application/vnd.apache.arrow.stream",
                    headers={
                        "X-Dataviz-Reference": canonical,
                        "X-Dataviz-Row-Count": str(row_count),
                        "Cache-Control": "private, no-store",
                    },
                )
            if use_arrow:
                encoded_reference = "/".join(
                    quote(part, safe="") for part in canonical.split("/")
                )
                return {
                    "reference": canonical,
                    "kind": artifact.kind,
                    "transport": {
                        "encoding": "arrow-ipc",
                        "compression": "http",
                        "url": (
                            f"/api/interactions/{interaction_id}/outputs/{encoded_reference}"
                            f"?session_id={session_id}&format=arrow"
                        ),
                        "row_count": row_count,
                        "schema": artifact.schema_ or [],
                        "content_hash": artifact.content_hash,
                    },
                    "artifact": artifact.model_dump(mode="json", by_alias=True),
                }
            value = store.read_value(artifact)
            value = json.loads(value.to_json(orient="records", date_format="iso"))
        else:
            value = store.read_value(artifact)
        if isinstance(value, Path):
            value = None
        encoded = json.dumps(
            value, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode()
        if len(encoded) > runtime.max_embedded_bytes:
            raise HTTPException(413, "Interactive Output exceeds the browser byte limit")
        return {
            "reference": canonical,
            "kind": artifact.kind,
            "value": value,
            "artifact": artifact.model_dump(mode="json", by_alias=True),
        }

    @app.get("/api/runs/{run_id}/artifacts/{artifact_id}")
    def get_artifact(run_id: str, artifact_id: str, session_id: str):
        record = manager.get(run_id, checked_session(session_id))
        snapshot = record.snapshot if record else None
        if not record or not snapshot:
            raise HTTPException(404, "Run result not found")
        artifact = find_node_artifact(snapshot.nodes, artifact_id)
        if artifact is None:
            raise HTTPException(404, "Artifact not found")
        return artifact_file_response(run_id, artifact)

    @app.get("/api/runs/{run_id}/outputs/{reference:path}")
    def get_output(
        run_id: str,
        reference: str,
        session_id: str,
        output_format: Literal["auto", "json", "arrow"] = Query("auto", alias="format"),
    ):
        record = manager.get(run_id, checked_session(session_id))
        snapshot = record.snapshot if record else None
        if not record or not snapshot:
            raise HTTPException(404, "Run snapshot not found")
        try:
            canonical = parse_output_reference(reference).canonical
        except Exception as error:
            raise HTTPException(422, str(error)) from error
        artifact = snapshot.outputs.get(canonical)
        if artifact is None:
            raise HTTPException(404, "Output is not ready")
        store = ArtifactStore(workspace_root, run_id)
        runtime = current_workspace().definition.runtime
        if artifact.kind == "table":
            row_count = int(artifact.metadata.get("row_count", 0))
            if row_count > runtime.max_embedded_rows:
                raise HTTPException(
                    413,
                    f"Output has {row_count:,} rows; browser limit is {runtime.max_embedded_rows:,}",
                )
            use_arrow = output_format == "arrow" or (
                output_format == "auto"
                and runtime.browser_table_transport != "json"
                and (
                    runtime.browser_table_transport == "arrow"
                    or row_count >= runtime.arrow_min_rows
                )
            )
            if use_arrow and output_format == "arrow":
                arrow_value = store.read_arrow_ipc(artifact)
                if len(arrow_value) > runtime.max_embedded_bytes:
                    raise HTTPException(
                        413,
                        f"Arrow Output is {len(arrow_value):,} bytes; browser limit is {runtime.max_embedded_bytes:,}",
                    )
                return Response(
                    arrow_value,
                    media_type="application/vnd.apache.arrow.stream",
                    headers={
                        "X-Dataviz-Reference": canonical,
                        "X-Dataviz-Row-Count": str(row_count),
                        "Cache-Control": "private, no-store",
                    },
                )
            if use_arrow:
                encoded_reference = "/".join(
                    quote(part, safe="")
                    for part in canonical.split("/")
                )
                return {
                    "reference": canonical,
                    "kind": artifact.kind,
                    "transport": {
                        "encoding": "arrow-ipc",
                        "compression": "http",
                        "url": (
                            f"/api/runs/{run_id}/outputs/{encoded_reference}"
                            f"?session_id={session_id}&format=arrow"
                        ),
                        "row_count": row_count,
                        "schema": artifact.schema_ or [],
                        "content_hash": artifact.content_hash,
                    },
                    "artifact": artifact.model_dump(mode="json", by_alias=True),
                }
            value = store.read_value(artifact)
            value = json.loads(value.to_json(orient="records", date_format="iso"))
        else:
            value = store.read_value(artifact)
        if isinstance(value, Path):
            value = None
        encoded = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
        if len(encoded) > runtime.max_embedded_bytes:
            raise HTTPException(
                413,
                f"Output is {len(encoded):,} bytes; browser limit is {runtime.max_embedded_bytes:,}",
            )
        return {
            "reference": canonical,
            "kind": artifact.kind,
            "value": value,
            "artifact": artifact.model_dump(mode="json", by_alias=True),
            "artifact_url": (
                f"/api/runs/{run_id}/artifacts/{artifact.artifact_id}?session_id={session_id}"
                if artifact.path
                else None
            ),
        }

    def resolve_result(
        dashboard_id: str, run_id: str | None, session_id: str
    ) -> RunResult | None:
        checked = checked_session(session_id)
        record = manager.get(run_id, checked) if run_id else manager.latest_for(checked, dashboard_id)
        if run_id and not record:
            raise HTTPException(404, "Run not found in this browser-tab session")
        if record and record.dashboard_id != dashboard_id:
            raise HTTPException(409, "Run belongs to another dashboard")
        return record.result if record and record.result else None

    @app.get("/api/dashboards/{dashboard_id}/canvas", response_class=HTMLResponse)
    def dashboard_canvas(
        dashboard_id: str,
        session_id: str,
        run_id: str | None = None,
        frame_id: str | None = None,
    ):
        try:
            snapshot, dashboard = dashboard_from_disk(
                dashboard_id,
                preserve_on_error=True,
            )
        except WorkspaceError:
            try:
                entry = current_workspace().catalog_entry(dashboard_id)
            except WorkspaceError as error:
                raise HTTPException(404, error.message) from error
            return HTMLResponse(
                _canvas_state_page(
                    label=entry.status.upper(),
                    title=entry.canvas_name,
                    message=entry.message or "Dashboard is unavailable",
                    detail=entry.relative_path,
                    note="其他看板仍可正常使用。修复该看板目录后刷新页面即可。",
                    tone="danger",
                    bridge=_canvas_interaction_bridge(dashboard_id, run_id, frame_id),
                )
            )
        checked = checked_session(session_id)
        record = manager.get(run_id, checked) if run_id else manager.latest_for(checked, dashboard_id)
        if run_id and not record:
            raise HTTPException(404, "Run not found in this browser-tab session")
        if record and record.dashboard_id != dashboard_id:
            raise HTTPException(409, "Run belongs to another dashboard")
        if record:
            with record.condition:
                result = record.snapshot
                query_snapshot_available = bool(record.snapshot or record.result)
                query_complete = record.result is not None
        else:
            result = None
            query_snapshot_available = False
            query_complete = False
        if not result and not record:
            try:
                waiting_content = interpolate_dashboard_content(
                    dashboard.definition,
                    {
                        item.id: resolve_parameter_default(
                            item,
                            timezone_name=snapshot.definition.context.timezone,
                        )
                        for item in dashboard.definition.query_parameters
                    },
                    fallback_title=dashboard.canvas_name,
                )
                waiting_title = waiting_content.title
            except ValueError:
                waiting_title = dashboard.canvas_name
            return HTMLResponse(
                _canvas_state_page(
                    label="Canvas waiting",
                    title=waiting_title,
                    message="设置参数并运行后，结果将在这里出现。",
                    tone="indigo",
                    bridge=_canvas_interaction_bridge(dashboard_id, run_id, frame_id),
                )
            )
        if result is None:
            result = RunResult(
                run_id=record.run_id,
                status="loading",
                workspace=snapshot.definition.id,
                dashboard=dashboard_id,
                query_scope=record.query_scope,
                query_targets=list(record.query_targets),
                query_nodes=list(record.query_nodes),
                query_contract_hash=record.query_contract_hash,
                query_parameters=record.requested_parameters,
            )
        live = None
        if record and not query_complete:
            live = {
                "run_id": record.run_id,
                "session_id": checked,
                "events_url": f"/api/runs/{record.run_id}/events?session_id={checked}",
                "outputs_url": f"/api/runs/{record.run_id}/outputs",
            }
        interaction = (
            {
                "run_id": record.run_id,
                "session_id": checked,
                "start_url": f"/api/runs/{record.run_id}/interactions",
                "status_url": "/api/interactions/{interaction_id}",
                "outputs_url": "/api/interactions/{interaction_id}/outputs",
                "query_snapshot_available": query_snapshot_available,
                "query_complete": query_complete,
            }
            if record
            else None
        )
        try:
            content = CanvasRenderer(snapshot).render(
                dashboard,
                result,
                asset_mode="server",
                live=live,
                interaction=interaction,
                session_id=checked,
                frame_id=frame_id,
            )
        except DatavizError as error:
            payload = error.as_dict()
            if payload.get("code") != "query_run_contract_changed":
                raise HTTPException(422, payload) from error
            return HTMLResponse(
                _canvas_contract_changed_page(
                    dashboard.canvas_name,
                    payload.get("message", str(error)),
                    dashboard_id,
                    run_id,
                    frame_id,
                ),
                status_code=409,
            )
        return HTMLResponse(content)

    @app.post("/api/dashboards/{dashboard_id}/report")
    def download_report(
        dashboard_id: str,
        request: ReportRequest,
    ):
        try:
            snapshot, dashboard = dashboard_from_disk(dashboard_id)
        except WorkspaceError as error:
            raise HTTPException(404, error.message) from error
        checked = checked_session(request.session_id)
        result = resolve_result(dashboard_id, request.run_id, checked)
        if not result:
            raise HTTPException(409, "Dashboard has no completed run")
        try:
            ensure_query_run_compatible(dashboard, result)
        except DatavizError as error:
            raise HTTPException(409, error.as_dict()) from error
        try:
            resolved_selection_state = resolve_selection_states(
                dashboard.definition, request.selection_state
            )
            resolved_compute = resolve_compute_values(
                dashboard.definition,
                request.compute_parameters,
            )
        except Exception as error:
            raise HTTPException(422, f"Invalid report state: {error}") from error
        derived_outputs = {}
        interactive_ids = dashboard.dependency_contract.reachable_interactive_order
        snapshot_interactions: set[str] = {
            transform_id
            for transform_id in interactive_ids
            if dashboard.interactive_transforms[transform_id][1].export.mode
            == "snapshot"
        }
        interaction_executor = InteractionExecutor(
            snapshot,
            cache=manager.executor_for(checked, workspace=snapshot).cache,
        )
        renderer = CanvasRenderer(snapshot)
        for transform_id in interactive_ids:
            transform = dashboard.interactive_transforms[transform_id][1]
            if transform.runtime != "server-python" or transform.export.mode != "snapshot":
                continue
            interaction_result = interaction_executor.execute(
                result,
                transform_id,
                compute_parameters=resolved_compute,
                selection_state=resolved_selection_state,
            )
            if interaction_result.status != "ready":
                raise HTTPException(
                    409,
                    {
                        "message": f"Snapshot computation failed: {transform_id}",
                        "result": interaction_result.model_dump(
                            mode="json", by_alias=True
                        ),
                    },
                )
            derived_outputs.update(interaction_result.outputs)

        browser_snapshot_ids = {
            transform_id
            for transform_id in snapshot_interactions
            if dashboard.interactive_transforms[transform_id][1].runtime
            in {"browser-js", "browser-python"}
        }
        allowed_snapshot_references = {
            f"interactive:{transform_id}/{name}"
            for transform_id in browser_snapshot_ids
            for name in dashboard.interactive_transforms[transform_id][1].outputs
        }
        unknown_snapshot_references = sorted(
            set(request.snapshot_outputs) - allowed_snapshot_references
        )
        if unknown_snapshot_references:
            raise HTTPException(
                422,
                {
                    "code": "snapshot_output_unknown",
                    "message": "Report contains undeclared browser snapshot Outputs",
                    "references": unknown_snapshot_references,
                },
            )
        encoded_snapshots = json.dumps(
            request.snapshot_outputs,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded_snapshots) > snapshot.definition.runtime.max_embedded_bytes:
            raise HTTPException(
                413,
                {
                    "code": "snapshot_payload_too_large",
                    "message": "Browser snapshot exceeds the configured report byte limit",
                    "bytes": len(encoded_snapshots),
                    "limit": snapshot.definition.runtime.max_embedded_bytes,
                },
            )
        snapshot_store = ArtifactStore(workspace_root, result.run_id)
        snapshot_nonce = uuid.uuid4().hex[:12]
        for transform_id in sorted(browser_snapshot_ids):
            definition = dashboard.interactive_transforms[transform_id][1]
            values = {
                name: request.snapshot_outputs[f"interactive:{transform_id}/{name}"]
                for name in definition.outputs
                if f"interactive:{transform_id}/{name}" in request.snapshot_outputs
            }
            missing = sorted(
                name
                for name, output in definition.outputs.items()
                if output.required and name not in values
            )
            if missing:
                raise HTTPException(
                    409,
                    {
                        "code": "snapshot_output_not_ready",
                        "message": (
                            f"Run the {transform_id} analysis before exporting this snapshot"
                        ),
                        "transform_id": transform_id,
                        "missing_outputs": missing,
                    },
                )
            try:
                outputs = normalize_outputs(
                    values,
                    store=snapshot_store,
                    node_id=(
                        f"interactive:{transform_id}__report_{snapshot_nonce}"
                    ),
                    declared=definition.outputs,
                    named=True,
                    metadata={
                        "title": definition.name or transform_id,
                        "origin": "browser_snapshot",
                    },
                )
            except Exception as error:
                detail = error.as_dict() if hasattr(error, "as_dict") else str(error)
                raise HTTPException(422, detail) from error
            for name, descriptor in outputs.items():
                if (
                    descriptor.kind == "table"
                    and int(descriptor.metadata.get("row_count", 0))
                    > snapshot.definition.runtime.max_embedded_rows
                ):
                    raise HTTPException(
                        413,
                        {
                            "code": "snapshot_rows_too_large",
                            "message": "Browser snapshot exceeds the configured report row limit",
                            "reference": f"interactive:{transform_id}/{name}",
                        },
                    )
                derived_outputs[f"interactive:{transform_id}/{name}"] = descriptor
        if renderer._browser_python_export_assets(dashboard) == "bundle":
            temporary = Path(tempfile.mkdtemp(prefix="dataviz-report-"))
            try:
                report_name = f"{dashboard_id}-{result.run_id}.html"
                renderer.write_report(
                    dashboard,
                    result,
                    temporary / report_name,
                    compute_parameters=resolved_compute,
                    selection_state=resolved_selection_state,
                    derived_outputs=derived_outputs,
                    snapshot_interactions=snapshot_interactions,
                )
                archive = temporary / f"{dashboard_id}-{result.run_id}.zip"
                with zipfile.ZipFile(
                    archive, "w", compression=zipfile.ZIP_DEFLATED
                ) as bundle:
                    for path in sorted(temporary.rglob("*")):
                        if path.is_file() and path != archive:
                            bundle.write(path, path.relative_to(temporary))
            except BaseException:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
            return FileResponse(
                archive,
                media_type="application/zip",
                filename=archive.name,
                background=BackgroundTask(shutil.rmtree, temporary, True),
            )
        content = renderer.render(
            dashboard,
            result,
            asset_mode="inline",
            compute_parameters=resolved_compute,
            selection_state=resolved_selection_state,
            derived_outputs=derived_outputs,
            snapshot_interactions=snapshot_interactions,
        )
        headers = {"Content-Disposition": f'attachment; filename="{dashboard_id}-{result.run_id}.html"'}
        return Response(content, media_type="text/html", headers=headers)

    return app


def _escape_html(value: str) -> str:
    import html

    return html.escape(value, quote=True)


def _canvas_interaction_bridge(
    dashboard_id: str,
    run_id: str | None,
    frame_id: str | None,
) -> str:
    identity = json.dumps(
        {
            "dashboard_id": dashboard_id,
            "run_id": run_id,
            "frame_id": frame_id,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return (
        "<script>const datavizFrameIdentity="
        f"{identity};"
        "['pointerdown','click'].forEach(type=>document.addEventListener(type,()=>"
        "parent.postMessage({type:'dataviz:canvas-interaction',...datavizFrameIdentity},"
        "location.origin),true))</script>"
    )


def _canvas_state_page(
    *,
    label: str,
    title: str,
    message: str,
    detail: str | None = None,
    note: str | None = None,
    tone: str = "indigo",
    bridge: str = "",
) -> str:
    palettes = {
        "indigo": ("#1a237e", "#283593", "#9fa8da", "#d9dcf3"),
        "warning": ("#5f4300", "#8a6200", "#ffe082", "#fff3c4"),
        "danger": ("#7f1d1d", "#a72c2c", "#ffcdd2", "#ffebee"),
    }
    start, end, label_color, copy_color = palettes.get(tone, palettes["indigo"])
    detail_markup = (
        "<code style='display:inline-block;margin-top:16px;padding:8px 10px;color:#202536;"
        "background:#fff;border:1px solid #d9e0ec;border-radius:6px;"
        "font:11px SFMono-Regular,Consolas,monospace'>"
        f"{_escape_html(detail)}</code>"
        if detail
        else ""
    )
    note_markup = (
        "<p style='max-width:64ch;margin:22px 0 0;color:#667085;font-size:13px;line-height:1.55'>"
        f"{_escape_html(note)}</p>"
        if note
        else ""
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
        "content='width=device-width,initial-scale=1'></head>"
        "<body style='margin:0;padding:clamp(24px,4vw,64px);color:#202536;background:#f5f7fa;"
        "font-family:-apple-system,BlinkMacSystemFont,&quot;Segoe UI&quot;,&quot;PingFang SC&quot;,sans-serif'>"
        "<main style='max-width:1180px;padding:clamp(26px,4vw,48px);color:#fff;"
        f"background:linear-gradient(135deg,{start},{end});border-radius:12px;"
        "box-shadow:0 10px 30px rgba(26,35,126,.16)'>"
        f"<p style='margin:0;color:{label_color};font:700 10px SFMono-Regular,Consolas,monospace;"
        f"letter-spacing:.12em;text-transform:uppercase'>{_escape_html(label)}</p>"
        "<h1 style='margin:12px 0 8px;font-size:clamp(34px,5vw,58px);line-height:1.02'>"
        f"{_escape_html(title)}</h1>"
        f"<p style='max-width:64ch;margin:0;color:{copy_color};font-size:16px;line-height:1.55'>"
        f"{_escape_html(message)}</p></main>{detail_markup}{note_markup}{bridge}</body></html>"
    )


def _canvas_contract_changed_page(
    canvas_name: str,
    message: str,
    dashboard_id: str,
    run_id: str | None,
    frame_id: str | None,
) -> str:
    return _canvas_state_page(
        label="QUERY RUN OUTDATED",
        title=canvas_name,
        message=message,
        note="看板的数据逻辑已改变。请点击 Run query 生成与当前定义一致的新数据。",
        tone="warning",
        bridge=_canvas_interaction_bridge(dashboard_id, run_id, frame_id),
    )


def _folder_summary(
    items, parent_id: str | None = None, parent_path: str = ""
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda value: value.order):
        if item.kind != "folder":
            continue
        logical_path = f"{parent_path}/{item.title}".strip("/")
        result.append(
            {
                "id": item.id,
                "title": item.title,
                "logical_path": logical_path,
                "parent_id": parent_id,
                "order": item.order,
            }
        )
        result.extend(_folder_summary(item.children, item.id, logical_path))
    return result


def _control_component_presentation(
    dashboard, key: str, definition
) -> dict[str, Any]:
    component = (
        dashboard.presentation.control_components.get(key)
        if dashboard.presentation
        else None
    )
    return resolve_control_component(definition, component)


def _control_panels_presentation(dashboard) -> dict[str, Any]:
    controls = (
        dashboard.presentation.control_panels
        if dashboard.presentation is not None
        else PresentationControlPanelsDefinition()
    )
    return controls.model_dump(mode="json")
