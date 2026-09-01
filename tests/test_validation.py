from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import shutil

from typer.testing import CliRunner
import yaml

from dataviz.cli import app
from dataviz.validation import VALIDATION_SCHEMA, validate_preflight


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_WORKSPACE = ROOT / "examples" / "minimal-workspace"


def _copy_workspace(tmp_path: Path) -> Path:
    destination = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, destination)
    return destination


def test_validate_preflight_has_stable_ai_contract_and_dashboard_scope(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)

    report = validate_preflight(workspace, dashboard_id="sales-overview")

    assert report["schema"] == VALIDATION_SCHEMA
    assert report["mode"] == "static-preflight"
    assert report["queries_executed"] == 0
    assert report["status"] == "valid"
    assert report["passed"] is True
    assert report["scope"] == {
        "dashboard": "sales-overview",
        "path": "dashboards/sales-overview",
    }
    assert report["summary"]["dashboards_checked"] == 1
    assert {item["id"] for item in report["checks"]} >= {
        "schema-contracts",
        "sql-contracts",
        "data-graph",
    }


def test_validate_detects_undeclared_and_unused_sql_parameters(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    sql = workspace / "dashboards" / "sales-overview" / "sources" / "sales.sql"
    sql.write_text(sql.read_text(encoding="utf-8").replace("$min_query_revenue", "$minimum"), encoding="utf-8")

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostics = {item["code"]: item for item in report["diagnostics"]}

    assert report["status"] == "invalid"
    assert report["passed"] is False
    assert diagnostics["sql_parameter_undeclared"]["details"]["parameters"] == ["minimum"]
    assert diagnostics["sql_parameter_unused"]["details"]["parameters"] == ["min_query_revenue"]
    assert diagnostics["sql_parameter_undeclared"]["category"] == "sql-contracts"
    assert "Source `query_inputs`" in diagnostics["sql_parameter_undeclared"]["hint"]


def test_validate_rejects_query_input_part_for_non_date_range(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["query_inputs"] = {
        "min_query_revenue": {
            "parameter": "min_query_revenue",
            "part": "start",
        }
    }
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "query_input_part_invalid"
    )

    assert report["status"] == "invalid"
    assert diagnostic["field"].endswith("query_inputs.min_query_revenue.part")
    assert "not range_input/date" in diagnostic["message"]


def test_validate_rejects_selection_projection_for_non_multiple_select(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["query_inputs"] = {
        "min_query_revenue": "min_query_revenue",
        "revenue_selection": {
            "parameter": "min_query_revenue",
            "projection": "selection",
        },
    }
    source_sql = workspace / "dashboards" / "sales-overview" / "sources" / "sales.sql"
    source_sql.write_text(
        source_sql.read_text(encoding="utf-8") + "\n-- :revenue_selection\n",
        encoding="utf-8",
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "query_input_selection_cardinality_invalid"
    )

    assert report["status"] == "invalid"
    assert diagnostic["field"].endswith(
        "query_inputs.revenue_selection.projection"
    )


def test_validate_rejects_unknown_control_option_domain(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"][0].pop("initial")
    definition["controls"][0]["options"] = {
        "mode": "infer",
        "source": "source:missing/main",
    }
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "control_option_domain_invalid"
    )

    assert report["status"] == "invalid"
    assert "Unknown output node" in diagnostic["message"]
    assert "options" in diagnostic["hint"]


def test_validate_reports_control_dependency_cycles_before_runtime(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"][0]["depends_on"] = ["dashboard.day"]
    definition["controls"].append(
        {
            "id": "day",

            "field": "day",
            "type": "multiple_select", "value_type": "text",
            "depends_on": ["dashboard.region"],
            "options": {
                "mode": "infer",
                "source": "source:sales/main",
            },
        }
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "control_dependency_cycle"
    )

    assert report["status"] == "invalid"
    assert diagnostic["details"]["cycle"] == [
        "dashboard:sales-overview/day",
        "dashboard:sales-overview/region",
        "dashboard:sales-overview/day",
    ]
    assert "direct Control parents" in diagnostic["hint"]


def test_validate_rejects_fields_outside_the_selected_source_variant(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["options"] = {"silently": "ignored"}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_invalid"
    )

    assert report["status"] == "invalid"
    assert diagnostic["category"] == "schema-contracts"
    assert any(
        item["loc"][-1] == "options" and item["type"] == "extra_forbidden"
        for item in diagnostic["details"]
    )
    assert all("input" not in item for item in diagnostic["details"])
    assert "silently" not in json.dumps(diagnostic, ensure_ascii=False)


def test_validate_reports_unreadable_yaml_without_echoing_file_bytes(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    dashboard_path.write_bytes(b"title: \xffcredential-secret\n")

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_invalid"
    )

    serialized = json.dumps(diagnostic, ensure_ascii=False)
    assert report["status"] == "invalid"
    assert diagnostic["message"] == "YAML file cannot be read as UTF-8"
    assert "UnicodeDecodeError" in serialized
    assert "credential-secret" not in serialized


def test_validate_rejects_impossible_sql_source_output_contract(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["outputs"] = {"result": {"kind": "table"}}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_invalid"
    )

    assert report["status"] == "invalid"
    assert any(
        "SQL Source outputs must be exactly main" in item["msg"]
        for item in diagnostic["details"]
    )


def test_validate_rejects_unknown_file_source_format_before_query(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"] = [
        {
            "id": "sales",
            "type": "file",
            "path": "data/sales.records",
            "outputs": {"main": {"kind": "table"}},
        }
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_invalid"
    )

    assert report["status"] == "invalid"
    assert any(
        "declare format explicitly" in item["msg"]
        for item in diagnostic["details"]
    )


def test_validate_reports_missing_excel_reader_before_query(
    tmp_path: Path,
    monkeypatch,
):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"] = [
        {
            "id": "sales",
            "type": "file",
            "path": "data/sales.xlsx",
            "outputs": {"main": {"kind": "table"}},
        }
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    excel_path = dashboard_path.parent / "data" / "sales.xlsx"
    excel_path.parent.mkdir(exist_ok=True)
    excel_path.write_bytes(b"fixture")
    original_version = importlib.metadata.version

    def version(name: str) -> str:
        if name == "openpyxl":
            raise importlib.metadata.PackageNotFoundError(name)
        return original_version(name)

    monkeypatch.setattr(importlib.metadata, "version", version)

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "file_reader_dependency_unavailable"
    )

    assert report["status"] == "invalid"
    assert diagnostic["category"] == "runtime-dependencies"
    assert "ai-dataviz[excel]" in diagnostic["hint"]


def test_validate_checks_file_source_paths_behind_workspace_adapters(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    adapter_path = workspace / "auth" / "adapters.yaml"
    adapters = yaml.safe_load(adapter_path.read_text(encoding="utf-8"))
    adapters["adapters"]["shared-files"] = {"type": "file", "root": "shared-data"}
    adapter_path.write_text(
        yaml.safe_dump(adapters, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["adapters"]["files"] = "shared-files"
    definition["sources"] = [
        {
            "id": "sales",
            "type": "file",
            "adapter": "files",
            "path": "missing.csv",
            "outputs": {"main": {"kind": "table"}},
        }
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "source_asset_missing"
    )

    assert report["status"] == "invalid"
    assert diagnostic["field"] == "path"
    assert diagnostic["file"].endswith("shared-data/missing.csv")


def test_validate_checks_runtime_credentials_for_referenced_sql_adapter(
    tmp_path: Path,
    monkeypatch,
):
    workspace = _copy_workspace(tmp_path)
    monkeypatch.delenv("DATAVIZ_TEST_MISSING_USER", raising=False)
    adapter_path = workspace / "auth" / "adapters.yaml"
    adapters = yaml.safe_load(adapter_path.read_text(encoding="utf-8"))
    adapters["adapters"]["demo-duckdb"] = {
        "type": "starrocks",
        "host": "warehouse.internal",
        "database": "analytics",
        "username_env": "DATAVIZ_TEST_MISSING_USER",
    }
    adapter_path.write_text(
        yaml.safe_dump(adapters, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "adapter_runtime_configuration_invalid"
    )

    assert report["status"] == "invalid"
    assert diagnostic["field"] == "adapter"
    assert "requires environment variable DATAVIZ_TEST_MISSING_USER" in diagnostic["message"]


def test_validate_loads_referenced_sqlalchemy_driver_without_connecting(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    adapter_path = workspace / "auth" / "adapters.yaml"
    adapters = yaml.safe_load(adapter_path.read_text(encoding="utf-8"))
    adapters["adapters"]["demo-duckdb"] = {
        "type": "sqlalchemy",
        "url": "dataviz_missing_driver://warehouse.invalid/analytics",
    }
    adapter_path.write_text(
        yaml.safe_dump(adapters, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "adapter_sql_driver_invalid"
    )

    assert report["status"] == "invalid"
    assert diagnostic["category"] == "adapter-bindings"
    assert "dataviz_missing_driver" in diagnostic["message"]


def test_validate_view_fields_against_declared_output_schema(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"] = []
    definition["sources"][0]["outputs"]["main"]["schema"] = [
        {"name": "day"},
        {"name": "revenue"},
        {"name": "orders"},
        {"name": "region"},
    ]
    trend = next(view for view in definition["views"] if view["id"] == "revenue-trend")
    trend["x"] = "missing_day"
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "view_field_unknown"
    )

    assert diagnostic["details"]["view"] == "revenue-trend"
    assert diagnostic["details"]["unknown"] == ["missing_day"]


def test_validate_rejects_python_attribute_names_as_dsl_aliases(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["outputs"]["main"]["schema_"] = [
        {"name": "revenue"}
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")

    assert report["status"] == "invalid"
    assert any(
        item["code"] == "dashboard_invalid"
        and "schema_" in json.dumps(item.get("details"), ensure_ascii=False)
        for item in report["diagnostics"]
    )


def test_validate_checks_configurable_local_browser_runtime_assets(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    workspace_path = workspace / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition["runtime"] = {
        **definition.get("runtime", {}),
        "arrow_js": "runtime/missing-arrow.js",
    }
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace)
    diagnostics = {item["code"]: item for item in report["diagnostics"]}

    assert diagnostics["runtime_asset_missing"]["field"] == "runtime.arrow_js"


def test_validate_control_filter_against_declared_output_schema(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["outputs"]["main"]["schema"] = [
        {"name": "day"},
        {"name": "revenue"},
        {"name": "orders"},
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostics = [
        item
        for item in report["diagnostics"]
        if item["code"] == "control_filter_field_unknown"
    ]

    assert diagnostics
    assert all(item["details"]["unknown"] == ["region"] for item in diagnostics)


def test_validate_strict_turns_warning_into_nonzero_cli_exit(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    sql = workspace / "dashboards" / "sales-overview" / "sources" / "sales.sql"
    sql.write_text(
        sql.read_text(encoding="utf-8").replace(
            "where revenue >= $min_query_revenue\n", ""
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    normal = runner.invoke(app, ["validate", str(workspace), "--format", "json"])
    strict = runner.invoke(
        app,
        ["validate", str(workspace), "--format", "json", "--strict"],
    )

    assert normal.exit_code == 0, normal.output
    assert json.loads(normal.output)["status"] == "valid_with_warnings"
    assert strict.exit_code == 1, strict.output
    strict_report = json.loads(strict.output)
    assert strict_report["status"] == "valid_with_warnings"
    assert strict_report["passed"] is False
    assert strict_report["exit_code"] == 1


def test_validate_focus_excludes_another_broken_dashboard(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    broken = workspace / "dashboards" / "broken"
    broken.mkdir()
    (broken / "dashboard.yaml").write_text(
        "schema: dataviz/dashboard/v16\nkind: dashboard\nid: broken\nretired_field: true\n",
        encoding="utf-8",
    )

    full = validate_preflight(workspace)
    focused = validate_preflight(workspace, dashboard_id="sales-overview")

    assert full["status"] == "invalid"
    invalid = next(item for item in full["diagnostics"] if item["code"] == "dashboard_invalid")
    assert invalid["file"] == "dashboards/broken/dashboard.yaml"
    assert invalid["field"] == "retired_field"
    assert invalid["details"]
    assert focused["status"] == "valid"
    assert focused["diagnostics"] == []


def test_validate_unknown_dashboard_is_structured_json(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "validate",
            str(workspace),
            "--dashboard",
            "missing",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1, result.output
    report = json.loads(result.output)
    diagnostic = next(item for item in report["diagnostics"] if item["code"] == "dashboard_not_found")
    assert report["schema"] == VALIDATION_SCHEMA
    assert report["queries_executed"] == 0
    assert diagnostic["details"]["available"] == ["sales-overview"]
    assert "dataviz tree" in diagnostic["hint"]


def test_validate_dashboard_scope_does_not_accept_a_folder_path_alias(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    source = workspace / "dashboards" / "sales-overview"
    destination = workspace / "dashboards" / "团队分析##销售看板"
    source.rename(destination)

    report = validate_preflight(workspace, dashboard_id="团队分析/销售看板")

    assert report["status"] == "invalid"
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_not_found"
    )
    assert diagnostic["details"]["available"] == ["sales-overview"]


def test_cli_docs_publish_the_validation_workflow():
    result = CliRunner().invoke(
        app,
        ["docs", "validation", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    topic = json.loads(result.output)
    assert topic["topic"] == "validation"
    assert "--dashboard" in topic["recommended_command"]
    assert topic["json_contract"]["queries_executed"].startswith("固定为 0")
    assert "sql_parameter_undeclared" in topic["sql_parameter_example"]["errors"]
