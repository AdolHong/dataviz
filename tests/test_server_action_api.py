from concurrent.futures import ThreadPoolExecutor
import sqlite3
import time
import io
import json

from fastapi.testclient import TestClient
import pytest
import yaml

from dataviz.artifacts import ArtifactStore
from dataviz.errors import ExecutionFailure
from dataviz.protocols import DASHBOARD_SCHEMA
from dataviz.server.app import create_app
from dataviz.sources import SOURCE_RUNNERS
from dataviz.standalone import prepare_input


def test_action_cli_uses_server_execution_and_receipts(action_app, monkeypatch):
    from urllib.parse import urlsplit
    from typer.testing import CliRunner
    from dataviz.cli import app as cli
    from dataviz import cli_actions

    client, manager, root, temporary = action_app
    applied = start(client, manager)

    class ServerTransport:
        def open(self, request, timeout):
            url = urlsplit(request.full_url)
            response = client.request(request.get_method(), url.path + ("?" + url.query if url.query else ""),
                                      content=request.data, headers=dict(request.header_items()))
            assert response.status_code == 200, response.text
            return io.BytesIO(response.content)

    monkeypatch.setattr(cli_actions, "build_opener", lambda *handlers: ServerTransport())
    common = ["test", "save", "--server", "http://testserver", "--session-id", SESSION,
              "--request-id", "cli-write"]
    runner = CliRunner()
    response = runner.invoke(cli, ["actions", "invoke", *common, "--run-id", applied.run_id])
    assert response.exit_code == 0, response.output
    receipt = json.loads(response.output)
    assert receipt["status"] == "succeeded"
    wait_run(manager, receipt["refresh"]["run_id"])
    for operation in ["status", "refresh"]:
        response = runner.invoke(cli, ["actions", operation, *common])
        assert response.exit_code == 0, response.output
        assert json.loads(response.output)["status"] == "succeeded"
    # Re-submitting the original invocation reads its receipt, not another write.
    response = runner.invoke(cli, ["actions", "invoke", *common, "--run-id", applied.run_id])
    assert response.exit_code == 0, response.output
    with sqlite3.connect(temporary / "facts.sqlite") as connection:
        assert connection.execute("select value from facts").fetchone()[0] == 2


SESSION = "session_action_test"


@pytest.fixture
def action_app(tmp_path):
    database = tmp_path / "facts.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("create table facts (value integer)")
        connection.execute("insert into facts values (1)")
    (tmp_path / "mutable").mkdir()
    auth = tmp_path / "connections.yaml"
    auth.write_text(yaml.safe_dump({"adapters": {
        "db": {"type": "sqlalchemy", "url": f"sqlite:///{database}"},
        "files": {"type": "file", "root": str(tmp_path / "mutable")},
    }}))
    action_code = '''
import time
from sqlalchemy import create_engine, text
def execute(context):
    if context.payload.get("effect") == "view":
        context.invalidate("view:sales")
        return {"saved": False}
    if context.payload.get("wait"):
        context.resources.path("files", "started").write_text("ready")
        while not context.resources.path("files", "release").exists():
            time.sleep(0.01)
    engine = create_engine(context.resources.config("db")["url"])
    try:
        with engine.begin() as connection:
            connection.execute(text("update facts set value=value+1"))
    finally:
        engine.dispose()
    context.invalidate("source:labels")
    return {"saved": True}
'''
    path = tmp_path / "dashboard.yaml"
    path.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "test",
        "sources": [{"id": name, "type": "sql", "adapter": "db", "code": {"inline": query},
                     "outputs": {"main": {"kind": "table"}}, "cache": {"mode": "none"}}
                    for name, query in [("labels", "select value from facts"), ("sales", "select 42 as value")]],
        "views": [{"id": name, "template": "metric", "input": f"source:{name}/main", "value": "value"}
                  for name in ["labels", "sales"]],
        "server_actions": [{"id": "save", "code": {"inline": action_code},
                            "resources": {"db": "db", "files": "files"},
                            "invalidates": ["source:labels", "view:sales"]}],
    }))
    root, _ = prepare_input(path, auth=auth)
    app = create_app(root, watch=False)
    with TestClient(app) as client:
        yield client, app.state.manager, root, tmp_path


def wait_run(manager, run_id):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        record = manager.get(run_id, SESSION)
        if record.status not in {"queued", "loading"}:
            return record
        with record.condition:
            record.condition.wait(0.05)
    raise AssertionError("Run did not finish")


