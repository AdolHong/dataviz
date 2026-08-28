from __future__ import annotations

import json
import ipaddress
import os
import platform
import shlex
import shutil
import socket
import statistics
import sys
import threading
import time
from pathlib import Path
from contextlib import contextmanager
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
from dataviz.execution.dependencies import (
    DEPENDENCY_CONTRACT_SCHEMA,
)
from dataviz.execution.interactive import load_run_result
from dataviz.execution.references import parse_output_reference
from dataviz.maintenance import cleanup_workspace_storage
from dataviz.rendering import CanvasRenderer, template_catalog
from dataviz.renderer_contract import run_renderer_contract
from dataviz.schema_docs import CURRENT_SCHEMAS, schema_catalog, schema_model_contract
from dataviz.server import create_app
from dataviz.templates import component_catalog
from dataviz.validation import format_validation_text, validate_preflight
from dataviz.workspace import load_workspace
from dataviz.selection_state import state_from_explicit_values
from dataviz.semantic_validation import validate_dashboard_semantics
from dataviz.workspace.controls import (
    project_selection_values,
    resolve_compute_values,
)


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
    query_parameters: dict[str, Any] | None = None,
    browser_name: str = "chromium",
    repeat: int = 1,
) -> dict[str, Any]:
    """Run an exported Runtime repeatedly and return observable scale metrics."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise typer.BadParameter(
            "--browser-runtime requires the dev extra: uv sync --extra dev"
        ) from error

    if browser_name not in {"chromium", "firefox", "webkit"}:
        raise typer.BadParameter("--browser must be chromium, firefox, or webkit")

    def process_max_rss_bytes() -> int | None:
        try:
            import resource

            value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        except (ImportError, OSError, ValueError):
            return None
        # macOS reports bytes; Linux and the BSDs report KiB.
        return value if sys.platform == "darwin" else value * 1024

    def duration_summary(values: list[float]) -> dict[str, float]:
        return {
            "minimum": round(min(values), 2),
            "median": round(statistics.median(values), 2),
            "maximum": round(max(values), 2),
        }

    query_rss_before = process_max_rss_bytes()
    query_started = time.perf_counter()
    result = Executor(workspace).run(
        dashboard.definition.id,
        query_parameters=query_parameters,
        refresh=True,
    )
    query_ms = (time.perf_counter() - query_started) * 1000
    query_rss_after = process_max_rss_bytes()
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
        report_bytes = report.stat().st_size
        browser_started = time.perf_counter()
        with sync_playwright() as playwright:
            try:
                browser_type = getattr(playwright, browser_name)
                launch_options: dict[str, Any] = {"headless": True}
                if browser_name == "chromium":
                    launch_options["args"] = ["--enable-precise-memory-info"]
                browser = browser_type.launch(**launch_options)
            except Exception as error:
                raise typer.BadParameter(
                    f"{browser_name} is unavailable; run: "
                    f"uv run --no-editable playwright install {browser_name}"
                ) from error
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.add_init_script(
                """(() => {
                  const state = {
                    supported: Boolean(performance.memory),
                    samples: [],
                    timer: null,
                  };
                  state.sample = () => {
                    if (!performance.memory) return null;
                    const value = Number(performance.memory.usedJSHeapSize || 0);
                    state.samples.push(value);
                    return value;
                  };
                  state.stop = () => {
                    clearInterval(state.timer);
                    state.sample();
                  };
                  state.sample();
                  state.timer = setInterval(state.sample, 20);
                  window.addEventListener('pagehide', state.stop, {once:true});
                  window.__datavizBenchmarkMemory = state;
                })();"""
            )
            console_errors: list[str] = []
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            process_rss_samples: list[int] = []
            process_rss_stop = threading.Event()
            process_rss_thread: threading.Thread | None = None
            process_rss_now = None
            process_rss_scope = "Process-tree RSS sampling is unavailable."
            try:
                import psutil

                driver = browser._impl_obj._connection._transport._proc
                driver_process = psutil.Process(driver.pid)

                def process_tree_rss() -> int:
                    processes = [driver_process, *driver_process.children(recursive=True)]
                    total = 0
                    for process in processes:
                        try:
                            total += int(process.memory_info().rss)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    return total

                def sample_process_tree() -> None:
                    while not process_rss_stop.wait(0.02):
                        process_rss_samples.append(process_tree_rss())

                process_rss_now = process_tree_rss
                process_rss_scope = (
                    "Playwright driver plus descendant browser-process RSS; includes workers, "
                    "native Arrow, GPU helpers and browser overhead."
                )
                process_rss_samples.append(process_tree_rss())
                process_rss_thread = threading.Thread(
                    target=sample_process_tree,
                    name="dataviz-browser-rss",
                    daemon=True,
                )
                process_rss_thread.start()
            except (ImportError, AttributeError, OSError):
                pass
            cdp = None
            if browser_name == "chromium":
                cdp = context.new_cdp_session(page)
                cdp.send("HeapProfiler.enable")

            def collect_garbage() -> None:
                if cdp is not None:
                    cdp.send("HeapProfiler.collectGarbage")

            iterations: list[dict[str, Any]] = []
            for index in range(repeat):
                page.goto("about:blank", wait_until="domcontentloaded")
                collect_garbage()
                rss_sample_offset = len(process_rss_samples)
                baseline_process_rss = process_rss_now() if process_rss_now else None
                baseline_heap = page.evaluate(
                    "() => Number(performance.memory?.usedJSHeapSize || 0) || null"
                )
                error_offset = len(console_errors)
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
                memory = page.evaluate(
                    """() => {
                      const state = window.__datavizBenchmarkMemory;
                      state?.stop?.();
                      const samples = state?.samples || [];
                      return {
                        supported:Boolean(state?.supported),
                        sample_count:samples.length,
                        peak_js_heap_bytes:samples.length ? Math.max(...samples) : null,
                        settled_js_heap_bytes:Number(performance.memory?.usedJSHeapSize || 0) || null,
                      };
                    }"""
                )
                collect_garbage()
                memory["active_post_gc_js_heap_bytes"] = page.evaluate(
                    "() => Number(performance.memory?.usedJSHeapSize || 0) || null"
                )
                metrics = page.evaluate(
                    """() => ({
                      runtime: structuredClone(window.datavizRuntime.metrics),
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
                page.evaluate("() => window.datavizRuntime.dispose()")
                created = int(metrics["runtime"]["perspective"]["created"])
                if created:
                    page.wait_for_function(
                        "count => window.datavizRuntime.metrics.perspective.disposed >= count",
                        arg=created,
                        timeout=min(timeout_seconds, 10) * 1000,
                    )
                page.goto("about:blank", wait_until="domcontentloaded")
                collect_garbage()
                released_heap = page.evaluate(
                    "() => Number(performance.memory?.usedJSHeapSize || 0) || null"
                )
                memory.update(
                    {
                        "baseline_js_heap_bytes": baseline_heap,
                        "released_js_heap_bytes": released_heap,
                        "retained_delta_bytes": (
                            released_heap - baseline_heap
                            if released_heap is not None and baseline_heap is not None
                            else None
                        ),
                        "scope": (
                            "Chromium main-renderer JavaScript heap; excludes native Arrow, "
                            "GPU and operating-system process memory."
                            if memory["supported"]
                            else "This browser does not expose performance.memory."
                        ),
                    }
                )
                process_samples = process_rss_samples[rss_sample_offset:]
                current_process_rss = process_rss_now() if process_rss_now else None
                if current_process_rss is not None:
                    process_samples = [*process_samples, current_process_rss]
                process_memory = {
                    "supported": process_rss_now is not None,
                    "sample_count": len(process_samples),
                    "baseline_rss_bytes": baseline_process_rss,
                    "peak_rss_bytes": max(process_samples) if process_samples else None,
                    "released_rss_bytes": current_process_rss,
                    "retained_delta_bytes": (
                        current_process_rss - baseline_process_rss
                        if current_process_rss is not None and baseline_process_rss is not None
                        else None
                    ),
                    "scope": process_rss_scope,
                }
                iterations.append(
                    {
                        "iteration": index + 1,
                        "page_ready_ms": round(page_ready_ms, 2),
                        "console_errors": console_errors[error_offset:],
                        "memory": memory,
                        "browser_process_memory": process_memory,
                        **metrics,
                    }
                )
            process_rss_stop.set()
            if process_rss_thread is not None:
                process_rss_thread.join(timeout=1)
            context.close()
            browser.close()
        browser_ms = (time.perf_counter() - browser_started) * 1000
    page_ready_values = [item["page_ready_ms"] for item in iterations]
    heap_peaks = [
        item["memory"]["peak_js_heap_bytes"]
        for item in iterations
        if item["memory"]["peak_js_heap_bytes"] is not None
    ]
    retained = [
        item["memory"]["retained_delta_bytes"]
        for item in iterations
        if item["memory"]["retained_delta_bytes"] is not None
    ]
    process_peaks = [
        item["browser_process_memory"]["peak_rss_bytes"]
        for item in iterations
        if item["browser_process_memory"]["peak_rss_bytes"] is not None
    ]
    process_retained = [
        item["browser_process_memory"]["retained_delta_bytes"]
        for item in iterations
        if item["browser_process_memory"]["retained_delta_bytes"] is not None
    ]
    process_peak_increases = [
        item["browser_process_memory"]["peak_rss_bytes"]
        - item["browser_process_memory"]["baseline_rss_bytes"]
        for item in iterations
        if item["browser_process_memory"]["peak_rss_bytes"] is not None
        and item["browser_process_memory"]["baseline_rss_bytes"] is not None
    ]
    released_process_rss = [
        item["browser_process_memory"]["released_rss_bytes"]
        for item in iterations
        if item["browser_process_memory"]["released_rss_bytes"] is not None
    ]
    last = iterations[-1]
    return {
        "schema": "dataviz/browser-runtime-benchmark/v3",
        "environment": {
            "dataviz": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "browser": browser_name,
        },
        "query": {
            "parameters": result.query_parameters,
            "duration_ms": round(query_ms, 2),
            "process_max_rss_bytes_before": query_rss_before,
            "process_max_rss_bytes_after": query_rss_after,
            "process_max_rss_increase_bytes": (
                max(0, query_rss_after - query_rss_before)
                if query_rss_after is not None and query_rss_before is not None
                else None
            ),
            "rss_scope": "Peak RSS for the benchmark CLI process; native allocations are included.",
        },
        "report": {
            "build_ms": round(report_ms, 2),
            "html_bytes": report_bytes,
        },
        "browser": {
            "name": browser_name,
            "repeat": repeat,
            "timeout_seconds": timeout_seconds,
            "total_ms": round(browser_ms, 2),
            "page_ready_ms": duration_summary(page_ready_values),
            "peak_js_heap_bytes": max(heap_peaks) if heap_peaks else None,
            "maximum_retained_delta_bytes": max(retained) if retained else None,
            "peak_process_tree_rss_bytes": max(process_peaks) if process_peaks else None,
            "peak_process_tree_increase_bytes": (
                max(process_peak_increases) if process_peak_increases else None
            ),
            "maximum_process_tree_retained_delta_bytes": (
                max(process_retained) if process_retained else None
            ),
            "final_process_tree_retained_delta_bytes": (
                process_retained[-1] if process_retained else None
            ),
            "post_warmup_process_tree_growth_bytes": (
                released_process_rss[-1] - released_process_rss[0]
                if len(released_process_rss) > 1
                else None
            ),
            "iterations": iterations,
        },
        # Last-iteration projections keep common evidence easy to inspect.
        "runtime": last["runtime"],
        "outputs": last["outputs"],
        "repeat_sections": last["repeat_sections"],
        "view_states": last["view_states"],
        "console_errors": console_errors,
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


def _result_detail(value: str) -> str:
    if value not in {"summary", "debug", "full"}:
        raise typer.BadParameter("--detail must be summary, debug, or full")
    return value


def _artifact_result_summary(
    *,
    status: str,
    reference: str,
    artifact,
    value: Any,
    truncated: bool,
    run_id: str,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    schema = artifact.schema_ or []
    columns = [item.get("name") for item in schema if item.get("name")]
    return {
        "schema": "dataviz/cli-result/v1",
        "status": status,
        "run_id": run_id,
        "reference": reference,
        "kind": artifact.kind,
        "rows": artifact.metadata.get("row_count"),
        "columns": columns,
        "duration_ms": duration_ms,
        "preview": value,
        "truncated": truncated,
        "next_actions": [
            "Use --detail debug to inspect bindings and diagnostics.",
            "Use --detail full only when the complete execution envelope is required.",
        ],
    }


def _failed_result_summary(result, reference: str, node=None) -> dict[str, Any]:
    return {
        "schema": "dataviz/cli-result/v1",
        "status": result.status,
        "run_id": result.run_id,
        "reference": reference,
        "error": node.error if node else {"code": "output_unavailable", "message": "Named Output was not produced"},
        "next_actions": [
            "Run dataviz validate WORKSPACE --dashboard DASHBOARD --format json.",
            "Repeat with --detail debug to inspect the failing node.",
        ],
    }


@contextmanager
def _visual_server(workspace: Path):
    import uvicorn

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(workspace, watch=False),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("Visual-check Server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _visual_page_diagnostics(page, *, target: str, viewport: str) -> list[dict[str, Any]]:
    return page.evaluate(
        """({target, viewport}) => {
          const diagnostics = [];
          const add = (level, code, message, details = {}) => diagnostics.push({
            level, code, message, target, viewport, details,
          });
          const doc = document.documentElement;
          if (doc.scrollWidth > doc.clientWidth + 2) add(
            'error', 'visual_horizontal_overflow',
            `Document is ${doc.scrollWidth - doc.clientWidth}px wider than the viewport`,
            {scroll_width:doc.scrollWidth, client_width:doc.clientWidth},
          );
          const views = [...document.querySelectorAll('.dv-view')].filter(node => {
            const style = getComputedStyle(node);
            return style.display !== 'none' && style.visibility !== 'hidden';
          });
          views.forEach(node => {
            const rect = node.getBoundingClientRect();
            const id = node.dataset.viewId || 'unknown';
            if (rect.width < 2 || rect.height < 2) add(
              'error', 'visual_zero_size_view', `View ${id} has no usable geometry`,
              {view:id, width:rect.width, height:rect.height},
            );
            if (node.dataset.viewStatus === 'loading') add(
              'error', 'visual_permanent_loading', `View ${id} is still Loading`, {view:id},
            );
          });
          for (let leftIndex = 0; leftIndex < views.length; leftIndex += 1) {
            const left = views[leftIndex];
            const a = left.getBoundingClientRect();
            for (let rightIndex = leftIndex + 1; rightIndex < views.length; rightIndex += 1) {
              const right = views[rightIndex];
              if (left.contains(right) || right.contains(left)) continue;
              const b = right.getBoundingClientRect();
              const width = Math.min(a.right, b.right) - Math.max(a.left, b.left);
              const height = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
              if (width > 4 && height > 4) add(
                'error', 'visual_view_overlap',
                `Views ${left.dataset.viewId} and ${right.dataset.viewId} overlap`,
                {views:[left.dataset.viewId, right.dataset.viewId], width, height},
              );
            }
          }
          document.querySelectorAll('[data-dv-control-panel]:not([hidden])').forEach(panel => {
            const rect = panel.getBoundingClientRect();
            if (rect.left < -2 || rect.right > innerWidth + 2) add(
              'error', 'visual_control_panel_clipped', 'A Control panel is clipped horizontally',
              {left:rect.left, right:rect.right, viewport_width:innerWidth},
            );
          });
          document.querySelectorAll('details[data-runtime-popover], details.dv-context-controls').forEach(owner => {
            const wasOpen = owner.open;
            const overlay = owner._datavizOverlayRecord?.api;
            if (overlay) overlay.open();
            else owner.open = true;
            const panel = owner.querySelector('.dv-runtime-popover, .dv-context-controls__panel');
            if (panel) {
              const rect = panel.getBoundingClientRect();
              if (rect.left < -2 || rect.right > innerWidth + 2 || rect.top < -2) add(
                'error', 'visual_overlay_clipped', 'A scoped Control overlay is outside the viewport',
                {left:rect.left, right:rect.right, top:rect.top, viewport_width:innerWidth},
              );
            }
            if (overlay && !wasOpen) overlay.close();
            else owner.open = wasOpen;
          });
          document.querySelectorAll('.dv-view--perspective').forEach(node => {
            const viewer = node.querySelector('perspective-viewer');
            if (!viewer) return;
            const body = node.querySelector('.dv-view-body');
            const height = viewer.getBoundingClientRect().height;
            if (height < 180 || (body && height < body.clientHeight * .65)) add(
              'error', 'visual_perspective_height',
              `Perspective View ${node.dataset.viewId || 'unknown'} has insufficient usable height`,
              {view:node.dataset.viewId, viewer_height:height, body_height:body?.clientHeight || null},
            );
          });
          return diagnostics;
        }""",
        {"target": target, "viewport": viewport},
    )


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
        ".gitignore": "auth/adapters.local.yaml\n.dataviz/\nshared_caches/\ndist/\n",
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
        "dashboards/hello/dashboard.yaml": """schema: dataviz/dashboard/v8
kind: dashboard
id: hello
title: Hello dashboard
description: A minimal self-contained canvas
controls:
  - id: category
    kind: selection
    type: multiple_select
    value_type: text
    default: [A, B, C]
    options:
      mode: static
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
  preset: business
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
    topic: str | None = typer.Argument(
        None,
        help="Topic, for example quickstart, design-language, charts, or troubleshooting",
    ),
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
    typer.echo("Before custom Presentation/CSS, read `dataviz docs design-language`.\n")
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


@app.command("visual-check")
def visual_check(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    browser: str = typer.Option("chromium", "--browser"),
    viewport: list[str] | None = typer.Option(
        None, "--viewport", help="Repeat WIDTHxHEIGHT; defaults to desktop and narrow"
    ),
    target: str = typer.Option("both", "--target", help="report, server, or both"),
    output: Path | None = typer.Option(None, "--output"),
    timeout_seconds: float = typer.Option(20.0, "--timeout", min=1),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Render in a real browser and report objective geometry/runtime defects."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise typer.BadParameter("visual-check requires: uv sync --extra dev") from error
    if browser not in {"chromium", "firefox", "webkit"}:
        raise typer.BadParameter("--browser must be chromium, firefox, or webkit")
    if target not in {"report", "server", "both"}:
        raise typer.BadParameter("--target must be report, server, or both")
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be text or json")
    viewports = viewport or ["1440x900", "390x844"]
    parsed_viewports: list[tuple[str, int, int]] = []
    for value in viewports:
        try:
            width, height = (int(item) for item in value.lower().split("x", 1))
        except (TypeError, ValueError) as error:
            raise typer.BadParameter(f"Invalid viewport {value}; use WIDTHxHEIGHT") from error
        if width < 240 or height < 240:
            raise typer.BadParameter("Viewport dimensions must be at least 240px")
        parsed_viewports.append((value, width, height))
    try:
        loaded = load_workspace(workspace)
        loaded_dashboard = loaded.dashboard(dashboard)
        output_root = (output or workspace / ".dataviz" / "visual-check" / dashboard).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        result = Executor(loaded).run(dashboard, refresh=True)
        if result.status != "ready":
            print_json(result)
            raise typer.Exit(1)
        report = CanvasRenderer(loaded).write_report(
            loaded_dashboard,
            result,
            output_root / "report.html",
        )
        diagnostics: list[dict[str, Any]] = []
        screenshots: list[str] = []
        with sync_playwright() as playwright:
            try:
                browser_instance = getattr(playwright, browser).launch(headless=True)
            except Exception as error:
                raise typer.BadParameter(
                    f"{browser} is unavailable; run: playwright install {browser}"
                ) from error

            def inspect_url(url: str, mode: str, *, server_shell: bool = False) -> None:
                for _viewport_name, width, height in parsed_viewports:
                    context = browser_instance.new_context(viewport={"width": width, "height": height})
                    page = context.new_page()
                    console_errors: list[str] = []
                    def capture_console_error(message, errors=console_errors):
                        if message.type == "error":
                            errors.append(message.text)

                    page.on("console", capture_console_error)
                    page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_seconds * 1000))
                    canvas_page = page
                    if server_shell:
                        dashboard_item = page.locator(
                            f'[data-nav-type="dashboard"][data-id="{dashboard}"]'
                        )
                        dashboard_item.click()
                        page.locator("#run-button").click()
                        page.locator("#query-diagnostics-label").wait_for(
                            state="visible", timeout=int(timeout_seconds * 1000)
                        )
                        page.wait_for_function(
                            "() => document.querySelector('#query-diagnostics-label')?.textContent?.trim() === 'Ready'",
                            timeout=int(timeout_seconds * 1000),
                        )
                        frame_handle = page.locator("#canvas-frame").element_handle()
                        canvas_page = frame_handle.content_frame() if frame_handle else page
                    try:
                        canvas_page.wait_for_function(
                            "() => [...document.querySelectorAll('.dv-view')].every(node => node.dataset.viewStatus !== 'loading')",
                            timeout=int(timeout_seconds * 1000),
                        )
                    except Exception:
                        pass
                    viewport_label = f"{width}x{height}"
                    diagnostics.extend(
                        _visual_page_diagnostics(
                            canvas_page,
                            target=mode,
                            viewport=viewport_label,
                        )
                    )
                    diagnostics.extend(
                        {
                            "level": "error",
                            "code": "visual_console_error",
                            "message": message,
                            "target": mode,
                            "viewport": viewport_label,
                            "details": {},
                        }
                        for message in console_errors
                    )
                    screenshot = output_root / f"{mode}-{browser}-{width}x{height}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    screenshots.append(str(screenshot))
                    context.close()

            if target in {"report", "both"}:
                inspect_url(report.as_uri(), "report")
            if target in {"server", "both"}:
                with _visual_server(workspace) as base_url:
                    inspect_url(base_url, "server", server_shell=True)
            browser_instance.close()
        payload = {
            "schema": "dataviz/visual-check/v1",
            "status": "failed" if any(item["level"] == "error" for item in diagnostics) else "passed",
            "dashboard": dashboard,
            "browser": browser,
            "targets": [target] if target != "both" else ["report", "server"],
            "viewports": [item[0] for item in parsed_viewports],
            "diagnostics": diagnostics,
            "screenshots": screenshots,
        }
        atomic_write_text(
            output_root / "visual-check.json",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        if output_format == "json":
            print_json(payload)
        else:
            typer.echo(
                f"Visual check {payload['status']}: {dashboard} · {browser} · "
                f"{len(diagnostics)} diagnostic(s)"
            )
            for item in diagnostics:
                typer.echo(
                    f"- {item['level'].upper()} {item['code']} "
                    f"[{item['target']} {item['viewport']}]: {item['message']}"
                )
            typer.echo(f"Artifacts: {output_root}")
        if payload["status"] == "failed":
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command("version")
def version(output_format: str = typer.Option("json", "--format", help="json or text")) -> None:
    """Show package, DSL, Component Registry and browser protocol versions."""
    if output_format not in {"json", "text"}:
        raise typer.BadParameter("--format must be json or text")
    payload = {
        "package": "ai-dataviz",
        "version": __version__,
        "dsl": CURRENT_SCHEMAS,
        "dependency_contract": DEPENDENCY_CONTRACT_SCHEMA,
        "component_registry": template_catalog()["component_registry_version"],
        "runtime_protocol": template_catalog()["runtime_protocol"],
        "workspace_change_protocol": "dataviz/workspace-change/v1",
    }
    if output_format == "json":
        print_json(payload)
    else:
        typer.echo(
            f"ai-dataviz {__version__} · "
            f"{payload['dependency_contract']} · {payload['runtime_protocol']} · "
            f"components {payload['component_registry']}"
        )


@app.command("frontend-adapters")
def frontend_adapters(
    name: str | None = typer.Argument(None, help="Adapter id, for example web-component"),
    output: Path | None = typer.Option(
        None, "--output", help="Copy an exportable reference Adapter to this file"
    ),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Inspect frontend implementations that consume dataviz/runtime/v5."""
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
    name: str | None = typer.Argument(None, help="Component name, for example control.cascader"),
    category: str | None = typer.Option(
        None,
        "--category",
        help="Filter by data-entry, view, section, layout, theme, renderer, runtime, data, or presentation",
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
    watch: bool = typer.Option(
        True,
        "--watch/--no-watch",
        help="Watch Workspace files and hot-reload open dashboards",
    ),
) -> None:
    """Open the runtime-native Data Entry, Section, View and Renderer Gallery."""
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

            uvicorn.run(create_app(gallery_root, watch=watch), host=host, port=port)
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


@app.command("dependencies")
def dependencies_command(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Explain the compiled Query, Control, Interactive and View dependency graph."""
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be text or json")
    try:
        loaded = load_workspace(workspace)
        item = loaded.dashboard(dashboard)
        contract = item.dependency_contract
        payload = contract.as_dict()
        if output_format == "json":
            print_json(payload)
            return
        typer.echo(f"# Dashboard dependencies · {item.canvas_name}\n")
        typer.echo("Initialization: Base Outputs → option domains → canonical Controls → Views → Interactive Transforms\n")
        typer.echo("## Query DAG\n")
        for node_id in contract.query_order:
            dependencies = ", ".join(contract.query_dependencies[node_id]) or "none"
            inputs = ", ".join(
                f"{alias}={reference}"
                for alias, reference in contract.data_inputs[node_id].items()
            ) or "none"
            parameters = ", ".join(
                f"{alias}←{binding['parameter']}"
                + (f".{binding['part']}" if binding.get('part') else "")
                for alias, binding in contract.parameter_inputs[node_id].items()
            ) or "none"
            views = ", ".join(
                contract.query_node_downstream_views[node_id]
            ) or "none"
            option_controls = ", ".join(
                contract.query_node_option_controls[node_id]
            ) or "none"
            typer.echo(
                f"- `{node_id}` ← nodes: {dependencies}; inputs: {inputs}; "
                f"Query Parameters: {parameters}; downstream Views: {views}; "
                f"option Controls: {option_controls}"
            )
        typer.echo("\n## Query Parameters\n")
        if not contract.query_parameters:
            typer.echo("- none")
        for key, dependency in contract.query_parameters.items():
            query_nodes = ", ".join(dependency.affected_query_nodes) or "none"
            interactive = ", ".join(
                dependency.affected_interactive_transforms
            ) or "none"
            option_controls = ", ".join(
                dependency.affected_option_controls
            ) or "none"
            views = ", ".join(dependency.affected_views) or "none"
            typer.echo(
                f"- `{key}` → Query nodes: {query_nodes}; "
                f"Interactive Transforms: {interactive}; "
                f"option Controls: {option_controls}; Views: {views}"
            )
        typer.echo("\n## Interactive DAG\n")
        if not contract.reachable_interactive_order:
            typer.echo("- none")
        for transform_id in contract.reachable_interactive_order:
            dependencies = ", ".join(
                contract.interactive_dependencies[transform_id]
            ) or "Base Outputs"
            inputs = ", ".join(
                f"{alias}={reference}"
                for alias, reference in contract.interactive_inputs[
                    transform_id
                ].items()
            ) or "none"
            selections = ", ".join(
                f"{alias}={key}"
                for alias, key in contract.interactive_selection_inputs[
                    transform_id
                ].items()
            ) or "none"
            computes = ", ".join(
                f"{alias}={key}"
                for alias, key in contract.interactive_compute_inputs[
                    transform_id
                ].items()
            ) or "none"
            views = ", ".join(contract.transform_downstream_views[transform_id]) or "none"
            typer.echo(
                f"- `{transform_id}` ({contract.interactive_runtimes[transform_id]}) "
                f"← nodes: {dependencies}; inputs: {inputs}; "
                f"Selections: {selections}; Compute: {computes}; "
                f"downstream Views: {views}"
            )
        typer.echo("\n## Controls\n")
        if not contract.controls:
            typer.echo("- none")
        for key, dependency in contract.controls.items():
            scope = ", ".join(dependency.scope_views) or "none"
            direct = ", ".join(dependency.direct_views) or "none"
            runtime_checked = ", ".join(dependency.runtime_checked_views) or "none"
            transforms = ", ".join(dependency.transform_consumers) or "none"
            derived = ", ".join(dependency.derived_views) or "none"
            direct_dependencies = ", ".join(dependency.depends_on) or "none"
            ancestors = ", ".join(dependency.dependency_ancestors) or "none"
            typer.echo(
                f"- `{key}` ({dependency.kind}) · scope: {scope}; "
                f"direct data Views: {direct} (runtime field check: {runtime_checked}); "
                f"depends on: {direct_dependencies}; effective ancestors: {ancestors}; "
                f"Transforms: {transforms}; "
                f"derived Views: {derived}"
            )
    except Exception as exc:
        handle_error(exc)


@app.command("inspect-layout")
def inspect_layout(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Print the one compiled Layout Contract without starting a browser."""
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be text or json")
    try:
        loaded = load_workspace(workspace)
        item = loaded.dashboard(dashboard)
        contract = item.layout_contract.as_dict()
        semantic = [
            diagnostic.as_dict()
            for diagnostic in validate_dashboard_semantics(item)
            if diagnostic.code.startswith(("layout_", "semantic_"))
        ]
        payload = {
            "schema": "dataviz/layout-inspection/v1",
            "dashboard": dashboard,
            "layout": contract,
            "diagnostics": semantic,
        }
        if output_format == "json":
            print_json(payload)
            return
        typer.echo(f"# Dashboard layout · {item.canvas_name}\n")
        typer.echo(f"Mode: {contract['mode']} · {contract['columns']} columns · gap {contract['gap']}px")
        if contract["mode"] == "custom":
            typer.echo("\nCustom Canvas boundary")
            typer.echo("- Sections: " + (", ".join(contract["mount_points"]["sections"]) or "none"))
            typer.echo("- Views: " + (", ".join(contract["mount_points"]["views"]) or "none"))
        for section in contract["sections"]:
            typer.echo(
                f"\n## {section['id']} · {section['template']} · {section['columns']} columns"
            )
            placements = {item["view"]: item for item in section["placements"]}
            for row in section["rows"]:
                cells = " | ".join(
                    f"{view} span={placements[view]['span']} "
                    f"({placements[view]['source']})"
                    for view in row["views"]
                )
                typer.echo(f"- row {row['index'] + 1}: {cells}")
        if semantic:
            typer.echo("\nDiagnostics")
            for diagnostic in semantic:
                typer.echo(
                    f"- [{diagnostic['level'].upper()}] {diagnostic['code']}: "
                    f"{diagnostic['message']}"
                )
    except Exception as exc:
        handle_error(exc)


@app.command()
def scaffold(
    recipe: str | None = typer.Argument(
        None,
        help=(
            "Recipe such as dashboard, view.line, control.cascader, "
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
        help="Also execute the exported page in a real browser and measure Runtime scale",
    ),
    query_param: list[str] | None = typer.Option(
        None,
        "--query-param",
        help="Query Parameter override as name=value; repeat for multiple values",
    ),
    browser: str = typer.Option(
        "chromium",
        "--browser",
        help="Browser Runtime engine: chromium, firefox, or webkit",
    ),
    repeat: int = typer.Option(
        1,
        "--repeat",
        min=1,
        max=20,
        help="Reload and dispose the same exported page this many times",
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
                query_parameters=parse_params(query_param),
                browser_name=browser,
                repeat=repeat,
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
                f"- Browser Runtime ({runtime['browser']['name']}): "
                f"query {runtime['query']['duration_ms']} ms; "
                f"report {runtime['report']['build_ms']} ms; "
                f"page ready median {runtime['browser']['page_ready_ms']['median']} ms"
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
                f"- Peak Chromium JS heap: "
                f"{runtime['browser']['peak_js_heap_bytes'] or 'unavailable'} bytes; "
                f"max retained delta: "
                f"{runtime['browser']['maximum_retained_delta_bytes'] or 'unavailable'} bytes"
            )
            typer.echo(
                f"- Browser process-tree peak increase: "
                f"{runtime['browser']['peak_process_tree_increase_bytes'] or 'unavailable'} bytes; "
                f"final retained delta: "
                f"{runtime['browser']['final_process_tree_retained_delta_bytes'] or 0} bytes"
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
    detail: str = typer.Option("summary", "--detail", help="summary, debug, or full"),
) -> None:
    """Query one named Source Output without starting a server."""
    try:
        if output_format not in {"json", "csv", "markdown", "text"}:
            raise typer.BadParameter("--format must be json, csv, markdown, or text")
        detail = _result_detail(detail)
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
            print_json(
                result if detail == "full" else _failed_result_summary(result, reference.canonical, node)
            )
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
            summary = _artifact_result_summary(
                status=result.status,
                reference=reference.canonical,
                artifact=artifact,
                value=value,
                truncated=truncated,
                run_id=result.run_id,
                duration_ms=node.duration_ms,
            )
            if detail == "debug":
                summary.update(
                    query_parameters=result.query_parameters,
                    artifact=artifact.model_dump(mode="json", by_alias=True),
                    node=node.model_dump(mode="json", by_alias=True),
                )
            print_json(
                result.model_dump(mode="json", by_alias=True)
                | {"value": value, "reference": reference.canonical}
                if detail == "full"
                else summary
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
    detail: str = typer.Option("summary", "--detail", help="summary, debug, or full"),
) -> None:
    """Execute the dependency closure and inspect one canonical Named Output."""
    try:
        if output_format not in {"json", "csv", "markdown", "text"}:
            raise typer.BadParameter("--format must be json, csv, markdown, or text")
        detail = _result_detail(detail)
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
            node = result.nodes.get(parsed.node_id)
            print_json(
                result if detail == "full" else _failed_result_summary(result, canonical, node)
            )
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
        truncated = artifact.kind == "table" and int(artifact.metadata.get("row_count", 0)) > limit
        node = result.nodes.get(parsed.node_id)
        summary = _artifact_result_summary(
            status=result.status,
            reference=canonical,
            artifact=artifact,
            value=value,
            truncated=truncated,
            run_id=result.run_id,
            duration_ms=node.duration_ms if node else None,
        )
        if detail == "debug":
            summary.update(
                query_parameters=result.query_parameters,
                artifact=artifact.model_dump(mode="json", by_alias=True),
                node=node.model_dump(mode="json", by_alias=True) if node else None,
            )
        print_json(
            result.model_dump(mode="json", by_alias=True)
            | {"value": value, "reference": canonical}
            if detail == "full"
            else summary
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
    detail: str = typer.Option("summary", "--detail", help="summary, debug, or full"),
) -> None:
    """Run one server-python Interactive Transform against an existing Query Run."""
    try:
        if output_format not in {"json", "csv", "markdown", "text"}:
            raise typer.BadParameter("--format must be json, csv, markdown, or text")
        detail = _result_detail(detail)
        loaded = load_workspace(workspace)
        run_result = load_run_result(loaded.root, run_id)
        if run_result.dashboard != dashboard:
            raise typer.BadParameter(
                f"Query Run {run_id} belongs to {run_result.dashboard}, not {dashboard}"
            )
        loaded_dashboard = loaded.dashboard(dashboard)
        selection_state = state_from_explicit_values(
            loaded_dashboard.definition,
            parse_params(selection),
        )
        interaction = InteractionExecutor(loaded).execute(
            run_result,
            interactive_transform,
            compute_parameters=parse_params(compute_param),
            selection_state=selection_state,
            refresh=refresh,
        )
        if output_format == "json":
            if detail == "full":
                print_json(interaction)
            else:
                output_summaries = []
                store = ArtifactStore(loaded.root, run_id)
                for reference, artifact in interaction.outputs.items():
                    preview = artifact.preview
                    if preview is None:
                        raw = store.read_value(artifact)
                        if artifact.kind == "table":
                            preview = json.loads(raw.head(limit).to_json(orient="records", date_format="iso"))
                        else:
                            preview = raw
                    output_summaries.append(
                        _artifact_result_summary(
                            status=interaction.status,
                            reference=reference,
                            artifact=artifact,
                            value=preview,
                            truncated=(
                                artifact.kind == "table"
                                and int(artifact.metadata.get("row_count", 0)) > limit
                            ),
                            run_id=run_id,
                            duration_ms=interaction.nodes.get(interactive_transform).duration_ms
                            if interaction.nodes.get(interactive_transform)
                            else None,
                        )
                    )
                payload = {
                    "schema": "dataviz/cli-result/v1",
                    "status": interaction.status,
                    "run_id": run_id,
                    "interaction_id": interaction.interaction_id,
                    "target": interactive_transform,
                    "outputs": output_summaries,
                }
                if detail == "debug":
                    payload.update(
                        compute_parameters=interaction.compute_parameters,
                        selection_state=interaction.selection_state,
                        nodes={
                            key: value.model_dump(mode="json", by_alias=True)
                            for key, value in interaction.nodes.items()
                        },
                    )
                print_json(payload)
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
        resolved_selection_state = state_from_explicit_values(
            loaded_dashboard.definition,
            parse_params(selection),
            phase="canvas-hydration",
        )
        selection_values = project_selection_values(
            loaded_dashboard.definition,
            resolved_selection_state,
        )
        interactive_ids = loaded_dashboard.dependency_contract.reachable_interactive_order
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
                selection_state=resolved_selection_state,
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
            selection_state=resolved_selection_state,
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
                "selection_state": resolved_selection_state,
                "selection_values": selection_values,
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
    watch: bool = typer.Option(
        True,
        "--watch/--no-watch",
        help="Watch Workspace files and hot-reload open dashboards",
    ),
) -> None:
    """Start the human-facing interactive dashboard server."""
    _require_remote_bind_opt_in(host, allow_remote=allow_remote)
    import uvicorn

    application = create_app(workspace, watch=watch)
    uvicorn.run(application, host=host, port=port)


if __name__ == "__main__":
    app()
