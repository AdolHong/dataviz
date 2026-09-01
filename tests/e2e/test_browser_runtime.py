from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import threading
import time
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
from dataviz.execution.parameter_materializations import ParameterMaterializationStore
import dataviz.execution.parameter_materializations as parameter_materializations
from dataviz.errors import ExecutionFailure
from dataviz.workspace import load_workspace


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


def _route_perspective_contract_runtime(page: Page) -> None:
    """Serve the Perspective browser contract without relying on a public CDN."""

    client = """
const perspective = {
  async worker() {
    return {
      async table(rows, options = {}) {
        let current = rows;
        return {
          name:options.name || '',
          async replace(next) { current = next; },
          async delete() { current = []; },
          get rows() { return current; },
        };
      },
      terminate() {},
    };
  },
};
export default perspective;
"""
    viewer = """
class DatavizTestPerspectiveViewer extends HTMLElement {
  constructor() {
    super();
    this._config = {
      plugin:'Datagrid', group_by:[], split_by:[], columns:[], aggregates:{},
      filter:[], sort:[], settings:false,
    };
    const shadow = this.attachShadow({mode:'open'});
    shadow.innerHTML = `
      <style>:host{display:block;height:100%;min-height:0}</style>
      <section id="settings_panel" style="background-color:#fff;background-image:none">
        <div id="plugin_selector_container">
          <button type="button" class="plugin-select-item" data-plugin="Datagrid">Datagrid</button>
        </div>
      </section>`;
    shadow.querySelector('.plugin-select-item').addEventListener('click', () => {
      shadow.querySelector('#plugin_selector_container').classList.add('open');
    });
  }
  async load(worker) { this._worker = worker; }
  async restore(config = {}) { this._config = {...this._config, ...config}; }
  async flush() {}
  async save() { return {...this._config}; }
  async resize() {}
  async delete() { this._worker = null; }
}
if (!customElements.get('perspective-viewer')) {
  customElements.define('perspective-viewer', DatavizTestPerspectiveViewer);
}
export default DatavizTestPerspectiveViewer;
"""

    def fulfill(route):
        url = route.request.url
        headers = {"access-control-allow-origin": "*"}
        if url.endswith("themes.css"):
            route.fulfill(
                status=200,
                content_type="text/css",
                headers=headers,
                body="perspective-viewer{display:block;height:100%}",
            )
        elif "/client@" in url:
            route.fulfill(
                status=200,
                content_type="application/javascript",
                headers=headers,
                body=client,
            )
        elif "/viewer@" in url and url.endswith("perspective-viewer.js"):
            route.fulfill(
                status=200,
                content_type="application/javascript",
                headers=headers,
                body=viewer,
            )
        else:
            route.fulfill(
                status=200,
                content_type="application/javascript",
                headers=headers,
                body="export {};",
            )

    page.route("https://cdn.jsdelivr.net/npm/@perspective-dev/**", fulfill)


def _copy_workspace(source: Path, destination: Path) -> Path:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(".dataviz", "dist", "__pycache__", "*.pyc"),
    )
    return destination


def _build_same_view_dependency_workspace(root: Path) -> Path:
    dashboard = root / "dashboards" / "same-view-controls"
    sources = dashboard / "sources"
    auth = root / "auth"
    sources.mkdir(parents=True)
    auth.mkdir()
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: same-view-controls
title: Same View Controls
folders: []
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
        """schema: dataviz/dashboard/v14
kind: dashboard
id: same-view-controls
title: Same View Controls
adapters: {warehouse: warehouse}
sources: [sources/daily.yaml]
views:
  - id: daily-detail
    title: Daily detail
    input: source:daily/main
    template: table
    columns: [dow, job_date, sales]
    controls:
      - id: dow
        field: dow
        type: single_select
        value_type: text
        label: Weekday
        initial: {mode: empty}
        options: {mode: infer, source: source:daily/main}
      - id: dates
        field: job_date
        type: multiple_select
        value_type: text
        label: Dates
        depends_on: [view.dow]
        options: {mode: infer, source: source:daily/main}
    control_inputs:
      dow: {mode: filter, control: view.dow, field: dow, inputs: [main], empty: match_none}
      dates: {mode: filter, control: view.dates, field: job_date, inputs: [main], empty: match_none}
sections:
  - {id: results, title: Results, views: [daily-detail]}
""",
        encoding="utf-8",
    )
    (sources / "daily.yaml").write_text(
        """schema: dataviz/source/v5
kind: source
id: daily
type: sql
adapter: warehouse
code: daily.sql
outputs:
  main:
    kind: table
    schema:
      - {name: dow}
      - {name: job_date}
      - {name: sales}
""",
        encoding="utf-8",
    )
    (sources / "daily.sql").write_text(
        """select * from (values
 ('周一', '2026-08-03', 10),
 ('周一', '2026-08-10', 20),
 ('周二', '2026-08-04', 30)
) as t(dow, job_date, sales)
""",
        encoding="utf-8",
    )
    return root


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
        """schema: dataviz/dashboard/v14
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
        """schema: dataviz/interactive-transform/v4
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
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: interactive-runtime-e2e
title: Interactive Runtime E2E
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v14
kind: dashboard
id: runtime-matrix
title: Interactive Runtime Matrix
query_parameters:
  - {id: batch, type: single_input, value_type: integer, label: Batch, default: 3}
controls:
  - {id: factor, label: Factor, type: single_input, value_type: number, default: 2}
  - id: name
    field: name
    type: multiple_select
    value_type: text
    initial: {mode: values, values: [alpha, beta]}
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
  - id: server-table
    title: Server Python
    template: table
    input: interactive:server/main
    control_inputs: &name_filter
      name: {mode: filter, control: dashboard.name, field: name, inputs: [main], empty: match_none}
  - id: browser-table
    title: Browser JS
    template: table
    input: interactive:browser/main
    control_inputs: *name_filter
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
        """schema: dataviz/interactive-transform/v4
kind: interactive_transform
id: server
runtime: server-python
code: server.py
inputs: {rows: source:raw/main}
query_inputs: {batch: batch}
control_inputs:
  factor: {mode: value, control: dashboard.factor}
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
    frame["value"] = frame["value"] * context.control_inputs["factor"] + 100
    context.progress(0.5, "server midpoint")
    return {"main": frame}
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "browser.yaml").write_text(
        """schema: dataviz/interactive-transform/v4
kind: interactive_transform
id: browser
runtime: browser-js
code: browser.js
inputs: {rows: source:raw/main}
query_inputs: {batch: batch}
control_inputs:
  factor: {mode: value, control: dashboard.factor}
trigger: auto
debounce_ms: 0
export: {mode: interactive}
outputs:
  main:
    kind: table
    schema: [{name: name}, {name: value}]
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "browser.js").write_text(
        """async function transform(context) {
  if (Number(context.query_inputs.batch) !== 3) throw new Error('missing browser-js query input');
  await new Promise(resolve => setTimeout(resolve, 700));
  const input = context.inputs.rows;
  const rows = input?.__datavizColumnarTable
    ? Array.from({length:input.length}, (_, index) => Object.fromEntries(
        Object.entries(input.columns).map(([name, column]) => [name, column[index]])
      ))
    : input;
  const factor = Number(context.control_inputs.factor);
  return {main:rows.map(row => ({name:row.name, value:Number(row.value) * factor}))};
}
""",
        encoding="utf-8",
    )
    return root


def _open_dashboard(page: Page, base_url: str, dashboard_id: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")
    dashboard = page.locator(f'[data-nav-type="dashboard"][data-id="{dashboard_id}"]')
    expect(dashboard).to_be_visible(timeout=10_000)
    if "active" not in (dashboard.get_attribute("class") or "").split():
        dashboard.click()
    expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)


def _run_and_wait(page: Page, expected: str = "Ready") -> None:
    page.locator("#run-button").click()
    expect(page.locator("#query-diagnostics-label")).to_have_text(
        expected,
        timeout=30_000,
    )


def _export_html(page: Page) -> None:
    share = page.locator("#share-control")
    if share.get_attribute("open") is None:
        page.locator("#share-button").click()
    page.locator("#download-button").click()


@pytest.mark.e2e
def test_parameter_domain_cascade_reload_and_tab_restore(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain")
    with _running_server(workspace) as base_url:
        domain_requests: list[str] = []
        page.on(
            "request",
            lambda request: (
                domain_requests.append(request.url)
                if "/parameter-domains/lookup" in request.url
                else None
            ),
        )
        _open_dashboard(page, base_url, "parameter-domain-lab")
        reload_options = page.locator("#query-parameter-options-reload")
        province = page.locator('select[name="provinces"]')
        city = page.locator('select[name="cities"]')

        expect(reload_options).to_be_visible()
        expect(province).to_have_values(["GD"])
        expect(city.locator("option")).to_have_count(2, timeout=20_000)
        expect(city).to_have_values([])
        assert len(domain_requests) >= 2
        city_control = page.locator("#parameter-form .dv-control").filter(has=city)
        expect(city_control.locator("[data-control-summary]")).to_have_text("全选")

        _run_and_wait(page)
        remembered = page.evaluate(
            """async () => {
              const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
              const response = await fetch(`/api/session/runs?session_id=${encodeURIComponent(sessionId)}`);
              return response.json();
            }"""
        )
        initial_run = next(
            item for item in remembered["runs"] if item["dashboard_id"] == "parameter-domain-lab"
        )
        assert initial_run["query_parameter_state"] == {
            "provinces": {"selection": "include", "value": ["GD"]},
            "cities": {"selection": "all", "value": []},
        }
        committed_run_id = page.locator("#canvas-frame").get_attribute("data-run-id")

        # Compact all/exclude state is part of the committed snapshot. Deselecting
        # one visible member stores only that exception; Revert restores all
        # without enumerating the candidate generation or rerunning Query.
        city_trigger = city_control.locator("[data-control-trigger]")
        city_trigger.click()
        city_control.locator(".dv-choice-option", has_text="广州").click()
        expect(city_control.locator("[data-control-summary]")).to_contain_text("排除 1 项")
        revert = page.locator("#query-parameters-revert")
        expect(page.locator("#query-control-meta")).to_have_text("Changed")
        expect(revert).to_be_visible()
        revert.click()
        expect(page.locator("#query-control-meta")).to_have_text("Applied")
        expect(revert).to_be_hidden()
        expect(city_control.locator("[data-control-summary]")).to_have_text("全选")
        assert page.locator("#canvas-frame").get_attribute("data-run-id") == committed_run_id

        # A normal parent edit coordinates the child draft. An old operand
        # that is invalid in the new parent range must not be merged back into
        # the visible options as an unavailable pseudo-candidate. Revert is the
        # only path that deliberately preserves unavailable committed values.
        city_trigger.click()
        city_control.get_by_role("button", name="Clear").click()
        city_control.locator(".dv-choice-option", has_text="深圳").click()
        expect(city).to_have_values(["SZ"])

        # Parent changes issue local Lookup predicates against the same immutable
        # materialization generation. The visible custom controls remain usable.
        province_control = page.locator("#parameter-form .dv-control").filter(has=province)
        province_trigger = province_control.locator("[data-control-trigger]")
        expect(province_trigger).to_be_enabled()
        province_trigger.click()
        province_control.locator(".dv-choice-option", has_text="湖南").click()
        expect(province).to_have_values(["GD", "HN"])

        province.select_option(["HN"], force=True)
        expect(city.locator("option")).to_have_count(1, timeout=10_000)
        expect(city.locator("option")).to_have_text(["长沙"])
        expect(city.locator('option[data-unavailable="true"]')).to_have_count(0)
        expect(city).to_have_values([])
        expect(city).to_have_attribute("data-query-selection", "all")
        expect(page.locator("#run-button")).to_be_enabled()

        # Revert restores the parent then rehydrates the child atomically from
        # the current generation; it does not execute the analytical Query.
        expect(revert).to_be_visible()
        revert.click()
        expect(province).to_have_values(["GD"], timeout=10_000)
        expect(city.locator("option")).to_have_count(2, timeout=10_000)
        expect(city).to_have_values([])
        expect(page.locator("#query-control-meta")).to_have_text("Applied")
        assert page.locator("#canvas-frame").get_attribute("data-run-id") == committed_run_id

        requests_before_reload = len(domain_requests)
        reload_options.click()
        expect(reload_options).to_be_enabled(timeout=10_000)
        expect(city).to_have_values([])
        assert len(domain_requests) > requests_before_reload

        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)
        expect(province).to_have_values(["GD"])
        expect(city.locator("option")).to_have_count(2, timeout=20_000)
        expect(city).to_have_values([])

        _run_and_wait(page)
        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        report = Path(download_info.value.path()).read_text(encoding="utf-8")
        assert "parameter-domains/lookup" not in report
        assert "locations.sql" not in report
        assert '"provinces": {"selection": "include", "value": ["GD"]}' in report
        assert '"cities": {"selection": "all", "value": []}' in report


