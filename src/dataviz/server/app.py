from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware
from starlette.background import BackgroundTask

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.components import component_runtime_assets
from dataviz.content_templates import (
    default_parameter_values,
    interpolate_dashboard_content,
)
from dataviz.errors import DatavizError, WorkspaceError
from dataviz.execution.results import RunResult
from dataviz.execution.interactive import (
    InteractionExecutor,
    resolve_compute_parameters,
)
from dataviz.execution.outputs import normalize_outputs
from dataviz.execution.plan import reachable_output_references
from dataviz.execution.references import parse_output_reference
from dataviz.rendering import CanvasRenderer
from dataviz.server.manager import RunManager
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.selections import compile_selection_contract, resolve_selection_values
from dataviz.workspace.selector_templates import resolve_selector_presentation
from dataviz.workspace.navigation import NavigationEditor


PACKAGE_ROOT = Path(__file__).resolve().parent


class RunRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=128)
    query_parameters: dict[str, Any] = Field(default_factory=dict)
    refresh: bool = False


class InteractionRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=128)
    transform_id: str
    generation: int = Field(ge=1)
    compute_parameters: dict[str, Any] = Field(default_factory=dict)
    selections: dict[str, Any] = Field(default_factory=dict)
    refresh: bool = False


class ReportRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=128)
    run_id: str
    selections: dict[str, Any] = Field(default_factory=dict)
    compute_parameters: dict[str, Any] = Field(default_factory=dict)
    snapshot_outputs: dict[str, Any] = Field(default_factory=dict)


class FolderRequest(BaseModel):
    title: str
    parent_id: str | None = None


class FolderRenameRequest(BaseModel):
    title: str


class DashboardPlacementRequest(BaseModel):
    parent_id: str | None = None


