from __future__ import annotations


import re


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


from dataviz.protocols import DASHBOARD_SCHEMA


from dataviz.workspace import load_workspace

from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _running_static_server,
    _open_single_fixture_dashboard,
    _open_dashboard,
    _run_and_wait,
    _export_html,
    SHOWCASE,
    MINIMAL,
)

@pytest.mark.e2e
def test_navigation_supersedes_slow_page_and_lookup_requests(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "slow-navigation")
    path = workspace / "dashboards" / "功能示例##parameter-domain-lab" / "dashboard.yaml"
    definition = yaml.safe_load(path.read_text())
    fields = {key: definition.pop(key) for key in ("query_parameters", "views", "sections")}
    definition["pages"] = [{"id": name, "title": name, **fields} for name in ("first", "slow", "last")]
    path.write_text(yaml.safe_dump(definition, allow_unicode=True))
    held = []
    lookups = []
    failed = []
    runs = []

    def hold_lookup(route):
        lookups.append(route.request.post_data_json)
        held.append(route)

    page.route("**/parameter-domains/lookup", hold_lookup)
    page.route("**/pages/slow", lambda route: held.append(route))
    page.on("requestfailed", lambda request: failed.append(request.url))
    page.on("request", lambda request: runs.append(request.url)
            if request.method == "POST" and request.url.endswith("/runs") else None)
    with _running_server(workspace, watch=False) as url:
        page.goto(f"{url}/dashboards/parameter-domain-lab#page=first")
        first = page.locator('#page-navigation-list [data-page-id="first"]')
        slow = page.locator('#page-navigation-list [data-page-id="slow"]')
        last = page.locator('#page-navigation-list [data-page-id="last"]')
        expect(first).to_have_attribute("aria-current", "page")
        page.wait_for_function("document.querySelector('#input-provinces').closest('.dv-control').getAttribute('aria-busy') === 'true'")
        with page.expect_request("**/pages/slow"):
            slow.click()
        expect(page.locator('#run-button')).to_be_disabled()
        last.click()
        expect(last).to_have_attribute("aria-current", "page", timeout=5_000)
        expect(page).to_have_url(re.compile(r"#page=last$"))
        # Lookup is deliberately held, so native options do not exist yet.
        # The canonical finite selection remains in the Page's URL/state.
        assert "provinces=GD" in page.url
        # Neither held request was released to let navigation complete.
        assert any("/pages/slow" in request for request in failed)
        assert any("/parameter-domains/lookup" in request for request in failed)
        other = page.locator('[data-nav-type="dashboard"][data-id="chart-gallery"]')
        other.click()
        expect(other).to_have_class(re.compile(r"\bactive\b"), timeout=5_000)
        expect(page.locator('#canvas-frame')).to_have_attribute("data-dashboard-id", "chart-gallery")
        # Drain abort continuations; stale outer loops must not request cities
        # against the new Page or Dashboard after their first await returns.
        page.evaluate("() => new Promise(resolve => setTimeout(resolve, 100))")
        assert lookups and all(item["parameter"] == "provinces" for item in lookups), lookups
        assert runs == []
        for route in held:
            route.abort()