@pytest.mark.e2e
def test_parameter_domain_lookup_search_and_cursor_pagination(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-pagination")
    dashboard_root = workspace / "dashboards" / "功能示例##parameter-domain-lab"
    domain_path = dashboard_root / "parameter_domains" / "locations.yaml"
    domain_path.write_text(
        domain_path.read_text(encoding="utf-8").replace("max_rows: 100", "max_rows: 200"),
        encoding="utf-8",
    )
    rows = ",\n".join(
        f"  ('GD', '广东', 1, 'C{index:03d}', '城市 {index:03d}', {index})"
        for index in range(1, 121)
    )
    (dashboard_root / "parameter_domains" / "locations.sql").write_text(
        "select * from (values\n"
        + rows
        + "\n) as locations("
        "province_code, province_name, province_order, city_code, city_name, city_order)\n",
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        requests = []
        ready_responses: list[dict] = []

        def record_request(request):
            if "/parameter-domains/lookup" in request.url:
                requests.append(request)

        def record_response(response):
            if "/parameter-domains/lookup" not in response.url or response.status != 200:
                return
            payload = response.json()
            if payload.get("status") == "ready":
                ready_responses.append(payload)

        page.on("request", record_request)
        page.on("response", record_response)
        _open_dashboard(page, base_url, "parameter-domain-lab")
        city = page.locator('select[name="cities"]')
        expect(city.locator("option")).to_have_count(50, timeout=20_000)
        city_control = page.locator("#parameter-form .dv-control").filter(has=city)
        city_control.locator("[data-control-trigger]").click()
        search = city_control.locator(".dv-choice-search")

        # This member is outside the first page, so finding it proves that the
        # Picker used remote Lookup search rather than filtering only loaded DOM.
        search.fill("城市 119")
        expect(city_control.locator(".dv-choice-option")).to_have_count(1, timeout=10_000)
        expect(city_control.locator(".dv-choice-option")).to_contain_text("城市 119")

        search.fill("")
        expect(city.locator("option")).to_have_count(50, timeout=10_000)
        viewport = city_control.locator(".dv-select-options")
        viewport.evaluate(
            "node => { node.scrollTop = node.scrollHeight; node.dispatchEvent(new Event('scroll')); }"
        )
        expect(city.locator("option")).to_have_count(100, timeout=10_000)

        payloads = [request.post_data_json for request in requests if request.post_data]
        assert any(payload.get("search") == "城市 119" for payload in payloads)
        assert any(payload.get("cursor") for payload in payloads)
        assert all("sql" not in payload and "adapter" not in payload for payload in payloads)
        generations = {payload["generation"] for payload in ready_responses}
        assert len(generations) == 1


@pytest.mark.e2e
def test_parameter_domain_failure_does_not_trap_dashboard_navigation(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-failure")
    domain_sql = (
        workspace
        / "dashboards"
        / "功能示例##parameter-domain-lab"
        / "parameter_domains"
        / "locations.sql"
    )
    domain_sql.write_text("select * from missing_parameter_domain_table", encoding="utf-8")

    with _running_server(workspace) as base_url:
        page.goto(
            f"{base_url}/dashboards/parameter-domain-lab",
            wait_until="domcontentloaded",
        )
        # Candidate failure does not invalidate a canonical all/include state;
        # users who already know the value may still run the analytical Query.
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)

        # A reload may retry the broken Domain, but it must not make the Shell
        # or another Dashboard unreachable.
        page.reload(wait_until="domcontentloaded")
        target = page.locator('[data-nav-type="dashboard"][data-id="chart-gallery"]')
        expect(target).to_be_visible(timeout=10_000)
        target.click()
        expect(target).to_have_class(re.compile(r"\bactive\b"))
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)
        expect(page).to_have_url(re.compile(r"/dashboards/chart-gallery"))


@pytest.mark.e2e
def test_parameter_domain_generation_is_shared_across_dashboards_and_browser_contexts(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-shared")
    original = workspace / "dashboards" / "功能示例##parameter-domain-lab"
    shared = workspace / "parameter_domains"
    shared.mkdir()
    shutil.copy2(original / "parameter_domains" / "locations.yaml", shared / "locations.yaml")
    shutil.copy2(original / "parameter_domains" / "locations.sql", shared / "locations.sql")
    dashboard_path = original / "dashboard.yaml"
    dashboard_path.write_text(
        dashboard_path.read_text(encoding="utf-8").replace(
            "parameter_domains: [parameter_domains/locations.yaml]",
            "parameter_domains: [workspace:/parameter_domains/locations.yaml]",
        ),
        encoding="utf-8",
    )
    copied = workspace / "dashboards" / "功能示例##parameter-domain-lab-copy"
    shutil.copytree(original, copied)
    copied_dashboard = copied / "dashboard.yaml"
    copied_dashboard.write_text(
        copied_dashboard.read_text(encoding="utf-8").replace(
            "id: parameter-domain-lab", "id: parameter-domain-lab-copy", 1
        ),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "parameter-domain-lab")
        expect(page.locator('select[name="cities"] option')).to_have_count(2, timeout=20_000)
        second_context = page.context.browser.new_context(viewport={"width": 1440, "height": 900})
        second_page = second_context.new_page()
        try:
            _open_dashboard(second_page, base_url, "parameter-domain-lab-copy")
            expect(second_page.locator('select[name="cities"] option')).to_have_count(
                2, timeout=20_000
            )
            index = workspace / ".dataviz" / "parameter-materializations" / "index.sqlite"
            with sqlite3.connect(index) as connection:
                rows = connection.execute(
                    "SELECT generation, status FROM materializations"
                ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] and rows[0][1] == "ready"
        finally:
            second_context.close()


@pytest.mark.e2e
def test_hard_expired_parameter_domain_disables_only_its_pickers(
    page: Page, tmp_path: Path, monkeypatch
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-expired")
    loaded = load_workspace(workspace)
    dashboard = loaded.dashboard("parameter-domain-lab")
    store = ParameterMaterializationStore(loaded)
    record = store.build(dashboard, "locations")
    with sqlite3.connect(store.index_path) as connection:
        connection.execute(
            "UPDATE materializations SET refresh_due_at=?, expires_at=? "
            "WHERE materialization_key=?",
            (time.time() - 2, time.time() - 1, record.key),
        )

    def fail_rebuild(**_kwargs):
        raise ExecutionFailure(
            "benchmark warehouse unavailable",
            details={"code": "parameter_materialization_test_failure"},
        )

    monkeypatch.setattr(parameter_materializations, "execute_sql_query", fail_rebuild)
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "parameter-domain-lab")
        province = page.locator('select[name="provinces"]')
        city = page.locator('select[name="cities"]')
        expect(province).to_be_disabled(timeout=20_000)
        expect(city).to_be_disabled(timeout=20_000)
        expect(city.locator("option")).to_have_count(0)
        expect(page.locator("#run-button")).to_be_enabled()
        expect(
            page.locator('[data-nav-type="dashboard"][data-id="chart-gallery"]')
        ).to_be_visible()


@pytest.mark.e2e
def test_date_parameter_inputs_share_iso_text_and_calendar_contract(
    page: Page,
    tmp_path: Path,
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "date-parameter-contract")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "date-parameter-lab")

        form = page.locator("#parameter-form")
        date_control = form.locator('[data-control-component="date-picker"]')
        date_input = date_control.locator('.dv-date-picker__control[type="text"]')
        expect(date_input).to_have_value(re.compile(r"^\d{4}-\d{2}-\d{2}$"))
        date_input.fill("20260809")
        expect(date_input).to_have_value("2026-08-09")
        expect(date_input).to_have_attribute("aria-invalid", "false")
        date_input.fill("20260231")
        expect(date_input).to_have_value("2026-02-31")
        expect(date_input).to_have_attribute("aria-invalid", "true")
        date_input.fill("20260809")
        date_input.press("Enter")
        expect(date_input).to_have_value("2026-08-09")
        expect(date_input).to_have_attribute("aria-invalid", "false")

        range_control = form.locator('[data-control-component="range-picker"]')
        endpoints = range_control.locator('.dv-date-range__endpoint[type="text"]')
        expect(endpoints).to_have_count(2)
        expect(endpoints.nth(0)).to_have_value(re.compile(r"^\d{4}-\d{2}-\d{2}$"))
        expect(endpoints.nth(1)).to_have_value(re.compile(r"^\d{4}-\d{2}-\d{2}$"))
        assert endpoints.evaluate_all(
            "items => items.map(item => getComputedStyle(item).borderWidth)"
        ) == ["0px", "0px"]

        range_control.locator("[data-control-trigger]").click()
        panel = range_control.locator("[data-control-panel]")
        expect(panel).to_be_visible()
        presets = panel.locator(".dv-date-range__presets")
        expect(presets).to_have_attribute("hidden", "")
        expect(presets).not_to_be_visible()
        assert presets.evaluate("node => getComputedStyle(node).display") == "none"
        expect(panel.locator(".dv-date-range__month")).to_have_count(2)
        expect(panel.locator(".dv-date-range__footer")).to_be_hidden()
        first_month = panel.locator(".dv-date-range__month").first
        first_month.locator(".dv-date-range__year-select").select_option("2025")
        first_month.locator(".dv-date-range__month-select").select_option("11")
        expect(
            panel.locator(".dv-date-range__month").nth(0).locator(".dv-date-range__year-select")
        ).to_have_value("2025")
        expect(
            panel.locator(".dv-date-range__month").nth(1).locator(".dv-date-range__year-select")
        ).to_have_value("2026")
        panel.press("Escape")

        endpoints.nth(0).fill("20260810")
        endpoints.nth(1).fill("20260820")
        endpoints.nth(1).press("Enter")
        expect(range_control.locator('input[name="report_range"]')).to_have_value(
            "2026-08-10,2026-08-20"
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

        page.locator('[data-nav-type="dashboard"][data-id="parameter-playground"]').click()
        expect(page.locator("#query-parameters-toggle")).to_be_visible()
        expect(page.locator("#query-parameters-toggle")).to_have_attribute("aria-expanded", "true")
        expect(page.locator("#query-parameters-panel")).to_be_visible()
        expect(page.locator("#parameter-form .field")).to_have_count(2)


@pytest.mark.e2e
def test_portable_query_tray_uses_document_flow_and_leaves_the_viewport(page: Page, tmp_path: Path):
    report_path = tmp_path / "portable-header-controls.html"
    with _running_server(MINIMAL) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        server_visual = page.evaluate(
            """() => {
              const header = document.querySelector('.topbar');
              const card = document.querySelector('.dv-query-card');
              const title = card.querySelector('h2');
              const field = card.querySelector('.field');
              const value = field.querySelector('input, select, output');
              const pick = (node, properties) => Object.fromEntries(
                properties.map(name => [name, getComputedStyle(node)[name]])
              );
              return {
                headerHeight:header.getBoundingClientRect().height,
                body:pick(document.body, ['fontFamily', 'fontSize', 'backgroundColor']),
                card:pick(card, ['backgroundColor', 'borderColor', 'borderRadius', 'boxShadow']),
                title:pick(title, ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight']),
                label:pick(field.querySelector(':scope > label'), ['fontFamily', 'fontSize', 'fontWeight']),
                value:pick(value, ['fontFamily', 'fontSize', 'minHeight']),
              };
            }"""
        )
        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        toggle = page.locator("[data-runtime-query-toggle]")
        panel = page.locator("#dv-runtime-query-panel")
        canvas = page.locator(".dv-canvas")
        expect(toggle).to_have_attribute("aria-expanded", "false")
        expect(panel).to_be_hidden()
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        expect(panel).to_be_visible()
        portable_visual = page.evaluate(
            """() => {
              const header = document.querySelector('.dv-runtime-header');
              const card = document.querySelector('.dv-query-card');
              const title = card.querySelector('h2');
              const field = card.querySelector('.dv-query-value');
              const value = field.querySelector('output');
              const pick = (node, properties) => Object.fromEntries(
                properties.map(name => [name, getComputedStyle(node)[name]])
              );
              return {
                headerHeight:header.getBoundingClientRect().height,
                body:pick(document.body, ['fontFamily', 'fontSize', 'backgroundColor']),
                card:pick(card, ['backgroundColor', 'borderColor', 'borderRadius', 'boxShadow']),
                title:pick(title, ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight']),
                label:pick(field.querySelector('label'), ['fontFamily', 'fontSize', 'fontWeight']),
                value:pick(value, ['fontFamily', 'fontSize', 'minHeight']),
              };
            }"""
        )
        assert abs(portable_visual.pop("headerHeight") - server_visual.pop("headerHeight")) <= 1
        assert portable_visual == server_visual
        geometry = page.evaluate(
            """() => {
              const toolbar = document.querySelector('.dv-runtime-header').getBoundingClientRect();
              const panel = document.querySelector('#dv-runtime-query-panel').getBoundingClientRect();
              const canvas = document.querySelector('.dv-canvas').getBoundingClientRect();
              const card = document.querySelector('.dv-query-card').getBoundingClientRect();
              const canvasPadding = parseFloat(getComputedStyle(document.querySelector('.dv-canvas')).paddingLeft);
              return {
                toolbar:{top:toolbar.top,bottom:toolbar.bottom},
                panel:{top:panel.top,bottom:panel.bottom,position:getComputedStyle(document.querySelector('#dv-runtime-query-panel')).position},
                canvas:{top:canvas.top},
                horizontal:{cardLeft:card.left,cardRight:card.right,canvasLeft:canvas.left,canvasRight:canvas.right,canvasPadding},
              };
            }"""
        )
        assert geometry["panel"]["position"] == "relative", geometry
        assert geometry["panel"]["top"] >= geometry["toolbar"]["bottom"] - 1, geometry
        assert geometry["canvas"]["top"] >= geometry["panel"]["bottom"] - 1, geometry
        horizontal = geometry["horizontal"]
        assert (
            abs(horizontal["cardLeft"] - horizontal["canvasLeft"] - horizontal["canvasPadding"])
            <= 1
        ), geometry
        assert (
            abs(horizontal["canvasRight"] - horizontal["cardRight"] - horizontal["canvasPadding"])
            <= 1
        ), geometry

        # Query evidence is Header content, not an Overlay. Escape and outside
        # clicks do not close it, and scrolling naturally moves it away while
        # the compact toolbar remains available.
        page.keyboard.press("Escape")
        expect(panel).to_be_visible()
        canvas.click(position={"x": 4, "y": 4})
        expect(panel).to_be_visible()
        page.evaluate(
            """() => {
              const card = document.querySelector('.dv-query-card');
              window.scrollTo(0, card.offsetTop + card.offsetHeight + 100);
            }"""
        )
        page.wait_for_timeout(100)
        scrolled = page.evaluate(
            """() => ({
              toolbarTop:document.querySelector('.dv-runtime-header').getBoundingClientRect().top,
              panelBottom:document.querySelector('#dv-runtime-query-panel').getBoundingClientRect().bottom,
            })"""
        )
        assert abs(scrolled["toolbarTop"]) <= 1, scrolled
        assert scrolled["panelBottom"] <= 1, scrolled


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
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready", timeout=30_000)
        expect(page.locator("#workspace-update")).to_be_hidden()


@pytest.mark.e2e
def test_committed_parameter_content_and_stale_selection_export(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "content-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator(".dv-subtitle")).to_have_text("当前取数下限：0")
        expect(frame.locator('[data-state-key="parameter:min_query_revenue"]')).to_contain_text(
            "取数最低收入0"
        )
        expect(frame.locator('[data-state-key="dashboard:sales-overview/region"]')).to_contain_text(
            "区域"
        )

        parameter = page.locator('#parameter-form input[name="min_query_revenue"]')
        parameter.fill("150000")
        expect(frame.locator(".dv-subtitle")).to_have_text("当前取数下限：0")
        pending_parameter = frame.locator('[data-state-key="parameter:min_query_revenue"]')
        expect(pending_parameter).to_have_attribute("data-state-stale", "true")
        expect(pending_parameter).to_contain_text("待应用：150000")
        _run_and_wait(page)
        expect(frame.locator(".dv-subtitle")).to_have_text(
            "当前取数下限：150000",
            timeout=20_000,
        )
        expect(frame.locator('[data-state-key="parameter:min_query_revenue"]')).to_contain_text(
            "150000"
        )

        inject_stale_state = """() => {
          const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
          const key = `dataviz.tab-ui.v4.${sessionId}`;
          const saved = JSON.parse(sessionStorage.getItem(key));
          saved.dashboards['sales-overview'].controlCheckpoint.controls['view:deleted/value'] = {
            intent:'explicit', value:['stale'], revision:1,
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
                sessionStorage.getItem(`dataviz.tab-ui.v4.${sessionId}`)
              );
              return !('view:deleted/value' in (
                saved.dashboards['sales-overview'].controlCheckpoint?.controls || {}
              ));
            }""",
            timeout=20_000,
        )
        remaining = page.evaluate(
            """() => {
              const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
              const saved = JSON.parse(
                sessionStorage.getItem(`dataviz.tab-ui.v4.${sessionId}`)
              );
              return Object.keys(
                saved.dashboards['sales-overview'].controlCheckpoint?.controls || {}
              );
            }"""
        )
        assert "view:deleted/value" not in remaining

        # Export independently collects the Canvas evidence snapshot; it never
        # serializes the Shell checkpoint as analysis state.
        with page.expect_request(
            lambda request: request.method == "POST" and request.url.endswith("/report"),
            timeout=20_000,
        ) as request_info:
            with page.expect_download(timeout=20_000) as download_info:
                _export_html(page)
        download = download_info.value
        supplied = request_info.value.post_data_json["control_state"]
        assert "view:deleted/value" not in supplied

        report_path = tmp_path / "parameter-report.html"
        download.save_as(report_path)
        report = report_path.read_text(encoding="utf-8")
        assert '<p class="dv-subtitle">当前取数下限：150000</p>' in report


@pytest.mark.e2e
def test_canvas_messages_are_bound_to_the_current_frame_instance(page: Page, tmp_path: Path):
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
                type:'dataviz:control-snapshot',
                dashboard_id:active.dataset.dashboardId,
                run_id:active.dataset.runId,
                frame_id:active.dataset.frameId,
                snapshot:{
                  control_version:999,
                  current_controls:{
                    'view:rogue/value':{intent:'explicit', value:['wrong-source'], revision:1},
                  },
                  dashboard_controls:[],
                },
              };
              rogue.contentWindow.eval(`parent.postMessage(${JSON.stringify(payload)}, location.origin)`);
            }"""
        )

        # A late message from the current WindowProxy but an older frame token
        # is rejected as well.
        frame.locator("body").evaluate(
            """() => parent.postMessage({
              type:'dataviz:control-snapshot',
              dashboard_id:window.dataviz.dashboard_id,
              run_id:window.dataviz.run_id,
              frame_id:'frame_stale',
              snapshot:{
                control_version:999,
                current_controls:{
                  'view:rogue/value':{intent:'explicit', value:['wrong-generation'], revision:1},
                },
                dashboard_controls:[],
              },
            }, location.origin)"""
        )
        page.wait_for_timeout(150)
        rogue_value = page.evaluate(
            """() => {
              const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
              const saved = JSON.parse(
                sessionStorage.getItem(`dataviz.tab-ui.v4.${sessionId}`)
              );
              return saved.dashboards['sales-overview'].controlCheckpoint?.controls?.['view:rogue/value'];
            }"""
        )
        assert rogue_value is None


@pytest.mark.e2e
def test_control_runtime_channel_is_versioned_idempotent_and_checkpointed(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "control-channel-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        expect(page.locator("#canvas-frame")).to_have_attribute(
            "data-runtime-ready", "true", timeout=20_000
        )

        result = page.evaluate(
            """async () => {
              const frame = document.querySelector('#canvas-frame');
              const identity = {
                dashboard_id:frame.dataset.dashboardId,
                run_id:frame.dataset.runId || null,
                frame_id:frame.dataset.frameId,
              };
              const exchange = (payload, match) => new Promise((resolve, reject) => {
                const timer = setTimeout(() => {
                  window.removeEventListener('message', receive);
                  reject(new Error(`No Control response for ${payload.type}`));
                }, 5000);
                const receive = event => {
                  if (event.source !== frame.contentWindow || !match(event.data || {})) return;
                  clearTimeout(timer);
                  window.removeEventListener('message', receive);
                  resolve(event.data);
                };
                window.addEventListener('message', receive);
                frame.contentWindow.postMessage({...payload, ...identity}, location.origin);
              });
              const actionId = crypto.randomUUID();
              const action = {
                type:'dataviz:control-action',
                action_id:actionId,
                source_view:null,
                base_control_version:0,
                action:{
                  type:'set',
                  control:'dashboard:sales-overview/region',
                  value:['华南'],
                  intent:'explicit',
                },
              };
              const first = await exchange(
                action,
                data => data.snapshot?.caused_by_action_id === actionId,
              );
              const duplicate = await exchange(
                action,
                data => data.snapshot?.caused_by_action_id === actionId,
              );
              const staleId = crypto.randomUUID();
              const stale = await exchange({
                ...action,
                action_id:staleId,
                action:{...action.action, value:['华东']},
              }, data => data.action_id === staleId);
              const invalidId = crypto.randomUUID();
              const invalid = await exchange({
                ...action,
                action_id:invalidId,
                base_control_version:first.snapshot.control_version,
                action:{...action.action, intent:'guess'},
              }, data => data.action_id === invalidId);
              const applyId = crypto.randomUUID();
              const applied = await exchange({
                type:'dataviz:control-apply',
                action_id:applyId,
                source_view:null,
                base_control_version:first.snapshot.control_version,
                keys:['dashboard:sales-overview/region'],
              }, data => data.snapshot?.caused_by_action_id === applyId);
              const secondId = crypto.randomUUID();
              const second = await exchange({
                ...action,
                action_id:secondId,
                base_control_version:first.snapshot.control_version,
                action:{...action.action, value:['华东']},
              }, data => data.snapshot?.caused_by_action_id === secondId);
              const lateDuplicate = await exchange(
                action,
                data => data.snapshot?.caused_by_action_id === actionId,
              );
              const lateRestore = await exchange({
                type:'dataviz:restore-checkpoint', checkpoint:null,
              }, data => data.type === 'dataviz:action-rejected'
                && data.code === 'restore_window_closed');
              await new Promise(resolve => setTimeout(resolve, 0));
              const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
              const saved = JSON.parse(
                sessionStorage.getItem(`dataviz.tab-ui.v4.${sessionId}`)
              ).dashboards['sales-overview'].controlCheckpoint;
              return {
                first, duplicate, stale, invalid, applied, second,
                lateDuplicate, lateRestore, saved,
              };
            }"""
        )

        assert result["first"]["type"] == "dataviz:control-snapshot"
        assert result["first"]["source_view"] is None
        assert result["first"]["snapshot"]["control_version"] == 1
        assert result["duplicate"] == result["first"]
        assert result["stale"]["code"] == "stale_control_version"
        assert result["stale"]["source_view"] is None
        assert result["stale"]["control_version"] == 1
        assert result["invalid"]["code"] == "control_action_intent_invalid"
        assert result["invalid"]["source_view"] is None
        assert result["invalid"]["control_version"] == 1
        assert result["applied"]["snapshot"]["control_version"] == 1
        assert result["second"]["snapshot"]["control_version"] == 2
        assert result["lateDuplicate"] == result["first"]
        assert result["lateRestore"]["code"] == "restore_window_closed"
        assert len(result["saved"]["control_contract_hash"]) == 64
        assert result["saved"]["controls"]["dashboard:sales-overview/region"]["value"] == ["华东"]

        page.frame_locator("#canvas-frame").locator("body").evaluate(
            """() => parent.postMessage({
              type:'dataviz:action-rejected',
              action_id:'malformed-reject-snapshot',
              source_view:null,
              code:'synthetic_rejection',
              snapshot:{control_version:'invalid', current_controls:{}},
              dashboard_id:window.dataviz.dashboard_id,
              run_id:window.dataviz.run_id,
              frame_id:window.dataviz.frame_id,
            }, location.origin)"""
        )
        expect(page.locator("#control-state")).to_have_text("Control Runtime disconnected.")


@pytest.mark.e2e
def test_view_applied_state_advances_only_for_current_ready_generation(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "view-generation-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        detail = frame.locator('[data-view-id="sales-detail"]')
        expect(detail).to_have_attribute("data-view-status", "ready", timeout=20_000)

        initial = frame.locator("body").evaluate(
            """() => {
              const renderer = window.datavizRuntime.renderers.get('table');
              const update = renderer.update.bind(renderer);
              window.__datavizViewGates = [];
              renderer.update = async (...args) => {
                await new Promise(resolve => window.__datavizViewGates.push(resolve));
                return update(...args);
              };
              return window.dataviz.stateSnapshot().consumer_revisions
                .views['sales-detail'].applied_control_state[
                  'dashboard:sales-overview/region'
                ];
            }"""
        )

        frame.locator("body").evaluate(
            """async () => {
              window.dataviz.control.set(
                'dashboard:sales-overview/region', ['华南'], {intent:'explicit'}
              );
              await window.dataviz.applyControls({
                keys:['dashboard:sales-overview/region'],
              });
            }"""
        )
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .__datavizViewGates.length === 1""",
            timeout=10_000,
        )
        frame.locator("body").evaluate(
            """async () => {
              window.dataviz.control.set(
                'dashboard:sales-overview/region', ['华东'], {intent:'explicit'}
              );
              await window.dataviz.applyControls({
                keys:['dashboard:sales-overview/region'],
              });
            }"""
        )
        pending = frame.locator("body").evaluate(
            """() => window.dataviz.stateSnapshot().consumer_revisions
              .views['sales-detail']"""
        )
        assert pending["stale"] is True
        assert pending["applied_control_state"]["dashboard:sales-overview/region"] == initial

        frame.locator("body").evaluate("() => window.__datavizViewGates[0]()")
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .__datavizViewGates.length === 2""",
            timeout=10_000,
        )
        superseded = frame.locator("body").evaluate(
            """() => window.dataviz.stateSnapshot().consumer_revisions
              .views['sales-detail'].applied_control_state[
                'dashboard:sales-overview/region'
              ]"""
        )
        assert superseded == initial

        frame.locator("body").evaluate("() => window.__datavizViewGates[1]()")
        page.wait_for_function(
            """() => {
              const frame = document.querySelector('#canvas-frame').contentWindow;
              const evidence = frame.dataviz.stateSnapshot().consumer_revisions
                .views['sales-detail'];
              return evidence.stale === false
                && evidence.applied_control_state[
                  'dashboard:sales-overview/region'
                ]?.value?.[0] === '华东';
            }""",
            timeout=10_000,
        )


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
            "field": "region",
            "type": "single_select",
            "value_type": "text",
            "initial": {"mode": "value", "value": "华东"},
            "options": {
                "mode": "static",
                "choices": [
                    {"label": "华东区域", "value": "华东"},
                    {"label": "华南区域", "value": "华南"},
                ],
            },
        }
    ]
    comparison = next(item for item in definition["views"] if item["id"] == "region-comparison")
    comparison["description"] = "当前分析：{{ controls.section.trend.focus_region }}"
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        title = frame.locator('[data-section-id="trend"] h2')
        description = frame.locator('[data-view-id="region-comparison"] .dv-view-description')
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
            '[data-control-key="section:trend/focus_region"] select[data-control-input]'
        )
        selector.select_option("华南", force=True)
        expect(title).to_have_text("华南区域趋势与结构", timeout=10_000)
        expect(description).to_have_text("当前分析：华南区域")
        affected = frame.locator("body").evaluate(
            "() => window.__selectionContentRenderCalls.at(-1)"
        )
        # Content bindings update their exact DOM targets without asking either
        # View Renderer to redraw.
        assert affected == []
        assert frame.locator('[data-view-id="total-revenue"]').evaluate(
            "node => Boolean(node.__selectionContentIdentity)"
        )

        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        report_path = tmp_path / "selection-content-report.html"
        download_info.value.save_as(report_path)
        report = report_path.read_text(encoding="utf-8")
        assert (
            '<h2 data-dv-content-field="sections.trend.title">华南区域趋势与结构</h2>'
        ) in report
        assert (
            'data-dv-content-field="views.region-comparison.description">当前分析：华南区域</p>'
        ) in report
        assert '"content_bindings": {' in report


@pytest.mark.e2e
def test_sources_inspector_exposes_resolved_and_parameterized_sql(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "source-evidence-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        page.locator('#parameter-form input[name="min_query_revenue"]').fill("150000")
        _run_and_wait(page)

        source = page.locator('[data-node-id="source:sales"]')
        expect(source).to_be_visible()
        source.click()

        inspector = page.locator("#node-inspector")
        expect(inspector).to_be_visible()
        expect(inspector.locator("#node-inspector-title")).to_have_text("销售数据")
        expect(inspector).to_contain_text("Resolved SQL")
        expect(inspector).to_contain_text("revenue >= 150000")
        expect(inspector).to_contain_text("demo-duckdb · duckdb")
        expect(inspector).to_contain_text("dashboards/sales-overview/sources/sales.sql")

        inspector.locator(".node-inspector__driver > summary").click()
        expect(inspector).to_contain_text("Driver statement")
        expect(inspector).to_contain_text("$min_query_revenue")
        expect(inspector).to_contain_text('"min_query_revenue": 150000')


@pytest.mark.e2e
def test_selection_impact_count_resolves_against_loaded_output_schemas(page: Page, tmp_path: Path):
    with _running_server(SHOWCASE) as base_url:
        _open_dashboard(page, base_url, "source-lab")

        dashboard_scope = page.locator(
            '#dashboard-control-form .control-scope[data-control-key="dashboard:source-lab/day"]'
        )
        expect(dashboard_scope.locator("[data-control-impact-count]")).to_have_text("Up to 3 views")

        _run_and_wait(page)
        expect(dashboard_scope.locator("[data-control-impact-count]")).to_have_text(
            "2 views",
            timeout=20_000,
        )

        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        report_path = tmp_path / "source-lab-impact.html"
        download_info.value.save_as(report_path)

    with _running_static_server(tmp_path) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        # Impact hints belong to the live Server shell. A portable report keeps
        # the Control itself, but does not manufacture a Server-only hint node.
        expect(page.locator('[data-control-key="dashboard:source-lab/day"]')).to_have_count(1)


@pytest.mark.e2e
def test_sources_inspector_loads_structured_python_execution_log(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SALES, tmp_path / "python-log-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales")
        _run_and_wait(page)

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
        "protocol": {"schema": "dataviz/runtime/v10", "component_registry_version": "3.0.0"},
        "control_state": {
            "dashboard:probe/region": {
                "intent": "explicit",
                "value": ["East"],
                "revision": 0,
            }
        },
        "view_specs": [{"id": "detail", "inputs": {"main": "source:data/main"}}],
        "dependency_contract": {
            "schema": "dataviz/dependency-contract/v11",
            "views": {
                "detail": {
                    "inputs": {"main": "source:data/main"},
                    "filter_contract": [
                        {
                            "key": "dashboard:probe/region",
                            "id": "region",
                            "origin": "dashboard",
                            "owner_id": "probe",
                            "definition": {
                                "type": "multiple_select",
                                "value_type": "text",
                                "path_fields": [],
                            },
                            "consumer_binding": {
                                "mode": "filter",
                                "control": "dashboard:probe/region",
                                "field": "region",
                                "inputs": ["main"],
                                "empty": "passthrough",
                                "operator": "auto",
                            },
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
          window.dataviz.control_state['dashboard:probe/region'] = {
            intent:'explicit', value:['West'], revision:1,
          };
          window.dispatchEvent(new CustomEvent('dataviz:controlchange'));
        }"""
    )
    expect(page.locator("#count")).to_have_text("2")


