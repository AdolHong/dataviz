from __future__ import annotations

from pathlib import Path

from sqlalchemy import URL

from dataviz.auth import ConnectionResolver
from dataviz.execution import Executor
from dataviz.workspace import load_workspace, validate_workspace


ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "examples" / "legacy-showcase"


def test_adapter_bindings_and_all_migrated_dashboards_run():
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
        assert result.status == "success", result.model_dump_json(indent=2)


def test_file_adapter_and_bundled_file_are_both_available():
    result = Executor(load_workspace(SHOWCASE)).run("cascade-explorer")
    assert result.nodes["source:uploaded-file"].status == "succeeded"
    assert result.nodes["source:bundled-file"].status == "succeeded"


def test_mysql_and_starrocks_urls_use_local_environment(monkeypatch):
    monkeypatch.setenv("DATAVIZ_MYSQL_USER", "reader")
    monkeypatch.setenv("DATAVIZ_MYSQL_PASSWORD", "mysql-secret")
    monkeypatch.setenv("DATAVIZ_STARROCKS_USER", "analyst")
    monkeypatch.setenv("DATAVIZ_STARROCKS_PASSWORD", "starrocks-secret")
    resolver = ConnectionResolver(SHOWCASE)

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
    resolver = ConnectionResolver(SHOWCASE)
    actual, adapter = resolver.resolve("warehouse", {"warehouse": "demo-duckdb"})
    assert actual == "demo-duckdb"
    assert adapter.type == "duckdb"
