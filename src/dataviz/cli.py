from __future__ import annotations

import json
import ipaddress
import shlex
import shutil
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import typer
import yaml

from dataviz import __version__
from dataviz.authoring import (
    build_authoring_benchmark,
    build_context_payload,
    scaffold_recipe,
    scaffold_recipes,
)
from dataviz.authoring_log import (
    AUTHORING_LOG_NAME,
    add_authoring_friction,
    authoring_log_report,
    finish_authoring_session,
    start_authoring_session,
)
from dataviz.authoring_evaluation import (
    AUTHORING_APPROACHES,
    authoring_evaluation_protocol,
    authoring_task_catalog,
    build_authoring_evaluation_report,
    inspect_authoring_trial,
    prepare_authoring_trial,
    record_authoring_assessment,
)
from dataviz.artifacts import ArtifactStore
from dataviz.components import component_story_catalog, validate_component_packages
from dataviz.errors import DatavizError, ExecutionFailure
from dataviz.frontend_adapters import frontend_adapter_catalog, frontend_adapter_source
from dataviz.filesystem import atomic_write_text, transactional_write_texts
from dataviz.documentation import DOC_TOPICS, docs_catalog, resolve_doc_topic
from dataviz.execution import Executor, InteractionExecutor
from dataviz.execution.interactive import load_run_result
from dataviz.execution.plan import reachable_output_references
from dataviz.execution.references import parse_output_reference
from dataviz.maintenance import cleanup_workspace_storage
from dataviz.rendering import CanvasRenderer, template_catalog
from dataviz.renderer_contract import run_renderer_contract
from dataviz.schema_docs import CURRENT_SCHEMAS, schema_catalog, schema_model_contract
from dataviz.server import create_app
from dataviz.templates import component_catalog
from dataviz.validation import format_validation_text, validate_preflight
from dataviz.workspace import load_workspace
from dataviz.workspace.controls import resolve_compute_values, resolve_selection_values


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


def _require_remote_bind_opt_in(host: str, *, allow_remote: bool) -> None:
    """Keep the unauthenticated local Server on loopback unless explicitly exposed."""
    normalized = host.strip().removeprefix("[").removesuffix("]")
    is_loopback = normalized.casefold() == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(normalized).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback and not allow_remote:
        raise typer.BadParameter(
            "Dataviz Server has no authentication. Non-loopback --host requires "
            "the explicit --allow-remote opt-in and a trusted network boundary."
        )


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
    atomic_write_text(
        story_asset,
        "window.datavizComponentStories = "
        + json.dumps(stories, ensure_ascii=False, indent=2).replace("</", "<\\/")
        + ";\n",
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
    if result.status not in {"ready", "partial"}:
        raise RuntimeError(f"Runtime benchmark query ended with {result.status}")

    with TemporaryDirectory(prefix="dataviz-runtime-benchmark-") as directory:
        report_started = time.perf_counter()
        report = CanvasRenderer(workspace).write_report(
            dashboard,
            result,
            Path(directory) / "benchmark.html",
        )
        report_ms = (time.perf_counter() - report_started) * 1000
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
            page_started = time.perf_counter()
            page.goto(report.as_uri(), wait_until="domcontentloaded")
            page.wait_for_function(
                """() => {
                  const portable = window.dataviz?.portable;
                  const transports = Object.keys(portable?.output_transports || {});
                  const hydrated = transports.every(reference =>
                    Object.prototype.hasOwnProperty.call(portable.outputs, reference));
                  const repeats = [...document.querySelectorAll('.dv-repeat')];
                  const repeatReady = repeats.every(host => host.dataset.repeatCount !== undefined);
                  const views = [...document.querySelectorAll('.dv-view')].filter(root =>
                    !root.classList.contains('dv-repeat-card')
                    || root.dataset.repeatMounted === 'true'
                  );
                  const terminal = new Set([
                    'ready', 'empty', 'stale', 'error', 'cancelled', 'unavailable',
                  ]);
                  const viewsSettled = views.every(root => terminal.has(root.dataset.viewStatus));
                  return window.datavizRuntime
                    && hydrated
                    && repeatReady
                    && viewsSettled
                    && window.datavizRuntime.activeTransforms.size === 0;
                }""",
                timeout=timeout_seconds * 1000,
            )
            page_ready_ms = (time.perf_counter() - page_started) * 1000
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
                  view_states: [...document.querySelectorAll('.dv-view')].reduce((counts, root) => {
                    const status = root.dataset.viewStatus || 'unknown';
                    counts[status] = (counts[status] || 0) + 1;
                    return counts;
                  }, {}),
                  navigation: performance.getEntriesByType('navigation')[0]?.toJSON?.() || {},
                })"""
            )
            browser.close()
        browser_ms = (time.perf_counter() - browser_started) * 1000
    return {
        "schema": "dataviz/browser-runtime-benchmark/v2",
        "query_ms": round(query_ms, 2),
        "report_build_ms": round(report_ms, 2),
        "page_ready_ms": round(page_ready_ms, 2),
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
    if path.exists():
        if not path.is_dir():
            raise typer.BadParameter(f"Workspace path is not a directory: {path}")
        if any(path.iterdir()):
            raise typer.BadParameter(f"Directory is not empty: {path}")
    files = {
        "workspace.yaml": """schema: dataviz/workspace/v1
