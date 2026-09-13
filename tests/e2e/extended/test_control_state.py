from __future__ import annotations

import json

import os

import re


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
)


from dataviz.cli import _copy_gallery_workspace


from dataviz.protocols import DASHBOARD_SCHEMA


from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _build_same_view_dependency_workspace,
    _running_static_server,
    _open_single_fixture_dashboard,
    _open_dashboard,
    _run_and_wait,
    _export_html,
    ROOT,
    SHOWCASE,
    MINIMAL,
    SALES,
    WORKER,
    REPEAT,
)

@pytest.mark.e2e
@pytest.mark.parametrize('width', [1440, 375])
def test_three_surface_choice_and_date_controls(page: Page, tmp_path: Path, width):
    errors = []
    page.on('pageerror', lambda error: errors.append(error.stack))
    workspace = _copy_workspace(MINIMAL, tmp_path / 'choice-date')
    folder = workspace / 'dashboards/sales-overview'
    path = folder / 'dashboard.yaml'
    dashboard = yaml.safe_load(path.read_text())
    choices = [{'label': name, 'value': name} for name in ['Alpha', 'Beta', 'Gamma']]
    dashboard['controls'] = [
        {'id': 'single', 'type': 'single_select', 'value_type': 'text', 'label': 'Single',
         'initial': {'mode': 'value', 'value': 'Alpha'}, 'options': {'mode': 'static', 'choices': choices}},
        {'id': 'multi', 'type': 'multiple_select', 'value_type': 'text', 'label': 'Multiple',
         'initial': {'mode': 'all'}, 'options': {'mode': 'static', 'choices': choices}},
        {'id': 'date', 'type': 'single_input', 'value_type': 'date', 'label': 'Date', 'default': '2026-03-01'},
        {'id': 'period', 'type': 'range_input', 'value_type': 'date', 'label': 'Period',
         'default': ['2026-03-01', '2026-03-10']},
    ]
    for view in dashboard['views']:
        view['control_inputs'] = {c['id']: {'mode': 'value', 'control': 'dashboard.' + c['id']}
                                  for c in dashboard['controls']}
    path.write_text(yaml.safe_dump(dashboard, allow_unicode=True))
    presentation_path = folder / 'presentation.yaml'
    presentation = yaml.safe_load(presentation_path.read_text())
    presentation['control_components'] = {
        'dashboard:sales-overview/' + key: {'component': component, **options}
        for key, component, options in [('single', 'select', {'search': 'always'}),
                                       ('multi', 'select', {'search': 'always'}),
                                       ('date', 'date-picker', {}), ('period', 'range-picker', {})]
    }
    presentation_path.write_text(yaml.safe_dump(presentation, allow_unicode=True))
    evidence = {}

    def inspect(surface):
        page.set_viewport_size({'width': width, 'height': 900})
        standalone = surface != 'server'
        canvas = page if standalone else page.frame_locator('#canvas-frame')
        expect(canvas.locator('[data-view-id="sales-perspective"]')).to_have_attribute('data-view-status', 'ready', timeout=20_000)
        live_page = page if standalone else next(item for item in page.frames if '/canvas?' in item.url)
        live_page.wait_for_function('''() => {
          const runtime = window.datavizRuntime;
          return runtime?.metrics.perspective.created > 0
            && runtime.viewAdapter.states.get('sales-perspective')?.state?.mode === 'perspective';
        }''', timeout=30_000)
        assert canvas.locator('body').evaluate('''() => ({
          plotly:window.Plotly.version, perspective:window.dataviz.runtime_versions.perspective
        })''') == {'plotly': '4.1.0', 'perspective': '5.4.0'}
        # At mobile width a retained Parameters tray is modal and legitimately
        # covers Header controls. Establish the closed-tray precondition before
        # testing Header activation; Escape after Share is not that guarantee.
        if not standalone and page.locator('#operation-panel').is_visible():
            page.locator('#operation-panel-close').click()
            expect(page.locator('#operation-panel')).to_be_hidden()
        page.locator('.dv-runtime-control[data-control-origin="dashboard"] > summary'
                     if standalone else '#dashboard-controls-toggle').click()
        sidebar = page.locator('.dv-context-sidebar' if standalone else '#operation-panel')
        expect(sidebar).to_be_visible()
        def bounds(panel):
            box = panel.bounding_box()
            assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1, (surface, box)
            assert box['y'] >= 0 and box['y'] + box['height'] <= 901, (surface, box)
        single, multi = [sidebar.locator('[data-control-component="select"]').nth(i) for i in (0, 1)]
        single.locator('[data-control-trigger]').click()
        search = single.locator('.dv-choice-search')
        search.fill('Beta')
        bounds(single.locator('[data-control-panel]'))
        single.locator('.dv-choice-option').click()
        expect(single.locator('select')).to_have_value('Beta')
        expect(single.locator('[data-control-panel]')).to_be_hidden()
        multi.locator('[data-control-trigger]').click()
        panel = multi.locator('[data-control-panel]')
        bounds(panel)
        panel.get_by_role('button', name='Clear', exact=True).click()
        expect(multi.locator('select')).to_have_values([])
        search = multi.locator('.dv-choice-search')
        search.fill('Alpha')
        panel.get_by_role('button', name='Select results', exact=True).click()
        search.fill('Beta')
        panel.get_by_role('button', name='Select results', exact=True).click()
        panel.get_by_role('button', name='Clear results', exact=True).click()
        expect(multi.locator('select')).to_have_values(['Alpha'])
        search.fill('')
        search.press('e')
        expect(search).to_have_value('e')
        expect(sidebar).to_be_visible()
        search.fill('no matching option')
        expect(panel.locator('.dv-choice-empty')).to_be_visible()
        expect(panel.get_by_role('button', name='Select results', exact=True)).to_be_disabled()
        search.press('Escape')
        expect(panel).to_be_hidden()
        expect(sidebar).to_be_visible()
        date = sidebar.locator('[data-control-component="date-picker"]')
        date_input = date.locator('.dv-date-picker__control[type="text"]')
        date_input.fill('2026-02-31')
        expect(date_input).to_have_attribute('aria-invalid', 'true')
        date_input.fill('2026-03-02')
        date_input.press('Enter')
        expect(date_input).to_have_attribute('aria-invalid', 'false')
        date.locator('[data-control-trigger]').click()
        expect(date.locator('[data-control-panel]')).to_be_visible()
        bounds(date.locator('[data-control-panel]'))
        page.keyboard.press('Escape')
        period = sidebar.locator('[data-control-component="range-picker"]')
        endpoints = period.locator('.dv-date-range__endpoint')
        endpoints.nth(0).fill('2026-03-03')
        endpoints.nth(1).fill('2026-03-08')
        endpoints.nth(1).press('Enter')
        expect(period.locator('input[data-control-input], input[data-control-state-input]')).to_have_value('2026-03-03,2026-03-08')
        period.locator('[data-control-trigger]').click()
        bounds(period.locator('[data-control-panel]'))
        page.keyboard.press('Escape')
        # Compare the whole field, not only the enhanced control's outer div.
        # Labels and native trigger borders can inherit different host CSS.
        evidence[surface] = sidebar.locator('[data-control-component]:visible').evaluate_all('''nodes => nodes.map(node => {
          const s = getComputedStyle(node);
          const field = node.closest('.field, .dv-control-field');
          const label = field?.querySelector(':scope > label, :scope > span');
          const ls = getComputedStyle(label);
          const entry = node.querySelector('[data-control-trigger], [data-control-native="visible"]');
          const es = getComputedStyle(entry);
          const rect = field.getBoundingClientRect();
          const parentTop = nodes[0].closest('.field, .dv-control-field').getBoundingClientRect().top;
          return {component:node.dataset.controlComponent, font:s.fontFamily, size:s.fontSize,
            color:s.color, background:s.backgroundColor, width:node.getBoundingClientRect().width,
            label:{font:ls.font,color:ls.color,spacing:ls.letterSpacing,transform:ls.textTransform},
            entry:{border:es.borderColor,background:es.backgroundColor},
            field:{height:rect.height,top:rect.top-parentTop,gap:getComputedStyle(field).gap}};
        })''')
        browser_name = os.environ.get('DATAVIZ_BROWSER', 'chromium')
        page.screenshot(path=f'/tmp/dataviz-choice-date-{browser_name}-{surface}-{width}.png')
        page.keyboard.press('Escape')
        expect(sidebar).to_be_hidden()
        # Unlike the separate adapter-contract matrix, this fixture uses the
        # actual CDN Perspective client/engine and must release its real worker.
        disposal = canvas.locator('body').evaluate('''async () => {
          const runtime = window.datavizRuntime;
          const created = runtime.metrics.perspective.created;
          runtime.dispose();
          const deadline = performance.now() + 5000;
          while (runtime.metrics.perspective.disposed < created && performance.now() < deadline)
            await new Promise(resolve => setTimeout(resolve, 20));
          return {created, disposed:runtime.metrics.perspective.disposed, states:runtime.viewAdapter.states.size};
        }''')
        assert disposal['created'] > 0 and disposal['disposed'] == disposal['created'], disposal
        assert disposal['states'] == 0, disposal

    with _running_server(workspace) as url, _running_static_server(tmp_path) as static_url:
        _open_dashboard(page, url, 'sales-overview')
        _run_and_wait(page)
        with page.expect_download() as download:
            _export_html(page)
        report = tmp_path / 'choice-date.html'
        download.value.save_as(report)
        page.locator('#share-button').click()
        with page.expect_response(lambda response: response.url.endswith('/sales-overview/share')) as response:
            page.locator('#copy-share-link').click()
        share_url = response.value.json()['url']
        page.keyboard.press('Escape')
        inspect('server')
        page.goto(url + share_url)
        inspect('share')
        page.goto(f'{static_url}/{report.name}')
        inspect('html')
    assert evidence['server'] == evidence['share'] == evidence['html'], json.dumps(evidence, ensure_ascii=False)
    assert not errors, errors