@pytest.mark.e2e
def test_portable_query_tray_uses_shared_sidebar_for_clicks_and_shortcuts(page: Page, tmp_path: Path):
    report_path = tmp_path / "portable-header-controls.html"
    with _running_server(MINIMAL) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        for selector in (
            '#keyboard-shortcuts-toggle', '#dashboard-controls-toggle',
            '#query-parameters-toggle', '#run-button strong',
        ):
            button = page.locator(selector)
            expect(button).to_have_css('font-size', '12px')
            expect(button).to_have_css('font-weight', '600')
            expect(button).to_have_css('letter-spacing', 'normal')
            expect(button).to_have_css('text-transform', 'none')
        expect(page.locator('#run-button strong')).to_have_text('Run')
        page.keyboard.press('Escape')
        page.mouse.move(0, 300)
        for selector in ('#keyboard-shortcuts-toggle', '#dashboard-controls-toggle',
                         '#query-parameters-toggle', '#share-button'):
            expect(page.locator(selector)).to_have_css('color', 'rgb(84, 90, 99)')
        expect(page.locator('#run-button strong')).to_have_css('color', 'rgb(255, 255, 255)')
        page.locator('.topbar').screenshot(path='/tmp/dataviz-header-02410.png')
        # Hotkeys and pointer focus must not look like a second selected state.
        for key, selector in (('q', '#sidebar-toggle'), ('e', '#query-parameters-toggle'),
                              ('w', '#dashboard-controls-toggle')):
            button = page.locator(selector)
            button.click()
            page.keyboard.press(key)
            button.focus()
            expect(button).to_have_css('outline-style', 'none')
            expect(button).to_have_css('box-shadow', 'none')
        page.keyboard.press('Escape')
        page.locator('#keyboard-shortcuts-toggle').focus()
        page.keyboard.press('Tab')
        focused_header = page.locator('.topbar :focus')
        expect(focused_header).to_have_count(1)
        expect(focused_header).to_have_css('outline-style', 'solid')
        page.locator('#sidebar-toggle').focus()
        expect(page.locator('#sidebar-toggle')).to_have_css('outline-style', 'solid')
        page.mouse.click(400, 200)
        server_visual = page.evaluate(
            """() => {
              const header = document.querySelector('.topbar');
              const card = document.querySelector('.dv-query-card');
              const title = card.querySelector('h2');
              const field = card.querySelector('.field');
              const value = field.querySelector('input, select, output');
              const brand = document.querySelector('.dv-shell-brand');
              const control = document.querySelector('.dv-shell-control__trigger');
              const pick = (node, properties) => Object.fromEntries(
                properties.map(name => [name, getComputedStyle(node)[name]])
              );
              return {
                headerHeight:header.getBoundingClientRect().height,
                body:pick(document.body, ['fontFamily', 'fontSize', 'backgroundColor']),
                brand:pick(brand, ['display', 'alignItems', 'gap', 'height', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'color', 'backgroundColor', 'borderRadius']),
                brandMark:pick(brand.querySelector('.dv-shell-brand__mark'), ['display', 'width', 'height', 'color', 'backgroundColor', 'borderRadius', 'fontFamily', 'fontSize', 'fontWeight', 'letterSpacing']),
                brandName:pick(brand.querySelector('.dv-shell-brand__name'), ['color', 'fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'letterSpacing']),
              };
            }"""
        )
        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        toggle = page.locator("[data-runtime-query-toggle]")
        expect(page.locator('#run-button, #share-control, button.query-run-control__primary')).to_have_count(0)
        page.keyboard.press('?')
        help_dialog = page.locator('[data-runtime-shortcut-help]')
        expect(help_dialog).to_be_visible()
        expect(help_dialog).not_to_contain_text('Run query')
        expect(help_dialog).not_to_contain_text('Sidebar')
        expect(help_dialog).not_to_contain_text('Ctrl/Cmd')
        help_dialog.locator('[data-runtime-single-key-shortcuts]').uncheck()
        expect(help_dialog.locator('[data-shortcut-key="E"]')).to_have_text('Cmd + Ctrl + E')
        page.keyboard.press('Escape')
        panel = page.locator("#dv-runtime-query-panel")
        page.keyboard.press('e')
        expect(panel).to_be_hidden()
        page.keyboard.press('Meta+Control+e')
        expect(panel).to_be_visible()
        page.keyboard.press('Meta+Control+e')
        expect(panel).to_be_hidden()
        page.keyboard.press('?')
        expect(help_dialog).to_be_visible()
        help_dialog.locator('[data-runtime-single-key-shortcuts]').check()
        page.keyboard.press('Escape')
        canvas = page.locator(".dv-canvas")
        expect(toggle).to_have_attribute("aria-expanded", "false")
        expect(panel).to_be_hidden()
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        expect(panel).to_be_visible()
        portable_visual = page.evaluate(
            """() => {
              const header = document.querySelector('.dv-runtime-header');
              const brand = document.querySelector('.dv-shell-brand');
              const control = document.querySelector('.dv-shell-control__trigger');
              const pick = (node, properties) => Object.fromEntries(
                properties.map(name => [name, getComputedStyle(node)[name]])
              );
              return {
                headerHeight:header.getBoundingClientRect().height,
                body:pick(document.body, ['fontFamily', 'fontSize', 'backgroundColor']),
                brand:pick(brand, ['display', 'alignItems', 'gap', 'height', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'color', 'backgroundColor', 'borderRadius']),
                brandMark:pick(brand.querySelector('.dv-shell-brand__mark'), ['display', 'width', 'height', 'color', 'backgroundColor', 'borderRadius', 'fontFamily', 'fontSize', 'fontWeight', 'letterSpacing']),
                brandName:pick(brand.querySelector('.dv-shell-brand__name'), ['color', 'fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'letterSpacing']),
              };
            }"""
        )
        assert abs(portable_visual.pop("headerHeight") - server_visual.pop("headerHeight")) <= 1
        # Fully transparent RGB channels are not visible. Firefox may retain
        # the hover color's RGB at alpha=0 after a transition on only one page.
        # Normalize that equivalent representation, not nonzero alpha/colors.
        for visual in (portable_visual, server_visual):
            for properties in visual.values():
                for name, value in properties.items():
                    if name in {'color', 'backgroundColor'} and re.fullmatch(
                        r'rgba\(\s*\d+,\s*\d+,\s*\d+,\s*0(?:\.0+)?\s*\)', value
                    ):
                        properties[name] = 'transparent'
        assert portable_visual == server_visual
        sidebar = page.locator('.dv-context-sidebar')
        expect(sidebar).to_have_attribute('aria-label', 'Parameters')
        assert sidebar.bounding_box()['width'] == 320
        assert panel.locator('input, select, textarea').count() == 0
        expect(page.locator('.dv-runtime-query-tray')).to_be_hidden()
        canvas_top = canvas.bounding_box()['y']
        page.screenshot(path='/tmp/dataviz-export-parameters-sidebar.png')
        page.keyboard.press('e')
        expect(sidebar).to_have_count(0)
        assert canvas.bounding_box()['y'] == pytest.approx(canvas_top, abs=1)
        page.keyboard.press('e')
        expect(sidebar).to_have_attribute('aria-label', 'Parameters')
        toggle.click()
        expect(sidebar).to_have_count(0)
        toggle.click()
        page.keyboard.press('Escape')
        expect(sidebar).to_have_count(0)
        expect(toggle).to_be_focused()
        owner = page.locator('.dv-runtime-control[data-control-origin="dashboard"]')
        entry = owner.locator(':scope > summary')
        entry.click()
        expect(sidebar).to_have_attribute('aria-label', 'Controls')
        expect(owner).not_to_have_attribute('open', '')
        page.keyboard.press('w')
        expect(sidebar).to_have_count(0)
        page.keyboard.press('w')
        expect(sidebar).to_have_attribute('aria-label', 'Controls')
        scope_heading = sidebar.locator('h3').last
        expect(scope_heading).to_be_focused()
        expect(scope_heading).to_have_css('outline-style', 'none')
        page.screenshot(path='/tmp/dataviz-export-heading-focus.png')
        page.keyboard.press('Tab')
        focused_control = sidebar.locator(':focus')
        expect(focused_control).to_have_count(1)
        assert focused_control.evaluate('(el) => el.matches("button, input, select, textarea, [role=combobox]")')
        expect(focused_control).to_have_css('outline-style', 'solid')
        toggle.click()
        expect(sidebar).to_have_attribute('aria-label', 'Parameters')
        entry.click()
        expect(sidebar).to_have_attribute('aria-label', 'Controls')
        entry.click()
        expect(sidebar).to_have_count(0)
        page.set_viewport_size({'width': 375, 'height': 760})
        page.keyboard.press('e')
        expect(sidebar).to_have_attribute('aria-modal', 'true')
        assert sidebar.bounding_box()['width'] == 320
        page.screenshot(path='/tmp/dataviz-export-parameters-mobile.png')
        page.keyboard.press('Escape')
        expect(sidebar).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.parametrize("reload_phase", ["running", "ready"])
