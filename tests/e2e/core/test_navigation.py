from __future__ import annotations


import re

import shutil


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


from dataviz.protocols import DASHBOARD_SCHEMA, WORKSPACE_SCHEMA


from e2e.support.runtime import (
    _running_server,
    _open_single_fixture_dashboard,
    _open_dashboard,
    MINIMAL,
)

@pytest.mark.e2e
def test_root_requires_explicit_or_remembered_dashboard(page: Page):
    with _running_server(MINIMAL) as base_url:
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#dashboard-empty")).to_be_visible()
        expect(page.locator(".nav-button.active")).to_have_count(0)
        expect(page.locator("#run-button")).to_be_disabled()
        expect(page.locator("#query-parameters-toggle")).to_be_disabled()
        expect(page.locator("#dashboard-controls-toggle")).to_be_disabled()
        assert not any("/canvas" in url or "/parameter-domains/" in url for url in requests)
        assert page.url.rstrip("/") == base_url.rstrip("/")
        page.reload(wait_until="networkidle")
        expect(page.locator("#dashboard-empty")).to_be_visible()

        _open_dashboard(page, base_url, "sales-overview")
        expect(page.locator("#dashboard-empty")).to_be_hidden()
        page.goto(base_url, wait_until="domcontentloaded")
        expect(page).to_have_url(re.compile(r"/dashboards/sales-overview"))
        expect(page.locator("#canvas-frame")).to_have_attribute("data-dashboard-id", "sales-overview")

        # A removed remembered dashboard must not silently select another one.
        page.evaluate("""() => {
          for (const key of Object.keys(sessionStorage)) {
            if (!key.startsWith('dataviz.tab-ui.v4.')) continue;
            const saved = JSON.parse(sessionStorage.getItem(key));
            saved.activeDashboardId = 'removed-dashboard';
            sessionStorage.setItem(key, JSON.stringify(saved));
          }
        }""")
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#dashboard-empty")).to_be_visible()
        expect(page.locator(".nav-button.active")).to_have_count(0)
        page.goto(base_url + "/dashboards/sales-overview", wait_until="domcontentloaded")
        expect(page.locator("#canvas-frame")).to_have_attribute("data-dashboard-id", "sales-overview")


