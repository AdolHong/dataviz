"""Explicit release comparison; requires the pinned baseline wheel, not regular CI assets.

Run: pytest tests/upgrade/test_transport_upgrade.py -o addopts= -q
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from zipfile import ZipFile

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from playwright.sync_api import sync_playwright, expect

from e2e.support.runtime import _copy_workspace, WORKER, _open_dashboard, _run_and_wait, _export_html, _running_static_server

ROOT = Path(__file__).resolve().parents[2]
BASELINE_SHA = '7ad29dfa10447ea7620517bf21a340d792bc464abb8750652b85da3caa2831b4'
pytestmark = pytest.mark.e2e


@contextmanager
def serve(workspace, package, log):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with log.open('w') as stream:
        process = subprocess.Popen([sys.executable, '-m', 'dataviz.cli', 'serve', str(workspace),
                                    '--port', str(port), '--no-watch'],
                                   env={**os.environ, 'PYTHONPATH':str(package)},
                                   cwd=workspace, stdout=stream, stderr=subprocess.STDOUT)
        try:
            for _ in range(200):
                if process.poll() is not None:
                    raise AssertionError(log.read_text())
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.1):
                        break
                except OSError:
                    time.sleep(.05)
            else:
                raise AssertionError('server startup timed out')
            yield f'http://127.0.0.1:{port}'
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.parametrize('transport', ['json', 'arrow'])
@pytest.mark.parametrize('unsafe', [False, True], ids=['safe-id','large-id'])
def test_transport_upgrade_business_results(tmp_path, transport, unsafe):
    baseline = Path(os.environ.get('DATAVIZ_UPGRADE_BASELINE', ROOT/'dist/ai_dataviz-0.25.6-py3-none-any.whl'))
    assert baseline.is_file(), 'Run this explicit acceptance with DATAVIZ_UPGRADE_BASELINE pointing to 0.25.6 wheel'
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == BASELINE_SHA
    old = tmp_path/'baseline'
    with ZipFile(baseline) as archive:
        archive.extractall(old)
    data = pa.table({'item':['A','A','B'], 'city':['上海','深圳','厦门'], 'qty':[10,20,7],
        'id':[9007199254740992,9007199254740993,9007199254740994] if unsafe else [1,2,3],
        'day':[date(2026,9,12),date(2026,9,13),date(2026,9,13)],
        'timestamp':[datetime(2026,9,12),datetime(2026,9,13),datetime(2026,9,13)],
        'amount':[Decimal('1.20'),Decimal('2.30'),Decimal('3.40')]})
    results = {}
    with sync_playwright() as playwright:
        browser = getattr(playwright, os.environ.get('DATAVIZ_BROWSER','chromium')).launch()
        try:
            for version, package in [('0.25.6',old),('current',ROOT/'src')]:
                workspace = _copy_workspace(WORKER,tmp_path/version)
                config_path=workspace/'workspace.yaml'
                config=yaml.safe_load(config_path.read_text())
                config['runtime']['browser_table_transport']=transport
                config_path.write_text(yaml.safe_dump(config))
                folder=workspace/'dashboards/worker-runtime'
                pq.write_table(data,folder/'data/rows.parquet')
                dashboard=yaml.safe_load((folder/'dashboard.yaml').read_text())
                dashboard['sources'][0].update(path='data/rows.parquet',format='parquet')
                dashboard['controls']=[{'id':'item','type':'single_select','value_type':'text','field':'item',
                    'initial':{'mode':'first'},'options':{'mode':'infer','source':'source:raw/main'}}]
                dashboard['views']=[{'id':'chart','template':'bar','input':'interactive:scaled/main',
                                    'x':'city','y':'qty','aggregate':'none'},
                                   {'id':'timeline','template':'line','input':'interactive:scaled/timeline',
                                    'x':'day','y':'qty','aggregate':'none'}]
                dashboard['sections'][0]['views']=['chart','timeline']
                (folder/'dashboard.yaml').write_text(yaml.safe_dump(dashboard))
                transform=yaml.safe_load((folder/'transforms/scaled.yaml').read_text())
                transform['control_inputs']={'item':'dashboard:worker-runtime/item'}
                transform['outputs']={'main':{'kind':'table'},'timeline':{'kind':'table'}}
                (folder/'transforms/scaled.yaml').write_text(yaml.safe_dump(transform))
                (folder/'transforms/scaled.js').write_text("""function transform(c) {
                  const rows=c.table('rows').rows().filter(r=>r.item===c.control_inputs.item);
                  return {main:rows.map(r=>({city:r.city,qty:r.qty})),
                    timeline:rows.map(r=>({day:r.day,qty:r.qty}))};
                }""")
                context=browser.new_context(accept_downloads=True)
                page=context.new_page()
                asset=ROOT/'.browser-test-assets/Arrow.es2015.min.js'
                manifest=json.loads((ROOT/'tests/e2e/assets.json').read_text())
                entry=next(a for a in manifest if a['file']==asset.name)
                assert hashlib.sha256(asset.read_bytes()).hexdigest()==entry['sha256']
                page.route(entry['url'],lambda route, request, asset=asset:route.fulfill(path=str(asset),content_type='application/javascript'))
                sample=r'''() => ({raw:window.datavizRuntimeServices.tableRows(window.dataviz.portable.outputs['source:raw/main']),
                  filtered:window.datavizRuntimeServices.tableRows(window.dataviz.portable.outputs['interactive:scaled/main']),
                  chart:[...document.querySelector('[data-view-id="chart"] .js-plotly-plot').data].map(t=>({x:[...t.x],y:[...t.y]})),
                  timeline:[...document.querySelector('[data-view-id="timeline"] .js-plotly-plot').data].map(t=>({x:[...t.x],y:[...t.y]}))})'''
                with serve(workspace,package,tmp_path/f'{version}.log') as url:
                    _open_dashboard(page,url,'worker-runtime'); _run_and_wait(page)
                    # Compare the same committed Run snapshot, not a race
                    # between legacy live publication and control restoration.
                    page.reload(wait_until='domcontentloaded')
                    frame=page.frame_locator('#canvas-frame')
                    page.wait_for_function("""() => {
                      const w=document.querySelector('#canvas-frame')?.contentWindow;
                      return w?.datavizRuntime?.transformErrors.size ||
                        w?.document.querySelector('[data-view-id="chart"]')?.dataset.viewStatus==='ready';
                    }""",timeout=15000)
                    errors=frame.locator('body').evaluate("() => [...window.datavizRuntime.transformErrors].map(([id,e])=>({id,code:e.code,message:e.message}))")
                    if errors and version=='0.25.6' and transport=='json' and unsafe:
                        assert errors[0]['code']=='unsafe_integer'
                        raw=frame.locator('body').evaluate("() => window.dataviz.portable.outputs['source:raw/main']")
                        assert raw[0]['id']==raw[1]['id'], 'baseline JSON loses distinct adjacent IDs'
                        results[version]={'error':errors,'raw':raw,'chart':None,
                            'export':{'attempted':False,'reason':'upstream transform rejected unsafe integer; no valid derived chart to export'}}
                        context.close()
                        continue
                    assert not errors, errors
                    expect(frame.locator('[data-view-id="chart"]')).to_have_attribute('data-view-status','ready',timeout=15000)
                    expect(frame.locator('[data-view-id="timeline"]')).to_have_attribute('data-view-status','ready')
                    before=frame.locator('body').evaluate(sample)
                    options=page.locator('select[name="dashboard:worker-runtime/item"]').evaluate('(s)=>[...s.options].map(o=>o.value)')
                    page.locator('select[name="dashboard:worker-runtime/item"]').select_option(label='B', force=True)
                    expect(frame.locator('[data-view-id="chart"] .js-plotly-plot')).to_contain_text('厦门')
                    expect(frame.locator('[data-view-id="timeline"]')).to_have_attribute('data-view-status','ready')
                    after=frame.locator('body').evaluate(sample)
                    report=tmp_path/f'{version}.html'
                    with page.expect_download(timeout=20000) as download:
                        _export_html(page)
                    download.value.save_as(report)
                    page.goto('about:blank')
                with _running_static_server(tmp_path) as url:
                    page.goto(f'{url}/{report.name}',wait_until='domcontentloaded')
                    expect(page.locator('[data-view-id="chart"]')).to_have_attribute('data-view-status','ready',timeout=15000)
                    expect(page.locator('[data-view-id="timeline"]')).to_have_attribute('data-view-status','ready')
                    exported=page.locator('body').evaluate(sample)
                results[version]={'options':options,'before':before,'after':after,'export':exported}
                context.close()
        finally:
            browser.close()
    evidence=Path(os.environ.get('DATAVIZ_UPGRADE_EVIDENCE',ROOT/'.test-evidence/upgrade-values'))
    evidence.mkdir(parents=True,exist_ok=True)
    (evidence/f'{transport}-{"large" if unsafe else "safe"}.json').write_text(json.dumps({'baseline_sha256':BASELINE_SHA,'results':results},ensure_ascii=False,indent=2))
    assert results['current']['options']==['','A','B']
    if 'error' not in results['0.25.6']:
        assert results['0.25.6']['options']==results['current']['options']
        assert results['0.25.6']['before']['chart']==results['current']['before']['chart']
    for version in results.values():
        if 'error' in version:
            continue
        assert version['before']['filtered']==[{'city':'上海','qty':10},{'city':'深圳','qty':20}]
        assert version['after']['filtered']==[{'city':'厦门','qty':7}]
        assert version['after']['chart']==version['export']['chart']
        assert version['after']['timeline']==version['export']['timeline']
        timeline=version['before']['timeline'][0]
        days=[datetime.fromtimestamp(x/1000, __import__('datetime').timezone.utc).date().isoformat()
              if isinstance(x,(int,float)) else x[:10] for x in timeline['x']]
        assert days==['2026-09-12','2026-09-13']
        assert timeline['y']==[10,20]
        assert version['after']['filtered']==version['export']['filtered']
    assert results['current']['after']['raw']==results['current']['export']['raw']
    assert results['current']['before']['raw'][1]['id']==('9007199254740993' if unsafe else 2)
    assert results['current']['before']['raw'][0]['amount']=='1.20'
    assert results['current']['before']['raw'][0]['day']=='2026-09-12'
