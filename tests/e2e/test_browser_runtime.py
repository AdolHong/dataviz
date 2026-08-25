from __future__ import annotations

import json
import os
import re
import shutil
import socket
import threading
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import uvicorn
import yaml
from playwright.sync_api import (
    Browser,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
    sync_playwright,
)

from dataviz.server import create_app
from dataviz.cli import _copy_gallery_workspace


ROOT = Path(__file__).resolve().parents[2]
SHOWCASE = ROOT / "examples" / "feature-showcase"
MINIMAL = ROOT / "examples" / "minimal-workspace"
SALES = ROOT / "examples" / "sales-workspace"
PROGRESSIVE = ROOT / "tests" / "fixtures" / "progressive-workspace"
WORKER = ROOT / "tests" / "fixtures" / "browser-worker-workspace"
REPEAT = ROOT / "examples" / "repeat-workspace"


def _free_port() -> int:
    with socket.socket() as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        return int(server_socket.getsockname()[1])


@contextmanager
def _running_server(workspace: Path):
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(workspace),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="on",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("E2E server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="session")
def browser() -> Browser:
    with sync_playwright() as playwright:
        # Browser availability is part of the P0 contract. CI installs Chromium
        # explicitly, so a missing or broken browser must fail instead of hiding
        # the regression behind a skipped test.
        browser_name = os.environ.get("DATAVIZ_BROWSER", "chromium")
        if browser_name not in {"chromium", "firefox", "webkit"}:
            raise RuntimeError(f"Unsupported DATAVIZ_BROWSER: {browser_name}")
        instance = getattr(playwright, browser_name).launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser: Browser) -> Page:
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    yield page
    context.close()


def _copy_workspace(source: Path, destination: Path) -> Path:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(".dataviz", "dist", "__pycache__", "*.pyc"),
    )
    return destination


def _build_scale_workspace(root: Path, *, rows: int = 150_000) -> Path:
    dashboard = root / "dashboards" / "scale"
    transforms = dashboard / "transforms"
    sources = dashboard / "sources"
    auth = root / "auth"
    transforms.mkdir(parents=True)
    sources.mkdir()
    auth.mkdir()
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: scale-runtime
title: Scale Runtime
folders: []
runtime:
  browser_table_transport: arrow
  arrow_min_rows: 1
  max_embedded_rows: 200000
  max_embedded_bytes: 50000000
""",
        encoding="utf-8",
    )
    (auth / "adapters.yaml").write_text(
        """adapters:
  warehouse:
    type: duckdb
    database: ':memory:'
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v5
kind: dashboard
id: scale
title: Scale Runtime
adapters: {warehouse: warehouse}
sources:
  - id: rows
    type: sql
    adapter: warehouse
    code: sources/rows.sql
    outputs: {main: {kind: table}}
interactive_transforms:
  - transforms/peak.yaml
views:
  - id: source-maximum
    title: Source maximum
    input: source:rows/main
    template: metric
    value: value
    aggregate: max
  - id: worker-maximum
    title: Worker maximum
    input: interactive:peak/main
    template: metric
    value: peak
    aggregate: max
sections:
  - id: results
    title: Scale results
    views: [source-maximum, worker-maximum]
""",
        encoding="utf-8",
    )
    (sources / "rows.sql").write_text(
        f"select i % 10 as bucket, i as value from range(1, {rows + 1}) as data(i)\n",
        encoding="utf-8",
    )
    (transforms / "peak.yaml").write_text(
        """schema: dataviz/interactive-transform/v2
kind: interactive_transform
id: peak
runtime: browser-js
code: peak.js
inputs: {rows: source:rows/main}
trigger: auto
debounce_ms: 0
export: {mode: interactive}
outputs:
  main:
    kind: table
    schema: [{name: bucket}, {name: peak}]
timeout_seconds: 10
""",
        encoding="utf-8",
    )
    (transforms / "peak.js").write_text(
        """function transform(context) {
  return {main: context.table('rows').groupBy('bucket').aggregate({
    peak: {field: 'value', op: 'max'},
  }).rows()};
}
""",
        encoding="utf-8",
    )
    return root


@contextmanager
def _running_static_server(directory: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(QuietHandler, directory=str(directory)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


def _build_interactive_runtime_workspace(root: Path) -> Path:
    dashboard = root / "dashboards" / "runtime-matrix"
    (dashboard / "sources").mkdir(parents=True)
    (dashboard / "transforms").mkdir()
    (root / "pyodide").mkdir()
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: interactive-runtime-e2e
title: Interactive Runtime E2E
runtime:
  pyodide_asset_policy: bundle
  pyodide_bundle_path: pyodide
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v5
kind: dashboard
id: runtime-matrix
title: Interactive Runtime Matrix
query_parameters:
  - {id: batch, type: integer, label: Batch, default: 3}
controls:
  - {id: factor, kind: compute, label: Factor, type: number, default: 2}
  - id: name
    kind: selection
    field: name
    type: multi_select
    default: [alpha, beta]
    options:
      mode: static
      choices:
        - {label: Alpha, value: alpha}
        - {label: Beta, value: beta}
sources:
  - id: raw
    type: python
    code: sources/raw.py
    timeout_seconds: 10
    outputs: {main: {kind: table}}
    cache: {mode: none}
  - id: unrelated-slow
    type: python
    code: sources/slow.py
    timeout_seconds: 30
    outputs: {main: {kind: table}}
    cache: {mode: none}
  - id: unrelated-pulse
    type: python
    code: sources/pulse.py
    timeout_seconds: 10
    outputs: {main: {kind: table}}
    cache: {mode: none}
interactive_transforms:
  - transforms/server.yaml
  - transforms/browser.yaml
views:
  - {id: server-table, title: Server Python, template: table, input: interactive:server/main}
  - {id: browser-table, title: Browser Python, template: table, input: interactive:browser/main}
  - {id: slow-table, title: Unrelated slow branch, template: table, input: source:unrelated-slow/main}
  - {id: pulse-table, title: Unrelated pulse branch, template: table, input: source:unrelated-pulse/main}
sections:
  - {id: results, title: Runtime results, template: split, views: [server-table, browser-table]}
  - {id: slow-result, title: Slow result, template: split, views: [slow-table, pulse-table]}
""",
        encoding="utf-8",
    )
    (dashboard / "sources" / "raw.py").write_text(
        """import time


def load(context):
    time.sleep(0.2)
    return [{"name": "alpha", "value": 1}, {"name": "beta", "value": 2}]
""",
        encoding="utf-8",
    )
    (dashboard / "sources" / "slow.py").write_text(
        """import time


def load(context):
    # The test releases this unrelated branch only after both fast Interactive
    # branches are visible. A filesystem gate proves progressive publication
    # deterministically across browsers without relying on arbitrary sleeps.
    release = context.dashboard_root / "release-slow"
    deadline = time.monotonic() + 25
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return [{"branch": "unrelated", "value": 1}]
""",
        encoding="utf-8",
    )
    (dashboard / "sources" / "pulse.py").write_text(
        """import time


def load(context):
    # Publish while the Browser Interactive branch is active. This unrelated
    # Output must not cancel or restart that computation.
    time.sleep(0.45)
    return [{"branch": "pulse", "value": 1}]
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "server.yaml").write_text(
        """schema: dataviz/interactive-transform/v2
kind: interactive_transform
id: server
runtime: server-python
code: server.py
inputs: {rows: source:raw/main}
query_inputs: {batch: batch}
compute_inputs:
  factor: dashboard:runtime-matrix/factor
trigger: auto
debounce_ms: 0
export: {mode: snapshot}
outputs:
  main:
    kind: table
    schema: [{name: name}, {name: value}]
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "server.py").write_text(
        """def transform(context):
    assert context.query_inputs["batch"] == 3
    frame = context.table("rows").copy()
    frame["value"] = frame["value"] * context.compute_params["factor"] + 100
    context.progress(0.5, "server midpoint")
    return {"main": frame}
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "browser.yaml").write_text(
        """schema: dataviz/interactive-transform/v2
kind: interactive_transform
id: browser
runtime: browser-python
code: browser.py
inputs: {rows: source:raw/main}
query_inputs: {batch: batch}
compute_inputs:
  factor: dashboard:runtime-matrix/factor
trigger: auto
debounce_ms: 0
export: {mode: interactive, assets: bundle}
outputs:
  main:
    kind: table
    schema: [{name: name}, {name: value}]
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "browser.py").write_text(
        """def transform(context):
    assert context.query_inputs["batch"] == 3
    rows = context.inputs["rows"]
    if isinstance(rows, dict) and rows.get("__datavizColumnarTable"):
        columns = rows["columns"]
        rows = [dict(zip(columns, values)) for values in zip(*columns.values())]
    factor = context.compute_params["factor"]
    return {"main": [{"name": row["name"], "value": row["value"] * factor} for row in rows]}
""",
        encoding="utf-8",
    )
    # A deterministic Pyodide API double keeps this contract test offline. The
    # Worker boundary, module loading, context transport and lifecycle are real;
    # Python semantics are covered separately by the Runtime process tests.
    (root / "pyodide" / "pyodide.mjs").write_text(
        """export async function loadPyodide() {
  const values = new Map();
  const globals = {
    set(name, value) { values.set(name, value); },
    get(name) { return values.get(name); },
    delete(name) { values.delete(name); },
  };
  return {
    globals,
    FS: {
      mkdirTree() {}, writeFile() {}, unlink() {}, rmdir() {},
      readdir() { return ['.', '..']; }, stat() { return {mode:0}; }, isDir() { return false; },
    },
    toPy(value) { return value; },
    setInterruptBuffer() {},
    async loadPackage() {},
    async runPythonAsync(source) {
      if (!source.includes('await _dataviz_execute')) return undefined;
      await new Promise(resolve => setTimeout(resolve, 700));
      const payload = JSON.parse(values.get('__dv_payload'));
      if (Number(payload.query_inputs.batch) !== 3) throw new Error('missing browser-python query input');
      const input = payload.inputs.rows;
      const rows = input?.__datavizColumnarTable
        ? Array.from({length:input.length}, (_, index) => Object.fromEntries(
            Object.entries(input.columns).map(([name, column]) => [name, column[index]])
          ))
        : input;
      const factor = Number(payload.compute_params.factor);
      return JSON.stringify({main:rows.map(row => ({name:row.name, value:Number(row.value) * factor}))});
    },
  };
}
""",
        encoding="utf-8",
    )
    for name in ("pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip"):
        (root / "pyodide" / name).write_bytes(b"offline contract fixture")
    (root / "pyodide" / "package.json").write_text(
        json.dumps({"name": "pyodide", "version": "314.0.4"}),
        encoding="utf-8",
    )
    (root / "pyodide" / "pyodide-lock.json").write_text(
        json.dumps({"info": {"python": "3.14.0"}, "packages": {}}),
        encoding="utf-8",
    )
    return root


