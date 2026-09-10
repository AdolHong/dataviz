from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dataviz.errors import WorkspaceError
from dataviz.execution.plan import compile_plan
from dataviz.protocols import DASHBOARD_SCHEMA
from dataviz.workspace.loading.parse_load import load_dashboard
from dataviz.workspace.models import DashboardDefinition


@pytest.fixture
def multipage(tmp_path: Path):
    # Same physical implementation, independent query contracts and result paths.
    (tmp_path / "rules.py").write_text("def load(context):\n    return {'main': []}\n")
    definition = {
        "schema": DASHBOARD_SCHEMA, "id": "holiday", "title": "Holiday analysis",
        "sources": [
            {"id": "annual", "type": "python", "code": "rules.py",
             "query_inputs": {"year": "year"}, "outputs": {"main": {"kind": "table"}}},
            {"id": "history", "type": "python", "code": "rules.py",
             "query_inputs": {"years": "year", "category": "category"},
             "outputs": {"main": {"kind": "table"}}},
        ],
        "pages": [
            {"id": "annual", "title": "One year",
             "query_parameters": [{"id": "year", "type": "single_input", "value_type": "integer", "default": 2025}],
             "views": [{"id": "table", "template": "table", "input": "source:annual/main"}]},
            {"id": "history", "title": "Across years",
             "query_parameters": [
                 {"id": "year", "type": "multiple_input", "value_type": "integer", "default": [2023, 2024]},
                 {"id": "category", "type": "single_input", "value_type": "text", "default": "fruit"}],
             "views": [{"id": "table", "template": "table", "input": "source:history/main"}]},
        ],
    }
    (tmp_path / "dashboard.yaml").write_text(yaml.safe_dump(definition))
    return tmp_path, definition


def test_page_projection_isolates_parameters_and_query_closure(multipage):
    root, _ = multipage
    annual = load_dashboard(root)
    history = load_dashboard(root, page_id="history")
    assert annual.page_id == "annual" and history.page_id == "history"
    assert annual.root == history.root
    assert annual.sources["annual"][1].code == history.sources["history"][1].code
    assert set(compile_plan(annual).nodes) == {"source:annual"}
    assert set(compile_plan(history).nodes) == {"source:history"}
    assert annual.definition.query_parameters[0].default == 2025
    assert history.definition.query_parameters[0].default == [2023, 2024]
    history.definition.query_parameters[0].default.append(2026)
    assert annual.project_definition.pages[1].query_parameters[0].default == [2023, 2024]
    # A selected definition remains valid when serialized as a run snapshot.
    DashboardDefinition.model_validate(history.definition.model_dump(by_alias=True, exclude_unset=True))


def test_unknown_page_does_not_fall_back(multipage):
    root, _ = multipage
    with pytest.raises(WorkspaceError, match="Unknown Page"):
        load_dashboard(root, page_id="missing")


def test_pages_reject_implicit_shared_parameters_and_duplicate_ids(multipage):
    _, definition = multipage
    definition["query_parameters"] = definition["pages"][0]["query_parameters"]
    with pytest.raises(ValidationError, match="belong to each Page"):
        DashboardDefinition.model_validate(definition)
    definition.pop("query_parameters")
    definition["pages"][1]["id"] = "annual"
    with pytest.raises(ValidationError, match="must be unique"):
        DashboardDefinition.model_validate(definition)


def test_no_pages_is_a_normal_single_page_dashboard(multipage):
    root, definition = multipage
    page = definition.pop("pages")[0]
    definition.update({name: page[name] for name in ("views", "query_parameters")})
    definition["sources"] = definition["sources"][:1]
    (root / "dashboard.yaml").write_text(yaml.safe_dump(definition))
    dashboard = load_dashboard(root)
    assert dashboard.page_id is None
    assert set(compile_plan(dashboard).nodes) == {"source:annual"}
    with pytest.raises(WorkspaceError, match="has no Page"):
        load_dashboard(root, page_id="anything")


