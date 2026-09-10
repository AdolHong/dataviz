import json
from pathlib import Path
import time
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml
from pydantic import ValidationError

from dataviz.actions import ActionContext, ActionResources, ServerActionDefinition, json_object
from dataviz.auth import AdapterResolver
from dataviz.errors import SourceFailure
from dataviz.protocols import DASHBOARD_SCHEMA
from dataviz.standalone import prepare_input
from dataviz.workspace import load_workspace
from dataviz.execution.action_journal import (
    ActionConflict, ActionJournal, action_journal_path, source_mutation_epoch, changed_run_sources,
)
from dataviz.execution.action_process import execute_action
from dataviz.execution.executor import Executor
from dataviz.artifacts import ArtifactStore
from dataviz.sources import SOURCE_RUNNERS


def action(**changes):
    return {"schema": "dataviz/server-action/v1", "id": "save", "code": "save.py", **changes}


def test_documented_transaction_validates_revision_and_commits_before_invalidation(tmp_path):
    document = (Path(__file__).resolve().parents[1] / "docs" / "server-actions.md").read_text()
    code = document.split("```python\n", 1)[1].split("```", 1)[0]
    namespace = {}
    exec(compile(code, "docs/server-actions.md", "exec"), namespace)
    database = tmp_path / "records.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("create table records (id text primary key, value text, revision integer)")
        connection.execute("insert into records values ('apple', 'before', 1)")

    class Resources:
        def config(self, alias):
            assert alias == "store"
            return {"url": f"sqlite:///{database}"}

    context = ActionContext("example", {"id": "apple", "value": "after", "expected_revision": 1},
                            Resources(), frozenset({"source:records"}))
    assert namespace["execute"](context) == {"saved": True, "id": "apple", "revision": 2}
    assert context.invalidations == ("source:records",)
    stale = ActionContext("stale", context.payload, Resources(), frozenset({"source:records"}))
    with pytest.raises(ValueError, match="changed"):
        namespace["execute"](stale)
    assert stale.invalidations == ()
    with sqlite3.connect(database) as connection:
        assert connection.execute("select value, revision from records").fetchone() == ("after", 2)


@pytest.mark.parametrize("changes", [
    {"invalidates": ["dataset:summary"]},
    {"invalidates": ["source:a", "source:a"]},
    {"invalidates": ["view:a/main"]},
    {"entrypoint": "execute()"},
    {"timeout_seconds": float("inf")},
    {"timeout_seconds": 0},
    {"resources": {"db": "../../db"}},
    {"retry": True},
])
def test_reject_unsafe_or_ambiguous_action_contract(changes):
    with pytest.raises(ValidationError):
        ServerActionDefinition.model_validate(action(**changes))


@pytest.mark.parametrize("payload", [[], {1: "key"}, {"a": (1, 2)}, {"a": float("nan")},
                                     {"a": Path("a")}, {"a": float("inf")}])
def test_payload_must_be_lossless_json(payload):
    with pytest.raises(ValueError):
        json_object(payload, label="payload")


def test_payload_copy_size_and_cycles():
    original = {"values": [1, None, True, "苹果"]}
    copied = json_object(original, label="payload")
    assert copied == original
    copied["values"].append(2)
    assert len(original["values"]) == 4
    with pytest.raises(ValueError, match="exceeds"):
        json_object(original, label="payload", max_bytes=2)
    original["cycle"] = original
    with pytest.raises(ValueError):
        json_object(original, label="payload")


def test_resources_use_external_binding_and_enforce_alias_and_root(tmp_path):
    auth = tmp_path / "auth"
    auth.mkdir()
    (auth / "adapters.yaml").write_text(yaml.safe_dump({"adapters": {
        "files": {"type": "file", "root": "mutable"},
    }}))
    resources = ActionResources(AdapterResolver(tmp_path), {"labels": "logical"}, {"logical": "files"})
    assert resources.path("labels", "annotations.json") == tmp_path / "mutable/annotations.json"
    with pytest.raises(ValueError, match="Undeclared"):
        resources.path("files", "a")
    with pytest.raises(SourceFailure, match="escapes"):
        resources.path("labels", "../outside")
    context = ActionContext("request-1", {}, resources, frozenset({"source:labels"}))
    context.invalidate("source:labels")
    context.invalidate("source:labels")
    assert context.invalidations == ("source:labels",)
    with pytest.raises(ValueError, match="Undeclared"):
        context.invalidate("source:sales")


