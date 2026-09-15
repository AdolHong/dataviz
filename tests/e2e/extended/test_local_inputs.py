"""Real standalone named inputs, inline code and portable report behavior."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from playwright.sync_api import expect
from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.standalone import prepare_input
from e2e.support.runtime import (
    _running_server, _running_static_server, _open_single_fixture_dashboard, _run_and_wait,
)


@pytest.mark.e2e
@pytest.mark.parametrize("example", ["local-csv", "local-sqlite"])
def test_local_inputs_server_and_cli_html(page, tmp_path, example):
    repository = Path(__file__).resolve().parents[3]
    for name in ("local-csv", "local-sqlite"):
        shutil.copytree(repository / "examples" / name, tmp_path / name)
    subprocess.run([sys.executable, str(tmp_path / "local-sqlite/create_data.py"),
                    str(tmp_path / "sales.sqlite")], check=True)
    binding = f"sales={tmp_path}/local-csv/sales.csv" if example == "local-csv" else f"warehouse={tmp_path}/sales.sqlite"
    source = tmp_path / example / "dashboard.yaml"
    root, _ = prepare_input(source, data=[binding])
    report = tmp_path / "report.html"
    query_args = ["--query-param", 'minimum={"value":100}'] if example == "local-sqlite" else []
    result = CliRunner().invoke(app, ["report", str(source), "--data", binding, "--output", str(report), *query_args])
    assert result.exit_code == 0, result.output

    def verify(surface, expected_rows=6):
        if example == "local-csv":
            table = surface.locator('[data-view-id="overview"]')
            expect(table).to_have_attribute('data-view-status', 'ready')
            expect(table).to_contain_text('405')
            expect(table).to_contain_text('285')
            table.locator('tbody tr').filter(has_text='drink').click()
            surface.wait_for_function('''() => {
              const graph = document.querySelector('[data-view-id="trend"] .js-plotly-plot');
              return graph?.data?.some(trace => JSON.stringify(Array.from(trace.y || [])) === '[80,95,110]');
            }''')
            table.locator('tbody tr').filter(has_text='food').click()
            surface.wait_for_function('''() => {
              const graph = document.querySelector('[data-view-id="trend"] .js-plotly-plot');
              return graph?.data?.some(trace => JSON.stringify(Array.from(trace.y || [])) === '[120,150,135]');
            }''')
        else:
            table = surface.locator('[data-view-id="details"]')
            expect(table).to_have_attribute('data-view-status', 'ready')
            expect(table.locator('tbody tr')).to_have_count(expected_rows)
            expect(surface.locator('[data-view-id="totals"]')).to_have_attribute('data-view-status', 'ready')

    with _running_server(root) as url:
        _open_single_fixture_dashboard(page, url, root)
        _run_and_wait(page)
        writes = []
        page.on('request', lambda request: writes.append(request.url)
                if request.method == 'POST' and request.url.endswith('/runs') else None)
        canvas = next(frame for frame in page.frames if '/canvas?' in frame.url)
        verify(canvas)
        assert not writes, 'post-query interaction must not submit another Run'
    with _running_static_server(tmp_path) as url:
        page.goto(f'{url}/report.html')
        verify(page, expected_rows=4)
        expect(page.locator('#run-button')).not_to_be_visible()
    assert not (source.parent / '.dataviz').exists()