@pytest.mark.e2e
def test_custom_selection_feedback_updates_without_data_change(page: Page, tmp_path: Path):
    from dataviz.standalone import prepare_input
    script = """window.datavizRuntime.registerRenderer('selection.example', {
      mount(context, descriptor) {
        const node = document.createElement('div'); context.body.append(node);
        const state = {node, context, updates:0};
        for (const row of descriptor.rows) {
          const button = document.createElement('button'); button.textContent = row.id;
          button.dataset.item = row.id;
          button.onclick = () => state.context.controlBinding?.emit('select', row);
          node.append(button);
        }
        this.update(context, descriptor, state); return state;
      },
      update(context, descriptor, state) {
        state.context = context; state.updates++;
        const selection = context.controlBinding?.state || window.dataviz.control.state('dashboard:selection/item');
        state.node.dataset.selection = selection.value || '';
        state.node.dataset.revision = selection.revision;
        state.node.dataset.updates = state.updates;
        state.node.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.item === selection.value)));
        return state;
      },
      dispose(context, state) { state.node.remove(); }
    });"""
    path = tmp_path / "selection.yaml"
    path.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "selection",
        "controls": [{"id": "item", "type": "single_select", "value_type": "text",
                      "initial": {"mode": "value", "value": "A"}, "clearable": True,
                      "options": {"mode": "static", "choices": [{"label": x, "value": x} for x in ['A', 'B']]}}],
        "sources": [{"id": "rows", "type": "python", "code": {"inline": "def load(context):\n    return [{'id': 'A'}, {'id': 'B'}]\n"},
                     "outputs": {"main": {"kind": "table"}}}],
        "canvas": {"scripts": [{"inline": script}]},
        "views": [
            {"id": "writer", "template": "custom", "renderer": "selection.example", "input": "source:rows/main",
             "control_binding": {"control": "dashboard.item", "field": "id"}},
            {"id": "observer", "template": "custom", "renderer": "selection.example", "input": "source:rows/main",
             "control_inputs": {"selection": {"mode": "value", "control": "dashboard.item"}}},
            {"id": "unrelated", "template": "table", "input": "source:rows/main"},
        ],
    }))
    root, _ = prepare_input(path)
    with _running_server(root) as url:
        _open_single_fixture_dashboard(page, url, root)
        _run_and_wait(page)
        frame = page.frame_locator('#canvas-frame')
        writer = frame.locator('[data-view-id="writer"]')
        observer = frame.locator('[data-view-id="observer"] [data-selection]')
        expect(writer.get_by_role('button', name='A', exact=True)).to_have_attribute('aria-pressed', 'true', timeout=20_000)
        run_id = page.locator('#canvas-frame').get_attribute('data-run-id')
        generation = frame.locator('[data-view-id="unrelated"]').evaluate('node => node._datavizRenderGeneration')
        writer.get_by_role('button', name='B', exact=True).click()
        expect(writer.get_by_role('button', name='B', exact=True)).to_have_attribute('aria-pressed', 'true')
        expect(observer).to_have_attribute('data-selection', 'B')
        # Same public state/apply path used by external controls and restoration;
        # a local click-only paint patch cannot make these assertions pass.
        for value in ['A', None, 'B']:
            frame.locator('body').evaluate("""async (_, value) => {
              window.dataviz.control.set('dashboard:selection/item', value);
              await window.dataviz.applyControls({keys:['dashboard:selection/item']});
            }""", value)
            expect(observer).to_have_attribute('data-selection', value or '')
            expect(writer.locator('[data-selection]')).to_have_attribute('data-selection', value or '')
        assert page.locator('#canvas-frame').get_attribute('data-run-id') == run_id
        assert frame.locator('[data-view-id="unrelated"]').evaluate('node => node._datavizRenderGeneration') == generation
        frame.locator('body').evaluate("""async () => {
          const key = 'dashboard:selection/item';
          window.dataviz.control.set(key, 'A');
          const first = window.dataviz.applyControls({keys:[key]});
          window.dataviz.control.set(key, 'B');
          await Promise.all([first, window.dataviz.applyControls({keys:[key]})]);
        }""")
        expect(writer.locator('[data-selection]')).to_have_attribute('data-selection', 'B')
        expect(observer).to_have_attribute('data-selection', 'B')
        evidence = frame.locator('body').evaluate("""() => ({
          current:window.dataviz.control.state('dashboard:selection/item').revision,
          rendered:window.datavizRuntime.viewRenderEvidence.get('writer'),
          requested:window.datavizRuntime.viewRefreshEvidence.get('observer'),
        })""")
        assert evidence['rendered']['phase'] == 'update'
        assert evidence['rendered']['binding_revisions']['dashboard:selection/item'] == evidence['current']
        assert evidence['requested']['control_revisions']['dashboard:selection/item'] == evidence['current']
        assert evidence['requested']['query_executed'] is False
        page.reload()
        expect(page.locator('#run-button')).to_be_enabled(timeout=10_000)
        _run_and_wait(page)
        expect(frame.locator('[data-view-id="writer"] [data-selection]')).to_have_attribute('data-selection', 'B', timeout=20_000)