def test_query_reload_restores_visible_date_range_and_single_select(page: Page, tmp_path: Path, reload_phase: str):
    from dataviz.standalone import prepare_input

    dashboard = tmp_path / "query.yaml"
    dashboard.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "query-restore", "title": "Query restore",
        "query_parameters": [
            {"id": "dates", "type": "range_input", "value_type": "date",
             "default": ["2026-09-03", "2026-09-09"]},
            {"id": "grain", "type": "single_select", "value_type": "text", "clearable": True,
             "default": {"mode": "value", "value": "all"},
             "options": {"mode": "static", "choices": [
                 {"label": "全部", "value": "all"}, {"label": "品类", "value": "category"}]}},
        ],
        "sources": [{"id": "rows", "type": "python", "query_inputs": {"dates": "dates", "grain": "grain"},
                     "code": {"inline": "import time\ndef load(context):\n    time.sleep(6)\n    return [{'dates': str(context.query_inputs['dates']), 'grain': context.query_inputs['grain']}]\n"},
                     "outputs": {"main": {"kind": "table"}}}],
        "views": [{"id": "table", "template": "table", "input": "source:rows/main"}],
    }), encoding="utf-8")
    runs = []
    page.on("request", lambda request: runs.append(request.post_data_json)
            if request.method == "POST" and request.url.endswith("/runs") else None)
    root, _ = prepare_input(dashboard)
    assert load_workspace(root).dashboard("query-restore").definition.id == "query-restore"
    with _running_server(root, watch=False) as url:
        _open_single_fixture_dashboard(page, url, root)
        endpoints = page.locator('#parameter-form .dv-date-range__endpoint')
        endpoints.nth(0).fill("2026-09-09")
        endpoints.nth(1).fill("2026-09-09")
        endpoints.nth(1).press("Enter")
        select = page.locator('#parameter-form select[name="grain"]')
        field = page.locator('#parameter-form .field', has=page.locator('select[name="grain"]'))
        field.locator('[data-control-trigger]').click()
        field.locator('.dv-choice-option', has_text="品类").click()
        summary = field.locator('[data-control-summary]')
        expect(summary).to_have_text("品类")
        page.locator('#run-button').click()
        expect(page.locator('#run-button strong')).to_have_text("Cancel")
        if reload_phase == "ready":
            expect(page.locator('#run-button strong')).to_have_text("Run", timeout=30_000)
        page.reload(wait_until="domcontentloaded")
        expect(select).to_have_value("category")
        expect(page.locator('#parameter-form input[name="dates"]')).to_have_value("2026-09-09,2026-09-09")
        if not endpoints.nth(0).is_visible():
            page.locator('#query-parameters-toggle').click()
        # Native inputs alone are insufficient: the visible component must
        # project the restored state rather than its mount-time defaults.
        expect(endpoints.nth(0)).to_have_value("2026-09-09")
        expect(endpoints.nth(1)).to_have_value("2026-09-09")
        expect(summary).to_have_text("品类")
        table = page.frame_locator('#canvas-frame').locator('[data-view-id="table"]')
        expect(table).to_contain_text("category", timeout=30_000)
        assert "2026-09-03" not in table.inner_text()
        assert len(runs) == 1
        assert runs[0]["query_parameter_state"] == {
            "dates": {"value": ["2026-09-09", "2026-09-09"]}, "grain": {"value": "category"},
        }
