"""Real component assets in a small document; no server, SQL or full Canvas."""
from pathlib import Path

import pytest
from dataviz.components.registry import component_runtime_assets


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def control_page(page):
    def mount(component, markup):
        page.set_content(markup)
        assets = component_runtime_assets([component])
        page.add_style_tag(content=assets['style'])
        for script in assets['scripts']:
            page.add_script_tag(content=script['source'])
        page.evaluate('() => window.datavizComponents.controls.hydrate(document)')
        return page
    return mount


@pytest.fixture
def table_page(page):
    page.set_content('<main class="dv-view" data-view-id="table"><div id="table"></div></main>')
    page.add_style_tag(content='#table {width:480px} body {margin:16px}')
    page.add_style_tag(path=str(ROOT / 'src/dataviz/components/packages/view.declarative/style.css'))
    # Only the hosting seam is supplied here. Table rendering, state store,
    # filtering, sorting, event handlers and CSS are the production assets.
    page.evaluate("""() => {
      window.dataviz = {};
      window.datavizRuntimeServices = {};
      window.datavizRuntime = {
        renderers:new Map(), metrics:{renderers:{}},
        registerRenderer(name, renderer) { this.renderers.set(name, renderer); }
      };
    }""")
    for name in ['vendor/tanstack-table/tanstack-table-core-9.2.4.min.js',
                 'components/packages/view.declarative/controller.js',
                 'components/packages/view.declarative/adapter.js']:
        page.add_script_tag(path=str(ROOT / 'src/dataviz' / name))
    page.evaluate("""() => {
      window.tableState = window.dataviz.tables.tanstack.mount(document.querySelector('#table'), {
        rows:Array.from({length:12}, (_, i) => ({region:i < 4 ? '华东' : '华南', revenue:120-i, orders:i})),
        options:{show_count:true, searchable:true, page_size:4}
      });
    }""")
    yield page
    page.evaluate('() => window.dataviz.tables.tanstack.dispose(window.tableState)')
