"""Local first-use and editing do not require Run or a service restart."""
from pathlib import Path
import shutil
import subprocess
import sys
import sqlite3
import threading
import yaml

import pytest
from playwright.sync_api import expect

from dataviz.server.standalone import StandaloneInput
from dataviz.standalone import prepare_input
from e2e.support.runtime import _running_server


@pytest.mark.e2e
def test_standalone_scheduled_refresh_coalesces_without_backlog(page, tmp_path, monkeypatch):
    from dataviz.execution import Executor
    from dataviz.protocols import DASHBOARD_SCHEMA
    source = tmp_path / 'analysis.yaml'
    document = {'schema': DASHBOARD_SCHEMA, 'id': 'timer',
                'sources': [{'id': 'numbers', 'type': 'python',
                             'code': {'inline': 'import time\ndef load(context):\n    return {"main": [{"amount": str(time.time_ns())}]}\n'},
                             'outputs': {'main': {'kind': 'table'}}}],
                'views': [{'id': 'values', 'template': 'table', 'input': 'source:numbers/main'}]}
    source.write_text(yaml.safe_dump(document))
    root, _ = prepare_input(source)
    original_run = Executor.run
    entered, release = threading.Event(), threading.Event()
    calls = []
    submissions = []
    page.on('request', lambda request: submissions.append(request.post_data_json)
            if request.method == 'POST' and request.url.endswith('/runs') else None)
    gate = {'active': False}

    def gated(self, *args, **kwargs):
        calls.append(kwargs.get('refresh', False))
        if gate['active']:
            entered.set()
            assert release.wait(15), 'test did not release computation'
        return original_run(self, *args, **kwargs)

    monkeypatch.setattr(Executor, 'run', gated)
    with _running_server(root, standalone_input=StandaloneInput(source, root), refresh_interval=1) as url:
        page.goto(url)
        table = page.frame_locator('#canvas-frame').locator('[data-view-id="values"] tbody')
        expect(table.locator('tr')).to_have_count(1)
        first = table.inner_text()
        # A timer must perform real Source computation, not return its cached output.
        expect(table).not_to_have_text(first)
        gate['active'] = True
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Cancel')
        assert entered.wait(3)
        count = len(calls)
        submission_count = len(submissions)
        previous = table.inner_text()
        try:
            # This wait spans two configured refresh periods: no extra task may start.
            page.wait_for_timeout(2200)
            assert len(calls) == count
            assert len(submissions) == submission_count
            assert table.inner_text() == previous
            for value in (42, 77):
                document['sources'][0]['code']['inline'] = f'def load(context):\n    return {{"main": [{{"amount": {value}}}]}}\n'
                with page.expect_response(lambda response: '/api/dashboards/timer/canvas?' in response.url):
                    source.write_text(yaml.safe_dump(document))
            assert len(calls) == count
            assert len(submissions) == submission_count
            assert table.inner_text() == previous
        finally:
            gate['active'] = False
            release.set()
        expect(table).to_contain_text('77')
        assert len(calls) == count + 1  # two changes merged into one latest run
        assert calls[1] is True
        assert submissions[1]['refresh'] is True
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Refresh')
        # Exercise the visibility lifecycle without relying on headless window focus.
        page.evaluate("""() => {
            Object.defineProperty(document, 'hidden', {configurable:true, get:() => true});
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        count = len(calls)
        page.wait_for_timeout(2200)
        assert len(calls) == count
        page.evaluate("""() => {
            delete document.hidden;
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        # Cancellation pauses periodic refresh instead of immediately restarting it.
        gate['active'] = True
        release.clear()
        entered.clear()
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Cancel')
        assert entered.wait(3)
        page.locator('#run-button').click()
        gate['active'] = False
        release.set()
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Refresh')
        count = len(calls)
        page.wait_for_timeout(2200)
        assert len(calls) == count


@pytest.mark.e2e
@pytest.mark.parametrize("mode", ["auto", "manual"])
def test_standalone_live_execution(page, tmp_path, mode):
    repo = Path(__file__).resolve().parents[3]
    for name in ("local-csv", "local-sqlite"):
        shutil.copytree(repo / "examples" / name, tmp_path / name)
    database = tmp_path / "sales.sqlite"
    subprocess.run([sys.executable, str(tmp_path / "local-sqlite/create_data.py"), str(database)], check=True)
    source = tmp_path / "local-sqlite/dashboard.yaml"
    data = [f"warehouse={database}"]
    root, _ = prepare_input(source, data=data)
    inputs = StandaloneInput(source, root, data=data)
    submitted = []
    page.on("request", lambda request: submitted.append(request.post_data_json)
            if request.method == "POST" and request.url.endswith("/runs") else None)
    with _running_server(root, standalone_input=inputs, execution=mode) as url:
        page.goto(url)
        expect(page.locator('#query-parameters-toggle')).to_be_enabled()
        if mode == "manual":
            expect(page.frame_locator('#canvas-frame').locator('body')).to_contain_text('Run')
            assert not submitted
            page.locator('#run-button').click()
        table = page.frame_locator('#canvas-frame').locator('[data-view-id="details"]')
        expect(table.locator('tbody tr')).to_have_count(6)
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Run' if mode == 'manual' else 'Refresh')
        if mode == "auto":
            expect(page.locator('#run-button')).to_contain_text('Refresh')
            page.locator('#query-parameters-toggle').click()
        parameter = page.locator('#parameter-form input[name="minimum"]')
        parameter.fill('100')
        parameter.dispatch_event('change')
        if mode == "manual":
            assert len(submitted) == 1
            page.locator('#run-button').click()
        expect(table.locator('tbody tr')).to_have_count(4)
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Run' if mode == 'manual' else 'Refresh')
        original = source.read_text()
        source.write_text('sources: [')
        expect(page.locator('#workspace-update')).to_contain_text('errors')
        expect(table.locator('tbody tr')).to_have_count(4)
        source.write_text(original.replace('revenue >= :minimum', 'revenue > :minimum + 20'))
        if mode == "manual":
            expect(page.locator('#workspace-update')).to_contain_text('Query definition changed')
            page.locator('#run-button').click()
        expect(table.locator('tbody tr')).to_have_count(2)
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Run' if mode == 'manual' else 'Refresh')
        with sqlite3.connect(database) as db:
            db.execute("UPDATE sales SET revenue=210 WHERE category='drink'")
        if mode == "manual":
            expect(page.locator('#workspace-update')).to_contain_text('Query definition changed')
            page.locator('#run-button').click()
        expect(table.locator('tbody tr')).to_have_count(5)
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Run' if mode == 'manual' else 'Refresh')
        assert all(item.get('automatic') == (mode == 'auto') for item in submitted)
        page.screenshot(path=str(tmp_path / f'standalone-{mode}.png'))
        page.locator('#query-parameters-toggle').click()
        page.set_viewport_size({'width': 390, 'height': 844})
        expect(page.locator('#run-button')).to_be_in_viewport()
        page.screenshot(path=str(tmp_path / f'standalone-{mode}-mobile.png'))
    assert not (source.parent / '.dataviz').exists()


@pytest.mark.e2e
def test_standalone_csv_inline_python_and_queued_draft(page, tmp_path, monkeypatch):
    import threading
    from dataviz.execution import Executor
    repository = Path(__file__).resolve().parents[3]
    shutil.copytree(repository / 'examples/local-csv', tmp_path / 'project')
    source = tmp_path / 'project/dashboard.yaml'
    csv = source.with_name('sales.csv')
    data = [f'sales={csv}']
    root, _ = prepare_input(source, data=data)
    inputs = StandaloneInput(source, root, data=data)
    original_run = Executor.run
    entered, release = threading.Event(), threading.Event()
    gate = {'active': False}

    def gated(self, *args, **kwargs):
        if gate['active']:
            entered.set()
            assert release.wait(10), 'test did not release computation'
        return original_run(self, *args, **kwargs)

    monkeypatch.setattr(Executor, 'run', gated)
    with _running_server(root, standalone_input=inputs) as url:
        page.goto(url)
        table = page.frame_locator('#canvas-frame').locator('[data-view-id="overview"]')
        expect(table).to_contain_text('405')
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Refresh')
        gate['active'] = True
        csv.write_text(csv.read_text() + '2026-01-04,food,25\n')
        try:
            expect(page.locator('#run-button [data-run-label]')).to_have_text('Cancel')
            assert entered.wait(2)
            # A newer file edit arrives while the old generation is running.
            with page.expect_response(lambda response: '/api/dashboards/local-sales/canvas?' in response.url):
                source.write_text(source.read_text().replace('.sum()', '.max()'))
            expect(table).to_contain_text('405')  # previous success stays visible
        finally:
            release.set()
        expect(table).to_contain_text('150')
        expect(table).not_to_contain_text('430')
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Refresh')
        expect(table).to_contain_text('110')
        page.reload()
        expect(table).to_contain_text('150')


@pytest.mark.e2e
def test_standalone_unbound_python_auto_and_execution_error(page, tmp_path):
    from dataviz.protocols import DASHBOARD_SCHEMA
    source = tmp_path / 'analysis.yaml'
    document = {'schema': DASHBOARD_SCHEMA, 'id': 'quick',
                'sources': [{'id': 'numbers', 'type': 'python',
                             'code': {'inline': 'def load(context):\n    return {"main": [{"amount": 17}]}\n'},
                             'outputs': {'main': {'kind': 'table'}}}],
                'views': [{'id': 'values', 'template': 'table', 'input': 'source:numbers/main'}]}
    source.write_text(yaml.safe_dump(document))
    original = source.read_text()
    root, _ = prepare_input(source)
    with _running_server(root, standalone_input=StandaloneInput(source, root)) as url:
        page.goto(url)
        table = page.frame_locator('#canvas-frame').locator('[data-view-id="values"]')
        expect(table).to_contain_text('17')
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Refresh')
        document['sources'][0]['code']['inline'] = 'def load(context):\n    raise ValueError("example calculation error")\n'
        source.write_text(yaml.safe_dump(document))
        expect(page.locator('#workspace-update')).to_contain_text('Analysis update failed')
        expect(table).to_contain_text('17')
        source.write_text(original.replace('17', '29'))
        expect(table).to_contain_text('29')
        expect(page.locator('#workspace-update')).not_to_be_visible()
        expect(page.locator('#run-button [data-run-label]')).to_have_text('Refresh')
