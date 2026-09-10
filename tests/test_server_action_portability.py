import json
import time

import pytest
import yaml
from fastapi.testclient import TestClient

from dataviz.protocols import DASHBOARD_SCHEMA, WORKSPACE_SCHEMA
from dataviz.authoring import build_context_payload
from dataviz.server import create_app
from dataviz.server.hot_reload import WorkspaceSemanticSnapshot, classify_workspace_change
from dataviz.workspace import bundle_dashboard, load_workspace


@pytest.fixture
def action_workspace(tmp_path):
    root = tmp_path / "workspace"
    dashboard = root / "dashboards" / "sample"
    code = dashboard / "actions"
    code.mkdir(parents=True)
    (root / "workspace.yaml").write_text(yaml.safe_dump({"schema": WORKSPACE_SCHEMA, "id": "test", "title": "Test"}))
    (dashboard / "rows.csv").write_text("value\n1\n")
    (dashboard / "dashboard.yaml").write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "sample", "title": "Sample",
        "sources": [{"id": "data", "type": "file", "path": "rows.csv", "format": "csv",
                     "outputs": {"main": {"kind": "table"}}}],
        "views": [{"id": "table", "template": "table", "input": "source:data/main"}],
        "server_actions": ["actions/save.yaml"],
    }))
    (code / "save.yaml").write_text(yaml.safe_dump({
        "schema": "dataviz/server-action/v1", "id": "save", "code": "save.py",
        "code_dependencies": ["helper.py"], "resources": {"store": "records"},
        "invalidates": ["view:table"],
    }))
    (code / "save.py").write_text("from helper import message\ndef execute(context):\n    return {'message': message}\n")
    (code / "helper.py").write_text("message = 'original'\n")
    (root / "auth").mkdir()
    (root / "auth" / "adapters.yaml").write_text(yaml.safe_dump({
        "adapters": {"records": {"type": "file", "root": "mutable",
                                  "secrets": {"api_key": "must-not-export-secret"}}},
    }))
    (root / "mutable").mkdir()
    (root / "mutable" / "records.json").write_text('{"private": true}')
    (root / ".dataviz" / "actions").mkdir(parents=True)
    (root / ".dataviz" / "actions" / "receipts.sqlite").write_bytes(b"private-receipts")
    return root, dashboard, code


def test_bundle_carries_action_code_and_binding_names_not_mutable_state(action_workspace, tmp_path):
    root, dashboard, code = action_workspace
    target = tmp_path / "bundle"
    bundle_dashboard(load_workspace(root), "sample", target)
    loaded = load_workspace(target).dashboard("sample")
    definition_path, action = loaded.server_actions["save"]
    assert (definition_path.parent / action.code).read_bytes() == (code / "save.py").read_bytes()
    assert (definition_path.parent / "helper.py").read_bytes() == (code / "helper.py").read_bytes()
    assert action.resources == {"store": "records"}
    manifest = json.loads((target / "dataviz-bundle.json").read_text())
    binding = manifest["dashboards"][0]["adapter_bindings"][0]
    assert binding["logical"] == "records"
    assert binding["configured"] is False
    assert not (target / "auth").exists()
    assert not (target / "mutable").exists()
    assert not (target / ".dataviz").exists()
    for path in target.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert b"must-not-export-secret" not in content
            assert b"private-receipts" not in content
            assert str(root / "mutable").encode() not in content


def test_bundle_records_resources_for_actions_only_on_second_page(action_workspace, tmp_path):
    root, dashboard, _code = action_workspace
    path = dashboard / "dashboard.yaml"
    definition = yaml.safe_load(path.read_text())
    views = definition.pop("views")
    definition["pages"] = [
        {"id": "read", "views": views},
        {"id": "review", "views": views, "server_actions": ["save"]},
    ]
    path.write_text(yaml.safe_dump(definition))
    workspace = load_workspace(root)
    assert workspace.dashboard("sample").server_actions == {}
    destination = tmp_path / "all-pages"
    bundle_dashboard(workspace, "sample", destination)
    manifest = json.loads((destination / "dataviz-bundle.json").read_text())
    assert [binding["logical"] for binding in manifest["dashboards"][0]["adapter_bindings"]] == ["records"]
    assert not (destination / "auth").exists()
    assert not (destination / "mutable").exists()
    assert "save" in load_workspace(destination).dashboard("sample", "review").server_actions


@pytest.mark.parametrize("filename", ["save.py", "helper.py", "save.yaml"])
def test_action_edits_never_invalidate_read_query(action_workspace, filename):
    root, dashboard, code = action_workspace
    before = WorkspaceSemanticSnapshot.from_workspace(load_workspace(root))
    path = code / filename
    if filename.endswith("yaml"):
        definition = yaml.safe_load(path.read_text())
        definition["description"] = "Updated command contract"
        path.write_text(yaml.safe_dump(definition))
    else:
        path.write_text(path.read_text() + "\n# changed\n")
    after = WorkspaceSemanticSnapshot.from_workspace(load_workspace(root))
    changes, _ = classify_workspace_change(before, after, {str(path)})
    assert changes == {"sample": "canvas"}
    assert before.dashboards["sample"].query == after.dashboards["sample"].query
    assert before.dashboards["sample"].analysis == after.dashboards["sample"].analysis


def test_watcher_publishes_action_helper_change_without_query(action_workspace):
    root, dashboard, code = action_workspace
    app = create_app(root, watch=True)
    with TestClient(app):
        journal = app.state.workspace_change_journal
        revision = journal.revision
        (code / "helper.py").write_text("message = 'updated'\n")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            events = journal.after(revision)
            if events:
                assert events[-1].status == "ready"
                assert events[-1].changes == {"sample": "canvas"}
                break
            time.sleep(0.03)
        else:
            raise AssertionError("Action dependency change was not published")


def test_focused_action_context_contains_declared_code_not_credentials(action_workspace):
    root, dashboard, code = action_workspace
    # Inspection must not import code, execute writes or open the resource store.
    (code / "save.py").write_text("raise RuntimeError('must not execute while inspecting')\n")
    workspace = load_workspace(root)
    context = build_context_payload(workspace, workspace.dashboard("sample"), focus="action:save")
    action = context["server_actions"]["save"]
    assert "must not execute" in action["code"]
    assert "original" in action["code_dependencies"]["helper.py"]
    assert context["resource_bindings"] == {"store": {"logical": "records", "actual": "records"}}
    assert "sources" not in context
    assert "must-not-export-secret" not in json.dumps(context)
