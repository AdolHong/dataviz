from __future__ import annotations

import json

import os

import re


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


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
@pytest.mark.parametrize("with_fields", [True, False])
def test_three_surface_shell_audit(page: Page, tmp_path: Path, with_fields: bool):
    """Collect comparable Server/Share/HTML shell evidence from one Result."""
    report = tmp_path / "three-surface.html"
    evidence = {}
    def appearance(locator):
        return locator.evaluate("""async node => {
          await Promise.all(node.getAnimations().map(animation => animation.finished.catch(() => {})));
          const s = getComputedStyle(node);
          return Object.fromEntries(['fontFamily','fontSize','fontWeight','color',
            'backgroundColor','padding','borderRadius','borderWidth','height','letterSpacing']
            .map(k => [k,s[k]]));
        }""")

    def inspect_surface(surface):
        standalone = surface != "server"
        controls = page.locator(
            ('.dv-runtime-control[data-control-origin="dashboard"] > summary'
             if with_fields else '[data-runtime-controls-disabled]')
            if standalone else '#dashboard-controls-toggle'
        )
        parameters = page.locator('[data-runtime-query-toggle]' if standalone else '#query-parameters-toggle')
        sidebar = page.locator('.dv-context-sidebar' if standalone else '#operation-panel')
        shortcuts = page.locator('[data-runtime-shortcuts-toggle]' if standalone else '#keyboard-shortcuts-toggle')
        help_dialog = page.locator('[data-runtime-shortcut-help]' if standalone else '#keyboard-shortcuts-dialog')
        evidence[surface] = {}
        page.keyboard.press("Escape")
        if sidebar.is_visible():
            page.keyboard.press("Escape")
        expect(sidebar).to_be_hidden()
        for width in (1440, 894, 375):
            page.set_viewport_size({"width": width, "height": 900})
            page.mouse.move(0, 899)
            header_state = {key: appearance(node) for key, node in
                            (("controls", controls), ("parameters", parameters), ("shortcuts", shortcuts))}
            page.screenshot(path=f"/tmp/dataviz-audit-header-{surface}-{width}.png")
            for entry in (controls, parameters, shortcuts):
                box = entry.bounding_box()
                assert box["x"] >= 0 and box["x"] + box["width"] <= width, (surface, width, box)
                header_box = page.locator('.dv-runtime-header' if standalone else '.topbar').bounding_box()
                assert box["y"] + box["height"] <= header_box["y"] + header_box["height"], (surface, width, box, header_box)
            shortcuts.click()
            expect(help_dialog).to_be_visible()
            expect(help_dialog.locator("h2")).to_have_text("Keyboard Shortcuts")
            expect(help_dialog.locator('h2')).to_be_focused()
            assert help_dialog.locator('h2').evaluate('node => getComputedStyle(node).outlineStyle') == 'none'
            help_state = {key: appearance(help_dialog.locator(selector)) for key, selector in
                          (("title", "h2"), ("key", "kbd[data-shortcut-key=W]"), ("footer", "footer button"))}
            page.keyboard.press("Escape")
            expect(help_dialog).to_be_hidden()
            expect(shortcuts).to_be_focused()
            page.keyboard.press('?')
            expect(help_dialog.locator('h2')).to_be_focused()
            expect(help_dialog.locator('header button')).not_to_be_focused()
            page.keyboard.press('Tab')
            expect(help_dialog.locator(':focus')).to_have_count(1)
            expect(help_dialog.locator('header button')).to_be_focused()
            page.keyboard.press('Shift+Tab')
            expect(help_dialog.locator('footer button')).to_be_focused()
            expect(help_dialog.locator('h2')).not_to_be_focused()
            page.keyboard.press('Escape')
            expect(help_dialog).to_be_hidden()
            expect(shortcuts).to_be_focused()
            if not with_fields:
                expect(controls).to_be_visible()
                expect(controls).to_be_disabled()
                expect(parameters).to_be_visible()
                expect(parameters).to_be_disabled()
                for key in ("w", "e"):
                    page.keyboard.press(key)
                    expect(sidebar).to_be_hidden()
                    expect(page.locator('[data-runtime-shortcut-toast]' if standalone else '#shortcut-toast')).to_be_visible()
                evidence[surface][str(width)] = {"header": header_state, "help": help_state}
                continue
            controls.click()
            expect(sidebar).to_be_visible()
            evidence[surface][str(width)] = sidebar.evaluate("""node => {
              const style = el => {
                const s = getComputedStyle(el);
                return Object.fromEntries(['fontFamily','fontSize','fontWeight','color',
                  'backgroundColor','padding','gap','borderRadius'].map(k => [k,s[k]]));
              };
              const box = node.getBoundingClientRect();
              return {box:{x:box.x,y:box.y,width:box.width,height:box.height},
                panel:style(node),heading:style(node.querySelector('h2')),
                close:style(node.querySelector('header button[aria-label^="Close"]')),
                scope:style(node.querySelector('h3')),
                modal:node.getAttribute('aria-modal')};
            }""")
            assert evidence[surface][str(width)]["box"]["width"] == 320
            evidence[surface][str(width)]["header"] = header_state
            evidence[surface][str(width)]["help"] = help_state
            page.screenshot(path=f"/tmp/dataviz-audit-{surface}-{width}.png")
            page.keyboard.press("e")
            expect(sidebar).to_be_hidden()
            parameters.click()
            expect(sidebar).to_be_visible()
            if standalone:
                expect(sidebar.locator("input, select, textarea")).to_have_count(0)
            page.keyboard.press("w")
            expect(sidebar).to_be_hidden()
        if standalone:
            expect(page.locator("#run-button, #share-button")).to_have_count(0)

    workspace = _copy_workspace(MINIMAL, tmp_path / "audit-workspace")
    if not with_fields:
        dashboard_path = workspace / "dashboards/sales-overview/dashboard.yaml"
        definition = yaml.safe_load(dashboard_path.read_text())
        definition.pop("query_parameters")
        definition.pop("controls")
        definition.pop("subtitle")
        for source in definition["sources"]:
            source.pop("query_inputs", None)
        for view in definition["views"]:
            view.pop("control_inputs", None)
            view.pop("options", None)
        dashboard_path.write_text(yaml.safe_dump(definition, allow_unicode=True))
        sql = dashboard_path.parent / "sources/sales.sql"
        sql.write_text(sql.read_text().replace("$min_query_revenue", "0"))
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        with page.expect_download(timeout=20_000) as download:
            _export_html(page)
        download.value.save_as(report)
        page.locator("#share-button").click()
        with page.expect_response(lambda response: response.url.endswith("/sales-overview/share")) as response:
            page.locator("#copy-share-link").click()
        share_url = response.value.json()["url"]
        page.keyboard.press("Escape")
        inspect_surface("server")
        page.goto(base_url + share_url, wait_until="domcontentloaded")
        expect(page.locator('[data-view-id="total-revenue"]')).to_have_attribute("data-view-status", "ready")
        inspect_surface("share")
        with _running_static_server(tmp_path) as static_url:
            page.goto(static_url + "/" + report.name, wait_until="domcontentloaded")
            expect(page.locator('[data-view-id="total-revenue"]')).to_have_attribute("data-view-status", "ready")
            inspect_surface("html")
    print("THREE_SURFACE_AUDIT " + json.dumps(evidence, ensure_ascii=False))
    for surface in ("share", "html"):
        for width in ("1440", "894", "375"):
            for part in evidence["server"][width]:
                assert evidence[surface][width][part] == evidence["server"][width][part], (surface, width, part)


