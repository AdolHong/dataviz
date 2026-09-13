import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def choice_markup(component, multiple=True):
    markup = f'''<div style="position:fixed;right:16px;width:288px" class="dv-control"
      data-control-component="{component}" data-clearable="true" data-search="true" data-search-threshold="0"
      data-cascader-levels='["province","city"]'>
      <select data-control-input {'multiple' if multiple else ''} style="display:none">
        <option value="a" data-path='["广东","深圳"]'>广东 / 深圳</option>
        <option value="b" data-path='["广东","佛山"]'>广东 / 佛山</option>
        <option value="c" data-path='["福建","厦门"]'>福建 / 厦门</option>
        <option value="d" data-path='["福建","泉州"]'>福建 / 泉州</option>
      </select><div data-control-mount></div></div>'''
    if component == 'cascader':
        for value, path in [('a','["广东","深圳"]'), ('b','["广东","佛山"]'),
                            ('c','["福建","厦门"]'), ('d','["福建","泉州"]')]:
            markup = markup.replace(f'value="{value}"', f"value='{path}'")
    return markup


@pytest.mark.parametrize('component', ['select', 'cascader'])
def test_search_bulk_actions_preserve_outside_selection(control_page, component):
    page = control_page('control.' + component, choice_markup(component))
    page.locator('[data-control-trigger]').click()
    page.get_by_role('button', name='Select all', exact=True).click()
    page.locator('.dv-choice-search').fill('广东')
    page.get_by_role('button', name='Clear results', exact=True).click()
    assert page.locator('select').evaluate('n => [...n.selectedOptions].every(o => o.textContent.includes("福建"))')
    assert page.locator('select').evaluate('n => n.selectedOptions.length') == 2
    page.get_by_role('button', name='Select results', exact=True).click()
    assert page.locator('select').evaluate('n => n.selectedOptions.length') == 4
    expect(page.get_by_role('button', name='Revert', exact=True)).to_have_count(0)
    page.locator('.dv-choice-search').press('Escape')
    expect(page.locator('[data-control-panel]')).to_be_hidden()


@pytest.mark.parametrize('width', [375, 894, 1440])
def test_cascader_bounds_and_search_row_density(control_page, width):
    page = control_page('control.cascader', choice_markup('cascader'))
    page.set_viewport_size({'width':width, 'height':600})
    page.locator('[data-control-trigger]').click()
    heights = []
    for query, count in [('广东', 2), (' / ', 4)]:
        page.locator('.dv-choice-search').fill(query)
        rows = page.locator('.dv-cascader-results .dv-cascader-option')
        expect(rows).to_have_count(count)
        heights += rows.evaluate_all('nodes => nodes.map(n => n.getBoundingClientRect().height)')
    box = page.locator('[data-control-panel]').bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= width
    assert max(heights) <= 50 and max(heights) - min(heights) <= 1


def test_single_select_keyboard_has_no_bulk_actions(control_page):
    page = control_page('control.select', choice_markup('select', False))
    trigger = page.locator('[data-control-trigger]')
    trigger.focus()
    trigger.press('Enter')
    expect(page.locator('[data-control-panel]')).to_be_visible()
    expect(page.get_by_role('button', name='Select all', exact=True)).to_have_count(0)
    page.keyboard.press('Escape')
    expect(page.locator('[data-control-panel]')).to_be_hidden()
    expect(trigger).to_be_focused()


def test_checkbox_group_consecutive_clicks_clear_and_restore(control_page):
    page = control_page('control.checkbox-group', choice_markup('checkbox-group').replace('<option ', '<option selected '))
    # Exercise consecutive edits without sleep or server acknowledgements.
    history = page.evaluate("""() => {
      const input = document.querySelector('select');
      const history = [];
      for (let cycle = 0; cycle < 2; cycle++) {
        for (const value of ['a', 'b', 'c', 'd']) {
          document.querySelector(`.dv-checkbox-option[data-value="${value}"]`).click();
          history.push([...input.selectedOptions].map(o => o.value));
        }
      }
      return history;
    }""")
    assert history == [['b', 'c', 'd'], ['c', 'd'], ['d'], [],
                       ['a'], ['a', 'b'], ['a', 'b', 'c'], ['a', 'b', 'c', 'd']]
    expect(page.locator('.dv-checkbox-option[aria-pressed="true"]')).to_have_count(4)