def create_app(workspace_path: str | Path) -> FastAPI:
    workspace = load_workspace(workspace_path)
    manager = RunManager(workspace)
    renderer = CanvasRenderer(workspace)
    navigation_editor = NavigationEditor(workspace.root)
    app = FastAPI(title=f"Dataviz · {workspace.definition.title}")
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)
    app.state.workspace = workspace
    app.state.manager = manager
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

    def refresh_workspace() -> None:
        """Rebuild the in-memory catalog from the filesystem source of truth."""
        fresh = load_workspace(workspace.root)
        workspace.definition_path = fresh.definition_path
        workspace.definition = fresh.definition
        workspace.dashboards = fresh.dashboards
        workspace.catalog = fresh.catalog
        workspace.load_diagnostics = fresh.load_diagnostics
        workspace.navigation = fresh.navigation
        workspace.trash = fresh.trash
        workspace.readme = fresh.readme

    def dashboard_from_disk(dashboard_id: str):
        """Resolve a dashboard, rescanning after an external rename/delete."""
        try:
            dashboard = workspace.dashboard(dashboard_id)
        except WorkspaceError:
            refresh_workspace()
            return workspace.dashboard(dashboard_id)
        if dashboard.definition_path.is_file():
            return dashboard
        refresh_workspace()
        return workspace.dashboard(dashboard_id)

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
        path = ArtifactStore(workspace.root, run_id).resolve(artifact)
        if path is None:
            raise HTTPException(404, "Artifact file not found")
        try:
            path.relative_to(workspace.root.resolve())
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
        configured = workspace.definition.runtime.pyodide_bundle_path
        if not configured:
            raise HTTPException(404, "Workspace has no bundled Pyodide Runtime")
        root = (workspace.root / configured).resolve()
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
        refresh_workspace()
        diagnostics = [item.as_dict() for item in validate_workspace(workspace)]
        dashboards = []
        for entry in workspace.catalog:
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
                        "compute_parameters": [],
                        "selections": [],
                        "selection_contract": {},
                        "nodes": [],
                        "views": [],
                    }
                )
                continue
            selection_contract = compile_selection_contract(dashboard.definition)
            section_titles = {item.id: item.title for item in dashboard.definition.sections}
            view_titles = {
                view_id: view.title or view_id
                for view_id, view in dashboard.views.items()
            }
            selection_controls = {}
            for view_id, effective in selection_contract.items():
                for item in effective:
                    control = selection_controls.setdefault(
                        item.key,
                        {
                            "key": item.key,
                            "id": item.id,
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
                            "presentation": _selector_presentation(dashboard, item.key, item.definition),
                            "affected_views": [],
                        },
                    )
                    control["affected_views"].append(view_id)
            compute_controls = []
            for parameter in dashboard.definition.compute_parameters:
                consumers = [
                    transform_id
                    for transform_id, (_, transform) in dashboard.interactive_transforms.items()
                    if parameter.id in transform.compute_params
                ]
                triggers = sorted(
                    {
                        dashboard.interactive_transforms[transform_id][1].trigger
                        for transform_id in consumers
                    }
                )
                compute_controls.append(
                    {
                        **parameter.model_dump(mode="json"),
                        "consumers": consumers,
                        "trigger": triggers[0] if triggers else "manual",
                    }
                )
            dashboards.append(
                {
                    **base,
                    "title": dashboard.title,
                    "subtitle": dashboard.definition.subtitle,
                    "description": dashboard.definition.description,
                    "presentation": {
                        "active": dashboard.presentation is not None,
                        "file": (
                            str(dashboard.presentation_path.relative_to(workspace.root))
                            if dashboard.presentation_path
                            else None
                        ),
                        "diagnostics": [
                            item.as_dict() for item in (dashboard.presentation_diagnostics or [])
                        ],
                    },
                    "query_parameters": [item.model_dump(mode="json") for item in dashboard.definition.query_parameters],
                    "compute_parameters": compute_controls,
                    "selections": list(selection_controls.values()),
                    "selection_contract": {
                        view_id: [item.as_dict() for item in effective]
                        for view_id, effective in selection_contract.items()
                    },
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
                            "query_params": list(transform.query_params),
                            "compute_params": list(transform.compute_params),
                            "selections": list(transform.selections),
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
            "workspace": workspace.definition.model_dump(mode="json", by_alias=True),
            "capabilities": {
                "navigation_management": True,
                "physical_navigation": True,
                "dashboard_path_separator": "##",
            },
            "folders": _folder_summary(workspace.navigation),
            "trash": [item.model_dump(mode="json") for item in workspace.trash],
            "dashboards": dashboards,
            "diagnostics": diagnostics,
        }

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
            entry = workspace.catalog_entry(dashboard_id)
        except WorkspaceError as error:
            raise HTTPException(404, error.message) from error
        return apply_navigation_change(lambda: navigation_editor.place_dashboard(entry, request.parent_id))

    @app.delete("/api/navigation/dashboards/{dashboard_id}")
    def trash_navigation_dashboard(dashboard_id: str):
        try:
            entry = workspace.catalog_entry(dashboard_id)
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
        try:
            dashboard_from_disk(dashboard_id)
        except WorkspaceError as error:
            raise HTTPException(409, error.message) from error
        record = manager.start(
            dashboard_id,
            request.query_parameters,
            session_id=checked_session(request.session_id),
            refresh=request.refresh,
        )
        return {"run_id": record.run_id, "status": record.status}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, session_id: str):
        record = manager.get(run_id, checked_session(session_id))
        if not record:
            raise HTTPException(404, "Run not found")
        return {
            "run_id": run_id,
            "dashboard_id": record.dashboard_id,
            "status": record.status,
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
        return {
            "runs": [
                {
                    "run_id": record.run_id,
                    "dashboard_id": record.dashboard_id,
                    "status": record.status,
                    "query_parameters": (
                        record.snapshot.query_parameters
                        if record.snapshot
                        else record.requested_parameters
                    ),
                    "nodes": {
                        node_id: node.status
                        for node_id, node in (record.snapshot.nodes.items() if record.snapshot else [])
                    },
                    "ready": record.result is not None,
                }
                for record in records
            ]
        }

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
        try:
            record = manager.start_interaction(
                run_id,
                session_id=session_id,
                target=request.transform_id,
                generation=request.generation,
                compute_parameters=request.compute_parameters,
                selections=request.selections,
                refresh=request.refresh,
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
        record = manager.get_interaction(
            interaction_id, checked_session(session_id)
        )
        if not record:
            raise HTTPException(404, "Interaction not found")
        record.cancel_event.set()
        return {"interaction_id": interaction_id, "status": "cancelled"}

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
        store = ArtifactStore(workspace.root, record.run_id)
        runtime = workspace.definition.runtime
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
        store = ArtifactStore(workspace.root, run_id)
        runtime = workspace.definition.runtime
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
    def dashboard_canvas(dashboard_id: str, session_id: str, run_id: str | None = None):
        try:
            dashboard = dashboard_from_disk(dashboard_id)
        except WorkspaceError:
            try:
                entry = workspace.catalog_entry(dashboard_id)
            except WorkspaceError as error:
                raise HTTPException(404, error.message) from error
            title = _escape_html(entry.canvas_name)
            message = _escape_html(entry.message or "Dashboard is unavailable")
            path = _escape_html(entry.relative_path)
            return HTMLResponse(
                "<html><body style='font-family:system-ui;padding:56px;background:#f3f0e7;color:#17211d'>"
                f"<p style='font:12px monospace;color:#d95f35'>{entry.status.upper()}</p>"
                f"<h1>{title}</h1><p>{message}</p><code>{path}</code>"
                "<p style='margin-top:28px;color:#68716c'>其他看板仍可正常使用。修复该看板目录后刷新页面即可。</p>"
                "<script>['pointerdown','click'].forEach(type=>document.addEventListener(type,()=>parent.postMessage({type:'dataviz:canvas-interaction'},location.origin),true))</script>"
                "</body></html>"
            )
        checked = checked_session(session_id)
        record = manager.get(run_id, checked) if run_id else manager.latest_for(checked, dashboard_id)
        if run_id and not record:
            raise HTTPException(404, "Run not found in this browser-tab session")
        if record and record.dashboard_id != dashboard_id:
            raise HTTPException(409, "Run belongs to another dashboard")
        result = record.snapshot if record else None
        if not result and not record:
            try:
                waiting_content = interpolate_dashboard_content(
                    dashboard.definition,
                    default_parameter_values(dashboard.definition),
                    fallback_title=dashboard.canvas_name,
                )
                waiting_title = waiting_content.title
            except ValueError:
                waiting_title = dashboard.canvas_name
            return HTMLResponse(
                "<html><body style='font-family:serif;padding:48px;background:#f3f0e7;color:#17211d'>"
                "<p style='font:12px monospace;color:#e2592a'>CANVAS WAITING</p>"
                f"<h1>{_escape_html(waiting_title)}</h1><p>设置参数并运行后，结果将在这里出现。</p>"
                "<script>['pointerdown','click'].forEach(type=>document.addEventListener(type,()=>parent.postMessage({type:'dataviz:canvas-interaction'},location.origin),true))</script>"
                "</body></html>"
            )
        if result is None:
            result = RunResult(
                run_id=record.run_id,
                status="loading",
                workspace=workspace.definition.id,
                dashboard=dashboard_id,
                query_parameters=record.requested_parameters,
            )
        live = None
        if record and record.result is None:
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
            }
            if record and record.result is not None
            else None
        )
        return HTMLResponse(
            renderer.render(
                dashboard,
                result,
                asset_mode="server",
                live=live,
                interaction=interaction,
                session_id=checked,
            )
        )

    @app.post("/api/dashboards/{dashboard_id}/report")
    def download_report(
        dashboard_id: str,
        request: ReportRequest,
    ):
        try:
            dashboard = dashboard_from_disk(dashboard_id)
        except WorkspaceError as error:
            raise HTTPException(404, error.message) from error
        checked = checked_session(request.session_id)
        result = resolve_result(dashboard_id, request.run_id, checked)
        if not result:
            raise HTTPException(409, "Dashboard has no completed run")
        try:
            resolved_selections, _ = resolve_selection_values(
                dashboard.definition, request.selections
            )
            resolved_compute = resolve_compute_parameters(
                dashboard, request.compute_parameters
            )
        except Exception as error:
            raise HTTPException(422, f"Invalid report state: {error}") from error

        derived_outputs = {}
        _, interactive_ids = reachable_output_references(dashboard)
        snapshot_interactions: set[str] = {
            transform_id
            for transform_id in interactive_ids
            if dashboard.interactive_transforms[transform_id][1].export.mode
            == "snapshot"
        }
        interaction_executor = InteractionExecutor(
            workspace,
            cache=manager.executor_for(checked).cache,
        )
        for transform_id in interactive_ids:
            transform = dashboard.interactive_transforms[transform_id][1]
            if transform.runtime != "server-python" or transform.export.mode != "snapshot":
                continue
            interaction_result = interaction_executor.execute(
                result,
                transform_id,
                compute_parameters=resolved_compute,
                selections=resolved_selections,
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
        if len(encoded_snapshots) > workspace.definition.runtime.max_embedded_bytes:
            raise HTTPException(
                413,
                {
                    "code": "snapshot_payload_too_large",
                    "message": "Browser snapshot exceeds the configured report byte limit",
                    "bytes": len(encoded_snapshots),
                    "limit": workspace.definition.runtime.max_embedded_bytes,
                },
            )
        snapshot_store = ArtifactStore(workspace.root, result.run_id)
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
                    > workspace.definition.runtime.max_embedded_rows
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
            report_name = f"{dashboard_id}-{result.run_id}.html"
            report_path = renderer.write_report(
                dashboard,
                result,
                temporary / report_name,
                compute_parameters=resolved_compute,
                selections=resolved_selections,
                derived_outputs=derived_outputs,
                snapshot_interactions=snapshot_interactions,
            )
            archive = temporary / f"{dashboard_id}-{result.run_id}.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(temporary.rglob("*")):
                    if path.is_file() and path != archive:
                        bundle.write(path, path.relative_to(temporary))
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
            selections=resolved_selections,
            derived_outputs=derived_outputs,
            snapshot_interactions=snapshot_interactions,
        )
        headers = {"Content-Disposition": f'attachment; filename="{dashboard_id}-{result.run_id}.html"'}
        return Response(content, media_type="text/html", headers=headers)

    return app


def _escape_html(value: str) -> str:
    import html

    return html.escape(value, quote=True)


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


def _selector_presentation(dashboard, key: str, definition) -> dict[str, Any]:
    selector = dashboard.presentation.selectors.get(key) if dashboard.presentation else None
    return resolve_selector_presentation(definition, selector)
