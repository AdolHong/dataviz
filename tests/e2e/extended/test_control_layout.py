from __future__ import annotations





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
    _open_dashboard,
    MINIMAL,
)

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

        geometry = page.locator('#operation-panel-body').evaluate(
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
        assert geometry["left"] >= 0, geometry
        assert geometry["top"] >= 8, geometry
        assert geometry["right"] <= geometry["viewport"][0], geometry
        assert geometry["bottom"] <= geometry["viewport"][1], geometry
        assert geometry["columns"] == 1, geometry
        assert geometry["panelScrollHeight"] > geometry["panelClientHeight"], geometry
        assert geometry["panelOverflow"] == "auto", geometry

        page.locator('#operation-panel-body').evaluate("panel => { panel.scrollTop = panel.scrollHeight; }")
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
        # Narrow screens use a modal sidebar; clicking its backdrop dismisses it.
        expect(panel).to_be_hidden()
        toggle.click()
        expect(panel).to_be_visible()
        page.keyboard.press("Escape")
        expect(panel).to_be_hidden()
        expect(toggle).to_have_attribute("aria-expanded", "false")
        page.locator("#run-button").click()

