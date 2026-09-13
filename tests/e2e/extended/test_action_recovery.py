import sqlite3

import pytest
from playwright.sync_api import expect

from e2e.support.runtime import _open_single_fixture_dashboard, _run_and_wait, _running_server

pytestmark = pytest.mark.e2e


def test_lost_write_response_recovers_receipt_after_reload(page, stable_analysis):
    root, database = stable_analysis
    writes = []

    def lose_response(route):
        writes.append(route.request.post_data_json)
        # Deliver the write to the real server, then lose only its response.
        response = route.fetch()
        assert response.status == 200
        route.abort('failed')

    with _running_server(root) as url:
        _open_single_fixture_dashboard(page, url, root)
        _run_and_wait(page)
        frame = page.frame_locator('#canvas-frame')
        expect(frame.locator('[data-view-id="editor"]')).to_have_attribute('data-view-status', 'ready')
        page.route('**/api/dashboards/stability/actions/save_label', lose_response)
        error = frame.locator('body').evaluate('''async () => {
          try {
            await window.dataviz.serverActions.invoke('save_label',
              {id:'A1', revision:0, label:'sensitive'}, {requestId:'lost-response'});
            return null;
          } catch (error) { return {requestId:error.requestId, saved:error.receipt?.status === 'succeeded'}; }
        }''')
        assert error == {'requestId': 'lost-response', 'saved': False}
        assert len(writes) == 1
        page.reload()
        frame = page.frame_locator('#canvas-frame')
        expect(frame.locator('[data-view-id="editor"]')).to_have_attribute('data-view-status', 'ready', timeout=30_000)
        canvas = next(frame for frame in page.frames if '/canvas?' in frame.url)
        canvas.wait_for_function('''async () => {
          window.recoveredReceipt = await window.dataviz.serverActions.status('save_label', 'lost-response');
          return window.recoveredReceipt.status === 'succeeded'
            && window.recoveredReceipt.refresh?.status === 'ready';
        }''', timeout=30_000)
        receipt = canvas.evaluate('window.recoveredReceipt')
        assert receipt['result']['revision'] == 1
        assert len(writes) == 1, 'recovery must not invoke the write again'
        with sqlite3.connect(database) as db:
            assert db.execute("select label, revision from annotations where id='A1'").fetchone() == ('sensitive', 1)
