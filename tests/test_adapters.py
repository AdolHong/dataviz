from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import URL
import pytest

from dataviz.artifacts import ArtifactStore
from dataviz.auth import AdapterResolver
from dataviz.errors import SourceFailure
from dataviz.execution import Executor
from dataviz.redaction import adapter_secret_values, redact_text
from dataviz.schema_docs import schema_model_contract
from dataviz.workspace import load_workspace, validate_workspace


ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "examples" / "feature-showcase"


@pytest.fixture(scope="module", autouse=True)
def _isolate_repository_workspaces(isolated_workspace):
    global SHOWCASE
    SHOWCASE = isolated_workspace(SHOWCASE)


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


def test_adapter_configuration_has_one_canonical_base_and_local_override(tmp_path: Path):
    root = tmp_path / "workspace"
    auth = root / "auth"
    auth.mkdir(parents=True)
    (root / "adapters.yaml").write_text(
        "adapters:\n  root-file: {type: duckdb, database: root-file.db}\n",
        encoding="utf-8",
    )
    (root / "adapters.local.yaml").write_text(
        "adapters:\n  root-local: {type: duckdb, database: root-local.db}\n",
        encoding="utf-8",
    )
    (auth / "adapters.example.yaml").write_text(
        "adapters:\n  example: {type: duckdb, database: example.db}\n",
        encoding="utf-8",
    )
    (auth / "adapters.yaml").write_text(
        """adapters:
  warehouse:
    type: starrocks
    host: warehouse.internal
    port: 9030
    database: analytics
    username_env: DATAVIZ_USER
    options: {charset: utf8mb4, connect_timeout: 20}
    config: {catalog: committed, timezone: Asia/Shanghai}
    secrets: {token: DATAVIZ_TOKEN}
""",
        encoding="utf-8",
    )
    (auth / "adapters.local.yaml").write_text(
        """adapters:
  warehouse:
    password_env: DATAVIZ_PASSWORD
    options: {connect_timeout: 5}
    config: {catalog: local}
    secrets: {client_secret: DATAVIZ_CLIENT_SECRET}
""",
        encoding="utf-8",
    )

    resolver = AdapterResolver(root)

    assert set(resolver.adapters) == {"warehouse"}
    adapter = resolver.adapters["warehouse"]
    assert adapter.type == "starrocks"
    assert adapter.host == "warehouse.internal"
    assert adapter.port == 9030
    assert adapter.database == "analytics"
    assert adapter.username_env == "DATAVIZ_USER"
    assert adapter.password_env == "DATAVIZ_PASSWORD"
    assert adapter.options == {"charset": "utf8mb4", "connect_timeout": 5}
    assert adapter.config == {"catalog": "local", "timezone": "Asia/Shanghai"}
    assert adapter.secrets == {
        "token": "DATAVIZ_TOKEN",
        "client_secret": "DATAVIZ_CLIENT_SECRET",
    }
    for ignored in ("root-file", "root-local", "example"):
        with pytest.raises(SourceFailure, match="not configured"):
            resolver.resolve(ignored)


@pytest.mark.parametrize(
    "adapter_yaml, field",
    [
        ("type: mysql\n    username: analyst\n    host: db\n    database: metrics", "username"),
        ("type: mysql\n    password: do-not-print\n    host: db\n    database: metrics", "password"),
        ("type: sqlalchemy\n    url: mysql+pymysql://analyst:do-not-print@db/metrics", "url credentials"),
        ("type: sqlalchemy\n    url: mysql+pymysql://db/metrics?token=do-not-print", "url query.token"),
        ("type: http\n    config: {api_key: do-not-print}", "config.api_key"),
    ],
)
def test_committed_adapter_file_rejects_direct_credentials_without_echoing_values(
    tmp_path: Path,
    adapter_yaml: str,
    field: str,
):
    root = tmp_path / "workspace"
    auth = root / "auth"
    auth.mkdir(parents=True)
    (auth / "adapters.yaml").write_text(
        f"adapters:\n  warehouse:\n    {adapter_yaml}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as failure:
        AdapterResolver(root)

    assert field in str(failure.value)
    assert "do-not-print" not in str(failure.value)


def test_local_adapter_override_accepts_direct_credentials(tmp_path: Path):
    root = tmp_path / "workspace"
    auth = root / "auth"
    auth.mkdir(parents=True)
    (auth / "adapters.yaml").write_text(
        """adapters:
  warehouse:
    type: mysql
    host: db.internal
    database: metrics
""",
        encoding="utf-8",
    )
    (auth / "adapters.local.yaml").write_text(
        """adapters:
  warehouse:
    username: analyst
    password: local-secret
""",
        encoding="utf-8",
    )

    _, adapter = AdapterResolver(root).resolve("warehouse")

    assert adapter.username == "analyst"
    assert adapter.password == "local-secret"


def test_sensitive_url_query_values_are_redacted_from_runtime_errors():
    token = "local-url-token"
    adapter = {"url": f"mysql+pymysql://db/metrics?access_token={token}"}

    secrets = adapter_secret_values(adapter)

    assert token in secrets
    assert token not in redact_text(f"connection failed: {adapter['url']}", secrets)


def test_builtin_adapter_rejects_fields_its_runtime_does_not_use(tmp_path: Path):
    root = tmp_path / "workspace"
    auth = root / "auth"
    auth.mkdir(parents=True)
    (auth / "adapters.yaml").write_text(
        "adapters:\n  files: {type: file, root: data, database: ignored.db}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"Adapter files type file does not use fields: database",
    ):
        AdapterResolver(root)


def test_sqlalchemy_adapter_requires_an_explicit_connection_source(tmp_path: Path):
    root = tmp_path / "workspace"
    auth = root / "auth"
    auth.mkdir(parents=True)
    (auth / "adapters.yaml").write_text(
        "adapters:\n  warehouse: {type: sqlalchemy}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"Adapter warehouse type sqlalchemy requires url or env",
    ):
        AdapterResolver(root)


def test_invalid_adapter_contract_is_reported_by_workspace_validation(tmp_path: Path):
    root = tmp_path / "workspace"
    (root / "auth").mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v1\nkind: workspace\nid: adapter-validation\n",
        encoding="utf-8",
    )
    (root / "auth" / "adapters.yaml").write_text(
        "adapters:\n  warehouse: {type: sqlalchemy}\n",
        encoding="utf-8",
    )

    diagnostics = validate_workspace(load_workspace(root))

    assert any(item.code == "adapter_configuration_invalid" for item in diagnostics)


