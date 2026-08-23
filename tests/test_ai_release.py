from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from dataviz.authoring_log import AUTHORING_LOG_NAME, authoring_log_report
from dataviz.cli import app
from dataviz.frontend_adapters import frontend_adapter_catalog, frontend_adapter_source
from dataviz.migrations import CURRENT_SCHEMAS, migrate_workspace
from dataviz.schema_docs import schema_catalog, schema_model_contract
from dataviz.workspace import load_workspace
from dataviz.workspace.models import DashboardDefinition, SourceDefinition


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_WORKSPACE = ROOT / "examples" / "minimal-workspace"


def _init_workspace(path: Path) -> Path:
    result = CliRunner().invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output
    return path


def test_generated_schema_cli_uses_strict_installed_models():
    catalog = schema_catalog()
    dashboard = schema_model_contract("dashboard", full=True)
    result = CliRunner().invoke(
        app, ["schemas", "source", "--full", "--format", "json"]
    )

    assert catalog["models"]["dashboard"]["contract_schema"] == CURRENT_SCHEMAS["dashboard"]
    assert dashboard["json_schema"]["properties"]["schema"]["const"] == CURRENT_SCHEMAS["dashboard"]
    assert next(field for field in dashboard["fields"] if field["name"] == "schema")["required"] is True
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["contract_schema"] == CURRENT_SCHEMAS["source"]
    assert payload["json_schema"]["additionalProperties"] is False


def test_dsl_schema_versions_are_literals_not_descriptive_strings():
    with pytest.raises(ValidationError):
        DashboardDefinition.model_validate(
            {"schema": "dataviz/dashboard/v2", "kind": "dashboard", "id": "future"}
        )
    with pytest.raises(ValidationError):
        SourceDefinition.model_validate(
            {
                "schema": "dataviz/source/v0",
                "kind": "source",
                "id": "old",
                "type": "file",
            }
        )


def test_migrate_adds_unambiguous_schema_headers_but_never_runs_legacy_protocols(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    dashboard = root / "dashboards" / "hello"
    dashboard.mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        "kind: workspace\nid: migration\ntitle: Migration\n", encoding="utf-8"
    )
    (dashboard / "dashboard.yaml").write_text(
        "kind: dashboard\nid: hello\ntitle: Hello\n", encoding="utf-8"
    )

    preview = migrate_workspace(root)
    assert preview["mode"] == "dry-run"
    assert not preview["blockers"]
    assert {change["expected"] for change in preview["changes"]} == {
        "dataviz/workspace/v1",
        "dataviz/dashboard/v1",
    }
    assert not (root / "workspace.yaml").read_text(encoding="utf-8").startswith("schema:")

    applied = migrate_workspace(root, apply=True)
    assert applied["mode"] == "apply"
    assert len(applied["changed"]) == 2
    assert (root / "workspace.yaml").read_text(encoding="utf-8").startswith(
        "schema: dataviz/workspace/v1"
    )
    assert load_workspace(root).definition.id == "migration"

    (dashboard / "dashboard.yaml").write_text(
        "schema: dataviz/dashboard/v0\nkind: dashboard\nid: hello\n",
        encoding="utf-8",
    )
    blocked = migrate_workspace(root, apply=True)
    assert blocked["mode"] == "dry-run"
    assert blocked["blockers"][0]["code"] == "unsupported_schema_version"
    assert "dataviz/dashboard/v0" in (dashboard / "dashboard.yaml").read_text(
        encoding="utf-8"
    )


def test_authoring_log_records_real_cost_friction_and_unknown_measurements(tmp_path: Path):
    root = _init_workspace(tmp_path / "workspace")
    runner = CliRunner()
    started = runner.invoke(
        app,
        [
            "authoring",
            "start",
            str(root),
            "--dashboard",
            "hello",
            "--task",
            "Add a line View",
            "--model",
            "test-model",
        ],
    )
    assert started.exit_code == 0, started.output
    session_id = json.loads(started.output)["session_id"]

    note = runner.invoke(
        app,
        [
            "authoring",
            "note",
            str(root),
            session_id,
            "--category",
            "documentation",
            "--reference",
            "docs charts",
            "--message",
            "The aggregation default was unclear",
        ],
    )
    assert note.exit_code == 0, note.output
    finished = runner.invoke(
        app,
        [
            "authoring",
            "finish",
            str(root),
            session_id,
            "--outcome",
            "success",
            "--first-attempt",
            "failure",
            "--correction-rounds",
            "2",
            "--input-tokens",
            "3100",
            "--output-tokens",
            "900",
            "--docs-used",
            "quickstart",
            "--docs-used",
            "charts",
        ],
    )
    assert finished.exit_code == 0, finished.output

    lines = (root / AUTHORING_LOG_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert all(json.loads(line)["schema"] == "dataviz/authoring-event/v1" for line in lines)
    report = authoring_log_report(root)
    assert report["metrics"]["first_attempt_success_rate"] == 0.0
    assert report["metrics"]["mean_correction_rounds"] == 2
    assert report["metrics"]["reported_input_tokens"] == 3100
    assert report["metrics"]["friction_by_category"] == {"documentation": 1}
    assert report["sessions"][0]["docs_used"] == ["charts", "quickstart"]

    second = runner.invoke(
        app,
        ["authoring", "start", str(root), "--task", "Unknown-token task"],
    )
    second_id = json.loads(second.output)["session_id"]
    unknown = runner.invoke(
        app,
        ["authoring", "finish", str(root), second_id, "--outcome", "partial"],
    )
    assert unknown.exit_code == 0, unknown.output
    assert json.loads(unknown.output)["token_source"] == "unknown"


def test_focused_context_prompts_ai_to_leave_shareable_feedback():
    result = CliRunner().invoke(
        app,
        [
            "context",
            str(MINIMAL_WORKSPACE),
            "sales-overview",
            "--focus",
            "view:revenue-trend",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    prompt = json.loads(result.output)["authoring_feedback"]
    assert prompt["log"] == AUTHORING_LOG_NAME
    assert "authoring start" in prompt["start"]
    assert "Report real measurements only" in prompt["rule"]


def test_reference_frontend_adapter_is_exportable_and_has_no_canvas_runtime_dependency(
    tmp_path: Path,
):
    catalog = frontend_adapter_catalog()
    source = frontend_adapter_source("web-component")
    output = tmp_path / "adapter.js"
    result = CliRunner().invoke(
        app, ["frontend-adapters", "web-component", "--output", str(output)]
    )

    assert catalog["web-component"]["protocol"] == "dataviz/runtime/v1"
    assert catalog["web-component"]["dependency"] == "none"
    assert "DatavizRuntimeV1Client" in source
    assert "datavizRuntime." not in source
    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8") == source