def start(client, manager):
    response = client.post("/api/dashboards/test/runs", json={"session_id": SESSION})
    assert response.status_code == 200, response.text
    record = wait_run(manager, response.json()["run_id"])
    assert record.status == "ready", record.error
    return record


def invoke(client, run_id, *, request_id="save-1", payload=None, headers=None):
    return client.post("/api/dashboards/test/actions/save", json={
        "session_id": SESSION, "run_id": run_id, "request_id": request_id, "payload": payload or {},
    }, headers=headers)


def poll(client, request_id="save-1"):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        response = client.get(f"/api/dashboards/test/actions/save/{request_id}", params={"session_id": SESSION})
        assert response.status_code == 200, response.text
        receipt = response.json()
        if receipt["status"] != "running" and receipt["refresh"]["status"] not in {"pending", "scheduling", "running"}:
            return receipt
        time.sleep(0.02)
    raise AssertionError("Action refresh did not finish")


def database_value(tmp_path):
    with sqlite3.connect(tmp_path / "facts.sqlite") as connection:
        return connection.execute("select value from facts").fetchone()[0]


def test_api_save_selective_refresh_and_deduplication(action_app, monkeypatch):
    client, manager, root, temporary = action_app
    original = start(client, manager)
    calls = []
    runner = SOURCE_RUNNERS["sql"].execute
    def track(request):
        calls.append(request.node_id)
        return runner(request)
    monkeypatch.setattr(SOURCE_RUNNERS["sql"], "execute", track)
    response = invoke(client, original.run_id)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    receipt = poll(client)
    assert receipt["status"] == "succeeded", receipt
    assert receipt["refresh"]["status"] == "ready", receipt
    assert all(receipt["timings"][key] >= 0 for key in (
        "worker_startup_ms", "code_load_ms", "python_execute_ms", "preparation_ms", "dispatch_to_outcome_ms",
    ))
    assert receipt["timings"]["dispatch_to_outcome_ms"] >= receipt["timings"]["python_execute_ms"]
    assert receipt["refresh"]["timings"]["scheduling_ms"] >= 0
    nodes = receipt["refresh"]["timings"]["nodes"]
    assert nodes["source:labels"]["result_origin"] == "executed"
    assert nodes["source:sales"]["result_origin"] == "result"
    from dataviz import __version__
    assert client.get("/api/workspace").json()["server"]["package_version"] == __version__
    assert calls == ["source:labels"]
    updated = manager.get(receipt["refresh"]["run_id"], SESSION)
    assert updated.reused_run_id == original.run_id
    assert ArtifactStore(root, updated.run_id).read_table(updated.result.outputs["source:labels/main"]).value.tolist() == [2]
    assert ArtifactStore(root, original.run_id).read_table(original.result.outputs["source:labels/main"]).value.tolist() == [1]
    assert invoke(client, original.run_id).json() == receipt
    assert database_value(temporary) == 2
    assert invoke(client, original.run_id, payload={"different": True}).status_code == 409
    assert client.get("/api/dashboards/test/actions/save/save-1", params={"session_id": "another_session"}).status_code == 404
    assert not manager.action_run_pins


def test_view_only_invalidation_does_not_query(action_app, monkeypatch):
    client, manager, _, temporary = action_app
    original = start(client, manager)
    def unexpected(_):
        raise AssertionError("View-only invalidation must not query")
    monkeypatch.setattr(SOURCE_RUNNERS["sql"], "execute", unexpected)
    response = invoke(client, original.run_id, payload={"effect": "view"})
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt["refresh"]["timings"]["scheduling_ms"] >= 0
    assert {key: value for key, value in receipt["refresh"].items() if key != "timings"} == {"status": "ready", "query_executed": False,
                                  "views": ["sales"], "base_run_id": original.run_id, "run_id": original.run_id}
    assert manager.latest_for(SESSION, "test").run_id == original.run_id
    assert database_value(temporary) == 1


