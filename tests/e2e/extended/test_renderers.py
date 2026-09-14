from __future__ import annotations

import json


import re


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


from dataviz.execution import Executor


from dataviz.protocols import DASHBOARD_SCHEMA, WORKSPACE_SCHEMA

from dataviz.rendering import CanvasRenderer

from dataviz.workspace import load_workspace

from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _running_static_server,
    _open_dashboard,
    _run_and_wait,
    _export_html,
    SHOWCASE,
    MINIMAL,
)

@pytest.mark.e2e
def test_managed_renderer_lifecycle_matrix_in_server_and_export(page: Page, tmp_path: Path):
    """One behavioral contract guards every imperative managed Renderer.

    Renderer implementations keep the small validate/mount/update/dispose hook
    API. The platform owns the wider behavioral matrix exercised here:
    mount -> update -> empty -> restore -> interaction -> resize -> dispose -> export.
    """
    page.add_init_script('''(() => {
      const resources = window.__lifecycleResources = {workers:0, observers:0, gestureListeners:0};
      const tracked = [];
      const nativeAdd = EventTarget.prototype.addEventListener;
      const nativeRemove = EventTarget.prototype.removeEventListener;
      const capture = options => typeof options === 'boolean' ? options : Boolean(options?.capture);
      EventTarget.prototype.addEventListener = function(type, callback, options) {
        if ((this === window || this === document) && ['pointerup','pointercancel','blur'].includes(type)
            && callback && !options?.once && !tracked.some(entry => entry.target === this
              && entry.type === type && entry.callback === callback && entry.capture === capture(options))) {
          tracked.push({target:this, type, callback, capture:capture(options)});
          resources.gestureListeners++;
        }
        return nativeAdd.call(this, type, callback, options);
      };
      EventTarget.prototype.removeEventListener = function(type, callback, options) {
        const index = tracked.findIndex(entry => entry.target === this && entry.type === type
          && entry.callback === callback && entry.capture === capture(options));
        if (index >= 0) { tracked.splice(index, 1); resources.gestureListeners--; }
        return nativeRemove.call(this, type, callback, options);
      };
      const NativeWorker = window.Worker, NativeObserver = window.ResizeObserver;
      window.Worker = class extends NativeWorker {
        constructor(...args) { super(...args); this._counted = true; resources.workers++; }
        terminate() {
          if (this._counted) { this._counted = false; resources.workers--; }
          return super.terminate();
        }
      };
      window.ResizeObserver = class extends NativeObserver {
        constructor(...args) { super(...args); this._targets = new Set(); }
        observe(...args) {
          const result = super.observe(...args);
          this._targets.add(args[0]);
          if (!this._counted) { this._counted = true; resources.observers++; }
          return result;
        }
        unobserve(target) {
          super.unobserve(target);
          this._targets.delete(target);
          if (!this._targets.size && this._counted) { this._counted = false; resources.observers--; }
        }
        disconnect() {
          this._targets.clear();
          if (this._counted) { this._counted = false; resources.observers--; }
          return super.disconnect();
        }
      };
    })();''')
    # Resource ownership requires the pinned real Perspective runtime, not the
    # lightweight contract double (whose terminate intentionally does nothing).
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
              let perspectiveConfig = await perspective.viewer.save();
              // One operation must work. Retrying restore until the timeout
              // could hide a dropped update in the lifecycle under test.
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
                workers:window.__lifecycleResources.workers,
                workerUrls:runtime.workerUrls.size,
                transports:runtime.transportPromises.size,
              };
            }""",
            view_ids,
        )
        assert evidence["states"] == 0
        assert evidence["rendererMetrics"]["disposes"] >= 3
        assert evidence["perspectiveMetrics"]["disposed"] >= 1
        assert evidence["rendererMetrics"]["failed"] == 0
        assert evidence['workers'] == evidence['workerUrls'] == evidence['transports'] == 0

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
        page.locator("#dashboard-controls-toggle").click()
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

        # Repeated resource churn, not merely a single successful teardown.
        # Real Plotly and Perspective workers remain in use; the wrappers only
        # count native construction/termination and observer disconnection.
        def resource_snapshot():
            return frame.locator('body').evaluate('''() => ({
              ...window.__lifecycleResources,
              states:window.datavizRuntime.viewAdapter.states.size,
              perspective:window.datavizRuntime.metrics.perspective.created
                - window.datavizRuntime.metrics.perspective.disposed,
              transports:window.datavizRuntime.transportPromises.size,
            })''')

        baseline = resource_snapshot()
        for cycle in range(20):
            options.nth(0).click()
            for view_id in view_ids:
                expect(frame.locator(f'[data-view-id="{view_id}"]')).to_have_attribute('data-view-status', 'empty')
            # Wait for the documented asynchronous Perspective cleanup, rather
            # than adding a fixed pause that hides slow/missing disposal.
            canvas = next(item for item in page.frames if '/canvas?' in item.url)
            canvas.wait_for_function('''() => window.datavizRuntime.metrics.perspective.created
              === window.datavizRuntime.metrics.perspective.disposed''', timeout=5_000)
            options.nth(0).click()
            expect_ready(frame)
            assert resource_snapshot() == baseline, f'resource accumulation in cycle {cycle + 1}'

        # export is generated from the same live canonical state before the
        # Server host is explicitly disposed.
        page.locator("#dashboard-controls-toggle").click()
        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

        page.locator('#share-button').click()
        with page.expect_response(lambda response: response.url.endswith('/sales-overview/share')) as response:
            page.locator('#copy-share-link').click()
        share_url = response.value.json()['url']

        # dispose
        assert_dispose(frame)

        # Share and HTML repeat the same lifecycle from the same Result.
        with _running_static_server(report_path.parent) as report_url:
            for target in (base_url + share_url, f"{report_url}/{report_path.name}"):
                page.goto(target, wait_until="domcontentloaded")
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
def test_three_surface_renderer_pending_error_and_recovery(page: Page, tmp_path: Path):
    from dataviz.standalone import prepare_input

    definition = tmp_path / 'view-states.yaml'
    definition.write_text(yaml.safe_dump({
        'schema': DASHBOARD_SCHEMA, 'id': 'view-states',
        'controls': [{'id': 'mode', 'type': 'single_select', 'value_type': 'text',
                      'initial': {'mode': 'value', 'value': 'ready'},
                      'options': {'mode': 'static', 'choices': [{'label': x, 'value': x} for x in ['ready', 'pending', 'error']]}}],
        'sources': [{'id': 'rows', 'type': 'python',
                     'code': {'inline': "def load(context):\n    return [{'value': 7}]\n"},
                     'outputs': {'main': {'kind': 'table'}}}],
        'canvas': {'scripts': [{'inline': """window.datavizRuntime.registerRenderer('audit.states', {
          validate() {
            if (!window.auditInitialValidated) {
              window.auditInitialValidated = true;
              return new Promise(resolve => {
                window.releaseAuditInitial = resolve;
                document.body.dataset.auditInitialPending = 'true';
              });
            }
            const mode = window.dataviz.control.value('dashboard:view-states/mode');
            if (mode === 'pending') return new Promise(resolve => {
              window.releaseAuditRender = resolve;
              document.body.dataset.auditRenderPending = 'true';
            });
            if (mode === 'error') {
              const error = new Error('Controlled renderer failure');
              error.stack = error.message; throw error;
            }
          },
          mount(context) {
            const node = document.createElement('p'); node.textContent = 'Ready value: 7';
            context.body.append(node); return {node};
          },
          update(context, descriptor, state) { return state; },
          dispose(context, state) { state.node.remove(); }
        });"""}]},
        'views': [{'id': 'state', 'title': 'State feedback', 'template': 'custom',
                   'renderer': 'audit.states', 'input': 'source:rows/main',
                   'control_inputs': {'mode': {'mode': 'value', 'control': 'dashboard.mode'}}}],
    }))
    (tmp_path / 'presentation.yaml').write_text(yaml.safe_dump({
        'schema': 'dataviz/presentation/v2', 'kind': 'presentation', 'dashboard': 'view-states',
        'control_components': {'dashboard:view-states/mode': {'component': 'select'}},
    }))
    workspace, _ = prepare_input(definition)
    evidence = {}

    def inspect(surface):
        frame = page.frame_locator('#canvas-frame') if surface == 'server' else page
        view = frame.locator('[data-view-id="state"]')
        # A loading View may still be fetching inputs. Only the renderer's own
        # marker proves its deferred validation (and resolver) exists.
        expect(frame.locator('body')).to_have_attribute('data-audit-initial-pending', 'true', timeout=20_000)
        expect(view).to_have_attribute('data-view-status', 'loading', timeout=20_000)
        expect(view).to_have_attribute('aria-busy', 'true')
        frame.locator('body').evaluate('() => window.releaseAuditInitial()')
        expect(view).to_have_attribute('data-view-status', 'ready', timeout=20_000)
        page.locator('#dashboard-controls-toggle' if surface == 'server'
                     else '.dv-runtime-control[data-control-origin="dashboard"] > summary').click()
        sidebar = page.locator('#operation-panel' if surface == 'server' else '.dv-context-sidebar')
        def change(mode):
            control = sidebar.locator('[data-control-component="select"]')
            control.locator('[data-control-trigger]').click()
            control.locator('.dv-choice-option').filter(has_text=re.compile('^' + mode + '$')).click()
        change('pending')
        expect(frame.locator('body')).to_have_attribute('data-audit-render-pending', 'true')
        expect(view).to_have_attribute('data-view-updating', 'true')
        expect(view).to_have_attribute('aria-busy', 'true')
        expect(view).to_contain_text('Ready value: 7')
        frame.locator('body').evaluate('() => window.releaseAuditRender()')
        expect(view).not_to_have_attribute('data-view-updating', 'true')
        change('error')
        expect(view).to_have_attribute('data-view-status', 'error')
        alert = view.get_by_role('alert')
        expect(alert).to_contain_text('Controlled renderer failure')
        evidence[surface] = alert.evaluate('''node => {
          const s = getComputedStyle(node);
          return {font:s.font, color:s.color, background:s.backgroundColor, padding:s.padding, border:s.border};
        }''')
        change('ready')
        expect(view).to_have_attribute('data-view-status', 'ready')
        expect(view.get_by_role('alert')).to_have_count(0)
        expect(view).to_contain_text('Ready value: 7')
        page.locator('#operation-panel-close' if surface == 'server' else '.dv-context-sidebar > header button').click()

    with _running_server(workspace) as url:
        page.goto(url + '/dashboards/view-states')
        _run_and_wait(page)
        inspect('server')
        report = tmp_path / 'view-states.html'
        with page.expect_download() as download:
            _export_html(page)
        download.value.save_as(report)
        page.locator('#share-button').click()
        with page.expect_response(lambda response: response.url.endswith('/view-states/share')) as response:
            page.locator('#copy-share-link').click()
        page.goto(url + response.value.json()['url'])
        inspect('share')
        with _running_static_server(tmp_path) as static_url:
            page.goto(static_url + '/' + report.name)
            inspect('html')
    assert evidence['server'] == evidence['share'] == evidence['html'], evidence


@pytest.mark.e2e
def test_workspace_asset_service_matches_server_and_portable_html(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "workspace-assets")
    workspace_definition_path = workspace / "workspace.yaml"
    workspace_definition = yaml.safe_load(
        workspace_definition_path.read_text(encoding="utf-8")
    )
    workspace_definition["schema"] = WORKSPACE_SCHEMA
    workspace_definition["assets"] = {
        "china-city": {
            "path": "assets/maps/china-city.geojson",
            "media_type": "application/geo+json",
        }
    }
    workspace_definition_path.write_text(
        yaml.safe_dump(workspace_definition, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    map_path = workspace / "assets" / "maps" / "china-city.geojson"
    map_path.parent.mkdir(parents=True)
    map_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "深圳"},
                        "geometry": {"type": "Point", "coordinates": [114.1, 22.5]},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dashboard_root = workspace / "dashboards" / "sales-overview"
    (dashboard_root / "presentation.yaml").unlink()
    definition_path = dashboard_root / "dashboard.yaml"
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["schema"] = DASHBOARD_SCHEMA
    definition["assets"] = ["china-city"]
    definition.setdefault("canvas", {})["scripts"] = ["assets/map-renderer.js"]
    definition["views"].append(
        {
            "id": "asset-map",
            "title": "Asset Map",
            "template": "custom",
            "renderer": "asset-map",
            "input": "source:sales/main",
        }
    )
    definition["sections"].append(
        {"id": "asset-map-section", "title": "Map", "views": ["asset-map"]}
    )
    definition_path.write_text(
        yaml.safe_dump(definition, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    renderer_path = dashboard_root / "assets" / "map-renderer.js"
    renderer_path.parent.mkdir(parents=True, exist_ok=True)
    renderer_path.write_text(
        """window.datavizRuntime.registerRenderer('asset-map', {
  async mount(context) {
    const geo = await context.assets.json('china-city');
    const bytes = await context.assets.bytes('china-city');
    const assetUrl = await context.assets.url('china-city');
    context.body.dataset.assetFeature = geo.features[0].properties.name;
    context.body.dataset.assetTransport = context.assets.describe('china-city').transport;
    context.body.dataset.assetBytes = String(bytes.byteLength);
    context.body.dataset.assetUrlKind = assetUrl.startsWith('blob:') ? 'blob' : 'server';
    context.body.textContent = `${geo.type}: ${geo.features.length}`;
    return {};
  },
  async update(context) { return this.mount(context); },
  dispose() {},
});
""",
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        identity = page.evaluate(
            """async () => {
              const deadline = Date.now() + 30000;
              while (Date.now() < deadline) {
                const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
                const response = await fetch(`/api/session/runs?session_id=${encodeURIComponent(sessionId)}`);
                const payload = await response.json();
                const run = payload.runs.find(item => item.dashboard_id === 'sales-overview' && item.status === 'ready');
                if (run) return {sessionId, runId:run.run_id};
                await new Promise(resolve => setTimeout(resolve, 50));
              }
              throw new Error('asset Run did not finish');
            }"""
        )
        page.goto(
            f"{base_url}/api/dashboards/sales-overview/canvas"
            f"?session_id={identity['sessionId']}&run_id={identity['runId']}",
            wait_until="domcontentloaded",
        )
        body = page.locator('[data-view-id="asset-map"] .dv-view-body')
        expect(body).to_have_attribute("data-asset-feature", "深圳", timeout=20_000)
        expect(body).to_have_attribute("data-asset-transport", "url")
        expect(body).to_have_attribute("data-asset-url-kind", "server")
        assert int(body.get_attribute("data-asset-bytes") or 0) > 0

    loaded = load_workspace(workspace)
    result = Executor(loaded).run("sales-overview")
    report_path = CanvasRenderer(loaded).write_report(
        loaded.dashboard("sales-overview"),
        result,
        tmp_path / "workspace-asset-report.html",
    )

    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        body = page.locator('[data-view-id="asset-map"] .dv-view-body')
        expect(body).to_have_attribute("data-asset-feature", "深圳", timeout=20_000)
        expect(body).to_have_attribute("data-asset-transport", "text")
        expect(body).to_have_attribute("data-asset-url-kind", "blob")
        assert int(body.get_attribute("data-asset-bytes") or 0) > 0


@pytest.mark.e2e
def test_native_map_point_region_asset_and_selection_match_server_and_portable(
    page: Page,
    tmp_path: Path,
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "native-map")

    def assert_maps_ready(root) -> None:
        point = root.locator('[data-view-id="store-points"]')
        city = root.locator('[data-view-id="city-stores"]')
        region = root.locator('[data-view-id="region-revenue"]')
        expect(point).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(city).to_have_attribute("data-view-status", "ready", timeout=20_000)
        if region.get_attribute("data-view-status") == "error":
            detail = region.locator(".dv-view-error").inner_text()
            raise AssertionError(f"region-revenue renderer failed: {detail}")
        expect(region).to_have_attribute("data-view-status", "ready", timeout=20_000)
        assert point.locator(".dv-plotly").evaluate(
            "node => ({type:node.data[0].type, count:node.data[0].lon.length})"
        ) == {"type": "scattergeo", "count": 8}
        assert city.locator(".dv-plotly").evaluate(
            "node => ({type:node.data[0].type, count:node.data[0].lon.length})"
        ) == {"type": "scattergeo", "count": 2}
        assert region.locator(".dv-plotly").evaluate(
            "node => ({type:node.data[0].type, features:node.data[0].geojson.features.length})"
        ) == {"type": "choropleth", "features": 4}

    city_key = "dashboard:map-lab/city"
    store_key = "dashboard:map-lab/store"

    def select_overview_store(root, *, store: str, city: str) -> None:
        root.locator('[data-view-id="store-points"] .dv-plotly').evaluate(
            """(node, datum) => node.emit('plotly_click', {points:[{customdata:{
              __datavizControlValue:datum.store,
              __datavizControlWrites:{[datum.cityKey]:datum.city},
            }}]})""",
            {"store": store, "city": city, "cityKey": city_key},
        )

    def assert_compound_state(root, *, store: str, city: str) -> dict:
        root.locator("body").evaluate(
            """async (_body, [cityKey, storeKey, city, store]) => {
              const deadline = performance.now() + 10_000;
              while (performance.now() < deadline) {
                if (
                  window.dataviz.control.state(cityKey)?.value === city
                  && window.dataviz.control.state(storeKey)?.value === store
                ) return;
                await new Promise(resolve => setTimeout(resolve, 25));
              }
              throw new Error(`Timed out waiting for ${city} / ${store}`);
            }""",
            [city_key, store_key, city, store],
        )
        return root.locator("body").evaluate(
            """(_body, keys) => ({
              city:window.dataviz.control.state(keys.city),
              store:window.dataviz.control.state(keys.store),
              cityProvenance:window.dataviz.control_writer_provenance[keys.city],
              storeProvenance:window.dataviz.control_writer_provenance[keys.store],
            })""",
            {"city": city_key, "store": store_key},
        )

    def assert_city_map(root, *, city: str, stores: list[str]) -> str:
        return root.locator('[data-view-id="city-stores"] .dv-plotly').evaluate(
            """async (node, expected) => {
              const deadline = performance.now() + 10_000;
              while (performance.now() < deadline) {
                const values = [...(node.data?.[0]?.customdata || [])].sort();
                const rendered = [...node.querySelectorAll('.scatterlayer .point')];
                const bounds = node.getBoundingClientRect();
                const visible = rendered.filter(point => {
                  const box = point.getBoundingClientRect();
                  return box.width > 0 && box.height > 0
                    && box.right >= bounds.left && box.left <= bounds.right
                    && box.bottom >= bounds.top && box.top <= bounds.bottom;
                });
                if (
                  JSON.stringify(values) === JSON.stringify([...expected.stores].sort())
                  && rendered.length === expected.stores.length
                  && visible.length === expected.stores.length
                ) return node.layout.geo.uirevision;
                await new Promise(resolve => setTimeout(resolve, 25));
              }
              throw new Error(`Timed out waiting for ${expected.city} map: ${JSON.stringify({
                data:node.data?.[0]?.customdata,
                rendered:node.querySelectorAll('.scatterlayer .point').length,
              })}`);
            }""",
            {"city": city, "stores": stores},
        )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "map-lab")
        _run_and_wait(page)
        frame = page.frame(name="canvas-frame")
        assert frame is not None
        assert_maps_ready(frame)
        select_overview_store(frame, store="GZ-001", city="广州")
        state = assert_compound_state(frame, store="GZ-001", city="广州")
        assert state["city"]["revision"] == state["store"]["revision"] == 1
        assert state["cityProvenance"]["action_id"] == state["storeProvenance"]["action_id"]
        assert state["cityProvenance"]["source_view"] == "store-points"
        assert state["storeProvenance"]["source_view"] == "store-points"
        expect(frame.locator('[data-view-id="city-stores"]')).to_have_attribute(
            "data-view-status", "ready", timeout=20_000
        )
        assert frame.locator('[data-view-id="city-stores"] .dv-plotly').evaluate(
            "node => node.data[0].lon.length"
        ) == 2
        assert_city_map(frame, city="广州", stores=["GZ-001", "GZ-002"])

        frame.locator('[data-view-id="city-stores"] .dv-plotly').evaluate(
            "node => node.emit('plotly_click', {points:[{customdata:'GZ-002'}]})"
        )
        state = assert_compound_state(frame, store="GZ-002", city="广州")
        assert state["city"]["revision"] == 1
        assert state["store"]["revision"] == 2
        assert state["storeProvenance"]["source_view"] == "city-stores"

        viewport_revisions: dict[str, str] = {}
        for city, store, stores in [
            ("深圳", "SZ-001", ["SZ-001", "SZ-002"]),
            ("厦门", "XM-001", ["XM-001", "XM-002"]),
            ("长沙", "CS-001", ["CS-001", "CS-002"]),
            ("广州", "GZ-001", ["GZ-001", "GZ-002"]),
        ] * 3:
            select_overview_store(frame, store=store, city=city)
            assert_compound_state(frame, store=store, city=city)
            revision = assert_city_map(frame, city=city, stores=stores)
            assert viewport_revisions.setdefault(city, revision) == revision
        assert len(set(viewport_revisions.values())) == 4

        rejected = frame.locator("body").evaluate(
            """async (_body, keys) => {
              const root = document.querySelector('[data-view-id="store-points"]');
              return window.dataviz.controlActions.dispatch({
                action_id:'overview-multiple-cities',
                source_view:'store-points',
                control:keys.store,
                generation:root._datavizRenderGeneration,
                action:'select_many',
                data:[
                  {__datavizControlValue:'SZ-001', __datavizControlWrites:{[keys.city]:'深圳'}},
                  {__datavizControlValue:'XM-001', __datavizControlWrites:{[keys.city]:'厦门'}},
                ],
              });
            }""",
            {"city": city_key, "store": store_key},
        )
        assert rejected["status"] == "rejected"
        assert rejected["code"] == "control_action_projection_cardinality_invalid"
        state = assert_compound_state(frame, store="GZ-001", city="广州")
        assert state["city"]["revision"] >= 1
        assert state["store"]["revision"] >= 2

    loaded = load_workspace(workspace)
    result = Executor(loaded).run("map-lab")
    report_path = CanvasRenderer(loaded).write_report(
        loaded.dashboard("map-lab"),
        result,
        tmp_path / "native-map.html",
    )
    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        assert_maps_ready(page)
        response = page.locator("body").evaluate(
            """async (_body, item) => {
              const root = document.querySelector('[data-view-id="store-points"]');
              return window.dataviz.controlActions.dispatch({
                action_id:'portable-overview-select',
                source_view:'store-points',
                control:item.storeKey,
                generation:root._datavizRenderGeneration,
                action:'select',
                data:{
                  __datavizControlValue:item.store,
                  __datavizControlWrites:{[item.cityKey]:item.city},
                },
              });
            }""",
            {
                "store": "XM-001",
                "city": "厦门",
                "cityKey": city_key,
                "storeKey": store_key,
            },
        )
        assert response["status"] == "committed"
        assert response["control_revisions"][city_key] >= 1
        assert response["control_revisions"][store_key] >= 1
        state = page.locator("body").evaluate(
            """(_body, keys) => ({
              city:window.dataviz.control.state(keys.city),
              store:window.dataviz.control.state(keys.store),
              cityProvenance:window.dataviz.control_writer_provenance[keys.city],
              storeProvenance:window.dataviz.control_writer_provenance[keys.store],
            })""",
            {"city": city_key, "store": store_key},
        )
        assert state["city"]["value"] == "厦门"
        assert state["store"]["value"] == "XM-001"
        assert state["cityProvenance"]["action_id"] == state["storeProvenance"]["action_id"]
