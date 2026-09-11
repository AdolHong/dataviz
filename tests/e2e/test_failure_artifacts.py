"""Exercise the actual pytest failure path, not a mocked screenshot writer."""
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest


@pytest.mark.e2e
def test_state_timeline_is_bounded_and_has_no_business_text(state_timeline):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = getattr(playwright, os.environ.get('DATAVIZ_BROWSER', 'chromium')).launch()
        page = browser.new_page()
        page.add_init_script(state_timeline)
        page.goto('data:text/html,<div data-view-id="probe" data-view-status="waiting">PRIVATE_VALUE</div>')
        page.evaluate("""async () => {
          const node = document.querySelector('[data-view-id]');
          for (let i=0;i<80;i++) {
            node.dataset.viewStatus = i % 2 ? 'ready' : 'loading';
            await new Promise(resolve => setTimeout(resolve,0));
          }
        }""")
        events = page.evaluate('window.__datavizTestTimeline')
        assert len(events) == 60
        assert events[-1]['views'][0]['status'] == 'ready'
        assert 'PRIVATE_VALUE' not in str(events)
        assert events[0]['at_ms'] <= events[-1]['at_ms']
        browser.close()


@pytest.mark.e2e
def test_failure_artifacts_retain_trace_and_screenshot_only_on_failure(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "conftest.py").write_text(Path(__file__).with_name("conftest.py").read_text())
    (harness / "test_probe.py").write_text('''
import os
import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture
def engine():
    with sync_playwright() as playwright:
        browser = getattr(playwright, os.environ.get("DATAVIZ_BROWSER", "chromium")).launch()
        yield browser
        browser.close()

@pytest.fixture
def page(engine, failure_artifacts):
    return failure_artifacts(engine.new_context()).new_page()

def test_synthetic_failure(page):
    page.set_content("<h1>Synthetic diagnostic probe</h1>")
    assert False, "intentional probe"

@pytest.fixture
def failed_setup(page):
    page.set_content("<h1>Synthetic setup probe</h1>")
    raise RuntimeError("intentional setup probe")

def test_setup_failure(failed_setup):
    pass

def test_success(page):
    page.set_content("<h1>Success</h1>")
    assert page.locator("h1").inner_text() == "Success"
''')
    evidence = tmp_path / "evidence"
    env = {**os.environ, "DATAVIZ_E2E_ARTIFACT_DIR": str(evidence)}
    result = subprocess.run([sys.executable, "-m", "pytest", str(harness), "-q", "-o", "addopts="],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 failed, 1 passed, 1 error" in result.stdout, result.stdout
    traces = list(evidence.rglob("*-trace.zip"))
    assert len(traces) == 2
    assert len(list(evidence.rglob("*.png"))) == 2
    assert {trace.with_name("test.txt").read_text().split('::')[-1] for trace in traces} == {
        'test_synthetic_failure', 'test_setup_failure',
    }
    for trace in traces:
        with ZipFile(trace) as archive:
            assert archive.testzip() is None
            assert any(name.endswith(".trace") for name in archive.namelist())