@pytest.mark.e2e
def test_component_gallery_story_overlay_keyboard_a11y_and_virtual_dom(page: Page, tmp_path: Path):
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
            owner_contract[key] for key in ("runtime", "data", "view", "section", "presentation")
        } == {"dataviz/runtime/v10"}
        assert {
            "data.pipeline",
            "view.declarative",
            "section.declarative",
            "presentation.shell",
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
        date_input = date_picker.locator('.dv-date-picker__control[type="text"]')
        expect(date_input).to_have_value(re.compile(r"^\d{4}-\d{2}-\d{2}$"))
        date_picker.locator("[data-control-trigger]").click()
        date_panel = date_picker.locator("[data-control-panel]")
        expect(date_panel).to_be_visible()
        expect(date_panel.locator(".dv-date-range__month")).to_have_count(1)
        date_input.fill("2026-02-31")
        expect(date_input).to_have_value("2026-02-31")
        expect(date_input).to_have_attribute("aria-invalid", "true")
        date_input.fill("2026-03-02")
        date_input.press("Enter")
        expect(date_input).to_have_value("2026-03-02")
        expect(date_input).to_have_attribute("aria-invalid", "false")
        if date_panel.is_visible():
            date_picker.locator("[data-control-trigger]").click()
        expect(date_panel).to_be_hidden()

        slider = header.locator(
            'input[type="range"][name="dashboard:component-gallery/confidence"]'
        )
        slider.fill("0.85")
        expect(slider.locator("xpath=..").locator(".dv-slider__input")).to_have_value("0.85")

        checkbox = header.locator('[data-control-component="checkbox-group"]')
        expect(checkbox).to_be_visible()
        expect(checkbox.locator(".dv-checkbox-group__toolbar")).to_have_count(0)
        options = checkbox.locator(".dv-checkbox-option")
        expect(options).to_have_count(3)
        expect(checkbox.locator("select option:checked")).to_have_count(3)
        options.nth(0).click()
        expect(checkbox.locator('select option[value="East"]:checked')).to_have_count(0)
        options.nth(0).click()
        expect(checkbox.locator("select option:checked")).to_have_count(3)
        for index in range(3):
            options.nth(index).click()
        expect(checkbox.locator("select option:checked")).to_have_count(0)
        # The remaining component specimens derive their inferred option domains
        # from the selected Dataset. Restore the dashboard domain explicitly and
        # synchronize on the compiled Control state; Chromium used to reach the
        # following tree assertions before the queued empty-domain update, while
        # Firefox exposed that accidental ordering dependency.
        for index in range(3):
            options.nth(index).click()
        expect(checkbox.locator("select option:checked")).to_have_count(3)
        page.keyboard.press("Escape")
        expect(header).not_to_have_attribute("open", "")

        story_index = frame.locator(".gallery-story-index")
        expect(story_index).to_be_visible()
        expect(story_index.locator("summary")).to_contain_text("38 runtime specimens")

        expected_states = {
            "ready",
            "loading",
            "stale",
            "empty",
            "error",
            "cancelled",
            "unavailable",
        }
        for family in ("control", "view", "section"):
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
        expect(tree.locator("xpath=ancestor::*[@data-control-key][1]")).to_have_attribute(
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
        tree_debug = tree.evaluate(
            """control => ({
              strategy:control.dataset.selectionStrategy,
              levels:control.dataset.cascaderLevels,
              nativeOptions:[...control.querySelector('select').options].map(option => option.value),
              treeItems:control.querySelectorAll('.dv-tree-option').length,
            })"""
        )
        assert tree.locator(".dv-tree-branch__check").count() > 0, tree_debug
        tree_branch = tree.locator(".dv-tree-branch__check").first
        tree_branch.click()
        assert tree.locator("select").evaluate("select => select.selectedOptions.length > 0")
        tree_summary = tree.locator("[data-control-summary]")
        expect(tree_summary).to_have_text(re.compile(r"\S"))
        # Selecting the only available parent is canonically "all available";
        # otherwise show_checked_strategy=parent emits compact parent tags. Both
        # summaries must avoid leaking full leaf paths into the trigger.
        assert " / " not in tree_summary.inner_text()
        tree.locator("footer button", has_text="Clear").click()
        assert tree.locator("select").evaluate("select => select.selectedOptions.length") == 0
        tree.locator(".dv-choice-search").press("Escape")

        radio = selections.locator('[data-control-component="radio-group"]')
        expect(radio.get_by_role("button", name="All", exact=True)).to_have_count(0)
        expect(radio.get_by_role("button", name="Clear", exact=True)).to_have_count(0)
        radio.locator("button", has_text="Software").press("Enter")
        expect(radio.locator("select")).to_have_value("Software")

        grouped_select = selections.locator(
            '[data-control-key="view:detail-table/product"] [data-control-component="select"]'
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
        assert grouped_select.locator(".dv-select-group").all_text_contents() == ["Core", "New"]
        grouped_select.locator(".dv-choice-search").fill("Growth")
        expect(grouped_select.locator("footer small")).to_contain_text("2 matching")
        grouped_action = grouped_select.locator(".dv-select-footer__actions button").first
        expect(grouped_action).to_have_text("Select all")
        grouped_action.click()
        assert (
            grouped_select.locator("select").evaluate("select => select.selectedOptions.length")
            == 2
        )
        expect(grouped_action).to_have_text("Invert")
        grouped_action.click()
        assert (
            grouped_select.locator("select").evaluate("select => select.selectedOptions.length")
            == 0
        )
        grouped_select.locator(".dv-choice-search").press("Escape")

        cascader = selections.locator('[data-control-component="cascader"]')
        cascader.locator("[data-control-trigger]").click()
        branch_check = cascader.locator(".dv-cascader-branch__check").first
        expect(branch_check).to_be_visible()
        branch_check.click()
        assert cascader.locator("select").evaluate("select => select.selectedOptions.length > 0")
        cascader_summary = cascader.locator("[data-control-summary]")
        expect(cascader_summary).to_have_text(re.compile(r"\S"))
        assert " / " not in cascader_summary.inner_text()
        cascader.locator(".dv-choice-search").press("Escape")

        range_picker = selections.locator('[data-control-component="range-picker"]')
        expect(range_picker.locator("[data-control-trigger]")).to_have_count(1)
        expect(range_picker.locator('input[type="date"]')).to_have_count(0)
        expect(range_picker.locator('.dv-date-range__endpoint[type="text"]')).to_have_count(2)
        range_picker.locator("[data-control-trigger]").click()
        date_panel = range_picker.locator("[data-control-panel]")
        expect(date_panel).to_be_visible()
        expect(date_panel).to_have_attribute("role", "dialog")
        expect(date_panel.locator(".dv-date-range__month")).to_have_count(2)
        range_picker.locator("button", has_text="Q1 2026").click()
        expect(range_picker.locator("input[data-control-input]")).to_have_value(
            "2026-01-01,2026-03-31"
        )
        expect(date_panel).to_be_hidden()
        endpoints = range_picker.locator(".dv-date-range__endpoint")
        endpoints.nth(0).fill("2026-01-05")
        endpoints.nth(1).fill("2026-01-12")
        endpoints.nth(1).press("Enter")
        expect(range_picker.locator("input[data-control-input]")).to_have_value(
            "2026-01-05,2026-01-12"
        )
        range_picker.locator("[data-control-trigger]").click()
        date_panel.locator('[data-date="2026-01-10"]').click()
        expect(date_panel).to_be_visible()
        date_panel.locator('[data-date="2026-01-20"]').click()
        expect(range_picker.locator("input[data-control-input]")).to_have_value(
            "2026-01-10,2026-01-20"
        )
        expect(date_panel).to_be_hidden()
        range_picker.locator("[data-control-trigger]").click()
        range_picker.locator("button", has_text="Clear").click()
        expect(range_picker.locator("input[data-control-input]")).to_have_value("")
        frame.locator("body").evaluate(
            """() => new Promise((resolve, reject) => {
              const deadline = performance.now() + 3000;
              const check = () => {
                const state = window.dataviz.control.state('view:detail-table/date-window');
                if (state.value.length === 0) return resolve();
                if (performance.now() > deadline) return reject(new Error(JSON.stringify(state)));
                setTimeout(check, 25);
              };
              check();
            })"""
        )
        expect(detail.locator("tbody tr")).to_have_count(8)

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
def test_default_query_grid_uses_up_to_six_bounded_tracks_without_oversizing_range_picker(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(MINIMAL, tmp_path / "six-column-query-grid")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["query_parameters"].insert(
        0,
        {
            "id": "job_date_range",
            "type": "range_input",
            "value_type": "date",
            "label": "Analysis window",
            "required": True,
            "default": ["2026-08-17", "2026-08-23"],
        },
    )
    definition["query_parameters"].extend(
        {
            "id": f"scenario_{index:02d}",
            "type": "single_input",
            "value_type": "number",
            "label": f"Scenario {index:02d}",
            "default": index,
        }
        for index in range(1, 10)
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    presentation_path = workspace / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation["control_components"] = {
        "query:scenario_01": {"span": 2},
    }
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    page.set_viewport_size({"width": 2048, "height": 900})
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        form = page.locator("#parameter-form")
        range_field = form.locator(".field", has=page.locator("#input-job_date_range"))
        wide_field = form.locator(".field", has=page.locator("#input-scenario_01"))
        expect(range_field.locator("[data-control-trigger]")).to_be_visible()

        wide = form.evaluate(
            """form => ({
              columns:getComputedStyle(form).gridTemplateColumns.split(' ').length,
              width:form.getBoundingClientRect().width,
              ownerWidth:form.parentElement.getBoundingClientRect().width,
            })"""
        )
        assert wide["columns"] == 5, wide
        assert wide["columns"] <= 6, wide
        assert wide["width"] >= wide["ownerWidth"] * 0.94, wide
        range_box = range_field.bounding_box()
        wide_box = wide_field.bounding_box()
        assert range_box is not None and wide_box is not None
        assert range_box["width"] < 500, range_box
        assert wide_box["width"] > range_box["width"] * 1.8, (range_box, wide_box)
        assert range_field.locator(".dv-date-range__field").evaluate(
            """field => {
              const owner = field.closest('.field').getBoundingClientRect();
              const rect = field.getBoundingClientRect();
              return rect.left >= owner.left - 1 && rect.right <= owner.right + 1;
            }"""
        )

        page.set_viewport_size({"width": 760, "height": 700})
        expect(page.locator("#query-parameters-control")).to_have_attribute(
            "data-control-effective-columns", "2"
        )
        assert (
            form.evaluate("form => getComputedStyle(form).gridTemplateColumns.split(' ').length")
            == 2
        )

        page.set_viewport_size({"width": 480, "height": 700})
        expect(page.locator("#query-parameters-control")).to_have_attribute(
            "data-control-effective-columns", "1"
        )
        narrow = form.evaluate(
            """form => ({
              columns:getComputedStyle(form).gridTemplateColumns.split(' ').length,
              width:form.getBoundingClientRect().width,
              widest:Math.max(...[...form.children].map(item => item.getBoundingClientRect().width)),
            })"""
        )
        assert narrow["columns"] == 1, narrow
        assert narrow["widest"] <= narrow["width"] + 1, narrow


@pytest.mark.e2e
def test_query_control_tray_is_responsive_bounded_and_selector_safe(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "adaptive-control-tray")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["query_parameters"].extend(
        {
            "id": f"scenario_{index:02d}",
            "type": "single_input",
            "value_type": "number",
            "label": f"Scenario {index:02d}",
            "default": index,
        }
        for index in range(1, 24)
    )
    definition["query_parameters"].append(
        {
            "id": "model_list",
            "type": "multiple_select",
            "value_type": "text",
            "label": "Model list",
            "default": {"mode": "include", "values": ["model-01"]},
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
            "columns": 4,
            "density": "compact",
        }
    }
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    page.set_viewport_size({"width": 1800, "height": 720})
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

        wide_geometry = panel.evaluate(
            """panel => {
              const form = panel.querySelector('#parameter-form');
              const card = panel.closest('.dv-query-card').getBoundingClientRect();
              const frame = document.querySelector('#canvas-frame').getBoundingClientRect();
              return {
                panelWidth: panel.getBoundingClientRect().width,
                formWidth: form.getBoundingClientRect().width,
                columns: getComputedStyle(form).gridTemplateColumns.split(' ').length,
                cardLeft:card.left,
                cardRight:card.right,
                frameLeft:frame.left,
                frameRight:frame.right,
              };
            }"""
        )
        assert wide_geometry["columns"] == 4, wide_geometry
        assert wide_geometry["formWidth"] >= wide_geometry["panelWidth"] * 0.94, wide_geometry
        assert abs((wide_geometry["cardLeft"] - wide_geometry["frameLeft"]) - 48) <= 1, (
            wide_geometry
        )
        assert abs((wide_geometry["frameRight"] - wide_geometry["cardRight"]) - 48) <= 1, (
            wide_geometry
        )

        page.set_viewport_size({"width": 900, "height": 360})
        # ResizeObserver publishes the effective track count on the next
        # rendering turn. Wait for that explicit Runtime state instead of
        # racing computed style immediately after changing the viewport.
        expect(control).not_to_have_attribute(
            "data-control-effective-columns",
            "4",
        )

        geometry = panel.evaluate(
            """panel => {
              const form = panel.querySelector('#parameter-form');
              const rect = panel.getBoundingClientRect();
              const owner = panel.closest('[data-control-role="query"]');
              const card = panel.closest('.dv-query-card');
              return {
                position:getComputedStyle(panel).position,
                width:rect.width,
                cardWidth:card.getBoundingClientRect().width,
                configuredColumns:owner.dataset.controlColumns,
                effectiveColumns:owner.dataset.controlEffectiveColumns,
                columnWidth:Number(owner.dataset.controlColumnWidth),
                columns: getComputedStyle(form).gridTemplateColumns.split(' ').length,
                formWidth:form.getBoundingClientRect().width,
                panelClientHeight: panel.clientHeight,
                panelScrollHeight: panel.scrollHeight,
                panelOverflow: getComputedStyle(panel).overflow,
              };
            }"""
        )
        assert geometry["position"] == "relative", geometry
        # The panel occupies the Card content box; the two-pixel delta is the
        # Card's left and right border.
        assert abs(geometry["width"] - geometry["cardWidth"]) <= 2, geometry
        assert geometry["configuredColumns"] == "4"
        expected_columns = max(
            1,
            min(4, int((geometry["formWidth"] + 10) // (geometry["columnWidth"] + 10))),
        )
        assert geometry["columns"] == expected_columns
        assert geometry["effectiveColumns"] == str(expected_columns)
        assert geometry["panelOverflow"] == "auto"
        assert geometry["panelScrollHeight"] > geometry["panelClientHeight"]

        page.evaluate(
            """() => {
              const card = document.querySelector('.dv-query-card');
              window.scrollTo(0, card.offsetTop + card.offsetHeight + 100);
            }"""
        )
        page.wait_for_timeout(100)
        flow_geometry = page.evaluate(
            """() => ({
              topbarTop:document.querySelector('.topbar').getBoundingClientRect().top,
              panelBottom:document.querySelector('#query-parameters-panel').getBoundingClientRect().bottom,
            })"""
        )
        assert abs(flow_geometry["topbarTop"]) <= 1, flow_geometry
        assert flow_geometry["panelBottom"] <= 1, flow_geometry
        page.evaluate("window.scrollTo(0, 0)")

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

        # At tablet width the open Sidebar is intentionally an overlay. Close
        # it before exercising controls underneath that overlay.
        page.locator("#sidebar-toggle").click()
        expect(page.locator("body")).to_have_class(re.compile(r"\bsidebar-collapsed\b"))
        panel.evaluate("panel => { panel.scrollTop = panel.scrollHeight; }")
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
def test_cross_browser_narrow_control_overlay_keyboard_scroll_and_aria(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "narrow-control-matrix")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["query_parameters"].extend(
        {
            "id": f"scenario_{index:02d}",
            "type": "single_input",
            "value_type": "number",
            "label": f"Scenario {index:02d}",
            "default": index,
        }
        for index in range(1, 16)
    )
    definition["query_parameters"].append(
        {
            "id": "model_list",
            "type": "multiple_select",
            "value_type": "text",
            "label": "Model list",
            "default": {"mode": "include", "values": ["model-01"]},
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
                panelClientHeight:panel.clientHeight,
                panelScrollHeight:panel.scrollHeight,
                panelOverflow:getComputedStyle(panel).overflowY,
              };
            }"""
        )
        assert geometry["left"] >= 8, geometry
        assert geometry["top"] >= 8, geometry
        assert geometry["right"] <= geometry["viewport"][0] - 8, geometry
        assert geometry["height"] <= geometry["viewport"][1] * 0.52 + 1, geometry
        assert geometry["columns"] == 1, geometry
        assert geometry["panelScrollHeight"] > geometry["panelClientHeight"], geometry
        assert geometry["panelOverflow"] == "auto", geometry

        panel.evaluate("panel => { panel.scrollTop = panel.scrollHeight; }")
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
        assert selector_geometry["bottom"] <= selector_geometry["viewport"][1] - 8, (
            selector_geometry
        )
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
    definition["controls"][0].pop("initial")
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
        selector = header.locator('select[name="dashboard:sales-overview/region"]')
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
def test_unified_dashboard_controls_drive_browser_named_output(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "showcase-controls")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        control = page.locator("#dashboard-controls-control")
        expect(control.locator("#dashboard-control-meta")).to_have_text("2 controls")
        control.locator("summary").click()
        expect(control.locator("#dashboard-control-group")).to_be_visible()
        expect(control.locator("#dashboard-control-form .control-scope")).to_have_count(2)

        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        radial = frame.locator('[data-view-id="radial"]')
        expect(radial).to_have_attribute("data-view-status", "ready", timeout=15_000)

        province = page.locator('select[name="dashboard:chart-gallery/province"]')
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
        city_count = page.locator('input[name="dashboard:chart-gallery/radar_city_count"]')
        city_count.fill("1")
        page.wait_for_function(
            """() => {
              const frame = document.querySelector('#canvas-frame').contentWindow;
              const output = frame.dataviz.portable.outputs['interactive:latest-metrics/main'];
              return frame.dataviz.control.value('dashboard:chart-gallery/radar_city_count') === 1
                && Array.isArray(output) && output.length === 1
                && output[0].province === '广东';
            }""",
            timeout=15_000,
        )
        expect(radial).to_have_attribute("data-view-status", "ready")
        page.locator("#sidebar-toggle").click()
        expect(control).not_to_have_attribute("open", "")


@pytest.mark.e2e
def test_selection_cascade_popovers_view_isolation_and_table_wheel(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "showcase")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "cascade-explorer")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator('[data-view-id="map-bars"][data-view-status="ready"]')).to_be_visible(
            timeout=15_000
        )

        # Header and Canvas-owned popovers both close when focus moves elsewhere.
        header = page.locator("#dashboard-controls-control")
        header.locator("summary").click()
        expect(header).to_have_attribute("open", "")
        province = header.locator('[data-control-component="checkbox-group"]')
        expect(province.locator(".dv-checkbox-group__toolbar")).to_have_count(0)
        guangdong = province.locator("button", has_text="广东")
        fujian = province.locator("button", has_text="福建")
        guangdong.click()
        fujian.click()
        assert province.locator("select").evaluate("select => select.selectedOptions.length") == 0
        guangdong.click()
        fujian.click()
        assert province.locator("select").evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        ) == ["广东", "福建"]
        guangdong.click()
        assert province.locator("select").evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        ) == ["福建"]
        guangdong.click()
        frame.locator('[data-view-id="map-bars"] .dv-view-body').click()
        expect(header).not_to_have_attribute("open", "")

        section_popover = frame.locator('.dv-context-controls[data-control-origin="section"]')
        section_popover.locator("summary").click()
        expect(section_popover).to_have_attribute("open", "")
        frame.locator(".cascade-hero").click()
        expect(section_popover).not_to_have_attribute("open", "")

        dashboard_select = page.locator('select[name="dashboard:cascade-explorer/province"]')
        city_select = frame.locator(
            '[data-control-key="section:geography/city"] select[data-control-input]'
        )
        city_rows = frame.locator('[data-view-id="city-detail"] tbody tr')
        expect(city_select).to_have_count(1)
        expect(city_select.locator("option:not([disabled])")).to_have_count(4)
        assert set(
            city_select.evaluate(
                "select => [...select.selectedOptions].map(option => option.value)"
            )
        ) == {"深圳", "佛山", "厦门", "泉州"}
        expect(city_rows).to_have_count(7)
        dashboard_select.select_option(["福建"], force=True)
        expect(city_select).to_have_values(["厦门", "泉州"], timeout=5_000)
        expect(city_rows).to_have_count(3, timeout=5_000)
        enabled_cities = city_select.evaluate(
            "select => [...select.options].filter(option => !option.disabled).map(option => option.value)"
        )
        assert enabled_cities == ["厦门", "泉州"]
        assert (
            frame.locator("body").evaluate(
                "() => window.dataviz.control.state('section:geography/city').intent"
            )
            == "all_available"
        )

        dashboard_select.select_option(["广东", "福建"], force=True)
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow.document
              .querySelector('[data-control-key="section:geography/city"] select[data-control-input]')
              ?.selectedOptions.length === 4"""
        )
        assert set(
            city_select.evaluate(
                "select => [...select.selectedOptions].map(option => option.value)"
            )
        ) == {"深圳", "佛山", "厦门", "泉州"}
        expect(city_rows).to_have_count(7, timeout=5_000)

        # Explicit subsets keep their identity even if an upstream contraction
        # temporarily makes that subset equal to the complete available domain.
        city_select.select_option(["厦门"], force=True)
        expect(city_rows).to_have_count(2, timeout=5_000)
        assert (
            frame.locator("body").evaluate(
                "() => window.dataviz.control.state('section:geography/city').intent"
            )
            == "explicit"
        )
        dashboard_select.select_option(["福建"], force=True)
        expect(city_select).to_have_values(["厦门"], timeout=5_000)
        dashboard_select.select_option(["广东", "福建"], force=True)
        expect(city_select).to_have_values(["厦门"], timeout=5_000)
        expect(city_rows).to_have_count(2, timeout=5_000)

        # A non-empty explicit choice that becomes completely unavailable falls
        # back to the configured initial policy (implicit all for this multi-select).
        city_select.select_option(["深圳"], force=True)
        dashboard_select.select_option(["福建"], force=True)
        expect(city_select).to_have_values(["厦门", "泉州"], timeout=5_000)

        # An empty set chosen by the user is intentional and must not be replaced
        # merely because an upstream candidate domain changes.
        city_select.select_option([], force=True)
        dashboard_select.select_option(["广东"], force=True)
        expect(city_select).to_have_values([], timeout=5_000)
        dashboard_select.select_option(["广东", "福建"], force=True)

        city_select.select_option(["深圳", "厦门"], force=True)
        page.wait_for_function(
            """() => {
              const values = document.querySelector('#canvas-frame').contentWindow.dataviz
                .control.value('section:geography/city');
              return values.length === 2 && values.includes('深圳') && values.includes('厦门');
            }"""
        )
        assert set(
            city_select.evaluate(
                "select => [...select.selectedOptions].map(option => option.value)"
            )
        ) == {"深圳", "厦门"}
        view_popover = frame.locator(
            '[data-view-id="city-detail"] .dv-context-controls[data-control-origin="view"]'
        )
        view_popover.locator("summary").click()
        cascader = view_popover.locator('[data-control-component="cascader"]')
        cascader.locator("[data-control-trigger]").click()
        cascader.locator("footer button", has_text="Clear").click()
        columns = cascader.locator(".dv-cascader-columns")
        page.wait_for_function(
            """() => {
              const state = document.querySelector('#canvas-frame').contentWindow.dataviz.control;
              return state.value('section:geography/city').length === 2
                && state.value('view:city-detail/district').length === 0;
            }"""
        )

        columns.locator(".dv-cascader-column").nth(0).locator("button", has_text="广东").click()
        columns.locator(".dv-cascader-column").nth(1).locator("button", has_text="深圳").click()
        columns.locator(".dv-cascader-column").nth(2).locator("button", has_text="南山区").click()
        columns.locator(".dv-cascader-column").nth(0).locator("button", has_text="福建").click()
        columns.locator(".dv-cascader-column").nth(1).locator("button", has_text="厦门").click()
        columns.locator(".dv-cascader-column").nth(2).locator("button", has_text="思明区").click()

        district_select = frame.locator(
            '[data-control-key="view:city-detail/district"] select[data-control-input]'
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
              const select = frame.document.querySelector('[data-control-key="view:city-detail/district"] select[data-control-input]');
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
        frame.locator(
            '[data-control-key="view:city-detail/min_value"] input[data-control-input]'
        ).evaluate(
            """input => {
              window.__datavizRenderCalls = [];
              input.value = '70';
              input.dispatchEvent(new Event('change', {bubbles:true}));
            }"""
        )
        page.wait_for_timeout(250)
        affected = frame.locator("body").evaluate("() => window.__datavizRenderCalls.at(-1)")
        assert affected == ["city-detail"]

        # A short basic table releases a vertical wheel to the Canvas page.
        scroll_after = frame.locator('[data-view-id="city-detail"] .dv-table-wrap').evaluate(
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
def test_managed_renderer_lifecycle_matrix_in_server_and_export(page: Page, tmp_path: Path):
    """One behavioral contract guards every imperative managed Renderer.

    Renderer implementations keep the small validate/mount/update/dispose hook
    API. The platform owns the wider behavioral matrix exercised here:
    mount -> update -> empty -> restore -> interaction -> resize -> dispose -> export.
    """
    _route_perspective_contract_runtime(page)
    workspace = _copy_workspace(MINIMAL, tmp_path / "renderer-lifecycle")
    report_path = tmp_path / "renderer-lifecycle.html"
    view_ids = ["revenue-trend", "region-comparison", "sales-perspective"]

    def expect_ready(frame):
        for view_id in view_ids:
            expect(frame.locator(f'[data-view-id="{view_id}"]')).to_have_attribute(
                "data-view-status", "ready", timeout=30_000
            )

    def mark_instances(frame):
        return frame.locator("body").evaluate(
            """(_body, ids) => {
              const states = window.datavizRuntime.viewAdapter.states;
              const trend = states.get(ids[0]).state;
              const comparison = states.get(ids[1]).state;
              const perspective = states.get(ids[2]).state;
              trend.node.__datavizLifecycleIdentity = 'trend-mounted';
              comparison.node.__datavizLifecycleIdentity = 'comparison-mounted';
              perspective.viewer.__datavizLifecycleIdentity = 'perspective-mounted';
              return {
                hooks:[...window.datavizRuntime.viewAdapter.lifecycle.hooks],
                phases:[...window.datavizRuntime.viewAdapter.lifecycle.phases],
                perspectiveWorkerOwned:Boolean(perspective.worker),
              };
            }""",
            view_ids,
        )

    def assert_update_reuses_instances(frame):
        identities = frame.locator("body").evaluate(
            """(_body, ids) => {
              const states = window.datavizRuntime.viewAdapter.states;
              return [
                states.get(ids[0]).state.node.__datavizLifecycleIdentity,
                states.get(ids[1]).state.node.__datavizLifecycleIdentity,
                states.get(ids[2]).state.viewer.__datavizLifecycleIdentity,
              ];
            }""",
            view_ids,
        )
        assert identities == ["trend-mounted", "comparison-mounted", "perspective-mounted"]

    def assert_interaction_and_resize(frame):
        evidence = frame.locator("body").evaluate(
            """async (_body, ids) => {
              const runtime = window.datavizRuntime;
              const states = runtime.viewAdapter.states;
              const trend = states.get(ids[0]).state;
              const comparison = states.get(ids[1]).state;
              const perspective = states.get(ids[2]).state;

              let trendInteraction = 0;
              let comparisonInteraction = 0;
              trend.node.once('plotly_click', () => { trendInteraction += 1; });
              comparison.node.once('plotly_click', () => { comparisonInteraction += 1; });
              trend.node.emit('plotly_click', {
                points:[{curveNumber:0, pointNumber:0}],
              });
              comparison.node.emit('plotly_click', {
                points:[{curveNumber:0, pointNumber:0}],
              });

              const expectedSettings = true;
              const perspectiveDeadline = performance.now() + 5000;
              let perspectiveConfig = await perspective.viewer.save();
              while (
                perspectiveConfig.settings !== expectedSettings
                && performance.now() < perspectiveDeadline
              ) {
                await perspective.viewer.restore({
                  plugin:perspectiveConfig.plugin,
                  group_by:perspectiveConfig.group_by,
                  split_by:perspectiveConfig.split_by,
                  columns:perspectiveConfig.columns,
                  aggregates:perspectiveConfig.aggregates,
                  filter:perspectiveConfig.filter,
                  sort:perspectiveConfig.sort,
                  settings:expectedSettings,
                });
                await perspective.viewer.flush();
                perspectiveConfig = await perspective.viewer.save();
                if (perspectiveConfig.settings !== expectedSettings) {
                  await new Promise(resolve => setTimeout(resolve, 50));
                }
              }

              const beforeResize = runtime.metrics.renderers.resizes;
              runtime.viewAdapter.states.get(ids[0]).state
                && runtime.viewAdapter.states.get(ids[0]).state.node
                && window.dataviz.charts.plotly.resize(trend);
              window.dataviz.charts.plotly.resize(comparison);
              await perspective.viewer.resize();
              return {
                trendInteraction,
                comparisonInteraction,
                perspectiveSettings:perspectiveConfig.settings,
                perspectiveConfig,
                resizeDelta:runtime.metrics.renderers.resizes - beforeResize,
                failures:runtime.metrics.renderers.failed,
              };
            }""",
            view_ids,
        )
        assert evidence["trendInteraction"] == 1
        assert evidence["comparisonInteraction"] == 1
        assert evidence["perspectiveSettings"] is True, evidence
        assert evidence["resizeDelta"] >= 2
        assert evidence["failures"] == 0

    def assert_dispose(frame):
        evidence = frame.locator("body").evaluate(
            """async (_body, ids) => {
              const runtime = window.datavizRuntime;
              const perspectiveBefore = structuredClone(runtime.metrics.perspective);
              runtime.dispose();
              const deadline = performance.now() + 5000;
              while (
                runtime.metrics.perspective.disposed < perspectiveBefore.created
                && performance.now() < deadline
              ) await new Promise(resolve => setTimeout(resolve, 20));
              return {
                states:runtime.viewAdapter.states.size,
                rendererMetrics:structuredClone(runtime.metrics.renderers),
                perspectiveMetrics:structuredClone(runtime.metrics.perspective),
              };
            }""",
            view_ids,
        )
        assert evidence["states"] == 0
        assert evidence["rendererMetrics"]["disposes"] >= 3
        assert evidence["perspectiveMetrics"]["disposed"] >= 1
        assert evidence["rendererMetrics"]["failed"] == 0

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")

        # mount
        expect_ready(frame)
        contract = mark_instances(frame)
        assert contract == {
            "hooks": ["validate", "mount", "update", "dispose"],
            "phases": [
                "mount",
                "update",
                "empty",
                "restore",
                "interaction",
                "resize",
                "dispose",
                "export",
            ],
            "perspectiveWorkerOwned": True,
        }

        # update: retain one region and preserve each Renderer instance.
        page.locator("#dashboard-controls-control > summary").click()
        options = page.locator(
            '#dashboard-control-form [data-control-component="checkbox-group"] .dv-checkbox-option'
        )
        expect(options).to_have_count(3)
        options.nth(1).click()
        options.nth(2).click()
        expect_ready(frame)
        assert_update_reuses_instances(frame)

        # empty: the host publishes one terminal state and disposes all Renderers.
        options.nth(0).click()
        for view_id in view_ids:
            view = frame.locator(f'[data-view-id="{view_id}"]')
            expect(view).to_have_attribute("data-view-status", "empty", timeout=2_000)
            expect(view).to_contain_text("No rows match the current selections.")
        assert frame.locator("body").evaluate(
            "(_body, ids) => ids.every(id => !window.datavizRuntime.viewAdapter.states.has(id))",
            view_ids,
        )

        # restore: every Renderer mounts exactly one fresh instance.
        options.nth(0).click()
        expect_ready(frame)
        restored = frame.locator("body").evaluate(
            """(_body, ids) => ({
              identities:[
                window.datavizRuntime.viewAdapter.states.get(ids[0]).state
                  .node.__datavizLifecycleIdentity || null,
                window.datavizRuntime.viewAdapter.states.get(ids[1]).state
                  .node.__datavizLifecycleIdentity || null,
                window.datavizRuntime.viewAdapter.states.get(ids[2]).state
                  .viewer.__datavizLifecycleIdentity || null,
              ],
              metrics:structuredClone(window.datavizRuntime.metrics.renderers),
            })""",
            view_ids,
        )
        assert restored["identities"] == [None, None, None]
        assert restored["metrics"]["restores"] >= 3

        # interaction + resize
        assert_interaction_and_resize(frame)

        # export is generated from the same live canonical state before the
        # Server host is explicitly disposed.
        page.locator("#dashboard-controls-control > summary").click()
        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

        # dispose
        assert_dispose(frame)

    # export: the portable host repeats the same lifecycle rather than using a
    # separate static chart implementation.
    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        expect_ready(page)
        mark_instances(page)
        selection = page.locator(
            '[data-control-key="dashboard:sales-overview/region"] select[data-control-input]'
        )

        selection.select_option(["华南"], force=True)
        expect_ready(page)
        assert_update_reuses_instances(page)

        selection.evaluate(
            """input => {
              window.datavizComponents.controls.clearOptions(input);
              window.datavizComponents.controls.markSelectionIntent(input, 'explicit');
              window.datavizComponents.controls.emitChange(input);
            }"""
        )
        for view_id in view_ids:
            expect(page.locator(f'[data-view-id="{view_id}"]')).to_have_attribute(
                "data-view-status", "empty", timeout=2_000
            )

        selection.evaluate(
            """input => {
              input.options[0].selected = true;
              window.datavizComponents.controls.markSelectionIntent(input, 'explicit');
              window.datavizComponents.controls.emitChange(input);
            }"""
        )
        expect_ready(page)
        assert_interaction_and_resize(page)
        assert_dispose(page)


@pytest.mark.e2e
def test_perspective_async_mount_has_bounded_table_fallback(page: Page, tmp_path: Path):
    """An unresolved external Renderer cannot leave a View permanently Loading."""
    workspace = _copy_workspace(MINIMAL, tmp_path / "perspective-bounded-fallback")
    page.add_init_script(
        """(() => {
          window.__datavizRendererOperationTimeoutMs = 100;
          Object.defineProperty(window, 'datavizPerspectiveReady', {
            configurable:true,
            get() { return new Promise(() => {}); },
            set(_value) {},
          });
        })();"""
    )
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        perspective = frame.locator('[data-view-id="sales-perspective"]')
        expect(perspective).to_have_count(1, timeout=20_000)
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=5_000)
        expect(perspective.locator("[data-view-status-label]")).to_have_text("table fallback")
        expect(perspective.locator("table")).to_have_count(1)
        assert (
            frame.locator("body").evaluate("window.datavizRuntime.metrics.perspective.failed") == 1
        )


@pytest.mark.e2e
def test_same_view_control_dependency_reconciles_in_server_and_export(page: Page, tmp_path: Path):
    workspace = _build_same_view_dependency_workspace(tmp_path / "same-view-controls")
    report_path = tmp_path / "same-view-controls.html"
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "same-view-controls")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        detail = frame.locator('[data-view-id="daily-detail"]')
        expect(detail).to_have_attribute("data-view-status", "empty", timeout=15_000)
        controls = detail.locator('.dv-context-controls[data-control-origin="view"]')
        controls.locator("summary").click()
        dow = frame.locator('[data-control-key="view:daily-detail/dow"] select[data-control-input]')
        dates = frame.locator(
            '[data-control-key="view:daily-detail/dates"] select[data-control-input]'
        )

        dow.select_option("周一", force=True)
        expect(dates).to_have_values(["2026-08-03", "2026-08-10"], timeout=5_000)
        expect(detail.locator("tbody tr")).to_have_count(2)
        dow.select_option("周二", force=True)
        expect(dates).to_have_values(["2026-08-04"], timeout=5_000)
        expect(detail.locator("tbody tr")).to_have_count(1)
        dow.select_option("周一", force=True)
        expect(dates).to_have_values(["2026-08-03", "2026-08-10"], timeout=5_000)
        expect(detail.locator("tbody tr")).to_have_count(2)

        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        detail = page.locator('[data-view-id="daily-detail"]')
        expect(detail).to_have_attribute("data-view-status", "ready", timeout=15_000)
        dates = page.locator(
            '[data-control-key="view:daily-detail/dates"] select[data-control-input]'
        )
        expect(dates).to_have_values(["2026-08-03", "2026-08-10"])
        expect(detail.locator("tbody tr")).to_have_count(2)


@pytest.mark.e2e
def test_plotly_defaults_to_page_wheel_and_allows_explicit_scroll_zoom(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "plotly-wheel")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    dashboard = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    explicit_view = next(view for view in dashboard["views"] if view["id"] == "region-comparison")
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

        expect(default_chart.locator(".modebar-btn")).to_have_count(0)
        expect(explicit_chart.locator(".modebar-btn")).to_have_count(0)
        assert default_chart.evaluate("node => node._context.scrollZoom") is False
        assert explicit_chart.evaluate("node => node._context.scrollZoom") is True

        default_chart.scroll_into_view_if_needed()
        before = default_chart.evaluate(
            """node => ({
              scrollY:window.scrollY,
              maxScrollY:Math.max(0, document.documentElement.scrollHeight - window.innerHeight),
              shellScrollY:window.parent.scrollY,
              shellMaxScrollY:Math.max(
                0,
                window.parent.document.documentElement.scrollHeight - window.parent.innerHeight,
              ),
              xRange:[...node._fullLayout.xaxis.range],
            })"""
        )
        drag_layer = default_chart.locator(".nsewdrag")
        can_scroll_down = (
            before["shellScrollY"] < before["shellMaxScrollY"] - 1
            or before["scrollY"] < before["maxScrollY"] - 1
        )
        wheel_delta = 500 if can_scroll_down else -500
        drag_layer.evaluate(
            """(node, deltaY) => node.dispatchEvent(new WheelEvent('wheel', {
              bubbles:true,
              cancelable:true,
              composed:true,
              deltaY,
            }))""",
            wheel_delta,
        )
        page.wait_for_timeout(150)
        after = default_chart.evaluate(
            """node => ({
              scrollY:window.scrollY,
              shellScrollY:window.parent.scrollY,
              xRange:[...node._fullLayout.xaxis.range],
            })"""
        )
        before_scroll = before["shellScrollY"] + before["scrollY"]
        after_scroll = after["shellScrollY"] + after["scrollY"]
        if wheel_delta > 0:
            assert after_scroll > before_scroll
        else:
            assert after_scroll < before_scroll
        assert after["xRange"] == before["xRange"]


@pytest.mark.e2e
def test_perspective_fills_view_uses_opaque_settings_and_releases_page_wheel(
    page: Page, tmp_path: Path
):
    _route_perspective_contract_runtime(page)
    workspace = _copy_workspace(MINIMAL, tmp_path / "minimal")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    dashboard_path.write_text(
        dashboard_path.read_text(encoding="utf-8").replace("settings: false", "settings: true"),
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

        plugin_choice = viewer.locator('.plugin-select-item[data-plugin="Datagrid"]')
        expect(plugin_choice).to_be_visible(timeout=10_000)
        plugin_choice.click()
        expect(viewer.locator("#plugin_selector_container")).to_have_class(re.compile(r"\bopen\b"))

        identity = viewer.evaluate("viewer => (viewer.__datavizTestIdentity = crypto.randomUUID())")
        dashboard_select = page.locator('select[name="dashboard:sales-overview/region"]')
        dashboard_select.select_option(["华东"], force=True)
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .datavizRuntime.metrics.perspective.updated >= 1"""
        )
        assert viewer.evaluate("viewer => viewer.__datavizTestIdentity") == identity

        scroll_state = viewer.evaluate(
            """viewer => {
              window.scrollTo(0, 0);
              const before = window.parent.scrollY + window.scrollY;
              viewer.dispatchEvent(new WheelEvent('wheel', {
                deltaY: 500, bubbles: true, cancelable: true, composed: true
              }));
              return {before, after:window.parent.scrollY + window.scrollY};
            }"""
        )
        assert scroll_state["after"] > scroll_state["before"]

        disposed = frame.locator("body").evaluate(
            """async () => {
              window.datavizRuntime.dispose();
              await new Promise(resolve => setTimeout(resolve, 100));
              return window.datavizRuntime.metrics.perspective.disposed;
            }"""
        )
        assert disposed >= 1


@pytest.mark.e2e
def test_perspective_enters_empty_state_immediately_after_last_selection_is_cleared(
    page: Page,
    tmp_path: Path,
):
    _route_perspective_contract_runtime(page)
    report_path = tmp_path / "perspective-empty-selection.html"
    with _running_server(MINIMAL) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        perspective = frame.locator('[data-view-id="sales-perspective"]')
        detail = frame.locator('[data-view-id="sales-detail"]')
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)

        page.locator("#dashboard-controls-control > summary").click()
        options = page.locator(
            '#dashboard-control-form [data-control-component="checkbox-group"] .dv-checkbox-option'
        )
        expect(options).to_have_count(3)
        options.nth(0).click()
        options.nth(1).click()
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=5_000)

        started = time.monotonic()
        options.nth(2).click()
        expect(detail).to_contain_text("No rows match the current selections.", timeout=2_000)
        expect(perspective).to_have_attribute("data-view-status", "empty", timeout=2_000)
        expect(perspective).to_contain_text("No rows match the current selections.", timeout=2_000)
        assert time.monotonic() - started < 2

        # Returning from Empty creates one fresh Perspective instance; stale
        # cleanup from the old instance must not overwrite the restored View.
        options.nth(0).click()
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
        expect(perspective.locator("perspective-viewer")).to_have_count(1)

        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

    # Portable reports use the same View Package lifecycle. Clearing the last
    # selected value must therefore publish Empty immediately without waiting
    # for Perspective's internal flush timeout.
    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        perspective = page.locator('[data-view-id="sales-perspective"]')
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
        selection = page.locator(
            '[data-control-key="dashboard:sales-overview/region"] select[data-control-input]'
        )
        expect(selection).to_have_count(1)

        started = time.monotonic()
        selection.evaluate(
            """input => {
              window.datavizComponents.controls.clearOptions(input);
              window.datavizComponents.controls.markSelectionIntent(input, 'explicit');
              window.datavizComponents.controls.emitChange(input);
            }"""
        )
        expect(perspective).to_have_attribute("data-view-status", "empty", timeout=2_000)
        expect(perspective).to_contain_text("No rows match the current selections.", timeout=2_000)
        assert time.monotonic() - started < 2

        selection.evaluate(
            """input => {
              input.options[0].selected = true;
              window.datavizComponents.controls.markSelectionIntent(input, 'explicit');
              window.datavizComponents.controls.emitChange(input);
            }"""
        )
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
        expect(perspective.locator("perspective-viewer")).to_have_count(1)


@pytest.mark.e2e
def test_cross_browser_perspective_repeated_dispose_and_restore(page: Page, tmp_path: Path):
    _route_perspective_contract_runtime(page)
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
            scroll_state = viewer.evaluate(
                """viewer => {
                  window.scrollTo(0, 0);
                  const before = window.parent.scrollY + window.scrollY;
                  viewer.dispatchEvent(new WheelEvent('wheel', {
                    deltaY:500, bubbles:true, cancelable:true, composed:true,
                  }));
                  return {before, after:window.parent.scrollY + window.scrollY};
                }"""
            )
            assert scroll_state["after"] > scroll_state["before"]
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
            page.locator("#dashboard-reload").evaluate("button => button.click()")
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
            "type": "single_select",
            "value_type": "text",
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
    transform["control_inputs"] = {
        "focus_name": {
            "mode": "filter",
            "control": "view:scaled-table/focus_name",
            "field": "name",
            "inputs": ["rows"],
            "empty": "match_none",
        },
    }
    transform_path.write_text(
        yaml.safe_dump(transform, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    console_errors: list[str] = []
    report_responses: list[tuple[int, str]] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text) if message.type == "error" else None,
    )
    page.on(
        "response",
        lambda response: (
            report_responses.append((response.status, response.url))
            if "/report" in response.url
            else None
        ),
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
            '[data-control-key="view:scaled-table/focus_name"] select[data-control-input]'
        )
        expect(selector.locator("option")).to_have_count(2)
        expect(selector.locator('option[data-empty-option="true"]')).to_have_count(0)
        assert selector.input_value() == "alpha"
        view_signal = table.locator('[data-view-pipeline-node="interactive:scaled"]')
        expect(view_signal).to_have_attribute("data-status", "ready", timeout=10_000)
        expect(view_signal).to_be_hidden()
        assert not [message for message in console_errors if "[dataviz:init]" in message]

        # The removed full-state Shell message is inert; export still reads the
        # canonical Canvas evidence snapshot atomically.
        frame.locator("body").evaluate(
            """() => window.parent.postMessage({
              type:'dataviz:controls-changed',
              dashboard_id:window.dataviz.dashboard_id,
              run_id:window.dataviz.run_id,
              frame_id:window.dataviz.frame_id,
              control_state:{},
            }, window.location.origin)"""
        )

        try:
            with page.expect_download(timeout=30_000) as download_info:
                _export_html(page)
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
def test_date_default_editor_uses_one_mode_and_one_value_per_endpoint(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "date-editor")
    dashboard_path = workspace / "dashboards" / "功能示例##date-parameter-lab" / "dashboard.yaml"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "date-parameter-lab")
        query_geometry = page.locator("#parameter-form").evaluate(
            """form => ({
              formWidth:form.getBoundingClientRect().width,
              fieldWidths:[...form.children].map(item => item.getBoundingClientRect().width),
              usedWidth:Math.max(...[...form.children].map(
                item => item.getBoundingClientRect().right
              )) - form.getBoundingClientRect().left,
            })"""
        )
        assert query_geometry["fieldWidths"]
        assert max(query_geometry["fieldWidths"]) <= 282, query_geometry
        assert query_geometry["usedWidth"] < query_geometry["formWidth"] * 0.72, query_geometry

        page.locator("#run-button").click(button="right")
        dialog = page.locator("#parameter-editor-dialog")
        expect(dialog).to_be_visible()

        single = dialog.locator('[data-editor-item="analysis_date"]')
        single.locator("[data-editor-disclosure]").click()
        expect(single.locator("[data-editor-date-atom]")).to_have_count(1)
        expect(single.locator("[data-editor-date-mode]")).to_have_count(1)
        expect(single.locator("[data-editor-date-value]")).to_have_count(1)
        expect(single.locator("[data-editor-date-value]")).to_have_attribute("type", "number")

        date_range = dialog.locator('[data-editor-item="report_range"]')
        date_range.locator("[data-editor-disclosure]").click()
        expect(date_range.locator("[data-editor-date-atom]")).to_have_count(2)
        expect(date_range.locator("[data-editor-date-mode]")).to_have_count(2)
        expect(date_range.locator("[data-editor-date-value]")).to_have_count(2)

        start = date_range.locator('[data-editor-date-atom="start"]')
        end = date_range.locator('[data-editor-date-atom="end"]')
        start.locator("[data-editor-date-mode]").select_option("fixed")
        expect(start.locator("[data-editor-date-value]")).to_have_attribute("type", "text")
        start.locator("[data-editor-date-value]").fill("20260801")
        expect(start.locator("[data-editor-date-value]")).to_have_value("2026-08-01")
        start.locator("[data-control-trigger]").click()
        expect(start.locator("[data-control-panel]")).to_be_visible()
        expect(start.locator(".dv-date-range__month")).to_have_count(1)
        expect(start.locator(".dv-date-range__year-select")).to_have_count(1)
        expect(start.locator(".dv-date-range__month-select")).to_have_count(1)
        start.locator("[data-control-panel]").press("Escape")
        expect(end.locator("[data-editor-date-value]")).to_have_attribute("type", "number")
        end.locator("[data-editor-date-value]").fill("-1")

        save = dialog.locator('button[type="submit"]')
        expect(save).to_be_enabled()
        save.click()
        expect(dialog).not_to_be_visible(timeout=10_000)

    saved = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    report_range = next(item for item in saved["query_parameters"] if item["id"] == "report_range")
    assert report_range["default"] == [
        "2026-08-01",
        {"mode": "relative", "anchor": "today", "offset": "-1d"},
    ]


@pytest.mark.e2e
def test_browser_query_inputs_project_date_range_parts(page: Page, tmp_path: Path):
    workspace = _copy_workspace(WORKER, tmp_path / "query-input-parts")
    dashboard_path = workspace / "dashboards" / "worker-runtime" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["query_parameters"] = [
        {
            "id": "job_date_range",
            "type": "range_input",
            "value_type": "date",
            "label": "Job date range",
            "required": True,
            "default": [
                {"mode": "relative", "anchor": "today", "offset": "-3d"},
                {"mode": "relative", "anchor": "today", "offset": "-1d"},
            ],
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
              const key = Object.keys(sessionStorage).find(value => value.startsWith('dataviz.tab-ui.v4.'));
              return JSON.parse(sessionStorage.getItem(key)).dashboards['worker-runtime'].queryParameterState;
            }"""
        )
        assert tuple(stored["job_date_range"]["value"]) in expected_ranges
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
def test_share_link_keeps_browser_interactions_and_uses_workspace_cache(page: Page, tmp_path: Path):
    workspace = _copy_workspace(WORKER, tmp_path / "shared-browser-runtime")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "worker-runtime")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        table = frame.locator('[data-view-id="scaled-table"]')
        expect(table).to_have_attribute("data-view-status", "ready", timeout=15_000)

        page.locator("#share-button").click()
        expect(page.locator("#copy-share-link")).to_be_visible()
        with page.expect_response(
            lambda response: response.url.endswith("/api/dashboards/worker-runtime/share"),
            timeout=30_000,
        ) as share_response:
            page.locator("#copy-share-link").click()
        response = share_response.value
        assert response.status == 200
        shared = response.json()
        cache = workspace / shared["path"]
        assert cache.parent == workspace / "shared_caches"
        assert (cache / "manifest.json").is_file()
        assert (cache / "query-result.json").is_file()
        expect(page.locator("#shortcut-toast")).to_have_text("分享链接已复制", timeout=10_000)

        page.goto(f"{base_url}{shared['url']}", wait_until="domcontentloaded")
        shared_table = page.locator('[data-view-id="scaled-table"]')
        expect(shared_table).to_have_attribute("data-view-status", "ready", timeout=15_000)
        completed = page.locator("body").evaluate(
            "() => window.datavizRuntime.metrics.interactiveTransforms.completed"
        )
        page.locator('details[data-control-origin="dashboard"] > summary').click()
        delay = page.locator(
            '[data-control-key="dashboard:worker-runtime/delay_ms"] input[data-control-input]'
        )
        delay.evaluate(
            "input => { input.value = '6'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_function(
            "before => window.datavizRuntime.metrics.interactiveTransforms.completed > before",
            arg=completed,
            timeout=10_000,
        )
        expect(shared_table).to_have_attribute("data-view-status", "ready")


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
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow.dataviz
              .control.value('dashboard:worker-runtime/delay_ms') === 1""",
            timeout=10_000,
        )
        expect(table).to_have_attribute("data-view-status", "ready")
        applied_before_timeout = frame.locator("body").evaluate(
            """() => window.dataviz.stateSnapshot().consumer_revisions
              .transforms.scaled"""
        )
        applied_entry = applied_before_timeout["applied_control_state"][
            "dashboard:worker-runtime/delay_ms"
        ]
        assert applied_before_timeout["stale"] is False
        assert applied_entry["value"] == 1
        assert (
            applied_entry["revision"]
            == applied_before_timeout["controls"]["dashboard:worker-runtime/delay_ms"][
                "applied_revision"
            ]
        )

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
        failed_evidence = frame.locator("body").evaluate(
            """() => window.dataviz.stateSnapshot().consumer_revisions
              .transforms.scaled"""
        )
        assert failed_evidence["stale"] is True
        assert (
            failed_evidence["applied_control_state"]["dashboard:worker-runtime/delay_ms"]
            == applied_entry
        )
        assert (
            failed_evidence["controls"]["dashboard:worker-runtime/delay_ms"]["effective_revision"]
            > applied_entry["revision"]
        )


@pytest.mark.e2e
def test_server_python_and_browser_js_share_output_contract_and_block_html_export(
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
        progressive_frame_id = page.locator("#canvas-frame").get_attribute("data-frame-id")
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
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready", timeout=30_000)
        assert page.locator("#canvas-frame").get_attribute("data-frame-id") == progressive_frame_id
        original_run = page.locator("#canvas-frame").get_attribute("data-run-id")

        completed_before_selection = frame.locator("body").evaluate(
            "() => window.datavizRuntime.metrics.interactiveTransforms.completed"
        )
        frame.locator("body").evaluate(
            """async () => {
              window.dataviz.control.set(
                'dashboard:runtime-matrix/name', ['alpha'], {intent:'explicit'},
              );
              await window.dataviz.applyControls();
            }"""
        )
        expect(server_table).to_contain_text("alpha")
        expect(server_table).not_to_contain_text("beta")
        assert (
            frame.locator("body").evaluate(
                "() => window.datavizRuntime.metrics.interactiveTransforms.completed"
            )
            == completed_before_selection
        )

        page.locator("#dashboard-controls-control summary").click()
        factor = page.locator(
            '#dashboard-control-form input[name="dashboard:runtime-matrix/factor"]'
        )
        factor.fill("3")
        factor.dispatch_event("change")
        expect(server_table).to_contain_text("103", timeout=20_000)
        expect(browser_table).to_contain_text("3", timeout=20_000)
        assert page.locator("#canvas-frame").get_attribute("data-run-id") == original_run
        runtime_state = frame.locator("body").evaluate(
            """() => ({
              committed:window.dataviz.control.value('dashboard:runtime-matrix/factor'),
              browserWorkers:window.datavizRuntime.metrics.interactiveTransforms.completed,
              active:window.datavizRuntime.activeTransforms.size,
            })"""
        )
        assert runtime_state == {"committed": 3, "browserWorkers": 2, "active": 0}

        export = page.locator("#download-button")
        expect(export).to_be_disabled()
        expect(export).to_have_attribute("title", re.compile("Server Python"))

        page.locator("#share-button").click()
        with page.expect_response(
            lambda response: response.url.endswith("/api/dashboards/runtime-matrix/share"),
            timeout=30_000,
        ) as share_response:
            page.locator("#copy-share-link").click()
        shared = share_response.value.json()
        page.goto(f"{base_url}{shared['url']}", wait_until="domcontentloaded")
        shared_server = page.locator('[data-view-id="server-table"]')
        shared_browser = page.locator('[data-view-id="browser-table"]')
        expect(shared_server).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(shared_browser).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(shared_server).to_contain_text("103")
        expect(shared_browser).to_contain_text("3")


@pytest.mark.e2e
def test_selection_gallery_canonical_empty_all_and_clear(page: Page):
    with _running_server(REPEAT) as base_url:
        _open_dashboard(page, base_url, "store-performance")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        host = frame.locator('[data-repeat-section="selected-stores"]')
        summary = frame.locator(
            '[data-control-key="section:selected-stores/stores"] [data-control-summary]'
        )

        expect(host).to_have_attribute("data-repeat-count", "0")
        expect(host).to_contain_text("Nothing selected")
        empty_state = frame.locator("body").evaluate(
            """() => window.dataviz.control.state(
              'section:selected-stores/stores'
            )"""
        )
        assert empty_state["intent"] == "explicit"
        assert empty_state["value"] == []

        store_select = frame.locator(
            '[data-control-key="section:selected-stores/stores"] select[data-control-input]'
        )
        expect(store_select.locator("option")).to_have_count(100, timeout=20_000)
        store_select.evaluate(
            """input => {
              Array.from(input.options).forEach(option => { option.selected = true; });
              window.datavizComponents.controls.markSelectionIntent(input, 'all_available');
              window.datavizComponents.controls.emitChange(input);
            }"""
        )
        expect(host).to_have_attribute("data-repeat-count", "100", timeout=20_000)
        expect(summary).to_have_text("全选")
        assert (
            frame.locator("body").evaluate(
                """() => window.dataviz.control.state(
              'section:selected-stores/stores'
            ).intent"""
            )
            == "all_available"
        )

        frame.locator(
            '[data-control-key="section:selected-stores/stores"] select[data-control-input]'
        ).evaluate(
            """input => {
              window.datavizComponents.controls.clearOptions(input);
              window.datavizComponents.controls.markSelectionIntent(input, 'explicit');
              window.datavizComponents.controls.emitChange(input);
            }"""
        )
        expect(host).to_have_attribute("data-repeat-count", "0")
        expect(host).to_contain_text("Nothing selected")
        cleared_state = frame.locator("body").evaluate(
            """() => window.dataviz.control.state(
              'section:selected-stores/stores'
            )"""
        )
        assert cleared_state["intent"] == "explicit"
        assert cleared_state["value"] == []


@pytest.mark.e2e
def test_plotly_control_binding_commits_once_and_keeps_bound_candidates(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "bound-view")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    bound_view = next(item for item in definition["views"] if item["id"] == "region-comparison")
    bound_view["control_binding"] = "dashboard.region"
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    report_path = tmp_path / "bound-view-report.html"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        bound = frame.locator('[data-view-id="region-comparison"]')
        consumer = frame.locator('[data-view-id="sales-detail"]')
        expect(bound).to_have_attribute("data-view-status", "ready", timeout=20_000)
        chart = bound.locator(".dv-plotly")
        expect(chart).to_be_visible()
        assert chart.evaluate("node => node.data[0].x.length") == 3

        selected_values = chart.evaluate(
            """node => {
              const values = node.data[0].customdata.slice(0, 2);
              node.emit('plotly_selected', {
                points:values.map(customdata => ({customdata})),
              });
              return values;
            }"""
        )
        expect(consumer.locator("tbody tr")).to_have_count(8)
        assert (
            frame.locator("body").evaluate(
                "() => window.dataviz.control.state('dashboard:sales-overview/region').value"
            )
            == selected_values
        )

        # Plotly's double-click gesture belongs to chart navigation.  It must
        # never be overloaded as a Control reset because two rapid point
        # selections can also be classified as a double click.
        chart.evaluate("node => node.emit('plotly_doubleclick')")
        page.wait_for_timeout(50)
        assert frame.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:sales-overview/region').value"
        ) == selected_values

        chart.locator('.modebar-btn[data-title="Restore default selection"]').click()
        expect(consumer.locator("tbody tr")).to_have_count(12)
        assert frame.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:sales-overview/region').value"
        ) == ["华东", "华南", "华北"]

        chart.evaluate(
            """node => {
              node.emit('plotly_click', {
                points:[{customdata:node.data[0].customdata[0]}],
              });
              node.emit('plotly_selected', {points:[]});
            }"""
        )
        expect(consumer.locator("tbody tr")).to_have_count(4)
        assert chart.evaluate("node => node.data[0].x.length") == 3
        state = frame.locator("body").evaluate(
            """() => ({
              selection:window.dataviz.control.state('dashboard:sales-overview/region'),
              revision:window.dataviz.controlActions.revision,
            })"""
        )
        assert state["selection"]["intent"] == "explicit"
        assert state["selection"]["value"] == ["华东"]
        assert state["revision"] == 3

        no_op = chart.evaluate(
            """node => window.dataviz.controlActions.dispatch({
              action_id:'region-noop',
              source_view:'region-comparison',
              control:'dashboard:sales-overview/region',
              generation:document.querySelector('[data-view-id="region-comparison"]')
                ._datavizRenderGeneration,
              action:'select',
              data:{__datavizControlValue:'华东'},
            })"""
        )
        assert no_op == {
            "status": "noop",
            "revision": 3,
            "action_id": "region-noop",
            "source_view": "region-comparison",
        }
        assert frame.locator("body").evaluate("() => window.dataviz.controlActions.revision") == 3

        stale = frame.locator("body").evaluate(
            """() => window.dataviz.controlActions.dispatch({
              action_id:'region-stale',
              source_view:'region-comparison',
              control:'dashboard:sales-overview/region',
              generation:0,
              action:'select',
              data:{__datavizControlValue:'华南'},
            })"""
        )
        assert stale == {
            "status": "rejected",
            "code": "stale_view_generation",
            "action_id": "region-stale",
            "source_view": "region-comparison",
        }
        assert frame.locator("body").evaluate("() => window.dataviz.controlActions.revision") == 3

        frame.locator("body").evaluate(
            """() => window.dataviz.controlActions.dispatch({
              action_id:'region-clear',
              source_view:'region-comparison',
              control:'dashboard:sales-overview/region',
              generation:document.querySelector('[data-view-id="region-comparison"]')
                ._datavizRenderGeneration,
              action:'clear',
            })"""
        )
        expect(consumer).to_have_attribute("data-view-status", "empty")
        expect(consumer).to_contain_text("No rows match the current selections.")
        assert chart.evaluate("node => node.data[0].x.length") == 3

        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

    # The portable report uses the same View Adapter and canonical commit path;
    # it does not carry a server-only callback implementation.
    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        bound = page.locator('[data-view-id="region-comparison"]')
        consumer = page.locator('[data-view-id="sales-detail"]')
        expect(bound).to_have_attribute("data-view-status", "ready", timeout=20_000)
        chart = bound.locator(".dv-plotly")
        assert chart.evaluate("node => node.data[0].x.length") == 3
        chart.evaluate(
            """node => node.emit('plotly_click', {
              points:[{customdata:node.data[0].customdata[0]}],
            })"""
        )
        expect(consumer.locator("tbody tr")).to_have_count(4)


@pytest.mark.e2e
def test_queued_plotly_writer_actions_survive_source_view_rerender(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "rapid-view-writers")

    def emit_plotly_click(chart, value) -> None:
        chart.evaluate(
            """(node, customdata) => node.emit('plotly_click', {
              points:[{customdata}],
            })""",
            value,
        )

    def arm_gate(frame) -> None:
        frame.evaluate(
            """() => {
              window.__writerActionTrace = [];
              window.__armWriterActionGate();
            }"""
        )

    def release_and_read(frame, expected_count: int) -> list[dict]:
        frame.evaluate("() => window.__releaseWriterActionGate()")
        frame.wait_for_function(
            "count => window.__writerActionTrace.length === count "
            "&& window.__writerActionTrace.every(item => item.result)",
            arg=expected_count,
            timeout=20_000,
        )
        return frame.evaluate("() => window.__writerActionTrace")

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame(name="canvas-frame")
        assert frame is not None
        for view_id in ("ranking", "scatter", "records"):
            expect(frame.locator(f'[data-view-id="{view_id}"]')).to_have_attribute(
                "data-view-status", "ready", timeout=20_000
            )

        frame.evaluate(
            """() => {
              const actions = window.dataviz.controlActions;
              const originalDispatch = actions.dispatch.bind(actions);
              const originalApply = window.dataviz.applyControls.bind(window.dataviz);
              window.__writerActionTrace = [];
              window.__writerActionGate = null;
              window.__armWriterActionGate = () => {
                let release;
                const promise = new Promise(resolve => { release = resolve; });
                window.__writerActionGate = {promise, release, entered:false};
                document.body.dataset.writerActionGate = 'armed';
              };
              window.__releaseWriterActionGate = () => {
                window.__writerActionGate?.release();
                document.body.dataset.writerActionGate = 'released';
              };
              actions.dispatch = event => {
                const record = {
                  action:event.action,
                  value:event.data?.__datavizControlValue,
                  generation:event.generation,
                };
                window.__writerActionTrace.push(record);
                return Promise.resolve(originalDispatch(event)).then(result => {
                  record.result = result;
                  return result;
                });
              };
              window.dataviz.applyControls = async options => {
                const gate = window.__writerActionGate;
                if (gate && !gate.entered) {
                  gate.entered = true;
                  document.body.dataset.writerActionGate = 'entered';
                  await gate.promise;
                }
                return originalApply(options);
              };
            }"""
        )

        ranking = frame.locator('[data-view-id="ranking"] .dv-plotly')
        ranking_points = ranking.locator(".bars .point")
        expect(ranking).to_be_visible()
        assert ranking_points.count() == 4
        ranking_values = ranking.evaluate("node => node.data[0].customdata.slice(0, 3)")

        arm_gate(frame)
        emit_plotly_click(ranking, ranking_values[0])
        expect(frame.locator("body")).to_have_attribute("data-writer-action-gate", "entered")
        emit_plotly_click(ranking, ranking_values[1])
        emit_plotly_click(ranking, ranking_values[2])
        ranking_trace = release_and_read(frame, 3)

        assert [item["value"] for item in ranking_trace] == ranking_values
        assert [item["result"]["status"] for item in ranking_trace] == [
            "committed",
            "committed",
            "committed",
        ]
        assert [item["result"]["revision"] for item in ranking_trace] == [1, 2, 3]

        scatter = frame.locator('[data-view-id="scatter"] .dv-plotly')
        expect(frame.locator('[data-view-id="scatter"]')).to_have_attribute(
            "data-view-status", "ready", timeout=20_000
        )
        scatter_traces = scatter.locator(".scatterlayer .trace")
        assert scatter_traces.count() >= 3
        scatter_values = scatter.evaluate(
            "node => node.data.slice(0, 3).map(trace => trace.customdata[0])"
        )

        arm_gate(frame)
        emit_plotly_click(scatter, scatter_values[0])
        expect(frame.locator("body")).to_have_attribute("data-writer-action-gate", "entered")
        emit_plotly_click(scatter, scatter_values[1])
        emit_plotly_click(scatter, scatter_values[2])
        scatter_trace = release_and_read(frame, 3)

        assert [item["value"] for item in scatter_trace] == scatter_values
        assert [item["result"]["status"] for item in scatter_trace] == [
            "committed",
            "committed",
            "committed",
        ]
        assert [item["result"]["revision"] for item in scatter_trace] == [4, 5, 6]
        assert frame.evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province').value"
        ) == [scatter_values[-1]]

        search = frame.locator('[data-view-id="records"] input.dv-table-search')
        expect(search).to_have_attribute("id", re.compile(r"^dataviz-view-records-search-\d+$"))


def _plotly_writer_targets(chart, point_kind: str) -> tuple[list, list[dict]]:
    """Freeze semantic values and physical hit boxes before an interaction burst."""

    chart.scroll_into_view_if_needed()
    if point_kind == "bar":
        points = chart.locator(".bars .point")
        values = chart.evaluate("node => node.data[0].customdata.slice(0, 4)")
        locators = [points.nth(index) for index in range(4)]
    else:
        traces = chart.locator(".scatterlayer .trace")
        assert traces.count() >= 4
        values = chart.evaluate("node => node.data.slice(0, 4).map(t => t.customdata[0])")
        locators = [traces.nth(index).locator(".point").first for index in range(4)]
    boxes = [locator.bounding_box() for locator in locators]
    assert len(values) == len(boxes) == 4
    assert all(box is not None for box in boxes)
    return values, boxes


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("view_id", "point_kind"),
    [
        pytest.param("ranking", "bar", id="bar"),
        pytest.param("scatter", "scatter", id="scatter"),
    ],
)
def test_plotly_writer_real_mouse_gestures_commit_at_human_cadence(
    page: Page,
    tmp_path: Path,
    view_id: str,
    point_kind: str,
):
    """One physical gesture must become one correct action across real timing windows."""

    workspace = _copy_workspace(SHOWCASE, tmp_path / f"natural-{point_kind}-writer")
    control_key = "dashboard:chart-gallery/province"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame(name="canvas-frame")
        assert frame is not None
        view = frame.locator(f'[data-view-id="{view_id}"]')
        chart = view.locator(".dv-plotly")
        expect(view).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(chart).to_be_visible()
        values, target_boxes = _plotly_writer_targets(chart, point_kind)
        baseline_revision = frame.evaluate("() => window.dataviz.controlActions.revision")

        # This observer is intentionally passive: wrapping Plotly.react/restyle
        # changes the microtask timing this regression is supposed to exercise.
        frame.evaluate(
            """viewId => {
              const trace = window.__plotlyNaturalMouseRegression = {
                pointers:[], raw:[], actions:[], afterplots:[],
              };
              const pointerTarget = target => ({
                tag:target?.tagName || null,
                class_name:typeof target?.className === 'object'
                  ? target.className.baseVal
                  : target?.className || null,
                view:target?.closest?.('[data-view-id]')?.dataset.viewId || null,
              });
              let pointerStartedInView = false;
              document.addEventListener('pointerdown', event => {
                if (!event.target?.closest?.(`[data-view-id="${CSS.escape(viewId)}"]`)) return;
                pointerStartedInView = true;
                trace.pointers.push({
                  at:performance.now(), type:'pointerdown',
                  x:event.clientX, y:event.clientY,
                  ...pointerTarget(event.target),
                });
              }, true);
              document.addEventListener('pointerup', event => {
                if (!pointerStartedInView) return;
                pointerStartedInView = false;
                trace.pointers.push({
                  at:performance.now(), type:'pointerup',
                  x:event.clientX, y:event.clientY,
                  ...pointerTarget(event.target),
                });
              }, true);
              const actions = window.dataviz.controlActions;
              const originalDispatch = actions.dispatch.bind(actions);
              actions.dispatch = event => {
                const record = {
                  at:performance.now(), action_id:event.action_id,
                  source_view:event.source_view, action:event.action,
                  value:event.data?.__datavizControlValue,
                };
                trace.actions.push(record);
                const outcome = originalDispatch(event);
                Promise.resolve(outcome).then(
                  result => { record.result = result; },
                  error => { record.error = String(error); },
                );
                return outcome;
              };
              const node = document.querySelector(
                `[data-view-id="${CSS.escape(viewId)}"] .dv-plotly`
              );
              node.on('plotly_click', event => trace.raw.push({
                at:performance.now(),
                values:(event?.points || []).map(point => point.customdata),
              }));
              node.on('plotly_afterplot', () => {
                trace.afterplots.push({at:performance.now()});
              });
            }""",
            view_id,
        )

        order = (0, 1, 2, 3, 2, 1, 0, 3, 1, 2, 0, 3, 2, 1, 3, 0, 1, 2)
        cadences_ms = (
            80,
            170,
            260,
            360,
            180,
            440,
            650,
            80,
            260,
            170,
            360,
            440,
            180,
            80,
            260,
            650,
            170,
            360,
        )
        travels = ((0, 0), (2, 1), (4, 3)) * 6
        for gesture_index, point_index in enumerate(order):
            target_box = target_boxes[point_index]
            assert target_box is not None
            x = target_box["x"] + target_box["width"] / 2
            y_fraction = (0.28, 0.5, 0.72)[gesture_index % 3] if point_kind == "bar" else 0.5
            y = target_box["y"] + target_box["height"] * y_fraction
            dx, dy = travels[gesture_index]
            page.mouse.move(x, y, steps=4)
            page.mouse.down()
            if dx or dy:
                page.mouse.move(x + dx, y + dy)
            page.mouse.up()
            page.wait_for_timeout(cadences_ms[gesture_index])

        try:
            frame.wait_for_function(
                """expected => {
                  const actions = window.__plotlyNaturalMouseRegression.actions;
                  return actions.length === expected
                    && actions.every(item => Boolean(item.result || item.error));
                }""",
                arg=len(order),
                timeout=10_000,
            )
        except PlaywrightTimeoutError:
            diagnostics = frame.evaluate("() => window.__plotlyNaturalMouseRegression")
            pytest.fail(f"{point_kind} natural gestures were lost or duplicated: {diagnostics}")

        diagnostics = frame.evaluate("() => window.__plotlyNaturalMouseRegression")
        expected_values = [values[index] for index in order]
        assert [item["type"] for item in diagnostics["pointers"]] == [
            event_type for _ in order for event_type in ("pointerdown", "pointerup")
        ]
        pointer_pairs = list(
            zip(diagnostics["pointers"][::2], diagnostics["pointers"][1::2], strict=True)
        )
        for (pointer_down, pointer_up), (expected_dx, expected_dy) in zip(
            pointer_pairs, travels, strict=True
        ):
            assert pointer_down["view"] == view_id
            assert pointer_up["x"] - pointer_down["x"] == pytest.approx(expected_dx, abs=0.5)
            assert pointer_up["y"] - pointer_down["y"] == pytest.approx(expected_dy, abs=0.5)

        pointer_downs = [pair[0]["at"] for pair in pointer_pairs]
        pointer_intervals = [
            current - previous
            for previous, current in zip(pointer_downs[:-1], pointer_downs[1:], strict=True)
        ]
        assert sum(interval < 220 for interval in pointer_intervals) >= 3, pointer_intervals
        assert sum(220 <= interval < 350 for interval in pointer_intervals) >= 6, pointer_intervals
        assert sum(350 <= interval < 600 for interval in pointer_intervals) >= 4, pointer_intervals
        assert sum(interval >= 600 for interval in pointer_intervals) >= 2, pointer_intervals

        actions = diagnostics["actions"]
        assert len({item["action_id"] for item in actions}) == len(order)
        assert [item["source_view"] for item in actions] == [view_id] * len(order)
        assert [item["action"] for item in actions] == ["select"] * len(order)
        assert [item["value"] for item in actions] == expected_values
        assert [item.get("error") for item in actions] == [None] * len(order)
        assert [item["result"]["status"] for item in actions] == ["committed"] * len(order)
        assert [item["result"]["revision"] for item in actions] == list(
            range(baseline_revision + 1, baseline_revision + len(order) + 1)
        )

        final_value = expected_values[-1]
        frame.wait_for_function(
            """settings => {
              const state = window.dataviz.control.state(settings.controlKey);
              const cells = [...document.querySelectorAll(
                '[data-view-id="records"] tbody tr td:first-child'
              )].map(cell => cell.textContent.trim());
              return state.value.length === 1 && state.value[0] === settings.value
                && cells.length > 0 && cells.every(value => value === settings.value);
            }""",
            arg={"controlKey": control_key, "value": final_value},
            timeout=10_000,
        )
        expect(page.locator(f'select[name="{control_key}"]')).to_have_values(
            [final_value], timeout=5_000
        )
        visual = chart.evaluate(
            """(node, settings) => {
              if (settings.kind === 'bar') {
                const points = [...node.querySelectorAll('.barlayer .point')];
                return points.map((point, index) => ({
                  value:node.data[0].customdata[index],
                  opacities:[Number(getComputedStyle(point.querySelector('path')).opacity)],
                }));
              }
              const traces = [...node.querySelectorAll('.scatterlayer .trace')];
              return traces.map((traceNode, index) => ({
                value:node.data[index].customdata[0],
                opacities:[...traceNode.querySelectorAll('.point')]
                  .map(point => Number(getComputedStyle(point).opacity)),
              }));
            }""",
            {"kind": point_kind},
        )
        selected_opacities = [
            opacity
            for item in visual
            if item["value"] == final_value
            for opacity in item["opacities"]
        ]
        unselected_opacities = [
            opacity
            for item in visual
            if item["value"] != final_value
            for opacity in item["opacities"]
        ]
        assert selected_opacities and unselected_opacities, visual
        assert min(selected_opacities) > max(unselected_opacities), visual


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("view_id", "point_kind"),
    [
        pytest.param("ranking", "bar", id="bar"),
        pytest.param("scatter", "scatter", id="scatter"),
    ],
)
def test_plotly_writer_recovers_wrong_or_missing_raw_click(
    page: Page,
    tmp_path: Path,
    view_id: str,
    point_kind: str,
):
    """Removing the Dataviz point candidate/fallback must make this test fail."""

    workspace = _copy_workspace(SHOWCASE, tmp_path / f"fault-{point_kind}-writer")
    control_key = "dashboard:chart-gallery/province"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame(name="canvas-frame")
        assert frame is not None
        view = frame.locator(f'[data-view-id="{view_id}"]')
        chart = view.locator(".dv-plotly")
        expect(view).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(chart).to_be_visible()
        values, target_boxes = _plotly_writer_targets(chart, point_kind)
        intended_indices = (1, 2)
        expected_values = [values[index] for index in intended_indices]

        frame.evaluate(
            """viewId => {
              const trace = window.__plotlyFaultRegression = {
                raw:[], actions:[], dropped_raw_clicks:0,
              };
              const actions = window.dataviz.controlActions;
              const originalDispatch = actions.dispatch.bind(actions);
              actions.dispatch = event => {
                const record = {
                  action_id:event.action_id, source_view:event.source_view,
                  action:event.action, value:event.data?.__datavizControlValue,
                };
                trace.actions.push(record);
                const outcome = originalDispatch(event);
                Promise.resolve(outcome).then(
                  result => { record.result = result; },
                  error => { record.error = String(error); },
                );
                return outcome;
              };
              const node = document.querySelector(
                `[data-view-id="${CSS.escape(viewId)}"] .dv-plotly`
              );
              node.on('plotly_click', event => trace.raw.push(
                (event?.points || []).map(point => point.customdata)
              ));
            }""",
            view_id,
        )

        def wait_for_action(action_count: int, value) -> None:
            frame.wait_for_function(
                """settings => {
                  const trace = window.__plotlyFaultRegression;
                  const state = window.dataviz.control.state(settings.controlKey);
                  return trace.actions.length === settings.actionCount
                    && Boolean(trace.actions.at(-1)?.result)
                    && state.value.length === 1
                    && state.value[0] === settings.value;
                }""",
                arg={
                    "actionCount": action_count,
                    "controlKey": control_key,
                    "value": value,
                },
                timeout=10_000,
            )

        # Reproduce Plotly 4.0.0's stale-hover path without changing its event
        # emitter: move to the intended point, then establish a different
        # Plotly hover immediately before the physical click. Fx.click can read
        # the throttled old _hoverdata, while Dataviz must use the down target.
        first_box = target_boxes[intended_indices[0]]
        assert first_box is not None
        first_x = first_box["x"] + first_box["width"] / 2
        first_y = first_box["y"] + first_box["height"] / 2
        page.mouse.move(first_x, first_y, steps=4)
        stale_hover = chart.evaluate(
            """(node, intendedValue) => {
              const candidates = (node.data || []).flatMap((trace, curveNumber) => (
                (trace.customdata || []).map((_value, pointNumber) => ({
                  curveNumber, pointNumber,
                }))
              ));
              for (const candidate of candidates) {
                window.Plotly.Fx.unhover(node);
                window.Plotly.Fx.hover(node, [candidate]);
                const values = (node._hoverdata || []).map(item => item.customdata);
                if (values.length && values[0] !== intendedValue) {
                  return {candidate, values};
                }
              }
              return null;
            }""",
            expected_values[0],
        )
        assert stale_hover is not None
        wrong_value = stale_hover["values"][0]
        assert wrong_value != expected_values[0]
        page.mouse.down()
        page.mouse.up()
        wait_for_action(1, expected_values[0])
        page.wait_for_timeout(400)

        # A missing raw event is a separate failure mode. Drop exactly the next
        # Plotly click at its emitter, then use another physical micro-jitter
        # gesture. Without the Dataviz fallback this produces no action.
        frame.evaluate(
            """viewId => {
              const trace = window.__plotlyFaultRegression;
              const node = document.querySelector(
                `[data-view-id="${CSS.escape(viewId)}"] .dv-plotly`
              );
              const originalEmit = node.emit.bind(node);
              let pendingDrop = true;
              node.emit = (name, ...args) => {
                if (name === 'plotly_click' && pendingDrop) {
                  pendingDrop = false;
                  trace.dropped_raw_clicks += 1;
                  return node;
                }
                return originalEmit(name, ...args);
              };
            }""",
            view_id,
        )
        second_box = target_boxes[intended_indices[1]]
        assert second_box is not None
        second_x = second_box["x"] + second_box["width"] / 2
        second_y = second_box["y"] + second_box["height"] / 2
        page.mouse.move(second_x, second_y, steps=4)
        page.mouse.down()
        page.mouse.move(second_x + 4, second_y + 3)
        page.mouse.up()
        wait_for_action(2, expected_values[1])
        page.wait_for_timeout(400)

        diagnostics = frame.evaluate("() => window.__plotlyFaultRegression")
        assert diagnostics["dropped_raw_clicks"] == 1
        assert diagnostics["raw"] == [[wrong_value]]
        actions = diagnostics["actions"]
        assert len(actions) == len(expected_values)
        assert len({item["action_id"] for item in actions}) == len(expected_values)
        assert [item["source_view"] for item in actions] == [view_id] * len(expected_values)
        assert [item["action"] for item in actions] == ["select"] * len(expected_values)
        assert [item["value"] for item in actions] == expected_values
        assert [item.get("error") for item in actions] == [None] * len(expected_values)
        assert [item["result"]["status"] for item in actions] == [
            "committed"
        ] * len(expected_values)
        assert frame.evaluate(
            "key => window.dataviz.control.state(key).value", control_key
        ) == [expected_values[-1]]


@pytest.mark.e2e
def test_plotly_native_double_click_restores_zoom_without_resetting_control(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "plotly-native-double-click")
    control_key = "dashboard:chart-gallery/province"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame(name="canvas-frame")
        assert frame is not None
        scatter = frame.locator('[data-view-id="scatter"] .dv-plotly')
        expect(scatter).to_be_visible()
        scatter.scroll_into_view_if_needed()

        selected_value = scatter.evaluate("node => node.data[0].customdata[0]")
        scatter.evaluate(
            """(node, customdata) => node.emit('plotly_click', {
              points:[{customdata}],
            })""",
            selected_value,
        )
        frame.wait_for_function(
            """expected => {
              const state = window.dataviz.control.state(
                'dashboard:chart-gallery/province'
              );
              return state.value.length === 1 && state.value[0] === expected;
            }""",
            arg=selected_value,
            timeout=5_000,
        )
        before = frame.evaluate(
            """key => ({
              control:window.dataviz.control.state(key),
              revision:window.dataviz.controlActions.revision,
              provenance:structuredClone(window.dataviz.control_writer_provenance),
            })""",
            control_key,
        )
        zoomed_range = scatter.evaluate(
            """async node => {
              const values = node.data.flatMap(trace => trace.x).map(Number);
              const minimum = Math.min(...values);
              const maximum = Math.max(...values);
              const range = [minimum, minimum + (maximum - minimum) / 3];
              window.__plotlyDoubleClicks = 0;
              node.on('plotly_doubleclick', () => { window.__plotlyDoubleClicks += 1; });
              await window.Plotly.relayout(node, {
                'xaxis.autorange':false,
                'xaxis.range':range,
              });
              return range;
            }"""
        )
        assert scatter.evaluate("node => node._fullLayout.xaxis.autorange") is False

        drag_surface = scatter.locator(".nsewdrag")
        expect(drag_surface).to_be_visible()
        drag_box = drag_surface.bounding_box()
        assert drag_box is not None
        occluders = scatter.locator(".scatterlayer .point, .legend, .modebar")
        occluder_boxes = [
            box
            for index in range(occluders.count())
            if (box := occluders.nth(index).bounding_box()) is not None
        ]
        candidates = [
            (
                drag_box["x"] + drag_box["width"] * x_fraction,
                drag_box["y"] + drag_box["height"] * y_fraction,
            )
            for y_fraction in (0.18, 0.38, 0.62, 0.82)
            for x_fraction in (0.12, 0.32, 0.52, 0.72, 0.88)
        ]
        background = next(
            (x, y)
            for x, y in candidates
            if not any(
                box["x"] - 6 <= x <= box["x"] + box["width"] + 6
                and box["y"] - 6 <= y <= box["y"] + box["height"] + 6
                for box in occluder_boxes
            )
        )
        # Locator.dblclick() performs an actionability check against Plotly's
        # intentional SVG overlays; a real mouse gesture should target a
        # verified empty coordinate in the rendered plotting rectangle.
        page.mouse.dblclick(
            *background,
            delay=80,
        )
        frame.wait_for_function(
            """() => {
              const node = document.querySelector('[data-view-id="scatter"] .dv-plotly');
              return window.__plotlyDoubleClicks === 1
                && node._fullLayout.xaxis.autorange === true;
            }""",
            timeout=5_000,
        )
        assert scatter.evaluate("node => node._fullLayout.xaxis.range") != zoomed_range
        after = frame.evaluate(
            """key => ({
              control:window.dataviz.control.state(key),
              revision:window.dataviz.controlActions.revision,
              provenance:structuredClone(window.dataviz.control_writer_provenance),
            })""",
            control_key,
        )
        assert after == before


@pytest.mark.e2e
def test_multi_view_linked_brushing_preserves_writer_provenance_across_runtime(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "multi-view-writers")
    report_path = tmp_path / "multi-view-writers.html"
    scenario = json.loads(
        (ROOT / "tests" / "fixtures" / "p1d-linked-brushing.json").read_text(encoding="utf-8")
    )
    control_key = scenario["use_case"]["control"]

    def dispatch(frame, action):
        return frame.locator("body").evaluate(
            """async (_body, item) => {
              const root = document.querySelector(
                `.dv-view[data-view-id="${CSS.escape(item.source_view)}"]`
              );
              const data = item.action === 'select_many'
                ? item.payload.map(value => ({__datavizControlValue:value}))
                : item.action === 'select'
                  ? {__datavizControlValue:item.payload}
                  : null;
              return window.dataviz.controlActions.dispatch({
                action_id:item.action_id,
                source_view:item.source_view,
                control:item.control,
                generation:root._datavizRenderGeneration,
                action:item.action,
                data,
              });
            }""",
            {**action, "control": control_key},
        )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        for view_id in ("ranking", "scatter", "trend", "records"):
            expect(frame.locator(f'[data-view-id="{view_id}"]')).to_have_attribute(
                "data-view-status", "ready", timeout=20_000
            )

        for item in scenario["actions"]:
            response = dispatch(frame, item)
            expected = item["expected"]
            assert response == {
                "status": "committed",
                "revision": expected["revision"],
                "action_revision": expected["revision"],
                "action_id": item["action_id"],
                "source_view": item["source_view"],
            }
            observed = frame.locator("body").evaluate(
                """(_body, key) => ({
                  state:window.dataviz.control.state(key),
                  provenance:window.dataviz.control_writer_provenance[key],
                })""",
                control_key,
            )
            assert observed["state"] == {
                "value": expected["value"],
                "intent": expected["intent"],
                "revision": expected["revision"],
            }
            assert observed["provenance"] == {
                "revision": expected["revision"],
                "action_id": item["action_id"],
                "source_view": expected["last_source_view"],
                "action": item["action"],
            }

        stale = frame.locator("body").evaluate(
            """(_body, key) => window.dataviz.controlActions.dispatch({
              action_id:'ranking-stale-generation',
              source_view:'ranking',
              control:key,
              generation:0,
              action:'select',
              data:{__datavizControlValue:'广东'},
            })""",
            control_key,
        )
        assert stale == {
            "status": "rejected",
            "code": "stale_view_generation",
            "action_id": "ranking-stale-generation",
            "source_view": "ranking",
        }
        forged = frame.locator("body").evaluate(
            """(_body, key) => window.dataviz.controlActions.dispatch({
              action_id:'trend-forged-writer',
              source_view:'trend',
              control:key,
              generation:document.querySelector('[data-view-id="trend"]')
                ._datavizRenderGeneration,
              action:'select',
              data:{__datavizControlValue:'广东'},
            })""",
            control_key,
        )
        assert forged == {
            "status": "rejected",
            "code": "control_action_binding_invalid",
            "action_id": "trend-forged-writer",
            "source_view": "trend",
        }

        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

        page.locator("#share-button").click()
        expect(page.locator("#copy-share-link")).to_be_visible()
        with page.expect_response(
            lambda response: response.url.endswith("/api/dashboards/chart-gallery/share"),
            timeout=30_000,
        ) as share_response:
            page.locator("#copy-share-link").click()
        shared = share_response.value.json()
        manifest = json.loads(
            (workspace / ".dataviz" / "results" / shared["result_id"] / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        result = manifest["result"]
        assert result["schema"] == "dataviz/analysis-result/v4"
        records_evidence = result["consumer_revisions"]["views"]["records"]
        assert records_evidence["applied_writer_provenance"][control_key] == {
            "revision": 4,
            "action_id": "scatter-reset",
            "source_view": "scatter",
            "action": "reset",
        }

    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        expect(page.locator('[data-view-id="ranking"]')).to_have_attribute(
            "data-view-status", "ready", timeout=20_000
        )
        response = dispatch(
            page,
            {
                "action_id": "ranking-portable-select",
                "source_view": "ranking",
                "action": "select",
                "payload": "广东",
            },
        )
        assert response["status"] == "committed"
        assert response["revision"] == 5
        snapshot = page.locator("body").evaluate(
            """(_body, key) => ({
              schema:window.dataviz.stateSnapshot().schema,
              state:window.dataviz.control.state(key),
              provenance:window.dataviz.control_writer_provenance[key],
              records:window.dataviz.stateSnapshot()
                .consumer_revisions.views.records.applied_writer_provenance[key],
            })""",
            control_key,
        )
        assert snapshot["schema"] == "dataviz/state-snapshot/v5"
        assert snapshot["state"]["value"] == ["广东"]
        assert (
            snapshot["provenance"]
            == snapshot["records"]
            == {
                "revision": 5,
                "action_id": "ranking-portable-select",
                "source_view": "ranking",
                "action": "select",
            }
        )


@pytest.mark.e2e
@pytest.mark.parametrize("dragmode", ["select", "lasso"])
def test_plotly_area_selection_gesture_commits_the_bound_control(
    page: Page, tmp_path: Path, dragmode: str
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / f"plotly-{dragmode}")
    report_path = tmp_path / f"plotly-{dragmode}-toggle.html"
    dashboard_path = workspace / "dashboards" / "功能示例##chart-gallery" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"][0]["initial"] = {"mode": "empty"}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        view = frame.locator('[data-view-id="scatter"]')
        chart = view.locator(".dv-plotly")
        expect(view).to_have_attribute("data-view-status", "ready", timeout=20_000)
        chart.scroll_into_view_if_needed()
        modebar_titles = chart.locator(".modebar-btn").evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('data-title'))"
        )
        assert set(modebar_titles) == {
            "Box Select",
            "Lasso Select",
            "Restore default selection",
        }
        expect(chart.locator(".modebar-group")).to_have_count(1)
        chart.evaluate(
            "(node, mode) => window.Plotly.relayout(node, {dragmode:mode})",
            dragmode,
        )
        drag_layer = chart.locator(".nsewdrag")
        box = drag_layer.bounding_box()
        assert box is not None

        points = [
            (box["x"] + box["width"] * 0.05, box["y"] + box["height"] * 0.45),
            (box["x"] + box["width"] * 0.58, box["y"] + box["height"] * 0.45),
            (box["x"] + box["width"] * 0.58, box["y"] + box["height"] * 0.95),
            (box["x"] + box["width"] * 0.05, box["y"] + box["height"] * 0.95),
        ]
        page.mouse.move(*points[0])
        page.mouse.down()
        if dragmode == "select":
            page.mouse.move(*points[2], steps=20)
        else:
            for point in [*points[1:], points[0]]:
                page.mouse.move(*point, steps=8)
        page.mouse.up()

        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .dataviz.control.state('dashboard:chart-gallery/province')
              .value.length > 0""",
            timeout=10_000,
        )
        selection = frame.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        )
        assert selection["intent"] == "explicit"
        assert 0 < len(selection["value"]) < 4

        page.wait_for_function(
            """() => {
              const node = document.querySelector('#canvas-frame').contentWindow
                .document.querySelector('[data-view-id="scatter"] .dv-plotly');
              return (node.layout?.selections || []).length === 0
                && !node.querySelector('.select-outline');
            }""",
            timeout=10_000,
        )

        mode_title = "Box Select" if dragmode == "select" else "Lasso Select"
        active_tool = chart.locator(f'.modebar-btn[data-title="{mode_title}"]')
        expect(active_tool).to_have_class(re.compile(r"\bactive\b"))
        active_tool.click()
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .document.querySelector('[data-view-id="scatter"] .dv-plotly')
              ._fullLayout.dragmode === 'zoom'""",
            timeout=10_000,
        )
        expect(active_tool).not_to_have_class(re.compile(r"\bactive\b"))
        assert frame.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        ) == selection

        # Seal the selected state before Reset so portable HTML proves the same
        # click-active-tool-again behavior with no Server callback.
        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

        chart.locator('.modebar-btn[data-title="Restore default selection"]').click()
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .dataviz.control.state('dashboard:chart-gallery/province')
              .value.length === 0""",
            timeout=10_000,
        )

    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        view = page.locator('[data-view-id="scatter"]')
        expect(view).to_have_attribute("data-view-status", "ready", timeout=20_000)
        chart = view.locator(".dv-plotly")
        active_tool = chart.locator(
            f'.modebar-btn[data-title="{"Box Select" if dragmode == "select" else "Lasso Select"}"]'
        )
        portable_selection = page.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        )
        assert portable_selection == selection
        active_tool.click()
        expect(active_tool).to_have_class(re.compile(r"\bactive\b"))
        chart.scroll_into_view_if_needed()
        drag_layer = chart.locator(".nsewdrag")
        box = drag_layer.bounding_box()
        assert box is not None
        points = [
            (box["x"] + box["width"] * 0.05, box["y"] + box["height"] * 0.45),
            (box["x"] + box["width"] * 0.95, box["y"] + box["height"] * 0.45),
            (box["x"] + box["width"] * 0.95, box["y"] + box["height"] * 0.95),
            (box["x"] + box["width"] * 0.05, box["y"] + box["height"] * 0.95),
        ]
        page.mouse.move(*points[0])
        page.mouse.down()
        if dragmode == "select":
            page.mouse.move(*points[2], steps=20)
        else:
            for point in [*points[1:], points[0]]:
                page.mouse.move(*point, steps=8)
        page.mouse.up()
        page.wait_for_function(
            """() => {
              const node = document.querySelector('[data-view-id="scatter"] .dv-plotly');
              return (node.layout?.selections || []).length === 0
                && !node.querySelector('.select-outline');
            }""",
            timeout=10_000,
        )
        expect(active_tool).to_have_class(re.compile(r"\bactive\b"))
        portable_selection_after_gesture = page.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        )
        assert portable_selection_after_gesture["value"]
        active_tool.click()
        page.wait_for_function(
            """() => document.querySelector('[data-view-id="scatter"] .dv-plotly')
              ._fullLayout.dragmode === 'zoom'""",
            timeout=10_000,
        )
        expect(active_tool).not_to_have_class(re.compile(r"\bactive\b"))
        assert page.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        ) == portable_selection_after_gesture