@pytest.fixture
def page_workspace(multipage, tmp_path):
    import shutil

    root, _ = multipage
    workspace_root = tmp_path / "workspace"
    dashboard_root = workspace_root / "dashboards" / "holiday"
    dashboard_root.mkdir(parents=True)
    for name in ("dashboard.yaml", "rules.py"):
        shutil.copyfile(root / name, dashboard_root / name)
    (workspace_root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v2\nid: demo\ntitle: Demo\n"
    )
    return workspace_root


def test_hot_reload_tracks_inactive_page_and_shared_code(page_workspace):
    from dataviz.server.hot_reload import (
        WorkspaceSemanticSnapshot, WorkspaceChangeJournal,
        classify_page_changes, classify_workspace_change,
    )
    from dataviz.workspace import load_workspace

    root = page_workspace / "dashboards" / "holiday"
    path = root / "dashboard.yaml"
    definition = yaml.safe_load(path.read_text())
    (root / "history.py").write_text((root / "rules.py").read_text())
    definition["sources"][1]["code"] = "history.py"
    path.write_text(yaml.safe_dump(definition))

    def snapshot():
        return WorkspaceSemanticSnapshot.from_workspace(load_workspace(page_workspace))

    before = snapshot()
    (root / "history.py").write_text("def load(context):\n    return {'main': [{'changed': 1}]}\n")
    after = snapshot()
    paths = {str(root / "history.py")}
    assert classify_page_changes(before, after, paths) == {"holiday": {"history": "query"}}
    assert classify_workspace_change(before, after, paths)[0] == {"holiday": "query"}
    event = WorkspaceChangeJournal().publish(
        status="ready", changes={"holiday": "query"},
        page_changes=classify_page_changes(before, after, paths),
    )
    assert event.as_dict()["page_changes"] == {"holiday": {"history": "query"}}

    # Parameter defaults and types belong to their Page, not its sibling.
    before = after
    definition["pages"][1]["query_parameters"][0]["default"] = [2024, 2025]
    path.write_text(yaml.safe_dump(definition))
    after = snapshot()
    assert classify_page_changes(before, after, {str(path)}) == {"holiday": {"history": "query"}}

    # Restore a shared implementation: changing it must invalidate both closures.
    definition["sources"][1]["code"] = "rules.py"
    path.write_text(yaml.safe_dump(definition))
    before = snapshot()
    (root / "rules.py").write_text("def load(context):\n    return {'main': [{'shared': 1}]}\n")
    after = snapshot()
    assert classify_page_changes(before, after, {str(root / "rules.py")}) == {
        "holiday": {"annual": "query", "history": "query"},
    }

    # Presentation edits must not become query invalidations.
    before = after
    definition["pages"][1]["views"][0]["title"] = "Updated details"
    path.write_text(yaml.safe_dump(definition))
    after = snapshot()
    assert classify_page_changes(before, after, {str(path)}) == {"holiday": {"history": "canvas"}}
    definition["pages"].pop()
    path.write_text(yaml.safe_dump(definition))
    removed = snapshot()
    assert classify_page_changes(after, removed, {str(path)}) == {"holiday": {"history": "canvas"}}


def test_executor_records_page_identity_and_rejects_sibling_run(page_workspace):
    from dataviz.errors import ExecutionFailure
    from dataviz.execution import Executor
    from dataviz.execution.fingerprint import ensure_query_run_compatible
    from dataviz.workspace import load_workspace

    workspace_root = page_workspace
    workspace = load_workspace(workspace_root)
    executor = Executor(workspace)
    annual = executor.run("holiday", page_id="annual")
    history = executor.run("holiday", page_id="history")
    assert annual.status == history.status == "ready"
    assert annual.page_id == "annual" and history.page_id == "history"
    assert set(annual.nodes) == {"source:annual"}
    assert set(history.nodes) == {"source:history"}
    assert annual.query_parameter_state["year"]["value"] == 2025
    assert history.query_parameter_state["year"]["value"] == [2023, 2024]
    with pytest.raises(ExecutionFailure, match="another Page"):
        ensure_query_run_compatible(workspace.dashboard("holiday", "history"), annual)


