import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e
MARKUP = '''<div class="dv-control" data-control-component="radio-group">
<select data-control-input style="display:none"><option value="a">A</option>
<option value="b">B</option></select><div data-control-mount></div></div>'''


@pytest.mark.parametrize('gesture', ['pointer', 'space'])
def test_radio_activation_survives_snapshot(control_page, gesture):
    page = control_page('control.radio-group', MARKUP)
    target = page.get_by_role('radio', name='B', exact=True)
    if gesture == 'pointer':
        box = target.bounding_box()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        page.mouse.down()
    else:
        target.focus()
        page.keyboard.down('Space')
    page.evaluate("() => document.querySelector('select')._syncChoiceControl()")
    if gesture == 'pointer':
        page.mouse.up()
    else:
        page.keyboard.up('Space')
    expect(page.locator('select')).to_have_value('b')
    expect(target).to_be_focused()


def test_radio_keyboard_resolves_current_options(control_page):
    page = control_page('control.radio-group', MARKUP)
    target = page.get_by_role('radio', name='A', exact=True)
    target.focus()
    page.evaluate('''() => {
      const input = document.querySelector('select');
      input.innerHTML = '<option value="a">A</option><option value="b" disabled>B</option><option value="c">C</option>';
      input._syncChoiceControl();
    }''')
    expect(target).to_be_focused()
    page.keyboard.press('ArrowRight')
    expect(page.locator('select')).to_have_value('c')
    expect(page.get_by_role('radio', name='C', exact=True)).to_be_focused()
