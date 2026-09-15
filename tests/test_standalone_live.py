import time
import threading
import yaml

import pytest
from fastapi.testclient import TestClient

from dataviz.server.app import create_app
from dataviz.server.standalone import StandaloneInput
from dataviz.standalone import prepare_input
from test_local_data import local_dashboard


def live_app(tmp_path, *, execution=None):
    path = local_dashboard(tmp_path, "csv")
    csv = tmp_path / "sales.csv"
    csv.write_text("amount\n10\n")
    data = [f"sales={csv}"]
    root, _ = prepare_input(path, data=data)
    inputs = StandaloneInput(path, root, data=data)
    return create_app(root, watch=False, standalone_input=inputs, execution=execution), path, csv


def run(client, *, automatic=False):
    response = client.post("/api/dashboards/local/runs", json={
        "session_id": "local-test-session", "query_parameter_state": {}, "automatic": automatic,
    })
    assert response.status_code == 200, response.text
    identifier = response.json()["run_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(f"/api/runs/{identifier}?session_id=local-test-session").json()
        if result["status"] not in ("queued", "loading"):
            assert result["status"] == "ready", result
            return identifier
        time.sleep(.01)
    pytest.fail("Run did not finish")


@pytest.mark.parametrize('interval', [0, -1, 86401, 1.5, True, '10'])
def test_refresh_interval_rejects_invalid_values(tmp_path, interval):
    app, path, csv = live_app(tmp_path)
    root = app.state.workspace.root
    from dataviz.errors import WorkspaceError
    with pytest.raises(WorkspaceError, match='integer'):
        create_app(root, standalone_input=StandaloneInput(path, root, data=[f'sales={csv}']), refresh_interval=interval)


def test_refresh_interval_requires_live_auto_mode(tmp_path):
    app, path, csv = live_app(tmp_path)
    root = app.state.workspace.root
    inputs = StandaloneInput(path, root, data=[f'sales={csv}'])
    from dataviz.errors import WorkspaceError
    for kwargs in ({}, {'standalone_input': inputs, 'execution': 'manual'}):
        with pytest.raises(WorkspaceError, match='auto mode'):
            create_app(root, refresh_interval=10, **kwargs)
    with TestClient(create_app(root, standalone_input=inputs, refresh_interval=10)) as client:
        assert client.get('/api/workspace').json()['standalone_execution']['refresh_interval'] == 10


def test_live_data_reload_preserves_old_run_and_reports(tmp_path):
    app, path, csv = live_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/workspace").json()["standalone_execution"] == {"mode": "auto", "auto_allowed": True, "refresh_interval": None}

        first = run(client, automatic=True)
        old_root = app.state.workspace.root
        csv.write_text("amount\n25\n")
        second = run(client, automatic=True)
        assert old_root != app.state.workspace.root
        for identifier, value in ((first, 10), (second, 25)):
            output = client.get(f"/api/runs/{identifier}/outputs/source:sales/main?session_id=local-test-session&format=json")
            assert output.status_code == 200, output.text
            assert output.json()["value"] == [{"amount": value}]
            canvas = client.get(f"/api/dashboards/local/canvas?session_id=local-test-session&run_id={identifier}")
            assert canvas.status_code == 200, canvas.text[:500]
            report = client.post('/api/dashboards/local/report', json={
                'session_id': 'local-test-session', 'run_id': identifier, 'destination': 'download',
            })
            assert report.status_code == 200, report.text[:500]
        assert app.state.manager.records[first].workspace.root == old_root
        assert not (tmp_path / ".dataviz").exists()


def test_live_invalid_yaml_keeps_snapshot_and_recovers(tmp_path):
    app, path, _ = live_app(tmp_path)
    with TestClient(app) as client:
        first = run(client)
        valid = path.read_text()
        root = app.state.workspace.root
        path.write_text("sources: [")
        response = client.post("/api/dashboards/local/runs", json={"session_id": "local-test-session"})
        assert response.status_code == 409, response.text
        assert app.state.workspace.root == root
        assert client.get(f"/api/dashboards/local/canvas?session_id=local-test-session&run_id={first}").status_code == 200
        report = client.post('/api/dashboards/local/report', json={
            'session_id': 'local-test-session', 'run_id': first,
        })
        assert report.status_code == 200, report.text[:500]
        path.write_text(valid)
        run(client)


def test_manual_mode_rejects_automatic_requests(tmp_path):
    app, _, _ = live_app(tmp_path, execution="manual")
    with TestClient(app) as client:
        response = client.post("/api/dashboards/local/runs", json={"session_id": "local-test-session", "automatic": True})
        assert response.status_code == 409
        assert not app.state.manager.records
        run(client)


def test_refresh_marks_old_local_data_generation_outdated(tmp_path):
    app, _, csv = live_app(tmp_path)
    with TestClient(app) as client:
        first = run(client)
        csv.write_text('amount\n30\n')
        app.state.workspace_watcher.flush()
        remembered = client.get('/api/session/runs?session_id=local-test-session').json()
        assert remembered['runs'][0]['run_id'] == first
        assert remembered['runs'][0]['query_outdated'] is True


def test_inflight_run_keeps_original_files(tmp_path, monkeypatch):
    from dataviz.execution import Executor
    app, _, csv = live_app(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = Executor.run

    def gated(self, *args, **kwargs):
        entered.set()
        assert release.wait(5), 'test did not release execution'
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Executor, 'run', gated)
    with TestClient(app) as client:
        response = client.post('/api/dashboards/local/runs', json={'session_id': 'local-test-session'})
        assert response.status_code == 200
        first = response.json()['run_id']
        try:
            assert entered.wait(2)
            old = app.state.workspace.root
            csv.write_text('amount\n99\n')
            app.state.workspace_watcher.flush()
            assert app.state.workspace.root != old
        finally:
            release.set()
        record = app.state.manager.records[first]
        with record.condition:
            assert record.condition.wait_for(lambda: record.status not in {'queued', 'loading'}, timeout=5)
        assert record.status == 'ready'
        result = client.get(f'/api/runs/{first}/outputs/source:sales/main?session_id=local-test-session&format=json')
        assert result.json()['value'] == [{'amount': 10}]


def test_missing_new_dependency_can_be_created_without_touching_yaml_again(tmp_path):
    app, path, _ = live_app(tmp_path)
    document = yaml.safe_load(path.read_text())
    document['dataset_transforms'] = [{
        'id': 'total', 'runtime': 'server-python', 'code': 'total.py',
        'inputs': {'sales': 'source:sales/main'}, 'outputs': {'main': {'kind': 'table'}},
    }]
    document['views'][0]['input'] = 'dataset:total/main'
    with TestClient(app) as client:
        run(client)
        old = app.state.workspace.root
        path.write_text(yaml.safe_dump(document))
        app.state.workspace_watcher.flush()
        assert app.state.workspace_change_journal.latest.status == 'invalid'
        assert app.state.workspace.root == old
        (tmp_path / 'total.py').write_text('def transform(context):\n    return {"main": context.table("sales")}\n')
        app.state.workspace_watcher.flush()
        assert app.state.workspace.root != old
        run(client)


def test_external_adapter_does_not_auto_execute(tmp_path):
    from test_standalone import document
    path = document(tmp_path)
    auth = tmp_path / 'connection.yaml'
    auth.write_text("adapters: {local: {type: sqlalchemy, url: 'sqlite:///:memory:'}}")
    root, _ = prepare_input(path, auth=auth)
    inputs = StandaloneInput(path, root, auth=auth)
    app = create_app(root, watch=False, standalone_input=inputs)
    with TestClient(app) as client:
        assert client.get('/api/workspace').json()['standalone_execution'] == {'mode': 'manual', 'auto_allowed': False, 'refresh_interval': None}
        assert not app.state.manager.records
    from dataviz.errors import WorkspaceError
    with pytest.raises(WorkspaceError, match='Automatic execution requires local'):
        create_app(root, standalone_input=inputs, execution='auto')


def test_shared_old_result_still_opens_after_input_change(tmp_path):
    app, _, csv = live_app(tmp_path)
    with TestClient(app) as client:
        first = run(client)
        shared = client.post('/api/dashboards/local/report', json={
            'session_id': 'local-test-session', 'run_id': first, 'destination': 'share',
        })
        assert shared.status_code == 200, shared.text
        csv.write_text('amount\n88\n')
        run(client)
        payload = shared.json()
        response = client.get(payload['url'])
        assert response.status_code == 200, response.text[:500]


def test_cli_wires_original_inputs_and_manual_mode(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from dataviz.cli import app as cli
    _, path, csv = live_app(tmp_path)
    captured = {}
    monkeypatch.setattr('uvicorn.run', lambda application, **kwargs: captured.update(app=application, **kwargs))
    result = CliRunner().invoke(cli, ['serve', str(path.parent), '--data', f'sales={csv}', '--execution', 'manual', '--no-watch'])
    assert result.exit_code == 0, result.output
    with TestClient(captured['app']) as client:
        assert client.get('/api/workspace').json()['standalone_execution']['mode'] == 'manual'
        run(client)
        csv.write_text('amount\n28\n')
        identifier = run(client)
        value = client.get(f'/api/runs/{identifier}/outputs/source:sales/main?session_id=local-test-session&format=json').json()['value']
        assert value == [{'amount': 28}]
    invalid = CliRunner().invoke(cli, ['serve', str(path), '--execution', 'typo'])
    assert invalid.exit_code != 0
    assert 'auto or manual' in invalid.output
    scheduled = CliRunner().invoke(cli, ['serve', str(path), '--data', f'sales={csv}', '--refresh-interval', '10'])
    assert scheduled.exit_code == 0, scheduled.output
    with TestClient(captured['app']) as client:
        assert client.get('/api/workspace').json()['standalone_execution']['refresh_interval'] == 10
    invalid = CliRunner().invoke(cli, ['serve', str(path), '--refresh-interval', '0'])
    assert invalid.exit_code != 0


def test_hidden_page_with_external_source_disables_default_auto(tmp_path):
    from dataviz.server.standalone import local_auto_eligible
    from dataviz.workspace import load_workspace
    _, path, csv = live_app(tmp_path)
    document = yaml.safe_load(path.read_text())
    local_view = document.pop('views')
    document['sources'].append({'id': 'remote', 'type': 'sql', 'adapter': 'external',
                                'code': {'inline': 'SELECT 1 AS amount'}, 'outputs': {'main': {'kind': 'table'}}})
    document['pages'] = [{'id': 'local', 'views': local_view},
                         {'id': 'remote', 'views': [{'id': 'remote_table', 'template': 'table', 'input': 'source:remote/main'}]}]
    path.write_text(yaml.safe_dump(document))
    root, _ = prepare_input(path, data=[f'sales={csv}'])
    assert not local_auto_eligible(load_workspace(root))