def test_refresh_retry_does_not_repeat_successful_write(action_app, monkeypatch):
    client, manager, _, temporary = action_app
    original = start(client, manager)
    runner = SOURCE_RUNNERS["sql"].execute
    failing = True
    def execute(request):
        if failing and request.node_id == "source:labels":
            raise ExecutionFailure("deliberate refresh failure")
        return runner(request)
    monkeypatch.setattr(SOURCE_RUNNERS["sql"], "execute", execute)
    assert invoke(client, original.run_id).status_code == 200
    failed = poll(client)
    assert failed["status"] == "succeeded"
    assert failed["refresh"]["status"] == "failed"
    assert database_value(temporary) == 2
    failing = False
    retry = client.post("/api/dashboards/test/actions/save/save-1/refresh", json={"session_id": SESSION})
    assert retry.status_code == 200, retry.text
    recovered = poll(client)
    assert recovered["refresh"]["status"] == "ready", recovered
    assert recovered["refresh"]["run_id"] != failed["refresh"]["run_id"]
    assert database_value(temporary) == 2


def test_late_action_cannot_replace_new_query(action_app):
    client, manager, _, temporary = action_app
    original = start(client, manager)
    with ThreadPoolExecutor(max_workers=1) as executor:
        task = executor.submit(invoke, client, original.run_id, payload={"wait": True})
        try:
            deadline = time.monotonic() + 15
            while not (temporary / "mutable/started").exists():
                assert time.monotonic() < deadline
                time.sleep(0.02)
            duplicate = invoke(client, original.run_id, payload={"wait": True})
            assert duplicate.status_code == 200
            assert duplicate.json()["status"] == "running"
            assert manager.action_run_pins[original.run_id] == 1
            newer = start(client, manager)
        finally:
            (temporary / "mutable/release").write_text("continue")
        result = task.result(timeout=15)
    assert result.status_code == 200, result.text
    receipt = result.json()
    assert receipt["status"] == "succeeded"
    assert receipt["refresh"]["status"] == "superseded"
    assert manager.latest_for(SESSION, "test").run_id == newer.run_id
    assert database_value(temporary) == 2
    assert not manager.action_run_pins


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://testserver:9999"])
def test_cross_origin_write_is_rejected(action_app, origin):
    client, manager, _, temporary = action_app
    original = start(client, manager)
    response = invoke(client, original.run_id, headers={"origin": origin})
    assert response.status_code == 403
    assert database_value(temporary) == 1


def test_stale_invocation_is_rejected_before_writing(action_app):
    client, manager, _, temporary = action_app
    original = start(client, manager)
    start(client, manager)
    response = invoke(client, original.run_id)
    assert response.status_code == 409, response.text
    assert database_value(temporary) == 1


def test_new_query_between_refresh_check_and_start_is_fenced(action_app, monkeypatch):
    client, manager, _, temporary = action_app
    original = start(client, manager)
    start_run = manager.start
    competing = []
    def race(*args, **kwargs):
        if kwargs.get("_expected_run_id"):
            competing.append(start_run("test", {}, SESSION))
        return start_run(*args, **kwargs)
    monkeypatch.setattr(manager, "start", race)
    response = invoke(client, original.run_id)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"
    assert response.json()["refresh"]["status"] == "superseded"
    assert len(competing) == 1
    assert manager.latest_for(SESSION, "test").run_id == competing[0].run_id
    assert database_value(temporary) == 2
    wait_run(manager, competing[0].run_id)


def test_refresh_poll_cannot_overwrite_a_new_retry(action_app):
    client, manager, _, _ = action_app
    original = start(client, manager)
    invoke(client, original.run_id, payload={"effect": "view"})
    service = client.app.state.action_service
    journal = service.journal
    scope = service.scope(SESSION, "test", "save")
    journal.set_refresh(scope, "save-1", {"status": "running", "run_id": "old"})
    journal.set_refresh(scope, "save-1", {"status": "failed", "run_id": "old"},
                        expected={"status": "running", "run_id": "old"})
    claimed, owner = journal.claim_refresh(scope, "save-1", retry=True)
    assert owner
    stale = journal.set_refresh(scope, "save-1", {"status": "failed", "run_id": "old"},
                                expected={"status": "running", "run_id": "old"})
    assert stale == claimed


def test_action_capacity_rejection_does_not_claim_or_write(action_app):
    client, manager, _, temporary = action_app
    original = start(client, manager)
    # A harmless receipt lookup initializes the lazy service without executing.
    assert client.get("/api/dashboards/test/actions/save/missing", params={"session_id": SESSION}).status_code == 404
    service = client.app.state.action_service
    acquired = 0
    try:
        while service.slots.acquire(blocking=False):
            acquired += 1
        assert invoke(client, original.run_id).status_code == 503
        assert service.journal.get(service.scope(SESSION, "test", "save"), "save-1") is None
        assert database_value(temporary) == 1
    finally:
        for _ in range(acquired):
            service.slots.release()
