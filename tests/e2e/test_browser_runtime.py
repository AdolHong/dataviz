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
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import uvicorn
import yaml
from playwright.sync_api import Browser, Page, expect, sync_playwright

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
            lifespan="off",
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
    (dashboard / "data").mkdir(parents=True)
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
        """schema: dataviz/dashboard/v2
kind: dashboard
id: runtime-matrix
title: Interactive Runtime Matrix
compute_parameters:
  - {id: factor, label: Factor, type: number, default: 2}
sources:
  - id: raw
    type: file
    path: data/rows.csv
    format: csv
    outputs: {main: {kind: table}}
interactive_transforms:
  - transforms/server.yaml
  - transforms/browser.yaml
views:
  - {id: server-table, title: Server Python, template: table, input: interactive:server/main}
  - {id: browser-table, title: Browser Python, template: table, input: interactive:browser/main}
sections:
  - {id: results, title: Runtime results, template: split, views: [server-table, browser-table]}
""",
        encoding="utf-8",
    )
    (dashboard / "data" / "rows.csv").write_text(
        "name,value\nalpha,1\nbeta,2\n", encoding="utf-8"
    )
    (dashboard / "transforms" / "server.yaml").write_text(
        """schema: dataviz/interactive-transform/v1
kind: interactive_transform
id: server
runtime: server-python
code: server.py
inputs: {rows: source:raw/main}
compute_params: [factor]
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
    frame = context.table("rows").copy()
    frame["value"] = frame["value"] * context.compute_params["factor"] + 100
    context.progress(0.5, "server midpoint")
    return {"main": frame}
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "browser.yaml").write_text(
        """schema: dataviz/interactive-transform/v1
kind: interactive_transform
id: browser
runtime: browser-python
code: browser.py
inputs: {rows: source:raw/main}
compute_params: [factor]
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
      const payload = JSON.parse(values.get('__dv_payload'));
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
def test_committed_parameter_content_and_stale_selection_export(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "content-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator(".dv-subtitle")).to_have_text("当前取数下限：0")

        page.locator("#query-parameters-control summary").click()
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
def test_section_selection_updates_bound_title_without_redrawing_siblings(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "selection-content-workspace")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    trend = next(item for item in definition["sections"] if item["id"] == "trend")
    trend["title"] = "{{ selections.section.trend.focus_region }}趋势与结构"
    trend["selections"] = [
        {
            "id": "focus_region",
            "field": "region",
            "type": "single_select",
            "default": "华东",
            "choices": [
                {"label": "华东区域", "value": "华东"},
                {"label": "华南区域", "value": "华南"},
            ],
        }
    ]
    comparison = next(
        item for item in definition["views"] if item["id"] == "region-comparison"
    )
    comparison["description"] = (
        "当前分析：{{ selections.section.trend.focus_region }}"
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
        page.locator("#query-parameters-control summary").click()
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
        "protocol": {"schema": "dataviz/runtime/v2", "component_registry_version": "3.0.0"},
        "selections": {"dashboard:probe/region": ["East"]},
        "view_specs": [{"id": "detail", "inputs": {"main": "source:data/main"}}],
        "portable": {
            "outputs": {
                "source:data/main": [
                    {"region": "East", "value": 1},
                    {"region": "West", "value": 2},
                    {"region": "West", "value": 3},
                ]
            },
            "view_inputs": {"detail": {"main": "source:data/main"}},
            "selection_contract": {
                "detail": [
                    {
                        "key": "dashboard:probe/region",
                        "id": "region",
                        "origin": "dashboard",
                        "owner_id": "probe",
                        "definition": {"type": "multi_select", "path_fields": []},
                        "binding": {"field": "region", "operator": "auto"},
                    }
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

        header = page.locator("#dashboard-selections-control")
        header.locator("summary").click()
        checkbox = header.locator('[data-selector-template="checkbox-group"]')
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
        page.keyboard.press("Escape")
        expect(header).not_to_have_attribute("open", "")

        story_index = frame.locator(".gallery-story-index")
        expect(story_index).to_be_visible()
        expect(story_index.locator("summary")).to_contain_text("23 runtime specimens")

        selections = detail.locator('.dv-context-selections[data-selection-origin="view"]')
        selections.locator("summary").click()
        expect(selections).to_have_attribute("open", "")
        tree = selections.locator('[data-selector-template="tree-select"]')
        tree.locator("[data-selector-trigger]").click()
        panel = tree.locator("[data-selector-panel]")
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
        assert tree.locator("[data-selector-trigger]").evaluate(
            "trigger => document.activeElement === trigger"
        )
        tree.locator("[data-selector-trigger]").click()
        tree_branch = tree.locator(".dv-tree-branch__check").first
        tree_branch.click()
        assert tree.locator("select").evaluate(
            "select => select.selectedOptions.length > 0"
        )
        tree_summary = tree.locator(".dv-choice-summary__tag").all_text_contents()
        assert tree_summary
        assert all(" / " not in label for label in tree_summary)
        tree.locator("footer button", has_text="Clear").click()
        assert tree.locator("select").evaluate(
            "select => select.selectedOptions.length"
        ) == 0
        tree.locator(".dv-choice-search").press("Escape")

        segmented = selections.locator('[data-selector-template="segmented"]')
        segmented.locator("button", has_text="All").click()
        expect(segmented.locator("select")).to_have_value("")
        segmented.locator("button", has_text="Software").press("Enter")
        expect(segmented.locator("select")).to_have_value("Software")

        grouped_select = selections.locator(
            '[data-selection-key="view:detail-table/product"] [data-selector-template="select"]'
        )
        grouped_select.locator("[data-selector-trigger]").click()
        select_panel = grouped_select.locator(".dv-select-panel")
        expect(select_panel).to_be_visible()
        panel_surface = select_panel.evaluate(
            """panel => ({
              sharedClass: panel.classList.contains('dv-selector-panel'),
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

        cascader = selections.locator('[data-selector-template="cascader"]')
        cascader.locator("[data-selector-trigger]").click()
        branch_check = cascader.locator(".dv-cascader-branch__check").first
        expect(branch_check).to_be_visible()
        branch_check.click()
        assert cascader.locator("select").evaluate(
            "select => select.selectedOptions.length > 0"
        )
        summary_labels = cascader.locator(".dv-choice-summary__tag").all_text_contents()
        assert summary_labels
        assert all(" / " not in label for label in summary_labels)
        cascader.locator(".dv-choice-search").press("Escape")

        date_range = selections.locator('[data-selector-template="date-range"]')
        expect(date_range.locator('input[type="date"]')).to_have_count(2)
        assert date_range.locator('input[type="date"]').evaluate_all(
            "inputs => inputs.every(input => input.labels.length === 1)"
        )
        date_range.locator("button", has_text="Q1 2026").click()
        expect(date_range.locator("input[data-selection-input]")).to_have_value(
            "2026-01-01,2026-03-31"
        )
        date_range.locator("button", has_text="Clear").click()
        expect(date_range.locator("input[data-selection-input]")).to_have_value("")
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

        # Build a 1,000-option Story fixture against the public package API.
        frame.locator("body").evaluate(
            """() => {
              const host = document.createElement('div');
              host.id = 'virtual-contract-host';
              host.className = 'dv-selector';
              host.dataset.selectorTemplate = 'select';
              host.dataset.searchMode = 'always';
              host.dataset.virtualMode = 'always';
              host.dataset.searchPlaceholder = 'Search 1000 options';
              host.innerHTML = '<select id="virtual-contract" multiple data-selection-input="virtual">'
                + Array.from({length:1000}, (_, index) => {
                    const value = String(index + 1).padStart(4, '0');
                    return `<option value="${value}">Item ${value}</option>`;
                  }).join('')
                + '</select><div data-selector-mount></div>';
              document.body.append(host);
              window.datavizComponents.hydrate(host);
            }"""
        )
        virtual = frame.locator("#virtual-contract-host")
        virtual.locator("[data-selector-trigger]").click()
        expect(virtual.locator("[data-selector-panel]")).to_be_visible()
        rendered = virtual.locator(".dv-select-rows .dv-choice-option").count()
        assert 1 <= rendered < 40
        virtual.locator(".dv-choice-search").fill("Item 1000")
        expect(virtual.locator(".dv-select-panel footer small")).to_contain_text("1 matching")
        assert virtual.locator(".dv-select-rows .dv-choice-option").count() == 1
        virtual.locator(".dv-choice-search").press("ArrowDown")
        virtual.locator(".dv-select-options").press("Enter")
        expect(virtual.locator("select")).to_have_values(["1000"])
        assert virtual.locator("[data-selector-trigger]").evaluate(
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
        header = page.locator("#dashboard-selections-control")
        header.locator("summary").click()
        expect(header).to_have_attribute("open", "")
        province = header.locator('[data-selector-template="checkbox-group"]')
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
        frame.locator("body").click(position={"x": 8, "y": 8})
        expect(header).not_to_have_attribute("open", "")

        section_popover = frame.locator(
            '.dv-context-selections[data-selection-origin="section"]'
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
        expect(city_select).to_have_count(1)
        dashboard_select.select_option(["福建"], force=True)
        expect(city_select).to_have_values(["厦门"], timeout=5_000)
        enabled_cities = city_select.evaluate(
            "select => [...select.options].filter(option => !option.disabled).map(option => option.value)"
        )
        assert enabled_cities == ["厦门"]

        dashboard_select.select_option(["广东", "福建"], force=True)
        page.wait_for_function(
            """() => {
              const select = document.querySelector('#canvas-frame').contentWindow.document
                .querySelector('select[data-selection-input="section:geography/city"]');
              return select && [...select.options].filter(option => !option.disabled).length === 3;
            }"""
        )
        city_select.select_option(["深圳", "厦门"], force=True)
        expect(city_select).to_have_values(["深圳", "厦门"])
        page.wait_for_function(
            """() => JSON.stringify(
              document.querySelector('#canvas-frame').contentWindow.dataviz
                .selections['section:geography/city']
            ) === JSON.stringify(['深圳', '厦门'])"""
        )
        view_popover = frame.locator(
            '[data-view-id="city-detail"] .dv-context-selections[data-selection-origin="view"]'
        )
        view_popover.locator("summary").click()
        cascader = view_popover.locator('[data-selector-template="cascader"]')
        cascader.locator("[data-selector-trigger]").click()
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

        # Instrument the public Runtime boundary: a View Selection may redraw
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

        delay = page.locator('input[name="dashboard:worker-runtime/delay_ms"]')
        delay.evaluate(
            "input => { input.value = '180'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_timeout(100)
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
            "input => { input.value = '500'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
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
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        server_table = frame.locator('[data-view-id="server-table"]')
        browser_table = frame.locator('[data-view-id="browser-table"]')
        expect(server_table).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(browser_table).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(server_table).to_contain_text("104")
        expect(browser_table).to_contain_text("4")
        original_run = page.locator("#canvas-frame").get_attribute("data-run-id")

        page.locator("#compute-parameters-control summary").click()
        factor = page.locator('#compute-parameter-form input[name="factor"]')
        factor.fill("3")
        factor.dispatch_event("change")
        expect(server_table).to_contain_text("106", timeout=20_000)
        expect(browser_table).to_contain_text("6", timeout=20_000)
        assert page.locator("#canvas-frame").get_attribute("data-run-id") == original_run
        runtime_state = frame.locator("body").evaluate(
            """() => ({
              committed:window.dataviz.compute_parameters.factor,
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
        expect(exported_server).to_contain_text("106")
        expect(exported_browser).to_contain_text("6")
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
