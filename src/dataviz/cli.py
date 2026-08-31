from __future__ import annotations

import json
import hashlib
import ipaddress
import os
import platform
import re
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
import click
import pandas as pd

from dataviz import __version__
from dataviz.analysis import (
    build_promotion_preview,
    create_analysis_evidence,
    ensure_analysis_catalog,
    inspect_analysis_closure,
    load_analysis_evidence,
    load_promotion_proposal,
    validate_analysis_catalog_producer,
    validate_analysis_describe_producer,
    validate_analysis_result_producer,
)
from dataviz.analysis.parameter_options import ParameterOptionsStore
from dataviz.analysis.results import AnalysisResultStore, result_manifest_hash
from dataviz.analysis.runner import (
    RunRequest,
    analysis_artifact_binding,
    analysis_artifact_payload,
    analysis_artifact_value,
    analysis_entry_summary,
    run_analysis,
    seal_analysis_result,
)
from dataviz.authoring import (
    build_context_payload,
    scaffold_catalog,
    scaffold_recipe,
)
from dataviz.artifacts import ArtifactStore
from dataviz.components import component_story_catalog, validate_component_packages
from dataviz.errors import DatavizError, ExecutionFailure
from dataviz.frontend_adapters import frontend_adapter_catalog, frontend_adapter_source
from dataviz.filesystem import (
    atomic_copy_file,
    atomic_write_text,
    sha256_file,
    transactional_write_texts,
)
from dataviz.documentation import (
    DOC_CATALOG_SCHEMA,
    DOC_PATHS,
    DOC_TOPICS,
    authoring_route_catalog,
    docs_catalog,
    resolve_authoring_route,
    resolve_doc_topic,
)
from dataviz.execution import Executor, InteractionExecutor
from dataviz.execution.dependencies import (
    DEPENDENCY_CONTRACT_SCHEMA,
)
from dataviz.execution.parameter_domains import resolve_parameter_domains
from dataviz.maintenance import cleanup_workspace_storage
from dataviz.plotly_runtime import PLOTLY_JS_VERSION
from dataviz.protocols import (
    ANALYSIS_CATALOG_SCHEMA,
    ANALYSIS_DESCRIBE_SCHEMA,
    ANALYSIS_RESULT_SCHEMA,
    CURRENT_PROTOCOL_SCHEMAS,
    WORKSPACE_CHANGE_SCHEMA,
)
from dataviz.rendering import CanvasRenderer, template_catalog
from dataviz.state_snapshot import (
    applied_control_state_for_consumers,
    applied_revisions_for_consumers,
    normalize_consumer_revisions,
)
from dataviz.renderer_contract import run_renderer_contract
from dataviz.schema_docs import CURRENT_SCHEMAS, schema_catalog, schema_model_contract
from dataviz.server import create_app
from dataviz.templates import component_catalog
from dataviz.target_reference import parse_target_reference
from dataviz.validation import format_validation_text, validate_preflight
from dataviz.workspace import load_workspace
from dataviz.input_state import state_from_values
from dataviz.semantic_validation import validate_dashboard_semantics