def _open_dashboard(page: Page, base_url: str, dashboard_id: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")
    dashboard = page.locator(f'[data-nav-type="dashboard"][data-id="{dashboard_id}"]')
    expect(dashboard).to_be_visible(timeout=10_000)
    dashboard.click()
    expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)


def _run_and_wait(page: Page, expected: str = "Ready") -> None:
    page.locator("#run-button").click()
    expect(page.locator("#query-diagnostics-label")).to_have_text(
        expected,
        timeout=30_000,
    )


@pytest.mark.e2e
def test_header_overlays_stay_in_viewport_and_query_parameters_are_discoverable(
    page: Page,
):
    page.set_viewport_size({"width": 1440, "height": 720})
    with _running_server(SHOWCASE) as base_url:
        _open_dashboard(page, base_url, "cascade-explorer")

        # Dashboards without Query Parameters do not render an empty tray.  The
        # Run control must say why its split-button toggle is absent.
        expect(page.locator("#query-parameters-toggle")).to_be_hidden()
        expect(page.locator("#query-parameters-control")).to_be_hidden()
        expect(page.locator("#query-control-meta")).to_have_text("No parameters")

        for trigger, panel_selector in (
            (
                "#dashboard-controls-control > summary",
                ".header-control__popover--controls",
            ),
            ("#query-diagnostics > summary", ".query-diagnostics__popover"),
        ):
            page.locator(trigger).click()
            panel = page.locator(panel_selector)
            expect(panel).to_be_visible()
            geometry = panel.evaluate(
                """panel => {
                  const rect = panel.getBoundingClientRect();
                  return {
                    left:rect.left, right:rect.right, top:rect.top, bottom:rect.bottom,
                    viewport:[innerWidth, innerHeight],
                    clientWidth:panel.clientWidth, scrollWidth:panel.scrollWidth,
                  };
                }"""
            )
            assert geometry["left"] >= 11, geometry
            assert geometry["right"] <= geometry["viewport"][0] - 11, geometry
            assert geometry["top"] >= 11, geometry
            assert geometry["bottom"] <= geometry["viewport"][1] - 11, geometry
            assert geometry["scrollWidth"] <= geometry["clientWidth"] + 1, geometry
            page.locator(trigger).click()

        page.locator(
            '[data-nav-type="dashboard"][data-id="parameter-playground"]'
        ).click()
        expect(page.locator("#query-parameters-toggle")).to_be_visible()
        expect(page.locator("#query-parameters-toggle")).to_have_attribute(
            "aria-expanded", "true"
        )
        expect(page.locator("#query-parameters-panel")).to_be_visible()
        expect(page.locator("#query-parameter-count")).to_contain_text("2 parameters")


@pytest.mark.e2e
def test_workspace_hot_reload_preserves_run_and_marks_query_contract_outdated(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "hot-reload-workspace")
    dashboard = workspace / "dashboards" / "sales-overview"
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.locator("#canvas-frame")
        run_id = frame.get_attribute("data-run-id")
        frame_id = frame.get_attribute("data-frame-id")

        css = dashboard / "assets" / "presentation.css"
        css.write_text(
            css.read_text(encoding="utf-8") + "\n/* e2e hot canvas */\n",
            encoding="utf-8",
        )
        expect(page.locator("#workspace-update-title")).to_have_text(
            "Canvas reloaded", timeout=10_000
        )
        expect(frame).not_to_have_attribute("data-frame-id", frame_id, timeout=10_000)
        assert frame.get_attribute("data-run-id") == run_id

        sql = dashboard / "sources" / "sales.sql"
        sql.write_text(
            sql.read_text(encoding="utf-8") + "\n-- e2e query contract\n",
            encoding="utf-8",
        )
        expect(page.locator("#workspace-update-title")).to_have_text(
            "Query definition changed", timeout=10_000
        )
        expect(page.locator("#query-diagnostics-label")).to_have_text("Outdated")
        expect(page.frame_locator("#canvas-frame").locator("body")).to_contain_text(
            "QUERY RUN OUTDATED", timeout=10_000
        )
        assert frame.get_attribute("data-run-id") == run_id

        page.locator("#workspace-update-action").click()
        expect(page.locator("#query-diagnostics-label")).to_have_text(
            "Ready", timeout=30_000
        )
        expect(page.locator("#workspace-update")).to_be_hidden()


@pytest.mark.e2e
def test_committed_parameter_content_and_stale_selection_export(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "content-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator(".dv-subtitle")).to_have_text("当前取数下限：0")

        parameter = page.locator(
            '#parameter-form input[name="min_query_revenue"]'
        )
        parameter.fill("150000")
        expect(frame.locator(".dv-subtitle")).to_have_text("当前取数下限：0")
        _run_and_wait(page)
        expect(frame.locator(".dv-subtitle")).to_have_text(
            "当前取数下限：150000",
            timeout=20_000,
        )

        inject_stale_state = """() => {
          const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
          const key = `dataviz.tab-ui.v2.${sessionId}`;
          const saved = JSON.parse(sessionStorage.getItem(key));
          saved.dashboards['sales-overview'].canvasSelections = {
            'view:deleted/value': ['stale'],
          };
          sessionStorage.setItem(key, JSON.stringify(saved));
        }"""
        page.evaluate(inject_stale_state)
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)
        _run_and_wait(page)
        page.wait_for_function(
            """() => {
              const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
              const saved = JSON.parse(
                sessionStorage.getItem(`dataviz.tab-ui.v2.${sessionId}`)
              );
              return !('view:deleted/value' in (
                saved.dashboards['sales-overview'].canvasSelections || {}
              ));
            }""",
            timeout=20_000,
        )
        remaining = page.evaluate(
            """() => {
              const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
              const saved = JSON.parse(
                sessionStorage.getItem(`dataviz.tab-ui.v2.${sessionId}`)
              );
              return Object.keys(
                saved.dashboards['sales-overview'].canvasSelections || {}
              );
            }"""
        )
        assert "view:deleted/value" not in remaining

        # Keep the restored stale key in memory by blocking the Canvas state
        # message. The export boundary must independently enforce the current
        # Dashboard contract instead of trusting sessionStorage.
        page.evaluate(inject_stale_state)
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)
        page.evaluate(
            """() => window.addEventListener('message', (event) => {
              if (event.data?.type === 'dataviz:selections-changed') {
                event.stopImmediatePropagation();
              }
            }, true)"""
        )
        _run_and_wait(page)
        with page.expect_request(
            lambda request: request.method == "POST" and request.url.endswith("/report"),
            timeout=20_000,
        ) as request_info:
            with page.expect_download(timeout=20_000) as download_info:
                page.locator("#download-button").click()
        download = download_info.value
        supplied = request_info.value.post_data_json["selections"]
        assert "view:deleted/value" not in supplied

        report_path = tmp_path / "parameter-report.html"
        download.save_as(report_path)
        report = report_path.read_text(encoding="utf-8")
        assert '<p class="dv-subtitle">当前取数下限：150000</p>' in report


