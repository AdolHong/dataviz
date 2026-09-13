from __future__ import annotations



import re


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


from dataviz.cli import _copy_gallery_workspace




from e2e.support.runtime import (
    _running_server,
    _running_static_server,
    _open_dashboard,
    _run_and_wait,
    _export_html,
)

from contextlib import contextmanager


@contextmanager
def _gallery_surface(page, tmp_path, surface):
    workspace = _copy_gallery_workspace(tmp_path)
    visual_path = workspace / 'dashboards/component-gallery/presentation.yaml'
    visual = yaml.safe_load(visual_path.read_text())
    visual.setdefault('control_panels', {}).update({'section': {'placement': 'popover'}, 'view': {'placement': 'popover'}})
    visual_path.write_text(yaml.safe_dump(visual, allow_unicode=True))
    dashboard_path = workspace / "dashboards" / "component-gallery" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"].append(
        {
            "id": "unbounded-note",
            "type": "single_input",
            "value_type": "text",
            "label": "Unbounded note",
            "default": "No bare count",
        }
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    presentation_path = workspace / "dashboards" / "component-gallery" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation["control_components"]["dashboard:component-gallery/unbounded-note"] = {
        "component": "input",
        "show_count": True,
    }
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    with _running_server(workspace) as base_url, _running_static_server(tmp_path) as static_url:
        _open_dashboard(page, base_url, "component-gallery")
        _run_and_wait(page)
        if surface == 'share':
            page.locator('#share-button').click()
            with page.expect_response(lambda response: response.url.endswith('/component-gallery/share')) as response:
                page.locator('#copy-share-link').click()
            page.goto(base_url + response.value.json()['url'])
        elif surface == 'html':
            with page.expect_download() as download:
                _export_html(page)
            report = tmp_path / 'component-gallery.html'
            download.value.save_as(report)
            page.goto(static_url + '/' + report.name)
        frame = page.frame_locator("#canvas-frame") if surface == 'server' else page
        detail = frame.locator('[data-view-id="detail-table"]')
        expect(detail).to_have_attribute("data-view-status", "ready", timeout=20_000)

        yield frame


