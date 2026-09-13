from __future__ import annotations



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
)

@pytest.mark.e2e
def test_cascader_search_density_and_exported_sidebar_corners(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / 'cascader-density', dashboards=('功能示例##cascade-explorer',))
    path = workspace / 'dashboards/功能示例##cascade-explorer/dashboard.yaml'
    dashboard = yaml.safe_load(path.read_text())
    for control_id in ['locations', 'locations2']:
        dashboard['controls'].append({
            'id': control_id, 'type': 'multiple_select', 'value_type': 'text',
            'label': control_id, 'path_fields': ['province', 'city'], 'options': {'mode': 'infer'},
        })
        dashboard['views'][0]['control_inputs'][control_id] = {
            'mode': 'filter', 'control': f'dashboard.{control_id}',
            'field': ['province', 'city'], 'inputs': ['main'], 'empty': 'match_none',
        }
    path.write_text(yaml.safe_dump(dashboard, allow_unicode=True))
    report = tmp_path / 'cascaders.html'
    with _running_server(workspace) as url:
        _open_dashboard(page, url, 'cascade-explorer')
        _run_and_wait(page)
        with page.expect_download() as download:
            _export_html(page)
        download.value.save_as(report)
    with _running_static_server(tmp_path) as url:
        page.goto(f'{url}/{report.name}')
        page.locator('[data-editor-owner="view:city-detail"] > summary').click()
        sidebar = page.locator('.dv-context-sidebar')
        expect(sidebar).to_be_visible()
        controls = sidebar.locator('.dv-context-sidebar__body > section').first.locator('[data-control-component="cascader"]')
        expect(controls).to_have_count(2)
        wrapper = sidebar.locator('.dv-runtime-popover').first
        style = wrapper.evaluate("node => ({radius:getComputedStyle(node).borderRadius, overflow:getComputedStyle(node).overflow})")
        for index in range(2):
            control = controls.nth(index)
            control.locator('[data-control-trigger]').click()
            search = control.locator('.dv-choice-search')
            search.fill('广东')
            expect(control.locator('.dv-cascader-results .dv-cascader-option')).to_have_count(2)
            search.press('Escape')
        # Search density is covered directly by components/test_choices.py.
        # Keep the export-specific wrapper and two independently usable pickers.
        assert style == {'radius': '0px', 'overflow': 'visible'}