def standalone(tmp_path, actions):
    path = tmp_path / "dashboard.yaml"
    path.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "test", "server_actions": actions,
        "sources": [{"id": "sales", "type": "sql", "adapter": "local",
                     "code": {"inline": "select 1 as value"},
                     "outputs": {"main": {"kind": "table"}}}],
        "views": [{"id": "total", "template": "metric", "input": "source:sales/main", "value": "value"}],
    }))
    return path


@pytest.mark.parametrize("auth_kind", ["file", "directory", "workspace"])
def test_action_omitted_file_root_uses_external_auth_base_for_crud(tmp_path, auth_kind):
    external = tmp_path / "external"
    (external / "auth").mkdir(parents=True)
    (external / "workspace.yaml").write_text(yaml.safe_dump({
        "schema": "dataviz/workspace/v2", "id": "external", "title": "External",
    }))
    adapter_file = external / "auth" / "adapters.yaml"
    adapter_file.write_text(yaml.safe_dump({"adapters": {"files": {"type": "file"}}}))
    auth = {"file": adapter_file, "directory": external / "auth", "workspace": external}[auth_kind]
    code = '''
import json
def execute(context):
    path = context.resources.path("store", context.payload.get("path", "records.json"))
    operation = context.payload["op"]
    if operation == "save":
        path.write_text(json.dumps(context.payload["value"]))
    elif operation == "delete":
        path.unlink()
    return {"value": json.loads(path.read_text()) if path.exists() else None}
'''
    source = standalone(tmp_path, [action(code={"inline": code}, resources={"store": "logical"})])
    root, _ = prepare_input(source, auth=auth)
    dashboard = load_workspace(root).dashboard("test")
    definition_path, definition = dashboard.server_actions["save"]
    resources = ActionResources(AdapterResolver(root), definition.resources, {"logical": "files"})
    expected = external / "records.json"
    assert resources.path("store", "records.json") == expected
    assert resources.config("store")["root"] == str(external.resolve())
    journal = ActionJournal(tmp_path / "test-receipts.sqlite")

    def run(payload, request_id):
        return execute_action(journal=journal, scope="audit", request_id=request_id,
                              definition=definition, definition_path=definition_path,
                              resources=resources, payload=payload, dashboard_root=dashboard.root)

    assert run({"op": "save", "value": {"a": 1}}, "create")["status"] == "succeeded"
    assert json.loads(expected.read_text()) == {"a": 1}
    assert run({"op": "read"}, "read")["result"]["value"] == {"a": 1}
    assert run({"op": "save", "value": {"a": 2}}, "update")["status"] == "succeeded"
    assert json.loads(expected.read_text()) == {"a": 2}
    assert run({"op": "delete"}, "delete")["result"]["value"] is None
    assert not expected.exists()
    failed = run({"op": "save", "path": "../escaped.json", "value": {}}, "escape")
    assert failed["status"] == "failed"
    assert "escapes" in failed["error"]["message"]
    assert not (tmp_path / "escaped.json").exists()


@pytest.mark.parametrize("root", [None, "", "relative"])
def test_worker_rejects_unresolved_file_root(root):
    from dataviz.execution.action_process import _BoundResources
    resources = _BoundResources({"store": {"type": "file", "root": root}})
    with pytest.raises(ValueError, match="absolute"):
        resources.path("store", "records.json")


def test_standalone_loads_action_without_executing_code(tmp_path):
    marker = tmp_path / "SHOULD_NOT_EXIST"
    code = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    path = standalone(tmp_path, [action(code={"inline": code}, invalidates=["source:sales", "view:total"])])
    root, _ = prepare_input(path)
    dashboard = load_workspace(root).dashboard("test")
    definition_path, definition = dashboard.server_actions["save"]
    assert (definition_path.parent / definition.code).read_text() == code
    assert not marker.exists()
    assert "server_actions" in json.loads(dashboard.definition.model_dump_json(by_alias=True))


@pytest.mark.parametrize("effects", [["source:missing"], ["view:missing"]])
def test_missing_effect_target_is_rejected_before_execution(tmp_path, effects):
    path = standalone(tmp_path, [action(code={"inline": "raise AssertionError('must not execute')"}, invalidates=effects)])
    root, _ = prepare_input(path)
    loaded = load_workspace(root)
    assert any("unknown target" in diagnostic.message for diagnostic in loaded.load_diagnostics)
    assert "test" not in loaded.dashboards


def test_duplicate_action_is_rejected(tmp_path):
    entry = action(code={"inline": "pass"})
    root, _ = prepare_input(standalone(tmp_path, [entry, entry]))
    loaded = load_workspace(root)
    assert any("Duplicate Server Action" in diagnostic.message for diagnostic in loaded.load_diagnostics)
    assert "test" not in loaded.dashboards