@pytest.mark.e2e
def test_contextual_controls_sidebar_and_portable_state(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "context-controls")
    visual_path = workspace / "dashboards" / "功能示例##cascade-explorer" / "presentation.yaml"
    visual = yaml.safe_load(visual_path.read_text())
    # No placement declaration: sidebar is the product default.
    visual.setdefault("control_panels", {}).pop("view", None)
    visual["control_panels"].pop("section", None)
    visual['sections'] = {'geography': {'controls': {'placement': 'popover'}}}
    visual_path.write_text(yaml.safe_dump(visual, allow_unicode=True))
    report_path = tmp_path / "context-report.html"
    with _running_server(workspace) as url:
        _open_dashboard(page, url, "cascade-explorer")
        _run_and_wait(page)
        frame = page.frame_locator('#canvas-frame')
        entry = frame.locator('[data-editor-owner="view:city-detail"] > summary')
        page.locator('#dashboard-controls-toggle').click()
        dashboard_heading = page.locator('[data-dashboard-group] > h3')
        expect(dashboard_heading).to_be_visible()
        before = dashboard_heading.bounding_box()
        page.screenshot(path='/tmp/dataviz-context-dashboard-only.png')
        entry.click()
        panel = page.locator('#operation-panel')
        expect(panel).to_be_visible()
        expect(panel.locator('[data-context-group]')).to_have_count(2)
        assert panel.bounding_box()['width'] == 320
        assert panel.locator('[data-context-group="view:city-detail"] .control-scope').first.bounding_box()['width'] == pytest.approx(panel.locator('[data-context-group="view:city-detail"] h3').bounding_box()['width'], abs=1)
        expect(panel.locator('[data-context-group="section:geography"]')).to_be_visible()
        after = dashboard_heading.bounding_box()
        assert abs(before['x'] - after['x']) < 1 and abs(before['y'] - after['y']) < 1
        value = panel.locator('input[name="view:city-detail/min_value"]')
        value.fill('100')
        value.dispatch_event('change')
        page.wait_for_function("document.querySelector('#canvas-frame').contentWindow.dataviz.control_state['view:city-detail/min_value']?.value === 100")
        page.screenshot(path='/tmp/dataviz-context-desktop.png')
        value.evaluate('(node) => node.blur()')
        page.keyboard.press('e')
        expect(panel.locator('[data-context-group]')).to_have_count(0)
        expect(panel).to_be_hidden()
        entry.click()
        expect(panel.locator('input[name="view:city-detail/min_value"]')).to_have_value('100')
        panel.locator('input[name="view:city-detail/min_value"]').fill('90')
        page.keyboard.press('Escape')
        page.wait_for_function("document.querySelector('#canvas-frame').contentWindow.dataviz.control_state['view:city-detail/min_value']?.value === 90")
        entry.click()
        expect(panel.locator('input[name="view:city-detail/min_value"]')).to_have_value('90')
        page.set_viewport_size({'width': 760, 'height': 700})
        expect(panel).to_have_attribute('aria-modal', 'true')
        page.screenshot(path='/tmp/dataviz-context-mobile.png')
        page.keyboard.press('Escape')
        expect(panel).to_be_hidden()
        page.set_viewport_size({'width': 1800, 'height': 1000})
        with page.expect_download() as download:
            _export_html(page)
        download.value.save_as(report_path)
    with _running_static_server(tmp_path) as url:
        page.goto(f'{url}/{report_path.name}')
        entry = page.locator('[data-editor-owner="view:city-detail"] > summary')
        entry.click()
        panel = page.locator('.dv-context-sidebar')
        expect(panel).to_be_visible()
        expect(panel.locator('.dv-context-sidebar__body > section')).to_have_count(3)
        page.keyboard.press('e')
        expect(panel).to_have_count(0)
        entry.click()
        expect(panel).to_be_visible()
        assert panel.evaluate("node => [...node.querySelectorAll('[id]')].every(item => document.querySelectorAll(`[id=\"${CSS.escape(item.id)}\"]`).length === 1)")
        entry.click()
        expect(panel).to_have_count(0)
        entry.click()
        expect(panel).to_be_visible()
        native = panel.locator('[data-control-state-input="view:city-detail/min_value"]')
        expect(native).to_have_value('90')
        native.fill('50')
        native.dispatch_event('change')
        page.keyboard.press('Escape')
        expect(panel).to_have_count(0)
        entry.click()
        expect(page.locator('.dv-context-sidebar [data-control-state-input="view:city-detail/min_value"]')).to_have_value('50')
        page.screenshot(path='/tmp/dataviz-context-report.png')
        section = page.locator('[data-editor-owner="section:geography"]')
        section.locator('summary').click()
        expect(section).to_have_attribute('open', '')
        expect(page.locator('.dv-context-sidebar')).to_be_visible()
        expect(page.locator('.dv-context-sidebar__body > section')).to_have_count(2)
        popup_select = section.locator('select[data-control-state-input="section:geography/city"]')
        sidebar_select = page.locator('.dv-context-sidebar select[data-control-state-input="section:geography/city"]')
        popup_select.select_option(['佛山'], force=True)
        expect(sidebar_select).to_have_values(['佛山'])
        sidebar_select.select_option(['深圳'], force=True)
        expect(popup_select).to_have_values(['深圳'])


