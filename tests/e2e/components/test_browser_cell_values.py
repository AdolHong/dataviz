from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import base64
import json
from pathlib import Path
import hashlib
import os
import pytest

import pyarrow as pa

from dataviz.artifacts.browser_values import browser_cell, browser_table_rows

pytestmark = pytest.mark.e2e


def test_browser_cells_preserve_precision_and_have_explicit_json_types():
    assert browser_cell(9007199254740993) == '9007199254740993'
    assert browser_cell(12) == 12
    assert browser_cell(Decimal('1E+3')) == '1000'
    assert browser_cell(False) is False
    assert browser_cell(float('nan')) is None
    assert browser_cell(Decimal('12345678901234567890.1234')) == '12345678901234567890.1234'
    assert browser_cell(date(2026, 9, 14)) == '2026-09-14'
    assert browser_cell(datetime(2026, 9, 14)) == '2026-09-14T00:00:00.000Z'
    assert browser_cell(datetime(2026, 9, 14, 8, tzinfo=timezone(timedelta(hours=8)))) == '2026-09-14T00:00:00.000Z'
    assert browser_cell({'nested': [b'AB', None]}) == {'nested': [[65, 66], None]}


def test_arrow_backed_json_rows_do_not_round_int64_or_decimal():
    table = pa.table({'id': [9007199254740993], 'amount': [Decimal('1.20')], 'day': [date(2026, 9, 14)]})
    assert browser_table_rows(table) == [{'id': '9007199254740993', 'amount': '1.20', 'day': '2026-09-14'}]


def test_real_arrow_decoder_matches_json_cells_and_columnar_worker_values(page):
    table = pa.table({
        'id': [9007199254740993, -9007199254740993],
        'amount': [Decimal('123456789012345.20'), Decimal('-1.20')],
        'day': [date(2026, 9, 14), None],
        'timestamp': [datetime(2026, 9, 14), None],
        'nested': [{'items': [1, 2]}, {'items': []}],
        'bytes': [b'AB', b''], 'value': [float('nan'), 1.5],
        'negative_scale': pa.array([Decimal('1E+3'), Decimal('-2E+3')], type=pa.decimal128(8, -3)),
        'zoned': pa.array([datetime(2026, 9, 14, 8, tzinfo=timezone(timedelta(hours=8))), None], type=pa.timestamp('us', tz='Asia/Shanghai')),
        'dictionary_date': pa.array([date(2026, 9, 14), None]).dictionary_encode(),
    })
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    root = Path(__file__).resolve().parents[3]
    # Same pinned asset and integrity check as the browser suite; never silently
    # exercise an arbitrary local Arrow build.
    asset_dir = Path(os.environ.get('DATAVIZ_E2E_ASSET_DIR', root / '.browser-test-assets'))
    asset = asset_dir / 'Arrow.es2015.min.js'
    manifest = json.loads((root / 'tests/e2e/assets.json').read_text())
    digest = next(item['sha256'] for item in manifest if item['file'] == asset.name)
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == digest
    page.add_script_tag(path=str(asset))
    page.add_script_tag(content=(root / 'src/dataviz/server/runtime_src/10-value-contracts.js').read_text())
    actual = page.evaluate(r'''input => {
const output=new DatavizArrowOutput(Arrow.tableFromIPC(Uint8Array.from(atob(input),c=>c.charCodeAt(0))),{},null);
const c=output.columnar();
const reconstructed=Array.from({length:c.length},(_,i)=>Object.fromEntries(Object.entries(c.columns).map(([k,v])=>[k,v[i]])));
return {rows:output.rows(), columnar:reconstructed, snapshot:datavizSnapshotValue(output)};
}''', base64.b64encode(sink.getvalue().to_pybytes()).decode())
    expected = browser_table_rows(table)
    assert actual == {'rows':expected, 'columnar':expected, 'snapshot':expected}
