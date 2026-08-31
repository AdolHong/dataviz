from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import threading

import pytest
from typer.testing import CliRunner

from dataviz.analysis import RunRequest, ensure_analysis_catalog, run_analysis
from dataviz.cli import app
from dataviz.errors import ExecutionFailure, ValidationFailure
from dataviz.protocols import ANALYSIS_RESULT_SCHEMA


MINIMAL_WORKSPACE = Path("examples/minimal-workspace")
BROWSER_WORKSPACE = Path("tests/fixtures/browser-worker-workspace")


def _workspace(tmp_path: Path) -> Path:
    destination = tmp_path / "workspace"
    shutil.copytree(
        MINIMAL_WORKSPACE,
        destination,
        ignore=shutil.ignore_patterns(".dataviz", "__pycache__", "*.pyc"),
    )
    return destination


def _source_target(workspace: Path) -> str:
    catalog = ensure_analysis_catalog(workspace)
    return next(
        entry["reference"]
        for entry in catalog.entries
        if entry["reference"] == "sales-overview::source:sales/main"
    )


def _browser_workspace(tmp_path: Path) -> Path:
    destination = tmp_path / "browser-workspace"
    shutil.copytree(
        BROWSER_WORKSPACE,
        destination,
        ignore=shutil.ignore_patterns(".dataviz", "__pycache__", "*.pyc"),
    )
    transform_root = destination / "dashboards/worker-runtime/transforms"
    definition = transform_root / "scaled.yaml"
    definition.write_text(
        definition.read_text(encoding="utf-8").replace(
            "timeout_seconds: 1",
            """  secondary:
    kind: table
    schema:
      - {name: name}
      - {name: value}
timeout_seconds: 1""",
        ),
        encoding="utf-8",
    )
    return destination


def _stable_result_projection(payload: dict) -> dict:
    outputs = [
        {
            key: value
            for key, value in output.items()
            if key not in {"duration_ms", "run_id", "storage"}
        }
        for output in payload["outputs"]
    ]
    return {
        "schema": payload["schema"],
        "status": payload["status"],
        "target": payload["target"],
        "query_parameters": payload["query_parameters"],
        "query_parameter_intents": payload.get("query_parameter_intents", {}),
        "effective_controls": payload["effective_controls"],
        "consumer_revisions": payload.get(
            "consumer_revisions", {"views": {}, "transforms": {}}
        ),
        "outputs": outputs,
        "lineage": payload["lineage"],
        "provenance": payload["provenance"],
    }


def test_browser_analysis_sync_boundary_isolated_from_caller_event_loop(
    monkeypatch: pytest.MonkeyPatch,
):
    from dataviz.analysis import browser as browser_analysis

    caller_thread = threading.get_ident()

    def observe_thread(*args, **kwargs):
        return {"thread": threading.get_ident()}

    monkeypatch.setattr(
        browser_analysis,
        "_run_browser_outputs_sync",
        observe_thread,
    )

    async def invoke():
        return browser_analysis.run_browser_outputs(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            None,
            targets=[("scaled", "main")],
            control_state={},
            refresh=False,
            allow_network=False,
            timeout_seconds=1,
        )

    observed = asyncio.run(invoke())

    assert observed["thread"] != caller_thread


def test_run_analysis_and_cli_publish_the_same_canonical_result(tmp_path: Path):
    workspace = _workspace(tmp_path)
    target = _source_target(workspace)

    direct = run_analysis(
        RunRequest(workspace=workspace, target=target, preview_rows=1)
    )
    invoked = CliRunner().invoke(
        app,
        [
            "run",
            str(workspace),
            target,
            "--preview-rows",
            "1",
            "--format",
            "json",
        ],
    )

    assert invoked.exit_code == 0, invoked.output
    cli_result = json.loads(invoked.output)
    assert direct["schema"] == ANALYSIS_RESULT_SCHEMA
    assert direct["result_id"] != cli_result["result_id"]
    assert _stable_result_projection(direct) == _stable_result_projection(cli_result)


def test_run_analysis_preflight_failure_does_not_publish_result(tmp_path: Path):
    workspace = _workspace(tmp_path)
    target = _source_target(workspace)
    before = list((workspace / ".dataviz" / "results").glob("result_*"))

    with pytest.raises(ValidationFailure, match="runtime"):
        run_analysis(
            RunRequest(workspace=workspace, target=target, runtime="invalid")  # type: ignore[arg-type]
        )

    invoked = CliRunner().invoke(
        app,
        [
            "run",
            str(workspace),
            target,
            "--runtime",
            "invalid",
            "--format",
            "json",
        ],
    )

    after = list((workspace / ".dataviz" / "results").glob("result_*"))
    assert invoked.exit_code == 1
    assert "result_id" not in json.loads(invoked.output)
    assert after == before


