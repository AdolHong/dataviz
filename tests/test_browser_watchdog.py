"""Real subprocess hangs must fail with evidence and no surviving children."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import psutil
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('browser_watchdog', ROOT / 'scripts/browser_watchdog.py')
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


@pytest.mark.parametrize('phase', ['setup', 'call', 'teardown', 'success', 'failure'])
def test_watchdog_records_phase_and_reaps_descendants(tmp_path, phase):
    (tmp_path / 'conftest.py').write_text((ROOT / 'tests/e2e/conftest.py').read_text())
    (tmp_path / 'test_probe.py').write_text(f'''
import subprocess,sys,time
from pathlib import Path
import pytest
@pytest.fixture(autouse=True)
def resource():
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
    Path('child.pid').write_text(str(child.pid))
    if {phase!r} == 'setup': time.sleep(60)
    yield
    if {phase!r} == 'teardown': time.sleep(60)
def test_probe(browser_step):
    with browser_step('synthetic-api-wait'):
        if {phase!r} == 'call': time.sleep(60)
        assert {phase!r} != 'failure'
''')
    progress = tmp_path / 'progress.json'
    env = {k:v for k,v in os.environ.items() if not k.startswith('DATAVIZ_E2E_')}
    result = watchdog.run_supervised(
        [sys.executable, '-m', 'pytest', 'test_probe.py', '-q', '-o', 'addopts='],
        cwd=tmp_path, env=env, log=tmp_path/'pytest.log', progress=progress, timeout=1)
    hung = phase in {'setup', 'call', 'teardown'}
    assert result['exit_code'] == (124 if hung else 1 if phase == 'failure' else 0)
    assert result['timed_out'] is hung
    state = json.loads(progress.read_text())
    if hung:
        assert state['nodeid'].endswith('test_probe.py::test_probe')
        assert state['phase'] == phase
        assert 'test_probe.py' in progress.with_suffix('.stacks.log').read_text()
        assert 'Timeout (' in progress.with_suffix('.stacks.log').read_text()
    steps = progress.with_suffix('.steps.jsonl')
    if phase == 'setup':
        assert not steps.exists()
    else:
        events = [json.loads(line) for line in steps.read_text().splitlines()]
        assert events[0]['step'] == 'synthetic-api-wait'
        assert events[0]['status'] == 'started'
        expected = ['started'] if phase == 'call' else ['started', 'failed' if phase == 'failure' else 'completed']
        assert [event['status'] for event in events] == expected
        assert all(set(event) == {'nodeid', 'step', 'status', 'at'} for event in events)
    child_pid = int((tmp_path/'child.pid').read_text())
    assert not psutil.pid_exists(child_pid) or psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE


def test_watchdog_bounds_process_without_pytest_hooks(tmp_path):
    result = watchdog.run_supervised(
        [sys.executable, '-c', 'import time; time.sleep(60)'], cwd=tmp_path, env=os.environ,
        log=tmp_path/'pytest.log', progress=tmp_path/'progress.json', timeout=0.1)
    assert result['exit_code'] == 124
    assert result['timed_out']
    assert 'startup' in (tmp_path/'pytest.log').read_text()
