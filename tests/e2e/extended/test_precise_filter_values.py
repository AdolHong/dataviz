from datetime import date
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from playwright.sync_api import expect

from e2e.support.runtime import (
    WORKER, _copy_workspace, _running_server, _open_dashboard, _run_and_wait,
    _export_html, _running_static_server,
)

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize('transport', ['json', 'arrow'])
def test_precise_values_as_native_filter_keys_survive_html(page, tmp_path: Path, transport):
    workspace = _copy_workspace(WORKER, tmp_path / 'workspace')
    config_path = workspace / 'workspace.yaml'
    config = yaml.safe_load(config_path.read_text())
    config['runtime']['browser_table_transport'] = transport
    config_path.write_text(yaml.safe_dump(config))
    folder = workspace / 'dashboards/worker-runtime'
    keys = {
        'day': ['2026-09-12', '2026-09-13', '2026-09-14'],
        'amount': ['1.2000', '1.2001', '2.3000'],
        'item': ['9007199254740992', '9007199254740993', '9007199254740994'],
    }
    pq.write_table(pa.table({
        'day': [date.fromisoformat(value) for value in keys['day']],
        'amount': [Decimal(value) for value in keys['amount']],
        'item': [int(value) for value in keys['item']],
        'business_key': ['first-row', 'second-row', 'third-row'],
    }), folder / 'data/precise.parquet')
    definition = yaml.safe_load((folder / 'dashboard.yaml').read_text())
    definition['sources'][0].update(path='data/precise.parquet', format='parquet')
    definition['interactive_transforms'] = []
    definition['controls'] = [{
        'id': field, 'field': field, 'type': 'single_select',
        'value_type': 'date' if field == 'day' else 'text',
        'initial': {'mode': 'first'}, 'options': {'mode': 'infer', 'source': 'source:raw/main'},
    } for field in keys]
    definition['views'] = [{
        'id': field, 'template': 'table', 'input': 'source:raw/main',
        'control_inputs': {'selection': {
            'mode': 'filter', 'control': f'dashboard.{field}', 'field': field,
            'inputs': ['main'], 'empty': 'match_none',
        }},
    } for field in keys]
    definition['sections'][0]['views'] = list(keys)
    (folder / 'dashboard.yaml').write_text(yaml.safe_dump(definition))
    report = tmp_path / 'precise.html'
    with _running_server(workspace) as url:
        _open_dashboard(page, url, 'worker-runtime')
        _run_and_wait(page)
        frame = page.frame_locator('#canvas-frame')
        for field, values in keys.items():
            select = page.locator(f'select[name="dashboard:worker-runtime/{field}"]')
            expect(select.locator('option')).to_have_count(4)
            actual = select.evaluate('s => [...s.options].map(o => o.value).filter(Boolean)')
            assert actual == values
            table = frame.locator(f'[data-view-id="{field}"]')
            for index in [1, 0, 2]:
                select.select_option(value=values[index], force=True)
                expect(table.locator('tbody tr')).to_have_count(1)
                expect(table.locator('tbody')).to_contain_text(['first-row', 'second-row', 'third-row'][index])
        with page.expect_download(timeout=20000) as download:
            _export_html(page)
        download.value.save_as(report)
        page.goto('about:blank')
    with _running_static_server(tmp_path) as url:
        page.goto(f'{url}/precise.html')
        for field in keys:
            table = page.locator(f'[data-view-id="{field}"]')
            expect(table.locator('tbody tr')).to_have_count(1, timeout=15000)
            expect(table.locator('tbody')).to_contain_text('third-row')
