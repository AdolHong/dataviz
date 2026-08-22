from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import typer
import yaml

from dataviz.errors import DatavizError
from dataviz.documentation import DOC_TOPICS, docs_catalog, resolve_doc_topic
from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer, template_catalog
from dataviz.server import create_app
from dataviz.templates import component_catalog
from dataviz.workspace import compile_selection_contract, load_workspace, validate_workspace


app = typer.Typer(
    name="dataviz",
    help="Workspace-first data dashboards for humans and AI.",
    epilog="AI start here: dataviz docs quickstart",
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
    print_json({
        "status": "error",
        "error": error,
        "help": {
            "command": "dataviz docs troubleshooting",
            "workflow": "dataviz docs workflow",
        },
    })
    raise typer.Exit(1)


@app.command()
def init(path: Path = typer.Argument(..., help="New workspace directory")) -> None:
    """Create a minimal Git-friendly workspace."""
    if path.exists() and any(path.iterdir()):
        raise typer.BadParameter(f"Directory is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    (path / "dashboards" / "hello" / "data").mkdir(parents=True, exist_ok=True)
    files = {
        "workspace.yaml": """schema: dataviz/workspace/v1
kind: workspace
id: my-analysis
title: My Analysis
description: A workspace-first dashboard project
folders: []
""",
        ".gitignore": "auth/adapters.local.yaml\nauth/connections.local.yaml\nadapters.local.yaml\n.dataviz/\ndist/\n",
        "README.md": "# My Analysis\n\nRun with `dataviz serve .`.\n",
        "dashboards/hello/dashboard.yaml": """schema: dataviz/dashboard/v1
kind: dashboard
id: hello
title: Hello dashboard
description: A minimal self-contained canvas
dashboard_selections:
  - id: category
    type: multi_select
    default: [A, B, C]
    choices:
      - {label: A, value: A}
      - {label: B, value: B}
      - {label: C, value: C}
sources:
  - id: data
    name: Sample data
    type: file
    path: data/sample.csv
    format: csv
views:
  - id: summary
    title: Sample values
    source: data
    template: bar
    x: category
    y: value
    aggregate: sum
sections:
  - id: overview
    title: Overview
    template: single
    views: [summary]
layout:
  template: overview
theme:
  preset: plain
""",
        "dashboards/hello/data/sample.csv": "category,value\nA,12\nB,19\nC,8\n",
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
                        "id": entry.id,
                        "canvas_name": entry.canvas_name,
                        "title": entry.title,
                        "path": entry.relative_path,
                        "logical_path": entry.logical_path,
                        "parent_id": entry.parent_id,
                        "status": entry.status,
                        "runnable": entry.runnable,
                        "discovered": entry.discovered,
                        "message": entry.message,
                        "presentation": (
                            str(entry.dashboard.presentation_path.relative_to(loaded.root))
                            if entry.dashboard and entry.dashboard.presentation_path
                            else None
                        ),
                        "presentation_active": bool(entry.dashboard and entry.dashboard.presentation),
                        "sources": list(entry.dashboard.sources) if entry.dashboard else [],
                        "widgets": list(entry.dashboard.widgets) if entry.dashboard else [],
                    }
                    for entry in loaded.catalog
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
def templates() -> None:
    """List stable templates for AI and dashboard authors."""
    print_json(template_catalog())


def _doc_heading(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _print_doc_topic(name: str, definition: dict[str, Any]) -> None:
    typer.echo(f"# Dataviz docs · {name}\n")
    typer.echo(f"{definition['summary']}\n")
    for key, value in definition.items():
        if key == "summary":
            continue
        typer.echo(f"## {_doc_heading(key)}\n")
        if isinstance(value, str):
            if "\n" in value:
                typer.echo("```yaml")
                typer.echo(value.rstrip())
                typer.echo("```\n")
            else:
                typer.echo(f"{value}\n")
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            for item in value:
                typer.echo(f"- {item}")
            typer.echo()
        else:
            typer.echo("```yaml")
            typer.echo(yaml.safe_dump(value, allow_unicode=True, sort_keys=False).rstrip())
            typer.echo("```\n")


@app.command("docs")
def documentation(
    topic: str | None = typer.Argument(None, help="Topic, for example quickstart, charts, or troubleshooting"),
    search: str | None = typer.Option(None, "--search", help="Search all built-in documentation"),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Read the built-in AI development manual, recipes and troubleshooting guide."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    if topic is not None:
        resolved = resolve_doc_topic(topic)
        definition = DOC_TOPICS.get(resolved)
        if definition is None:
            raise typer.BadParameter(
                f"Unknown docs topic: {topic}. Available: {', '.join(DOC_TOPICS)}"
            )
        if output_format == "json":
            print_json({"topic": resolved, **definition})
        else:
            _print_doc_topic(resolved, definition)
        return

    catalog = docs_catalog(search)
    if output_format == "json":
        print_json({
            "start_here": "quickstart",
            "recommended_workflow": "workflow",
            "topics": catalog,
        })
        return
    typer.echo("# Dataviz CLI development manual\n")
    typer.echo("AI should begin with `dataviz docs quickstart`, then follow `dataviz docs workflow`.\n")
    if search:
        typer.echo(f"Search: `{search}`\n")
    for name, definition in catalog.items():
        typer.echo(f"- **{name}** — {definition['summary']}")
    typer.echo("\nRead a topic with `dataviz docs <topic>`; use `--format json` for machine input.")


@app.command()
def components(
    name: str | None = typer.Argument(None, help="Component name, for example selector.cascader"),
    category: str | None = typer.Option(None, "--category", help="Filter list by selector, view, section, or layout"),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Browse component contracts, examples, semantic DOM and style tokens."""
    catalog = component_catalog(category)
    if name is None:
        if output_format == "json":
            print_json(catalog)
            return
        typer.echo("# Dataviz component templates\n")
        for component_name, definition in catalog.items():
            typer.echo(f"- {component_name}: {definition['purpose']}")
        typer.echo("\nRun `dataviz components <name>` for the complete contract and example.")
        return
    definition = component_catalog().get(name)
    if definition is None:
        raise typer.BadParameter(
            f"Unknown component: {name}. Available: {', '.join(component_catalog())}"
        )
    if output_format == "json":
        print_json({"name": name, **definition})
        return
    typer.echo(f"# {name}\n")
    typer.echo(f"{definition['purpose']}\n")
    if definition.get("use_when"):
        typer.echo(f"Use when: {definition['use_when']}\n")
    for title, key in [
        ("Logic contract", "logic"),
        ("Presentation contract", "presentation"),
        ("Behavior contract", "behavior"),
        ("Semantic DOM", "semantic_dom"),
        ("Design tokens", "tokens"),
        ("Example", "example"),
    ]:
        if key not in definition:
            continue
        typer.echo(f"## {title}\n")
        typer.echo("```yaml")
        typer.echo(yaml.safe_dump(definition[key], allow_unicode=True, sort_keys=False).rstrip())
        typer.echo("```\n")


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
            "canvas_name": item.canvas_name,
            "content_title": item.title,
            "dashboard_logic": item.logic_definition.model_dump(mode="json", by_alias=True),
            "dashboard": item.definition.model_dump(mode="json", by_alias=True),
            "presentation": (
                item.presentation.model_dump(mode="json", by_alias=True)
                if item.presentation
                else None
            ),
            "presentation_file": (
                str(item.presentation_path.relative_to(loaded.root))
                if item.presentation_path
                else None
            ),
            "presentation_diagnostics": [
                diagnostic.as_dict() for diagnostic in (item.presentation_diagnostics or [])
            ],
            "dashboard_readme": item.readme,
            "templates": template_catalog(),
            "effective_selections": {
                widget_id: [value.as_dict() for value in values]
                for widget_id, values in compile_selection_contract(item.definition).items()
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
            typer.echo(f"# {item.title}\n\n{item.readme}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n")
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
    param: list[str] | None = typer.Option(None, "--param"),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Query every source required by a dashboard."""
    try:
        loaded = load_workspace(workspace)
        item = loaded.dashboard(dashboard)
        result = Executor(loaded).run(
            dashboard, params=parse_params(param), source_targets=list(item.sources), refresh=refresh
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
    selection: list[str] | None = typer.Option(None, "--selection"),
    legacy_filter: list[str] | None = typer.Option(None, "--filter", hidden=True),
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
            selections=parse_params(selection if selection is not None else legacy_filter),
            source_targets=list(loaded.dashboard(dashboard).sources),
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
                "selections": result.selections,
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
