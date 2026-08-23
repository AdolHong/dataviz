from __future__ import annotations

import json
from pathlib import Path
import shutil

from typer.testing import CliRunner

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
    assert "Source `params`" in diagnostics["sql_parameter_undeclared"]["hint"]


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
        "schema: dataviz/dashboard/v1\nkind: dashboard\nid: broken\nretired_field: true\n",
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
    assert "dataviz list" in diagnostic["hint"]


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
