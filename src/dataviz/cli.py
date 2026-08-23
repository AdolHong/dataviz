from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd
import typer
import yaml

from dataviz import __version__
from dataviz.authoring import (
    build_authoring_benchmark,
    build_context_payload,
    scaffold_recipe,
)
from dataviz.authoring_log import (
    AUTHORING_LOG_NAME,
    add_authoring_friction,
    authoring_log_report,
    finish_authoring_session,
    start_authoring_session,
)
from dataviz.artifacts import ArtifactStore
from dataviz.components import component_story_catalog, validate_component_packages
from dataviz.errors import DatavizError
from dataviz.frontend_adapters import frontend_adapter_catalog, frontend_adapter_source
from dataviz.documentation import DOC_TOPICS, docs_catalog, resolve_doc_topic
from dataviz.execution import Executor
from dataviz.execution.references import parse_output_reference
from dataviz.maintenance import cleanup_workspace_storage
from dataviz.migrations import CURRENT_SCHEMAS, migrate_workspace
from dataviz.rendering import CanvasRenderer, template_catalog
from dataviz.renderer_contract import run_renderer_contract
from dataviz.schema_docs import schema_catalog, schema_model_contract
from dataviz.server import create_app
from dataviz.templates import component_catalog
from dataviz.validation import format_validation_text, validate_preflight
from dataviz.workspace import load_workspace


app = typer.Typer(
    name="dataviz",
    help="Workspace-first data dashboards for humans and AI.",
    epilog="AI start here: dataviz docs quickstart",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
authoring_app = typer.Typer(
    name="authoring",
    help="Record real AI authoring cost and friction in the Workspace.",
    no_args_is_help=True,
)
app.add_typer(authoring_app, name="authoring")
GALLERY_WORKSPACE = Path(__file__).resolve().parent / "gallery"


def _copy_gallery_workspace(parent: Path) -> Path:
    """Materialize the read-only packaged Gallery as an ephemeral workspace."""
    destination = parent / "gallery"
    shutil.copytree(
        GALLERY_WORKSPACE,
        destination,
        ignore=shutil.ignore_patterns(".dataviz", "__pycache__", "*.pyc"),
    )
    stories = [component_story_catalog()[key] for key in sorted(component_story_catalog())]
    story_asset = destination / "dashboards" / "component-gallery" / "assets" / "component-stories.js"
    story_asset.write_text(
        "window.datavizComponentStories = "
        + json.dumps(stories, ensure_ascii=False, indent=2).replace("</", "<\\/")
        + ";\n",
        encoding="utf-8",
    )
    return destination


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


def _browser_runtime_benchmark(
    workspace,
    dashboard,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Run the exported Runtime in Chromium and return observable scale metrics."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise typer.BadParameter(
            "--browser-runtime requires the dev extra: uv sync --extra dev"
        ) from error

    query_started = time.perf_counter()
    result = Executor(workspace).run(dashboard.definition.id, refresh=True)
    query_ms = (time.perf_counter() - query_started) * 1000
    if result.status not in {"success", "partial"}:
        raise RuntimeError(f"Runtime benchmark query ended with {result.status}")

    with TemporaryDirectory(prefix="dataviz-runtime-benchmark-") as directory:
        report = CanvasRenderer(workspace).write_report(
            dashboard,
            result,
            Path(directory) / "benchmark.html",
        )
        browser_started = time.perf_counter()
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as error:
                raise typer.BadParameter(
                    "Chromium is unavailable; run: uv run --no-editable playwright install chromium"
                ) from error
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.goto(report.as_uri(), wait_until="domcontentloaded")
            page.wait_for_function(
                """() => {
                  const portable = window.dataviz?.portable;
                  const transports = Object.keys(portable?.output_transports || {});
                  const hydrated = transports.every(reference =>
                    Object.prototype.hasOwnProperty.call(portable.outputs, reference));
                  const repeats = [...document.querySelectorAll('.dv-repeat')];
                  const repeatReady = repeats.every(host => host.dataset.repeatCount !== undefined);
                  return window.datavizRuntime && hydrated && repeatReady;
                }""",
                timeout=timeout_seconds * 1000,
            )
            metrics = page.evaluate(
                """() => ({
                  runtime: window.datavizRuntime.metrics,
                  outputs: {
                    inline: Object.keys(window.dataviz.portable?.outputs || {}).length,
                    transports: Object.keys(window.dataviz.portable?.output_transports || {}).length,
                  },
                  repeat_sections: [...document.querySelectorAll('.dv-repeat')].map(host => ({
                    section: host.dataset.repeatSection,
                    groups: Number(host.dataset.repeatCount || 0),
                    filtered_groups: Number(host.dataset.repeatFilteredCount || 0),
                    rendered_cards: Number(host.dataset.repeatRenderedCards || 0),
                    build_ms: Number(host.dataset.repeatBuildMs || 0),
                    reconcile_ms: Number(host.dataset.repeatReconcileMs || 0),
                  })),
                  navigation: performance.getEntriesByType('navigation')[0]?.toJSON?.() || {},
                })"""
            )
            browser.close()
        browser_ms = (time.perf_counter() - browser_started) * 1000
    return {
        "schema": "dataviz/browser-runtime-benchmark/v1",
        "query_ms": round(query_ms, 2),
        "browser_total_ms": round(browser_ms, 2),
        "timeout_seconds": timeout_seconds,
        "console_errors": console_errors,
        **metrics,
    }


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
        ".gitignore": "auth/adapters.local.yaml\nadapters.local.yaml\n.dataviz/\ndist/\n",
        "README.md": """# My Analysis

Run with `dataviz serve .`.

AI authoring starts with:

```bash
dataviz docs quickstart
dataviz authoring start . --task \"Describe the dashboard change\"
```

Finish the returned session with `dataviz authoring finish`. Commit the generated
`dataviz-authoring.jsonl` when its task text and notes contain no sensitive data;
sharing that file gives the Dataviz author real retry, time and documentation-friction data.
""",
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
    kind: source
    name: Sample data
    type: file
    path: data/sample.csv
    format: csv
views:
  - id: summary
    title: Sample values
    input: data
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
                        "server_transforms": list(entry.dashboard.transforms) if entry.dashboard else [],
                        "browser_transforms": list(entry.dashboard.browser_transforms) if entry.dashboard else [],
                        "views": list(entry.dashboard.views) if entry.dashboard else [],
                    }
                    for entry in loaded.catalog
                ],
            }
        )
    except Exception as exc:
        handle_error(exc)