app = typer.Typer(
    name="dataviz",
    help="Workspace-first data dashboards for humans and AI.",
    epilog="AI start here: dataviz docs quickstart",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
catalog_app = typer.Typer(
    name="catalog",
    help="Discover reusable Dashboard data contracts without executing them.",
    no_args_is_help=True,
)
result_app = typer.Typer(
    name="result",
    help="List, read, inspect, and export immutable Results without re-running data.",
    no_args_is_help=True,
)
evidence_app = typer.Typer(
    name="evidence",
    help="Turn immutable Results into reviewable analysis evidence.",
    no_args_is_help=True,
)
inspect_app = typer.Typer(
    name="inspect",
    help="Inspect compiled Dashboard context, dependencies, and layout.",
    no_args_is_help=True,
)
components_app = typer.Typer(
    name="components",
    help="Inspect, validate, and preview Component Packages.",
    no_args_is_help=True,
)
renderer_app = typer.Typer(
    name="renderer",
    help="Develop and verify Custom Renderers.",
    no_args_is_help=True,
)
benchmark_app = typer.Typer(
    name="benchmark",
    help="Measure observable Dataviz runtime performance.",
    no_args_is_help=True,
)
parameters_app = typer.Typer(
    name="parameters",
    help=(
        "Optionally inspect live Query Parameter candidates; data execution never "
        "depends on this discovery step."
    ),
    no_args_is_help=True,
)
app.add_typer(catalog_app, name="catalog")
app.add_typer(result_app, name="result")
app.add_typer(evidence_app, name="evidence")
app.add_typer(inspect_app, name="inspect")
app.add_typer(components_app, name="components")
app.add_typer(renderer_app, name="renderer")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(parameters_app, name="parameters")
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
    context = click.get_current_context(silent=True)
    command_path = f" {context.command_path} " if context else ""
    is_data_command = any(
        marker in command_path
        for marker in (" catalog ", " result ", " evidence ", " run ")
    )
    if is_data_command:
        if not error.get("code"):
            error["code"] = (
                "analysis_argument_invalid"
                if isinstance(exc, typer.BadParameter)
                else "analysis_internal_error"
            )
        print_json(
            validate_analysis_result_producer(
                {
                    "schema": ANALYSIS_RESULT_SCHEMA,
                    "status": "failed",
                    "error": error,
                    "next_actions": [
                        "dataviz catalog --help",
                        "dataviz run --help",
                    ],
                }
            )
        )
        raise typer.Exit(1)
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

Build and verify the Dashboard:

```bash
dataviz docs quickstart
dataviz validate . --strict
dataviz inspect dependencies . hello
dataviz report . hello --output report.html
```

Explore and execute its reusable data contract:

```bash
dataviz catalog search . \"sample|category\"
dataviz catalog describe . 'hello::source:data/main'
dataviz run . 'hello::source:data/main'
```
""",
        "dashboards/hello/dashboard.yaml": """schema: dataviz/dashboard/v13
kind: dashboard
id: hello
title: Hello dashboard
description: A minimal self-contained canvas
controls:
  - id: category
    type: multiple_select
    value_type: text
    initial: {mode: values, values: [A, B, C]}
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
    outputs:
      main:
        kind: table
        semantics:
          visibility: public
          title: Sample category values
          purpose: Compare the sample value for each category.
          grain: One row per category.
          caveats: [Demonstration data only.]
views:
  - id: summary
    title: Sample values
    input: source:data/main
    template: bar
    x: category
    y: value
    aggregate: sum
    control_inputs:
      category: {mode: filter, control: dashboard.category, field: category, inputs: [main], empty: match_none}
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


@app.command("tree")
def tree_workspace(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Show the physical Workspace and Dashboard hierarchy."""
    try:
        if output_format not in {"text", "json"}:
            raise typer.BadParameter("--format must be text or json")
        loaded = load_workspace(workspace)
        entries = [
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
                    list(entry.dashboard.dataset_transforms) if entry.dashboard else []
                ),
                "interactive_transforms": (
                    list(entry.dashboard.interactive_transforms) if entry.dashboard else []
                ),
                "views": list(entry.dashboard.views) if entry.dashboard else [],
            }
            for entry in loaded.catalog
        ]
        payload = {
            "schema": "dataviz/workspace-tree/v1",
            "workspace": loaded.definition.model_dump(mode="json", by_alias=True),
            "dashboards": entries,
        }
        if output_format == "json":
            print_json(payload)
            return
        typer.echo(f"{loaded.root.name}/")
        for index, entry in enumerate(entries):
            branch = "└──" if index == len(entries) - 1 else "├──"
            status = "" if entry["status"] == "ready" else f" [{entry['status']}]"
            typer.echo(f"{branch} {entry['logical_path']}{status}")
            details = [
                ("sources", entry["sources"]),
                ("datasets", entry["dataset_transforms"]),
                ("interactive", entry["interactive_transforms"]),
                ("views", entry["views"]),
            ]
            continuation = "    " if index == len(entries) - 1 else "│   "
            nonempty = [(label, values) for label, values in details if values]
            for detail_index, (label, values) in enumerate(nonempty):
                detail_branch = "└──" if detail_index == len(nonempty) - 1 else "├──"
                typer.echo(
                    f"{continuation}{detail_branch} {label}: " + ", ".join(values)
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


def _doc_fence_language(key: str) -> str:
    normalized = key.casefold()
    if "css" in normalized:
        return "css"
    if any(token in normalized for token in ("javascript", "browser_js", "service_example")):
        return "javascript"
    if "sql" in normalized:
        return "sql"
    return "yaml"


def _print_doc_section(key: str, value: Any, *, level: int = 2) -> None:
    typer.echo(f"{'#' * level} {_doc_heading(key)}\n")
    if isinstance(value, str):
        if "\n" in value:
            typer.echo(f"```{_doc_fence_language(key)}")
            typer.echo(value.rstrip())
            typer.echo("```\n")
        else:
            typer.echo(f"{value}\n")
        return
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        for item in value:
            typer.echo(f"- {item}")
        typer.echo()
        return
    if isinstance(value, dict) and any(
        isinstance(item, str) and "\n" in item for item in value.values()
    ):
        for nested_key, nested_value in value.items():
            _print_doc_section(nested_key, nested_value, level=level + 1)
        return
    typer.echo("```yaml")
    typer.echo(yaml.safe_dump(value, allow_unicode=True, sort_keys=False).rstrip())
    typer.echo("```\n")


def _print_doc_topic(name: str, definition: dict[str, Any]) -> None:
    typer.echo(f"# Dataviz docs · {name}\n")
    typer.echo(f"{definition['summary']}\n")
    for key, value in definition.items():
        if key == "summary":
            continue
        _print_doc_section(key, value)


def _print_authoring_route(payload: dict[str, Any]) -> None:
    typer.echo(f"# Dataviz authoring route · {payload['task']}\n")
    typer.echo(f"{payload['summary']}\n")
    typer.echo(f"Concept closure: {' → '.join(payload['concepts'])}\n")
    for identifier, document in payload["documents"].items():
        typer.echo(f"## {identifier}\n")
        typer.echo(f"{document['purpose']}\n")
        typer.echo(f"Path: {document['path']}\n")
        for step in document["steps"]:
            typer.echo(f"- {step}")
        typer.echo()
        for key in (
            "minimal_example",
            "allowed_fields",
            "common_errors",
            "validation_commands",
        ):
            if key not in document:
                continue
            typer.echo(f"### {_doc_heading(key)}\n")
            value = document[key]
            if key == "minimal_example":
                typer.echo("```yaml")
                typer.echo(value.rstrip())
                typer.echo("```\n")
            elif isinstance(value, list):
                for item in value:
                    typer.echo(f"- {item}")
                typer.echo()
            else:
                typer.echo("```yaml")
                typer.echo(yaml.safe_dump(value, allow_unicode=True, sort_keys=False).rstrip())
                typer.echo("```\n")
    typer.echo("## Commands\n")
    for command in payload["commands"]:
        typer.echo(f"- `{command}`")


@app.command("docs")
def documentation(
    topic: str | None = typer.Argument(
        None,
        help="Topic, for example quickstart, design-language, charts, or troubleshooting",
    ),
    search: str | None = typer.Option(None, "--search", help="Search all built-in documentation"),
    task: str | None = typer.Option(
        None,
        "--task",
        help=(
            "Return the minimum authoring closure for a route such as minimal, "
            "cascading-selection, view-filter, browser-compute, or custom-renderer"
        ),
    ),
    component: str | None = typer.Option(
        None,
        "--component",
        help="Route from one Component id, for example control.select or view.custom",
    ),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Read the built-in AI development manual, recipes and troubleshooting guide."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    selectors = [topic is not None, search is not None, task is not None, component is not None]
    if sum(selectors) > 1:
        raise typer.BadParameter(
            "Choose only one of TOPIC, --search, --task, or --component"
        )
    if task is not None or component is not None:
        try:
            payload = resolve_authoring_route(task, component=component)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
        if output_format == "json":
            print_json(payload)
        else:
            _print_authoring_route(payload)
        return
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
            "schema": DOC_CATALOG_SCHEMA,
            "start_here": {
                "build_dashboard": "quickstart",
                "explore_data": "analysis-quickstart",
            },
            "paths": DOC_PATHS,
            "authoring_routes": authoring_route_catalog(),
            "topics": catalog,
        })
        return
    typer.echo("# Dataviz built-in manual\n")
    typer.echo("Choose the path that matches the job; do not load the entire Runtime contract.\n")
    if search:
        typer.echo(f"Search: `{search}`\n")
        for name, definition in catalog.items():
            typer.echo(f"- **{name}** — {definition['summary']}")
        if not catalog:
            typer.echo("No matching topics.")
    else:
        grouped: set[str] = set()
        for path in DOC_PATHS.values():
            typer.echo(f"## {path['title']}\n")
            typer.echo(f"{path['summary']} 从 `{path['command']}` 开始。\n")
            for name in path["workflow"]:
                grouped.add(name)
                typer.echo(f"- **{name}** — {DOC_TOPICS[name]['summary']}")
            typer.echo()
        remaining = [name for name in catalog if name not in grouped]
        if remaining:
            typer.echo("## 参考主题\n")
            for name in remaining:
                typer.echo(f"- **{name}** — {catalog[name]['summary']}")
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
        raise typer.BadParameter(
            'visual-check is not installed; run: pip install "ai-dataviz[visual-check]"'
        ) from error
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
                    f"{browser} is unavailable; run: python -m playwright install {browser}. "
                    f"On Linux, install browser system libraries with: "
                    f"python -m playwright install --with-deps {browser}"
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
                            state="attached", timeout=int(timeout_seconds * 1000)
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
        "protocols": dict(CURRENT_PROTOCOL_SCHEMAS),
        "plotly_js": PLOTLY_JS_VERSION,
        "workspace_change_protocol": WORKSPACE_CHANGE_SCHEMA,
    }
    if output_format == "json":
        print_json(payload)
    else:
        typer.echo(
            f"ai-dataviz {__version__} · "
            f"{payload['dependency_contract']} · {payload['runtime_protocol']} · "
            f"components {payload['component_registry']} · Plotly.js {payload['plotly_js']}"
        )


@app.command("frontend-adapters")
def frontend_adapters(
    name: str | None = typer.Argument(None, help="Adapter id, for example web-component"),
    output: Path | None = typer.Option(
        None, "--output", help="Copy an exportable reference Adapter to this file"
    ),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Inspect frontend implementations that consume dataviz/runtime/v9."""
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


@components_app.command("list")
def components(
    category: str | None = typer.Option(
        None,
        "--category",
        help="Filter by data-entry, view, section, layout, theme, renderer, runtime, data, or presentation",
    ),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """List installed Component contracts, optionally filtered by category."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    catalog = component_catalog(category)
    if output_format == "json":
        print_json(catalog)
        return
    typer.echo("# Dataviz component templates\n")
    for component_name, definition in catalog.items():
        typer.echo(f"- {component_name}: {definition['purpose']}")
    typer.echo(
        "\nRun `dataviz components show <name>` for the complete contract and example."
    )


def _print_component_definition(name: str, definition: dict[str, Any]) -> None:
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


@components_app.command("show")
def component_show(
    name: str = typer.Argument(..., help="Component name, for example control.cascader"),
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Show one Component contract, example, semantic DOM, and style tokens."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
    definition = component_catalog().get(name)
    if definition is None:
        raise typer.BadParameter(
            f"Unknown component: {name}. Available: {', '.join(component_catalog())}"
        )
    if output_format == "json":
        print_json({"name": name, **definition})
        return
    _print_component_definition(name, definition)


@components_app.command("check")
def component_check(
    output_format: str = typer.Option("markdown", "--format", help="markdown or json"),
) -> None:
    """Validate every installed Component Package and its declared assets."""
    if output_format not in {"markdown", "json"}:
        raise typer.BadParameter("--format must be markdown or json")
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


@components_app.command("gallery")
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


@renderer_app.command("test")
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


@inspect_app.command("context")
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


@inspect_app.command("dependencies")
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
            control_inputs = ", ".join(
                f"{alias}={binding['control']} ({binding['mode']})"
                for alias, binding in contract.interactive_control_inputs[
                    transform_id
                ].items()
            ) or "none"
            views = ", ".join(contract.transform_downstream_views[transform_id]) or "none"
            typer.echo(
                f"- `{transform_id}` ({contract.interactive_runtimes[transform_id]}) "
                f"← nodes: {dependencies}; inputs: {inputs}; "
                f"Control inputs: {control_inputs}; "
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
                f"- `{key}` · scope: {scope}; "
                f"direct data Views: {direct} (runtime field check: {runtime_checked}); "
                f"depends on: {direct_dependencies}; effective ancestors: {ancestors}; "
                f"Transforms: {transforms}; "
                f"derived Views: {derived}"
            )
    except Exception as exc:
        handle_error(exc)


@inspect_app.command("layout")
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
            catalog = scaffold_catalog()
            if output_format == "json":
                print_json(catalog)
            else:
                typer.echo("# Dataviz scaffold profiles\n")
                for name in catalog["profiles"]:
                    typer.echo(f"- `{name}`")
                typer.echo("\n# Fragment recipes\n")
                for definition in catalog["recipes"]:
                    if definition["scope"] == "fragment":
                        typer.echo(
                            f"- `{definition['id']}` · {definition['route']}"
                        )
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
                    "next": payload["verify"],
                }
            )
            return
        if output_format == "json":
            print_json(payload)
            return
        typer.echo(f"# Dataviz scaffold · {recipe}\n")
        typer.echo(f"Route: `{payload['route']}` · scope: `{payload['scope']}`\n")
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
        typer.echo("Verification chain:\n")
        for command in payload["verify"]:
            typer.echo(f"- `{command}`")
    except Exception as exc:
        handle_error(exc)


@benchmark_app.command("runtime")
def benchmark(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard: str = typer.Argument(...),
    output_format: str = typer.Option("json", "--format", help="json or markdown"),
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
    """Measure Query, report, browser rendering, memory, and disposal performance."""
    try:
        if output_format not in {"markdown", "json"}:
            raise typer.BadParameter("--format must be markdown or json")
        loaded = load_workspace(workspace)
        payload = _browser_runtime_benchmark(
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
        transport = payload["runtime"].get("transports", {})
        renderers = payload["runtime"].get("renderers", {})
        typer.echo(f"# Dataviz runtime benchmark · {payload['dashboard']}\n")
        typer.echo(
            f"- Browser: {payload['browser']['name']} · "
            f"query {payload['query']['duration_ms']} ms · "
            f"report {payload['report']['build_ms']} ms · "
            f"page ready median {payload['browser']['page_ready_ms']['median']} ms"
        )
        typer.echo(
            f"- Arrow: {transport.get('arrowRows', 0)} rows / "
            f"{transport.get('arrowBytes', 0)} bytes · "
            f"renderer failures: {renderers.get('failed', 0)}"
        )
        typer.echo(f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```")
    except Exception as exc:
        handle_error(exc)


def _analysis_entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    return analysis_entry_summary(entry)


def _analysis_parameter_text(entry: dict[str, Any]) -> str:
    parts: list[str] = []
    for parameter in entry.get("parameter_contracts", []):
        flags = [str(parameter.get("value_type") or parameter.get("type") or "value")]
        if parameter.get("required"):
            flags.append("required")
        if "default" in parameter:
            flags.append(f"default={parameter['default']!r}")
        options = parameter.get("options") or {}
        if options:
            candidate = str(options.get("mode"))
            if options.get("count") is not None:
                candidate += f"({options['count']})"
            flags.append(candidate)
        parts.append(f"{parameter['id']}[{', '.join(flags)}]")
    return ", ".join(parts)


def _analysis_catalog_text(entries: list[dict[str, Any]]) -> None:
    for index, entry in enumerate(entries):
        if index:
            typer.echo()
        typer.echo(str(entry.get("title") or entry["reference"]))
        if entry.get("purpose"):
            typer.echo(f"  {entry['purpose']}")
        context: list[str] = []
        if entry.get("grain"):
            context.append(f"Grain: {entry['grain']}")
        assurance = entry.get("assurance") or {}
        if assurance.get("status"):
            context.append(str(assurance["status"]).title())
        output = entry.get("output") or {}
        if output.get("kind"):
            field_count = len(output.get("schema") or [])
            output_text = str(output["kind"])
            if field_count:
                output_text += f" / {field_count} fields"
            context.append(f"Output: {output_text}")
        if context:
            typer.echo("  " + " · ".join(context))
        parameters = _analysis_parameter_text(entry)
        if parameters:
            typer.echo(f"  Inputs: {parameters}")
        controls = entry.get("control_contracts") or []
        if controls:
            typer.echo(
                "  Controls: "
                + ", ".join(
                    f"{item['key']}[{item['kind']}, {item['value_type']}]"
                    for item in controls
                )
            )
        consumers = entry.get("downstream_views") or []
        if consumers:
            typer.echo("  Used by: " + ", ".join(consumers))
        occurrence_count = int(entry.get("occurrence_count") or 1)
        occurrence = f" · {occurrence_count} exact occurrences" if occurrence_count > 1 else ""
        typer.echo(
            f"  Ref: {entry['reference']} · {entry['kind']}{occurrence}"
        )
        reasons = entry.get("match_reasons") or []
        if reasons:
            typer.echo("  Match: " + ", ".join(reasons))


def _analysis_match_reasons(
    entry: dict[str, Any], query: str, *, regex: bool
) -> list[str]:
    if not query:
        return []
    fields: list[tuple[str, str]] = [
        ("title", str(entry.get("title") or "")),
        ("purpose", str(entry.get("purpose") or "")),
        ("grain", str(entry.get("grain") or "")),
        ("dashboard", " ".join(str(value) for value in entry.get("dashboard", {}).values())),
        ("parameter", " ".join(entry.get("query_parameters") or [])),
        (
            "field",
            " ".join(
                str(item.get("name") or "")
                for item in (entry.get("output") or {}).get("schema", [])
            ),
        ),
        ("view", " ".join(entry.get("downstream_views") or [])),
    ]
    if regex:
        pattern = re.compile(query, re.IGNORECASE)
        return [name for name, value in fields if value and pattern.search(value)]
    terms = [term.casefold() for term in query.split() if term]
    return [
        name
        for name, value in fields
        if value and any(term in value.casefold() for term in terms)
    ]


def _analysis_primary_search_entries(
    catalog,
    entries: list[dict[str, Any]],
    *,
    explicit_kind: str | None,
    include_internal: bool,
    include_untrusted: bool,
) -> list[dict[str, Any]]:
    """Keep reusable Outputs primary while retaining Source/View match evidence."""

    if explicit_kind is not None:
        return entries
    selected: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry["kind"] in {"base_output", "derived_output"}:
            selected.setdefault(entry["reference"], dict(entry))
            continue
        related = (
            list(entry.get("outputs", []))
            if entry["kind"] == "source"
            else list((entry.get("inputs") or {}).values())
        )
        for reference in related:
            try:
                output = dict(catalog.resolve(reference))
            except Exception:
                continue
            if output["kind"] not in {"base_output", "derived_output"}:
                continue
            if not include_internal and output.get("visibility", "public") != "public":
                continue
            if (
                not include_untrusted
                and output.get("assurance", {}).get("status", "draft")
                not in {"reviewed", "certified"}
            ):
                continue
            target = selected.setdefault(output["reference"], output)
            target.setdefault("related_matches", []).append(
                f"{entry['kind']}:{entry.get('title') or entry['reference']}"
            )
    return sorted(
        selected.values(),
        key=lambda entry: (
            entry["dashboard"]["id"],
            entry["kind"],
            entry["reference"],
        ),
    )


def _analysis_catalog_payload(catalog, entries: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = [
        entry["reference"]
        for entry in entries
        if entry.get("semantic_status") == "incomplete"
    ]
    return validate_analysis_catalog_producer({
        "schema": ANALYSIS_CATALOG_SCHEMA,
        "generation": catalog.generation,
        "count": len(entries),
        "entries": [_analysis_entry_summary(entry) for entry in entries],
        "diagnostics": list(getattr(catalog, "diagnostics", [])) + (
            [
                {
                    "level": "advice",
                    "code": "analysis_output_semantics_incomplete",
                    "message": (
                        f"{len(incomplete)} public Output(s) need purpose/grain metadata "
                        "before the Analysis Catalog can be treated as self-explanatory."
                    ),
                    "references": incomplete,
                }
            ]
            if incomplete
            else []
        ),
        "stale": bool(getattr(catalog, "stale", False)),
    })


def _analysis_validate_kind(kind: str | None) -> str | None:
    if kind in {None, "all"}:
        return None
    aliases = {
        "source": "source",
        "base": "base_output",
        "base_output": "base_output",
        "derived": "derived_output",
        "derived_output": "derived_output",
        "view": "view",
    }
    normalized = aliases.get(kind)
    if normalized is None:
        raise typer.BadParameter(
            "--kind must be base, derived, source, view, or all"
        )
    return normalized


def _analysis_artifact_binding(loaded, dashboard, entry, store, artifact) -> dict[str, Any]:
    return analysis_artifact_binding(loaded, dashboard, entry, store, artifact)


def _analysis_result_text(payload: dict[str, Any]) -> None:
    typer.echo(str(payload.get("status") or "ready").upper())
    typer.echo(f"Result: {payload['result_id']}")
    typer.echo(f"Path: {payload['result_path']}")
    target = payload.get("target") or {}
    if target:
        typer.echo(
            f"Target: {target.get('title') or target.get('reference')} "
            f"({target.get('reference')})"
        )
    lineage = payload.get("lineage") or {}
    nodes = [
        *lineage.get("query_nodes", []),
        *lineage.get("interactive_nodes", []),
    ]
    if nodes:
        typer.echo("DAG: " + " <- ".join(dict.fromkeys(nodes)))
    for output in payload.get("outputs", []):
        rows = output.get("rows")
        suffix = f" · {rows} rows" if rows is not None else ""
        typer.echo()
        typer.echo(f"{output['reference']} · {output['kind']}{suffix}")
        preview = output.get("preview")
        if output.get("kind") == "table" and isinstance(preview, list):
            import pandas as pd

            frame = pd.DataFrame(preview)
            if not frame.empty:
                typer.echo(frame.to_string(index=False))
        elif preview is not None:
            typer.echo(str(preview))
    typer.echo()
    typer.echo("Next:")
    for action in payload.get("next_actions", []):
        typer.echo(f"  {action}")


@evidence_app.command("create")
def evidence_create(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    result: str = typer.Argument(..., help="Immutable Result id"),
    question: str = typer.Option(..., "--question"),
    conclusion: list[str] = typer.Option(..., "--conclusion"),
    assertion: list[str] | None = typer.Option(None, "--assertion"),
    generated_by: str = typer.Option("ai", "--generated-by"),
    status: str = typer.Option("draft", "--status", help="draft or reviewed"),
    reviewer: str = typer.Option("", "--reviewer"),
    snapshot_rows: int = typer.Option(0, "--snapshot-rows", min=0, max=100),
) -> None:
    """Persist a compact, hash-linked Evidence Artifact from an Analysis Result."""

    try:
        if status not in {"draft", "reviewed"}:
            raise typer.BadParameter("--status must be draft or reviewed")
        store = AnalysisResultStore(workspace)
        with store.lease(result):
            manifest = store.load(result)
        payload = manifest["result"]
        source = f".dataviz/results/{result}/manifest.json"
        evidence, destination = create_analysis_evidence(
            workspace,
            payload,
            result_source=source,
            question=question,
            conclusions=conclusion,
            assertions=assertion,
            generated_by=generated_by,
            reviewer=reviewer,
            status=status,
            snapshot_rows=snapshot_rows,
        )
        output = evidence.model_dump(mode="json", by_alias=True)
        output["artifact"] = destination.relative_to(workspace.resolve()).as_posix()
        output["next_actions"] = [
            f"dataviz evidence promote {shlex.quote(str(workspace))} "
            f"{evidence.evidence_id} proposal.yaml --dry-run"
        ]
        print_json(output)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@evidence_app.command("promote")
def evidence_promote(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    evidence_reference: str = typer.Argument(..., help="Evidence id or JSON path"),
    proposal: Path = typer.Argument(..., exists=True, dir_okay=False),
    dry_run: bool = typer.Option(False, "--dry-run"),
    output: Path | None = typer.Option(None, "--output", help="Write the unified patch preview"),
) -> None:
    """Validate and explain a Promotion patch without mutating the Workspace."""

    try:
        if not dry_run:
            raise typer.BadParameter(
                "Promotion is review-only in P1; pass --dry-run to generate a patch preview"
            )
        evidence, _evidence_path = load_analysis_evidence(workspace, evidence_reference)
        parsed = load_promotion_proposal(proposal)
        promotion = build_promotion_preview(workspace, evidence, parsed)
        payload = promotion.model_dump(mode="json", by_alias=True)
        patch_text = "".join(
            operation.get("diff", "") for operation in payload["operations"]
        )
        payload["patch_sha256"] = hashlib.sha256(
            patch_text.encode("utf-8")
        ).hexdigest()
        payload["mutated_workspace"] = False
        if output is not None:
            atomic_write_text(output, patch_text)
            payload["patch_file"] = str(output.resolve())
        print_json(payload)
        if promotion.status != "ready":
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@parameters_app.command("options")
def parameter_options(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    dashboard_id: str = typer.Argument(..., help="Dashboard id"),
    parameters: list[str] | None = typer.Option(
        None,
        "--parameter",
        help="Return one dynamic Query Parameter; repeat to select several",
    ),
    query_param: list[str] | None = typer.Option(
        None,
        "--query-param",
        help="Optional parent/input value as name=JSON; repeat as needed",
    ),
    preview_rows: int = typer.Option(10, "--preview-rows", min=1, max=100),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Execute and seal live candidate tables; print only a bounded preview."""

    try:
        if output_format not in {"text", "json"}:
            raise typer.BadParameter("--format must be text or json")
        loaded = load_workspace(workspace)
        dashboard = loaded.dashboard(dashboard_id)
        supplied = parse_params(query_param)
        resolution = resolve_parameter_domains(
            loaded,
            dashboard,
            supplied,
            timezone_name=loaded.definition.context.timezone,
            initialized_parameters=set(supplied),
            strict=False,
        )
        available = list(resolution.choices)
        selected = list(dict.fromkeys(parameters or available))
        unknown = [parameter for parameter in selected if parameter not in resolution.choices]
        if unknown:
            raise typer.BadParameter(
                "Unknown dynamic Query Parameter(s): " + ", ".join(unknown)
            )
        if not selected:
            if output_format == "json":
                print_json(
                    {
                        "schema": "dataviz/parameter-options/v1",
                        "status": "ready",
                        "dashboard": dashboard_id,
                        "tables": [],
                        "note": "This Dashboard has no dynamic Query Parameter candidates.",
                    }
                )
            else:
                typer.echo(f"{dashboard_id}: no dynamic Query Parameter candidates")
            return
        definitions = {
            item.id: item for item in dashboard.definition.query_parameters
        }
        domain_ids = {
            definitions[parameter].options.source for parameter in selected
        }
        snapshot = ParameterOptionsStore(workspace).publish(
            dashboard=dashboard_id,
            generation=resolution.as_dict()["generation"],
            query_parameters=supplied,
            frames={
                domain_id: frame
                for domain_id, frame in resolution.frames.items()
                if domain_id in domain_ids
            },
            metadata=resolution.domains,
        )
        tables: list[dict[str, Any]] = []
        for table in snapshot["tables"]:
            frame = resolution.frames[table["domain"]]
            tables.append(
                {
                    **table,
                    "preview_rows": min(preview_rows, len(frame)),
                    "truncated": len(frame) > preview_rows,
                    "preview": frame.head(preview_rows).to_dict(orient="records"),
                }
            )
        payload = {
            "schema": "dataviz/parameter-options/v1",
            "status": "ready",
            "options_id": snapshot["options_id"],
            "options_path": snapshot["options_path"],
            "dashboard": dashboard_id,
            "generation": snapshot["generation"],
            "query_parameters": supplied,
            "tables": tables,
            "note": (
                "Candidate discovery is optional and this snapshot is immutable; "
                "dataviz run does not execute or enforce Parameter Domains."
            ),
        }
        if output_format == "json":
            print_json(payload)
            return
        typer.echo(f"READY\nOptions: {snapshot['options_id']}\nPath: {snapshot['options_path']}")
        for table in tables:
            typer.echo(f"\n{table['domain']} · {table['rows']} rows")
            frame = pd.DataFrame(table["preview"])
            if not frame.empty:
                typer.echo(frame.to_string(index=False))
            if table["truncated"]:
                typer.echo(f"… preview limited to {preview_rows} rows")
        quoted_workspace = json.dumps(str(workspace.resolve()), ensure_ascii=False)
        typer.echo("\nNext:")
        for table in tables:
            typer.echo(
                f"  dataviz parameters filter {quoted_workspace} "
                f"{snapshot['options_id']} --domain {table['domain']}"
            )
        typer.echo("\nOptional discovery only; dataviz run does not query this Domain.")
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@parameters_app.command("filter")
def parameter_options_filter(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    options_id: str = typer.Argument(..., help="Immutable options snapshot id"),
    domain: str | None = typer.Option(None, "--domain"),
    where: list[str] | None = typer.Option(
        None,
        "--where",
        help="Filter a raw Domain column as name=JSON; repeat as needed",
    ),
    columns: list[str] | None = typer.Option(
        None,
        "--column",
        help="Return one raw Domain column; repeat as needed",
    ),
    offset: int = typer.Option(0, "--offset", min=0),
    limit: int = typer.Option(10, "--limit", min=1, max=100),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Filter one sealed candidate table without executing its SQL again."""

    try:
        if output_format not in {"text", "json"}:
            raise typer.BadParameter("--format must be text or json")
        store = ParameterOptionsStore(workspace)
        manifest = store.load(options_id)
        domain_id, frame, total = store.read(
            manifest,
            domain=domain,
            filters=parse_params(where),
            columns=columns,
            offset=offset,
            limit=limit,
        )
        payload = {
            "schema": "dataviz/parameter-options-page/v1",
            "status": "ready",
            "options_id": options_id,
            "domain": domain_id,
            "offset": offset,
            "limit": limit,
            "total": total,
            "truncated": offset + limit < total,
            "rows": frame.to_dict(orient="records"),
        }
        if output_format == "json":
            print_json(payload)
            return
        typer.echo(
            f"{options_id} · {domain_id} · {total} matching rows · "
            f"showing {offset}..{min(offset + len(frame), total)}"
        )
        if frame.empty:
            typer.echo("No matching candidates")
        else:
            typer.echo(frame.to_string(index=False))
        if payload["truncated"]:
            typer.echo(f"… use --offset {offset + limit} --limit {limit} for more")
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@catalog_app.command("list")
def catalog_list(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    kind: str | None = typer.Option("base", "--kind", help="base, derived, source, view, or all"),
    dashboard: str | None = typer.Option(None, "--dashboard", help="Filter by Dashboard id"),
    source_type: str | None = typer.Option(None, "--source-type", help="Filter by Source type"),
    parameter: str | None = typer.Option(None, "--parameter", help="Require a Query Parameter id"),
    output_format: str = typer.Option("text", "--format", help="text or json"),
    refresh_catalog: bool = typer.Option(False, "--refresh-catalog", help="Force a safe Catalog rebuild"),
    include_internal: bool = typer.Option(False, "--include-internal", help="Include internal Outputs"),
    include_untrusted: bool = typer.Option(
        False, "--include-untrusted", help="Include draft and deprecated Outputs"
    ),
    fold: bool = typer.Option(
        True, "--fold/--no-fold", help="Fold only exactly identical Output implementations"
    ),
    expand_occurrences: bool = typer.Option(
        False,
        "--expand-occurrences",
        help="Include every folded physical reference and its own usage",
    ),
    top: int | None = typer.Option(
        None, "--top", min=1, help="Return N results after exact folding"
    ),
) -> None:
    """Show a compact overview of all reusable data contracts."""
    try:
        if output_format not in {"json", "text"}:
            raise typer.BadParameter("--format must be json or text")
        catalog = ensure_analysis_catalog(workspace, refresh=refresh_catalog)
        entries = catalog.select(
            kind=_analysis_validate_kind(kind),
            dashboard=dashboard,
            source_type=source_type,
            parameter=parameter,
            include_internal=include_internal,
            include_untrusted=include_untrusted,
        )
        entries = catalog.overview(
            entries,
            fold=fold,
            expand_occurrences=expand_occurrences,
            top=top,
        )
        if output_format == "json":
            print_json(_analysis_catalog_payload(catalog, entries))
            return
        _analysis_catalog_text(entries)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@catalog_app.command("search")
def catalog_search(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    query_text: str = typer.Argument(..., help="Words describing the desired data contract"),
    kind: str | None = typer.Option(None, "--kind", help="source, base, derived, or view"),
    dashboard: str | None = typer.Option(None, "--dashboard", help="Filter by Dashboard id"),
    source_type: str | None = typer.Option(None, "--source-type", help="Filter by Source type"),
    parameter: str | None = typer.Option(None, "--parameter", help="Require a Query Parameter id"),
    output_format: str = typer.Option("text", "--format", help="text or json"),
    regex: bool = typer.Option(
        True,
        "--regex/--literal",
        help="Use case-insensitive grep-like regular expressions, or literal all-word matching.",
    ),
    refresh_catalog: bool = typer.Option(False, "--refresh-catalog", help="Force a safe Catalog rebuild"),
    include_internal: bool = typer.Option(False, "--include-internal", help="Include internal Outputs"),
    include_untrusted: bool = typer.Option(
        False, "--include-untrusted", help="Include draft and deprecated Outputs"
    ),
    fold: bool = typer.Option(
        True, "--fold/--no-fold", help="Fold only exactly identical Output implementations"
    ),
    expand_occurrences: bool = typer.Option(
        False,
        "--expand-occurrences",
        help="Include every folded physical reference and its own usage",
    ),
    top: int | None = typer.Option(
        None, "--top", min=1, help="Return N results after exact folding"
    ),
) -> None:
    """Search Output meaning, fields, parameters, lineage, and View consumers."""
    try:
        if output_format not in {"json", "text"}:
            raise typer.BadParameter("--format must be json or text")
        catalog = ensure_analysis_catalog(workspace, refresh=refresh_catalog)
        normalized_kind = _analysis_validate_kind(kind)
        entries = catalog.select(
            query=query_text,
            kind=normalized_kind,
            dashboard=dashboard,
            source_type=source_type,
            parameter=parameter,
            regex=regex,
            include_internal=include_internal,
            include_untrusted=include_untrusted,
        )
        entries = _analysis_primary_search_entries(
            catalog,
            entries,
            explicit_kind=normalized_kind,
            include_internal=include_internal,
            include_untrusted=include_untrusted,
        )
        entries = catalog.overview(
            entries,
            fold=fold,
            expand_occurrences=expand_occurrences,
            top=top,
        )
        entries = [
            {
                **entry,
                "match_reasons": _analysis_match_reasons(
                    entry, query_text, regex=regex
                ) + list(entry.get("related_matches") or []),
            }
            for entry in entries
        ]
        if output_format == "json":
            print_json(_analysis_catalog_payload(catalog, entries))
            return
        _analysis_catalog_text(entries)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@catalog_app.command("describe")
def catalog_describe(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    references: list[str] = typer.Argument(
        ..., help="One or more canonical Target References"
    ),
    refresh_catalog: bool = typer.Option(False, "--refresh-catalog"),
    detail: str = typer.Option("summary", "--detail", help="summary, debug, or full"),
    output_format: str = typer.Option("text", "--format", help="text or json"),
    include_code: bool = typer.Option(
        False,
        "--include-code",
        help="Include redacted SQL/JS/Python text for the target closure",
    ),
) -> None:
    """Describe how to execute one or more contracts without running data."""
    try:
        if output_format not in {"text", "json"}:
            raise typer.BadParameter("--format must be text or json")
        detail = _result_detail(detail)
        if include_code and detail != "full":
            raise typer.BadParameter("--include-code requires --detail full")
        catalog = ensure_analysis_catalog(workspace, refresh=refresh_catalog)
        loaded = load_workspace(workspace) if detail == "full" else None
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        failed = False
        for requested in references:
            try:
                resolved = dict(catalog.resolve(requested))
                if resolved["reference"] in seen:
                    continue
                seen.add(resolved["reference"])
                entry = (
                    _analysis_entry_summary(resolved)
                    if detail == "summary"
                    else resolved
                )
                local_closure = {
                    key: resolved.get(key, [])
                    for key in (
                        "query_nodes",
                        "interactive_nodes",
                        "base_inputs",
                        "upstream_outputs",
                        "inputs",
                    )
                    if resolved.get(key)
                }
                item: dict[str, Any] = {
                    "status": "ready",
                    "requested_reference": requested,
                    "entry": entry,
                    "invocation": {
                        "query_parameters": resolved.get("parameter_contracts", []),
                        "controls": resolved.get("control_contracts", []),
                        "outputs": resolved.get("outputs")
                        or resolved.get("inputs")
                        or [resolved["reference"]],
                    },
                    "closure": local_closure,
                    "next_actions": [
                        f"dataviz run {shlex.quote(str(workspace))} {resolved['reference']}"
                    ],
                }
                if detail == "full" and loaded is not None:
                    dashboard = loaded.dashboard(resolved["dashboard"]["id"])
                    closure_references = (
                        resolved.get("inputs", {}).values()
                        if resolved["kind"] == "view"
                        else [resolved["reference"]]
                    )
                    item["closure"] = inspect_analysis_closure(
                        loaded,
                        dashboard,
                        closure_references,
                        include_code=include_code,
                    )
                items.append(item)
            except Exception as error:
                failed = True
                details = getattr(error, "details", {}) or {}
                items.append(
                    {
                        "status": "error",
                        "requested_reference": requested,
                        "error": {
                            "code": details.get("code", "analysis_describe_failed"),
                            "message": str(error),
                        },
                    }
                )
        payload = validate_analysis_describe_producer(
            {
                "schema": ANALYSIS_DESCRIBE_SCHEMA,
                "generation": catalog.generation,
                "count": len(items),
                "items": items,
            }
        )
        if output_format == "json":
            print_json(payload)
        else:
            for index, item in enumerate(payload["items"]):
                if index:
                    typer.echo()
                if item["status"] == "error":
                    typer.echo(
                        f"{item['requested_reference']}: ERROR {item['error']['message']}"
                    )
                    continue
                entry = item["entry"]
                typer.echo(str(entry.get("title") or entry["reference"]))
                if entry.get("purpose"):
                    typer.echo(f"  {entry['purpose']}")
                typer.echo(
                    f"  Ref: {entry['reference']} · {entry['kind']}"
                )
                parameters = _analysis_parameter_text(entry)
                typer.echo(f"  Parameters: {parameters or 'none'}")
                closure = item.get("closure") or {}
                for key, values in closure.items():
                    if values:
                        typer.echo(f"  {key}: {values}")
                typer.echo(f"  Run: {item['next_actions'][0]}")
        if failed:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


def _analysis_artifact_value(store: ArtifactStore, artifact, limit: int) -> tuple[Any, bool]:
    return analysis_artifact_value(store, artifact, limit)


@result_app.command("list")
def result_list(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    status: str | None = typer.Option(
        None, "--status", help="Filter by ready, partial, failed, or cancelled"
    ),
    limit: int = typer.Option(50, "--limit", min=1, max=1000),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """List sealed Results without loading their data Artifacts."""

    try:
        if output_format not in {"text", "json"}:
            raise typer.BadParameter("--format must be text or json")
        if status not in {None, "ready", "partial", "failed", "cancelled"}:
            raise typer.BadParameter(
                "--status must be ready, partial, failed, or cancelled"
            )
        store = AnalysisResultStore(workspace)
        values = store.list(limit=limit, status=status)
        payload = {
            "schema": "dataviz/result-list/v1",
            "count": len(values),
            "results": values,
        }
        if output_format == "json":
            print_json(payload)
            return
        for item in values:
            target = item.get("target") or {}
            typer.echo(
                f"{item['result_id']}  {item['status']}  "
                f"{target.get('reference') or 'unknown-target'}  "
                f"{item['outputs']} output(s)  {item['created_at']}"
            )
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@result_app.command("show")
def result_show(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    result_id: str = typer.Argument(...),
    output: str | None = typer.Argument(
        None, help="Canonical Output reference; required for multi-Output paging"
    ),
    offset: int = typer.Option(0, "--offset", min=0),
    limit: int = typer.Option(100, "--limit", min=1),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Read an immutable Result Output without executing its Dashboard again."""

    try:
        if output_format not in {"text", "json"}:
            raise typer.BadParameter("--format must be text or json")
        store = AnalysisResultStore(workspace)
        with store.lease(result_id):
            manifest = store.load(result_id)
            outputs = manifest["result"].get("outputs", [])
            selected = (
                [store.resolve_output(manifest, output)]
                if output is not None or len(outputs) == 1
                else outputs
            )
            rendered: list[dict[str, Any]] = []
            for item in selected:
                value, total = store.read_output(
                    manifest, item, offset=offset, limit=limit
                )
                if item.get("kind") == "table":
                    records = json.loads(value.to_json(orient="records", date_format="iso"))
                else:
                    records = value
                rendered.append(
                    {
                        "reference": item["reference"],
                        "kind": item["kind"],
                        "rows": total,
                        "offset": offset,
                        "limit": limit,
                        "value": records,
                    }
                )
        payload = {
            "schema": "dataviz/analysis-result-page/v1",
            "result_id": result_id,
            "outputs": rendered,
        }
        if output_format == "json":
            print_json(payload)
            return
        typer.echo(f"Result: {result_id}")
        for item in rendered:
            typer.echo()
            rows = f" · {item['rows']} rows" if item["rows"] is not None else ""
            typer.echo(f"{item['reference']} · {item['kind']}{rows}")
            if item["kind"] == "table":
                import pandas as pd

                frame = pd.DataFrame(item["value"])
                if not frame.empty:
                    typer.echo(frame.to_string(index=False))
            else:
                typer.echo(str(item["value"]))
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@result_app.command("inspect")
def result_inspect(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    result_id: str = typer.Argument(...),
    output_format: str = typer.Option("text", "--format", help="text or json"),
    detail: str = typer.Option("summary", "--detail", help="summary or full"),
) -> None:
    """Inspect Result lineage, storage, hashes, and provenance without re-running."""

    try:
        if output_format not in {"text", "json"}:
            raise typer.BadParameter("--format must be text or json")
        if detail not in {"summary", "full"}:
            raise typer.BadParameter("--detail must be summary or full")
        store = AnalysisResultStore(workspace)
        with store.lease(result_id):
            manifest = store.load(result_id)
        payload = manifest if detail == "full" else {
            "schema": manifest["schema"],
            "result_id": manifest["result_id"],
            "status": manifest["status"],
            "created_at": manifest["created_at"],
            "manifest_hash": result_manifest_hash(manifest),
            "target": manifest["result"].get("target"),
            "query_parameters": manifest["result"].get("query_parameters", {}),
            "effective_controls": manifest["result"].get("effective_controls", {}),
            "consumer_revisions": manifest["result"].get(
                "consumer_revisions", {"views": {}, "transforms": {}}
            ),
            "outputs": [
                {
                    key: item.get(key)
                    for key in (
                        "reference",
                        "kind",
                        "rows",
                        "content_hash",
                        "storage",
                    )
                }
                for item in manifest["result"].get("outputs", [])
            ],
            "lineage": manifest["result"].get("lineage", {}),
            "timing": manifest["result"].get("timing", {}),
            "provenance": manifest["result"].get("provenance", {}),
        }
        if output_format == "json":
            print_json(payload)
            return
        typer.echo(f"Result: {result_id} · {manifest['status']}")
        typer.echo(f"Created: {manifest['created_at']}")
        target = manifest["result"].get("target") or {}
        typer.echo(f"Target: {target.get('title') or target.get('reference')}")
        for item in manifest["result"].get("outputs", []):
            typer.echo(
                f"  {item['reference']} · {item['kind']} · {item.get('rows', '?')} rows · "
                f"{item['storage']['mode']}:{item['storage'].get('path')}"
            )
        if detail == "full":
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        else:
            typer.echo("Use --detail full --format json for the complete immutable manifest.")
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@result_app.command("export")
def result_export(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    result_id: str = typer.Argument(...),
    output: str = typer.Argument(..., help="Canonical Output reference"),
    destination: Path = typer.Option(..., "--to", help="Copy the native Artifact here"),
) -> None:
    """Copy one existing native Output Artifact without conversion or re-execution."""

    try:
        store = AnalysisResultStore(workspace)
        with store.lease(result_id):
            manifest = store.load(result_id)
            selected = store.resolve_output(manifest, output)
            target = store.export_output(manifest, selected, destination)
        print_json(
            {
                "schema": "dataviz/analysis-result-export/v1",
                "status": "ready",
                "result_id": result_id,
                "output": selected["reference"],
                "path": str(target),
                "content_hash": sha256_file(target),
                "converted": False,
            }
        )
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


def _analysis_artifact_payload(
    *,
    entry: dict[str, Any],
    artifact,
    value: Any,
    truncated: bool,
    run_id: str,
    duration_ms: int | None,
) -> dict[str, Any]:
    return analysis_artifact_payload(
        entry=entry,
        artifact=artifact,
        value=value,
        truncated=truncated,
        run_id=run_id,
        duration_ms=duration_ms,
    )


@app.command()
def run(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    target: str = typer.Argument(..., help="Dashboard id or canonical Target Reference"),
    also: list[str] | None = typer.Option(
        None, "--also", help="Repeat compatible canonical Output targets in one execution"
    ),
    query_param: list[str] | None = typer.Option(None, "--query-param"),
    control: list[str] | None = typer.Option(None, "--control"),
    output_name: str | None = typer.Option(None, "--output", help="View input name"),
    runtime: str = typer.Option("auto", "--runtime", help="auto, server, or browser"),
    output_format: str = typer.Option("text", "--format", help="text or json"),
    preview_rows: int = typer.Option(10, "--preview-rows", min=1),
    refresh: bool = typer.Option(False, "--refresh"),
    refresh_catalog: bool = typer.Option(False, "--refresh-catalog"),
    allow_network: bool = typer.Option(False, "--allow-network"),
    timeout_seconds: float = typer.Option(60.0, "--timeout", min=1.0),
    detail: str = typer.Option("summary", "--detail", help="summary, debug, or full"),
    overlay: str | None = typer.Option(None, "--overlay"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
) -> None:
    """Execute a Dashboard or canonical data Target and seal one immutable Result."""
    try:
        parsed = parse_target_reference(target)
        if output_format not in {"json", "text"}:
            raise typer.BadParameter("--format must be text or json")
        published = run_analysis(
            RunRequest(
                workspace=workspace,
                target=parsed.canonical,
                also=tuple(also or ()),
                query_parameters=parse_params(query_param),
                controls=parse_params(control),
                output_name=output_name,
                runtime=runtime,
                preview_rows=preview_rows,
                refresh=refresh,
                refresh_catalog=refresh_catalog,
                allow_network=allow_network,
                timeout_seconds=timeout_seconds,
                detail=_result_detail(detail),
                overlay=Path(overlay) if overlay is not None else None,
                dry_run=dry_run,
            )
        )
        if published.get("schema") == "dataviz/analysis-overlay-explanation/v1":
            print_json(published)
            return
        if output_format == "json":
            print_json(published)
        else:
            _analysis_result_text(published)
        status = published["status"]
        if status == "cancelled":
            raise typer.Exit(130)
        if status != "ready" and not (allow_partial and status == "partial"):
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_error(exc)


@app.command()
def report(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    target: str = typer.Argument(..., help="Result id or Dashboard id convenience target"),
    output: Path = typer.Option(..., "--output"),
    query_param: list[str] | None = typer.Option(None, "--query-param"),
    control: list[str] | None = typer.Option(None, "--control"),
    refresh: bool = typer.Option(False, "--refresh"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
) -> None:
    """Write a report from an immutable Result, or run a Dashboard as a convenience."""
    try:
        if target.startswith("result_"):
            store = AnalysisResultStore(workspace)
            with store.lease(target):
                manifest = store.load(target)
                renderability = manifest["result"].get("renderability") or {}
                snapshot = renderability.get("snapshot")
                if not renderability.get("renderable") or not snapshot:
                    raise typer.BadParameter(
                        "This Result is data-only and has no sealed Presentation snapshot"
                    )
                source = (store.root / target / snapshot).resolve()
                expected = str(renderability.get("content_hash") or sha256_file(source))
                copied = atomic_copy_file(source, output.resolve(), expected_sha256=expected)
            print_json(
                {
                    "status": "success",
                    "result_id": target,
                    "report": str(output.resolve()),
                    "content_hash": copied,
                    "reexecuted": False,
                }
            )
            return
        dashboard = target
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
        resolved_control_state = state_from_values(
            loaded_dashboard.definition,
            parse_params(control),
            phase="canvas-hydration",
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
            == "browser-js"
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
                control_state=resolved_control_state,
                refresh=refresh,
            )
            interaction_results.append(interaction)
            if interaction.status != "ready":
                print_json(interaction)
                raise typer.Exit(1)
            derived_outputs.update(interaction.outputs)
        applied_revisions = applied_revisions_for_consumers(
            loaded_dashboard,
            resolved_control_state,
            transform_ids={
                value.interaction_id for value in interaction_results
            },
        )
        applied_control_state = applied_control_state_for_consumers(
            loaded_dashboard,
            resolved_control_state,
            transform_ids={
                value.interaction_id for value in interaction_results
            },
        )
        path = CanvasRenderer(loaded).write_report(
            loaded_dashboard,
            result,
            output.resolve(),
            control_state=resolved_control_state,
            applied_revisions=applied_revisions,
            applied_control_state=applied_control_state,
            derived_outputs=derived_outputs,
            snapshot_interactions=snapshot_interactions,
        )
        manifest_path = path.with_suffix(path.suffix + ".manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        catalog = ensure_analysis_catalog(workspace)
        artifact_store = ArtifactStore(loaded.root, result.run_id)
        result_outputs: list[dict[str, Any]] = []
        result_bindings: dict[str, dict[str, Any]] = {"__report__": {"source_path": path}}
        for local_reference, artifact in sorted(
            {**result.outputs, **derived_outputs}.items()
        ):
            canonical = f"{dashboard}::{local_reference}"
            try:
                entry = catalog.resolve(canonical)
            except Exception:
                continue
            value, truncated = _analysis_artifact_value(artifact_store, artifact, 10)
            result_outputs.append(
                _analysis_artifact_payload(
                    entry=entry,
                    artifact=artifact,
                    value=value,
                    truncated=truncated,
                    run_id=result.run_id,
                    duration_ms=None,
                )
            )
            result_bindings[canonical] = _analysis_artifact_binding(
                loaded, loaded_dashboard, entry, artifact_store, artifact
            )
        sealed = seal_analysis_result(
            workspace,
            {
                    "schema": ANALYSIS_RESULT_SCHEMA,
                    "status": result.status,
                    "generation": catalog.generation,
                    "target": {
                        "reference": dashboard,
                        "kind": "dashboard",
                        "title": loaded_dashboard.title,
                        "dashboard": {
                            "id": dashboard,
                            "title": loaded_dashboard.title,
                            "path": loaded_dashboard.root.relative_to(loaded.root).as_posix(),
                        },
                    },
                    "query_parameters": result.query_parameters,
                    "effective_controls": resolved_control_state,
                    "consumer_revisions": normalize_consumer_revisions(
                        loaded_dashboard,
                        resolved_control_state,
                        applied_revisions,
                        applied_control_state,
                    ),
                    "outputs": result_outputs,
                    "lineage": {
                        "query_nodes": result.query_nodes,
                        "interactive_nodes": [
                            value.interaction_id for value in interaction_results
                        ],
                    },
                    "provenance": {
                        "catalog_generation": catalog.generation,
                        "query_contract_hash": result.query_contract_hash,
                    },
                    "renderability": {
                        "kind": "dashboard",
                        "renderable": True,
                        "dashboard": dashboard,
                    },
                    "timing": {},
                },
            result_bindings,
        )
        print_json(
            {
                "status": "success",
                "run_id": result.run_id,
                "result_id": sealed["result_id"],
                "report": str(path),
                "manifest": str(manifest_path),
                "portable_without_network": manifest["portable_without_network"],
                "portability_scope": manifest["portability_scope"],
                "network_dependencies": manifest["network_dependencies"],
                "query_parameters": result.query_parameters,
                "control_state": resolved_control_state,
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


@app.command("prune")
def prune_workspace(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Delete listed entries. Without this flag the command is a dry run.",
    ),
    all_state: bool = typer.Option(
        False,
        "--all",
        help="Select every unprotected Result, Run, options snapshot, and cache entry.",
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
        help="Override newest persistent cache and options snapshots to retain.",
    ),
    cache_max_age_hours: float | None = typer.Option(
        None,
        "--cache-max-age-hours",
        min=0,
        help="Select persistent cache entries older than this many hours.",
    ),
    keep_results: int | None = typer.Option(
        None,
        "--keep-results",
        min=0,
        help="Override the number of newest immutable Results to retain.",
    ),
    result_max_age_days: float = typer.Option(
        30,
        "--result-max-age-days",
        min=0,
        help="Select immutable Results older than this many days.",
    ),
    include_runs: bool = typer.Option(True, "--runs/--no-runs"),
    include_cache: bool = typer.Option(True, "--cache/--no-cache"),
    include_results: bool = typer.Option(True, "--results/--no-results"),
) -> None:
    """Preview or remove old Results, Runs, options snapshots, and caches."""
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
            max_results=(0 if all_state else keep_results),
            result_max_age_seconds=(
                0 if all_state else result_max_age_days * 24 * 3600
            ),
            include_runs=include_runs,
            include_cache=include_cache,
            include_results=include_results,
            apply=apply,
        )
        if apply and report["results"]:
            AnalysisResultStore(loaded.root).rebuild_index()
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
