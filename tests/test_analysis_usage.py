from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from dataviz.analysis import ensure_analysis_catalog
from dataviz.analysis.usage import (
    UsageKey,
    dashboard_query_usage,
    output_analysis_usage,
    read_usage,
    record_usage,
    record_usage_best_effort,
)
from dataviz.cli import app
from dataviz.server.app import create_app


FEATURE_SHOWCASE = Path("examples/feature-showcase")
MINIMAL_WORKSPACE = Path("examples/minimal-workspace")


def _record_many(root: str, count: int) -> int:
    key = output_analysis_usage("sales::source:orders/main")
    for _ in range(count):
        record_usage(Path(root), key)
    return count


def _build_fold_workspace(root: Path) -> Path:
    (root / "auth").mkdir(parents=True)
    (root / "dashboards").mkdir()
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: fold-tests
title: Fold tests
""",
        encoding="utf-8",
    )
    (root / "auth/adapters.yaml").write_text(
        """adapters:
  warehouse:
    type: duckdb
    database: ':memory:'
""",
        encoding="utf-8",
    )
    source = """schema: dataviz/source/v2
kind: source
id: rows
name: 收入
description: 精确重复的 SQL Output。
type: sql
adapter: warehouse
code: query.sql
outputs:
  main:
    kind: table
    schema: [{name: value, dtype: int64}]
    semantics:
      visibility: public
      title: 收入
      purpose: 验证精确折叠。
      grain: 每次查询一行。
      assurance: {status: draft}
"""
    for dashboard_id in ("one", "two"):
        dashboard = root / "dashboards" / dashboard_id
        (dashboard / "sources").mkdir(parents=True)
        (dashboard / "dashboard.yaml").write_text(
            f"""schema: dataviz/dashboard/v9
kind: dashboard
id: {dashboard_id}
title: {dashboard_id}
adapters: {{warehouse: warehouse}}
sources: [sources/rows.yaml]
views:
  - {{id: result, title: Result, template: table, input: source:rows/main}}
sections:
  - {{id: result, title: Result, views: [result]}}
""",
            encoding="utf-8",
        )
        (dashboard / "sources/rows.yaml").write_text(source, encoding="utf-8")
        (dashboard / "sources/query.sql").write_text(
            "select 1::BIGINT as value\n", encoding="utf-8"
        )
    return root


def test_usage_upsert_is_process_safe_and_last_used_is_monotonic(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    workers = 6
    per_worker = 20
    with ProcessPoolExecutor(max_workers=workers) as pool:
        assert sum(pool.map(_record_many, [str(workspace)] * workers, [per_worker] * workers)) == (
            workers * per_worker
        )

    key = output_analysis_usage("sales::source:orders/main")
    usage = read_usage(workspace)[key]
    assert usage["use_count"] == workers * per_worker

    newer = datetime(2030, 8, 28, 12, tzinfo=timezone.utc)
    older = datetime(2030, 8, 27, 12, tzinfo=timezone.utc)
    record_usage(workspace, key, used_at=newer)
    record_usage(workspace, key, used_at=older)
    usage = read_usage(workspace)[key]
    assert usage["use_count"] == workers * per_worker + 2
    assert usage["last_used_at"].startswith("2030-08-28T12:00:00")


def test_usage_busy_timeout_is_bounded_and_best_effort(tmp_path: Path, caplog):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    key = UsageKey("output", "x::source:y/main", "test", "ai")
    record_usage(workspace, key)
    connection = sqlite3.connect(workspace / ".dataviz/usage.sqlite")
    connection.execute("BEGIN IMMEDIATE")
    started = time.perf_counter()
    try:
        assert record_usage_best_effort(
            workspace, key, busy_timeout_ms=50
        ) is False
    finally:
        connection.rollback()
        connection.close()
    assert time.perf_counter() - started < 0.75
    assert "successful action is unchanged" in caplog.text


def test_run_records_only_success_and_usage_failure_does_not_fail_command(
    isolated_workspace,
):
    workspace = isolated_workspace(FEATURE_SHOWCASE)
    catalog = ensure_analysis_catalog(workspace)
    entry = next(
        item
        for item in catalog.entries
        if item["reference"] == "date-parameter-lab::source:date-window/main"
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(workspace), entry["reference"], "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    usage = read_usage(workspace)[output_analysis_usage(entry["reference"])]
    assert usage["use_count"] == 1

    usage_path = workspace / ".dataviz/usage.sqlite"
    usage_path.unlink()
    usage_path.mkdir()
    successful = runner.invoke(
        app,
        [
            "run",
            str(workspace),
            entry["reference"],
            "--format",
            "json",
        ],
    )
    assert successful.exit_code == 0, successful.output
    assert json.loads(successful.output)["status"] == "ready"


def test_server_success_records_human_dashboard_query(isolated_workspace):
    workspace = isolated_workspace(MINIMAL_WORKSPACE)
    with TestClient(create_app(workspace, watch=False)) as client:
        started = client.post(
            "/api/dashboards/sales-overview/runs",
            json={
                "session_id": "usage-test-session",
                "query_parameters": {"min_query_revenue": 0},
                "refresh": True,
            },
        ).json()
        for _ in range(100):
            result = client.get(
                f"/api/runs/{started['run_id']}",
                params={"session_id": "usage-test-session"},
            ).json()
            if result["status"] in {"ready", "partial", "error", "cancelled"}:
                break
            time.sleep(0.05)
    assert result["status"] == "ready", result
    usage = read_usage(workspace)[dashboard_query_usage("sales-overview")]
    assert usage["use_count"] == 1


def test_catalog_exact_fold_is_conservative_and_top_runs_after_fold(tmp_path: Path):
    workspace = _build_fold_workspace(tmp_path / "workspace")
    catalog = ensure_analysis_catalog(workspace)
    entries = catalog.select(kind="base_output", include_untrusted=True)
    folded = catalog.overview(entries, expand_occurrences=True, top=1)
    assert len(folded) == 1
    assert folded[0]["occurrence_count"] == 2
    assert len(folded[0]["references"]) == 2
    assert folded[0]["representative"]["reference"] == "one::source:rows/main"

    query = workspace / "dashboards/two/sources/query.sql"
    query.write_text("select 2::BIGINT as value\n", encoding="utf-8")
    refreshed = ensure_analysis_catalog(workspace)
    entries = refreshed.select(kind="base_output", include_untrusted=True)
    assert len(refreshed.overview(entries)) == 2