@app.command()
def validate(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str | None = typer.Option(
        None,
        "--dashboard",
        "-d",
        help="Validate one Dashboard id and its Workspace-level dependencies.",
    ),
    output_format: str = typer.Option(
        "text",
        "--format",
        help="text for humans or json for a stable AI-readable contract.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Return exit code 1 for warnings as well as errors.",
    ),
) -> None:
    """Run a static preflight without querying data or starting a Server."""
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be text or json")
    try:
        report = validate_preflight(
            workspace,
            dashboard_id=dashboard,
            strict=strict,
        )
        if output_format == "json":
            print_json(report)
        else:
            typer.echo(format_validation_text(report))
        if not report["passed"]:
            raise typer.Exit(report["exit_code"])
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


def _markdown_scalar(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return f"`{json.dumps(value, ensure_ascii=False, default=str)}`"
    return str(value).replace("|", "\\|").replace("\n", " ")


@app.command("schemas")
def schemas(
    name: str | None = typer.Argument(
        None, help="Model such as dashboard, source, view, or presentation"
    ),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
    full: bool = typer.Option(
        False,
        "--full",
        help="Include the complete generated JSON Schema with nested $defs",
    ),
) -> None:
    """Generate current DSL reference directly from installed Pydantic models."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    try:
        payload = schema_model_contract(name, full=full) if name else schema_catalog(full=full)
    except Exception as exc:
        handle_error(exc)
        return
    if output_format == "json":
        print_json(payload)
        return
    if name is None:
        typer.echo("# Dataviz generated schema catalog\n")
        typer.echo("Generated from the installed Pydantic models; it cannot drift from validation.\n")
        typer.echo("| Model | Contract schema | Fields |")
        typer.echo("| --- | --- | ---: |")
        for model_name, definition in payload["models"].items():
            typer.echo(
                f"| {model_name} | {_markdown_scalar(definition['contract_schema'])} | "
                f"{len(definition['fields'])} |"
            )
        typer.echo("\nUse `dataviz schemas <model> --format json` for one focused contract.")
        return
    typer.echo(f"# Dataviz schema · {payload['name']}\n")
    typer.echo(f"Model: `{payload['model']}`  ")
    typer.echo(f"Contract: `{payload['contract_schema'] or 'embedded'}`\n")
    typer.echo("| Field | Required | Type | Default | Description |")
    typer.echo("| --- | --- | --- | --- | --- |")
    for field in payload["fields"]:
        typer.echo(
            f"| {field['name']} | {'yes' if field['required'] else 'no'} | "
            f"{_markdown_scalar(field['type'])} | {_markdown_scalar(field.get('default'))} | "
            f"{_markdown_scalar(field.get('description'))} |"
        )
    if full:
        typer.echo("\n## Complete JSON Schema\n")
        typer.echo(f"```json\n{json.dumps(payload['json_schema'], ensure_ascii=False, indent=2)}\n```")


@app.command("version")
def version(output_format: str = typer.Option("json", "--format", help="json or text")) -> None:
    """Show package, DSL, Component Registry and browser protocol versions."""
    if output_format not in {"json", "text"}:
        raise typer.BadParameter("--format must be json or text")
    payload = {
        "package": "workspace-dataviz",
        "version": __version__,
        "dsl": CURRENT_SCHEMAS,
        "component_registry": template_catalog()["component_registry_version"],
        "runtime_protocol": template_catalog()["runtime_protocol"],
    }
    if output_format == "json":
        print_json(payload)
    else:
        typer.echo(
            f"workspace-dataviz {__version__} · "
            f"{payload['runtime_protocol']} · components {payload['component_registry']}"
        )


@app.command("migrate")
def migrate(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply registered offline migrations. Without it this is a dry run.",
    ),
) -> None:
    """Inspect or apply explicit DSL migrations; Runtime never runs legacy protocols."""
    try:
        report = migrate_workspace(workspace, apply=apply)
        print_json({"status": "blocked" if report["blockers"] else "success", **report})
        if report["blockers"]:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command("frontend-adapters")
def frontend_adapters(
    name: str | None = typer.Argument(None, help="Adapter id, for example web-component"),
    output: Path | None = typer.Option(
        None, "--output", help="Copy an exportable reference Adapter to this file"
    ),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Inspect frontend implementations that consume dataviz/runtime/v1."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    catalog = frontend_adapter_catalog()
    if name is not None and name not in catalog:
        raise typer.BadParameter(
            f"Unknown Frontend Adapter: {name}. Available: {', '.join(catalog)}"
        )
    if output is not None:
        if name is None:
            raise typer.BadParameter("--output requires an Adapter name")
        try:
            source = frontend_adapter_source(name)
        except Exception as exc:
            handle_error(exc)
            return
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(source, encoding="utf-8")
        print_json({"status": "success", "adapter": name, "output": str(output)})
        return
    payload: Any = catalog[name] if name else catalog
    if output_format == "json":
        print_json(payload)
        return
    typer.echo("# Dataviz frontend adapters\n")
    values = {name: payload} if name else payload
    for adapter_id, definition in values.items():
        typer.echo(
            f"- **{adapter_id}** ({definition['status']}) — {definition['purpose']} "
            f"Protocol: `{definition['protocol']}`."
        )
    typer.echo(
        "\nThe Web Component reference does not import Canvas Runtime internals; "
        "it is the decoupling contract probe."
    )


def _first_attempt_value(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"success", "yes", "true"}:
        return True
    if normalized in {"failure", "failed", "no", "false"}:
        return False
    if normalized in {"unknown", "unmeasured", "none"}:
        return None
    raise typer.BadParameter("--first-attempt must be success, failure, or unknown")


@authoring_app.command("start")
def authoring_start(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    task: str = typer.Option(..., "--task", help="Concrete dashboard authoring task"),
    dashboard: str | None = typer.Option(None, "--dashboard"),
    model: str | None = typer.Option(None, "--model"),
    tool: str | None = typer.Option(None, "--tool"),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Start one append-only, shareable authoring measurement session."""
    try:
        event = start_authoring_session(
            workspace,
            task=task,
            dashboard_id=dashboard,
            model=model,
            tool=tool,
            notes=notes,
        )
        print_json(
            {
                "status": "started",
                "session_id": event.session_id,
                "log": str(workspace.resolve() / AUTHORING_LOG_NAME),
                "next": (
                    f"dataviz authoring finish {workspace} {event.session_id} "
                    "--outcome success --first-attempt success --correction-rounds 0"
                ),
            }
        )
    except Exception as exc:
        handle_error(exc)


@authoring_app.command("note")
def authoring_note(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    session_id: str = typer.Argument(...),
    category: str = typer.Option(..., "--category"),
    message: str = typer.Option(..., "--message"),
    reference: str | None = typer.Option(None, "--reference"),
) -> None:
    """Append one unclear document, bad contract or tooling friction observation."""
    try:
        event = add_authoring_friction(
            workspace,
            session_id,
            category=category,
            message=message,
            reference=reference,
        )
        print_json(
            {
                "status": "recorded",
                "session_id": event.session_id,
                "category": event.category,
            }
        )
    except Exception as exc:
        handle_error(exc)


@authoring_app.command("finish")
def authoring_finish(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    session_id: str = typer.Argument(...),
    outcome: str = typer.Option("success", "--outcome"),
    first_attempt: str = typer.Option("unknown", "--first-attempt"),
    correction_rounds: int = typer.Option(0, "--correction-rounds", min=0),
    input_tokens: int | None = typer.Option(None, "--input-tokens", min=0),
    output_tokens: int | None = typer.Option(None, "--output-tokens", min=0),
    docs_used: list[str] | None = typer.Option(None, "--docs-used"),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Finish a session with measured quality, retries, elapsed time and token usage."""
    try:
        event = finish_authoring_session(
            workspace,
            session_id,
            outcome=outcome,
            first_attempt_success=_first_attempt_value(first_attempt),
            correction_rounds=correction_rounds,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            docs_used=docs_used,
            notes=notes,
        )
        print_json(
            {
                "status": "finished",
                "session_id": event.session_id,
                "outcome": event.outcome,
                "elapsed_seconds": event.elapsed_seconds,
                "token_source": event.token_source,
            }
        )
    except Exception as exc:
        handle_error(exc)


@authoring_app.command("show")
def authoring_show(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    session_id: str | None = typer.Option(None, "--session"),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Aggregate the append-only authoring log without inventing missing measurements."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    try:
        report = authoring_log_report(workspace, session_id=session_id)
    except Exception as exc:
        handle_error(exc)
        return
    if output_format == "json":
        print_json(report)
        return
    metrics = report["metrics"]
    typer.echo("# Dataviz authoring log\n")
    typer.echo(f"File: `{report['log_file']}`\n")
    typer.echo(f"- Sessions: {metrics['sessions']} ({metrics['finished']} finished)")
    typer.echo(f"- Successful: {metrics['successful']}")
    typer.echo(
        f"- First-attempt success: {metrics['first_attempt_success_rate'] if metrics['first_attempt_success_rate'] is not None else 'unmeasured'}"
    )
    typer.echo(
        f"- Mean correction rounds: {metrics['mean_correction_rounds'] if metrics['mean_correction_rounds'] is not None else 'unmeasured'}"
    )
    typer.echo(
        f"- Reported tokens: {metrics['reported_input_tokens']} input / "
        f"{metrics['reported_output_tokens']} output across {metrics['token_measured_sessions']} sessions\n"
    )
    for session in report["sessions"]:
        typer.echo(
            f"## {session['session_id']} · {session.get('outcome', session['status'])}\n\n"
            f"{session.get('task', 'Orphaned event')}\n"
        )
        for friction in session["frictions"]:
            reference = f" · {friction['reference']}" if friction.get("reference") else ""
            typer.echo(f"- {friction['category']}{reference}: {friction['message']}")
        if session["frictions"]:
            typer.echo()


@app.command()
def components(
    name: str | None = typer.Argument(None, help="Component name, for example selector.cascader"),
    category: str | None = typer.Option(
        None,
        "--category",
        help="Filter by selector, view, section, layout, theme, renderer, runtime, data, or presentation",
    ),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
    check_packages: bool = typer.Option(
        False,
        "--check",
        help="Validate every physical Manifest, Controller, Adapter, Style, Story and Test",
    ),
) -> None:
    """Browse component contracts, examples, semantic DOM and style tokens."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    catalog = component_catalog(category)
    if check_packages:
        report = validate_component_packages(component_catalog().keys())
        if output_format == "json":
            print_json(report)
        else:
            status = "PASS" if report["valid"] else "FAIL"
            typer.echo(f"# Component Package check · {status}\n")
            typer.echo(
                f"{report['packages']} packages · {report['components']} components · "
                f"{report['stories']} stories · {report['tests']} tests"
            )
            for error in report["errors"]:
                typer.echo(f"- {error}")
        if not report["valid"]:
            raise typer.Exit(1)
        return
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
        ("Physical package", "package"),
        ("Logic contract", "logic"),
        ("Presentation contract", "presentation"),
        ("Behavior contract", "behavior"),
        ("Semantic DOM", "semantic_dom"),
        ("Design tokens", "tokens"),
        ("Contract tests", "tests"),
        ("Gallery Story", "gallery"),
        ("Example", "example"),
    ]:
        if key not in definition:
            continue
        typer.echo(f"## {title}\n")
        typer.echo("```yaml")
        typer.echo(yaml.safe_dump(definition[key], allow_unicode=True, sort_keys=False).rstrip())
        typer.echo("```\n")


@app.command()
def gallery(
    output: Path | None = typer.Option(
        None, "--output", help="Export the Gallery as one interactive HTML instead of serving it"
    ),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8079, "--port"),
) -> None:
    """Open the runtime-native Section, View, Selector and Renderer Gallery."""
    try:
        with TemporaryDirectory(prefix="dataviz-gallery-") as temporary:
            gallery_root = _copy_gallery_workspace(Path(temporary))
            if output is not None:
                workspace = load_workspace(gallery_root)
                result = Executor(workspace).run("component-gallery", refresh=True)
                path = CanvasRenderer(workspace).write_report(
                    workspace.dashboard("component-gallery"), result, output.resolve()
                )
                print_json(
                    {
                        "status": "success",
                        "gallery": str(path),
                        "component_registry_version": template_catalog()["component_registry_version"],
                    }
                )
                return
            import uvicorn

            uvicorn.run(create_app(gallery_root), host=host, port=port)
    except Exception as exc:
        handle_error(exc)