@pytest.mark.e2e
def test_canvas_messages_are_bound_to_the_current_frame_instance(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "frame-message-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator(".dv-canvas")).to_be_visible(timeout=20_000)

        # A same-origin sibling iframe must not be able to mutate the active
        # Dashboard state, even when it copies the visible frame identity.
        page.evaluate(
            """async () => {
              const active = document.querySelector('#canvas-frame');
              const rogue = document.createElement('iframe');
              rogue.hidden = true;
              rogue.src = '/';
              document.body.append(rogue);
              await new Promise(resolve => rogue.addEventListener('load', resolve, {once:true}));
              const payload = {
                type:'dataviz:selections-changed',
                dashboard_id:active.dataset.dashboardId,
                run_id:active.dataset.runId,
                frame_id:active.dataset.frameId,
                selections:{'view:rogue/value':['wrong-source']},
              };
              rogue.contentWindow.eval(`parent.postMessage(${JSON.stringify(payload)}, location.origin)`);
            }"""
        )

        # A late message from the current WindowProxy but an older frame token
        # is rejected as well.
        frame.locator("body").evaluate(
            """() => parent.postMessage({
              type:'dataviz:selections-changed',
              dashboard_id:window.dataviz.dashboard_id,
              run_id:window.dataviz.run_id,
              frame_id:'frame_stale',
              selections:{'view:rogue/value':['wrong-generation']},
            }, location.origin)"""
        )
        page.wait_for_timeout(150)
        rogue_value = page.evaluate(
            """() => {
              const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
              const saved = JSON.parse(
                sessionStorage.getItem(`dataviz.tab-ui.v2.${sessionId}`)
              );
              return saved.dashboards['sales-overview'].canvasSelections?.['view:rogue/value'];
            }"""
        )
        assert rogue_value is None


@pytest.mark.e2e
def test_section_selection_updates_bound_title_without_redrawing_siblings(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "selection-content-workspace")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    trend = next(item for item in definition["sections"] if item["id"] == "trend")
    trend["title"] = "{{ controls.section.trend.focus_region }}趋势与结构"
    trend["controls"] = [
        {
            "id": "focus_region",
            "kind": "selection",
            "field": "region",
            "type": "single_select",
            "default": "华东",
            "options": {
                "mode": "static",
                "choices": [
                    {"label": "华东区域", "value": "华东"},
                    {"label": "华南区域", "value": "华南"},
                ],
            },
        }
    ]
    comparison = next(
        item for item in definition["views"] if item["id"] == "region-comparison"
    )
    comparison["description"] = (
        "当前分析：{{ controls.section.trend.focus_region }}"
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        title = frame.locator('[data-section-id="trend"] h2')
        description = frame.locator(
            '[data-view-id="region-comparison"] .dv-view-description'
        )
        expect(title).to_have_text("华东区域趋势与结构", timeout=20_000)
        expect(description).to_have_text("当前分析：华东区域")

        frame.locator("body").evaluate(
            """() => {
              const sibling = document.querySelector('[data-view-id="total-revenue"]');
              sibling.__selectionContentIdentity = crypto.randomUUID();
              const original = window.datavizRuntime.renderViews.bind(window.datavizRuntime);
              window.__selectionContentRenderCalls = [];
              window.datavizRuntime.renderViews = context => {
                window.__selectionContentRenderCalls.push(context.affectedViewIds);
                return original(context);
              };
            }"""
        )
        selector = frame.locator(
            'select[data-selection-input="section:trend/focus_region"]'
        )
        selector.select_option("华南", force=True)
        expect(title).to_have_text("华南区域趋势与结构", timeout=10_000)
        expect(description).to_have_text("当前分析：华南区域")
        affected = frame.locator("body").evaluate(
            "() => window.__selectionContentRenderCalls.at(-1)"
        )
        assert set(affected) == {"revenue-trend", "region-comparison"}
        assert frame.locator('[data-view-id="total-revenue"]').evaluate(
            "node => Boolean(node.__selectionContentIdentity)"
        )

        with page.expect_download(timeout=20_000) as download_info:
            page.locator("#download-button").click()
        report_path = tmp_path / "selection-content-report.html"
        download_info.value.save_as(report_path)
        report = report_path.read_text(encoding="utf-8")
        assert (
            '<h2 data-dv-content-field="sections.trend.title">'
            "华南区域趋势与结构</h2>"
        ) in report
        assert (
            'data-dv-content-field="views.region-comparison.description">'
            "当前分析：华南区域</p>"
        ) in report
        assert '"content_bindings": {' in report


@pytest.mark.e2e
def test_sources_inspector_exposes_resolved_and_parameterized_sql(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "source-evidence-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        page.locator('#parameter-form input[name="min_query_revenue"]').fill("150000")
        _run_and_wait(page)

        page.locator("#query-diagnostics > summary").click()
        source = page.locator('[data-node-id="source:sales"]')
        expect(source).to_be_visible()
        source.click()

        inspector = page.locator("#node-inspector")
        expect(inspector).to_be_visible()
        expect(inspector.locator("#node-inspector-title")).to_have_text("销售数据")
        expect(inspector).to_contain_text("Resolved SQL")
        expect(inspector).to_contain_text("revenue >= 150000")
        expect(inspector).to_contain_text("demo-duckdb · duckdb")
        expect(inspector).to_contain_text(
            "dashboards/sales-overview/sources/sales.sql"
        )

        inspector.locator(".node-inspector__driver > summary").click()
        expect(inspector).to_contain_text("Driver statement")
        expect(inspector).to_contain_text("$min_query_revenue")
        expect(inspector).to_contain_text('"min_query_revenue": 150000')


@pytest.mark.e2e
def test_sources_inspector_loads_structured_python_execution_log(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SALES, tmp_path / "python-log-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales")
        _run_and_wait(page)

        page.locator("#query-diagnostics > summary").click()
        transform = page.locator('[data-node-id="dataset:sales-metrics"]')
        expect(transform).to_be_visible()
        transform.click()

        inspector = page.locator("#node-inspector")
        expect(inspector).to_be_visible()
        expect(inspector.locator("#node-inspector-title")).to_have_text("销售衍生指标")
        expect(inspector).to_contain_text("Structured node log")
        expect(inspector).to_contain_text("dataviz/execution-log/v1")
        expect(inspector).to_contain_text("runtime_completed")


@pytest.mark.e2e
def test_web_component_reference_adapter_consumes_runtime_v2_without_canvas_runtime(
    page: Page,
):
    manifest = {
        "protocol": {"schema": "dataviz/runtime/v3", "component_registry_version": "3.0.0"},
        "selections": {"dashboard:probe/region": ["East"]},
        "view_specs": [{"id": "detail", "inputs": {"main": "source:data/main"}}],
        "dependency_contract": {
            "schema": "dataviz/dependency-contract/v2",
            "views": {
                "detail": {
                    "inputs": {"main": "source:data/main"},
                    "selection_contract": [
                        {
                            "key": "dashboard:probe/region",
                            "id": "region",
                            "origin": "dashboard",
                            "owner_id": "probe",
                            "definition": {"type": "multi_select", "path_fields": []},
                            "binding": {"field": "region", "operator": "auto"},
                        }
                    ],
                }
            },
        },
        "portable": {
            "outputs": {
                "source:data/main": [
                    {"region": "East", "value": 1},
                    {"region": "West", "value": 2},
                    {"region": "West", "value": 3},
                ]
            },
        },
    }
    adapter = (
        ROOT / "src" / "dataviz" / "server" / "static" / "runtime-web-component-adapter.js"
    ).read_text(encoding="utf-8")
    page.set_content(
        "<script>window.dataviz="
        + json.dumps(manifest)
        + "</script><script>"
        + adapter
        + "</script><dataviz-output id='count' view='detail' mode='count'></dataviz-output>"
    )
    expect(page.locator("#count")).to_have_text("1")
    assert page.evaluate("() => typeof window.datavizRuntime") == "undefined"
    page.evaluate(
        """() => {
          window.dataviz.selections['dashboard:probe/region'] = ['West'];
          window.dispatchEvent(new CustomEvent('dataviz:selectionchange'));
        }"""
    )
    expect(page.locator("#count")).to_have_text("2")


@pytest.mark.e2e
def test_component_gallery_story_overlay_keyboard_a11y_and_virtual_dom(
    page: Page, tmp_path: Path
):
    workspace = _copy_gallery_workspace(tmp_path)
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "component-gallery")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        detail = frame.locator('[data-view-id="detail-table"]')
        expect(detail).to_have_attribute("data-view-status", "ready", timeout=20_000)

        owner_contract = frame.locator("body").evaluate(
            """() => ({
              runtime: window.datavizRuntime.protocol,
              data: window.datavizRuntime.dataPipeline?.protocol,
              view: window.datavizRuntime.viewAdapter?.protocol,
              section: window.datavizRuntime.sectionAdapter?.protocol,
              presentation: window.datavizRuntime.presentationAdapter?.protocol,
              packages: [...(window.datavizComponents?.adapters?.keys() || [])],
            })"""
        )
        assert {
            owner_contract[key]
            for key in ("runtime", "data", "view", "section", "presentation")
        } == {"dataviz/runtime/v3"}
        assert {
            "data.pipeline", "view.declarative", "section.declarative", "presentation.shell"
        } <= set(owner_contract["packages"])

        header = page.locator("#dashboard-controls-control")
        header.locator("summary").click()

        text_control = header.locator('[data-control-component="input"]')
        expect(text_control.locator("input")).to_have_value("Review the selected cohort")
        text_control.locator("input").fill("Review East cohort")
        expect(text_control.locator(".dv-input__count")).to_contain_text("18 / 120")

        auto_complete = header.locator('[data-control-component="auto-complete"]')
        auto_input = auto_complete.locator("input")
        auto_input.focus()
        auto_input.fill("up")
        expect(auto_complete.locator('[role="listbox"]')).to_be_visible()
        auto_complete.get_by_role("option", name="Upside").click()
        expect(auto_input).to_have_value("Upside")

        input_number = header.locator('[data-control-component="input-number"]')
        input_number.get_by_role("button", name="Increase value").click()
        expect(input_number.locator('input[type="number"]')).to_have_value("60")

        boolean_checkbox = header.locator('[data-control-component="checkbox"]')
        boolean_checkbox.locator('input[type="checkbox"]').check()
        expect(boolean_checkbox.locator('input[type="checkbox"]')).to_be_checked()

        switch = header.locator('[data-control-component="switch"]')
        switch.get_by_role("switch").click()
        expect(switch.get_by_role("switch")).to_have_attribute("aria-checked", "false")

        date_picker = header.locator('[data-control-component="date-picker"]')
        date_picker.locator('input[type="date"]').fill("2026-03-02")
        expect(date_picker.locator('input[type="date"]')).to_have_value("2026-03-02")

        slider = header.locator('[data-control-component="slider"]')
        slider.locator('input[type="range"]').fill("0.85")
        expect(slider.locator(".dv-slider__input")).to_have_value("0.85")

        checkbox = header.locator('[data-control-component="checkbox-group"]')
        expect(checkbox).to_be_visible()
        action = checkbox.locator(".dv-checkbox-group__action")
        expect(action).to_have_text("Invert")
        assert checkbox.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 3
        checkbox.locator("button", has_text="East").click()
        assert "East" not in checkbox.locator("select").evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        )
        expect(action).to_have_text("Select all")
        action.click()
        assert checkbox.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 3
        expect(action).to_have_text("Invert")
        checkbox.locator("button", has_text="East").click()
        assert checkbox.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 2
        expect(action).to_have_text("Select all")
        action.click()
        action.click()
        assert checkbox.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 0
        checkbox.locator("button", has_text="South").click()
        assert checkbox.locator("select").evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        ) == ["South"]
        action.click()
        action.click()
        assert checkbox.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 0
        # The remaining component specimens derive their inferred option domains
        # from the selected Dataset. Restore the dashboard domain explicitly and
        # synchronize on the compiled Control state; Chromium used to reach the
        # following tree assertions before the queued empty-domain update, while
        # Firefox exposed that accidental ordering dependency.
        action.click()
        assert checkbox.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 3
        page.keyboard.press("Escape")
        expect(header).not_to_have_attribute("open", "")

        story_index = frame.locator(".gallery-story-index")
        expect(story_index).to_be_visible()
        expect(story_index.locator("summary")).to_contain_text("38 runtime specimens")

        expected_states = {
            "ready", "loading", "stale", "empty", "error", "cancelled", "unavailable"
        }
        for family in ("control", "compute", "view", "section"):
            matrix = frame.locator(f"#story-{family}-state-matrix")
            expect(matrix).to_be_visible()
            expect(matrix.locator(".gallery-state-card")).to_have_count(7)
            observed = set(
                matrix.locator(".gallery-state-card").evaluate_all(
                    "cards => cards.map(card => card.dataset.componentStatus)"
                )
            )
            assert observed == expected_states
            expect(
                matrix.locator('.gallery-state-card[data-gallery-status="loading"]')
            ).to_have_attribute("aria-busy", "true")
            expect(
                matrix.locator('.gallery-state-card[data-gallery-status="error"]')
            ).to_have_attribute("aria-invalid", "true")
            expect(
                matrix.locator('.gallery-state-card[data-gallery-status="unavailable"]')
            ).to_have_attribute("aria-disabled", "true")

        selections = detail.locator('.dv-context-controls[data-control-origin="view"]')
        selections.locator("summary").click()
        expect(selections).to_have_attribute("open", "")
        tree = selections.locator('[data-control-component="tree-select"]')
        expect(tree.locator("xpath=ancestor::*[@data-selection-key][1]")).to_have_attribute(
            "data-option-domain-state", "ready"
        )
        tree.locator("[data-control-trigger]").click()
        panel = tree.locator("[data-control-panel]")
        expect(panel).to_be_visible()
        geometry = panel.evaluate(
            """panel => {
              const rect = panel.getBoundingClientRect();
              return {
                left:rect.left, top:rect.top, right:rect.right, bottom:rect.bottom,
                width:rect.width, height:rect.height,
                viewport:[document.documentElement.clientWidth, document.documentElement.clientHeight],
              };
            }"""
        )
        assert geometry["left"] >= 8
        assert geometry["top"] >= 8
        assert geometry["right"] <= geometry["viewport"][0] - 8
        assert geometry["bottom"] <= geometry["viewport"][1] - 8
        assert geometry["width"] >= 320

        tree.locator(".dv-choice-search").press("Escape")
        expect(panel).to_be_hidden()
        assert tree.locator("[data-control-trigger]").evaluate(
            "trigger => document.activeElement === trigger"
        )
        tree.locator("[data-control-trigger]").click()
        tree_branch = tree.locator(".dv-tree-branch__check").first
        tree_branch.click()
        assert tree.locator("select").evaluate(
            "select => select.selectedOptions.length > 0"
        )
        tree_summary = tree.locator("[data-control-summary]")
        expect(tree_summary).to_have_text(re.compile(r"\S"))
        # Selecting the only available parent is canonically "all available";
        # otherwise show_checked_strategy=parent emits compact parent tags. Both
        # summaries must avoid leaking full leaf paths into the trigger.
        assert " / " not in tree_summary.inner_text()
        tree.locator("footer button", has_text="Clear").click()
        assert tree.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 0
        tree.locator(".dv-choice-search").press("Escape")

        radio = selections.locator('[data-control-component="radio-group"]')
        expect(radio.get_by_role("button", name="All", exact=True)).to_have_count(0)
        expect(radio.get_by_role("button", name="Clear", exact=True)).to_have_count(0)
        radio.locator("button", has_text="Software").press("Enter")
        expect(radio.locator("select")).to_have_value("Software")

        grouped_select = selections.locator(
            '[data-selection-key="view:detail-table/product"] [data-control-component="select"]'
        )
        grouped_select.locator("[data-control-trigger]").click()
        select_panel = grouped_select.locator(".dv-select-panel")
        expect(select_panel).to_be_visible()
        panel_surface = select_panel.evaluate(
            """panel => ({
              sharedClass: panel.classList.contains('dv-control-panel'),
              background: getComputedStyle(panel).backgroundColor,
            })"""
        )
        assert panel_surface["sharedClass"] is True
        assert panel_surface["background"] not in {"transparent", "rgba(0, 0, 0, 0)"}
        assert grouped_select.locator(".dv-select-group").all_text_contents() == [
            "Core", "New"
        ]
        grouped_select.locator(".dv-choice-search").fill("Growth")
        expect(grouped_select.locator("footer small")).to_contain_text("2 matching")
        grouped_action = grouped_select.locator(
            ".dv-select-footer__actions button"
        ).first
        expect(grouped_action).to_have_text("Select all")
        grouped_action.click()
        assert grouped_select.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 2
        expect(grouped_action).to_have_text("Invert")
        grouped_action.click()
        assert grouped_select.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 0
        grouped_select.locator(".dv-choice-search").press("Escape")

        cascader = selections.locator('[data-control-component="cascader"]')
        cascader.locator("[data-control-trigger]").click()
        branch_check = cascader.locator(".dv-cascader-branch__check").first
        expect(branch_check).to_be_visible()
        branch_check.click()
        assert cascader.locator("select").evaluate(
            "select => select.selectedOptions.length > 0"
        )
        cascader_summary = cascader.locator("[data-control-summary]")
        expect(cascader_summary).to_have_text(re.compile(r"\S"))
        assert " / " not in cascader_summary.inner_text()
        cascader.locator(".dv-choice-search").press("Escape")

        range_picker = selections.locator('[data-control-component="range-picker"]')
        expect(range_picker.locator('[data-control-trigger]')).to_have_count(1)
        expect(range_picker.locator('input[type="date"]')).to_have_count(0)
        range_picker.locator('[data-control-trigger]').click()
        date_panel = range_picker.locator('[data-control-panel]')
        expect(date_panel).to_be_visible()
        expect(date_panel).to_have_attribute("role", "dialog")
        expect(date_panel.locator(".dv-date-range__month")).to_have_count(2)
        range_picker.locator("button", has_text="Q1 2026").click()
        expect(range_picker.locator("input[data-selection-input]")).to_have_value(
            "2026-01-01,2026-03-31"
        )
        expect(date_panel).to_be_hidden()
        range_picker.locator('[data-control-trigger]').click()
        date_panel.locator('[data-date="2026-01-10"]').click()
        expect(date_panel).to_be_visible()
        date_panel.locator('[data-date="2026-01-20"]').click()
        expect(range_picker.locator("input[data-selection-input]")).to_have_value(
            "2026-01-10,2026-01-20"
        )
        expect(date_panel).to_be_hidden()
        range_picker.locator('[data-control-trigger]').click()
        range_picker.locator("button", has_text="Clear").click()
        expect(range_picker.locator("input[data-selection-input]")).to_have_value("")
        frame.locator("body").evaluate(
            """() => new Promise((resolve, reject) => {
              const deadline = performance.now() + 3000;
              const check = () => {
                const value = window.dataviz.selections['view:detail-table/date-window'];
                if (Array.isArray(value) && value.length === 0) return resolve();
                if (performance.now() > deadline) return reject(new Error(JSON.stringify(value)));
                setTimeout(check, 25);
              };
              check();
            })"""
        )
        expect(detail).not_to_contain_text("No rows match the current selections")

        # The Gallery owns three real scale Stories. The 1,000-option Story uses
        # a canonical native select while keeping the enhanced row DOM bounded.
        expect(frame.locator("#story-control-scale-10 select option")).to_have_count(10)
        expect(frame.locator("#story-control-scale-100 select option")).to_have_count(100)
        expect(frame.locator("#story-control-scale-1000 select option")).to_have_count(1000)
        virtual = frame.locator("#story-control-scale-1000 .dv-control")
        virtual.locator("[data-control-trigger]").click()
        expect(virtual.locator("[data-control-panel]")).to_be_visible()
        rendered = virtual.locator(".dv-select-rows .dv-choice-option").count()
        assert 1 <= rendered < 40
        virtual.locator(".dv-choice-search").fill("Store 1000")
        expect(virtual.locator(".dv-select-panel footer small")).to_contain_text("1 matching")
        assert virtual.locator(".dv-select-rows .dv-choice-option").count() == 1
        virtual.locator(".dv-choice-search").press("ArrowDown")
        virtual.locator(".dv-select-options").press("Enter")
        expect(virtual.locator("select")).to_have_values(["1000"])
        assert virtual.locator("[data-control-trigger]").evaluate(
            """trigger => {
              const panel = document.getElementById(trigger.getAttribute('aria-controls'));
              return Boolean(trigger.getAttribute('aria-haspopup') === 'listbox'
                && trigger.getAttribute('aria-expanded') === 'true'
                && panel?.getAttribute('role') === null
                && panel?.querySelector('[role="listbox"]'));
            }"""
        )

        # Context Overlay uses the same outside-click controller.
        frame.locator(".dv-section--band").click(position={"x": 10, "y": 10})
        expect(selections).not_to_have_attribute("open", "")

        contract = frame.locator("body").evaluate(
            """async () => window.datavizRuntime.testRenderer('gallery.spark', [
              {type:'gallery.spark', rows:[{revenue:1, store_id:'S01', month:'2026-01'}]},
              {type:'gallery.spark', rows:[]},
            ])"""
        )
        assert contract["valid"] is True

        # A lifecycle failure stays in its View and exposes a structured boundary.
        frame.locator("body").evaluate(
            """() => {
              window.datavizRuntime.renderers.get('gallery.spark').update = () => {
                throw new Error('expected renderer failure');
              };
            }"""
        )
        page.locator('select[name="dashboard:component-gallery/region"]').select_option(
            ["East"], force=True
        )
        custom = frame.locator('[data-view-id="custom-specimen"]')
        expect(custom).to_have_attribute("data-view-status", "error", timeout=10_000)
        boundary = frame.locator("body").evaluate(
            """() => window.datavizRuntime.rendererErrors.get('custom-specimen')"""
        )
        assert boundary["code"] == "renderer_lifecycle_error"
        assert boundary["phase"] == "update"
        assert boundary["renderer"] == "gallery.spark"
        expect(frame.locator('[data-view-id="narrative"]')).to_have_attribute(
            "data-view-status", "ready"
        )