def test_page_detail_does_not_rescan_or_validate_workspace(page_workspace, monkeypatch):
    import importlib
    from fastapi.testclient import TestClient

    server = importlib.import_module("dataviz.server.app")
    app = server.create_app(page_workspace, watch=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("Page navigation must not rescan/validate the Workspace")
    monkeypatch.setattr(server, "load_workspace", forbidden)
    monkeypatch.setattr(server, "validate_workspace", forbidden)
    with TestClient(app) as client:
        for page in ("annual", "history", "annual"):
            response = client.get(f"/api/dashboards/holiday/pages/{page}")
            assert response.status_code == 200, response.text
            assert response.json()["page_id"] == page
        assert client.get("/api/dashboards/holiday/pages/missing").status_code == 404


def test_server_keeps_both_pages_running_and_restorable(page_workspace):
    from fastapi.testclient import TestClient
    from dataviz.server.app import create_app

    # Overlap the runs: starting the second Page must not cancel the first.
    (page_workspace / "dashboards/holiday/rules.py").write_text(
        "import time\ndef load(context):\n    time.sleep(.3)\n    return {'main': []}\n"
    )
    app = create_app(page_workspace, watch=False)
    with TestClient(app) as client:
        manager = app.state.manager
        session = "page_test_session"
        summary = client.get("/api/workspace").json()["dashboards"][0]
        assert [item["id"] for item in summary["pages"]] == ["annual", "history"]
        detail = client.get("/api/dashboards/holiday/pages/history")
        assert detail.status_code == 200, detail.text
        assert detail.json()["page_id"] == "history"
        assert [item["id"] for item in detail.json()["query_parameters"]] == ["year", "category"]
        assert manager.latest_for_session(session) == []  # Navigation metadata never queries.
        assert client.get("/api/dashboards/holiday/pages/missing").status_code == 404
        records = {}
        for page_id in ("annual", "history"):
            response = client.post("/api/dashboards/holiday/runs", json={
                "session_id": session, "page_id": page_id})
            assert response.status_code == 200, response.text
            record = manager.get(response.json()["run_id"], session)
            records[page_id] = record
        for page_id, record in records.items():
            with record.condition:
                assert record.condition.wait_for(lambda record=record: record.result is not None or record.error is not None, timeout=15)
            assert record.status == "ready", record.error
            assert not record.cancel_event.is_set()
            assert manager.latest_for(session, "holiday", page_id).run_id == record.run_id
            response = client.get(f"/api/runs/{record.run_id}", params={"session_id": session})
            assert response.json()["page_id"] == page_id
        restored = client.get("/api/session/runs", params={"session_id": session})
        assert restored.status_code == 200
        payload = restored.json()
        assert {item["page_id"] for item in payload["runs"]} == {"annual", "history"}
        wrong = client.get("/api/dashboards/holiday/canvas", params={
            "session_id": session, "page_id": "history", "run_id": records["annual"].run_id})
        assert wrong.status_code == 409
        history = records["history"]
        canvas = client.get("/api/dashboards/holiday/canvas", params={
            "session_id": session, "page_id": "history", "run_id": history.run_id})
        assert canvas.status_code == 200, canvas.text[:500]
        assert '"page_id": "history"' in canvas.text
        report = client.post("/api/dashboards/holiday/report", json={
            "session_id": session, "run_id": history.run_id})
        assert report.status_code == 200, report.text[:500]
        assert "Across years" in report.text


def test_parameter_editor_targets_page_and_preserves_siblings(page_workspace):
    from fastapi.testclient import TestClient
    from dataviz.server.app import create_app

    path = page_workspace / "dashboards/holiday/dashboard.yaml"
    original = yaml.safe_load(path.read_text())
    app = create_app(page_workspace, watch=False)
    with TestClient(app) as client:
        endpoint = "/api/dashboards/holiday/parameter-editor"
        contract = client.get(endpoint, params={"page_id": "history"}).json()
        assert contract["page_id"] == "history"
        group = next(item for item in contract["groups"] if item["owner"] == "query")
        assert group["items"][0]["default"] == [2023, 2024]
        group["items"][0]["default"] = [2024, 2025]
        group = {"owner": group["owner"], "order": group["order"],
                 "items": [{"id": item["id"], "default": item["default"]} for item in group["items"]]}
        response = client.patch(endpoint, params={"page_id": "history"}, json={
            "revision": contract["revision"], "group": group,
        })
        assert response.status_code == 200, response.text
        assert response.json()["editor"]["page_id"] == "history"
        updated = yaml.safe_load(path.read_text())
        assert updated["pages"][0] == original["pages"][0]
        assert updated["sources"] == original["sources"]
        assert updated["pages"][1]["query_parameters"][0]["default"] == [2024, 2025]
        assert "query_parameters" not in updated
        stale = client.patch(endpoint, params={"page_id": "history"}, json={"revision": contract["revision"], "group": group})
        assert stale.status_code == 409
        assert client.get(endpoint, params={"page_id": "missing"}).status_code == 409


def test_shared_source_versions_identify_only_affected_page_results(page_workspace):
    import copy
    import time
    from fastapi.testclient import TestClient
    from dataviz.server.app import create_app
    from dataviz.execution.action_journal import ActionJournal, action_journal_path

    path = page_workspace / "dashboards/holiday/dashboard.yaml"
    definition = yaml.safe_load(path.read_text())
    isolated = copy.deepcopy(definition["pages"][0])
    isolated["id"] = "isolated"
    definition["sources"].append({"id": "labels", "type": "python", "code": "rules.py",
                                  "outputs": {"main": {"kind": "table"}}})
    for page in definition["pages"]:
        page["views"].append({"id": "labels", "template": "table", "input": "source:labels/main"})
    definition["pages"].append(isolated)
    path.write_text(yaml.safe_dump(definition))
    app = create_app(page_workspace, watch=False)
    session = "shared_pages"
    with TestClient(app) as client:
        records = {}

        def run(page_id):
            response = client.post("/api/dashboards/holiday/runs", json={"session_id": session, "page_id": page_id})
            assert response.status_code == 200, response.text
            record = app.state.manager.get(response.json()["run_id"], session)
            with record.condition:
                assert record.condition.wait_for(lambda: record.result is not None or record.error is not None, timeout=15)
            assert record.status == "ready", record.error
            return record

        for page_id in ("annual", "history", "isolated"):
            records[page_id] = run(page_id)
        original = records["history"].result.model_dump_json()
        journal = ActionJournal(action_journal_path(page_workspace))
        journal.claim("test", "save", "payload", deadline=time.time() + 30)
        journal.finish("test", "save", {"status": "succeeded", "invalidations": ["source:labels"]}, dashboard_id="holiday")

        def states():
            return {item["page_id"]: item for item in client.get("/api/session/runs", params={"session_id": session}).json()["runs"]}

        result = states()
        for page_id in ("annual", "history"):
            assert result[page_id]["data_outdated_sources"] == {"source:labels": {"observed": 0, "current": 1}}
            assert result[page_id]["query_outdated"] is False  # Data changed, not Python/query contract.
            assert result[page_id]["run_id"] == records[page_id].run_id  # No implicit Query.
        assert result["isolated"]["data_outdated_sources"] == {}
        run("annual")
        result = states()
        assert result["annual"]["data_outdated_sources"] == {}
        assert result["history"]["data_outdated_sources"]
        evidence = client.get(f'/api/runs/{records["history"].run_id}', params={"session_id": session}).json()
        assert evidence["data_outdated_sources"] == result["history"]["data_outdated_sources"]
        assert records["history"].result.model_dump_json() == original


def test_validation_covers_nondefault_pages_without_leaking_their_parameters(page_workspace):
    from dataviz.execution import Executor
    from dataviz.errors import ValidationFailure
    from dataviz.workspace import load_workspace
    from dataviz.workspace.loading.contract_validation import validate_workspace

    path = page_workspace / "dashboards/holiday/dashboard.yaml"
    payload = yaml.safe_load(path.read_text())
    payload["sources"][1]["query_inputs"]["category"] = "missing_parameter"
    path.write_text(yaml.safe_dump(payload))
    workspace = load_workspace(page_workspace)
    assert any(item.level == "error" for item in validate_workspace(workspace))
    assert Executor(workspace).ensure_valid("holiday", "annual").page_id == "annual"
    with pytest.raises(ValidationFailure):
        Executor(workspace).ensure_valid("holiday", "history")


@pytest.mark.parametrize("page_count", [0, 1, 2])
def test_cli_page_is_optional(page_workspace, page_count):
    import json
    from typer.testing import CliRunner
    from dataviz.cli import app

    path = page_workspace / "dashboards" / "holiday" / "dashboard.yaml"
    definition = yaml.safe_load(path.read_text())
    if page_count == 0:
        page = definition.pop("pages")[0]
        definition.update({name: page[name] for name in ("views", "query_parameters")})
        definition["sources"] = definition["sources"][:1]
    else:
        definition["pages"] = definition["pages"][:page_count]
    path.write_text(yaml.safe_dump(definition))
    response = CliRunner().invoke(app, ["run", str(page_workspace), "holiday", "--format", "json"])
    assert response.exit_code == 0, response.output
    result = json.loads(response.output)
    assert result.get("page_id") == ("annual" if page_count else None)
    assert result["lineage"]["query_nodes"] == ["source:annual"]


def test_cli_runs_and_exports_selected_page_without_requery(page_workspace, tmp_path):
    import json
    from typer.testing import CliRunner
    from dataviz.cli import app
    from dataviz.analysis.results import AnalysisResultStore

    cli = CliRunner()
    response = cli.invoke(app, ["run", str(page_workspace), "holiday", "--page", "history", "--format", "json"])
    assert response.exit_code == 0, response.output
    result = json.loads(response.output)
    assert result["page_id"] == "history"
    assert result["lineage"]["query_nodes"] == ["source:history"]
    assert result["query_parameter_state"]["year"]["value"] == [2023, 2024]
    sealed = AnalysisResultStore(page_workspace).load(result["result_id"])["result"]
    assert sealed["page_id"] == "history"
    output = tmp_path / "history.html"
    exported = cli.invoke(app, ["report", str(page_workspace), result["result_id"], "--output", str(output)])
    assert exported.exit_code == 0, exported.output
    assert json.loads(exported.output)["reexecuted"] is False
    assert "Across years" in output.read_text()
    assert ".dv-default-shell > .dv-report-header h1" not in output.read_text()
    # Canonical View references resolve in this Page, even when ids overlap.
    target = cli.invoke(app, ["run", str(page_workspace), "holiday::view:table", "--page", "history", "--format", "json"])
    assert target.exit_code == 0, target.output
    assert json.loads(target.output)["page_id"] == "history"


def test_bundle_includes_second_page_assets_without_widening_runs(page_workspace, tmp_path):
    import json
    from dataviz.workspace import bundle_dashboard, load_workspace
    from dataviz.execution import Executor

    assets = page_workspace / "assets"
    assets.mkdir()
    for name in ("annual", "history", "unused"):
        (assets / f"{name}.csv").write_text("value\n42\n")
    workspace_path = page_workspace / "workspace.yaml"
    metadata = yaml.safe_load(workspace_path.read_text())
    metadata["assets"] = {name: {"path": f"assets/{name}.csv", "media_type": "text/csv"}
                          for name in ("annual", "history", "unused")}
    workspace_path.write_text(yaml.safe_dump(metadata))
    path = page_workspace / "dashboards" / "holiday" / "dashboard.yaml"
    definition = yaml.safe_load(path.read_text())
    definition["sources"] = [
        {"id": name, "type": "file", "path": f"asset:{name}", "format": "csv",
         "outputs": {"main": {"kind": "table"}}}
        for name in ("annual", "history")
    ]
    path.write_text(yaml.safe_dump(definition))
    destination = tmp_path / "portable"
    workspace = load_workspace(page_workspace)
    assert set(workspace.dashboard("holiday").sources) == {"annual"}
    bundle_dashboard(workspace, "holiday", destination)
    manifest = json.loads((destination / "dataviz-bundle.json").read_text())
    assert [asset["id"] for asset in manifest["dashboards"][0]["assets"]] == ["annual", "history"]
    assert not (destination / "assets" / "unused.csv").exists()
    portable = load_workspace(destination)
    for name in ("annual", "history"):
        run = Executor(portable).run("holiday", page_id=name)
        assert run.status == "ready"
        assert set(run.nodes) == {f"source:{name}"}