def test_journal_atomic_claim_restart_and_conflict(tmp_path):
    journal = ActionJournal(tmp_path / "receipts.sqlite")
    def claim(_):
        return journal.claim("scope", "request", "fingerprint", deadline=time.time() + 60)
    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(claim, range(16)))
    assert sum(claimed for _, claimed in claims) == 1
    journal.finish("scope", "request", {"status": "succeeded", "result": {"saved": True}})
    restarted = ActionJournal(journal.path)
    receipt, claimed = restarted.claim("scope", "request", "fingerprint", deadline=time.time() + 60)
    assert not claimed
    assert receipt["result"] == {"saved": True}
    with pytest.raises(ActionConflict):
        restarted.claim("scope", "request", "different", deadline=time.time() + 60)
    refreshed = restarted.set_refresh("scope", "request", {"status": "failed", "message": "query failed"})
    assert refreshed["status"] == "succeeded"
    assert refreshed["refresh"]["status"] == "failed"
    assert restarted.get("another-scope", "request") is None


def test_expired_receipt_is_unknown_and_never_reclaimed(tmp_path):
    journal = ActionJournal(tmp_path / "receipts.sqlite")
    journal.claim("scope", "request", "hash", deadline=time.time() - 1)
    assert journal.get("scope", "request")["status"] == "unknown"
    receipt, claimed = journal.claim("scope", "request", "hash", deadline=time.time() + 60)
    assert not claimed
    assert receipt["status"] == "unknown"
    assert journal.finish("scope", "request", {"status": "succeeded"})["status"] == "unknown"


def executor_fixture(tmp_path, code, *, timeout=10, secrets=None, dependencies=None):
    auth = tmp_path / "auth"
    auth.mkdir()
    (auth / "adapters.yaml").write_text(yaml.safe_dump({"adapters": {
        "database": {"type": "sqlalchemy", "url": "sqlite:///annotations.sqlite"},
        "files": {"type": "file", "root": "mutable", "secrets": secrets or {}},
    }}))
    (tmp_path / "mutable").mkdir()
    (tmp_path / "save.py").write_text(code)
    definition = ServerActionDefinition.model_validate(action(
        resources={"db": "database", "files": "files"},
        invalidates=["source:labels", "view:details"], timeout_seconds=timeout,
        code_dependencies=dependencies or [],
    ))
    resources = ActionResources(AdapterResolver(tmp_path), definition.resources, {})
    journal = ActionJournal(tmp_path / "receipts.sqlite")
    def execute(payload, request_id="request"):
        return execute_action(journal=journal, scope="session/dashboard", request_id=request_id,
                              definition=definition, definition_path=tmp_path / "dashboard.yaml",
                              resources=resources, payload=payload, invocation_context={"run_id": "applied"})
    return execute, journal


def test_python_action_sqlite_crud_and_duplicate_write_protection(tmp_path):
    execute, journal = executor_fixture(tmp_path, '''
from sqlalchemy import create_engine, text
def execute(context):
    payload = context.payload
    if payload["op"] not in {"save", "delete", "read"}:
        raise ValueError("invalid operation")
    engine = create_engine(context.resources.config("db")["url"])
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE IF NOT EXISTS labels (id TEXT PRIMARY KEY, label TEXT, revision INTEGER)"))
            if payload["op"] == "save":
                connection.execute(text("INSERT INTO labels VALUES (:id, :label, 1) ON CONFLICT(id) DO UPDATE SET label=:label, revision=revision+1"), payload)
            elif payload["op"] == "delete":
                connection.execute(text("DELETE FROM labels WHERE id=:id"), payload)
            rows = [dict(row) for row in connection.execute(text("SELECT * FROM labels ORDER BY id")).mappings()]
        context.invalidate("source:labels")
        return {"rows": rows}
    finally:
        engine.dispose()
''')
    payload = {"op": "save", "id": "apple", "label": "sensitive"}
    first = execute(payload)
    assert first["status"] == "succeeded", first
    assert first["invalidations"] == ["source:labels"]
    assert execute(payload) == first
    with pytest.raises(ActionConflict):
        execute({**payload, "label": "different"})
    read = execute({"op": "read"}, "read")
    assert read["result"]["rows"] == [{"id": "apple", "label": "sensitive", "revision": 1}]
    updated = execute({**payload, "label": "normal"}, "update")
    assert updated["result"]["rows"][0]["revision"] == 2
    deleted = execute({"op": "delete", "id": "apple"}, "delete")
    assert deleted["result"]["rows"] == []
    assert (tmp_path / "annotations.sqlite").is_file()
    assert journal.get("session/dashboard", "request")["result"] == first["result"]


