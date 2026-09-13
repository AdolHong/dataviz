from __future__ import annotations


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


from dataviz.protocols import DASHBOARD_SCHEMA


from e2e.support.runtime import (
    _running_server,
    _open_single_fixture_dashboard,
)

@pytest.mark.e2e
@pytest.mark.parametrize('has_fields', [True, False])
def test_operation_panel_shortcuts_and_responsive_state(page: Page, tmp_path: Path, has_fields: bool):
    from dataviz.standalone import prepare_input
    source = tmp_path / "panel.yaml"
    source.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "panel", "title": "Panel analysis",
        "query_parameters": [
            {"id": "label", "label": "Analysis label", "type": "single_input", "value_type": "text", "default": "applied"},
            {"id": "period", "label": "日期范围", "type": "range_input", "value_type": "date", "default": ["2026-09-01", "2026-09-11"]},
        ] if has_fields else [],
        "controls": [{"id": "factor", "label": "Factor", "type": "single_input", "value_type": "number", "default": 2}] if has_fields else [],
        "sources": [{"id": "rows", "type": "python", "code": {"inline": "def load(context):\n    return [{'value': 42}]\n"}, "outputs": {"main": {"kind": "table"}}}],
        "views": [{"id": "rows", "template": "table", "input": "source:rows/main"}],
    }))
    root, _ = prepare_input(source)
    runs = []
    page.on("request", lambda request: runs.append(request.url) if request.method == "POST" and request.url.endswith('/runs') else None)
    with _running_server(root, watch=False) as url:
        _open_single_fixture_dashboard(page, url, root)
        panel = page.locator('#operation-panel')
        if not has_fields:
            for selector in ['#query-parameters-toggle', '#dashboard-controls-toggle']:
                expect(page.locator(selector)).to_be_visible()
                expect(page.locator(selector)).to_be_disabled()
            page.keyboard.press('w')
            expect(page.locator('#shortcut-toast')).to_have_text('This Dashboard has no query parameters.')
            page.keyboard.press('e')
            expect(page.locator('#shortcut-toast')).to_have_text('This Dashboard has no dashboard controls.')
            expect(panel).to_be_hidden()
            assert not runs
            return
        expect(panel).to_be_visible()
        field = page.locator('#parameter-form input[name="label"]')
        expect(page.locator('#query-parameters-toggle')).to_have_text('Parameters')
        expect(page.locator('#dashboard-controls-toggle')).to_have_text('Controls')
        expect(page.locator('#operation-panel-title')).to_have_text('Parameters')
        waiting = page.frame_locator('#canvas-frame')
        waiting.locator('main').click()
        page.keyboard.press('w')
        expect(panel).to_be_hidden()
        waiting.locator('main').click()
        page.keyboard.press('w')
        expect(panel).to_be_visible()
        waiting.locator('main').click()
        page.keyboard.press('e')
        expect(page.locator('#operation-panel-title')).to_have_text('Controls')
        waiting.locator('main').click()
        page.keyboard.press('w')
        expect(field).to_be_visible()
        waiting.locator('main').click()
        page.keyboard.press('q')
        expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'false')
        waiting.locator('main').click()
        page.keyboard.press('q')
        expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'true')
        assert panel.bounding_box()['width'] == 320
        page.screenshot(path='/tmp/dataviz-query-width.png')
        assert page.locator('#parameter-form').evaluate('node => node.scrollWidth <= node.clientWidth')
        dates = page.locator('#parameter-form .dv-date-range__endpoint[type="text"]')
        expect(dates).to_have_count(2)
        expect(dates.nth(0)).to_have_value('2026-09-01')
        expect(dates.nth(1)).to_have_value('2026-09-11')
        assert dates.evaluate_all('nodes => nodes.every(node => node.scrollWidth <= node.clientWidth + 1)')
        assert page.locator('.workbench').evaluate('node => parseFloat(getComputedStyle(node).marginRight)') == 320
        field.fill('draft qc')
        field.press('q')
        expect(panel).to_be_visible()
        field.fill('draft')
        page.locator('#operation-panel-close').focus()
        page.keyboard.press('w')
        expect(panel).to_be_hidden()
        page.keyboard.press('w')
        expect(field).to_have_value('draft')
        page.keyboard.press('e')
        expect(page.locator('#operation-panel-title')).to_have_text('Controls')
        expect(page.locator('#operation-panel-close')).not_to_be_focused()
        expect(page.locator('#operation-panel-footer, #panel-run-button')).to_have_count(0)
        page.keyboard.press('e')
        expect(panel).to_be_hidden()
        page.keyboard.press('w')
        waiting.locator('main').click()
        page.keyboard.press('r')
        expect(page.frame_locator('#canvas-frame').locator('[data-view-id="rows"]')).to_contain_text('42', timeout=20_000)
        expect(panel).to_be_visible()
        expect(field).to_have_value('draft')
        assert len(runs) == 1
        expect(page.locator('#query-parameters-toggle kbd, #dashboard-controls-toggle kbd')).to_have_count(0)
        ready = page.frame_locator('#canvas-frame')
        ready.locator('[data-view-id="rows"]').click()
        page.keyboard.press('w')
        expect(panel).to_be_hidden()
        ready.locator('[data-view-id="rows"]').click()
        page.keyboard.press('w')
        expect(panel).to_be_visible()
        # The host must recognize editable elements from the iframe's realm.
        ready.locator('body').evaluate("""node => {
          const input = document.createElement('input');
          input.id = 'shortcut-typing-probe';
          node.prepend(input);
        }""")
        ready.locator('#shortcut-typing-probe').fill('')
        ready.locator('#shortcut-typing-probe').press('w')
        expect(ready.locator('#shortcut-typing-probe')).to_have_value('w')
        expect(panel).to_be_visible()
        ready.locator('#shortcut-typing-probe').evaluate('node => node.remove()')
        # Every explicit chord/alias is accepted; typing, IME and repeats are not.
        assert page.evaluate("""async () => {
          const source = await fetch('/static/app.js').then(response => response.text());
          const handlers = source.slice(source.indexOf('function keyboardTargetIsEditable('), source.indexOf('let shortcutToastTimer'));
          const classify = new Function('document', '$', handlers + ';return keyboardShortcutCommand;')(document, selector => document.querySelector(selector));
          const command = overrides => classify({key:'r', target:document.body, ...overrides});
          return ['q','w','e','r'].map(key => command({key})).concat([
            command({key:'R', ctrlKey:true, metaKey:true}),
            command({key:'Enter', metaKey:true}), command({key:'Enter', ctrlKey:true}),
            command({key:'End', ctrlKey:true}), command({key:'r', repeat:true}),
            command({key:'r', isComposing:true}), command({key:'r', altKey:true}),
            command({key:'r', target:document.querySelector('#parameter-form input')}),
            command({key:'c'}), command({key:'b'})]);
        }""") == ['toggle-sidebar', 'toggle-query-parameters', 'toggle-dashboard-controls', 'run-query'] + ['run-query'] * 4 + [None] * 6
        page.keyboard.press('q')
        expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'false')
        page.keyboard.press('q')
        expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'true')
        page.keyboard.press('?')
        help_dialog = page.locator('#keyboard-shortcuts-dialog')
        expect(help_dialog).to_be_visible()
        page.locator('#single-key-shortcuts').uncheck()
        expect(help_dialog.locator('[data-shortcut-key="W"]')).to_have_text('Cmd + Ctrl + W')
        page.screenshot(path='/tmp/dataviz-0244-shortcuts-desktop.png')
        page.keyboard.press('Escape')
        page.locator('#operation-panel-close').focus()
        page.keyboard.press('w')
        expect(panel).to_be_visible()
        page.keyboard.press('Meta+Control+w')
        expect(panel).to_be_hidden()
        # Canvas forwards modified shortcuts even with single-key mode disabled.
        frame = page.frame_locator('#canvas-frame')
        frame.locator('body').click(position={'x':5, 'y':5})
        page.keyboard.press('e')
        expect(panel).to_be_hidden()
        page.keyboard.press('Meta+Control+e')
        expect(page.locator('#operation-panel-title')).to_have_text('Controls')
        page.keyboard.press('?')
        expect(help_dialog).to_be_visible()
        page.set_viewport_size({'width':390, 'height':844})
        page.screenshot(path='/tmp/dataviz-0244-shortcuts-mobile.png')
        assert help_dialog.evaluate('node => node.scrollWidth <= node.clientWidth')
        page.locator('#single-key-shortcuts').check()
        page.keyboard.press('Escape')
        page.set_viewport_size({'width':1440, 'height':900})
        page.locator('#query-parameters-toggle').click()
        page.screenshot(path='/tmp/dataviz-operation-panel-desktop.png')
        page.locator('#dashboard-controls-toggle').click()
        expect(page.locator('#dashboard-control-form')).to_be_visible()
        control = page.locator('#dashboard-control-form input[name="dashboard:panel/factor"]')
        expect(control).to_be_visible()
        box = control.bounding_box()
        assert box['x'] >= panel.bounding_box()['x'] and box['y'] >= panel.bounding_box()['y'], page.locator('#dashboard-controls-control').evaluate('(node) => node.outerHTML')
        page.screenshot(path='/tmp/dataviz-operation-panel-controls.png')
        page.locator('#query-parameters-toggle').click()
        page.set_viewport_size({"width": 390, "height": 844})
        expect(panel).to_have_attribute('aria-modal', 'true')
        expect(page.locator('#operation-panel-close')).to_be_focused()
        expect(page.locator('.workbench')).to_have_attribute('inert', '')
        assert panel.bounding_box()['width'] <= 390
        page.screenshot(path='/tmp/dataviz-operation-panel-mobile.png')
        page.locator('#operation-panel-close').click()
        expect(panel).to_be_hidden()
        assert not page.locator('.workbench').evaluate('(node) => node.inert')
        page.locator('#query-parameters-toggle').click()
        expect(field).to_have_value('draft')
        page.keyboard.press('Escape')
        expect(panel).to_be_hidden()
        assert len(runs) == 1

