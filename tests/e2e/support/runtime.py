from __future__ import annotations


import re

import shutil

import socket


import threading

import time

from contextlib import contextmanager


from functools import partial

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path


import uvicorn


from playwright.sync_api import (
    Page,
    expect,
)

from dataviz.server import create_app


from dataviz.workspace import load_workspace


ROOT = Path(__file__).resolve().parents[3]

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
def _running_server(workspace: Path, *, watch: bool = True, standalone_input=None, execution=None, refresh_interval=None):
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(workspace, watch=watch, standalone_input=standalone_input, execution=execution, refresh_interval=refresh_interval),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="on",
            # Test assertions have finished when this host is shut down. Open
            # browser EventSources must not keep each test waiting ten seconds
            # or leave daemon servers behind. Production settings are unchanged.
            timeout_graceful_shutdown=0.2,
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
        if thread.is_alive():
            raise RuntimeError("E2E server leaked beyond teardown")


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


def _copy_workspace(source: Path, destination: Path, *, dashboards: tuple[str, ...] | None = None) -> Path:
    if dashboards is not None:
        if not dashboards or any(Path(name).name != name or not (source / 'dashboards' / name).is_dir()
                                 for name in dashboards):
            raise ValueError('Requested test dashboard directory does not exist')
    ignored_files = shutil.ignore_patterns('.dataviz', 'dist', '__pycache__', '*.pyc')

    def ignore(directory, names):
        ignored = set(ignored_files(directory, names))
        if dashboards is not None and Path(directory) == source / 'dashboards':
            ignored.update(name for name in names if name not in dashboards)
        return ignored

    shutil.copytree(
        source,
        destination,
        ignore=ignore,
    )
    return destination


def _build_same_view_dependency_workspace(root: Path) -> Path:
    dashboard = root / "dashboards" / "same-view-controls"
    sources = dashboard / "sources"
    auth = root / "auth"
    sources.mkdir(parents=True)
    auth.mkdir()
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v2
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
        """schema: dataviz/dashboard/v20
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
        """schema: dataviz/source/v6
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
        """schema: dataviz/workspace/v2
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
        """schema: dataviz/dashboard/v20
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
        """schema: dataviz/workspace/v2
kind: workspace
id: interactive-runtime-e2e
title: Interactive Runtime E2E
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v20
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


def _open_single_fixture_dashboard(page: Page, base_url: str, root: Path) -> None:
    # Root intentionally stays empty without tab history. These tests target a
    # specific single-Dashboard fixture, including standalone inputs with no nav.
    dashboards = load_workspace(root).dashboards
    assert len(dashboards) == 1, "Fixture must identify its Dashboard explicitly"
    page.goto(f"{base_url}/dashboards/{next(iter(dashboards))}")


def _open_dashboard(page: Page, base_url: str, dashboard_id: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")
    dashboard = page.locator(f'[data-nav-type="dashboard"][data-id="{dashboard_id}"]')
    expect(dashboard).to_be_attached(timeout=10_000)
    switched = "active" not in (dashboard.get_attribute("class") or "").split()
    if switched:
        if page.locator('#operation-panel[aria-modal="true"]').is_visible():
            page.locator('#operation-panel-close').click()
        # A translated-offscreen mobile navigation tree is still CSS-visible.
        # Open it through its real button rather than attempting an offscreen click.
        if page.locator('#sidebar-toggle').get_attribute('aria-expanded') == 'false' or not dashboard.is_visible():
            page.locator('#sidebar-toggle').click()
        dashboard.click()
        expect(dashboard).to_have_class(re.compile(r"\bactive\b"), timeout=10_000)
        expect(page.locator("#canvas-frame")).to_have_attribute(
            "data-dashboard-id", dashboard_id, timeout=10_000
        )
        page.wait_for_url(re.compile(rf"/dashboards/{re.escape(dashboard_id)}(?:[?]|$)"))
    expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)


def _run_and_wait(page: Page, expected: str = "Ready") -> None:
    if page.locator('#operation-panel[aria-modal="true"]').is_visible():
        page.locator('#operation-panel-close').click()
    page.locator('#run-button').click()
    expect(page.locator("#query-diagnostics-label")).to_have_text(
        expected,
        timeout=30_000,
    )


def _export_html(page: Page) -> None:
    share = page.locator("#share-control")
    if share.get_attribute("open") is None:
        page.locator("#share-button").click()
    page.locator("#download-button").click()


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
