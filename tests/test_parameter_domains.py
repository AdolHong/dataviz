from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from typer.testing import CliRunner

from dataviz.artifacts import ArtifactStore
from dataviz.cli import app
from dataviz.errors import ExecutionFailure
from dataviz.execution import Executor
from dataviz.execution.parameter_materializations import ParameterMaterializationStore
import dataviz.execution.parameter_materializations as parameter_materializations
from dataviz.server import create_app
from dataviz.workspace import load_workspace, validate_workspace


def _dashboard(root: Path, dashboard_id: str) -> None:
    dashboard = root / "dashboards" / dashboard_id
    sources = dashboard / "sources"
    sources.mkdir(parents=True)
    (dashboard / "dashboard.yaml").write_text(
        f"""schema: dataviz/dashboard/v14
kind: dashboard
id: {dashboard_id}
title: Domain lab
adapters: {{warehouse: demo}}
parameter_domains: [workspace:/parameter_domains/locations.yaml]
query_parameters:
  - id: province
    type: multiple_select
    value_type: text
    required: true
    default: {{mode: include, values: [GD]}}
    options:
      mode: domain
      source: locations
      value_field: province_code
      label_field: province_name
      keywords_field: province_keywords
  - id: city
    type: multiple_select
    value_type: text
    default: {{mode: all}}
    options:
      mode: domain
      source: locations
      value_field: city_code
      label_field: city_name
      keywords_field: city_keywords
      depends_on: {{province: {{field: province_code}}}}
sources: [sources/metrics.yaml]
views:
  - {{id: rows, title: Rows, template: table, input: source:metrics/main}}
sections:
  - {{id: main, title: Main, views: [rows]}}
""",
        encoding="utf-8",
    )
    (sources / "metrics.yaml").write_text(
        """schema: dataviz/source/v5
kind: source
id: metrics
type: sql
adapter: warehouse
code: metrics.sql
query_filters:
  province: {parameter: province, field: province_code, empty: match_none}
  city: {parameter: city, field: city_code, empty: match_none}
outputs: {main: {kind: table}}
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (sources / "metrics.sql").write_text(
        """select province_code, city_code, value
from (values ('GD', 'SZ', 10), ('GD', 'GZ', 8), ('HN', 'CS', 7))
  as metrics(province_code, city_code, value)
where {{ dataviz_filter:province }} and {{ dataviz_filter:city }}
order by province_code, city_code
""",
        encoding="utf-8",
    )


def _workspace(root: Path, *, second_dashboard: bool = False) -> Path:
    (root / "auth").mkdir(parents=True)
    (root / "parameter_domains").mkdir()
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v1\nkind: workspace\nid: domain-tests\ntitle: Domain tests\n",
        encoding="utf-8",
    )
    (root / "auth" / "adapters.yaml").write_text(
        "adapters:\n  demo:\n    type: duckdb\n    database: ':memory:'\n",
        encoding="utf-8",
    )
    (root / "parameter_domains" / "locations.yaml").write_text(
        """schema: dataviz/parameter-domain/v2
kind: parameter_domain
id: locations
type: sql
adapter: warehouse
code: locations.sql
materialization: {refresh_after_seconds: 43200, expire_after_seconds: 604800}
""",
        encoding="utf-8",
    )
    (root / "parameter_domains" / "locations.sql").write_text(
        """select * from (values
('GD', '广东', 'guang dong', 'SZ', '深圳', 'shen zhen'),
('GD', '广东', 'guang dong', 'GZ', '广州', 'guang zhou'),
('HN', '湖南', 'hu nan', 'CS', '长沙', 'chang sha')
) as locations(province_code, province_name, province_keywords, city_code, city_name, city_keywords)
""",
        encoding="utf-8",
    )
    _dashboard(root, "domain-lab")
    if second_dashboard:
        _dashboard(root, "domain-lab-copy")
    return root


def _store(root: Path):
    workspace = load_workspace(root)
    return workspace, workspace.dashboard("domain-lab"), ParameterMaterializationStore(workspace)


def _use_single_select_parent(root: Path) -> None:
    """Make province a scalar parent without using it as a Source query_filter."""

    dashboard = root / "dashboards" / "domain-lab" / "dashboard.yaml"
    definition = dashboard.read_text(encoding="utf-8")
    definition = definition.replace("type: multiple_select", "type: single_select", 1)
    definition = definition.replace(
        "default: {mode: include, values: [GD]}",
        "default: {mode: value, value: GD}",
        1,
    )
    dashboard.write_text(definition, encoding="utf-8")

    source = root / "dashboards" / "domain-lab" / "sources" / "metrics.yaml"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "  province: {parameter: province, field: province_code}\n", ""
        ),
        encoding="utf-8",
    )


def test_shared_domain_contract_contains_only_topology(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    dashboard = workspace.dashboard("domain-lab")

    assert validate_workspace(workspace) == []
    assert dashboard.parameter_domain_contract.as_dict() == {
        "schema": "dataviz/parameter-domain-contract/v3",
        "contract_hash": dashboard.parameter_domain_contract.contract_hash,
        "dependencies": {"province": [], "city": ["province"]},
        "descendants": {"province": ["city"], "city": []},
        "order": ["province", "city"],
        "domain_consumers": {"locations": ["city", "province"]},
    }
    assert "深圳" not in json.dumps(
        dashboard.parameter_domain_contract.as_dict(), ensure_ascii=False
    )


def test_materialization_is_shared_and_lookup_filters_searches_and_pages(tmp_path: Path):
    root = _workspace(tmp_path / "workspace", second_dashboard=True)
    workspace, dashboard, store = _store(root)
    record = store.build(dashboard, "locations")

    copied = workspace.dashboard("domain-lab-copy")
    assert store.identity(dashboard, "locations")[0] == store.identity(copied, "locations")[0]
    assert store.status(copied, "locations").generation == record.generation

    first = store.lookup(dashboard, "province", limit=1)
    assert first["status"] == "ready"
    assert first["total"] == 2
    assert len(first["items"]) == 1
    second = store.lookup(dashboard, "province", limit=1, cursor=first["next_cursor"])
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None

    cities = store.lookup(
        dashboard,
        "city",
        parent_states={"province": {"selection": "include", "value": ["GD"]}},
    )
    assert [item["value"] for item in cities["items"]] == ["GZ", "SZ"]
    excluded = store.lookup(
        dashboard,
        "city",
        parent_states={"province": {"selection": "exclude", "value": ["GD"]}},
    )
    assert [item["value"] for item in excluded["items"]] == ["CS"]
    none = store.lookup(
        dashboard,
        "city",
        parent_states={"province": {"selection": "none", "value": []}},
    )
    assert none["items"] == []
    searched = store.lookup(dashboard, "city", search="shen zhen")
    assert [item["value"] for item in searched["items"]] == ["SZ"]

    selected_outside_search = store.lookup(
        dashboard,
        "city",
        parent_states={"province": {"selection": "include", "value": ["GD"]}},
        search="guang zhou",
        selected=["SZ"],
    )
    assert [item["value"] for item in selected_outside_search["items"]] == ["GZ"]
    assert selected_outside_search["selected_items"] == [
        {
            "value": "SZ",
            "label": "深圳",
            "keywords": ["shen zhen"],
            "available": True,
        }
    ]


def test_lookup_filters_by_single_select_parent_canonical_scalar_state(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _use_single_select_parent(root)
    _workspace_loaded, dashboard, store = _store(root)
    store.build(dashboard, "locations")

    cities = store.lookup(
        dashboard,
        "city",
        parent_states={"province": {"value": "GD"}},
    )
    assert [item["value"] for item in cities["items"]] == ["GZ", "SZ"]

    cleared = store.lookup(
        dashboard,
        "city",
        parent_states={"province": {"value": None}},
    )
    assert cleared["items"] == []


def test_server_lookup_accepts_single_select_parent_state_from_browser(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _use_single_select_parent(root)
    workspace, dashboard, store = _store(root)
    store.build(dashboard, "locations")
    client = TestClient(create_app(workspace.root, watch=False))

    response = client.post(
        "/api/dashboards/domain-lab/parameter-domains/lookup",
        json={
            "session_id": "domain_session",
            "parameter": "city",
            "parent_states": {"province": {"value": "GD"}},
        },
    )

    assert response.status_code == 200
    assert [item["value"] for item in response.json()["items"]] == ["GZ", "SZ"]


def test_lookup_preserves_finite_selected_operands_and_marks_unavailable(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _workspace_loaded, dashboard, store = _store(root)
    store.build(dashboard, "locations")

    payload = store.lookup(dashboard, "city", selected=["SZ", "LEGACY"])

    assert payload["selected_items"][0] == {
        "value": "SZ",
        "label": "深圳",
        "keywords": ["shen zhen"],
        "available": True,
    }
    assert payload["selected_items"][1] == {
        "value": "LEGACY",
        "label": "LEGACY",
        "available": False,
    }


def test_cursor_is_generation_bound(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _workspace_loaded, dashboard, store = _store(root)
    store.build(dashboard, "locations")
    cursor = store.lookup(dashboard, "city", limit=1)["next_cursor"]
    domain_sql = root / "parameter_domains" / "locations.sql"
    domain_sql.write_text(domain_sql.read_text(encoding="utf-8").replace("长沙", "长沙市"), encoding="utf-8")
    workspace, dashboard, store = _store(root)
    store.build(dashboard, "locations", force=True)

    with pytest.raises(ExecutionFailure) as failure:
        store.lookup(dashboard, "city", limit=1, cursor=cursor)
    assert failure.value.details["code"] == "parameter_lookup_cursor_stale"


def test_stale_generation_remains_readable_while_refresh_starts(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _workspace_loaded, dashboard, store = _store(root)
    initial = store.build(dashboard, "locations")
    with sqlite3.connect(store.index_path) as connection:
        connection.execute(
            "UPDATE materializations SET refresh_due_at=? WHERE materialization_key=?",
            (time.time() - 1, initial.key),
        )
    stale = store.ensure(dashboard, "locations", background=True)
    assert stale.generation == initial.generation
    assert stale.freshness() == "stale"


def test_prune_never_removes_current_generation(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _workspace_loaded, dashboard, store = _store(root)
    first = store.build(dashboard, "locations")
    second = store.build(dashboard, "locations", force=True)
    assert first.generation != second.generation

    preview = store.prune_generations()
    assert [item["generation"] for item in preview["generations"]] == [first.generation]
    applied = store.prune_generations(apply=True)
    assert applied["deleted_count"] == 1
    assert second.data_path.is_file()


def test_executor_uses_canonical_state_without_materializing_candidates(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    (root / "parameter_domains" / "locations.sql").write_text(
        "this SQL must not run during Dashboard execution", encoding="utf-8"
    )

    result = Executor(workspace).run(
        "domain-lab",
        query_parameter_state={
            "province": {"selection": "include", "value": ["GD"]},
            "city": {"selection": "exclude", "value": ["GZ"]},
        },
    )

    assert result.status == "ready"
    assert result.query_parameter_state == {
        "province": {"selection": "include", "value": ["GD"]},
        "city": {"selection": "exclude", "value": ["GZ"]},
    }
    frame = ArtifactStore(root, result.run_id).read_table(result.outputs["source:metrics/main"])
    assert frame[["province_code", "city_code"]].to_dict("records") == [
        {"province_code": "GD", "city_code": "SZ"}
    ]


def test_cli_prewarm_status_and_lookup_are_bounded(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    runner = CliRunner()
    prewarm = runner.invoke(app, ["parameters", "prewarm", str(root), "domain-lab"])
    assert prewarm.exit_code == 0, prewarm.output
    assert json.loads(prewarm.output)["materializations"][0]["rows"] == 3

    status = runner.invoke(app, ["parameters", "status", str(root), "domain-lab"])
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["materializations"][0]["freshness"] == "fresh"

    lookup = runner.invoke(
        app,
        [
            "parameters", "lookup", str(root), "domain-lab", "city",
            "--parent-state", 'province={"selection":"include","value":["GD"]}',
            "--search", "深", "--limit", "1",
        ],
    )
    assert lookup.exit_code == 0, lookup.output
    payload = json.loads(lookup.output)
    assert payload["items"] == [
        {"value": "SZ", "label": "深圳", "keywords": ["shen zhen"]}
    ]


def test_server_lookup_does_not_embed_rows_or_lock_workspace_navigation(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    client = TestClient(create_app(root, watch=False))
    workspace_payload = client.get("/api/workspace")
    assert workspace_payload.status_code == 200
    serialized = workspace_payload.text
    assert "locations.sql" not in serialized
    assert "深圳" not in serialized

    lookup = client.post(
        "/api/dashboards/domain-lab/parameter-domains/lookup",
        json={"session_id": "domain_session", "parameter": "city"},
    )
    assert lookup.status_code == 200
    assert lookup.json()["status"] in {"building", "ready"}
    assert client.get("/").status_code == 200


def test_materialization_guards_are_server_side(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    definition = root / "parameter_domains" / "locations.yaml"
    definition.write_text(
        definition.read_text(encoding="utf-8").replace(
            "materialization:", "max_rows: 2\nmaterialization:"
        ),
        encoding="utf-8",
    )
    _workspace_loaded, dashboard, store = _store(root)
    with pytest.raises(ExecutionFailure) as failure:
        store.build(dashboard, "locations")
    assert failure.value.details["code"] == "parameter_materialization_row_limit"


def test_portable_bundle_copies_shared_domain_closure_without_runtime_state_or_secrets(
    tmp_path: Path,
):
    root = _workspace(tmp_path / "workspace")
    workspace, dashboard, store = _store(root)
    store.build(dashboard, "locations")
    destination = tmp_path / "portable"

    runner = CliRunner()
    first = runner.invoke(app, ["bundle", str(root), "domain-lab", str(destination)])
    assert first.exit_code == 0, first.output
    payload = json.loads(first.output)
    assert payload["schema"] == "dataviz/dashboard-bundle/v1"
    assert payload["materializations_copied"] is False
    assert payload["credentials_copied"] is False

    assert (destination / "dashboards" / "domain-lab" / "dashboard.yaml").is_file()
    assert (destination / "parameter_domains" / "locations.yaml").is_file()
    assert (destination / "parameter_domains" / "locations.sql").is_file()
    assert not (destination / ".dataviz").exists()
    assert not (destination / "auth").exists()
    bundled = load_workspace(destination).dashboard("domain-lab")
    assert bundled.parameter_domains["locations"][0] == (
        destination / "parameter_domains" / "locations.yaml"
    )
    manifest = json.loads((destination / "dataviz-bundle.json").read_text(encoding="utf-8"))
    assert manifest["dashboards"][0]["adapter_bindings"] == [
        {
            "actual": "demo",
            "configured": False,
            "description": "",
            "logical": "warehouse",
            "type": "duckdb",
            "visibility_scope": "default",
        }
    ]
    assert "password" not in json.dumps(manifest).casefold()

    repeated = runner.invoke(app, ["bundle", str(root), "domain-lab", str(destination)])
    assert repeated.exit_code == 0, repeated.output
    assert "parameter_domains/locations.sql" in json.loads(repeated.output)["reused"]

    (destination / "parameter_domains" / "locations.sql").write_text(
        "select 'conflict'", encoding="utf-8"
    )
    conflict = runner.invoke(app, ["bundle", str(root), "domain-lab", str(destination)])
    assert conflict.exit_code == 1
    assert "dashboard_bundle_content_conflict" in conflict.output


def test_expired_generation_is_not_served_and_restarts_as_building(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _workspace_loaded, dashboard, store = _store(root)
    record = store.build(dashboard, "locations")
    with sqlite3.connect(store.index_path) as connection:
        connection.execute(
            "UPDATE materializations SET refresh_due_at=?, expires_at=? "
            "WHERE materialization_key=?",
            (time.time() - 2, time.time() - 1, record.key),
        )

    response = store.lookup(dashboard, "city", selected=["LEGACY"])

    assert response["status"] in {"building", "unavailable"}
    assert response["generation"] is None
    assert response["items"] == []
    assert response["selected_items"] == [
        {"value": "LEGACY", "label": "LEGACY", "available": False}
    ]


def test_failed_refresh_preserves_readable_stale_generation(tmp_path: Path, monkeypatch):
    root = _workspace(tmp_path / "workspace")
    _workspace_loaded, dashboard, store = _store(root)
    initial = store.build(dashboard, "locations")
    with sqlite3.connect(store.index_path) as connection:
        connection.execute(
            "UPDATE materializations SET refresh_due_at=? WHERE materialization_key=?",
            (time.time() - 1, initial.key),
        )

    def fail_refresh(**_kwargs):
        raise ExecutionFailure(
            "warehouse unavailable",
            details={"code": "parameter_materialization_test_failure"},
        )

    monkeypatch.setattr(parameter_materializations, "execute_sql_query", fail_refresh)
    with pytest.raises(ExecutionFailure):
        store.build(dashboard, "locations", force=True)

    failed = store.status(dashboard, "locations")
    assert failed.generation == initial.generation
    assert failed.status == "refresh_failed"
    assert failed.freshness() == "stale"
    response = store.lookup(dashboard, "city")
    assert response["status"] == "ready"
    assert response["generation"] == initial.generation
    assert response["last_error"]["code"] == "parameter_materialization_test_failure"


def test_cross_store_refresh_lease_and_restart_recovery_share_one_generation(
    tmp_path: Path, monkeypatch
):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    dashboard = workspace.dashboard("domain-lab")
    first_store = ParameterMaterializationStore(workspace)
    second_store = ParameterMaterializationStore(workspace)
    original = parameter_materializations.execute_sql_query
    calls = 0
    entered = threading.Event()
    release = threading.Event()

    def delayed_query(**kwargs):
        nonlocal calls
        calls += 1
        entered.set()
        release.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(parameter_materializations, "execute_sql_query", delayed_query)
    result: list = []
    thread = threading.Thread(
        target=lambda: result.append(first_store.build(dashboard, "locations", force=True))
    )
    thread.start()
    assert entered.wait(timeout=5)
    competing = second_store.build(dashboard, "locations", force=True)
    release.set()
    thread.join(timeout=5)

    assert calls == 1
    assert competing.status == "building"
    assert result[0].generation
    restarted = ParameterMaterializationStore(load_workspace(root))
    recovered_dashboard = restarted.workspace.dashboard("domain-lab")
    assert restarted.status(recovered_dashboard, "locations").generation == result[0].generation


def test_expired_refresh_lease_is_reclaimed_after_interrupted_builder(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _workspace_loaded, dashboard, store = _store(root)
    key, definition_hash, _code_path, _adapter = store.identity(dashboard, "locations")
    with sqlite3.connect(store.index_path) as connection:
        connection.execute(
            "INSERT INTO materializations "
            "(materialization_key, domain_id, definition_hash, status, rows, lease_until, updated_at) "
            "VALUES (?, ?, ?, 'building', 0, ?, 'interrupted')",
            (key, "locations", definition_hash, time.time() - 1),
        )

    recovered = ParameterMaterializationStore(load_workspace(root))
    record = recovered.build(recovered.workspace.dashboard("domain-lab"), "locations")

    assert record.status == "ready"
    assert record.generation


def test_visibility_scope_changes_materialization_identity(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _workspace_loaded, dashboard, store = _store(root)
    first_key = store.identity(dashboard, "locations")[0]
    adapter_path = root / "auth" / "adapters.yaml"
    adapter_path.write_text(
        adapter_path.read_text(encoding="utf-8").replace(
            "type: duckdb", "type: duckdb\n    visibility_scope: restricted"
        ),
        encoding="utf-8",
    )
    workspace = load_workspace(root)
    changed = ParameterMaterializationStore(workspace)
    second_key = changed.identity(workspace.dashboard("domain-lab"), "locations")[0]
    assert first_key != second_key


def test_reader_pin_blocks_prune_until_lookup_generation_is_released(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _workspace_loaded, dashboard, store = _store(root)
    first = store.build(dashboard, "locations")
    with store._reader_pin(first):
        second = store.build(dashboard, "locations", force=True)
        assert store.prune_generations()["generations"] == []
    candidates = store.prune_generations()["generations"]
    assert [item["generation"] for item in candidates] == [first.generation]
    assert second.data_path.is_file()


def test_fixed_parameter_domain_benchmark_is_bounded():
    payload = json.loads(
        (
            Path(__file__).parents[1]
            / "benchmarks"
            / "results"
            / "parameter-domain-lookup-2026-09-01.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["row_counts"] == [10_000, 100_000, 250_000]
    assert [case["rows"] for case in payload["cases"]] == payload["row_counts"]
    assert all(case["bounded"] for case in payload["cases"])
    assert all(case["first_page_items"] == 50 for case in payload["cases"])
    assert all(case["response_bytes"] < 16_384 for case in payload["cases"])