@pytest.mark.e2e
def test_table_row_count_is_opt_in_instead_of_a_default_metadata_row(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "table-count-visibility")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    detail = next(item for item in definition["views"] if item["id"] == "sales-detail")
    counted = dict(detail)
    counted["id"] = "sales-detail-counted"
    counted["title"] = "Sales detail with count"
    counted["options"] = {
        **counted.get("options", {}),
        "show_count": True,
        "searchable": True,
        "page_size": 4,
    }
    definition["views"].append(counted)
    definition["sections"].append(
        {
            "id": "counted-detail",
            "title": "Explicit row count",
            "template": "single",
            "views": ["sales-detail-counted"],
        }
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        default_table = frame.locator('[data-view-id="sales-detail"]')
        counted_table = frame.locator('[data-view-id="sales-detail-counted"]')
        expect(default_table).to_have_attribute("data-view-status", "ready")
        expect(counted_table).to_have_attribute("data-view-status", "ready")
        expect(default_table.locator(".dv-table-meta")).to_have_count(0)
        expect(counted_table.locator(".dv-table-meta strong")).to_have_text("12")
        expect(counted_table.locator(".dv-table-wrap")).to_have_attribute(
            "data-tanstack-table-version", "9.2.4"
        )
        assert frame.locator("body").evaluate(
            """() => ({
              version: window.dataviz.tables.tanstack.version,
              constructTable: typeof window.dataviz.tables.tanstack.core.constructTable,
              tableFeatures: typeof window.dataviz.tables.tanstack.core.tableFeatures,
              managedMount: typeof window.dataviz.tables.tanstack.mount,
            })"""
        ) == {
            "version": "9.2.4",
            "constructTable": "function",
            "tableFeatures": "function",
            "managedMount": "function",
        }
        expect(counted_table.locator("tbody tr")).to_have_count(4)
        expect(counted_table.locator(".dv-table-page-status")).to_have_text("1 / 3")

        search = counted_table.locator(".dv-table-search")
        composition_probe = search.evaluate(
            """node => {
              node.dispatchEvent(new CompositionEvent('compositionstart', {
                bubbles:true,
                data:'shenzhen',
              }));
              node.value = 'shenzhen';
              node.dispatchEvent(new InputEvent('input', {
                bubbles:true,
                data:'shenzhen',
                inputType:'insertCompositionText',
                isComposing:true,
              }));
              return {
                connected:node.isConnected,
                sameNode:document.querySelector('.dv-table-search') === node,
                value:node.value,
              };
            }"""
        )
        assert composition_probe == {
            "connected": True,
            "sameNode": True,
            "value": "shenzhen",
        }
        expect(counted_table.locator(".dv-table-meta strong")).to_have_text("12")
        search.evaluate(
            """node => {
              node.value = '华东';
              node.dispatchEvent(new CompositionEvent('compositionend', {
                bubbles:true,
                data:'华东',
              }));
            }"""
        )
        expect(counted_table.locator(".dv-table-meta strong")).to_have_text("4")
        search = counted_table.locator(".dv-table-search")
        search.fill("")

        revenue_header = counted_table.locator('th[data-column="revenue"]')
        revenue_header.locator("button").click()
        expect(revenue_header).to_have_attribute("aria-sort", "ascending")
        revenue_values = counted_table.locator(
            'tbody td[data-column="revenue"]'
        ).all_text_contents()
        numeric_values = [
            float(
                "".join(character for character in value if character.isdigit() or character == ".")
            )
            for value in revenue_values
        ]
        assert numeric_values == sorted(numeric_values)

        counted_table.locator(".dv-table-search").fill("华东")
        expect(counted_table.locator("tbody tr")).to_have_count(4)
        expect(counted_table.locator(".dv-table-meta strong")).to_have_text("4")
        assert all(
            "华东" in value for value in counted_table.locator("tbody tr").all_text_contents()
        )

        counted_table.locator(".dv-table-search").fill("")
        counted_table.locator('.dv-table-page-button[aria-label="Next page"]').click()
        expect(counted_table.locator(".dv-table-page-status")).to_have_text("2 / 3")


@pytest.mark.e2e
def test_table_control_binding_writes_the_shared_selection(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "table-bound-view")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    bound_view = next(item for item in definition["views"] if item["id"] == "sales-detail")
    bound_view["control_binding"] = {
        "control": "dashboard.region",
        "field": "region",
    }
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        table = frame.locator('[data-view-id="sales-detail"]')
        chart = frame.locator('[data-view-id="region-comparison"] .dv-plotly')
        expect(table).to_have_attribute("data-view-status", "ready", timeout=20_000)
        assert table.locator("tbody tr").count() == 12

        east_row = table.locator("tbody tr").filter(has_text="华东").first
        east_row.click()

        expect(east_row).to_have_attribute("aria-selected", "true")
        assert table.locator("tbody tr").count() == 12
        expect(chart).to_be_visible(timeout=20_000)
        assert chart.evaluate("node => node.data[0].x") == ["华东"]
        assert frame.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:sales-overview/region').value"
        ) == ["华东"]