@app.command("renderer-test")
def renderer_test(
    script: Path = typer.Argument(..., exists=True, dir_okay=False, help="Custom Renderer JavaScript"),
    renderer_id: str = typer.Option(..., "--renderer-id", help="Registered Renderer id"),
    contract: Path | None = typer.Option(
        None,
        "--contract",
        exists=True,
        dir_okay=False,
        help="Optional dataviz/renderer-contract/v1 JSON",
    ),
    timeout_seconds: float = typer.Option(10.0, "--timeout-seconds", min=1, max=120),
) -> None:
    """Run validate, mount, update and dispose for a custom Renderer in Chromium."""
    try:
        result = run_renderer_contract(
            script.resolve(),
            renderer_id,
            contract=contract.resolve() if contract else None,
            timeout_seconds=timeout_seconds,
        )
        print_json(result)
        if not result["valid"]:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command()
def context(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    focus: str | None = typer.Option(
        None,
        "--focus",
        help="Dependency slice such as view:<id>, section:<id>, source:<id>, or component:<id>",
    ),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Emit a complete or dependency-focused AI authoring context."""
    try:
        if output_format not in {"markdown", "json"}:
            raise typer.BadParameter("--format must be markdown or json")
        loaded = load_workspace(workspace)
        item = loaded.dashboard(dashboard)
        payload = build_context_payload(loaded, item, focus=focus)
        if output_format == "json":
            print_json(payload)
        else:
            label = f" · {focus}" if focus else ""
            typer.echo(
                f"# {item.title}{label}\n\n"
                f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n"
            )
    except Exception as exc:
        handle_error(exc)


@app.command()
def scaffold(
    recipe: str = typer.Argument(
        ...,
        help="Recipe such as dashboard, view.line, selector.cascader, or transform.server-python",
    ),
    identifier: str = typer.Option("example", "--id", help="Stable id used in generated files"),
    output: Path | None = typer.Option(
        None, "--output", help="Optional directory to materialize the recipe"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing recipe files"),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Print or materialize a strict current-schema authoring recipe."""
    try:
        if output_format not in {"markdown", "json"}:
            raise typer.BadParameter("--format must be markdown or json")
        payload = scaffold_recipe(recipe, identifier)
        if output is not None:
            root = output.resolve()
            conflicts = [
                str(relative)
                for relative in payload["files"]
                if (root / relative).exists() and not force
            ]
            if conflicts:
                raise typer.BadParameter(
                    "Refusing to overwrite existing files: " + ", ".join(conflicts)
                )
            written = []
            for relative, content in payload["files"].items():
                destination = (root / relative).resolve()
                if not destination.is_relative_to(root):
                    raise typer.BadParameter(f"Recipe path escapes output directory: {relative}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
                written.append(str(destination))
            print_json(
                {
                    "status": "success",
                    "recipe": recipe,
                    "id": identifier,
                    "output": str(root),
                    "files": written,
                    "next": "dataviz validate <workspace>",
                }
            )
            return
        if output_format == "json":
            print_json(payload)
            return
        typer.echo(f"# Dataviz scaffold · {recipe}\n")
        for relative, content in payload["files"].items():
            language = {
                ".yaml": "yaml",
                ".yml": "yaml",
                ".py": "python",
                ".js": "javascript",
                ".sql": "sql",
                ".css": "css",
                ".html": "html",
            }.get(Path(relative).suffix.lower(), "text")
            typer.echo(f"## {relative}\n\n```{language}\n{content.rstrip()}\n```\n")
        typer.echo("Run `dataviz validate <workspace>` after merging these files.")
    except Exception as exc:
        handle_error(exc)


@app.command()
def benchmark(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    focus: str | None = typer.Option(
        None, "--focus", help="Measure one context slice instead of every View"
    ),
    output_format: str = typer.Option("json", "--format", help="json or markdown"),
    browser_runtime: bool = typer.Option(
        False,
        "--browser-runtime",
        help="Also execute the exported page in Chromium and measure Runtime/Repeat scale",
    ),
    timeout_seconds: float = typer.Option(
        30.0,
        "--timeout-seconds",
        min=1,
        help="Browser Runtime benchmark deadline",
    ),
) -> None:
    """Measure authoring code and deterministic context size without guessing tokens."""
    try:
        if output_format not in {"markdown", "json"}:
            raise typer.BadParameter("--format must be markdown or json")
        loaded = load_workspace(workspace)
        payload = build_authoring_benchmark(
            loaded, loaded.dashboard(dashboard), focus=focus
        )
        if browser_runtime:
            payload["browser_runtime"] = _browser_runtime_benchmark(
                loaded,
                loaded.dashboard(dashboard),
                timeout_seconds=timeout_seconds,
            )
        if output_format == "json":
            print_json(payload)
            return
        summary = payload["context"]["focused_summary"]
        files = payload["authoring_files"]["totals"]
        typer.echo(f"# Dataviz authoring benchmark · {payload['dashboard']}\n")
        typer.echo(
            f"- Authoring code: {files['all']['lines']} lines / "
            f"{files['all']['utf8_bytes']} bytes"
        )
        typer.echo(f"- Full context: {payload['context']['full']['utf8_bytes']} bytes")
        typer.echo(
            f"- Focused context median: {summary['median_utf8_bytes']} bytes "
            f"({summary['median_reduction_percent']}% smaller)"
        )
        typer.echo(
            f"- Strict validation: "
            f"{'valid' if payload['validation']['valid'] else 'invalid'}"
        )
        if payload.get("browser_runtime"):
            runtime = payload["browser_runtime"]
            typer.echo(f"- Browser Runtime: {runtime['browser_total_ms']} ms")
            typer.echo(
                f"- Repeat Sections: {len(runtime['repeat_sections'])}; "
                f"max groups: {max((item['groups'] for item in runtime['repeat_sections']), default=0)}"
            )
        typer.echo(
            "\nToken counts and AI retry quality are intentionally left for model-specific evals.\n"
        )
        typer.echo(f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```")
    except Exception as exc:
        handle_error(exc)


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
            dashboard, params=parse_params(param), targets=[f"source:{source}"], refresh=refresh
        )
        node = result.nodes[f"source:{source}"]
        artifact = node.outputs.get("main")
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


@app.command("output")
def inspect_output(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    reference: str = typer.Argument(
        ..., help="Named Output, for example transform:sales-metrics/trend"
    ),
    param: list[str] | None = typer.Option(None, "--param"),
    output_format: str = typer.Option("json", "--format", help="json, csv, markdown, or text"),
    limit: int = typer.Option(100, "--limit", min=1),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Execute the dependency closure and inspect one canonical Named Output."""
    try:
        if output_format not in {"json", "csv", "markdown", "text"}:
            raise typer.BadParameter("--format must be json, csv, markdown, or text")
        loaded = load_workspace(workspace)
        parsed = parse_output_reference(reference)
        canonical = parsed.canonical
        if parsed.node_id.startswith("browser:"):
            raise typer.BadParameter(
                "Browser Transform outputs only exist in HTML; inspect their server input or export a report"
            )
        result = Executor(loaded).run(
            dashboard,
            params=parse_params(param),
            targets=[canonical],
            refresh=refresh,
        )
        artifact = result.outputs.get(canonical)
        if artifact is None:
            print_json(result)
            raise typer.Exit(1)
        store = ArtifactStore(loaded.root, result.run_id)
        value = store.read_value(artifact)
        if artifact.kind == "table":
            frame = value.head(limit)
            if output_format == "csv":
                typer.echo(frame.to_csv(index=False), nl=False)
                return
            if output_format == "markdown":
                typer.echo(frame.to_markdown(index=False))
                return
            if output_format == "text":
                typer.echo(frame.to_string(index=False))
                return
            value = json.loads(frame.to_json(orient="records", date_format="iso"))
        elif output_format != "json":
            typer.echo(str(value))
            return
        print_json(
            {
                "status": result.status,
                "run_id": result.run_id,
                "reference": canonical,
                "parameters": result.parameters,
                "artifact": artifact.model_dump(mode="json", by_alias=True),
                "value": value,
                "truncated": (
                    artifact.kind == "table"
                    and int(artifact.metadata.get("row_count", 0)) > limit
                ),
            }
        )
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command()
def run(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    param: list[str] | None = typer.Option(None, "--param"),
    target: list[str] | None = typer.Option(
        None, "--target", help="Source/Transform node or Named Output; repeatable"
    ),
    refresh: bool = typer.Option(False, "--refresh"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
) -> None:
    """Execute the Source and Server Transform DAG."""
    try:
        loaded = load_workspace(workspace)
        result = Executor(loaded).run(
            dashboard,
            params=parse_params(param),
            targets=target,
            refresh=refresh,
        )
        print_json(result)
        if result.status != "success" and not (allow_partial and result.status == "partial"):
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
            selections=parse_params(selection),
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


@app.command("clean")
def clean_workspace(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Delete listed entries. Without this flag the command is a dry run.",
    ),
    all_state: bool = typer.Option(
        False,
        "--all",
        help="Select every unprotected Run and cache entry.",
    ),
    keep_runs: int | None = typer.Option(
        None,
        "--keep-runs",
        min=0,
        help="Override the number of newest Run directories to retain.",
    ),
    run_max_age_hours: float | None = typer.Option(
        None,
        "--run-max-age-hours",
        min=0,
        help="Select Run directories older than this many hours.",
    ),
    keep_cache_entries: int | None = typer.Option(
        None,
        "--keep-cache-entries",
        min=0,
        help="Override the number of newest persistent cache entries to retain.",
    ),
    cache_max_age_hours: float | None = typer.Option(
        None,
        "--cache-max-age-hours",
        min=0,
        help="Select persistent cache entries older than this many hours.",
    ),
    include_runs: bool = typer.Option(True, "--runs/--no-runs"),
    include_cache: bool = typer.Option(True, "--cache/--no-cache"),
) -> None:
    """Preview or remove old .dataviz Run Artifacts and persistent caches."""
    try:
        loaded = load_workspace(workspace)
        runtime = loaded.definition.runtime
        report = cleanup_workspace_storage(
            loaded.root,
            max_runs=(
                0
                if all_state
                else keep_runs
                if keep_runs is not None
                else runtime.max_retained_runs
            ),
            run_max_age_seconds=(
                0
                if all_state
                else run_max_age_hours * 3600
                if run_max_age_hours is not None
                else runtime.run_retention_seconds
            ),
            max_cache_entries=(
                0
                if all_state
                else keep_cache_entries
                if keep_cache_entries is not None
                else runtime.max_retained_cache_entries
            ),
            cache_max_age_seconds=(
                0
                if all_state
                else cache_max_age_hours * 3600
                if cache_max_age_hours is not None
                else runtime.cache_retention_seconds
            ),
            include_runs=include_runs,
            include_cache=include_cache,
            apply=apply,
        )
        print_json({"status": "success", **report})
        if report["errors"]:
            raise typer.Exit(1)
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