@pytest.mark.e2e
def test_pages_preserve_independent_queries_and_history(page: Page, tmp_path: Path):
    root = tmp_path / "workspace"
    dashboard = root / "dashboards" / "holiday"
    dashboard.mkdir(parents=True)
    (root / "workspace.yaml").write_text(yaml.safe_dump({"schema": WORKSPACE_SCHEMA, "id": "pages", "title": "Pages"}))
    (dashboard / "rules.py").write_text(
        "import time\ndef load(context):\n    time.sleep(.3)\n"
        "    return {'main': [{'period': str(context.query_inputs['period'])}]}\n"
    )
    for name in ("annual", "history"):
        shutil.copyfile(dashboard / "rules.py", dashboard / f"{name}.py")
    (dashboard / "scroll.css").write_text("body { min-height: 2400px; }\n")
    (dashboard / "dashboard.yaml").write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "holiday", "title": "Holiday analysis",
        "canvas": {"styles": ["scroll.css"]},
        "sources": [
            {"id": name, "type": "python", "code": f"{name}.py", "query_inputs": {"period": "year"},
             "outputs": {"main": {"kind": "table"}}} for name in ("annual", "history")],
        "pages": [
            {"id": "annual", "title": "One year", "query_parameters": [
                {"id": "year", "label": "Year", "type": "single_input", "value_type": "integer", "default": 2025}],
             "controls": [{"id": "factor", "type": "single_input", "value_type": "integer", "default": 1}],
             "views": [{"id": "table", "template": "table", "input": "source:annual/main"}]},
            {"id": "history", "title": "Across years", "query_parameters": [
                {"id": "year", "label": "Years", "type": "multiple_input", "value_type": "integer", "default": [2023, 2024]}],
             "controls": [{"id": "factor", "type": "single_input", "value_type": "integer", "default": 10}],
             "views": [{"id": "table", "template": "table", "input": "source:history/main"}]},
        ],
    }))
    runs = []
    page.on("request", lambda request: runs.append(request.post_data_json)
            if request.method == "POST" and request.url.endswith("/runs") else None)
    with _running_server(root) as url:
        _open_single_fixture_dashboard(page, url, root)
        annual = page.locator('#page-navigation-list button[data-page-id="annual"]')
        history = page.locator('#page-navigation-list button[data-page-id="history"]')
        expect(annual).to_have_attribute("aria-current", "page")
        expect(page.locator('#parameter-form input[name="year"]')).to_have_value("2025")
        assert runs == []
        page.locator("#run-button").click()
        expect(page.locator("#run-button strong")).to_have_text("Cancel")
        history.click()
        expect(history).to_have_attribute("aria-current", "page")
        expect(page.locator('#parameter-form input[name="year"]')).to_have_value("[2023,2024]")
        page.locator("#run-button").click()
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator('[data-view-id="table"]')).to_contain_text("2023", timeout=30_000)
        expect(page.locator("#run-button strong")).to_have_text("Run", timeout=30_000)
        history_run = page.locator("#canvas-frame").get_attribute("data-run-id")
        annual.click()
        expect(annual).to_have_attribute("aria-current", "page")
        expect(frame.locator('[data-view-id="table"]')).to_contain_text("2025", timeout=30_000)
        expect(page.locator("#run-button strong")).to_have_text("Run")
        assert len(runs) == 2
        assert {request["page_id"] for request in runs} == {"annual", "history"}
        frame.locator('body').evaluate("""async () => {
          await window.dataviz.control.set('dashboard:holiday/factor', 5);
          await window.dataviz.applyControls({keys:['dashboard:holiday/factor']});
          window.scrollTo(0, 450);
        }""")
        expect(frame.locator('body')).to_have_js_property('scrollHeight', 2400)
        history.click()
        expect(frame.locator('[data-view-id="table"]')).to_contain_text('2023', timeout=15_000)
        assert frame.locator('body').evaluate("() => window.dataviz.control.state('dashboard:holiday/factor').value") == 10
        frame.locator('body').evaluate("""async () => {
          await window.dataviz.control.set('dashboard:holiday/factor', 20);
          await window.dataviz.applyControls({keys:['dashboard:holiday/factor']});
        }""")
        annual.click()
        expect(frame.locator('[data-view-id="table"]')).to_contain_text('2025', timeout=15_000)
        assert frame.locator('body').evaluate("() => window.dataviz.control.state('dashboard:holiday/factor').value") == 5
        assert frame.locator('body').evaluate('() => window.scrollY') == 450
        history.click()
        expect(history).to_have_attribute("aria-current", "page")
        expect(page.locator("#canvas-frame")).to_have_attribute("data-run-id", history_run)
        assert "#page=history" in page.url
        page.reload()
        expect(history).to_have_attribute("aria-current", "page")
        expect(frame.locator('[data-view-id="table"]')).to_contain_text("2023", timeout=30_000)
        assert frame.locator('body').evaluate("() => window.dataviz.control.state('dashboard:holiday/factor').value") == 20
        assert len(runs) == 2
        page.go_back()
        expect(annual).to_have_attribute("aria-current", "page")
        expect(frame.locator('[data-view-id="table"]')).to_contain_text("2025", timeout=30_000)
        assert len(runs) == 2

        # Editing an inactive Page marks only that Page outdated, without
        # querying or replacing the currently visible Canvas.
        active_frame_id = page.locator("#canvas-frame").get_attribute("data-frame-id")
        history_code = dashboard / "history.py"
        history_code.write_text(history_code.read_text() + "\n# history-only change\n")
        expect(history).to_contain_text("Outdated", timeout=10_000)
        expect(annual).not_to_contain_text("Outdated")
        expect(page.locator("#canvas-frame")).to_have_attribute("data-frame-id", active_frame_id)
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready")
        assert len(runs) == 2
        history.click()
        expect(page.locator("#query-diagnostics-label")).to_have_text("Outdated")
        expect(frame.locator("body")).to_contain_text("QUERY RUN OUTDATED", timeout=10_000)
        assert "#page=history" in page.url
        page.locator("#run-button").click()
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready", timeout=30_000)
        assert len(runs) == 3

        # Reload the active Page's presentation, keeping its identity and
        # parameters (the default Page uses an incompatible scalar type).
        definition_path = dashboard / "dashboard.yaml"
        definition = yaml.safe_load(definition_path.read_text())
        definition["pages"][1]["views"][0]["title"] = "Updated history table"
        definition_path.write_text(yaml.safe_dump(definition))
        expect(page.locator("#workspace-update-title")).to_have_text("Canvas reloaded", timeout=10_000)
        expect(history).to_have_attribute("aria-current", "page")
        expect(page.locator('#parameter-form input[name="year"]')).to_have_value("[2023,2024]")
        expect(frame.locator('[data-view-id="table"]')).to_contain_text("Updated history table", timeout=10_000)
        assert len(runs) == 3

        # Navigation-only refresh must not replace the selected Page's detail
        # metadata with the default Page returned by /api/workspace.
        other = root / "dashboards" / "other"
        other.mkdir()
        (other / "rules.py").write_text("def load(context):\n    return {'main': []}\n")
        (other / "dashboard.yaml").write_text(yaml.safe_dump({
            "schema": DASHBOARD_SCHEMA, "id": "other", "title": "Other",
            "sources": [{"id": "data", "type": "python", "code": "rules.py", "outputs": {"main": {"kind": "table"}}}],
            "views": [{"id": "table", "template": "table", "input": "source:data/main"}],
        }))
        expect(page.locator('.nav-button[data-id="other"]')).to_be_visible(timeout=10_000)
        expect(history).to_have_attribute("aria-current", "page")
        expect(page.locator('#parameter-form input[name="year"]')).to_have_value("[2023,2024]")
        assert len(runs) == 3
        page.locator("#run-button").click()
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready", timeout=30_000)
        assert len(runs) == 4 and runs[-1]["page_id"] == "history"
        page.reload()
        expect(history).to_have_attribute("aria-current", "page")
        expect(frame.locator('[data-view-id="table"]')).to_contain_text("Updated history table", timeout=30_000)
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready")
        expect(history).not_to_contain_text("Outdated")
        assert len(runs) == 4

        page.locator('#query-parameters-toggle').click(button="right")
        editor = page.locator('#parameter-editor-dialog')
        expect(editor).to_be_visible()
        item = editor.locator('[data-editor-item="year"]')
        item.locator('[data-editor-disclosure]').click()
        expect(item.locator('[data-editor-multiple-value]')).to_have_count(2)
        item.locator('[data-editor-multiple-value]').first.fill("2022")
        editor.get_by_role('button', name='Save', exact=True).click()
        expect(editor).to_be_hidden()
        expect(history).to_have_attribute('aria-current', 'page')
        changed = yaml.safe_load(definition_path.read_text())
        assert changed['pages'][0]['query_parameters'][0]['default'] == 2025
        assert changed['pages'][1]['query_parameters'][0]['default'] == [2022, 2024]
        assert 'query_parameters' not in changed
        assert len(runs) == 4