@pytest.mark.e2e
def test_query_control_tray_is_responsive_bounded_and_selector_safe(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "adaptive-control-tray")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["query_parameters"].extend(
        {
            "id": f"scenario_{index:02d}",
            "type": "number",
            "label": f"Scenario {index:02d}",
            "default": index,
        }
        for index in range(1, 24)
    )
    definition["query_parameters"].append(
        {
            "id": "model_list",
            "type": "multi_select",
            "label": "Model list",
            "default": ["model-01"],
            "options": {
                "mode": "static",
                "choices": [
                    {"label": f"Model {index:02d}", "value": f"model-{index:02d}"}
                    for index in range(1, 13)
                ],
            },
        }
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    presentation_path = workspace / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation["control_panels"] = {
        "query": {
            "template": "grid",
            "width": "wide",
            "columns": 3,
            "density": "compact",
        }
    }
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    page.set_viewport_size({"width": 900, "height": 360})
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        control = page.locator("#query-parameters-control")
        toggle = page.locator("#query-parameters-toggle")
        panel = control.locator(".header-control__popover")
        form = control.locator("#parameter-form")
        canvas = page.locator(".canvas-panel")
        expect(panel).to_be_visible()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        expect(panel).not_to_have_attribute("data-overlay-placement", re.compile(".+"))

        geometry = panel.evaluate(
            """panel => {
              const form = panel.querySelector('#parameter-form');
              const rect = panel.getBoundingClientRect();
              return {
                position:getComputedStyle(panel).position,
                width:rect.width,
                ownerWidth:panel.parentElement.getBoundingClientRect().width,
                columns: getComputedStyle(form).gridTemplateColumns.split(' ').length,
                formClientHeight: form.clientHeight,
                formScrollHeight: form.scrollHeight,
                panelOverflow: getComputedStyle(panel).overflow,
                formOverflow: getComputedStyle(form).overflow,
              };
            }"""
        )
        assert geometry["position"] == "relative", geometry
        assert abs(geometry["width"] - geometry["ownerWidth"]) <= 1, geometry
        assert geometry["columns"] == 3
        assert geometry["panelOverflow"] == "hidden"
        assert geometry["formOverflow"] == "auto"
        assert geometry["formScrollHeight"] > geometry["formClientHeight"]

        expanded_canvas_top = canvas.bounding_box()["y"]
        page.keyboard.press("Escape")
        expect(panel).to_be_visible()
        toggle.click()
        expect(panel).to_be_hidden()
        expect(toggle).to_have_attribute("aria-expanded", "false")
        collapsed_canvas_top = canvas.bounding_box()["y"]
        assert collapsed_canvas_top < expanded_canvas_top - 40
        toggle.click()
        expect(panel).to_be_visible()
        expect(toggle).to_have_attribute("aria-expanded", "true")

        form.evaluate("form => { form.scrollTop = form.scrollHeight; }")
        model_field = form.locator(".field", has=page.locator("#input-model_list"))
        trigger = model_field.locator("[data-control-trigger]")
        expect(trigger).to_be_visible()
        trigger.click()
        selector_panel = model_field.locator("[data-control-panel]")
        expect(selector_panel).to_be_visible()
        selector_geometry = selector_panel.evaluate(
            """panel => {
              const rect = panel.getBoundingClientRect();
              const style = getComputedStyle(panel);
              return {top:rect.top, right:rect.right, bottom:rect.bottom, left:rect.left,
                panelHeight:rect.height, maxHeight:style.maxHeight,
                boxSizing:style.boxSizing,
                clientHeight:document.documentElement.clientHeight,
                visualHeight:visualViewport?.height || null,
                width:innerWidth, height:innerHeight};
            }"""
        )
        assert selector_geometry["top"] >= 11
        assert selector_geometry["left"] >= 11
        assert selector_geometry["right"] <= selector_geometry["width"] - 11
        assert selector_geometry["bottom"] <= selector_geometry["height"] - 11, selector_geometry

        page.keyboard.press("Escape")
        expect(selector_panel).to_be_hidden()
        toggle.click()
        expect(panel).to_be_hidden()
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#query-parameters-toggle")).to_have_attribute(
            "aria-expanded", "false", timeout=10_000
        )
        expect(page.locator("#query-parameters-panel")).to_be_hidden()


