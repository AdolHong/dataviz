from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.semantic_validation import validate_dashboard_semantics
from dataviz.validation import validate_preflight
from dataviz.workspace import load_workspace


ROOT = Path(__file__).resolve().parents[1]
MINIMAL = ROOT / "examples" / "minimal-workspace"


def test_semantic_advice_does_not_fail_strict_validation(tmp_path: Path):
    workspace = tmp_path / "workspace"
    import shutil

    shutil.copytree(MINIMAL, workspace)
    presentation_path = workspace / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation.setdefault("views", {}).setdefault("sales-detail", {})["min_height"] = 999
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview", strict=True)

    assert report["schema"] == "dataviz/validation/v3"
    assert report["passed"] is True
    assert report["summary"]["advice"] >= 1
    assert any(
        item["code"] == "semantic_min_height_large" and item["level"] == "advice"
        for item in report["diagnostics"]
    )


def test_unused_control_is_a_strict_warning(tmp_path: Path):
    workspace = tmp_path / "workspace"
    import shutil

    shutil.copytree(MINIMAL, workspace)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"].append(
        {
            "id": "unused_note",
            "kind": "compute",
            "type": "string",
            "label": "Unused",
            "default": "x",
        }
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview", strict=True)

    assert report["passed"] is False
    assert any(item["code"] == "semantic_control_unused" for item in report["diagnostics"])


def test_inspect_layout_emits_compiled_rows_and_sources():
    result = CliRunner().invoke(
        app,
        ["inspect-layout", str(MINIMAL), "sales-overview", "--format", "json"],
    )

    assert result.exit_code == 0, result.stdout
    payload = __import__("json").loads(result.stdout)
    assert payload["schema"] == "dataviz/layout-inspection/v1"
    assert payload["layout"]["schema"] == "dataviz/layout-contract/v1"
    assert payload["layout"]["sections"][0]["rows"]
    assert payload["layout"]["sections"][0]["placements"][0]["source"]


def test_current_examples_have_no_semantic_warnings():
    dashboard = load_workspace(MINIMAL).dashboard("sales-overview")
    diagnostics = validate_dashboard_semantics(dashboard)
    assert not [item for item in diagnostics if item.level in {"error", "warning"}]