@pytest.mark.parametrize('surface', ['server', 'share', 'html'])
@pytest.mark.e2e
def test_cascader_sidebar_bounds_and_global_all(page: Page, tmp_path: Path, surface):
    # Exercise every hosting surface at the tightest width. Component tests
    # cover all three widths without repeating query/export setup nine times.
    viewport_width = 375
    workspace = _copy_workspace(SHOWCASE, tmp_path / 'cascader-bounds', dashboards=('功能示例##cascade-explorer',))
    path = workspace / 'dashboards/功能示例##cascade-explorer/dashboard.yaml'
    dashboard = yaml.safe_load(path.read_text())
    view = next(view for view in dashboard['views'] if view['id'] == 'city-detail')
    control = next(control for control in view['controls'] if control['id'] == 'district')
    control['path_fields'] = ['province', 'city']
    view['control_inputs']['district']['field'] = ['province', 'city']
    path.write_text(yaml.safe_dump(dashboard, allow_unicode=True))
    page.set_viewport_size({'width': viewport_width, 'height': 900})
    with _running_server(workspace) as url, _running_static_server(tmp_path) as static_url:
        _open_dashboard(page, url, 'cascade-explorer')
        _run_and_wait(page)
        if page.locator('#sidebar-toggle').get_attribute('aria-expanded') == 'true':
            page.locator('#sidebar-toggle').click()
        if surface == 'html':
            with page.expect_download() as download:
                _export_html(page)
            report = tmp_path / 'cascade-audit.html'
            download.value.save_as(report)
            page.goto(f'{static_url}/{report.name}')
        elif surface == 'share':
            page.locator('#share-button').click()
            with page.expect_response(lambda response: response.url.endswith('/cascade-explorer/share')) as response:
                page.locator('#copy-share-link').click()
            page.goto(url + response.value.json()['url'])
        frame = page.frame_locator('#canvas-frame') if surface == 'server' else page
        frame.locator('[data-editor-owner="view:city-detail"] > summary').click()
        sidebar = page.locator('#operation-panel' if surface == 'server' else '.dv-context-sidebar')
        number = sidebar.locator('[data-control-component="input-number"]')
        number_input = number.locator('input')
        assert number_input.evaluate('node => getComputedStyle(node).appearance') == 'textfield'
        number.get_by_role('button', name='Increase value').click()
        expect(number_input).to_have_value('1')
        number.get_by_role('button', name='Decrease value').click()
        expect(number_input).to_have_value('0')
        cascader = sidebar.locator('[data-control-component="cascader"]')
        runtime = "document.querySelector('#canvas-frame').contentWindow" if surface == 'server' else 'window'
        cascader.locator('[data-control-trigger]').click()
        panel = cascader.locator('.dv-cascader-panel')
        expect(panel).to_be_visible()
        def assert_bounds():
            box = panel.bounding_box()
            assert box['x'] >= 11
            assert box['x'] + box['width'] <= viewport_width - 11
            assert panel.evaluate('node => node.scrollWidth <= node.clientWidth + 1')
        assert_bounds()
        clear = panel.get_by_role('button', name=re.compile('^Clear'))
        clear.click()
        expect(cascader.locator('select')).to_have_values([])
        expect(panel.get_by_role('button', name='Revert', exact=True)).to_have_count(0)
        panel.get_by_role('button', name='Select all', exact=True).click()
        page.wait_for_function(runtime + ".dataviz.control.state('view:city-detail/district').intent === 'all_available'")
        assert cascader.locator('select').evaluate('s => s.selectedOptions.length === s.options.length')
        clear.click()
        expect(cascader.locator('select')).to_have_values([])
        panel.locator('.dv-choice-search').fill('深圳')
        all_button = panel.get_by_role('button', name='Select results', exact=True)
        all_button.click()
        assert cascader.locator('select').evaluate('s => s.selectedOptions.length > 0 && [...s.selectedOptions].every(o => o.textContent.includes("深圳"))')
        expect(all_button).to_be_disabled()
        panel.locator('.dv-choice-search').fill('佛山')
        panel.get_by_role('button', name='Select results', exact=True).click()
        panel.get_by_role('button', name='Clear results', exact=True).click()
        assert cascader.locator('select').evaluate('s => s.selectedOptions.length > 0 && [...s.selectedOptions].every(o => o.textContent.includes("深圳"))')
        panel.locator('.dv-choice-search').fill('')
        panel.get_by_role('button', name='Select all', exact=True).click()
        page.wait_for_function(runtime + ".dataviz.control.state('view:city-detail/district').intent === 'all_available'")
        panel.locator('.dv-choice-search').fill('no-matching-path')
        expect(panel.locator('.dv-choice-empty')).to_be_visible()
        expect(panel.get_by_role('button', name='Select results', exact=True)).to_be_disabled()
        expect(panel.get_by_role('button', name='Clear results', exact=True)).to_be_disabled()
        assert_bounds()
        panel.locator('.dv-choice-search').press('Escape')
        expect(panel).to_be_hidden()
        expect(sidebar).to_be_visible()


@pytest.mark.e2e
def test_selection_cascade_popovers_view_isolation_and_table_wheel(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "showcase", dashboards=('功能示例##cascade-explorer',))
    visual_path = workspace / 'dashboards/功能示例##cascade-explorer/presentation.yaml'
    visual = yaml.safe_load(visual_path.read_text())
    visual.setdefault('control_panels', {}).update({'section': {'placement': 'popover'}, 'view': {'placement': 'popover'}})
    visual_path.write_text(yaml.safe_dump(visual, allow_unicode=True))
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "cascade-explorer")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator('[data-view-id="map-bars"][data-view-status="ready"]')).to_be_visible(
            timeout=15_000
        )

        # Header and Canvas-owned popovers both close when focus moves elsewhere.
        header = page.locator("#dashboard-controls-control")
        page.locator("#dashboard-controls-toggle").click()
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
        expect(header).to_be_visible()

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
        page.wait_for_function("() => document.querySelector('#canvas-frame').contentWindow.__datavizRenderCalls.length > 0")
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
