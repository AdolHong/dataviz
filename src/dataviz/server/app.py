from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dataviz.artifacts import ArtifactStore
from dataviz.errors import WorkspaceError
from dataviz.execution.results import RunResult
from dataviz.rendering import CanvasRenderer
from dataviz.server.manager import RunManager
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.selections import compile_selection_contract, resolve_selection_values
from dataviz.workspace.navigation import NavigationEditor


PACKAGE_ROOT = Path(__file__).resolve().parent


class RunRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)
    refresh: bool = False


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
    app.state.workspace = workspace
    app.state.manager = manager
    app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")

    def checked_session(value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value or ""):
            raise HTTPException(422, "Invalid or missing browser-tab session id")
        return value

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (PACKAGE_ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    @app.get("/runtime/plotly.js")
    def plotly_runtime():
        from plotly.offline.offline import get_plotlyjs

        return Response(get_plotlyjs(), media_type="application/javascript")

    @app.get("/api/workspace")
    def workspace_summary():
        diagnostics = [item.as_dict() for item in validate_workspace(workspace)]
        dashboards = []
        for entry in workspace.catalog:
            dashboard = entry.dashboard
            base = {
                "id": entry.id,
                "canvas_name": entry.canvas_name,
                "title": entry.title,
                "route": entry.navigation.route if entry.navigation else None,
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
                        "selections": [],
                        "selection_contract": {},
                        "nodes": [],
                        "views": [],
                    }
                )
                continue
            selection_contract = compile_selection_contract(dashboard.definition)
            section_titles = {item.id: item.title for item in dashboard.definition.sections}
            widget_titles = {widget_id: widget.title for widget_id, (_, widget) in dashboard.widgets.items()}
            selection_controls = {}
            for widget_id, effective in selection_contract.items():
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
                                else widget_titles.get(item.owner_id, item.owner_id)
                            ),
                            "definition": item.definition.model_dump(mode="json"),
                            "presentation": _selector_presentation(dashboard, item.key, item.definition),
                            "affected_views": [],
                        },
                    )
                    control["affected_views"].append(widget_id)
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
                    "selections": list(selection_controls.values()),
                    "selection_contract": {
                        widget_id: [item.as_dict() for item in effective]
                        for widget_id, effective in selection_contract.items()
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
                    ],
                    "views": [
                        {
                            "id": widget_id,
                            "local_id": widget_id,
                            "type": "view",
                            "subtype": "browser",
                            "title": widget.title,
                            "description": widget.description,
                        }
                        for widget_id, (_, widget) in dashboard.widgets.items()
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
            "folders": _folder_summary(workspace.definition.navigation),
            "trash": [item.model_dump(mode="json") for item in workspace.definition.trash],
            "dashboards": dashboards,
            "diagnostics": diagnostics,
        }

    def refresh_workspace() -> None:
        fresh = load_workspace(workspace.root)
        workspace.definition_path = fresh.definition_path
        workspace.definition = fresh.definition
        workspace.dashboards = fresh.dashboards
        workspace.catalog = fresh.catalog
        workspace.load_diagnostics = fresh.load_diagnostics
        workspace.readme = fresh.readme

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
            workspace.dashboard(dashboard_id)
        except WorkspaceError as error:
            raise HTTPException(409, error.message) from error
        record = manager.start(
            dashboard_id,
            request.parameters,
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
            "result": record.result.model_dump(mode="json", by_alias=True) if record.result else None,
            "error": record.error,
            "events": [event.model_dump(mode="json") for event in record.events],
        }

    @app.get("/api/session/runs")
    def session_runs(session_id: str):
        records = manager.latest_for_session(checked_session(session_id))
        return {
            "runs": [
                {
                    "run_id": record.run_id,
                    "dashboard_id": record.dashboard_id,
                    "status": record.status,
                    "parameters": record.result.parameters if record.result else None,
                    "selections": record.result.selections if record.result else None,
                    "nodes": {
                        node_id: node.status
                        for node_id, node in (record.result.nodes.items() if record.result else [])
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
                while cursor < len(record.events):
                    event = record.events[cursor]
                    cursor += 1
                    yield f"event: {event.event}\ndata: {event.model_dump_json()}\n\n"
                if record.status in {"success", "partial", "failed", "cancelled"} and cursor >= len(record.events):
                    yield f"event: stream_end\ndata: {json.dumps({'status': record.status})}\n\n"
                    break
                yield ": keepalive\n\n"
                await asyncio.sleep(0.35)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/runs/{run_id}/artifacts/{artifact_id}")
    def get_artifact(run_id: str, artifact_id: str, session_id: str):
        record = manager.get(run_id, checked_session(session_id))
        if not record or not record.result:
            raise HTTPException(404, "Run result not found")
        artifact = next(
            (
                item
                for node in record.result.nodes.values()
                for item in node.artifacts
                if item.artifact_id == artifact_id
            ),
            None,
        )
        if not artifact:
            raise HTTPException(404, "Artifact not found")
        path = ArtifactStore(workspace.root, run_id).resolve(artifact)
        if not path or not path.exists() or workspace.root not in path.parents:
            raise HTTPException(404, "Artifact file not found")
        return FileResponse(path, media_type=artifact.mime_type, filename=path.name)

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
            dashboard = workspace.dashboard(dashboard_id)
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
                "</body></html>"
            )
        result = resolve_result(dashboard_id, run_id, session_id)
        if not result:
            return HTMLResponse(
                "<html><body style='font-family:serif;padding:48px;background:#f3f0e7;color:#17211d'>"
                "<p style='font:12px monospace;color:#e2592a'>CANVAS WAITING</p>"
                f"<h1>{_escape_html(dashboard.title)}</h1><p>设置参数并运行后，结果将在这里出现。</p></body></html>"
            )
        return HTMLResponse(renderer.render(dashboard, result, asset_mode="server"))

    @app.get("/api/dashboards/{dashboard_id}/report")
    def download_report(
        dashboard_id: str,
        session_id: str,
        run_id: str | None = None,
        selection_values: str | None = Query(None, alias="selections"),
        legacy_filter_values: str | None = Query(None, alias="filters"),
    ):
        dashboard = workspace.dashboard(dashboard_id)
        result = resolve_result(dashboard_id, run_id, session_id)
        if not result:
            raise HTTPException(409, "Dashboard has no completed run")
        export_result = result
        supplied_values = selection_values or legacy_filter_values
        if supplied_values:
            try:
                supplied = json.loads(supplied_values)
                if not isinstance(supplied, dict):
                    raise ValueError("selections must be a JSON object")
                resolved, _ = resolve_selection_values(dashboard.definition, supplied)
            except (json.JSONDecodeError, ValueError, TypeError) as error:
                raise HTTPException(422, f"Invalid selections: {error}") from error
            except Exception as error:
                raise HTTPException(422, f"Invalid selections: {error}") from error
            export_result = result.model_copy(update={"selections": resolved})
        content = renderer.render(dashboard, export_result, asset_mode="inline")
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
    result = selector.model_dump(mode="json") if selector else {
        "template": "auto",
        "show_unavailable": False,
        "search_placeholder": "Search options…",
        "empty_text": "No matching options",
        "css_class": "",
    }
    if result["template"] == "auto":
        if definition.path_fields:
            result["template"] = "cascader"
            return result
        choice_count = len(definition.choices)
        if definition.type == "multi_select":
            result["template"] = "chips" if choice_count <= 8 else "searchable"
        elif definition.type == "single_select":
            result["template"] = "dropdown" if choice_count <= 20 else "searchable"
    return result
