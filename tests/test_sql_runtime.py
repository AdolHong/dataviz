from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from dataviz.artifacts import ArtifactStore
from dataviz.errors import QueryExecutionFailure, QueryTimeoutFailure
from dataviz.execution import Executor
from dataviz.sources import sql as sql_runtime
from dataviz.sql_contract import resolve_sql_preview
from dataviz.workspace import load_workspace, validate_workspace


def _sql_workspace(
    root: Path,
    query: str,
    *,
    timeout_seconds: float | None = None,
    timeout_retries: int | None = None,
    adapter: str = "warehouse",
    adapter_yaml: str = "type: duckdb\n    database: ':memory:'",
) -> Path:
    dashboard = root / "dashboards" / "sql-test"
    sources = dashboard / "sources"
    sources.mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v1\nkind: workspace\nid: sql-tests\ntitle: SQL tests\n",
        encoding="utf-8",
    )
    (root / "adapters.local.yaml").write_text(
        f"adapters:\n  {adapter}:\n    {adapter_yaml}\n",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v1
kind: dashboard
id: sql-test
title: SQL test
sources: [sources/query.yaml]
views:
  - {id: result, title: Result, template: table, input: query}
sections:
  - {id: main, title: Main, views: [result]}
""",
        encoding="utf-8",
    )
    timeout_line = (
        f"timeout_seconds: {timeout_seconds}\n" if timeout_seconds is not None else ""
    )
    retry_line = (
        f"timeout_retries: {timeout_retries}\n" if timeout_retries is not None else ""
    )
    (sources / "query.yaml").write_text(
        f"""schema: dataviz/source/v1
kind: source
id: query
type: sql
adapter: {adapter}
code: query.sql
{timeout_line}{retry_line}cache: {{mode: none}}
""",
        encoding="utf-8",
    )
    (sources / "query.sql").write_text(query, encoding="utf-8")
    return root


def test_sql_source_with_timeout_returns_table_and_cleans_temporary_file(tmp_path: Path):
    root = _sql_workspace(
        tmp_path / "workspace",
        "select 1 as value",
        timeout_seconds=10,
    )
    workspace = load_workspace(root)
    assert validate_workspace(workspace) == []

    result = Executor(workspace).run("sql-test", refresh=True)
    artifact = result.nodes["source:query"].outputs["main"]
    frame = ArtifactStore(root, result.run_id).read_table(artifact)

    assert result.status == "success"
    assert frame.to_dict(orient="records") == [{"value": 1}]
    query_evidence = result.nodes["source:query"].diagnostics["query"]
    assert query_evidence["adapter_alias"] == "warehouse"
    assert query_evidence["adapter_type"] == "duckdb"
    assert query_evidence["statement"] == "select 1 as value"
    assert query_evidence["resolved_sql"] == "select 1 as value"
    assert query_evidence["source_file"].endswith("sources/query.sql")
    assert query_evidence["timeout_seconds"] == 10
    assert "url" not in query_evidence
    assert not (root / ".dataviz" / "runs" / result.run_id / "tmp").exists()


def test_sql_timeout_hard_cancels_only_its_node_and_is_structured(tmp_path: Path):
    root = _sql_workspace(
        tmp_path / "workspace",
        "select sum(sin(i)) as value from range(1000000000) values(i)",
        timeout_seconds=0.1,
    )
    workspace = load_workspace(root)

    started = time.monotonic()
    result = Executor(workspace).run("sql-test", refresh=True)
    elapsed = time.monotonic() - started
    node = result.nodes["source:query"]

    assert elapsed < 5
    assert node.status == "failed"
    assert node.error["type"] == "query_timeout"
    assert node.error["details"]["cancelled"] is True
    assert node.error["details"]["adapter_type"] == "duckdb"
    assert node.error["details"]["attempt"] == 2
    assert node.error["details"]["max_attempts"] == 2
    assert node.error["details"]["timeout_retries"] == 1
    assert node.diagnostics["query"]["resolved_sql"].startswith("select sum(sin(i))")
    assert node.diagnostics["query"]["timeout_seconds"] == 0.1
    assert node.log is not None
    assert not (root / ".dataviz" / "runs" / result.run_id / "tmp").exists()


def test_resolved_sql_preview_only_literalizes_code_parameters():
    query = """select :name as person, ':name' as literal, amount::text
-- :name remains a comment
/* $name remains a comment */
select $body$:name and $name stay literal$body$
where owner = $name and missing = :missing
"""

    resolved = resolve_sql_preview(query, {"name": "O'Reilly"})

    assert "select 'O''Reilly' as person" in resolved
    assert "':name' as literal" in resolved
    assert "amount::text" in resolved
    assert "-- :name remains a comment" in resolved
    assert "/* $name remains a comment */" in resolved
    assert "$body$:name and $name stay literal$body$" in resolved
    assert "owner = 'O''Reilly'" in resolved
    assert "missing = :missing" in resolved


def test_sql_timeout_does_not_block_an_independent_fast_branch(tmp_path: Path):
    root = _sql_workspace(
        tmp_path / "workspace",
        "select sum(sin(i)) as value from range(1000000000) values(i)",
        timeout_seconds=0.1,
    )
    dashboard = root / "dashboards" / "sql-test"
    sources = dashboard / "sources"
    (sources / "fast.csv").write_text("label,value\nready,7\n", encoding="utf-8")
    (sources / "fast.yaml").write_text(
        """schema: dataviz/source/v1
kind: source
id: fast
type: file
path: fast.csv
format: csv
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v1
kind: dashboard
id: sql-test
title: SQL test
sources: [sources/query.yaml, sources/fast.yaml]
views:
  - {id: timed-out, title: Timed out, template: table, input: query}
  - {id: fast, title: Fast, template: table, input: fast}
sections:
  - {id: main, title: Main, views: [timed-out, fast]}
""",
        encoding="utf-8",
    )

    result = Executor(load_workspace(root)).run("sql-test", refresh=True)

    assert result.status == "partial"
    assert result.nodes["source:query"].error["type"] == "query_timeout"
    assert result.nodes["source:fast"].status == "succeeded"
    fast = ArtifactStore(root, result.run_id).read_table(
        result.nodes["source:fast"].outputs["main"]
    )
    assert fast.to_dict(orient="records") == [{"label": "ready", "value": 7}]


def test_sql_defaults_to_120_seconds_and_one_immediate_timeout_retry(
    tmp_path: Path, monkeypatch
):
    root = _sql_workspace(tmp_path / "workspace", "select 1")
    attempts: list[float | None] = []

    def transient_timeout(**kwargs):
        attempts.append(kwargs["timeout_seconds"])
        if len(attempts) == 1:
            raise QueryTimeoutFailure(
                "transient timeout",
                details={"timeout_origin": "server_deadline", "cancelled": True},
            )
        return pd.DataFrame([{"value": 1}])

    monkeypatch.setattr(sql_runtime, "execute_sql_query", transient_timeout)
    events = []
    result = Executor(load_workspace(root)).run(
        "sql-test",
        refresh=True,
        observer=events.append,
    )

    assert result.status == "success"
    assert attempts == [120.0, 120.0]
    retry_events = [event for event in events if event.event == "node_retrying"]
    assert len(retry_events) == 1
    assert retry_events[0].data == {
        "reason": "query_timeout",
        "completed_attempt": 1,
        "next_attempt": 2,
        "max_attempts": 2,
        "timeout_seconds": 120.0,
        "retries_remaining": 1,
    }


def test_sql_timeout_retry_count_is_configurable_and_other_errors_do_not_retry(
    tmp_path: Path, monkeypatch
):
    retry_root = _sql_workspace(
        tmp_path / "retry",
        "select 1",
        timeout_seconds=3.5,
        timeout_retries=2,
    )
    retry_attempts: list[float | None] = []

    def succeeds_on_third_attempt(**kwargs):
        retry_attempts.append(kwargs["timeout_seconds"])
        if len(retry_attempts) < 3:
            raise QueryTimeoutFailure("transient timeout")
        return pd.DataFrame([{"value": 1}])

    monkeypatch.setattr(sql_runtime, "execute_sql_query", succeeds_on_third_attempt)
    retry_result = Executor(load_workspace(retry_root)).run("sql-test", refresh=True)
    assert retry_result.status == "success"
    assert retry_attempts == [3.5, 3.5, 3.5]

    failure_root = _sql_workspace(
        tmp_path / "failure",
        "select 1",
        timeout_retries=5,
    )
    failure_attempts = 0

    def permanent_failure(**kwargs):
        nonlocal failure_attempts
        failure_attempts += 1
        raise QueryExecutionFailure("syntax error")

    monkeypatch.setattr(sql_runtime, "execute_sql_query", permanent_failure)
    failure_result = Executor(load_workspace(failure_root)).run(
        "sql-test", refresh=True
    )
    assert failure_result.status == "failed"
    assert failure_attempts == 1
    assert (
        failure_result.nodes["source:query"].error["type"]
        == "query_execution_error"
    )


def test_database_timeout_errors_are_classified_without_matching_other_sql_errors():
    assert sql_runtime._is_query_timeout_error(
        RuntimeError(3024, "maximum statement execution time exceeded")
    )
    assert sql_runtime._is_query_timeout_error(
        RuntimeError("StarRocks query timeout after 120 seconds")
    )
    assert sql_runtime._is_query_timeout_error(RuntimeError(1064, "timeout"))
    assert sql_runtime._is_query_timeout_error(
        RuntimeError("Query exceeded time limit of 120 seconds")
    )
    assert not sql_runtime._is_query_timeout_error(
        RuntimeError("syntax error near SELECT")
    )


def test_timeout_retries_is_rejected_for_non_sql_sources(tmp_path: Path):
    root = _sql_workspace(tmp_path / "workspace", "select 1")
    sources = root / "dashboards" / "sql-test" / "sources"
    (sources / "query.csv").write_text("value\n1\n", encoding="utf-8")
    (sources / "query.yaml").write_text(
        """schema: dataviz/source/v1
kind: source
id: query
type: file
path: query.csv
format: csv
timeout_retries: 1
cache: {mode: none}
""",
        encoding="utf-8",
    )

    diagnostics = validate_workspace(load_workspace(root))

    assert any(
        item.field == "timeout_retries"
        and item.message == "timeout_retries is only valid for SQL sources"
        for item in diagnostics
    )


def test_sql_execution_and_connection_failures_have_distinct_codes(tmp_path: Path):
    execution_root = _sql_workspace(
        tmp_path / "execution",
        "select definitely_missing from nowhere",
    )
    execution = Executor(load_workspace(execution_root)).run("sql-test", refresh=True)
    assert execution.nodes["source:query"].error["type"] == "query_execution_error"

    connection_root = _sql_workspace(
        tmp_path / "connection",
        "select 1",
        adapter_yaml="type: sqlalchemy\n    url: sqlite:///missing-parent/database.sqlite",
    )
    connection = Executor(load_workspace(connection_root)).run("sql-test", refresh=True)
    assert connection.nodes["source:query"].error["type"] == "query_connection_error"
