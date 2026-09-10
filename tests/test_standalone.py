from pathlib import Path
import json

import pytest
import yaml
from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.auth import AdapterResolver
from dataviz.errors import WorkspaceError
from dataviz.protocols import DASHBOARD_SCHEMA
from dataviz.standalone import prepare_input
from dataviz.workspace import load_workspace, validate_workspace


def document(tmp_path: Path) -> Path:
    path = tmp_path / "sales.yaml"
    path.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "sales", "title": "Sales",
        "sources": [{"id": "sales", "type": "sql", "adapter": "local",
                     "code": {"inline": "select 42 as revenue"},
                     "outputs": {"main": {"kind": "table"}}}],
        "views": [{"id": "total", "template": "metric", "input": "source:sales/main", "value": "revenue"}],
    }))
    return path


def test_standalone_inline_sql_runs_with_external_auth(tmp_path):
    path = document(tmp_path)
    auth = tmp_path / "connections.yaml"
    auth.write_text("adapters:\n  local:\n    type: sqlalchemy\n    url: 'sqlite:///:memory:'\n")
    root, target = prepare_input(path, auth=auth)
    assert target == "sales"
    assert not validate_workspace(load_workspace(root))
    assert AdapterResolver(root).resolve("local")[1].type == "sqlalchemy"
    assert not (root / "auth").exists()
    result = CliRunner().invoke(app, ["run", str(path), "--auth", str(auth), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "ready"
    assert prepare_input(path, auth=auth)[0] == root
    result_id = json.loads(result.stdout)["result_id"]
    report = tmp_path / "report.html"
    exported = CliRunner().invoke(app, ["report", str(path), result_id, "--auth", str(auth), "--output", str(report)])
    assert exported.exit_code == 0, exported.output
    assert json.loads(exported.stdout)["reexecuted"] is False
    assert "sqlite:///:memory:" not in report.read_text()
    assert str(auth) not in report.read_text()


def test_inline_renderer_and_styles_use_existing_canvas_assets(tmp_path):
    path = document(tmp_path)
    payload = yaml.safe_load(path.read_text())
    payload["canvas"] = {"scripts": [{"inline": "window.example = true;"}],
                         "styles": [{"inline": ".example { color: red; }"}]}
    path.write_text(yaml.safe_dump(payload))
    root, _ = prepare_input(path)
    loaded = load_workspace(root).dashboard("sales")
    assert (loaded.root / loaded.definition.canvas.scripts[0]).read_text() == "window.example = true;"
    assert path.read_text() == yaml.safe_dump(payload)


def test_private_dependency_and_ambiguous_code_fail(tmp_path):
    path = document(tmp_path)
    payload = yaml.safe_load(path.read_text())
    payload["sources"][0]["code"] = {"inline": "select 1", "path": "query.sql"}
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(WorkspaceError, match="Code must"):
        prepare_input(path)
    (tmp_path / ".private.sql").write_text("select 1")
    payload["sources"][0]["code"] = ".private.sql"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(WorkspaceError, match="Private"):
        prepare_input(path)


@pytest.mark.parametrize("kind", ["file", "directory", "workspace", "manifest"])
def test_external_adapter_environment_forms(tmp_path, kind):
    path = document(tmp_path)
    environment = tmp_path / "environment"
    config_dir = environment / "auth"
    config_dir.mkdir(parents=True)
    config = config_dir / "adapters.yaml"
    config.write_text("adapters:\n  local:\n    type: sqlalchemy\n    url: 'sqlite:///:memory:'\n")
    (environment / "workspace.yaml").write_text("schema: dataviz/workspace/v2\nid: environment\n")
    selected = {"file": config, "directory": config_dir, "workspace": environment,
                "manifest": environment / "workspace.yaml"}[kind]
    root, _ = prepare_input(path, auth=selected)
    assert AdapterResolver(root).resolve("local")[1].type == "sqlalchemy"
    assert not list((root / "dashboards").rglob("adapters.yaml"))


def test_dependency_edits_create_new_snapshot_and_reject_escape(tmp_path):
    path = document(tmp_path)
    payload = yaml.safe_load(path.read_text())
    query = tmp_path / "query.sql"
    query.write_text("select 1 as revenue")
    payload["sources"][0]["code"] = "query.sql"
    path.write_text(yaml.safe_dump(payload))
    root, _ = prepare_input(path)
    query.write_text("select 2 as revenue")
    newer, _ = prepare_input(path)
    assert newer != root
    assert (root / "dashboards/main/query.sql").read_text() == "select 1 as revenue"
    payload["sources"][0]["code"] = "../outside.sql"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(WorkspaceError, match="local file"):
        prepare_input(path)


def test_standalone_server_has_no_navigation_and_blocks_snapshot_edits(tmp_path):
    from fastapi.testclient import TestClient
    from dataviz.server import create_app

    root, _ = prepare_input(document(tmp_path))
    with TestClient(create_app(root, watch=False)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert 'class="standalone-dashboard"' in response.text
        assert 'id="sidebar-toggle" disabled' in response.text
        assert client.post("/api/navigation/move", json={}).status_code == 409
        assert client.put("/api/dashboards/sales/parameter-editor", json={}).status_code == 409


def test_standalone_docs_example_is_executable(tmp_path):
    from dataviz.documentation import DOC_TOPICS

    topic = DOC_TOPICS["standalone"]
    path = tmp_path / "sales.yaml"
    auth = tmp_path / "connections.yaml"
    path.write_text(yaml.safe_dump(topic["example"]))
    auth.write_text(yaml.safe_dump(topic["adapter_example"]))
    result = CliRunner().invoke(app, ["validate", str(path), "--auth", str(auth), "--strict"])
    assert result.exit_code == 0, result.output


def test_auth_file_cannot_be_copied_as_dependency(tmp_path):
    path = document(tmp_path)
    auth = tmp_path / "connections.yaml"
    auth.write_text("adapters: {}")
    payload = yaml.safe_load(path.read_text())
    payload["canvas"] = {"styles": ["connections.yaml"]}
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(WorkspaceError, match="Adapter configuration"):
        prepare_input(path, auth=auth)


def test_inline_python_source_runs_without_auth(tmp_path):
    path = document(tmp_path)
    payload = yaml.safe_load(path.read_text())
    (tmp_path / "standalone_helper.py").write_text("REVENUE = 42\n")
    payload["sources"][0].update(type="python", code_dependencies=["standalone_helper.py"],
                                  code={"inline": "import pandas as pd\nfrom standalone_helper import REVENUE\ndef load(context):\n    return pd.DataFrame([{'revenue': REVENUE}])\n"})
    payload["sources"][0].pop("adapter")
    path.write_text(yaml.safe_dump(payload))
    result = CliRunner().invoke(app, ["run", str(path), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "ready"


@pytest.mark.parametrize("layout", ["workspace", "auth", "connections"])
def test_relative_adapter_paths_are_independent_of_reference_form(tmp_path, layout):
    path = document(tmp_path)
    environment = tmp_path / "environment"
    config_dir = environment / "auth" if layout in {"workspace", "auth"} else environment
    config_dir.mkdir(parents=True)
    config = config_dir / "adapters.yaml"
    config.write_text(yaml.safe_dump({"adapters": {
        "local": {"type": "sqlalchemy", "url": "sqlite:///data/sales.db"},
        "files": {"type": "file", "root": "data"},
    }}))
    choices = [config_dir, config]
    if layout == "workspace":
        manifest = environment / "workspace.yaml"
        manifest.write_text("schema: dataviz/workspace/v2\nid: environment\n")
        choices += [environment, manifest]
    for selected in choices:
        root, _ = prepare_input(path, auth=selected)
        resolver = AdapterResolver(root)
        assert resolver.resolve_url("local") == f"sqlite:///{environment / 'data/sales.db'}"
        assert resolver.resolve_path("files", "sales.csv") == environment / "data/sales.csv"


@pytest.mark.parametrize("value", [None, "helper.py", 42, {}])
def test_invalid_dependencies_report_the_field(tmp_path, value):
    path = document(tmp_path)
    payload = yaml.safe_load(path.read_text())
    payload["sources"][0]["code_dependencies"] = value
    path.write_text(yaml.safe_dump(payload))
    result = CliRunner().invoke(app, ["validate", str(path), "--format", "json"])
    assert result.exit_code != 0
    error = json.loads(result.stdout)["error"]
    assert error["type"] == "workspace_error"
    assert "sources[0].code_dependencies" in error["message"]


@pytest.mark.parametrize("payload,field", [
    ({"assets": None}, "assets"),
    ({"assets": {"js": None}}, "assets.js"),
    ({"canvas": None}, "canvas"),
])
def test_invalid_presentation_reports_file_and_field(tmp_path, payload, field):
    path = document(tmp_path)
    presentation = tmp_path / "presentation.yaml"
    presentation.write_text(yaml.safe_dump(payload))
    with pytest.raises(WorkspaceError, match=field) as caught:
        prepare_input(path)
    assert caught.value.file == str(presentation)