def test_python_action_file_crud_and_transaction_failure_feedback(tmp_path):
    execute, _ = executor_fixture(tmp_path, '''
import json
def execute(context):
    path = context.resources.path("files", "labels.json")
    op = context.payload["op"]
    if op == "save":
        path.write_text(json.dumps(context.payload["value"]))
    elif op == "delete":
        path.unlink(missing_ok=True)
    elif op == "fail":
        path.write_text("{}")
        raise ValueError("failed after write")
    return {"value": json.loads(path.read_text()) if path.exists() else None}
''')
    assert execute({"op": "save", "value": {"a": True}})["result"]["value"] == {"a": True}
    assert execute({"op": "save", "value": {"a": False}}, "update")["result"]["value"] == {"a": False}
    assert execute({"op": "delete"}, "delete")["result"]["value"] is None
    failed = execute({"op": "fail"}, "fail")
    assert failed["status"] == "failed"
    assert failed["error"]["writes_may_have_occurred"] is True
    assert "failed after write" in failed["error"]["traceback"]
    assert (tmp_path / "mutable/labels.json").read_text() == "{}"


def test_timeout_never_replays_action(tmp_path):
    execute, _ = executor_fixture(tmp_path, '''
import time
def execute(context):
    path = context.resources.path("files", "writes.txt")
    with path.open("a") as stream:
        stream.write("write\\n")
    time.sleep(10)
    return {}
''', timeout=2)
    receipt = execute({})
    assert receipt["status"] == "unknown"
    assert execute({}) == receipt
    path = tmp_path / "mutable/writes.txt"
    # Even a heavily loaded machine that times out during process imports must
    # not repeat an invocation whose outcome is unknown.
    if path.exists():
        assert path.read_text() == "write\n"


def test_bad_payload_does_not_claim_or_execute(tmp_path):
    execute, journal = executor_fixture(tmp_path, "raise AssertionError('must not import')")
    with pytest.raises(ValueError):
        execute({"bad": float("nan")})
    assert journal.get("session/dashboard", "request") is None


def test_action_redacts_resource_secrets_in_results_and_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAVIZ_TEST_ACTION_SECRET", "secret-action-credential-123")
    execute, journal = executor_fixture(tmp_path, '''
def execute(context):
    secret = context.resources.config("files")["secrets"]["api_key"]
    print(secret)
    if context.payload.get("fail"):
        raise ValueError("credential " + secret)
    return {secret: "credential " + secret}
''', secrets={"api_key": "DATAVIZ_TEST_ACTION_SECRET"})
    result = execute({})
    assert result["status"] == "succeeded"
    assert result["result"] == {"[REDACTED]": "credential [REDACTED]"}
    failed = execute({"fail": True}, "failure")
    assert failed["status"] == "failed"
    assert "secret-action-credential-123" not in json.dumps(failed)
    assert "[REDACTED]" in failed["error"]["message"]
    assert "secret-action-credential-123" not in journal.path.read_bytes().decode(errors="ignore")


def test_existing_receipt_is_available_after_action_code_removed(tmp_path):
    execute, _ = executor_fixture(tmp_path, "def execute(context): return {'saved': True}")
    first = execute({})
    assert first["status"] == "succeeded"
    (tmp_path / "save.py").unlink()
    assert execute({}) == first


def test_worker_executes_captured_code_and_declared_dependencies(tmp_path, monkeypatch):
    (tmp_path / "helper.py").write_text("VALUE = 'captured'\n")
    execute, journal = executor_fixture(tmp_path,
        "from helper import VALUE\ndef execute(context): return {'value': VALUE}\n",
        dependencies=["helper.py"])
    claim = journal.claim
    def change_after_capture(*args, **kwargs):
        receipt = claim(*args, **kwargs)
        (tmp_path / "helper.py").write_text("VALUE = 'changed'\n")
        (tmp_path / "save.py").write_text("raise AssertionError('new code must not execute')\n")
        return receipt
    monkeypatch.setattr(journal, "claim", change_after_capture)
    result = execute({})
    assert result["status"] == "succeeded", result
    assert result["result"] == {"value": "captured"}