@pytest.mark.e2e
def test_cross_browser_narrow_control_overlay_keyboard_scroll_and_aria(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "narrow-control-matrix")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["query_parameters"].extend(
        {
            "id": f"scenario_{index:02d}",
            "type": "number",
            "label": f"Scenario {index:02d}",
            "default": index,
        }
        for index in range(1, 16)
    )
    definition["query_parameters"].append(
        {
            "id": "model_list",
            "type": "multi_select",
            "label": "Model list",
            "default": ["model-01"],
            "options": {
                "mode": "static",
                "choices": [
                    {"label": f"Model {index:02d}", "value": f"model-{index:02d}"}
                    for index in range(1, 31)
                ],
            },
        }
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    presentation_path = workspace / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation["control_panels"] = {
        "query": {
            "template": "grid",
            "width": "wide",
            "columns": 3,
            "density": "compact",
        }
    }
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    page.set_viewport_size({"width": 390, "height": 520})
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        control = page.locator("#query-parameters-control")
        toggle = page.locator("#query-parameters-toggle")
        panel = control.locator(".header-control__popover")
        form = control.locator("#parameter-form")
        expect(panel).to_be_visible()
        expect(toggle).to_have_attribute("aria-expanded", "true")

        geometry = panel.evaluate(
            """panel => {
              const form = panel.querySelector('#parameter-form');
              const rect = panel.getBoundingClientRect();
              return {
                left:rect.left, top:rect.top, right:rect.right, bottom:rect.bottom,
                height:rect.height,
                viewport:[innerWidth, innerHeight],
                columns:getComputedStyle(form).gridTemplateColumns.split(' ').length,
                formClientHeight:form.clientHeight,
                formScrollHeight:form.scrollHeight,
                formOverflow:getComputedStyle(form).overflowY,
              };
            }"""
        )
        assert geometry["left"] >= 8, geometry
        assert geometry["top"] >= 8, geometry
        assert geometry["right"] <= geometry["viewport"][0] - 8, geometry
        assert geometry["height"] <= geometry["viewport"][1] * 0.52 + 1, geometry
        assert geometry["columns"] == 1, geometry
        assert geometry["formScrollHeight"] > geometry["formClientHeight"], geometry
        assert geometry["formOverflow"] == "auto", geometry

        form.evaluate("form => { form.scrollTop = form.scrollHeight; }")
        model_field = form.locator(".field", has=page.locator("#input-model_list"))
        trigger = model_field.locator("[data-control-trigger]")
        expect(trigger).to_be_visible()
        trigger.click()
        selector_panel = model_field.locator("[data-control-panel]")
        expect(selector_panel).to_be_visible()
        selector_geometry = selector_panel.evaluate(
            """panel => {
              const rect = panel.getBoundingClientRect();
              return {
                left:rect.left, top:rect.top, right:rect.right, bottom:rect.bottom,
                viewport:[innerWidth, innerHeight],
                background:getComputedStyle(panel).backgroundColor,
              };
            }"""
        )
        assert selector_geometry["left"] >= 8, selector_geometry
        assert selector_geometry["top"] >= 8, selector_geometry
        assert selector_geometry["right"] <= selector_geometry["viewport"][0] - 8, selector_geometry
        assert selector_geometry["bottom"] <= selector_geometry["viewport"][1] - 8, selector_geometry
        assert selector_geometry["background"] not in {"transparent", "rgba(0, 0, 0, 0)"}
        assert trigger.evaluate(
            """trigger => {
              const controlled = document.getElementById(trigger.getAttribute('aria-controls'));
              return trigger.getAttribute('aria-expanded') === 'true'
                && trigger.getAttribute('aria-haspopup') === 'listbox'
                && Boolean(controlled?.querySelector('[role="listbox"]'));
            }"""
        )

        search = model_field.locator(".dv-choice-search")
        search.fill("Model 30")
        search.press("ArrowDown")
        model_field.locator('[role="listbox"]').press("Enter")
        expect(model_field.locator("select")).to_have_values(["model-01", "model-30"])
        search.press("Escape")
        expect(selector_panel).to_be_hidden()
        assert trigger.evaluate("trigger => document.activeElement === trigger")
        page.mouse.click(2, 510)
        expect(panel).to_be_visible()
        page.keyboard.press("Escape")
        expect(panel).to_be_visible()
        toggle.click()
        expect(panel).to_be_hidden()
        expect(toggle).to_have_attribute("aria-expanded", "false")
        page.locator("#run-button").click()


@pytest.mark.e2e
def test_server_header_hydrates_dataset_driven_dashboard_selection_options(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "dynamic-dashboard-selection")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"][0].pop("default")
    definition["controls"][0]["options"] = {"mode": "infer"}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        header = page.locator("#dashboard-controls-control")
        header.locator("summary").click()
        selector = header.locator(
            'select[name="dashboard:sales-overview/region"]'
        )
        expect(selector).to_have_attribute("data-value-encoding", "string")
        expect(selector.locator("option")).to_have_count(3, timeout=20_000)
        assert selector.evaluate(
            "select => [...select.options].map(option => option.value).sort()"
        ) == ["华东", "华北", "华南"]
        assert selector.evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        ) == ["华东", "华北", "华南"]

        selector.select_option(["华南"], force=True)
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator('[data-view-id="total-revenue"]')).to_contain_text(
            "449,000", timeout=10_000
        )


@pytest.mark.e2e
def test_unified_dashboard_controls_drive_browser_named_output(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "showcase-controls")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        control = page.locator("#dashboard-controls-control")
        expect(control.locator("#dashboard-control-meta")).to_have_text(
            "1 data · 1 logic"
        )
        control.locator("summary").click()
        expect(
            control.locator('.dashboard-control-group[data-control-kind="selection"]')
        ).to_be_visible()
        expect(
            control.locator('.dashboard-control-group[data-control-kind="compute"]')
        ).to_be_visible()

        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        radial = frame.locator('[data-view-id="radial"]')
        expect(radial).to_have_attribute("data-view-status", "ready", timeout=15_000)

        province = page.locator(
            'select[name="dashboard:chart-gallery/province"]'
        )
        province.select_option(["广东"], force=True)
        page.wait_for_function(
            """() => {
              const frame = document.querySelector('#canvas-frame').contentWindow;
              const output = frame.dataviz.portable.outputs['interactive:latest-metrics/main'];
              return Array.isArray(output) && output.length > 0
                && output.every(row => row.province === '广东');
            }""",
            timeout=15_000,
        )

        control.locator("summary").click()
        city_count = page.locator(
            'input[name="dashboard:chart-gallery/radar_city_count"]'
        )
        city_count.fill("1")
        page.wait_for_function(
            """() => {
              const frame = document.querySelector('#canvas-frame').contentWindow;
              const output = frame.dataviz.portable.outputs['interactive:latest-metrics/main'];
              return frame.dataviz.compute_parameters['dashboard:chart-gallery/radar_city_count'] === 1
                && Array.isArray(output) && output.length === 1
                && output[0].province === '广东';
            }""",
            timeout=15_000,
        )
        expect(radial).to_have_attribute("data-view-status", "ready")
        page.locator("#query-diagnostics > summary").click()
        expect(control).not_to_have_attribute("open", "")


