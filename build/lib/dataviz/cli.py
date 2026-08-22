from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import typer

from dataviz.errors import DatavizError
from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer
from dataviz.server import create_app
from dataviz.workspace import compile_filter_contract, load_workspace, validate_workspace


app = typer.Typer(
    name="dataviz",
    help="Workspace-first data dashboards for humans and AI.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def parse_params(values: list[str] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values or []:
        if "=" not in value:
            raise typer.BadParameter(f"Parameter must use name=value: {value}")
        name, raw = value.split("=", 1)
        try:
            result[name] = json.loads(raw)
        except json.JSONDecodeError:
            result[name] = raw
    return result


def print_json(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def handle_error(exc: Exception) -> None:
    error = exc.as_dict() if isinstance(exc, DatavizError) else {
        "type": type(exc).__name__, "message": str(exc)
    }
    print_json({"status": "error", "error": error})
    raise typer.Exit(1)


@app.command()
def init(path: Path = typer.Argument(..., help="New workspace directory")) -> None:
    """Create a minimal Git-friendly workspace."""
    if path.exists() and any(path.iterdir()):
        raise typer.BadParameter(f"Directory is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    (path / "dashboards" / "hello" / "data").mkdir(parents=True, exist_ok=True)
    (path / "dashboards" / "hello" / "sources").mkdir(parents=True, exist_ok=True)
    (path / "dashboards" / "hello" / "widgets" / "summary").mkdir(parents=True, exist_ok=True)
    files = {
        "workspace.yaml": """schema: dataviz/workspace/v1
kind: workspace
id: my-analysis
title: My Analysis
description: A workspace-first dashboard project
navigation:
  - id: hello
    title: Hello dashboard
    dashboard: dashboards/hello
    route: /hello
    order: 10
""",
        ".gitignore": "auth/connections.local.yaml\n.dataviz/\ndist/\n",
        "README.md": "# My Analysis\n\nRun with `dataviz serve .`.\n",
        "dashboards/hello/dashboard.yaml": """schema: dataviz/dashboard/v1
kind: dashboard
id: hello
title: Hello dashboard
description: A minimal self-contained canvas
query_parameters: []
dashboard_filters: []
sections:
  - id: overview
    title: Overview
    views: [summary]
sources:
  - sources/data.yaml
widgets:
  - widgets/summary/widget.yaml
layout:
  columns: 12
  items:
    - widget: summary
      x: 0
      y: 0
      width: 12
      height: 4
""",
        "dashboards/hello/data/sample.csv": "category,value\nA,12\nB,19\nC,8\n",
        "dashboards/hello/sources/data.yaml": """schema: dataviz/source/v1
kind: datasource
id: data
name: Sample data
type: file
path: ../data/sample.csv
format: csv
cache:
  mode: persistent
""",
        "dashboards/hello/widgets/summary/widget.yaml": """schema: dataviz/widget/v1
kind: widget
id: summary
title: Sample values
code: main.py
depends_on: [data]
output:
  type: plotly
""",
        "dashboards/hello/widgets/summary/main.py": """import plotly.express as px

def render(context):
    return px.bar(context.table("data"), x="category", y="value", color="category")
""",
    }
    for relative, content in files.items():
        destination = path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    print_json({"status": "success", "workspace": str(path.resolve())})


@app.command("list")
def list_dashboards(workspace: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """List dashboards and execution nodes."""
    try:
        loaded = load_workspace(workspace)
        print_json(
            {
                "workspace": loaded.definition.model_dump(mode="json", by_alias=True),
                "dashboards": [
                    {
                        "id": dashboard.definition.id,
                        "title": dashboard.definition.title,
                        "path": str(dashboard.root.relative_to(loaded.root)),
                        "sources": list(dashboard.sources),
                        "widgets": list(dashboard.widgets),
                    }
                    for dashboard in loaded.dashboards.values()
                ],
            }
        )
    except Exception as exc:
        handle_error(exc)


@app.command()
def validate(workspace: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Validate YAML schemas, references, code files and canvas assets."""
    try:
        loaded = load_workspace(workspace)
        diagnostics = validate_workspace(loaded)
        print_json(
            {
                "status": "valid" if not any(item.level == "error" for item in diagnostics) else "invalid",
                "diagnostics": [item.as_dict() for item in diagnostics],
            }
        )
        if any(item.level == "error" for item in diagnostics):
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command()
def context(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    output_format: str = typer.Option("markdown", "--format"),
) -> None:
    """Emit an AI-friendly dashboard context bundle."""
    try:
        loaded = load_workspace(workspace)
        item = loaded.dashboard(dashboard)
        payload = {
            "workspace": loaded.definition.model_dump(mode="json", by_alias=True),
            "workspace_readme": loaded.readme,
            "dashboard": item.definition.model_dump(mode="json", by_alias=True),
            "dashboard_readme": item.readme,
            "effective_filters": {
                widget_id: [value.as_dict() for value in values]
                for widget_id, values in compile_filter_contract(item.definition).items()
            },
            "sources": {
                key: {
                    "definition": definition.model_dump(mode="json", by_alias=True),
                    "file": str(path.relative_to(loaded.root)),
                    "code": _code_content(path, definition.code or definition.path),
                }
                for key, (path, definition) in item.sources.items()
            },
            "widgets": {
                key: {
                    "definition": definition.model_dump(mode="json", by_alias=True),
                    "file": str(path.relative_to(loaded.root)),
                    "code": _code_content(path, definition.code),
                }
                for key, (path, definition) in item.widgets.items()
            },
        }
        if output_format == "json":
            print_json(payload)
        else:
            typer.echo(f"# {item.definition.title}\n\n{item.readme}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n")
    except Exception as exc:
        handle_error(exc)


def _code_content(definition_path: Path, relative: str | None) -> str | None:
    if not relative:
        return None
    path = (definition_path.parent / relative).resolve()
    if not path.exists() or path.is_dir():
        return None
    if path.stat().st_size > 500_000:
        return f"<omitted: {path.stat().st_size} bytes>"
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "<binary file>"


@app.command()
def query(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    source: str = typer.Option(..., "--source"),
    param: list[str] | None = typer.Option(None, "--param"),
    output_format: str = typer.Option("json", "--format"),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Query a File, SQL or Python source without starting a server."""
    try:
        loaded = load_workspace(workspace)
        result = Executor(loaded).run(
            dashboard, params=parse_params(param), source_targets=[source], refresh=refresh
        )
        node = result.nodes[f"source:{source}"]
        artifact = next((item for item in node.artifacts if item.kind == "table"), None)
        if not artifact:
            print_json(result)
            raise typer.Exit(1)
        if output_format == "json":
            print_json(
                {
                    "status": result.status,
                    "run_id": result.run_id,
                    "source": source,
                    "parameters": result.parameters,
                    "schema": artifact.schema_,
                    "row_count": artifact.metadata.get("row_count"),
                    "preview": artifact.preview,
                    "artifact": artifact.model_dump(mode="json", by_alias=True),
                    "node": node.model_dump(mode="json", by_alias=True),
                }
            )
        else:
            frame = pd.DataFrame(artifact.preview or [])
            if output_format == "csv":
                typer.echo(frame.to_csv(index=False), nl=False)
            elif output_format == "markdown":
                typer.echo(frame.to_markdown(index=False))
            else:
                typer.echo(frame.to_string(index=False))
        if result.status == "failed":
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command()
def run(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    widget: list[str] | None = typer.Option(None, "--widget"),
    param: list[str] | None = typer.Option(None, "--param"),
    filter_value: list[str] | None = typer.Option(None, "--filter"),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Execute widgets or a complete dashboard."""
    try:
        loaded = load_workspace(workspace)
        result = Executor(loaded).run(
            dashboard,
            params=parse_params(param),
            filters=parse_params(filter_value),
            widget_targets=widget,
            refresh=refresh,
        )
        print_json(result)
        if result.status == "failed":
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command()
def report(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    output: Path = typer.Option(..., "--output"),
    param: list[str] | None = typer.Option(None, "--param"),
    filter_value: list[str] | None = typer.Option(None, "--filter"),
    chart_mode: str = typer.Option("interactive", "--chart-mode"),
    image_format: str = typer.Option("svg", "--image-format"),
    refresh: bool = typer.Option(False, "--refresh"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
) -> None:
    """Execute a dashboard and write a shareable HTML report."""
    try:
        loaded = load_workspace(workspace)
        result = Executor(loaded).run(
            dashboard,
            params=parse_params(param),
            filters=parse_params(filter_value),
            refresh=refresh,
        )
        if result.status != "success" and not (allow_partial and result.status == "partial"):
            print_json(result)
            raise typer.Exit(1)
        path = CanvasRenderer(loaded).write_report(
            loaded.dashboard(dashboard), result, output.resolve(), chart_mode=chart_mode, image_format=image_format
        )
        print_json(
            {
                "status": "success",
                "run_id": result.run_id,
                "report": str(path),
                "manifest": str(path.with_suffix(path.suffix + ".manifest.json")),
                "parameters": result.parameters,
                "filters": result.filters,
                "warnings": result.warnings,
            }
        )
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command()
def serve(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the human-facing interactive dashboard server."""
    import uvicorn

    application = create_app(workspace)
    uvicorn.run(application, host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