def test_selective_source_refresh_reuses_unaffected_branch_and_preserves_old_run(tmp_path, monkeypatch):
    database = tmp_path / "facts.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("create table facts (value integer)")
        connection.execute("insert into facts values (1)")
    auth = tmp_path / "connections.yaml"
    auth.write_text(yaml.safe_dump({"adapters": {"db": {
        "type": "sqlalchemy", "url": f"sqlite:///{database}",
    }}}))
    path = tmp_path / "dashboard.yaml"
    path.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "test",
        "sources": [
            {"id": name, "type": "sql", "adapter": "db",
             "code": {"inline": query}, "outputs": {"main": {"kind": "table"}},
             "cache": {"mode": "persistent"}}
            for name, query in [("labels", "select value from facts"), ("sales", "select 42 as value")]
        ],
        "dataset_transforms": [{
            "id": "summary", "code": {"inline": "def transform(context):\n    rows = context.table('rows')\n    return {'main': rows.assign(value=rows.value * 10)}\n"},
            "inputs": {"rows": "source:labels/main"},
            "outputs": {"main": {"kind": "table"}},
        }],
        "views": [{"id": name, "template": "metric", "input": reference, "value": "value"}
                  for name, reference in [("labels", "dataset:summary/main"), ("sales", "source:sales/main")]],
    }))
    root, _ = prepare_input(path, auth=auth)
    executor = Executor(load_workspace(root))
    calls = []
    original = SOURCE_RUNNERS["sql"].execute
    def track(request):
        calls.append(request.node_id)
        return original(request)
    monkeypatch.setattr(SOURCE_RUNNERS["sql"], "execute", track)
    first = executor.run("test")
    assert first.status == "ready", first
    assert first.nodes["source:labels"].diagnostics["source_mutation_epoch"] == 0
    assert changed_run_sources(root, first) == {}
    another_session = Executor(load_workspace(root), cache_namespace="another-session")
    assert another_session.run("test").status == "ready"
    cached = another_session.run("test")
    assert cached.nodes["source:labels"].result_origin == "cache"
    original_document = first.model_dump_json()
    with sqlite3.connect(database) as connection:
        connection.execute("update facts set value=2")
    journal = ActionJournal(action_journal_path(root))
    journal.claim("scope", "write", "hash", deadline=time.time() + 60)
    journal.finish("scope", "write", {"status": "succeeded", "invalidations": ["source:labels"]},
                   dashboard_id="test")
    assert source_mutation_epoch(root, "test", "source:labels") == 1
    assert source_mutation_epoch(root, "test", "source:sales") == 0
    assert changed_run_sources(root, first) == {"source:labels": {"observed": 0, "current": 1}}
    assert changed_run_sources(root, cached) == changed_run_sources(root, first)
    calls.clear()
    updated = executor.run("test", query_parameter_state=first.query_parameter_state,
                           _reuse_run=first, _refresh_sources={"source:labels"})
    assert updated.status == "ready", updated
    assert updated.nodes["source:labels"].diagnostics["source_mutation_epoch"] == 1
    assert changed_run_sources(root, updated) == {}
    assert calls == ["source:labels"]
    assert updated.nodes["source:sales"].result_origin == "result"
    assert updated.nodes["dataset:summary"].result_origin == "executed"
    old_store = ArtifactStore(root, first.run_id)
    new_store = ArtifactStore(root, updated.run_id)
    assert old_store.read_table(first.outputs["dataset:summary/main"]).value.tolist() == [10]
    assert new_store.read_table(updated.outputs["dataset:summary/main"]).value.tolist() == [20]
    assert new_store.read_table(updated.outputs["source:sales/main"]).value.tolist() == [42]
    assert first.model_dump_json() == original_document
    assert first.run_id != updated.run_id
    assert updated.run_id in updated.outputs["source:sales/main"].path
    calls.clear()
    ordinary = another_session.run("test")
    assert ordinary.status == "ready"
    assert changed_run_sources(root, ordinary) == {}
    assert ordinary.nodes["source:sales"].result_origin == "cache"
    assert ArtifactStore(root, ordinary.run_id).read_table(
        ordinary.outputs["dataset:summary/main"]
    ).value.tolist() == [20]
    # A duplicate completion must not keep invalidating otherwise valid caches.
    journal.finish("scope", "write", {"status": "succeeded", "invalidations": ["source:labels"]},
                   dashboard_id="test")
    assert source_mutation_epoch(root, "test", "source:labels") == 1
    with pytest.raises(ValueError, match="known Source"):
        executor.run("test", _reuse_run=first, _refresh_sources={"source:missing"})


def test_standalone_action_receipts_survive_content_snapshot_changes(tmp_path):
    path = standalone(tmp_path, [action(code={"inline": "def execute(context): return {}"})])
    original_root, _ = prepare_input(path)
    document = yaml.safe_load(path.read_text())
    document["title"] = "Updated dashboard"
    path.write_text(yaml.safe_dump(document))
    updated_root, _ = prepare_input(path)
    assert original_root != updated_root
    assert action_journal_path(original_root) == action_journal_path(updated_root)
    assert not action_journal_path(original_root).is_relative_to(original_root)