@pytest.mark.e2e
def test_component_gallery_story_overlay_keyboard_a11y_and_virtual_dom(page: Page, tmp_path: Path):
    # Component behavior runs once; the portable test checks packaging/state
    # without replaying every form interaction on three hosting surfaces.
    surface = 'server'
    with _gallery_surface(page, tmp_path, surface) as frame:
        detail = frame.locator('[data-view-id="detail-table"]')
        owner_contract = frame.locator("body").evaluate(
            """() => ({
              runtime: window.datavizRuntime.protocol,
              data: window.datavizRuntime.dataPipeline?.protocol,
              view: window.datavizRuntime.viewAdapter?.protocol,
              section: window.datavizRuntime.sectionAdapter?.protocol,
              presentation: window.datavizRuntime.presentationAdapter?.protocol,
              packages: [...(window.datavizComponents?.adapters?.keys() || [])],
            })"""
        )
        assert {
            owner_contract[key] for key in ("runtime", "data", "view", "section", "presentation")
        } == {"dataviz/runtime/v15"}
        assert {
            "data.pipeline",
            "view.declarative",
            "section.declarative",
            "presentation.shell",
        } <= set(owner_contract["packages"])

        header = page.locator("#dashboard-controls-control" if surface == 'server' else '.dv-context-sidebar')
        page.locator("#dashboard-controls-toggle" if surface == 'server'
                     else '.dv-runtime-control[data-control-origin="dashboard"] > summary').click()

        text_control = header.locator(
            '[data-control-component="input"]',
            has=page.locator('input[data-control-state-input="dashboard:component-gallery/analyst-note"]'),
        )
        expect(text_control.locator("input")).to_have_value("Review the selected cohort")
        text_control.locator("input").fill("Review East cohort")
        expect(text_control.locator(".dv-input__count")).to_contain_text("18 / 120")
        text_input_visuals = text_control.locator(".dv-input__control").evaluate(
            """input => {
              const style = getComputedStyle(input);
              return {borderStyle:style.borderStyle, borderRadius:style.borderRadius};
            }"""
        )
        assert text_input_visuals == {"borderStyle": "none", "borderRadius": "0px"}
        unbounded_text = header.locator(
            '[data-control-component="input"]',
            has=page.locator('input[data-control-state-input="dashboard:component-gallery/unbounded-note"]'),
        )
        expect(unbounded_text.locator(".dv-input__count")).to_be_hidden()

        auto_complete = header.locator('[data-control-component="auto-complete"]')
        auto_input = auto_complete.locator("input")
        auto_input.focus()
        auto_input.fill("up")
        expect(auto_complete.locator('[role="listbox"]')).to_be_visible()
        auto_complete.get_by_role("option", name="Upside").click()
        expect(auto_input).to_have_value("Upside")

        input_number = header.locator('[data-control-component="input-number"]')
        number_input_visuals = input_number.evaluate(
            """control => {
              const input = control.querySelector('.dv-input-number__control');
              const style = getComputedStyle(input);
              return {
                borderStyle:style.borderStyle,
                borderRadius:style.borderRadius,
                hiddenAffixes:[...control.querySelectorAll('.dv-input-number__affix[hidden]')]
                  .map(node => getComputedStyle(node).display),
              };
            }"""
        )
        assert number_input_visuals == {
            "borderStyle": "none",
            "borderRadius": "0px",
            "hiddenAffixes": ["none", "none"],
        }
        input_number.get_by_role("button", name="Increase value").click()
        expect(input_number.locator('input[type="number"]')).to_have_value("60")

        boolean_checkbox = header.locator('[data-control-component="checkbox"]')
        boolean_checkbox.locator('input[type="checkbox"]').check()
        expect(boolean_checkbox.locator('input[type="checkbox"]')).to_be_checked()

        switch = header.locator('[data-control-component="switch"]')
        switch.get_by_role("switch").click()
        expect(switch.get_by_role("switch")).to_have_attribute("aria-checked", "false")

        date_picker = header.locator('[data-control-component="date-picker"]')
        date_input = date_picker.locator('.dv-date-picker__control[type="text"]')
        expect(date_input).to_have_value(re.compile(r"^\d{4}-\d{2}-\d{2}$"))
        # Reproduce focus moving to text before the opening RAF runs. Pending
        # calendar focus must not steal it and expose the draft to snapshots.
        pending_focus = date_picker.evaluate('''async control => {
          const input = control.querySelector('.dv-date-picker__control');
          input.focus();
          control.querySelector('[data-control-trigger]').click();
          input.value = '2026-02-31';
          input.dispatchEvent(new Event('input', {bubbles:true}));
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          return {focused:document.activeElement === input, value:input.value, invalid:input.getAttribute('aria-invalid')};
        }''')
        assert pending_focus == {'focused': True, 'value': '2026-02-31', 'invalid': 'true'}
        date_panel = date_picker.locator("[data-control-panel]")
        expect(date_panel).to_be_visible()
        expect(date_panel.locator(".dv-date-range__month")).to_have_count(1)
        date_input.fill("2026-02-31")
        expect(date_input).to_have_value("2026-02-31")
        expect(date_input).to_have_attribute("aria-invalid", "true")
        date_input.fill("2026-03-02")
        date_input.press("Enter")
        expect(date_input).to_have_value("2026-03-02")
        expect(date_input).to_have_attribute("aria-invalid", "false")
        if date_panel.is_visible():
            date_picker.locator("[data-control-trigger]").click()
        expect(date_panel).to_be_hidden()

        slider = header.locator(
            'input[type="range"][data-control-state-input="dashboard:component-gallery/confidence"]'
        )
        slider.fill("0.85")
        expect(slider.locator("xpath=..").locator(".dv-slider__input")).to_have_value("0.85")

        band = header.locator('.dv-slider--range')
        expect(band.locator('.dv-slider__track').first).to_have_value('0.25')
        expect(band.locator('.dv-slider__track').last).to_have_value('0.75')
        band.locator('.dv-slider__input').first.fill('0.3')
        expect(band.locator('.dv-slider__track').first).to_have_value('0.3')
        band.locator('.dv-slider__track').last.fill('0.9')
        expect(band.locator('.dv-slider__input').last).to_have_value('0.9')
        values = header.locator('[data-control-component="multiple-input"]')
        values.get_by_role('button', name='+ Add value', exact=True).click()
        values.locator('[data-multiple-value]').last.fill('extra')
        expect(values.locator('[data-multiple-value]')).to_have_count(3)
        values.get_by_role('button', name='Remove value').last.click()
        expect(values.locator('[data-multiple-value]')).to_have_count(2)

        checkbox = header.locator('[data-control-component="checkbox-group"]')
        expect(checkbox).to_be_visible()
        expect(checkbox.locator(".dv-checkbox-group__toolbar")).to_have_count(0)
        options = checkbox.locator(".dv-checkbox-option")
        expect(options).to_have_count(3)
        expect(checkbox.locator("select option:checked")).to_have_count(3)
        def await_region_count(count):
            page.wait_for_function(
                "count => document.querySelector('#canvas-frame').contentWindow"
                ".dataviz.control.state('dashboard:component-gallery/region').value.length === count",
                arg=count,
            )
            expect(checkbox.locator('select option:checked')).to_have_count(count)

        options.nth(0).click()
        await_region_count(2)
        options.nth(0).click()
        await_region_count(3)
        # Clear/restore mechanics and detached-button regression live in the
        # isolated checkbox test. This Gallery is sequential integration, not
        # a timed burst; downstream inferred domains need the committed state.
        page.keyboard.press("Escape")
        expect(header).to_be_hidden()

        story_index = frame.locator(".gallery-story-index")
        expect(story_index).to_be_visible()
        expect(story_index.locator("summary")).to_contain_text("38 runtime specimens")

        expected_states = {
            "ready",
            "loading",
            "stale",
            "empty",
            "error",
            "cancelled",
            "unavailable",
        }
        for family in ("control", "view", "section"):
            matrix = frame.locator(f"#story-{family}-state-matrix")
            expect(matrix).to_be_visible()
            expect(matrix.locator(".gallery-state-card")).to_have_count(7)
            observed = set(
                matrix.locator(".gallery-state-card").evaluate_all(
                    "cards => cards.map(card => card.dataset.componentStatus)"
                )
            )
            assert observed == expected_states
            expect(
                matrix.locator('.gallery-state-card[data-gallery-status="loading"]')
            ).to_have_attribute("aria-busy", "true")
            expect(
                matrix.locator('.gallery-state-card[data-gallery-status="error"]')
            ).to_have_attribute("aria-invalid", "true")
            expect(
                matrix.locator('.gallery-state-card[data-gallery-status="unavailable"]')
            ).to_have_attribute("aria-disabled", "true")

        selections = detail.locator('.dv-context-controls[data-control-origin="view"]')
        selections.locator("summary").click()
        expect(selections).to_have_attribute("open", "")
        tree = selections.locator('[data-control-component="tree-select"]')
        expect(tree.locator("xpath=ancestor::*[@data-control-key][1]")).to_have_attribute(
            "data-option-domain-state", "ready"
        )
        tree.locator("[data-control-trigger]").click()
        panel = tree.locator("[data-control-panel]")
        expect(panel).to_be_visible()
        geometry = panel.evaluate(
            """panel => {
              const rect = panel.getBoundingClientRect();
              return {
                left:rect.left, top:rect.top, right:rect.right, bottom:rect.bottom,
                width:rect.width, height:rect.height,
                viewport:[document.documentElement.clientWidth, document.documentElement.clientHeight],
              };
            }"""
        )
        assert geometry["left"] >= 8
        assert geometry["top"] >= 8
        assert geometry["right"] <= geometry["viewport"][0] - 8
        assert geometry["bottom"] <= geometry["viewport"][1] - 8
        assert geometry["width"] >= 320

        tree.locator(".dv-choice-search").press("Escape")
        expect(panel).to_be_hidden()
        assert tree.locator("[data-control-trigger]").evaluate(
            "trigger => document.activeElement === trigger"
        )
        tree.locator("[data-control-trigger]").click()
        tree_debug = tree.evaluate(
            """control => ({
              strategy:control.dataset.selectionStrategy,
              levels:control.dataset.cascaderLevels,
              nativeOptions:[...control.querySelector('select').options].map(option => option.value),
              treeItems:control.querySelectorAll('.dv-tree-option').length,
            })"""
        )
        assert tree.locator(".dv-tree-branch__check").count() > 0, tree_debug
        tree_branch = tree.locator(".dv-tree-branch__check").first
        tree_branch.click()
        assert tree.locator("select").evaluate("select => select.selectedOptions.length > 0")
        tree_summary = tree.locator("[data-control-summary]")
        expect(tree_summary).to_have_text(re.compile(r"\S"))
        # Selecting the only available parent is canonically "all available";
        # otherwise show_checked_strategy=parent emits compact parent tags. Both
        # summaries must avoid leaking full leaf paths into the trigger.
        assert " / " not in tree_summary.inner_text()
        tree.locator("footer button", has_text="Clear").click()
        assert tree.locator("select").evaluate("select => select.selectedOptions.length") == 0
        tree.locator(".dv-choice-search").press("Escape")

        radio = selections.locator('[data-control-component="radio-group"]')
        expect(radio.get_by_role("button", name="All", exact=True)).to_have_count(0)
        expect(radio.get_by_role("button", name="Clear", exact=True)).to_have_count(0)
        radio.locator("button", has_text="Software").press("Enter")
        expect(radio.locator("select")).to_have_value("Software")

        grouped_select = selections.locator(
            '[data-control-key="view:detail-table/product"] [data-control-component="select"]'
        )
        grouped_select.locator("[data-control-trigger]").click()
        select_panel = grouped_select.locator(".dv-select-panel")
        expect(select_panel).to_be_visible()
        panel_surface = select_panel.evaluate(
            """panel => ({
              sharedClass: panel.classList.contains('dv-control-panel'),
              background: getComputedStyle(panel).backgroundColor,
            })"""
        )
        assert panel_surface["sharedClass"] is True
        assert panel_surface["background"] not in {"transparent", "rgba(0, 0, 0, 0)"}
        assert grouped_select.locator(".dv-select-group").all_text_contents() == ["Core", "New"]
        grouped_select.locator(".dv-choice-search").fill("Growth")
        expect(grouped_select.locator("footer small")).to_contain_text("2 matching")
        grouped_action = grouped_select.locator(".dv-select-footer__actions button").first
        expect(grouped_action).to_have_text("Select results")
        grouped_action.click()
        assert (
            grouped_select.locator("select").evaluate("select => select.selectedOptions.length")
            == 2
        )
        expect(grouped_action).to_have_text("Select results")
        expect(grouped_action).to_be_disabled()
        expect(grouped_select.get_by_role("button", name="Revert")).to_have_count(0)
        grouped_select.get_by_role("button", name="Clear results", exact=True).click()
        assert (
            grouped_select.locator("select").evaluate("select => select.selectedOptions.length")
            == 0
        )
        grouped_select.locator(".dv-choice-search").fill("")
        grouped_select.locator(".dv-choice-option").first.click()
        expect(grouped_select.locator("[data-control-summary]")).to_have_text("Atlas")
        expect(grouped_select.locator(".dv-choice-summary__tag")).to_have_count(0)
        grouped_select.get_by_role("button", name="Clear", exact=True).click()
        expect(grouped_select.locator("select")).to_have_values([])
        long_label = "这是一个需要完整阅读的超长商品名称" * 12
        grouped_select.locator("select option").first.evaluate(
            "(option, label) => { option.textContent = label; }",
            long_label,
        )
        grouped_select.evaluate("control => control._syncControl?.()")
        long_row = grouped_select.locator(".dv-choice-option").first
        expect(long_row).to_have_attribute("title", re.compile(long_label[:20]))
        long_label_layout = long_row.evaluate(
            """row => {
              const label = row.querySelector('strong');
              const panel = row.closest('.dv-select-panel');
              const panelRect = panel.getBoundingClientRect();
              return {
                whiteSpace:getComputedStyle(label).whiteSpace,
                rowHeight:row.getBoundingClientRect().height,
                panelWidth:panelRect.width,
                panelRight:panelRect.right,
                viewportWidth:document.documentElement.clientWidth,
              };
            }"""
        )
        assert long_label_layout["whiteSpace"] == "normal"
        assert long_label_layout["rowHeight"] > 38
        assert long_label_layout["panelWidth"] >= 600
        assert long_label_layout["panelRight"] <= long_label_layout["viewportWidth"] - 8
        grouped_select.locator("select").evaluate(
            """(select, label) => {
              [...select.options].slice(0, 3).forEach((option, index) => {
                option.selected = true;
                option.textContent = `${label} ${index + 1}`;
              });
            }""",
            long_label,
        )
        grouped_select.evaluate("control => control._syncControl?.()")
        summary_geometry = grouped_select.locator("[data-control-trigger]").evaluate(
            """trigger => {
              const bounds = trigger.getBoundingClientRect();
              const tags = [...trigger.querySelectorAll('.dv-choice-summary__tag')];
              const rest = trigger.querySelector('.dv-choice-summary__rest');
              return {
                height:bounds.height,
                overflow:getComputedStyle(trigger).overflow,
                wrap:getComputedStyle(trigger.querySelector('[data-control-summary]')).flexWrap,
                tags:tags.map(tag => {
                  const rect = tag.getBoundingClientRect();
                  return {top:rect.top, bottom:rect.bottom, title:tag.title};
                }),
                restVisible:Boolean(rest && rest.getBoundingClientRect().width > 0),
                contained:tags.every(tag => {
                  const rect = tag.getBoundingClientRect();
                  return rect.top >= bounds.top && rect.bottom <= bounds.bottom;
                }),
              };
            }"""
        )
        assert 40 <= summary_geometry["height"] <= 42
        assert summary_geometry["overflow"] == "hidden"
        assert summary_geometry["wrap"] == "nowrap"
        assert summary_geometry["contained"] is True
        assert summary_geometry["restVisible"] is True
        assert all(item["title"].startswith(long_label) for item in summary_geometry["tags"])
        grouped_select.locator(".dv-choice-search").press("Escape")

        cascader = selections.locator('[data-control-component="cascader"]')
        cascader.locator("[data-control-trigger]").click()
        branch_check = cascader.locator(".dv-cascader-branch__check").first
        expect(branch_check).to_be_visible()
        branch_check.click()
        assert cascader.locator("select").evaluate("select => select.selectedOptions.length > 0")
        cascader_summary = cascader.locator("[data-control-summary]")
        expect(cascader_summary).to_have_text(re.compile(r"\S"))
        assert " / " not in cascader_summary.inner_text()
        cascader.locator(".dv-choice-search").press("Escape")

        range_picker = selections.locator('[data-control-component="range-picker"]')
        expect(range_picker.locator("[data-control-trigger]")).to_have_count(1)
        expect(range_picker.locator('input[type="date"]')).to_have_count(0)
        expect(range_picker.locator('.dv-date-range__endpoint[type="text"]')).to_have_count(2)
        range_picker.locator("[data-control-trigger]").click()
        date_panel = range_picker.locator("[data-control-panel]")
        expect(date_panel).to_be_visible()
        expect(date_panel).to_have_attribute("role", "dialog")
        expect(date_panel.locator(".dv-date-range__month")).to_have_count(2)
        range_picker.locator("button", has_text="Q1 2026").click()
        expect(range_picker.locator("input[data-control-input]")).to_have_value(
            "2026-01-01,2026-03-31"
        )
        expect(date_panel).to_be_hidden()
        endpoints = range_picker.locator(".dv-date-range__endpoint")
        endpoints.nth(0).fill("2026-01-05")
        endpoints.nth(1).fill("2026-01-12")
        endpoints.nth(1).press("Enter")
        expect(range_picker.locator("input[data-control-input]")).to_have_value(
            "2026-01-05,2026-01-12"
        )
        range_picker.locator("[data-control-trigger]").click()
        date_panel.locator('[data-date="2026-01-10"]').click()
        expect(date_panel).to_be_visible()
        date_panel.locator('[data-date="2026-01-20"]').click()
        expect(range_picker.locator("input[data-control-input]")).to_have_value(
            "2026-01-10,2026-01-20"
        )
        expect(date_panel).to_be_hidden()
        range_picker.locator("[data-control-trigger]").click()
        range_picker.locator("button", has_text="Clear").click()
        expect(range_picker.locator("input[data-control-input]")).to_have_value("")
        frame.locator("body").evaluate(
            """() => new Promise((resolve, reject) => {
              const deadline = performance.now() + 3000;
              const check = () => {
                const state = window.dataviz.control.state('view:detail-table/date-window');
                if (state.value.length === 0) return resolve();
                if (performance.now() > deadline) return reject(new Error(JSON.stringify(state)));
                setTimeout(check, 25);
              };
              check();
            })"""
        )
        expect(detail.locator("tbody tr")).to_have_count(8)

        # The Gallery owns three real scale Stories. The 1,000-option Story uses
        # a canonical native select while keeping the enhanced row DOM bounded.
        expect(frame.locator("#story-control-scale-10 select option")).to_have_count(10)
        expect(frame.locator("#story-control-scale-100 select option")).to_have_count(100)
        expect(frame.locator("#story-control-scale-1000 select option")).to_have_count(1000)
        virtual = frame.locator("#story-control-scale-1000 .dv-control")
        virtual.locator("[data-control-trigger]").click()
        expect(virtual.locator("[data-control-panel]")).to_be_visible()
        rendered = virtual.locator(".dv-select-rows .dv-choice-option").count()
        assert 1 <= rendered < 40
        virtual_row = virtual.locator(".dv-choice-option").first
        expect(virtual_row).not_to_have_attribute("title", "")
        assert virtual_row.locator("strong").evaluate(
            "label => getComputedStyle(label).whiteSpace"
        ) == "nowrap"
        virtual.locator(".dv-choice-search").fill("Store 1000")
        expect(virtual.locator(".dv-select-panel footer small")).to_contain_text("1 matching")
        assert virtual.locator(".dv-select-rows .dv-choice-option").count() == 1
        virtual.locator(".dv-choice-search").press("ArrowDown")
        virtual.locator(".dv-select-options").press("Enter")
        expect(virtual.locator("select")).to_have_values(["1000"])
        assert virtual.locator("[data-control-trigger]").evaluate(
            """trigger => {
              const panel = document.getElementById(trigger.getAttribute('aria-controls'));
              return Boolean(trigger.getAttribute('aria-haspopup') === 'listbox'
                && trigger.getAttribute('aria-expanded') === 'true'
                && panel?.getAttribute('role') === null
                && panel?.querySelector('[role="listbox"]'));
            }"""
        )

        # Context Overlay uses the same outside-click controller.
        frame.locator(".dv-section--band").click(position={"x": 10, "y": 10})
        expect(selections).not_to_have_attribute("open", "")

        contract = frame.locator("body").evaluate(
            """async () => window.datavizRuntime.testRenderer('gallery.spark', [
              {type:'gallery.spark', rows:[{revenue:1, store_id:'S01', month:'2026-01'}]},
              {type:'gallery.spark', rows:[]},
            ])"""
        )
        assert contract["valid"] is True
        assert contract["lifecycle"] == {"mounts": 2, "updates": 2, "disposes": 2}
        assert contract["warnings"] == []
        lifecycle = frame.locator("body").evaluate(
            """() => ({
              lifecycle:window.datavizRuntime.rendererLifecycleEvidence.get('custom-specimen'),
              renderer:window.datavizRuntime.viewRenderEvidence.get('custom-specimen'),
            })"""
        )
        assert lifecycle["lifecycle"]["custom"] is True
        assert lifecycle["lifecycle"]["mounts"] >= 1
        assert lifecycle["lifecycle"]["active"] is True
        assert lifecycle["lifecycle"]["diagnostics"] == []
        assert lifecycle["renderer"]["inputs"]["main"]["rows"] > 0
        assert lifecycle["renderer"]["inputs"]["main"]["bytes"] > 0
        leaky = frame.locator("body").evaluate(
            """async () => {
              window.datavizRuntime.registerRenderer('test.leaky', {
                mount(context) {
                  const node = document.createElement('div');
                  context.body.append(node);
                  return {node};
                },
                update(_context, _descriptor, state) { return state; },
                dispose() {},
              });
              return window.datavizRuntime.testRenderer('test.leaky', [
                {type:'test.leaky', rows:[{value:1}]},
              ]);
            }"""
        )
        assert leaky["valid"] is False
        assert leaky["failures"][0]["phase"] == "dispose"
        assert "left 1 DOM root" in leaky["failures"][0]["message"]

        # A lifecycle failure stays in its View and exposes a structured boundary.
        frame.locator("body").evaluate(
            """() => {
              window.datavizRuntime.renderers.get('gallery.spark').update = () => {
                throw new Error('expected renderer failure');
              };
            }"""
        )
        page.locator('select[data-control-state-input="dashboard:component-gallery/region"]'
                     if surface != 'server' else 'select[name="dashboard:component-gallery/region"]').select_option(
            ["East"], force=True
        )
        custom = frame.locator('[data-view-id="custom-specimen"]')
        expect(custom).to_have_attribute("data-view-status", "error", timeout=10_000)
        boundary = frame.locator("body").evaluate(
            """() => window.datavizRuntime.rendererErrors.get('custom-specimen')"""
        )
        assert boundary["code"] == "renderer_lifecycle_error"
        assert boundary["phase"] == "update"
        assert boundary["renderer"] == "gallery.spark"
        expect(frame.locator('[data-view-id="narrative"]')).to_have_attribute(
            "data-view-status", "ready"
        )