def test_adapter_schema_docs_expose_strict_builtin_contracts():
    contract = schema_model_contract("adapter", full=True)

    assert contract["adapter_contracts"]["file"]["optional"] == ["root"]
    assert contract["adapter_contracts"]["sqlalchemy"]["connection"] == "url or env"
    assert (
        contract["json_schema"]["x-dataviz-adapter-contracts"]
        == contract["adapter_contracts"]
    )


def test_executor_resolves_adapter_files_once_per_query_run(tmp_path: Path):
    root = tmp_path / "workspace"
    dashboard = root / "dashboards" / "adapter-refresh"
    auth = root / "auth"
    dashboard.mkdir(parents=True)
    auth.mkdir()
    (root / "data-a").mkdir()
    (root / "data-b").mkdir()
    (root / "data-a" / "rows.csv").write_text("value\nA\n", encoding="utf-8")
    (root / "data-b" / "rows.csv").write_text("value\nB\n", encoding="utf-8")
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: adapter-refresh
title: Adapter refresh
""",
        encoding="utf-8",
    )
    adapter_path = auth / "adapters.yaml"
    adapter_path.write_text(
        "adapters:\n  files: {type: file, root: data-a}\n",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v5
kind: dashboard
id: adapter-refresh
adapters: {data: files}
sources:
  - id: rows
    type: file
    adapter: data
    path: rows.csv
    outputs: {main: {kind: table}}
views:
  - {id: rows, template: table, input: source:rows/main}
""",
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    executor = Executor(workspace, cache_namespace="same-tab")
    first = executor.run("adapter-refresh")
    first_frame = ArtifactStore(root, first.run_id).read_table(
        first.outputs["source:rows/main"]
    )

    adapter_path.write_text(
        "adapters:\n  files: {type: file, root: data-b}\n",
        encoding="utf-8",
    )
    second = executor.run("adapter-refresh")
    second_frame = ArtifactStore(root, second.run_id).read_table(
        second.outputs["source:rows/main"]
    )

    assert first_frame["value"].tolist() == ["A"]
    assert second_frame["value"].tolist() == ["B"]
    assert second.nodes["source:rows"].result_origin == "executed"


def test_python_source_receives_resolved_workspace_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAVIZ_API_USER", "reader")
    monkeypatch.setenv("DATAVIZ_API_PASSWORD", "password-secret")
    monkeypatch.setenv("DATAVIZ_API_TOKEN", "token-secret")
    root = tmp_path / "workspace"
    dashboard = root / "dashboards" / "adapter-source"
    sources = dashboard / "sources"
    sources.mkdir(parents=True)
    (root / "auth").mkdir()
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: adapter-tests
title: Adapter tests
""",
        encoding="utf-8",
    )
    (root / "auth" / "adapters.local.yaml").write_text(
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
        """schema: dataviz/dashboard/v5
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
        """schema: dataviz/source/v2
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
    secrets = AdapterResolver(root).redaction_values("api", {"api": "team-api"})
    assert {"reader", "password-secret", "token-secret"} <= set(secrets)
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

    (sources / "api.py").write_text(
        """def load(context):
    context.progress(0.25, "using password-secret")
    context.log("token token-secret", password="password-secret")
    raise RuntimeError("adapter failed with password-secret and token-secret")
""",
        encoding="utf-8",
    )
    failed = Executor(load_workspace(root)).run("adapter-source", refresh=True)
    serialized = failed.model_dump_json()

    assert failed.status == "error"
    assert "password-secret" not in serialized
    assert "token-secret" not in serialized
    assert "[REDACTED]" in serialized
    log = failed.nodes["source:api"].log
    assert log is not None
    log_value = ArtifactStore(root, failed.run_id).read_value(log)
    assert "password-secret" not in json.dumps(log_value)
    assert "token-secret" not in json.dumps(log_value)


def test_invalid_local_adapter_schema_never_echoes_credential_values(tmp_path):
    root = tmp_path / "workspace"
    (root / "auth").mkdir(parents=True)
    (root / "auth" / "adapters.local.yaml").write_text(
        """adapters:
  warehouse:
    type: mysql
    host: db.internal
    database: analytics
    username: reader-secret
    password: [password-secret]
""",
        encoding="utf-8",
    )

    with pytest.raises(SourceFailure) as failure:
        AdapterResolver(root)

    serialized = json.dumps(failure.value.as_dict(), ensure_ascii=False)
    assert failure.value.details["code"] == "adapter_schema_invalid"
    assert "reader-secret" not in serialized
    assert "password-secret" not in serialized
    assert "input" not in failure.value.details["errors"][0]
