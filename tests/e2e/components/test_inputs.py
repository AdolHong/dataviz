import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_multiple_input_unchanged_sync_keeps_draft_and_caret(control_page):
    page = control_page('control.multiple-input', '''<div class="dv-control"
        data-control-component="multiple-input" data-value-type="text">
        <input data-control-input type="hidden" value='["one","two"]'>
        <div data-control-mount></div></div>''')
    page.get_by_role('button', name='+ Add value', exact=True).click()
    inputs = page.locator('[data-multiple-value]')
    expect(inputs).to_have_count(3)
    inputs.last.focus()
    page.evaluate('() => window.datavizComponents.controls.sync(document)')
    expect(inputs).to_have_count(3)
    expect(inputs.last).to_be_focused()
    expect(inputs.last).to_have_value('')
    inputs.last.fill('three')
    assert page.locator('[data-control-input]').input_value() == '["one","two","three"]'
    inputs.last.evaluate('(input) => input.setSelectionRange(2, 2)')
    page.evaluate('() => window.datavizComponents.controls.sync(document)')
    expect(inputs.last).to_be_focused()
    assert inputs.last.evaluate('(input) => [input.selectionStart, input.selectionEnd]') == [2, 2]
    page.evaluate("""() => {
      document.querySelector('[data-control-input]').value='["external"]';
      window.datavizComponents.controls.sync(document);
    }""")
    expect(inputs).to_have_count(1)
    expect(inputs).to_have_value('external')


def test_multiple_input_sync_during_composition_preserves_editing_node(control_page):
    page = control_page('control.multiple-input', '''<div class="dv-control"
      data-control-component="multiple-input" data-value-type="text">
      <input data-control-input type="hidden" value='["原值"]'>
      <div data-control-mount></div></div>''')
    field = page.locator('[data-multiple-value]')
    field.focus()
    field.evaluate('''node => {
      window.editingNode = node;
      node.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true}));
      node.value = '广东';
      node.setSelectionRange(1, 1);
      node.dispatchEvent(new InputEvent('input', {bubbles:true, isComposing:true, data:'广东'}));
      document.querySelector('[data-control-input]')._syncChoiceControl();
    }''')
    assert field.evaluate('node => node === window.editingNode')
    expect(field).to_be_focused()
    expect(field).to_have_value('广东')
    assert field.evaluate('node => node.selectionStart') == 1
    field.dispatch_event('compositionend', {'data': '广东'})
    expect(page.locator('[data-control-input]')).to_have_value('["广东"]')