kind: workspace
id: my-analysis
title: My Analysis
description: A workspace-first dashboard project
folders: []
""",
        ".gitignore": "auth/adapters.local.yaml\n.dataviz/\ndist/\n",
        "auth/adapters.yaml": "adapters: {}\n",
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
        "dashboards/hello/dashboard.yaml": """schema: dataviz/dashboard/v3
kind: dashboard
id: hello
title: Hello dashboard
description: A minimal self-contained canvas
controls:
  - id: category
    kind: selection
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
    outputs: {main: {kind: table}}
views:
  - id: summary
    title: Sample values
    input: source:data/main
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
    transactional_write_texts(path, files)
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
                        "dataset_transforms": (
                            list(entry.dashboard.dataset_transforms)
                            if entry.dashboard
                            else []
                        ),
                        "interactive_transforms": (
                            list(entry.dashboard.interactive_transforms)
                            if entry.dashboard
                            else []
                        ),
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
    if payload.get("variants"):
        typer.echo(
            "Variants: "
            + ", ".join(
                f"`{item['type']}`" for item in payload["variants"]
            )
            + f" (discriminator: `{payload['discriminator']}`)\n"
        )
    has_variants = bool(payload.get("variants"))
    if has_variants:
        typer.echo("| Field | Required in | Applies to | Type | Default | Description |")
        typer.echo("| --- | --- | --- | --- | --- | --- |")
    else:
        typer.echo("| Field | Required | Type | Default | Description |")
        typer.echo("| --- | --- | --- | --- | --- |")
    for field in payload["fields"]:
        if has_variants:
            typer.echo(
                f"| {field['name']} | "
                f"{_markdown_scalar(field.get('required_in', []))} | "
                f"{_markdown_scalar(field.get('variants', []))} | "
                f"{_markdown_scalar(field['type'])} | "
                f"{_markdown_scalar(field.get('default'))} | "
                f"{_markdown_scalar(field.get('description'))} |"
            )
        else:
            typer.echo(
                f"| {field['name']} | {'yes' if field['required'] else 'no'} | "
                f"{_markdown_scalar(field['type'])} | {_markdown_scalar(field.get('default'))} | "
                f"{_markdown_scalar(field.get('description'))} |"
            )
    template_contracts = payload.get("template_contracts", {})
    if template_contracts:
        typer.echo("\n## Template contracts\n")
        typer.echo("| Template | Required | Optional | Additional constraint |")
        typer.echo("| --- | --- | --- | --- |")
        for template, contract in template_contracts.items():
            constraints = []
            if contract.get("one_of"):
                constraints.append(f"one of {contract['one_of']}")
            if contract.get("engine"):
                constraints.append(f"engine={contract['engine']}")
            if contract.get("aggregate"):
                constraints.append(f"aggregate in {contract['aggregate']}")
            typer.echo(
                f"| {template} | {_markdown_scalar(contract['required'])} | "
                f"{_markdown_scalar(contract['optional'])} | "
                f"{_markdown_scalar('; '.join(constraints) or None)} |"
            )
    adapter_contracts = payload.get("adapter_contracts", {})
    if adapter_contracts:
        typer.echo("\n## Built-in Adapter contracts\n")
        typer.echo("| Type | Optional fields | Connection requirement |")
        typer.echo("| --- | --- | --- |")
        for adapter_type, contract in adapter_contracts.items():
            typer.echo(
                f"| {adapter_type} | {_markdown_scalar(contract['optional'])} | "
                f"{_markdown_scalar(contract.get('connection'))} |"
            )
        typer.echo(
            "\nUnknown Adapter types are reserved for trusted Python Sources and use "
            "the generic configuration envelope."
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


@app.command("frontend-adapters")
def frontend_adapters(
    name: str | None = typer.Argument(None, help="Adapter id, for example web-component"),
    output: Path | None = typer.Option(
        None, "--output", help="Copy an exportable reference Adapter to this file"
    ),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Inspect frontend implementations that consume dataviz/runtime/v2."""
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
        atomic_write_text(output, source)
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
    task: str | None = typer.Option(None, "--task", help="Concrete ad-hoc authoring task"),
    dashboard: str | None = typer.Option(None, "--dashboard"),
    model: str | None = typer.Option(None, "--model"),
    tool: str | None = typer.Option(None, "--tool"),
    trial_directory: Path | None = typer.Option(
        None,
        "--trial-dir",
        exists=True,
        file_okay=False,
        help="Prepared fixed-task directory; supplies task, approach and trial identity",
    ),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Start one append-only, shareable authoring measurement session."""
    try:
        trial = inspect_authoring_trial(trial_directory) if trial_directory else None
        if trial is not None:
            if not trial["integrity_passed"] or not trial["assessment_valid"]:
                raise ValueError(
                    "Prepared trial is invalid; run `dataviz authoring verify TRIAL_DIR`"
                )
            if task is not None:
                raise ValueError("--task and --trial-dir are mutually exclusive")
            if not model or not tool:
                raise ValueError("Benchmark trials require both --model and --tool")
            task = trial["task"]
        elif not task or not task.strip():
            raise ValueError("Provide --task for ad-hoc work or --trial-dir for a benchmark")
        event = start_authoring_session(
            workspace,
            task=task,
            dashboard_id=dashboard,
            model=model,
            tool=tool,
            benchmark_task=trial["benchmark_task"] if trial else None,
            approach=trial["approach"] if trial else None,
            trial_id=trial["trial_id"] if trial else None,
            task_contract_sha256=trial["task_contract_sha256"] if trial else None,
            task_prompt_sha256=trial["task_prompt_sha256"] if trial else None,
            fixture_sha256=trial["fixture_sha256"] if trial else None,
            notes=notes,
        )
        workspace_arg = shlex.quote(str(workspace.resolve()))
        session_arg = shlex.quote(event.session_id)
        finish_command = (
            f"dataviz authoring finish {workspace_arg} {session_arg} "
            "--outcome success --first-attempt success --correction-rounds 0"
        )
        if trial_directory:
            trial_arg = shlex.quote(str(trial_directory.resolve()))
            next_steps = [
                f"dataviz authoring assess {trial_arg} CHECK_ID --status passed "
                "--assessor ASSESSOR --evidence EVIDENCE",
                f"dataviz authoring verify {trial_arg} --format json",
                f"{finish_command} --trial-dir {trial_arg}",
            ]
        else:
            next_steps = [finish_command]
        print_json(
            {
                "status": "started",
                "session_id": event.session_id,
                "log": str(workspace.resolve() / AUTHORING_LOG_NAME),
                "benchmark_task": event.benchmark_task,
                "approach": event.approach,
                "trial_id": event.trial_id,
                "next_steps": next_steps,
            }
        )
    except Exception as exc:
        handle_error(exc)


@authoring_app.command("tasks")
def authoring_tasks(
    task: str | None = typer.Argument(None, help="Optional fixed evaluation task id"),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """List the five fixed Dataviz versus standalone-HTML evaluation tasks."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    try:
        payload = authoring_task_catalog(task)
    except Exception as exc:
        handle_error(exc)
        return
    if output_format == "json":
        print_json(payload)
        return
    typer.echo("# Dataviz AI authoring evaluation tasks\n")
    for definition in payload["tasks"].values():
        typer.echo(f"## {definition['id']} · {definition['title']}\n")
        typer.echo(f"{definition['brief']}\n")
        typer.echo("Acceptance:\n")
        for item in definition["acceptance"]:
            typer.echo(f"- [{item['id']}] {item['criterion']}")
        typer.echo()


@authoring_app.command("protocol")
def authoring_protocol(
    task: str | None = typer.Option(None, "--task"),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Print the reproducible paired-evaluation protocol without running an AI."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    try:
        payload = authoring_evaluation_protocol(task)
    except Exception as exc:
        handle_error(exc)
        return
    if output_format == "json":
        print_json(payload)
        return
    typer.echo("# Dataviz AI authoring paired protocol\n")
    typer.echo(f"{payload['quality_gate']}\n")
    typer.echo(f"{payload['token_rule']}\n")
    typer.echo("Run the same task once with `dataviz` and once with `standalone-html`, using the same `trial_id`.\n")
    for name, command in payload["commands"].items():
        typer.echo(f"- {name}: `{command}`")


@authoring_app.command("prepare")
def authoring_prepare(
    task: str = typer.Argument(..., help="One id from `dataviz authoring tasks`"),
    destination: Path = typer.Argument(...),
    approach: str = typer.Option(..., "--approach", help="dataviz or standalone-html"),
    trial_id: str = typer.Option(..., "--trial-id"),
) -> None:
    """Create a neutral data/task pack for one side of a paired trial."""
    try:
        payload = prepare_authoring_trial(
            task,
            destination,
            approach=approach,
            trial_id=trial_id,
        )
        print_json(payload)
    except Exception as exc:
        handle_error(exc)


@authoring_app.command("verify")
def authoring_verify(
    trial_directory: Path = typer.Argument(..., exists=True, file_okay=False),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Verify fixed task/input hashes and the evidence-backed acceptance record."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    payload = inspect_authoring_trial(trial_directory)
    if output_format == "json":
        print_json(payload)
    else:
        typer.echo(f"# Authoring trial · {payload['trial_id']}\n")
        typer.echo(f"- Input integrity: {'passed' if payload['integrity_passed'] else 'failed'}")
        typer.echo(f"- Assessment structure: {'valid' if payload['assessment_valid'] else 'invalid'}")
        typer.echo(f"- Quality gate: {'passed' if payload['quality_passed'] else 'not passed'}")
        for item in payload["checks"]:
            typer.echo(f"- [{item['status']}] {item['id']}: {item['evidence'] or 'no evidence'}")
        for item in payload["diagnostics"]:
            typer.echo(f"- ERROR {item['code']}: {item['message']}")
    if not payload["integrity_passed"] or not payload["assessment_valid"]:
        raise typer.Exit(code=1)


@authoring_app.command("assess")
def authoring_assess(
    trial_directory: Path = typer.Argument(..., exists=True, file_okay=False),
    check_id: str = typer.Argument(...),
    status: str = typer.Option(..., "--status", help="passed, failed or unmeasured"),
    assessor: str | None = typer.Option(
        None, "--assessor", help="human, automation or mixed"
    ),
    evidence: str = typer.Option("", "--evidence"),
) -> None:
    """Record evidence for exactly one fixed acceptance check."""
    try:
        payload = record_authoring_assessment(
            trial_directory,
            check_id,
            status=status,
            assessor=assessor,
            evidence=evidence,
        )
        print_json(
            {
                "status": "recorded",
                "check_id": check_id,
                "quality_passed": payload["quality_passed"],
                "remaining": [
                    item["id"]
                    for item in payload["checks"]
                    if item["status"] != "passed"
                ],
            }
        )
    except Exception as exc:
        handle_error(exc)


@authoring_app.command("compare")
def authoring_compare(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    task: str | None = typer.Option(None, "--task"),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Compare complete Dataviz/standalone-HTML trial pairs using real measurements."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    try:
        sessions = authoring_log_report(workspace)["sessions"]
        payload = build_authoring_evaluation_report(sessions, task_id=task)
    except Exception as exc:
        handle_error(exc)
        return
    if output_format == "json":
        print_json(payload)
        return
    typer.echo("# Dataviz AI authoring comparison\n")
    typer.echo(f"- Complete pairs: {payload['complete_pairs']}")
    typer.echo(f"- Identity-matched pairs: {payload['comparable_pairs']}")
    typer.echo(f"- Both approaches passed: {payload['quality_pairs']}")
    typer.echo(f"- Measured sessions: {payload['sessions']}")
    for approach in AUTHORING_APPROACHES:
        metrics = payload["approaches"][approach]
        typer.echo(
            f"- {approach}: {metrics['successful']}/{metrics['sessions']} successful; "
            f"first-attempt {metrics['first_attempt_success_rate'] if metrics['first_attempt_success_rate'] is not None else 'unmeasured'}; "
            f"input tokens {metrics['mean_input_tokens'] if metrics['mean_input_tokens'] is not None else 'unmeasured'}"
        )
    if payload["diagnostics"]:
        typer.echo("\nIncomplete/duplicate trial pairs are excluded; inspect `--format json` for diagnostics.")


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
    trial_directory: Path | None = typer.Option(
        None,
        "--trial-dir",
        exists=True,
        file_okay=False,
        help="Required for a fixed benchmark session; rechecks fixtures and acceptance evidence",
    ),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Finish a session with measured quality, retries, elapsed time and token usage."""
    try:
        trial = inspect_authoring_trial(trial_directory) if trial_directory else None
        event = finish_authoring_session(
            workspace,
            session_id,
            outcome=outcome,
            first_attempt_success=_first_attempt_value(first_attempt),
            correction_rounds=correction_rounds,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            docs_used=docs_used,
            trial_integrity_passed=trial["integrity_passed"] if trial else None,
            acceptance_passed=trial["quality_passed"] if trial else None,
            acceptance_results=trial["checks"] if trial else None,
            benchmark_task=trial["benchmark_task"] if trial else None,
            approach=trial["approach"] if trial else None,
            trial_id=trial["trial_id"] if trial else None,
            task_contract_sha256=trial["task_contract_sha256"] if trial else None,
            task_prompt_sha256=trial["task_prompt_sha256"] if trial else None,
            fixture_sha256=trial["fixture_sha256"] if trial else None,
            notes=notes,
        )
        print_json(
            {
                "status": "finished",
                "session_id": event.session_id,
                "outcome": event.outcome,
                "elapsed_seconds": event.elapsed_seconds,
                "token_source": event.token_source,
                "trial_integrity_passed": event.trial_integrity_passed,
                "acceptance_passed": event.acceptance_passed,
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
        help="Validate package metadata/assets and report explicit bridge ownership",
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
                f"{report['stories']} stories · {report['test_declarations']} test declarations · "
                f"{report['package_implemented']} package-owned / "
                f"{report['bridge_implemented']} bridged"
            )
            typer.echo(
                "\nThis check validates package metadata, assets and test declarations; "
                "pytest/E2E executes behavior."
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
    allow_remote: bool = typer.Option(
        False,
        "--allow-remote",
        help="Acknowledge that this unauthenticated Server will accept remote connections",
    ),
) -> None:
    """Open the runtime-native Section, View, Selector and Renderer Gallery."""
    if output is None:
        _require_remote_bind_opt_in(host, allow_remote=allow_remote)
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
    recipe: str | None = typer.Argument(
        None,
        help=(
            "Recipe such as dashboard, view.line, selector.cascader, "
            "dataset-transform.server-python, or interactive-transform.browser-js"
        ),
    ),
    identifier: str = typer.Option("example", "--id", help="Stable id used in generated files"),
    output: Path | None = typer.Option(
        None, "--output", help="Optional directory to materialize the recipe"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing recipe files"),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
    list_recipes: bool = typer.Option(
        False, "--list", help="List every recipe accepted by this installed version"
    ),
) -> None:
    """Print or materialize a strict current-schema authoring recipe."""
    try:
        if output_format not in {"markdown", "json"}:
            raise typer.BadParameter("--format must be markdown or json")
        if list_recipes:
            if output is not None:
                raise typer.BadParameter("--output cannot be used with --list")
            catalog = {
                "schema": "dataviz/scaffold-catalog/v1",
                "recipes": list(scaffold_recipes()),
            }
            if output_format == "json":
                print_json(catalog)
            else:
                typer.echo("# Dataviz scaffold recipes\n")
                for name in catalog["recipes"]:
                    typer.echo(f"- `{name}`")
            return
        if recipe is None:
            raise typer.BadParameter("Provide a recipe, or use --list")
        payload = scaffold_recipe(recipe, identifier)
        if output is not None:
            root = output.resolve()
            try:
                written = transactional_write_texts(
                    root,
                    payload["files"],
                    overwrite=force,
                )
            except (FileExistsError, IsADirectoryError, NotADirectoryError, ValueError) as error:
                raise typer.BadParameter(str(error)) from error
            print_json(
                {
                    "status": "success",
                    "recipe": recipe,
                    "id": identifier,
                    "output": str(root),
                    "files": [str(path) for path in written],
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
    """Measure authoring footprint and, optionally, the real browser Runtime."""
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
            transport = runtime["runtime"].get("transports", {})
            renderers = runtime["runtime"].get("renderers", {})
            typer.echo(
                f"- Browser Runtime: query {runtime['query_ms']} ms; "
                f"report {runtime['report_build_ms']} ms; "
                f"page ready {runtime['page_ready_ms']} ms"
            )
            typer.echo(
                f"- Arrow: {transport.get('arrowRows', 0)} rows / "
                f"{transport.get('arrowBytes', 0)} bytes; "
                f"renderer failures: {renderers.get('failed', 0)}"
            )
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
    output_name: str = typer.Option("main", "--output-name"),
    query_param: list[str] | None = typer.Option(None, "--query-param"),
    output_format: str = typer.Option(
        "json", "--format", help="json, csv, markdown, or text"
    ),
    limit: int = typer.Option(100, "--limit", min=1),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Query one named Source Output without starting a server."""
    try:
        if output_format not in {"json", "csv", "markdown", "text"}:
            raise typer.BadParameter("--format must be json, csv, markdown, or text")
        loaded = load_workspace(workspace)
        reference = parse_output_reference(f"source:{source}/{output_name}")
        result = Executor(loaded).run(
            dashboard,
            query_parameters=parse_params(query_param),
            targets=[reference.canonical],
            refresh=refresh,
        )
        node = result.nodes[reference.node_id]
        artifact = node.outputs.get(reference.output)
        if not artifact:
            print_json(result)
            raise typer.Exit(1)
        store = ArtifactStore(loaded.root, result.run_id)
        value = store.read_value(artifact)
        truncated = False
        if artifact.kind == "table":
            frame = value.head(limit)
            truncated = int(artifact.metadata.get("row_count", 0)) > limit
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
        if output_format == "json":
            print_json(
                {
                    "status": result.status,
                    "run_id": result.run_id,
                    "source": source,
                    "reference": reference.canonical,
                    "query_parameters": result.query_parameters,
                    "schema": artifact.schema_,
                    "row_count": artifact.metadata.get("row_count"),
                    "value": value,
                    "truncated": truncated,
                    "artifact": artifact.model_dump(mode="json", by_alias=True),
                    "node": node.model_dump(mode="json", by_alias=True),
                }
            )
        if result.status == "error":
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
        ..., help="Base Named Output, for example dataset:sales-metrics/trend"
    ),
    query_param: list[str] | None = typer.Option(None, "--query-param"),
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
        if parsed.node_id.startswith("interactive:"):
            raise typer.BadParameter(
                "Interactive Outputs require `dataviz compute`; `dataviz output` only executes the Query DAG"
            )
        result = Executor(loaded).run(
            dashboard,
            query_parameters=parse_params(query_param),
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
                "query_parameters": result.query_parameters,
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
def compute(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    interactive_transform: str = typer.Argument(..., help="Interactive Transform id"),
    run_id: str = typer.Option(..., "--run-id", help="Completed immutable Query Run id"),
    compute_param: list[str] | None = typer.Option(None, "--compute-param"),
    selection: list[str] | None = typer.Option(None, "--selection"),
    output_name: str | None = typer.Option(
        None, "--output-name", help="Named Output to print for non-JSON formats"
    ),
    output_format: str = typer.Option(
        "json", "--format", help="json, csv, markdown, or text"
    ),
    limit: int = typer.Option(100, "--limit", min=1),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Run one server-python Interactive Transform against an existing Query Run."""
    try:
        if output_format not in {"json", "csv", "markdown", "text"}:
            raise typer.BadParameter("--format must be json, csv, markdown, or text")
        loaded = load_workspace(workspace)
        run_result = load_run_result(loaded.root, run_id)
        if run_result.dashboard != dashboard:
            raise typer.BadParameter(
                f"Query Run {run_id} belongs to {run_result.dashboard}, not {dashboard}"
            )
        interaction = InteractionExecutor(loaded).execute(
            run_result,
            interactive_transform,
            compute_parameters=parse_params(compute_param),
            selections=parse_params(selection),
            refresh=refresh,
        )
        if output_format == "json":
            print_json(interaction)
        else:
            if not output_name:
                raise typer.BadParameter("--output-name is required for non-JSON formats")
            reference = f"interactive:{interactive_transform}/{output_name}"
            artifact = interaction.outputs.get(reference)
            if artifact is None:
                raise typer.BadParameter(
                    f"Unknown or unavailable Interactive Output: {reference}"
                )
            value = ArtifactStore(loaded.root, run_id).read_value(artifact)
            if artifact.kind == "table":
                frame = value.head(limit)
                if output_format == "csv":
                    typer.echo(frame.to_csv(index=False), nl=False)
                elif output_format == "markdown":
                    typer.echo(frame.to_markdown(index=False))
                else:
                    typer.echo(frame.to_string(index=False))
            else:
                typer.echo(str(value))
        if interaction.status != "ready":
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command()
def run(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    query_param: list[str] | None = typer.Option(None, "--query-param"),
    target: list[str] | None = typer.Option(
        None, "--target", help="Source/Dataset node or Base Named Output; repeatable"
    ),
    refresh: bool = typer.Option(False, "--refresh"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
) -> None:
    """Execute the immutable Source and Dataset Transform Query DAG."""
    try:
        loaded = load_workspace(workspace)
        result = Executor(loaded).run(
            dashboard,
            query_parameters=parse_params(query_param),
            targets=target,
            refresh=refresh,
        )
        print_json(result)
        if result.status != "ready" and not (allow_partial and result.status == "partial"):
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
    query_param: list[str] | None = typer.Option(None, "--query-param"),
    compute_param: list[str] | None = typer.Option(None, "--compute-param"),
    selection: list[str] | None = typer.Option(None, "--selection"),
    refresh: bool = typer.Option(False, "--refresh"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
) -> None:
    """Execute a dashboard and write a shareable HTML report."""
    try:
        loaded = load_workspace(workspace)
        result = Executor(loaded).run(
            dashboard,
            query_parameters=parse_params(query_param),
            refresh=refresh,
        )
        if result.status != "ready" and not (allow_partial and result.status == "partial"):
            print_json(result)
            raise typer.Exit(1)
        loaded_dashboard = loaded.dashboard(dashboard)
        compute_values = resolve_compute_values(
            loaded_dashboard.definition,
            parse_params(compute_param),
        )
        selection_values = resolve_selection_values(
            loaded_dashboard.definition, parse_params(selection)
        )
        _, interactive_ids = reachable_output_references(loaded_dashboard)
        derived_outputs = {}
        snapshot_interactions: set[str] = {
            transform_id
            for transform_id in interactive_ids
            if loaded_dashboard.interactive_transforms[transform_id][1].export.mode
            == "snapshot"
        }
        browser_snapshot_ids = sorted(
            transform_id
            for transform_id in snapshot_interactions
            if loaded_dashboard.interactive_transforms[transform_id][1].runtime
            in {"browser-js", "browser-python"}
        )
        if browser_snapshot_ids:
            raise ExecutionFailure(
                "CLI report cannot capture an already-rendered browser snapshot",
                details={
                    "code": "browser_snapshot_requires_canvas",
                    "transforms": browser_snapshot_ids,
                    "suggestion": (
                        "Export from the Server page after running the analysis, or use "
                        "export.mode=interactive/unavailable for browser runtimes"
                    ),
                },
            )
        interaction_executor = InteractionExecutor(loaded)
        interaction_results = []
        for transform_id in interactive_ids:
            definition = loaded_dashboard.interactive_transforms[transform_id][1]
            if definition.runtime != "server-python" or definition.export.mode != "snapshot":
                continue
            interaction = interaction_executor.execute(
                result,
                transform_id,
                compute_parameters=compute_values,
                selections=selection_values,
                refresh=refresh,
            )
            interaction_results.append(interaction)
            if interaction.status != "ready":
                print_json(interaction)
                raise typer.Exit(1)
            derived_outputs.update(interaction.outputs)
        path = CanvasRenderer(loaded).write_report(
            loaded_dashboard,
            result,
            output.resolve(),
            compute_parameters=compute_values,
            selections=selection_values,
            derived_outputs=derived_outputs,
            snapshot_interactions=snapshot_interactions,
        )
        manifest_path = path.with_suffix(path.suffix + ".manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print_json(
            {
                "status": "success",
                "run_id": result.run_id,
                "report": str(path),
                "manifest": str(manifest_path),
                "portable_without_network": manifest["portable_without_network"],
                "portability_scope": manifest["portability_scope"],
                "network_dependencies": manifest["network_dependencies"],
                "query_parameters": result.query_parameters,
                "compute_parameters": compute_values,
                "selections": selection_values,
                "snapshot_interactions": [
                    value.interaction_id for value in interaction_results
                ],
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
    allow_remote: bool = typer.Option(
        False,
        "--allow-remote",
        help="Acknowledge that this unauthenticated Server will accept remote connections",
    ),
) -> None:
    """Start the human-facing interactive dashboard server."""
    _require_remote_bind_opt_in(host, allow_remote=allow_remote)
    import uvicorn

    application = create_app(workspace)
    uvicorn.run(application, host=host, port=port)


if __name__ == "__main__":
    app()