@pytest.mark.e2e
def test_standalone_inline_python_renders_without_sidebar(page: Page, tmp_path: Path):
    from dataviz.standalone import prepare_input

    source = tmp_path / "sales.yaml"
    source.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "standalone-sales", "title": "Standalone Sales",
        "sources": [{"id": "sales", "type": "python",
                     "code": {"inline": "import pandas as pd\ndef load(context):\n    return pd.DataFrame([{'revenue': 42}])\n"},
                     "outputs": {"main": {"kind": "table"}}}],
        "interactive_transforms": [{"id": "double", "runtime": "browser-js",
                                    "code": {"inline": "function transform(context) { return {main: context.inputs.rows.map(row => ({revenue: row.revenue * 2}))}; }"},
                                    "inputs": {"rows": "source:sales/main"},
                                    "outputs": {"main": {"kind": "table"}}, "export": {"mode": "interactive"}}],
        "canvas": {"scripts": [{"inline": """
window.datavizRuntime.registerRenderer('standalone.detail', {
  mount(context, descriptor) {
    const root = document.createElement('p');
    root.textContent = 'Inline detail: ' + descriptor.rows[0].revenue;
    context.body.append(root);
    return {root};
  },
  update(context, descriptor, state) {
    state.root.textContent = 'Inline detail: ' + descriptor.rows[0].revenue;
    return state;
  },
  dispose(context, state) { state.root.remove(); }
});
"""}]},
        "views": [{"id": "total", "template": "metric", "input": "interactive:double/main", "value": "revenue"},
                  {"id": "detail", "template": "custom", "renderer": "standalone.detail", "input": "source:sales/main"}],
    }))
    root, _ = prepare_input(source)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    with _running_server(root) as url:
        _open_single_fixture_dashboard(page, url, root)
        expect(page.locator("#dashboard-sidebar")).to_be_hidden()
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)
        page.locator("#run-button").click()
        expect(page.frame_locator("#canvas-frame").locator("body")).to_contain_text("84", timeout=30_000)
        expect(page.frame_locator("#canvas-frame").locator("body")).to_contain_text("Inline detail: 42", timeout=30_000)
        bounds = page.locator(".workbench").bounding_box()
        assert bounds is not None and bounds["x"] < 40 and bounds["width"] > 1300
        page.screenshot(path=str(tmp_path / "standalone.png"))
        assert errors == []


