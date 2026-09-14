from __future__ import annotations


import re







from datetime import datetime, timedelta


from pathlib import Path

from zoneinfo import ZoneInfo


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)







from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _open_dashboard,
    _run_and_wait,
    _export_html,
    SHOWCASE,
    MINIMAL,
    PROGRESSIVE,
    WORKER,
)

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
        control_heights = {
            "date": date_control.locator(".dv-date-picker").evaluate(
                "node => node.getBoundingClientRect().height"
            ),
            "range": range_control.locator(".dv-date-range__field").evaluate(
                "node => node.getBoundingClientRect().height"
            ),
        }
        assert control_heights == {"date": 42, "range": 42}
        expect(endpoints.nth(0)).to_have_value(re.compile(r"^\d{4}-\d{2}-\d{2}$"))
        expect(endpoints.nth(1)).to_have_value(re.compile(r"^\d{4}-\d{2}-\d{2}$"))
        assert endpoints.evaluate_all(
            "items => items.map(item => getComputedStyle(item).borderWidth)"
        ) == ["0px", "0px"]
        range_control.locator(".dv-date-range__field").evaluate(
            "field => { field.style.width = '224px'; }"
        )
        endpoint_widths = endpoints.evaluate_all(
            """items => items.map(item => ({
              clientWidth:item.clientWidth,
              scrollWidth:item.scrollWidth,
            }))"""
        )
        assert all(
            endpoint["scrollWidth"] <= endpoint["clientWidth"] + 1
            for endpoint in endpoint_widths
        ), endpoint_widths

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

        # Empty entry points keep their Header position but cannot open a panel.
        expect(page.locator("#query-parameters-toggle")).to_be_visible()
        expect(page.locator("#query-parameters-toggle")).to_be_disabled()
        expect(page.locator("#query-parameters-control")).to_be_hidden()
        expect(page.locator("#query-control-meta")).to_have_text("No parameters")

        for trigger, panel_selector in (
            (
                "#dashboard-controls-toggle",
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

        expect(page.locator("#query-parameters-toggle")).to_have_attribute(
            "aria-expanded", "true"
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
def test_sidebar_query_grid_keeps_bounded_fields_and_equal_entry_heights(
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
        assert wide["columns"] == 1, wide
        assert wide["width"] >= wide["ownerWidth"] * 0.94, wide
        range_box = range_field.bounding_box()
        wide_box = wide_field.bounding_box()
        assert range_box is not None and wide_box is not None
        assert range_box["width"] < 500, range_box
        assert abs(wide_box["width"] - range_box["width"]) <= 1, (range_box, wide_box)
        entry_heights = {
            "range": range_field.locator(".dv-date-range__field").evaluate(
                "node => node.getBoundingClientRect().height"
            ),
            "number": wide_field.locator(".dv-input-number").evaluate(
                "node => node.getBoundingClientRect().height"
            ),
        }
        assert entry_heights == {"range": 42, "number": 42}
        assert range_field.locator(".dv-date-range__field").evaluate(
            """field => {
              const owner = field.closest('.field').getBoundingClientRect();
              const rect = field.getBoundingClientRect();
              return rect.left >= owner.left - 1 && rect.right <= owner.right + 1;
            }"""
        )

        page.set_viewport_size({"width": 760, "height": 700})
        expect(page.locator("#query-parameters-control")).to_have_attribute(
            "data-control-effective-columns", "1"
        )
        assert (
            form.evaluate("form => getComputedStyle(form).gridTemplateColumns.split(' ').length")
            == 1
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

        rail = page.locator('#operation-panel')
        scroller = page.locator('#operation-panel-body')
        assert form.evaluate("node => getComputedStyle(node).gridTemplateColumns.split(' ').length") == 1
        rail_box, canvas_box = rail.bounding_box(), canvas.bounding_box()
        assert canvas_box['x'] + canvas_box['width'] <= rail_box['x'] + 1
        assert abs(rail_box['x'] + rail_box['width'] - 1800) <= 1
        assert rail.evaluate("node => getComputedStyle(node).position") == 'fixed'

        page.set_viewport_size({"width": 900, "height": 360})
        expect(rail).to_have_attribute('aria-modal', 'true')
        expect(page.locator('.workbench')).to_have_attribute('inert', '')
        geometry = scroller.evaluate("""node => ({
            client:node.clientHeight, scroll:node.scrollHeight,
            overflow:getComputedStyle(node).overflowY,
            bottom:node.getBoundingClientRect().bottom,
        })""")
        assert geometry['scroll'] > geometry['client'], geometry
        assert geometry['overflow'] == 'auto', geometry
        assert geometry['bottom'] <= 360, geometry
        expanded_canvas_top = canvas.bounding_box()['y']
        page.keyboard.press('Escape')
        expect(panel).to_be_hidden()
        assert abs(canvas.bounding_box()['y'] - expanded_canvas_top) <= 1
        expect(page.locator('body')).to_have_class(re.compile(r'\bsidebar-collapsed\b'))
        page.locator('#sidebar-toggle').click()
        expect(page.locator('body')).not_to_have_class(re.compile(r'\bsidebar-collapsed\b'))
        page.locator('#sidebar-toggle').click()
        toggle.click()
        expect(panel).to_be_visible()
        scroller.evaluate("node => { node.scrollTop = node.scrollHeight; }")
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

        # Pointer events inside the Canvas iframe cannot reach the Shell's
        # ordinary outside-click handler. Its authenticated interaction
        # message must dismiss Shell-owned data-entry overlays without
        # collapsing the Query Panel itself.
        page.keyboard.press('Escape')
        page.set_viewport_size({"width": 1800, "height": 720})
        trigger.click()
        page.frame_locator("#canvas-frame").locator("body").click(position={"x": 8, "y": 8})
        expect(selector_panel).to_be_hidden()
        expect(panel).to_be_visible()

        trigger.click()
        expect(selector_panel).to_be_visible()
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
def test_parameters_header_context_menu_edits_defaults_without_running(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameters-context-menu")
    definition = workspace / "dashboards" / "功能示例##parameter-playground" / "dashboard.yaml"
    runs = []
    page.on('request', lambda request: runs.append(request.url)
            if request.method == 'POST' and request.url.endswith('/runs') else None)
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, 'parameter-playground')
        trigger = page.locator('#query-parameters-toggle')
        dialog = page.locator('#parameter-editor-dialog')
        for opened in (False, True):
            if trigger.get_attribute('aria-expanded') != str(opened).lower():
                trigger.click()
            trigger.click(button='right')
            expect(dialog).to_be_visible()
            expect(dialog.locator('[data-editor-item="multiplier"]')).to_be_visible()
            dialog.get_by_role('button', name='Cancel', exact=True).click()
            expect(dialog).to_be_hidden()
            expect(trigger).to_have_attribute('aria-expanded', str(opened).lower())

        trigger.click(button='right')
        item = dialog.locator('[data-editor-item="multiplier"]')
        item.locator('[data-editor-disclosure]').click()
        item.locator('.parameter-editor__default input').fill('3')
        dialog.get_by_role('button', name='Save', exact=True).click()
        expect(dialog).to_be_hidden()
        assert yaml.safe_load(definition.read_text())['query_parameters'][0]['default'] == 3
        page.locator('#run-button').click(button='right')
        expect(dialog).to_be_visible()
        item.locator('[data-editor-disclosure]').click()
        expect(item.locator('.parameter-editor__default input')).to_have_value('3')
        dialog.get_by_role('button', name='Cancel', exact=True).click()
        assert runs == []


@pytest.mark.e2e
def test_parameter_editor_choice_rows_share_the_drag_sorting_model(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "choice-editor")
    dashboard_path = workspace / "dashboards" / "功能示例##chart-gallery" / "dashboard.yaml"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        page.locator("#dashboard-controls-toggle").click(button="right")
        dialog = page.locator("#parameter-editor-dialog")
        expect(dialog).to_be_visible()

        province = dialog.locator('[data-editor-item="province"]')
        province.locator("[data-editor-disclosure]").click()
        selection_policy = province.locator(".parameter-editor__default--selection")
        expect(selection_policy.get_by_text("Default selection", exact=True)).to_be_visible()
        assert selection_policy.evaluate("node => node.getBoundingClientRect().width") <= 321
        toolbar_geometry = province.locator(".parameter-editor__choice-toolbar").evaluate(
            """node => {
              const policy = node.querySelector('.parameter-editor__default--selection').getBoundingClientRect();
              const add = node.querySelector('.parameter-editor__add-choice').getBoundingClientRect();
              return {policyRight:policy.right, addLeft:add.left};
            }"""
        )
        assert toolbar_geometry["addLeft"] > toolbar_geometry["policyRight"]
        rows = province.locator("[data-editor-choice]")
        expect(rows).to_have_count(4)
        handles = province.locator(".parameter-editor__choice-drag-handle")
        expect(handles).to_have_count(4)
        expect(handles.first).to_have_attribute("draggable", "true")
        expect(province.locator('[data-move="up"], [data-move="down"]')).to_have_count(0)

        handles.first.press("ArrowDown")
        expect(rows.nth(0).locator("[data-choice-label]")).to_have_value("湖南")
        expect(rows.nth(1).locator("[data-choice-label]")).to_have_value("广东")

        dialog.locator('button[type="submit"]').click()
        expect(dialog).not_to_be_visible(timeout=10_000)

    saved = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    assert [choice["label"] for choice in saved["controls"][0]["options"]["choices"]] == [
        "湖南",
        "广东",
        "福建",
        "浙江",
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
        expect(fast).to_have_attribute("data-view-status", "ready", timeout=30_000)
        expect(slow).to_have_attribute("data-view-status", "loading")

        cancelled_run_id = page.locator("#canvas-frame").get_attribute("data-run-id")
        session_id = page.evaluate("() => sessionStorage.getItem('dataviz.tab-session.v2')")
        assert cancelled_run_id and session_id
        expect(page.locator("#run-button")).to_contain_text("Cancel")
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
