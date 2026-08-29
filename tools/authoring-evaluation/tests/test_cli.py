from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dataviz_authoring_eval.cli import app


def test_authoring_eval_is_a_standalone_repository_tool(tmp_path: Path) -> None:
    runner = CliRunner()
    tasks = runner.invoke(app, ["tasks"])
    assert tasks.exit_code == 0, tasks.output
    assert "default-dashboard" in json.loads(tasks.output)["tasks"]

    trial = tmp_path / "trial"
    prepared = runner.invoke(
        app,
        [
            "prepare",
            "dataset-multi-output",
            str(trial),
            "--approach",
            "dataviz",
            "--trial-id",
            "trial-001",
        ],
    )
    assert prepared.exit_code == 0, prepared.output
    manifest = json.loads(prepared.output)
    assert manifest["approach"] == "dataviz"
    assert (trial / "trial.json").is_file()


def test_context_benchmark_reports_measurements_without_token_estimates() -> None:
    workspace = Path(__file__).resolve().parents[3] / "examples" / "minimal-workspace"
    result = CliRunner().invoke(
        app, ["benchmark-context", str(workspace), "sales-overview"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["validation"]["valid"] is True
    assert "estimated_tokens" not in result.output
    assert "model-specific input/output tokens" in payload["not_measured"]
