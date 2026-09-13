"""Independent table contracts without a Dashboard or unrelated charts."""
import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_sort_keeps_focus_and_horizontal_scroll(table_page):
    page = table_page
    page.add_style_tag(content='.dv-table {min-width:1200px}')
    button = page.locator('th[data-column="orders"] button')
    button.focus()
    expect(button).to_be_focused()
    page.locator('.dv-table-wrap').evaluate('node => {node.scrollLeft=220}')
    button.press('Enter')
    expect(page.locator('th[data-column="orders"]')).to_have_attribute('aria-sort', 'ascending')
    expect(button).to_be_focused()
    assert page.locator('.dv-table-wrap').evaluate('node => node.scrollLeft') == 220


def test_search_preserves_ime_composition(table_page):
    search = table_page.locator('.dv-table-search')
    search.focus()
    search.evaluate("""node => {
      window.composingInput = node;
      node.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true}));
      node.value='shenzhen';
      node.dispatchEvent(new InputEvent('input', {bubbles:true, isComposing:true, data:'shenzhen'}));
    }""")
    expect(table_page.locator('.dv-table-meta strong')).to_have_text('12')
    assert search.evaluate('node => node === window.composingInput && node.isConnected')
    expect(search).to_have_value('shenzhen')
    search.evaluate("""node => {
      node.value='华东';
      node.dispatchEvent(new CompositionEvent('compositionend', {bubbles:true, data:'华东'}));
    }""")
    expect(table_page.locator('.dv-table-meta strong')).to_have_text('4')
    expect(search).to_be_focused()


def test_sort_orders_numeric_values(table_page):
    header = table_page.locator('th[data-column="revenue"]')
    header.locator('button').click()
    expect(header).to_have_attribute('aria-sort', 'ascending')
    values = [float(v) for v in table_page.locator('tbody td[data-column="revenue"]').all_text_contents()]
    assert values == [109, 110, 111, 112]


def test_search_filters_rows_and_count(table_page):
    table_page.locator('.dv-table-search').fill('华东')
    expect(table_page.locator('tbody tr')).to_have_count(4)
    expect(table_page.locator('.dv-table-meta strong')).to_have_text('4')
    assert all('华东' in text for text in table_page.locator('tbody tr').all_text_contents())


def test_pagination_changes_visible_rows(table_page):
    expect(table_page.locator('.dv-table-page-status')).to_have_text('1 / 3')
    before = table_page.locator('tbody').inner_text()
    table_page.get_by_role('button', name='Next page').click()
    expect(table_page.locator('.dv-table-page-status')).to_have_text('2 / 3')
    expect(table_page.locator('tbody tr')).to_have_count(4)
    assert table_page.locator('tbody').inner_text() != before