def test_run_analysis_seals_failure_after_execution_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    workspace = _workspace(tmp_path)
    target = _source_target(workspace)

    def fail_after_preflight(*args, **kwargs):
        raise ExecutionFailure(
            "Synthetic execution failure",
            details={"code": "synthetic_execution_failure"},
        )

    monkeypatch.setattr("dataviz.analysis.runner.Executor.run", fail_after_preflight)
    result = run_analysis(
        RunRequest(
            workspace=workspace,
            target=target,
            query_parameters={"min_query_revenue": 100},
        )
    )

    assert result["schema"] == ANALYSIS_RESULT_SCHEMA
    assert result["status"] == "failed"
    assert result["error"]["code"] == "synthetic_execution_failure"
    assert result["query_parameters"] == {"min_query_revenue": 100}
    assert result["query_parameter_intents"] == {"min_query_revenue": "explicit"}
    assert result["result_id"].startswith("result_")


def test_run_analysis_failure_preserves_effective_browser_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    workspace = _browser_workspace(tmp_path)
    catalog = ensure_analysis_catalog(workspace, refresh=True)
    target = catalog.resolve("worker-runtime::interactive:scaled/main")
    control_key = "dashboard:worker-runtime/delay_ms"

    def fail_browser(*args, **kwargs):
        raise ExecutionFailure(
            "Synthetic browser failure",
            details={"code": "synthetic_browser_failure"},
        )

    monkeypatch.setattr("dataviz.analysis.runner.run_browser_outputs", fail_browser)
    result = run_analysis(
        RunRequest(
            workspace=workspace,
            target=target["reference"],
            controls={control_key: 0},
        )
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "synthetic_browser_failure"
    assert result["effective_controls"] == {
        control_key: {"value": 0, "revision": 0}
    }


def test_run_analysis_seals_cancellation_after_execution_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    workspace = _workspace(tmp_path)
    target = _source_target(workspace)

    def cancel_after_preflight(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("dataviz.analysis.runner.Executor.run", cancel_after_preflight)
    result = run_analysis(RunRequest(workspace=workspace, target=target))

    assert result["status"] == "cancelled"
    assert result["error"]["code"] == "execution_cancelled"
    assert result["result_id"].startswith("result_")


def test_run_analysis_dashboard_target_uses_the_same_result_store(tmp_path: Path):
    workspace = _workspace(tmp_path)

    result = run_analysis(
        RunRequest(workspace=workspace, target="sales-overview", preview_rows=1)
    )

    assert result["schema"] == ANALYSIS_RESULT_SCHEMA
    assert result["status"] == "ready"
    assert result["target"]["kind"] == "dashboard"
    assert result["renderability"]["renderable"] is True
    assert (workspace / result["result_path"] / "manifest.json").is_file()


def test_run_analysis_resolves_view_to_its_canonical_data_target(tmp_path: Path):
    workspace = _workspace(tmp_path)

    result = run_analysis(
        RunRequest(
            workspace=workspace,
            target="sales-overview::view:sales-detail",
            preview_rows=1,
        )
    )

    assert result["status"] == "ready"
    assert result["target"]["kind"] == "view"
    assert result["resolved_target"]["kind"] == "base_output"
    assert result["view_input"] == {
        "main": "sales-overview::source:sales/main"
    }
    assert result["outputs"][0]["reference"] == "sales-overview::source:sales/main"


def test_run_analysis_seals_partial_result_with_available_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    workspace = _workspace(tmp_path)
    target = _source_target(workspace)
    from dataviz.execution import Executor

    original_run = Executor.run

    def return_partial(self, *args, **kwargs):
        result = original_run(self, *args, **kwargs)
        result.status = "partial"
        return result

    monkeypatch.setattr("dataviz.analysis.runner.Executor.run", return_partial)
    result = run_analysis(
        RunRequest(workspace=workspace, target=target, preview_rows=1)
    )

    assert result["status"] == "partial"
    assert result["outputs"][0]["rows"] == 12
    assert result["result_id"].startswith("result_")
    assert (workspace / result["result_path"] / "manifest.json").is_file()

    rejected = CliRunner().invoke(
        app,
        ["run", str(workspace), target, "--format", "json"],
    )
    accepted = CliRunner().invoke(
        app,
        [
            "run",
            str(workspace),
            target,
            "--format",
            "json",
            "--allow-partial",
        ],
    )
    assert rejected.exit_code == 1
    assert json.loads(rejected.output)["status"] == "partial"
    assert accepted.exit_code == 0, accepted.output
    assert json.loads(accepted.output)["status"] == "partial"


def test_run_analysis_overlay_dry_run_is_unsealed_and_execution_is_immutable(
    tmp_path: Path,
):
    workspace = _workspace(tmp_path)
    target = _source_target(workspace)
    original = workspace / "dashboards/sales-overview/sources/sales.sql"
    before = original.read_bytes()
    experiment = tmp_path / "experiment"
    experiment.mkdir()
    (experiment / "replacement.sql").write_text(
        """select '2026-08-31' as day, '华南' as region, 999 as revenue, 3 as orders
where 999 >= $min_query_revenue
""",
        encoding="utf-8",
    )
    overlay = experiment / "overlay.yaml"
    overlay.write_text(
        """schema: dataviz/analysis-overlay/v1
replacements:
  source:sales:
    code: replacement.sql
""",
        encoding="utf-8",
    )
    before_results = set((workspace / ".dataviz/results").glob("result_*"))

    explained = run_analysis(
        RunRequest(
            workspace=workspace,
            target=target,
            overlay=overlay,
            dry_run=True,
        )
    )

    assert explained["schema"] == "dataviz/analysis-overlay-explanation/v1"
    assert set((workspace / ".dataviz/results").glob("result_*")) == before_results

    executed = run_analysis(
        RunRequest(workspace=workspace, target=target, overlay=overlay)
    )
    assert executed["status"] == "ready"
    assert executed["outputs"][0]["preview"] == [
        {"day": "2026-08-31", "region": "华南", "revenue": 999, "orders": 3}
    ]
    assert executed["overlay"]["overlay_hash"]
    assert original.read_bytes() == before


def test_browser_derived_batch_has_direct_cli_parity_without_host_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    workspace = _browser_workspace(tmp_path)
    catalog = ensure_analysis_catalog(workspace, refresh=True)
    target = catalog.resolve("worker-runtime::interactive:scaled/main")
    secondary = catalog.resolve("worker-runtime::interactive:scaled/secondary")
    calls: list[dict] = []

    def browser_batch(_loaded, _dashboard, run_result, **kwargs):
        calls.append(kwargs)
        return {
            "outputs": [
                {
                    "kind": "table",
                    "rows": 2,
                    "schema": [
                        {"name": "name", "dtype": "str"},
                        {"name": "value", "dtype": "int64"},
                    ],
                    "content_hash": "1" * 64,
                    "transport": "json",
                    "value": [
                        {"name": "alpha", "value": 10},
                        {"name": "beta", "value": 20},
                    ],
                },
                {
                    "kind": "table",
                    "rows": 2,
                    "schema": [
                        {"name": "name", "dtype": "str"},
                        {"name": "value", "dtype": "int64"},
                    ],
                    "content_hash": "2" * 64,
                    "transport": "json",
                    "value": [
                        {"name": "alpha", "value": 100},
                        {"name": "beta", "value": 200},
                    ],
                },
            ],
            "consumer_revisions": {"views": {}, "transforms": {}},
            "server_interactions": [],
            "duration_ms": 4,
            "timing": {
                "browser_launch_ms": 1,
                "runtime_ready_ms": 1,
                "transform_ms": 1,
                "extraction_ms": 1,
            },
            "metrics": {"interactiveTransforms": {"completed": 1}},
            "console_errors": [],
        }

    monkeypatch.setattr("dataviz.analysis.runner.run_browser_outputs", browser_batch)
    control_key = "dashboard:worker-runtime/delay_ms"
    request = RunRequest(
        workspace=workspace,
        target=target["reference"],
        also=(secondary["reference"],),
        controls={control_key: 0},
        preview_rows=1,
        detail="debug",
    )
    direct = run_analysis(request)
    invoked = CliRunner().invoke(
        app,
        [
            "run",
            str(workspace),
            target["reference"],
            "--also",
            secondary["reference"],
            "--control",
            f"{control_key}=0",
            "--preview-rows",
            "1",
            "--detail",
            "debug",
            "--format",
            "json",
        ],
    )

    assert invoked.exit_code == 0, invoked.output
    cli_result = json.loads(invoked.output)
    assert _stable_result_projection(direct) == _stable_result_projection(cli_result)
    assert [item["reference"] for item in direct["outputs"]] == [
        target["reference"],
        secondary["reference"],
    ]
    assert [item["preview"] for item in direct["outputs"]] == [
        [{"name": "alpha", "value": 10}],
        [{"name": "alpha", "value": 100}],
    ]
    assert len(calls) == 2
    assert all(
        call["targets"] == [("scaled", "main"), ("scaled", "secondary")]
        for call in calls
    )
    assert all(call["control_state"][control_key]["value"] == 0 for call in calls)
