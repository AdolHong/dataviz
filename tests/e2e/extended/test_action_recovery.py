import sqlite3

import pytest
from playwright.sync_api import expect

from e2e.support.runtime import _open_single_fixture_dashboard, _run_and_wait, _running_server

pytestmark = pytest.mark.e2e


def test_hung_write_response_releases_host_and_recovers_original_receipt(page, stable_analysis):
    root, database = stable_analysis
    writes = []
    # Capture only the host's HTTP deadline; do not sleep for five minutes or
    # alter Canvas RPC, server execution, polling or normal application timers.
    page.add_init_script('''(() => {
      const schedule = window.setTimeout;
      window.setTimeout = (callback, delay, ...args) => {
        if (delay === 290000) window.fireActionHttpDeadline = () => callback(...args);
        return schedule(callback, delay, ...args);
      };
    })();''')

    def hang_after_save(route):
        writes.append(route.request.post_data_json)
        response = route.fetch()
        assert response.status == 200
        # The server received the write. Deliberately do not deliver headers.

    with _running_server(root) as url:
        _open_single_fixture_dashboard(page, url, root)
        _run_and_wait(page)
        frame = page.frame_locator('#canvas-frame')
        expect(frame.locator('[data-view-id="editor"]')).to_have_attribute('data-view-status', 'ready')
        page.route('**/api/dashboards/stability/actions/save_label', hang_after_save)
        frame.locator('body').evaluate('''() => {
          window.timeoutOutcome = null;
          window.dataviz.serverActions.invoke('save_label',
            {id:'A1', revision:0, label:'sensitive'}, {requestId:'hung-response'})
            .then(() => { window.timeoutOutcome = {unexpectedSuccess:true}; })
            .catch(error => { window.timeoutOutcome = {code:error.code, requestId:error.requestId}; });
        }''')
        # The host starts its deadline before the preflight GET; wait until the
        # real write receipt succeeds, not merely until that timer exists.
        page.evaluate('''async () => {
          const url = new URL(document.querySelector('#canvas-frame').src);
          const session = url.searchParams.get('session_id');
          const deadline = Date.now() + 15000;
          while (Date.now() < deadline) {
            const response = await fetch(`/api/dashboards/stability/actions/save_label/hung-response?session_id=${encodeURIComponent(session)}`);
            if (response.ok && (await response.json()).status === 'succeeded') return;
            await new Promise(resolve => setTimeout(resolve, 50));
          }
          throw new Error('write receipt did not become succeeded');
        }''')
        # Independently verify the business row, not just receipt status.
        def committed():
            with sqlite3.connect(database) as db:
                return db.execute("select revision from annotations where id='A1'").fetchone() == (1,)
        assert len(writes) == 1
        assert committed()
        page.evaluate('window.fireActionHttpDeadline()')
        canvas = next(item for item in page.frames if '/canvas?' in item.url)
        canvas.wait_for_function('window.timeoutOutcome !== null')
        assert canvas.evaluate('window.timeoutOutcome') == {
            'code': 'action_response_unknown', 'requestId': 'hung-response'}
        receipt = canvas.evaluate('''async () => {
          const deadline = Date.now() + 15000;
          while (Date.now() < deadline) {
            const receipt = await window.dataviz.serverActions.status('save_label', 'hung-response');
            if (receipt.status === 'succeeded' && receipt.refresh?.status === 'ready') return receipt;
            await new Promise(resolve => setTimeout(resolve, 50));
          }
          throw new Error('saved receipt refresh did not finish');
        }''')
        assert receipt['status'] == 'succeeded'
        assert receipt['result']['revision'] == 1
        assert len(writes) == 1


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
        receipt = canvas.evaluate('''async () => {
          const deadline = Date.now() + 30000;
          while (Date.now() < deadline) {
            const receipt = await window.dataviz.serverActions.status('save_label', 'lost-response');
            if (receipt.status === 'succeeded' && receipt.refresh?.status === 'ready') return receipt;
            await new Promise(resolve => setTimeout(resolve, 50));
          }
          throw new Error('recovered receipt refresh did not finish');
        }''')
        assert receipt['result']['revision'] == 1
        assert len(writes) == 1, 'recovery must not invoke the write again'
        with sqlite3.connect(database) as db:
            assert db.execute("select label, revision from annotations where id='A1'").fetchone() == ('sensitive', 1)
