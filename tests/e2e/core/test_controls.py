from __future__ import annotations


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
    _open_single_fixture_dashboard,
    _open_dashboard,
    _run_and_wait,
    MINIMAL,
)

@pytest.mark.e2e
@pytest.mark.parametrize("domain_result", ["ready", "empty", "error"])
def test_server_compute_waits_for_required_control_domain(page: Page, tmp_path: Path, domain_result: str):
    from dataviz.standalone import prepare_input

    source = tmp_path / "readiness.yaml"
    ending = ("raise RuntimeError('category domain failed')" if domain_result == "error" else
              "return [{'category': 'A'}]" if domain_result == "ready" else
              "return pd.DataFrame(columns=['category'])")
    source.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "readiness", "title": "Readiness",
        "controls": [{"id": "category", "label": "Category", "type": "single_select", "value_type": "text",
                      "field": "category", "required": True, "clearable": False, "initial": {"mode": "first"},
                      "options": {"mode": "infer", "source": "source:categories/main"}}],
        "sources": [
            {"id": "rows", "type": "python", "code": {"inline": "def load(context):\n    return [{'value': 42}]\n"},
             "outputs": {"main": {"kind": "table"}}},
            {"id": "categories", "type": "python", "code": {"inline":
                "import time\nimport pandas as pd\ndef load(context):\n"
                "    deadline = time.monotonic() + 25\n"
                "    while not (context.dashboard_root / 'release').exists():\n"
                "        if time.monotonic() > deadline: raise RuntimeError('test gate timed out')\n"
                "        time.sleep(.02)\n    " + ending + "\n"},
                 "outputs": {"main": {"kind": "table", "schema": [{"name": "category"}]}}},
        ],
        "interactive_transforms": [
            {"id": name, "runtime": "server-python", "trigger": "auto",
             "code": {"inline": "def transform(context):\n    return {'main': [{'value': 42}]}\n"},
             "inputs": {"rows": "source:rows/main"},
             "control_inputs": ({"category": {"mode": "value", "control": "dashboard.category"}} if name == "dependent" else {}),
             "outputs": {"main": {"kind": "table"}}, "export": {"mode": "snapshot"}}
            for name in ("free", "dependent")],
        "views": [{"id": name, "template": "table", "input": f"interactive:{name}/main"}
                  for name in ("free", "dependent")],
    }))
    root, _ = prepare_input(source)
    loaded = load_workspace(root).dashboard("readiness")
    calls, errors = [], []
    page.on("request", lambda request: calls.append(request.post_data_json)
            if request.method == "POST" and request.url.endswith("/interactions") else None)
    page.on("response", lambda response: errors.append(response.status)
            if "/interactions" in response.url and response.status >= 400 else None)
    with _running_server(root, watch=False) as url:
        _open_single_fixture_dashboard(page, url, root)
        page.locator('#run-button').click()
        frame = page.frame_locator('#canvas-frame')
        free = frame.locator('[data-view-id="free"]')
        dependent = frame.locator('[data-view-id="dependent"]')
        try:
            expect(free).to_contain_text("42", timeout=20_000)
            expect(dependent).to_have_attribute("data-view-status", "loading")
            assert calls and all(call["transform_id"] == "free" for call in calls), calls
        finally:
            (loaded.root / "release").touch()
        if domain_result == "ready":
            expect(dependent).to_contain_text("42", timeout=20_000)
            submitted = [call for call in calls if call["transform_id"] == "dependent"]
            assert submitted and all(call["control_state"]["dashboard:readiness/category"]["value"] == "A" for call in submitted)
        else:
            expect(dependent).to_have_attribute("data-view-status", "empty" if domain_result == "empty" else "error", timeout=20_000)
            assert not any(call["transform_id"] == "dependent" for call in calls), calls
        assert errors == [], errors


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