@pytest.mark.e2e
def test_selection_cascade_popovers_view_isolation_and_table_wheel(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "showcase")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "cascade-explorer")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        expect(
            frame.locator('[data-view-id="map-bars"][data-view-status="ready"]')
        ).to_be_visible(timeout=15_000)

        # Header and Canvas-owned popovers both close when focus moves elsewhere.
        header = page.locator("#dashboard-controls-control")
        header.locator("summary").click()
        expect(header).to_have_attribute("open", "")
        province = header.locator('[data-control-component="checkbox-group"]')
        province_action = province.locator(".dv-checkbox-group__action")
        expect(province_action).to_have_text("反选")
        province_action.click()
        expect(province_action).to_have_text("全选")
        assert province.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 0
        province_action.click()
        expect(province_action).to_have_text("反选")
        assert province.locator("select").evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        ) == ["广东", "福建"]
        province.locator("button", has_text="广东").click()
        expect(province_action).to_have_text("全选")
        assert province.locator("select").evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        ) == ["福建"]
        province_action.click()
        expect(province_action).to_have_text("反选")
        frame.locator('[data-view-id="map-bars"] .dv-view-body').click()
        expect(header).not_to_have_attribute("open", "")

        section_popover = frame.locator(
            '.dv-context-controls[data-control-origin="section"]'
        )
        section_popover.locator("summary").click()
        expect(section_popover).to_have_attribute("open", "")
        frame.locator(".cascade-hero").click()
        expect(section_popover).not_to_have_attribute("open", "")

        dashboard_select = page.locator(
            'select[name="dashboard:cascade-explorer/province"]'
        )
        city_select = frame.locator(
            'select[data-selection-input="section:geography/city"]'
        )
        city_rows = frame.locator('[data-view-id="city-detail"] tbody tr')
        expect(city_select).to_have_count(1)
        expect(city_select.locator("option:not([disabled])")).to_have_count(4)
        assert set(city_select.evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        )) == {"深圳", "佛山", "厦门", "泉州"}
        expect(city_rows).to_have_count(7)
        dashboard_select.select_option(["福建"], force=True)
        expect(city_select).to_have_values(["厦门", "泉州"], timeout=5_000)
        expect(city_rows).to_have_count(3, timeout=5_000)
        enabled_cities = city_select.evaluate(
            "select => [...select.options].filter(option => !option.disabled).map(option => option.value)"
        )
        assert enabled_cities == ["厦门", "泉州"]
        assert frame.locator("body").evaluate(
            "() => window.dataviz.selection_intents['section:geography/city']"
        ) == "all_available"

        dashboard_select.select_option(["广东", "福建"], force=True)
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow.document
              .querySelector('select[data-selection-input="section:geography/city"]')
              ?.selectedOptions.length === 4"""
        )
        assert set(city_select.evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        )) == {"深圳", "佛山", "厦门", "泉州"}
        expect(city_rows).to_have_count(7, timeout=5_000)

        # Explicit subsets keep their identity even if an upstream contraction
        # temporarily makes that subset equal to the complete available domain.
        city_select.select_option(["厦门"], force=True)
        expect(city_rows).to_have_count(2, timeout=5_000)
        assert frame.locator("body").evaluate(
            "() => window.dataviz.selection_intents['section:geography/city']"
        ) == "explicit"
        dashboard_select.select_option(["福建"], force=True)
        expect(city_select).to_have_values(["厦门"], timeout=5_000)
        dashboard_select.select_option(["广东", "福建"], force=True)
        expect(city_select).to_have_values(["厦门"], timeout=5_000)
        expect(city_rows).to_have_count(2, timeout=5_000)

        city_select.select_option(["深圳", "厦门"], force=True)
        page.wait_for_function(
            """() => {
              const values = document.querySelector('#canvas-frame').contentWindow.dataviz
                .selections['section:geography/city'];
              return values.length === 2 && values.includes('深圳') && values.includes('厦门');
            }"""
        )
        assert set(city_select.evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        )) == {"深圳", "厦门"}
        view_popover = frame.locator(
            '[data-view-id="city-detail"] .dv-context-controls[data-control-origin="view"]'
        )
        view_popover.locator("summary").click()
        cascader = view_popover.locator('[data-control-component="cascader"]')
        cascader.locator("[data-control-trigger]").click()
        cascader.locator("footer button", has_text="Clear").click()
        columns = cascader.locator(".dv-cascader-columns")

        columns.locator(".dv-cascader-column").nth(0).locator(
            "button", has_text="广东"
        ).click()
        columns.locator(".dv-cascader-column").nth(1).locator(
            "button", has_text="深圳"
        ).click()
        columns.locator(".dv-cascader-column").nth(2).locator(
            "button", has_text="南山区"
        ).click()
        columns.locator(".dv-cascader-column").nth(0).locator(
            "button", has_text="福建"
        ).click()
        columns.locator(".dv-cascader-column").nth(1).locator(
            "button", has_text="厦门"
        ).click()
        columns.locator(".dv-cascader-column").nth(2).locator(
            "button", has_text="思明区"
        ).click()

        district_select = frame.locator(
            'select[data-selection-input="view:city-detail/district"]'
        )
        selected_paths = district_select.evaluate(
            "select => [...select.selectedOptions].map(option => JSON.parse(option.value))"
        )
        assert selected_paths == [
            ["广东", "深圳", "南山区"],
            ["福建", "厦门", "思明区"],
        ]

        # A parent change prunes both unavailable choices and stale selected paths.
        dashboard_select.select_option(["福建"], force=True)
        expect(city_select).to_have_values(["厦门"], timeout=5_000)
        page.wait_for_function(
            """() => {
              const frame = document.querySelector('#canvas-frame').contentWindow;
              const select = frame.document.querySelector('select[data-selection-input="view:city-detail/district"]');
              return select && [...select.selectedOptions].every(option => JSON.parse(option.value)[0] === '福建');
            }"""
        )

        # Instrument the public Runtime boundary: a View-scoped Selection Control may redraw
        # city-detail, but must not touch the sibling map-bars renderer.
        frame.locator("body").evaluate(
            """() => {
              const original = window.datavizRuntime.renderViews.bind(window.datavizRuntime);
              window.__datavizRenderCalls = [];
              window.datavizRuntime.renderViews = context => {
                window.__datavizRenderCalls.push(context.affectedViewIds);
                return original(context);
              };
            }"""
        )
        frame.locator('input[data-selection-input="view:city-detail/min_value"]').evaluate(
            """input => {
              input.value = '70';
              input.dispatchEvent(new Event('change', {bubbles:true}));
            }"""
        )
        page.wait_for_timeout(250)
        affected = frame.locator("body").evaluate(
            "() => window.__datavizRenderCalls.at(-1)"
        )
        assert affected == ["city-detail"]

        # A short basic table releases a vertical wheel to the Canvas page.
        scroll_after = frame.locator(
            '[data-view-id="city-detail"] .dv-table-wrap'
        ).evaluate(
            """host => {
              window.scrollTo(0, 0);
              host.dispatchEvent(new WheelEvent('wheel', {
                deltaY: 500, bubbles: true, cancelable: true, composed: true
              }));
              return window.scrollY;
            }"""
        )
        assert scroll_after > 0


@pytest.mark.e2e
def test_plotly_defaults_to_page_wheel_and_allows_explicit_scroll_zoom(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "plotly-wheel")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    dashboard = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    explicit_view = next(
        view for view in dashboard["views"] if view["id"] == "region-comparison"
    )
    explicit_view["config"] = {"scrollZoom": True}
    dashboard_path.write_text(
        yaml.safe_dump(dashboard, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        default_chart = frame.locator('[data-view-id="revenue-trend"] .dv-plotly')
        explicit_chart = frame.locator('[data-view-id="region-comparison"] .dv-plotly')
        expect(default_chart).to_be_visible(timeout=15_000)
        expect(explicit_chart).to_be_visible(timeout=15_000)

        assert default_chart.evaluate("node => node._context.scrollZoom") is False
        assert explicit_chart.evaluate("node => node._context.scrollZoom") is True

        default_chart.scroll_into_view_if_needed()
        before = default_chart.evaluate(
            """node => ({
              scrollY:window.scrollY,
              xRange:[...node._fullLayout.xaxis.range],
            })"""
        )
        drag_layer = default_chart.locator(".nsewdrag")
        box = drag_layer.bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(150)
        after = default_chart.evaluate(
            """node => ({
              scrollY:window.scrollY,
              xRange:[...node._fullLayout.xaxis.range],
            })"""
        )
        assert after["scrollY"] > before["scrollY"]
        assert after["xRange"] == before["xRange"]


@pytest.mark.e2e
def test_perspective_fills_view_uses_opaque_settings_and_releases_page_wheel(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "minimal")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    dashboard_path.write_text(
        dashboard_path.read_text(encoding="utf-8").replace(
            "settings: false", "settings: true"
        ),
        encoding="utf-8",
    )
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        perspective = frame.locator('[data-view-id="sales-perspective"]')
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
        viewer = perspective.locator("perspective-viewer")
        expect(viewer).to_have_count(1, timeout=30_000)

        dimensions = viewer.evaluate(
            """viewer => ({
              body: viewer.closest('.dv-view-body').getBoundingClientRect().height,
              viewer: viewer.getBoundingClientRect().height,
            })"""
        )
        assert dimensions["body"] >= 320
        assert abs(dimensions["body"] - dimensions["viewer"]) <= 1

        settings_surface = viewer.evaluate(
            """viewer => {
              const panel = viewer.shadowRoot.querySelector('#settings_panel');
              const style = getComputedStyle(panel);
              return {
                color: style.backgroundColor,
                image: style.backgroundImage,
              };
            }"""
        )
        assert settings_surface["color"] == "rgb(255, 255, 255)"
        assert settings_surface["image"] == "none"

        plugin_choice = viewer.locator(
            '.plugin-select-item[data-plugin="Datagrid"]'
        )
        expect(plugin_choice).to_be_visible(timeout=10_000)
        plugin_choice.click()
        expect(viewer.locator("#plugin_selector_container")).to_have_class(
            re.compile(r"\bopen\b")
        )

        identity = viewer.evaluate(
            "viewer => (viewer.__datavizTestIdentity = crypto.randomUUID())"
        )
        dashboard_select = page.locator(
            'select[name="dashboard:sales-overview/region"]'
        )
        dashboard_select.select_option(["华东"], force=True)
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .datavizRuntime.metrics.perspective.updated >= 1"""
        )
        assert viewer.evaluate(
            "viewer => viewer.__datavizTestIdentity"
        ) == identity

        scroll_after = viewer.evaluate(
            """viewer => {
              window.scrollTo(0, 0);
              viewer.dispatchEvent(new WheelEvent('wheel', {
                deltaY: 500, bubbles: true, cancelable: true, composed: true
              }));
              return window.scrollY;
            }"""
        )
        assert scroll_after > 0

        disposed = frame.locator("body").evaluate(
            """async () => {
              window.datavizRuntime.dispose();
              await new Promise(resolve => setTimeout(resolve, 100));
              return window.datavizRuntime.metrics.perspective.disposed;
            }"""
        )
        assert disposed >= 1


@pytest.mark.e2e
def test_cross_browser_perspective_repeated_dispose_and_restore(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "perspective-restore-matrix")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        for _cycle in range(3):
            page.wait_for_timeout(300)
            frame = page.frame_locator("#canvas-frame")
            perspective = frame.locator('[data-view-id="sales-perspective"]')
            expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
            viewer = perspective.locator("perspective-viewer")
            expect(viewer).to_be_visible(timeout=30_000)
            scroll_after = viewer.evaluate(
                """viewer => {
                  window.scrollTo(0, 0);
                  viewer.dispatchEvent(new WheelEvent('wheel', {
                    deltaY:500, bubbles:true, cancelable:true, composed:true,
                  }));
                  return window.scrollY;
                }"""
            )
            assert scroll_after > 0
            frame_id = page.locator("#canvas-frame").get_attribute("data-frame-id")
            disposed = frame.locator("body").evaluate(
                """async () => {
                  const runtime = window.datavizRuntime;
                  runtime.dispose();
                  const deadline = performance.now() + 5000;
                  while (
                    runtime.metrics.perspective.disposed < runtime.metrics.perspective.created
                    && performance.now() < deadline
                  ) await new Promise(resolve => setTimeout(resolve, 20));
                  return structuredClone(runtime.metrics.perspective);
                }"""
            )
            assert disposed["created"] >= 1
            assert disposed["disposed"] == disposed["created"]
            page.locator("#dashboard-reload").click()
            page.wait_for_function(
                "previous => document.querySelector('#canvas-frame')?.dataset.frameId !== previous",
                arg=frame_id,
                timeout=15_000,
            )
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready")