@pytest.mark.e2e
def test_arrow_transport_and_repeat_thousand_group_search_lazy_budget(page: Page, tmp_path: Path):
    workspace = _copy_workspace(REPEAT, tmp_path / "repeat")
    sql = workspace / "dashboards" / "store-performance" / "sources" / "store-sales.sql"
    sql.write_text(
        sql.read_text(encoding="utf-8").replace("range(1, 101)", "range(1, 1001)"), encoding="utf-8"
    )
    dashboard = workspace / "dashboards" / "store-performance" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard.read_text(encoding="utf-8"))
    definition["sections"][1]["repeat"]["limit"] = 1000
    all_store_view = next(item for item in definition["views"] if item["id"] == "all-store-trend")
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
        expect(
            host.locator(":scope > .dv-repeat-card").first.locator(".dv-view-description")
        ).to_have_text("每家门店共享同一份 Dataset。")
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
def test_progressive_failure_and_consecutive_run_are_isolated(page: Page, tmp_path: Path):
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
def test_large_aggregations_do_not_cross_the_javascript_argument_limit(page: Page, tmp_path: Path):
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
def test_cancelled_query_branch_reaches_a_terminal_view_state(page: Page, tmp_path: Path):
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
        session_id = page.evaluate("() => sessionStorage.getItem('dataviz.tab-session.v2')")
        assert cancelled_run_id and session_id
        expect(page.locator("#run-button")).to_contain_text("取消")
        page.locator("#run-button").click()
        expect(page.locator("#run-message")).to_contain_text("Query cancelled", timeout=20_000)
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
        expect(cancelled_slow).to_have_attribute("data-view-status", "cancelled", timeout=20_000)
        expect(cancelled_slow).to_contain_text("Computation cancelled")
        expect(cancelled_fast).to_have_attribute("data-view-status", "ready")