@pytest.mark.e2e
def test_remote_single_select_search_repaints_with_scalar_state(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-single-search")
    dashboard_root = workspace / "dashboards" / "功能示例##parameter-domain-lab"
    dashboard_path = dashboard_root / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    city = next(item for item in definition["query_parameters"] if item["id"] == "cities")
    city["type"] = "single_select"
    city["default"] = {"mode": "value", "value": "C001"}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    domain_path = dashboard_root / "parameter_domains" / "locations.yaml"
    domain_path.write_text(
        domain_path.read_text(encoding="utf-8").replace("max_rows: 100", "max_rows: 700"),
        encoding="utf-8",
    )
    rows = ",\n".join(
        f"  ('GD', '广东', 1, 'C{index:03d}', '城市 {index:03d}', {index})"
        for index in range(1, 621)
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
        page_errors = []
        page.on(
            "request",
            lambda request: requests.append(request)
            if "/parameter-domains/lookup" in request.url
            else None,
        )
        page.on("pageerror", lambda error: page_errors.append(error))
        _open_dashboard(page, base_url, "parameter-domain-lab")
        select = page.locator('select[name="cities"]')
        expect(select).to_have_value("C001", timeout=20_000)
        control = page.locator("#parameter-form .dv-control").filter(has=select)
        control.locator("[data-control-trigger]").click()
        search = control.locator(".dv-choice-search")

        search.fill("城市 619")
        expect(control.locator(".dv-choice-option", has_text="城市 619")).to_have_count(
            1, timeout=10_000
        )
        expect(control.locator("[data-control-trigger]")).to_have_attribute(
            "aria-expanded", "true"
        )
        expect(search).to_be_focused()
        assert not page_errors

        payloads = [request.post_data_json for request in requests if request.post_data]
        searched = next(payload for payload in payloads if payload.get("search") == "城市 619")
        assert searched["selected"] == ["C001"]


@pytest.mark.e2e
def test_sidebar_updates_dashboard_url_before_dynamic_domain_hydration(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "dashboard-route-before-domain")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        page.evaluate(
            """() => {
              const originalFetch = window.fetch.bind(window);
              window.fetch = (input, init) => (
                String(input).includes('/parameter-domains/lookup')
                  ? new Promise(() => {})
                  : originalFetch(input, init)
              );
            }"""
        )

        target = page.locator(
            '[data-nav-type="dashboard"][data-id="parameter-domain-lab"]'
        )
        target.click()
        expect(target).to_have_class(re.compile(r"\bactive\b"))
        expect(page).to_have_url(
            re.compile(r"/dashboards/parameter-domain-lab(?:\?|$)"), timeout=1_000
        )


@pytest.mark.e2e
def test_canvas_messages_are_bound_to_the_current_frame_instance(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "frame-message-workspace")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator(".dv-canvas")).to_be_visible(timeout=20_000)
        page.evaluate("""() => {
          window.__receivedRogueSnapshots = 0;
          window.addEventListener('message', event => {
            if (event.data?.type === 'dataviz:control-snapshot'
                && event.data?.snapshot?.control_version === 999) {
              window.__receivedRogueSnapshots += 1;
            }
          });
        }""")

        # A same-origin sibling iframe must not be able to mutate the active
        # Dashboard state, even when it copies the visible frame identity.
        page.evaluate(
            """async () => {
              const active = document.querySelector('#canvas-frame');
              const rogue = document.createElement('iframe');
              rogue.hidden = true;
              rogue.src = 'about:blank';
              const loaded = new Promise(resolve => rogue.addEventListener('load', resolve, {once:true}));
              document.body.append(rogue);
              await loaded;
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
              rogue.contentWindow.eval(`parent.postMessage(${JSON.stringify(payload)}, parent.location.origin)`);
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
        # Observe both posted messages after the shell's listener has handled
        # them; do not guess delivery with a fixed sleep.
        page.wait_for_function('window.__receivedRogueSnapshots === 2')
        page.wait_for_function(
            """() => {
              const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
              if (!sessionId) return false;
              const saved = JSON.parse(
                sessionStorage.getItem(`dataviz.tab-ui.v4.${sessionId}`) || 'null'
              );
              return Boolean(saved?.dashboards?.['sales-overview']);
            }""",
            timeout=10_000,
        )
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
        "protocol": {"schema": "dataviz/runtime/v15", "component_registry_version": "3.0.0"},
        "control_state": {
            "dashboard:probe/region": {
                "intent": "explicit",
                "value": ["East"],
                "revision": 0,
            }
        },
        "view_specs": [{"id": "detail", "inputs": {"main": "source:data/main"}}],
        "dependency_contract": {
            "schema": "dataviz/dependency-contract/v13",
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
def test_multiple_input_keeps_blank_draft_during_other_control_commit(page: Page, tmp_path: Path):
    workspace = _copy_gallery_workspace(tmp_path)
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, 'component-gallery')
        _run_and_wait(page)
        page.locator('#dashboard-controls-toggle').click()
        values = page.locator('#dashboard-controls-control [data-control-component="multiple-input"]')
        expect(values.locator('[data-multiple-value]')).to_have_count(2)
        values.get_by_role('button', name='+ Add value', exact=True).click()
        expect(values.locator('[data-multiple-value]')).to_have_count(3)
        page.locator('#dashboard-controls-control [data-control-component="input-number"]').get_by_role(
            'button', name='Increase value'
        ).click()
        page.wait_for_function("""() => {
          const id = sessionStorage.getItem('dataviz.tab-session.v2');
          const saved = JSON.parse(sessionStorage.getItem(`dataviz.tab-ui.v4.${id}`) || '{}');
          return saved.dashboards?.['component-gallery']?.controlCheckpoint?.controls[
            'dashboard:component-gallery/sample-size']?.value === 60;
        }""")
        expect(values.locator('[data-multiple-value]')).to_have_count(3)
        expect(values.locator('[data-multiple-value]').last).to_have_value('')
        values.locator('[data-multiple-value]').last.fill('extra')
        page.wait_for_function("""() => document.querySelector('#canvas-frame').contentWindow
          .dataviz.control.state('dashboard:component-gallery/scenario-tags').value.includes('extra')""")
        expect(values.locator('[data-multiple-value]')).to_have_count(3)


@pytest.mark.e2e
def test_unified_dashboard_controls_drive_browser_named_output(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "showcase-controls")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        control = page.locator("#dashboard-controls-control")
        expect(control.locator("#dashboard-control-meta")).to_have_text("2 controls")
        page.locator("#dashboard-controls-toggle").click()
        expect(control.locator("#dashboard-control-group")).to_be_visible()
        expect(control.locator("#dashboard-control-form .control-scope")).to_have_count(2)
        control_geometry = control.evaluate(
            """owner => {
              const panel = owner.querySelector('.header-control__popover--controls');
              const form = owner.querySelector('#dashboard-control-form');
              const fields = [...form.querySelectorAll('.control-scope')];
              return {
                template:owner.dataset.controlTemplate,
                effectiveColumns:owner.dataset.controlEffectiveColumns,
                panelWidth:panel.getBoundingClientRect().width,
                formWidth:form.getBoundingClientRect().width,
                columns:getComputedStyle(form).gridTemplateColumns.split(' ').length,
                fieldWidths:fields.map(field => field.getBoundingClientRect().width),
              };
            }"""
        )
        assert control_geometry["template"] == "stack"
        assert control_geometry["effectiveColumns"] == "1"
        assert control_geometry["columns"] == 1
        assert control_geometry["panelWidth"] <= 610
        assert control_geometry["formWidth"] <= 570
        assert all(width <= control_geometry["panelWidth"] for width in control_geometry["fieldWidths"])

        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        radial = frame.locator('[data-view-id="radial"]')
        expect(radial).to_have_attribute("data-view-status", "ready", timeout=30_000)

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

        evidence = frame.locator("body").evaluate(
            """() => ({
              refresh:window.datavizRuntime.viewRefreshEvidence.get('radial'),
              renderer:window.datavizRuntime.viewRenderEvidence.get('radial'),
            })"""
        )
        assert evidence["refresh"]["query_executed"] is False
        assert "latest-metrics" in evidence["refresh"]["interactive_transforms"]
        assert evidence["renderer"]["duration_ms"] >= 0
        assert evidence["renderer"]["inputs"]["main"]["rows"] == 1
        assert evidence["renderer"]["inputs"]["main"]["bytes"] > 0

        page.locator("#query-parameter-author-mode").evaluate("button => button.click()")
        signal = radial.locator("[data-view-evidence-signal]")
        expect(signal).to_be_visible()
        signal.click()
        inspector = page.locator("#node-inspector")
        expect(inspector).to_be_visible()
        expect(inspector).to_contain_text("Why this View updated")
        expect(inspector).to_contain_text("Renderer input and timing")
        expect(inspector).to_contain_text("latest-metrics")
        expect(inspector.locator("#node-inspector-copy-diagnosis")).to_be_visible()
        expect(inspector.locator('.node-inspector__status')).to_have_text('ready')
        # Clipboard uses the bounded report, not the raw trace sections.
        page.evaluate("""() => {
          window.copiedDiagnosis = null;
          Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{
            writeText:async text => { window.copiedDiagnosis = JSON.parse(text); },
          }});
        }""")
        inspector.locator('#node-inspector-copy-diagnosis').click()
        page.wait_for_function('window.copiedDiagnosis !== null')
        diagnosis = page.evaluate('window.copiedDiagnosis')
        assert diagnosis['status'] == 'ready'
        assert diagnosis['inputs']['main']['rows'] == 1
        assert 'renderer' not in diagnosis  # Raw nested renderer payload is omitted.
        assert 'privacy' in diagnosis
        inspector.locator(".dialog-close").click()

        page.locator("#sidebar-toggle").click()
        expect(control).to_be_visible()
        page.locator('#dashboard-controls-toggle').click()
        expect(control).to_be_hidden()


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
        assert max(query_geometry["fieldWidths"]) <= query_geometry["formWidth"] + 1, query_geometry
        assert query_geometry["usedWidth"] <= query_geometry["formWidth"] + 1, query_geometry

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
        expect(page.locator("#shortcut-toast")).to_have_text("Share link copied.", timeout=10_000)

        page.goto(f"{base_url}{shared['url']}", wait_until="domcontentloaded")
        shared_table = page.locator('[data-view-id="scaled-table"]')
        expect(shared_table).to_have_attribute("data-view-status", "ready", timeout=15_000)
        completed = page.locator("body").evaluate(
            "() => window.datavizRuntime.metrics.interactiveTransforms.completed"
        )
        page.locator('details[data-control-origin="dashboard"] > summary').click()
        delay = page.locator(
            '.dv-context-sidebar [data-control-key="dashboard:worker-runtime/delay_ms"] input[data-control-input]'
        )
        delay.fill('6')
        delay.press('Tab')
        page.wait_for_function(
            "before => window.datavizRuntime.metrics.interactiveTransforms.completed > before",
            arg=completed,
            timeout=10_000,
        )
        expect(shared_table).to_have_attribute("data-view-status", "ready")


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
        expect(summary).to_have_text("全部")
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
def test_native_table_distinguishes_all_available_from_explicit_empty(page: Page):
    with _running_server(MINIMAL) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        table = frame.locator('[data-view-id="sales-detail"]')
        expect(table.locator("tbody tr")).to_have_count(12, timeout=20_000)

        all_evidence = frame.locator("body").evaluate(
            """async () => {
              const key = 'dashboard:sales-overview/region';
              window.dataviz.control.set(key, [], {intent:'all_available'});
              await window.datavizRuntime.renderViews({
                initial:false,
                changedControlKeys:[key],
                changedOutputReferences:[],
                queryExecuted:false,
                affectedViewIds:['sales-detail'],
              });
              return window.datavizRuntime.viewRenderEvidence.get('sales-detail').filtering;
            }"""
        )
        expect(table.locator("tbody tr")).to_have_count(12)
        assert all_evidence["rows_before"] == 12
        assert all_evidence["rows_after"] == 12
        assert all_evidence["controls"][0] == {
            "control": "dashboard:sales-overview/region",
            "intent": "all_available",
            "operands": [],
            "empty": "match_none",
            "applicable": True,
            "rows_before": 12,
            "rows_after": 12,
        }

        empty_evidence = frame.locator("body").evaluate(
            """async () => {
              const key = 'dashboard:sales-overview/region';
              window.dataviz.control.set(key, [], {intent:'explicit'});
              await window.datavizRuntime.renderViews({
                initial:false,
                changedControlKeys:[key],
                changedOutputReferences:[],
                queryExecuted:false,
                affectedViewIds:['sales-detail'],
              });
              return window.datavizRuntime.viewRenderEvidence.get('sales-detail').filtering;
            }"""
        )
        expect(table).to_have_attribute("data-view-status", "empty")
        expect(table).to_contain_text("No rows match the current selections.")
        assert empty_evidence["rows_before"] == 12
        assert empty_evidence["rows_after"] == 0
        assert empty_evidence["controls"][0]["intent"] == "explicit"
        assert empty_evidence["controls"][0]["operands"] == []


@pytest.mark.e2e
@pytest.mark.parametrize('surface', ['server', 'share', 'html'])
def test_table_row_count_is_opt_in_instead_of_a_default_metadata_row(page: Page, tmp_path: Path, surface):
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

    with _running_server(workspace) as base_url, _running_static_server(tmp_path) as static_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        if surface == 'share':
            page.locator('#share-button').click()
            with page.expect_response(lambda response: response.url.endswith('/sales-overview/share')) as response:
                page.locator('#copy-share-link').click()
            page.goto(base_url + response.value.json()['url'])
        elif surface == 'html':
            with page.expect_download() as download:
                _export_html(page)
            report = tmp_path / 'table-operations.html'
            download.value.save_as(report)
            page.goto(static_url + '/' + report.name)
        frame = page.frame_locator("#canvas-frame") if surface == 'server' else page
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
