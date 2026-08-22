from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dataviz.artifacts import ArtifactStore
from dataviz.execution.results import RunResult
from dataviz.rendering import CanvasRenderer
from dataviz.server.manager import RunManager
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.filters import compile_filter_contract


PACKAGE_ROOT = Path(__file__).resolve().parent


class RunRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    refresh: bool = False


def create_app(workspace_path: str | Path) -> FastAPI:
    workspace = load_workspace(workspace_path)
    manager = RunManager(workspace)
    renderer = CanvasRenderer(workspace)
    app = FastAPI(title=f"Dataviz · {workspace.definition.title}")
    app.state.workspace = workspace
    app.state.manager = manager
    app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")

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
        navigation = {item.id: item for item in workspace.definition.navigation}
        dashboards = []
        for dashboard_id, dashboard in workspace.dashboards.items():
            nav = navigation.get(dashboard_id)
            filter_contract = compile_filter_contract(dashboard.definition)
            filter_controls = {}
            for widget_id, effective in filter_contract.items():
                for item in effective:
                    control = filter_controls.setdefault(
                        item.key,
                        {
                            "key": item.key,
                            "id": item.id,
                            "origin": item.origin,
                            "owner_id": item.owner_id,
                            "definition": item.definition.model_dump(mode="json"),
                            "affected_views": [],
                        },
                    )
                    control["affected_views"].append(widget_id)
            dashboards.append(
                {
                    "id": dashboard_id,
                    "title": dashboard.definition.title,
                    "description": dashboard.definition.description,
                    "route": nav.route if nav else None,
                    "query_parameters": [item.model_dump(mode="json") for item in dashboard.definition.query_parameters],
                    "filters": list(filter_controls.values()),
                    "filter_contract": {
                        widget_id: [item.as_dict() for item in effective]
                        for widget_id, effective in filter_contract.items()
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
                    ]
                    + [
                        {
                            "id": f"widget:{widget_id}",
                            "local_id": widget_id,
                            "type": "widget",
                            "subtype": widget.output.type,
                            "title": widget.title,
                            "description": widget.description,
                        }
                        for widget_id, (_, widget) in dashboard.widgets.items()
                    ],
                }
            )
        return {
            "workspace": workspace.definition.model_dump(mode="json", by_alias=True),
            "dashboards": dashboards,
            "diagnostics": diagnostics,
        }

    @app.post("/api/dashboards/{dashboard_id}/runs")
    def start_run(dashboard_id: str, request: RunRequest):
        workspace.dashboard(dashboard_id)
        record = manager.start(dashboard_id, request.parameters, request.filters, request.refresh)
        return {"run_id": record.run_id, "status": record.status}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        record = manager.get(run_id)
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

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str):
        record = manager.get(run_id)
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
    def get_artifact(run_id: str, artifact_id: str):
        record = manager.get(run_id)
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

    def resolve_result(dashboard_id: str, run_id: str | None) -> RunResult | None:
        record = manager.get(run_id) if run_id else manager.latest_for(dashboard_id)
        return record.result if record and record.result else None

    @app.get("/api/dashboards/{dashboard_id}/canvas", response_class=HTMLResponse)
    def dashboard_canvas(dashboard_id: str, run_id: str | None = None):
        dashboard = workspace.dashboard(dashboard_id)
        result = resolve_result(dashboard_id, run_id)
        if not result:
            return HTMLResponse(
                "<html><body style='font-family:serif;padding:48px;background:#f3f0e7;color:#17211d'>"
                "<p style='font:12px monospace;color:#e2592a'>CANVAS WAITING</p>"
                f"<h1>{dashboard.definition.title}</h1><p>设置参数并运行后，结果将在这里出现。</p></body></html>"
            )
        return HTMLResponse(renderer.render(dashboard, result, asset_mode="server"))

    @app.get("/api/dashboards/{dashboard_id}/report")
    def download_report(dashboard_id: str, run_id: str | None = None):
        dashboard = workspace.dashboard(dashboard_id)
        result = resolve_result(dashboard_id, run_id)
        if not result:
            raise HTTPException(409, "Dashboard has no completed run")
        content = renderer.render(dashboard, result, asset_mode="inline")
        headers = {"Content-Disposition": f'attachment; filename="{dashboard_id}-{result.run_id}.html"'}
        return Response(content, media_type="text/html", headers=headers)

    return app