@pytest.mark.e2e
def test_required_dynamic_view_selection_bootstraps_from_base_output_and_exports(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(WORKER, tmp_path / "dynamic-view-domain")
    dashboard_path = workspace / "dashboards" / "worker-runtime" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["views"][0]["controls"] = [
        {
            "id": "focus_name",
            "kind": "selection",
            "type": "single_select",
            "field": "name",
            "required": True,
            "options": {"mode": "infer"},
        }
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    transform_path = workspace / "dashboards" / "worker-runtime" / "transforms" / "scaled.yaml"
    transform = yaml.safe_load(transform_path.read_text(encoding="utf-8"))
    transform["selection_inputs"] = {
        "focus_name": "view:scaled-table/focus_name",
    }
    transform_path.write_text(
        yaml.safe_dump(transform, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    console_errors: list[str] = []
    report_responses: list[tuple[int, str]] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on(
        "response",
        lambda response: report_responses.append((response.status, response.url))
        if "/report" in response.url
        else None,
    )
    report_path = tmp_path / "dynamic-view-domain.html"
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "worker-runtime")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        table = frame.locator('[data-view-id="scaled-table"]')
        expect(table).to_have_attribute("data-view-status", "ready", timeout=15_000)
        expect(table.locator("tbody")).to_contain_text("alpha")
        expect(table.locator("tbody")).not_to_contain_text("beta")
        selector = frame.locator(
            'select[data-selection-input="view:scaled-table/focus_name"]'
        )
        expect(selector.locator("option")).to_have_count(2)
        expect(selector.locator('option[data-empty-option="true"]')).to_have_count(0)
        assert selector.input_value() == "alpha"
        expect(page.locator('[data-node-id="interactive:scaled"]')).to_have_attribute(
            "data-status", "ready", timeout=10_000
        )
        assert not [message for message in console_errors if "[dataviz:init]" in message]

        # A delayed parent shadow must never override the canonical Canvas
        # state used for report export. Firefox made this race reproducible;
        # inject it explicitly so every browser guards the protocol invariant.
        frame.locator("body").evaluate(
            """() => window.parent.postMessage({
              type:'dataviz:selections-changed',
              dashboard_id:window.dataviz.dashboard_id,
              run_id:window.dataviz.run_id,
              frame_id:window.dataviz.frame_id,
              selections:{},
              selection_intents:{},
            }, window.location.origin)"""
        )

        try:
            with page.expect_download(timeout=30_000) as download_info:
                page.locator("#download-button").click()
        except PlaywrightTimeoutError as error:
            raise AssertionError(
                {
                    "run_message": page.locator("#run-message").inner_text(),
                    "report_responses": report_responses,
                    "console_errors": console_errors,
                }
            ) from error
        download_info.value.save_as(report_path)

    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        exported = page.locator('[data-view-id="scaled-table"]')
        expect(exported).to_have_attribute("data-view-status", "ready", timeout=15_000)
        expect(exported.locator("tbody")).to_contain_text("alpha")
        expect(exported).not_to_contain_text("Waiting for")
        assert not [message for message in console_errors if "[dataviz:init]" in message]


@pytest.mark.e2e
def test_browser_query_inputs_project_date_range_parts(page: Page, tmp_path: Path):
    workspace = _copy_workspace(WORKER, tmp_path / "query-input-parts")
    dashboard_path = workspace / "dashboards" / "worker-runtime" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["query_parameters"] = [
        {
            "id": "job_date_range",
            "type": "date_range",
            "label": "Job date range",
            "required": True,
            "default": {
                "mode": "relative",
                "anchor": "today",
                "start_offset": "-3d",
                "end_offset": "-1d",
            },
        }
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    transform_root = workspace / "dashboards" / "worker-runtime" / "transforms"
    transform_path = transform_root / "scaled.yaml"
    transform = yaml.safe_load(transform_path.read_text(encoding="utf-8"))
    transform["query_inputs"] = {
        "start_date": {"parameter": "job_date_range", "part": "start"},
        "end_date": {"parameter": "job_date_range", "part": "end"},
    }
    transform_path.write_text(
        yaml.safe_dump(transform, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (transform_root / "scaled.js").write_text(
        """async function transform(context) {
  return {
    main: context.inputs.rows.map(row => ({
      name: `${context.query_inputs.start_date}|${context.query_inputs.end_date}|${row.name}`,
      value: Number(row.value) * 10,
    })),
  };
}
""",
        encoding="utf-8",
    )

    timezone = ZoneInfo("Asia/Shanghai")
    before = datetime.now(timezone).date()
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "worker-runtime")
        after = datetime.now(timezone).date()
        expected_ranges = {
            (
                (anchor - timedelta(days=3)).isoformat(),
                (anchor - timedelta(days=1)).isoformat(),
            )
            for anchor in {before, after}
        }
        stored = page.evaluate(
            """() => {
              const key = Object.keys(sessionStorage).find(value => value.startsWith('dataviz.tab-ui.v2.'));
              return JSON.parse(sessionStorage.getItem(key)).dashboards['worker-runtime'].queryParameterValues;
            }"""
        )
        assert tuple(stored["job_date_range"]) in expected_ranges
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        table = frame.locator('[data-view-id="scaled-table"]')
        expect(table).to_have_attribute("data-view-status", "ready", timeout=15_000)
        table_text = table.inner_text()
        assert any(f"{start}|{end}|alpha" in table_text for start, end in expected_ranges)
        parameter_inputs = frame.locator("body").evaluate(
            """() => window.dataviz.dependency_contract.interactive.parameter_inputs.scaled"""
        )
        assert parameter_inputs == {
            "start_date": {"parameter": "job_date_range", "part": "start"},
            "end_date": {"parameter": "job_date_range", "part": "end"},
        }


@pytest.mark.e2e
def test_browser_js_interactive_worker_cancellation_timeout_and_serializable_error(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(WORKER, tmp_path / "worker")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "worker-runtime")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        table = frame.locator('[data-view-id="scaled-table"]')
        expect(table).to_have_attribute("data-view-status", "ready", timeout=15_000)
        expect(table).to_contain_text("20")
        metrics = frame.locator("body").evaluate(
            """() => ({
              worker: window.datavizRuntime.metrics.interactiveTransforms,
              leakedEntrypoint: typeof window.transform,
            })"""
        )
        assert metrics["worker"]["completed"] >= 1
        assert metrics["leakedEntrypoint"] == "undefined"

        delay = page.locator(
            'input[name="dashboard:worker-runtime/delay_ms"]'
        )
        completed_before_drift = frame.locator("body").evaluate(
            """() => {
              const runtime = window.datavizRuntime;
              // Registration payloads are drift assertions, not a second
              // dependency source. Runtime scheduling and declarative View
              // reads must continue to use the compiled contract.
              runtime.transforms.get('scaled').spec.inputs.rows = 'source:invalid/main';
              window.dataviz.view_specs.find(view => view.id === 'scaled-table').input = 'source:invalid/main';
              return runtime.metrics.interactiveTransforms.completed;
            }"""
        )
        delay.evaluate(
            "input => { input.value = '6'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_function(
            """completed => {
              const frame = document.querySelector('#canvas-frame').contentWindow;
              const output = frame.dataviz.portable.outputs['interactive:scaled/main'];
              return frame.datavizRuntime.metrics.interactiveTransforms.completed > completed
                && Array.isArray(output) && output.some(row => Number(row.value) === 20);
            }""",
            arg=completed_before_drift,
            timeout=10_000,
        )
        expect(table).to_have_attribute("data-view-status", "ready")
        expect(table).to_contain_text("20")

        delay.evaluate(
            "input => { input.value = '750'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_function(
            """() => {
              const runtime = document.querySelector('#canvas-frame').contentWindow.datavizRuntime;
              return runtime.activeTransforms.size === 1;
            }""",
            timeout=10_000,
        )
        delay.evaluate(
            "input => { input.value = '1'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_function(
            """() => {
              const runtime = document.querySelector('#canvas-frame').contentWindow.datavizRuntime;
              return runtime.metrics.interactiveTransforms.cancelled >= 1
                && runtime.activeTransforms.size === 0;
            }""",
            timeout=10_000,
        )
        expect(table).to_have_attribute("data-view-status", "ready")

        delay.evaluate(
            "input => { input.value = '1500'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        expect(table).to_have_attribute("data-view-status", "error", timeout=10_000)
        error = frame.locator("body").evaluate(
            """() => {
              const value = window.datavizRuntime.transformErrors.get('scaled');
              return {code:value.code, name:value.name, message:value.message, worker:value.worker};
            }"""
        )
        assert error["code"] == "interactive_transform_timeout"
        assert error["name"] == "TimeoutError"
        assert error["worker"] is True


@pytest.mark.e2e
def test_server_and_browser_python_share_output_contract_and_export_runtime(
    page: Page, tmp_path: Path
):
    workspace = _build_interactive_runtime_workspace(tmp_path / "runtime-matrix")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "runtime-matrix")
        page.locator("#run-button").click()
        page.wait_for_function(
            """() => {
              const frame = document.querySelector('#canvas-frame');
              return frame?.dataset.runId
                && frame.contentWindow?.datavizRuntime
                && frame.contentWindow.dataviz.interaction
                && document.querySelector('#query-diagnostics-label')?.textContent === 'Loading';
            }""",
            timeout=20_000,
        )
        progressive_frame_id = page.locator("#canvas-frame").get_attribute(
            "data-frame-id"
        )
        frame = page.frame_locator("#canvas-frame")
        server_table = frame.locator('[data-view-id="server-table"]')
        browser_table = frame.locator('[data-view-id="browser-table"]')
        expect(server_table).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(browser_table).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(server_table).to_contain_text("104")
        expect(browser_table).to_contain_text("4")
        assert frame.locator("body").evaluate(
            """() => ({
              started:window.datavizRuntime.metrics.interactiveTransforms.started,
              completed:window.datavizRuntime.metrics.interactiveTransforms.completed,
              cancelled:window.datavizRuntime.metrics.interactiveTransforms.cancelled,
            })"""
        ) == {"started": 1, "completed": 1, "cancelled": 0}
        # The Server and Browser Interactive branches must publish before the
        # unrelated slow Query branch completes.
        expect(page.locator("#query-diagnostics-label")).to_have_text("Loading")
        (workspace / "dashboards" / "runtime-matrix" / "release-slow").write_text(
            "release\n", encoding="utf-8"
        )
        expect(page.locator("#query-diagnostics-label")).to_have_text(
            "Ready", timeout=30_000
        )
        assert page.locator("#canvas-frame").get_attribute(
            "data-frame-id"
        ) == progressive_frame_id
        original_run = page.locator("#canvas-frame").get_attribute("data-run-id")

        completed_before_selection = frame.locator("body").evaluate(
            "() => window.datavizRuntime.metrics.interactiveTransforms.completed"
        )
        frame.locator("body").evaluate(
            """async () => {
              window.dataviz.selections['dashboard:runtime-matrix/name'] = ['alpha'];
              await window.dataviz.applySelections();
            }"""
        )
        expect(server_table).to_contain_text("alpha")
        expect(server_table).not_to_contain_text("beta")
        assert frame.locator("body").evaluate(
            "() => window.datavizRuntime.metrics.interactiveTransforms.completed"
        ) == completed_before_selection

        page.locator("#dashboard-controls-control summary").click()
        factor = page.locator(
            '#compute-parameter-form input[name="dashboard:runtime-matrix/factor"]'
        )
        factor.fill("3")
        factor.dispatch_event("change")
        expect(server_table).to_contain_text("103", timeout=20_000)
        expect(browser_table).to_contain_text("3", timeout=20_000)
        assert page.locator("#canvas-frame").get_attribute("data-run-id") == original_run
        runtime_state = frame.locator("body").evaluate(
            """() => ({
              committed:window.dataviz.compute_parameters['dashboard:runtime-matrix/factor'],
              browserWorkers:window.datavizRuntime.metrics.interactiveTransforms.completed,
              active:window.datavizRuntime.activeTransforms.size,
            })"""
        )
        assert runtime_state == {"committed": 3, "browserWorkers": 2, "active": 0}

        with page.expect_download(timeout=30_000) as download_info:
            page.locator("#download-button").click()
        download = download_info.value
        assert download.suggested_filename.endswith(".zip")
        archive = tmp_path / "runtime-report.zip"
        download.save_as(archive)
        extracted = tmp_path / "runtime-report"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)
            names = set(bundle.namelist())
        html_name = next(name for name in names if name.endswith(".html"))
        assert any(name.endswith(".assets/pyodide/pyodide.mjs") for name in names)

    with _running_static_server(extracted) as report_url:
        page.goto(f"{report_url}/{html_name}", wait_until="domcontentloaded")
        exported_server = page.locator('[data-view-id="server-table"]')
        exported_browser = page.locator('[data-view-id="browser-table"]')
        expect(exported_server).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(exported_browser).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(exported_server).to_contain_text("103")
        expect(exported_browser).to_contain_text("3")
        assert page.locator("body").evaluate(
            "() => window.datavizRuntime.metrics.interactiveTransforms.completed"
        ) >= 1


@pytest.mark.e2e
def test_arrow_transport_and_repeat_thousand_group_search_lazy_budget(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(REPEAT, tmp_path / "repeat")
    sql = workspace / "dashboards" / "store-performance" / "sources" / "store-sales.sql"
    sql.write_text(sql.read_text(encoding="utf-8").replace("range(1, 101)", "range(1, 1001)"), encoding="utf-8")
    dashboard = workspace / "dashboards" / "store-performance" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard.read_text(encoding="utf-8"))
    definition["sections"][1]["repeat"]["limit"] = 1000
    all_store_view = next(
        item for item in definition["views"] if item["id"] == "all-store-trend"
    )
    all_store_view["description"] = "每家门店共享同一份 Dataset。"
    dashboard.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "store-performance")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        host = frame.locator('[data-repeat-section="all-stores"]')
        expect(host).to_have_attribute("data-repeat-count", "1000", timeout=30_000)
        expect(host).to_have_attribute("data-repeat-rendered-cards", "40")
        expect(host.locator(":scope > .dv-repeat-card").first.locator(".dv-view-description")).to_have_text(
            "每家门店共享同一份 Dataset。"
        )
        assert frame.locator("body").evaluate(
            """() => {
              const output = window.dataviz.portable.outputs['source:store-sales/main'];
              return output?.__datavizArrowOutput === true
                && window.datavizRuntime.metrics.transports.arrowRows === 12000;
            }"""
        )
        assert host.locator(":scope > .dv-repeat-card").count() == 40

        search = host.locator(".dv-repeat-search input")
        search.fill("S1000")
        expect(host).to_have_attribute("data-repeat-filtered-count", "1")
        expect(host.locator(":scope > .dv-repeat-card")).to_have_count(1)
        expect(host).to_contain_text("门店 1000")

        search.fill("")
        expect(host).to_have_attribute("data-repeat-rendered-cards", "40")
        host.locator("[data-repeat-more]").click()
        expect(host).to_have_attribute("data-repeat-rendered-cards", "80")
        performance = host.evaluate(
            """host => ({
              reconcileMs:Number(host.dataset.repeatReconcileMs),
              mounted:window.datavizRuntime.metrics.repeat.mounted,
              maxMounted:window.datavizRuntime.metrics.repeat.maxMounted,
              cards:Number(host.dataset.repeatRenderedCards),
            })"""
        )
        assert performance["reconcileMs"] < 750
        assert performance["mounted"] < performance["cards"]
        assert performance["maxMounted"] < performance["cards"]


@pytest.mark.e2e
def test_progressive_failure_and_consecutive_run_are_isolated(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(PROGRESSIVE, tmp_path / "progressive")
    slow_code = workspace / "dashboards" / "progressive" / "sources" / "slow.py"
    slow_code.write_text(
        # Leave a deterministic observation window after the fast branch is
        # visible, even on a cold browser/CI worker.
        "import time\n\ndef load(context):\n    time.sleep(4)\n    raise RuntimeError('expected branch failure')\n",
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "progressive")
        page.locator("#run-button").click()
        frame = page.frame_locator("#canvas-frame")
        fast = frame.locator('[data-view-id="fast-view"]')
        slow = frame.locator('[data-view-id="slow-view"]')
        expect(fast).to_have_attribute("data-view-status", "ready", timeout=15_000)
        expect(slow).to_have_attribute("data-view-status", "loading")
        first_run_id = page.locator("#canvas-frame").get_attribute("data-run-id")
        expect(slow).to_have_attribute("data-view-status", "error", timeout=15_000)
        expect(page.locator("#query-diagnostics-label")).to_have_text("Partial")

        slow_code.write_text(
            "def load(context):\n    return [{'branch': 'slow-second', 'value': 2}]\n",
            encoding="utf-8",
        )
        page.locator("#run-button").click()
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready", timeout=20_000)
        second_run_id = page.locator("#canvas-frame").get_attribute("data-run-id")
        assert first_run_id and second_run_id and first_run_id != second_run_id
        expect(slow).to_have_attribute("data-view-status", "ready", timeout=15_000)
        expect(slow).to_contain_text(re.compile("slow-second"))


@pytest.mark.e2e
def test_large_aggregations_do_not_cross_the_javascript_argument_limit(
    page: Page, tmp_path: Path
):
    workspace = _build_scale_workspace(tmp_path / "scale")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "scale")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        source = frame.locator('[data-view-id="source-maximum"]')
        worker = frame.locator('[data-view-id="worker-maximum"]')
        expect(source).to_have_attribute("data-view-status", "ready", timeout=30_000)
        expect(worker).to_have_attribute("data-view-status", "ready", timeout=30_000)
        expect(source).to_contain_text("150,000")
        expect(worker).to_contain_text("150,000")

        # Custom Canvas authors receive the same safe aggregation primitive.
        custom_peak = frame.locator("body").evaluate(
            """() => window.dataviz.data.frame(
              Array.from({length:150000}, (_, index) => ({bucket:0, value:index + 1}))
            ).groupBy('bucket').aggregate({
              peak:{field:'value', op:'max'},
            }).rows()[0].peak"""
        )
        assert custom_peak == 150_000
        runtime_metrics = frame.locator("body").evaluate(
            """() => ({
              arrowRows:window.datavizRuntime.metrics.transports.arrowRows,
              arrowBytes:window.datavizRuntime.metrics.transports.arrowBytes,
              rendererFailures:window.datavizRuntime.metrics.renderers.failed,
            })"""
        )
        assert runtime_metrics["arrowRows"] == 150_000
        assert runtime_metrics["arrowBytes"] > 0
        assert runtime_metrics["rendererFailures"] == 0

        # A renderer with no descriptor is a terminal empty state, not an
        # infinite "rendering" state.
        frame.locator("body").evaluate(
            "() => window.dataviz.renderView('source-maximum', () => null)"
        )
        expect(source).to_have_attribute("data-view-status", "empty")
        expect(source).to_contain_text("No data")


@pytest.mark.e2e
def test_cancelled_query_branch_reaches_a_terminal_view_state(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(PROGRESSIVE, tmp_path / "cancelled-progressive")
    slow_code = workspace / "dashboards" / "progressive" / "sources" / "slow.py"
    slow_code.write_text(
        "import time\n\ndef load(context):\n    time.sleep(10)\n    return [{'branch': 'late', 'value': 2}]\n",
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "progressive")
        page.locator("#run-button").click()
        frame = page.frame_locator("#canvas-frame")
        fast = frame.locator('[data-view-id="fast-view"]')
        slow = frame.locator('[data-view-id="slow-view"]')
        expect(fast).to_have_attribute("data-view-status", "ready", timeout=15_000)
        expect(slow).to_have_attribute("data-view-status", "loading")

        cancelled_run_id = page.locator("#canvas-frame").get_attribute("data-run-id")
        session_id = page.evaluate(
            "() => sessionStorage.getItem('dataviz.tab-session.v2')"
        )
        assert cancelled_run_id and session_id
        expect(page.locator("#run-button")).to_contain_text("Cancel query")
        page.locator("#run-button").click()
        expect(page.locator("#run-message")).to_contain_text(
            "Query cancelled", timeout=20_000
        )
        # The shell restores the previously committed Dataset (none in this
        # test). The cancelled Run remains independently inspectable and must
        # render a terminal branch state instead of returning HTTP 500.
        page.goto(
            f"{base_url}/api/dashboards/progressive/canvas"
            f"?session_id={session_id}&run_id={cancelled_run_id}",
            wait_until="domcontentloaded",
        )
        cancelled_slow = page.locator('[data-view-id="slow-view"]')
        cancelled_fast = page.locator('[data-view-id="fast-view"]')
        expect(cancelled_slow).to_have_attribute(
            "data-view-status", "cancelled", timeout=20_000
        )
        expect(cancelled_slow).to_contain_text("Computation cancelled")
        expect(cancelled_fast).to_have_attribute("data-view-status", "ready")
