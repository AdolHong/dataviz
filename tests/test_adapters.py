from __future__ import annotations

from pathlib import Path

from sqlalchemy import URL

from dataviz.artifacts import ArtifactStore
from dataviz.auth import AdapterResolver
from dataviz.execution import Executor
from dataviz.workspace import load_workspace, validate_workspace


ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "examples" / "feature-showcase"


def test_adapter_bindings_and_all_example_dashboards_run():
    workspace = load_workspace(SHOWCASE)
    assert not [item for item in validate_workspace(workspace) if item.level == "error"]
    assert set(workspace.dashboards) == {
        "source-lab",
        "chart-gallery",
        "cascade-explorer",
        "parameter-playground",
    }
    executor = Executor(workspace)
    for dashboard_id in workspace.dashboards:
        result = executor.run(dashboard_id)
        assert result.status == "ready", result.model_dump_json(indent=2)


def test_file_adapter_and_bundled_file_are_both_available():
    result = Executor(load_workspace(SHOWCASE)).run("cascade-explorer")
    assert result.nodes["source:uploaded-file"].status == "ready"
    assert result.nodes["source:bundled-file"].status == "ready"


def test_mysql_and_starrocks_urls_use_local_environment(monkeypatch):
    monkeypatch.setenv("DATAVIZ_MYSQL_USER", "reader")
    monkeypatch.setenv("DATAVIZ_MYSQL_PASSWORD", "mysql-secret")
    monkeypatch.setenv("DATAVIZ_STARROCKS_USER", "analyst")
    monkeypatch.setenv("DATAVIZ_STARROCKS_PASSWORD", "starrocks-secret")
    resolver = AdapterResolver(SHOWCASE)

    mysql = resolver.resolve_url("mysql-example")
    starrocks = resolver.resolve_url("starrocks-example")
    assert isinstance(mysql, URL)
    assert isinstance(starrocks, URL)
    assert mysql.drivername == "mysql+pymysql"
    assert mysql.port == 3306
    assert mysql.username == "reader"
    assert starrocks.port == 9030
    assert starrocks.username == "analyst"


def test_dashboard_logical_adapter_resolves_to_workspace_adapter():
    resolver = AdapterResolver(SHOWCASE)
    actual, adapter = resolver.resolve("warehouse", {"warehouse": "demo-duckdb"})
    assert actual == "demo-duckdb"
    assert adapter.type == "duckdb"


def test_python_source_receives_resolved_workspace_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAVIZ_API_USER", "reader")
    monkeypatch.setenv("DATAVIZ_API_PASSWORD", "password-secret")
    monkeypatch.setenv("DATAVIZ_API_TOKEN", "token-secret")
    root = tmp_path / "workspace"
    dashboard = root / "dashboards" / "adapter-source"
    sources = dashboard / "sources"
    sources.mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: adapter-tests
title: Adapter tests
""",
        encoding="utf-8",
    )
    (root / "adapters.local.yaml").write_text(
        """adapters:
  team-api:
    type: http
    username_env: DATAVIZ_API_USER
    password_env: DATAVIZ_API_PASSWORD
    config:
      endpoint: https://api.example.test/v1
      tenant: north
    secrets:
      token: DATAVIZ_API_TOKEN
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v2
kind: dashboard
id: adapter-source
title: Adapter source
adapters:
  api: team-api
sources: [sources/api.yaml]
views: []
""",
        encoding="utf-8",
    )
    (sources / "api.yaml").write_text(
        """schema: dataviz/source/v1
kind: source
id: api
type: python
adapter: api
code: api.py
outputs:
  main: {kind: object}
""",
        encoding="utf-8",
    )
    (sources / "api.py").write_text(
        """def load(context):
    adapter = context.adapter
    return {
        "main": {
            "name": adapter["name"],
            "type": adapter["type"],
            "endpoint": adapter["config"]["endpoint"],
            "tenant": adapter["config"]["tenant"],
            "credentials_resolved": (
                adapter["username"] == "reader"
                and adapter["password"] == "password-secret"
                and adapter["secrets"]["token"] == "token-secret"
            ),
        }
    }
""",
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    assert validate_workspace(workspace) == []
    result = Executor(workspace).run("adapter-source", refresh=True)
    value = ArtifactStore(root, result.run_id).read_value(
        result.outputs["source:api/main"]
    )

    assert result.status == "ready"
    assert value == {
        "name": "team-api",
        "type": "http",
        "endpoint": "https://api.example.test/v1",
        "tenant": "north",
        "credentials_resolved": True,
    }
