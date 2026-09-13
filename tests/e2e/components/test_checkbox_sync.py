"""Control snapshots must not interrupt an in-flight user gesture."""
import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

MARKUP = '''<div class="dv-control" data-control-component="checkbox-group" data-clearable="true">
  <select data-control-input multiple style="display:none">
    <option value="gd">广东</option><option value="fj" selected>福建</option>
  </select><div data-control-mount></div></div>'''


@pytest.mark.parametrize('gesture', ['pointer', 'space'])
def test_checkbox_sync_preserves_inflight_gesture(control_page, gesture):
    page = control_page('control.checkbox-group', MARKUP)
    button = page.locator('.dv-checkbox-option[data-value="gd"]')
    page.evaluate('''() => {
      window.changes = 0;
      document.querySelector('select').addEventListener('change', () => window.changes++);
    }''')
    if gesture == 'pointer':
        box = button.bounding_box()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        page.mouse.down()
    else:
        button.focus()
        page.keyboard.down('Space')
    # The host syncs choice controls when a snapshot arrives, even when its
    # options/values are unchanged. Inject that exact seam during activation.
    page.evaluate("() => document.querySelector('select')._syncChoiceControl()")
    if gesture == 'pointer':
        page.mouse.up()
    else:
        page.keyboard.up('Space')
    expect(page.locator('select')).to_have_values(['gd', 'fj'])
    expect(button).to_have_attribute('aria-pressed', 'true')
    assert page.evaluate('window.changes') == 1
    if gesture == 'space':
        expect(button).to_be_focused()


def test_checkbox_sync_reconciles_replaced_options_and_constraints(control_page):
    page = control_page('control.checkbox-group', MARKUP.replace(
        'data-clearable="true"', 'data-clearable="false" data-max-selected="1"'))
    gd = page.locator('.dv-checkbox-option[data-value="gd"]')
    fj = page.locator('.dv-checkbox-option[data-value="fj"]')
    expect(gd).to_be_disabled()  # Selection cap, not a disabled candidate.
    fj.click()
    expect(page.locator('select')).to_have_values(['fj'])  # Required last value.
    page.evaluate('''() => {
      window.originalFj = document.querySelector('[data-value="fj"]');
      const input = document.querySelector('select');
      input.innerHTML = '<option value="fj">福建更新</option>'
        + '<option value="gd" disabled>广东</option><option value="new">新增</option>';
      input._syncChoiceControl();
    }''')
    expect(page.locator('.dv-checkbox-option')).to_have_text(['福建更新', '新增'])
    assert fj.evaluate('node => node === window.originalFj')
    fj.click()  # Must modify the new option, not a detached captured option.
    expect(page.locator('select')).to_have_values(['fj'])
    expect(page.locator('[data-value="new"]')).to_be_disabled()
    page.evaluate('''() => {
      const input = document.querySelector('select');
      input.disabled = true;
      input._syncChoiceControl();
    }''')
    expect(fj).to_be_disabled()
    page.evaluate('''() => {
      const input = document.querySelector('select');
      input.disabled = false;
      input.innerHTML = '<option value="new">新增</option><option value="fj" selected>福建更新</option>';
      input._syncChoiceControl();
    }''')
    expect(page.locator('.dv-checkbox-option')).to_have_text(['新增', '✓福建更新'])
    assert fj.evaluate('node => node === window.originalFj')