@pytest.mark.e2e
@pytest.mark.parametrize('surface', ['share', 'html'])
def test_component_gallery_portable_hydration_and_selection(page: Page, tmp_path: Path, surface):
    with _gallery_surface(page, tmp_path, surface) as frame:
        # Every declared component must have its actual adapter in the bundle.
        contract = frame.locator('body').evaluate("""() => ({
          missing:[...document.querySelectorAll('[data-control-component]')]
            .filter(n => n.dataset.controlHydrated !== 'true')
            .map(n => n.dataset.controlComponent),
          custom:window.datavizRuntime.rendererLifecycleEvidence.get('custom-specimen'),
        })""")
        assert contract['missing'] == []
        assert contract['custom']['active'] is True
        assert contract['custom']['diagnostics'] == []
        page.locator('.dv-runtime-control[data-control-origin="dashboard"] > summary').click()
        sidebar = page.locator('.dv-context-sidebar')
        expect(sidebar).to_be_visible()
        checkbox = sidebar.locator('[data-control-component="checkbox-group"]')
        expect(checkbox.locator('select option:checked')).to_have_count(3)
        checkbox.locator('.dv-checkbox-option').first.click()
        expect(checkbox.locator('select option:checked')).to_have_count(2)
        page.wait_for_function("""() => {
          const state = window.dataviz.control.state('dashboard:component-gallery/region');
          return state.value.length === 2 && !state.value.includes('East');
        }""")
        detail = frame.locator('[data-view-id="detail-table"]')
        expect(detail).to_have_attribute('data-view-status', 'ready')
        expect(frame.locator('[data-view-id="custom-specimen"]')).to_have_attribute('data-view-status', 'ready')
        expect(frame.locator('#story-control-scale-1000 option')).to_have_count(1000)
        page.keyboard.press('Escape')
        expect(sidebar).to_be_hidden()