@pytest.mark.e2e
@pytest.mark.parametrize('with_dashboard', [True, False])
def test_contextual_controls_sibling_switch_and_popover_override(page: Page, tmp_path: Path, with_dashboard: bool):
    workspace = _copy_workspace(SHOWCASE, tmp_path / 'context-siblings')
    root = workspace / 'dashboards' / '功能示例##cascade-explorer'
    definition = yaml.safe_load((root / 'dashboard.yaml').read_text())
    definition.pop('canvas', None)
    definition['query_parameters'] = [{'id': 'sample', 'type': 'single_input', 'value_type': 'number', 'default': 2}]
    if not with_dashboard:
        definition.pop('controls', None)
        for view in definition['views']:
            view['control_inputs'] = {key: item for key, item in view.get('control_inputs', {}).items()
                                      if not item['control'].startswith('dashboard.')}
        for section in definition['sections']:
            for control in section.get('controls', []):
                control['depends_on'] = [key for key in control.get('depends_on', []) if not key.startswith('dashboard.')]
    sibling = json.loads(json.dumps(next(view for view in definition['views'] if view['id'] == 'city-detail')))
    sibling['id'] = 'other-detail'
    sibling['title'] = '另一张明细'
    definition['views'].append(sibling)
    definition['sections'][0]['views'].append('other-detail')
    (root / 'dashboard.yaml').write_text(yaml.safe_dump(definition, allow_unicode=True))
    visual = yaml.safe_load((root / 'presentation.yaml').read_text())
    visual['control_panels'] = {'section': {'placement': 'sidebar'}, 'view': {'placement': 'sidebar'}}
    visual['sections'] = {'geography': {'controls': {'placement': 'popover'}}}
    if not with_dashboard:
        visual['control_components'].pop('dashboard:cascade-explorer/province', None)
    (root / 'presentation.yaml').write_text(yaml.safe_dump(visual, allow_unicode=True))
    with _running_server(workspace) as url:
        _open_dashboard(page, url, 'cascade-explorer')
        _run_and_wait(page)
        frame = page.frame_locator('#canvas-frame')
        first = frame.locator('[data-editor-owner="view:city-detail"] > summary')
        second = frame.locator('[data-editor-owner="view:other-detail"] > summary')
        panel = page.locator('#operation-panel')
        section = frame.locator('[data-editor-owner="section:geography"]')
        # A popover cannot open a hidden sidebar.
        if panel.is_visible():
            page.locator('#operation-panel-close').click()
        section.locator('summary').click()
        expect(section).to_have_attribute('open', '')
        expect(panel).to_be_hidden()
        section.locator('summary').click()
        # Any local entry replaces an open Query panel without losing its draft.
        page.locator('#query-parameters-toggle').click()
        page.locator('#parameter-form input[name="sample"]').fill('7')
        section.locator('summary').click()
        expect(panel).to_be_visible()
        expect(page.locator('#operation-panel-title')).to_have_text('Controls')
        expect(panel.locator('[data-context-group="section:geography"]')).to_be_visible()
        section.locator('summary').click()
        expect(panel).to_be_visible()
        page.locator('#query-parameters-toggle').click()
        expect(page.locator('#parameter-form input[name="sample"]')).to_have_value('7')
        page.locator('#operation-panel-close').click()
        first.click()
        expect(panel.locator('[data-context-group="section:geography"]')).to_be_visible()
        if not with_dashboard:
            expect(page.locator('#dashboard-controls-toggle')).to_be_disabled()
            page.locator('#operation-panel-title').click()
            page.keyboard.press('e')
            expect(panel).to_be_hidden()
            page.keyboard.press('e')
            expect(page.locator('#shortcut-toast')).to_contain_text('no dashboard controls')
            first.click()
        second.click()
        expect(panel.locator('[data-context-group="view:city-detail"]')).to_have_count(0)
        expect(panel.locator('[data-context-group="view:other-detail"]')).to_be_visible()
        expect(panel.locator('[data-context-group]')).to_have_count(2)
        second.click()
        expect(panel).to_be_hidden()
        first.click()
        section = frame.locator('[data-editor-owner="section:geography"]')
        section.locator('summary').click()
        expect(panel).to_be_visible()
        expect(panel.locator('[data-context-group]')).to_have_count(1)
        expect(section).to_have_attribute('open', '')
        expect(section.locator('[data-control-key="section:geography/city"]')).to_be_visible()
        popup_select = section.locator('select[data-control-state-input="section:geography/city"]')
        sidebar_select = panel.locator('select[name="section:geography/city"]')
        popup_select.select_option(['佛山'], force=True)
        expect(sidebar_select).to_have_values(['佛山'])
        sidebar_select.select_option(['深圳'], force=True)
        expect(popup_select).to_have_values(['深圳'])


        # Exercise the same contextual navigation on a real Share and HTML,
        # including the no-dashboard-controls variant. Query values are read-only.
        page.keyboard.press('Escape')
        page.keyboard.press('Escape')
        with page.expect_download() as download:
            _export_html(page)
        report = tmp_path / 'context-siblings.html'
        download.value.save_as(report)
        page.locator('#share-button').click()
        with page.expect_response(lambda response: response.url.endswith('/cascade-explorer/share')) as response:
            page.locator('#copy-share-link').click()
        share_url = response.value.json()['url']
        with _running_static_server(tmp_path) as static_url:
            for surface, target in [('share', url + share_url), ('html', static_url + '/' + report.name)]:
                page.goto(target)
                panel = page.locator('.dv-context-sidebar')
                section = page.locator('[data-editor-owner="section:geography"]')
                first = page.locator('[data-editor-owner="view:city-detail"] > summary')
                second = page.locator('[data-editor-owner="view:other-detail"] > summary')
                section.locator('summary').click()
                expect(section).to_have_attribute('open', '')
                expect(panel).to_be_hidden()
                section.locator('summary').click()
                page.locator('[data-runtime-query-toggle]').click()
                expect(panel.locator('input, select, textarea')).to_have_count(0)
                section.locator('summary').click()
                expect(panel).to_be_visible()
                expect(panel.locator('h2')).to_have_text('Controls')
                expect(panel.locator('.dv-context-sidebar__body > section')).to_have_count(2 if with_dashboard else 1)
                section.locator('summary').click()
                expect(panel).to_be_visible()
                first.click()
                expect(panel.locator('.dv-context-sidebar__body > section')).to_have_count(3 if with_dashboard else 2)
                second.click()
                expect(panel.get_by_role('heading', name=re.compile('另一张明细'))).to_be_visible()
                expect(panel.get_by_role('heading', name=re.compile('级联后的城市明细'))).to_have_count(0)
                browser_name = os.environ.get('DATAVIZ_BROWSER', 'chromium')
                panel.screenshot(path=f'/tmp/dataviz-context-path-{browser_name}-{surface}-{with_dashboard}.png')
                second.click()
                expect(panel).to_be_hidden()
                first.click()
                section.locator('summary').click()
                expect(panel).to_be_visible()
                expect(section).to_have_attribute('open', '')
                expect(panel.locator('.dv-context-sidebar__body > section')).to_have_count(2 if with_dashboard else 1)
                popup_choice = section.locator('.dv-checkbox-option[data-value="佛山"]')
                popup_choice.click()
                expect(panel.locator('select[data-control-state-input="section:geography/city"]')).to_have_values(['佛山', '深圳'])
                panel.locator('.dv-checkbox-option[data-value="深圳"]').click()
                expect(section.locator('select')).to_have_values(['佛山'])
                # Clicking the sidebar is outside the popover: native light
                # dismiss closes it. Reopen to verify Escape closes only it.
                expect(section).not_to_have_attribute('open', '')
                section.locator('summary').click()
                expect(section).to_have_attribute('open', '')
                page.keyboard.press('Escape')
                expect(section).not_to_have_attribute('open', '')
                expect(panel).to_be_visible()
                page.keyboard.press('e')
                expect(panel).to_be_hidden()


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
        page.locator("#dashboard-controls-toggle").click()
        selector = header.locator('select[name="dashboard:sales-overview/region"]')
        expect(selector).to_have_attribute("data-value-encoding", "string")
        expect(selector.locator("option")).to_have_count(3, timeout=20_000)
        assert selector.evaluate(
            "select => [...select.options].map(option => option.value).sort()"
        ) == ["华东", "华北", "华南"]
        assert selector.evaluate(
            "select => [...select.selectedOptions].map(option => option.value)"
        ) == ["华东", "华北", "华南"]
        selector_summary = header.locator("[data-control-summary]")
        expect(selector_summary).to_have_text("全部")
        expect(selector).to_have_attribute("data-selection-intent", "all_available")

        selector.select_option(["华南"], force=True)
        expect(selector_summary).to_have_text("华南")
        expect(selector).to_have_attribute("data-selection-intent", "explicit")
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator('[data-view-id="total-revenue"]')).to_contain_text(
            "449,000", timeout=10_000
        )
        expect(frame.locator('[data-view-id="total-revenue"] .dv-metric__unit')).to_have_text(
            "元"
        )
        expect(
            frame.locator('[data-view-id="total-revenue"] .dv-metric__secondary')
        ).to_contain_text("订单")

