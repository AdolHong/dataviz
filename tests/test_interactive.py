from __future__ import annotations

import threading
import time
from pathlib import Path

import yaml

from dataviz.artifacts import ArtifactStore
from dataviz.execution import Executor, InteractionExecutor
from dataviz.server.manager import RunManager
from dataviz.server import create_app
from dataviz.workspace import load_workspace, validate_workspace
from fastapi.testclient import TestClient


SESSION_A = "interactive-tab-a"
SESSION_B = "interactive-tab-b"


def build_interactive_workspace(root: Path, *, timeout: float = 5) -> Path:
    dashboard = root / "dashboards" / "interactive"
    (dashboard / "data").mkdir(parents=True)
    (dashboard / "transforms").mkdir()
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: interactive-tests
title: Interactive tests
runtime:
  max_workers: 3
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v2
kind: dashboard
id: interactive
title: Interactive contract
query_parameters:
  - {id: batch, type: integer, default: 7}
compute_parameters:
  - {id: factor, type: integer, default: 2}
  - {id: delay, type: number, default: 0}
dashboard_selections:
  - id: region
    type: multi_select
    field: region
    choices:
      - {label: North, value: north}
      - {label: South, value: south}
sources:
  - id: raw
    kind: source
    type: file
    path: data/rows.csv
    format: csv
    query_params: [batch]
    outputs: {main: {kind: table}}
interactive_transforms: [transforms/summary.yaml]
views:
  - {id: result, title: Result, template: table, input: interactive:summary/main}
sections:
  - {id: result, title: Result, views: [result]}
""",
        encoding="utf-8",
    )
    (dashboard / "data" / "rows.csv").write_text(
        "region,value\nnorth,2\nsouth,5\n",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "summary.yaml").write_text(
        f"""schema: dataviz/interactive-transform/v1
kind: interactive_transform
id: summary
runtime: server-python
code: summary.py
inputs:
  rows: source:raw/main
query_params: [batch]
compute_params: [factor, delay]
selections: [dashboard:interactive/region]
trigger: apply
export: {{mode: snapshot}}
outputs:
  main:
    kind: table
    schema:
      - {{name: region, dtype: str}}
      - {{name: value, dtype: int64}}
      - {{name: batch, dtype: int64}}
  total: {{kind: scalar}}
timeout_seconds: {timeout}
cache: {{mode: session}}
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "summary.py").write_text(
        """import time

def transform(context):
    assert context.adapter is None
    context.progress(0.1, "started")
    time.sleep(float(context.compute_params["delay"]))
    frame = context.table("rows").copy()
    selected = context.selections["dashboard:interactive/region"]
    context.log("applying region selection", selected=selected)
    if selected:
        frame = frame[frame["region"].isin(selected)]
    frame["value"] = frame["value"] * int(context.compute_params["factor"])
    frame["batch"] = int(context.query_params["batch"])
    context.progress(1.0, "complete")
    return {"main": frame, "total": int(frame["value"].sum())}
""",
        encoding="utf-8",
    )
    return root


def wait_for(predicate, *, timeout: float = 6) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for asynchronous execution")


def test_server_interactive_transform_has_isolated_context_named_outputs_and_cache(
    tmp_path: Path,
):
    workspace = load_workspace(build_interactive_workspace(tmp_path / "workspace"))
    assert validate_workspace(workspace) == []
    query_executor = Executor(workspace, cache_namespace=SESSION_A)
    run = query_executor.run("interactive", query_parameters={"batch": 11})
    events = []
    executor = InteractionExecutor(workspace, cache=query_executor.cache)

    first = executor.execute(
        run,
        "summary",
        compute_parameters={"factor": 3, "delay": 0},
        selections={"dashboard:interactive/region": ["north"]},
        observer=events.append,
    )
    second = executor.execute(
        run,
        "summary",
        compute_parameters={"factor": 3, "delay": 0},
        selections={"dashboard:interactive/region": ["north"]},
    )

    store = ArtifactStore(workspace.root, run.run_id)
    frame = store.read_table(first.outputs["interactive:summary/main"])
    assert first.status == "ready"
    assert first.query_parameters == {"batch": 11}
    assert first.compute_parameters == {"factor": 3, "delay": 0}
    assert first.selections == {"dashboard:interactive/region": ["north"]}
    assert frame.to_dict(orient="records") == [
        {"region": "north", "value": 6, "batch": 11}
    ]
    assert store.read_value(first.outputs["interactive:summary/total"]) == 6
    assert first.nodes["interactive:summary"].result_origin == "executed"
    assert second.nodes["interactive:summary"].result_origin == "cache"
    assert any(event["event"] == "node_progress" for event in events)
    assert any(event["event"] == "node_log" for event in events)
    log = first.nodes["interactive:summary"].log
    assert log is not None
    records = store.read_value(log)["records"]
    assert [item["event"] for item in records if "event" in item] == [
        "runtime_started",
        "runtime_completed",
    ]
    assert any(item["message"] == "applying region selection" for item in records)
    assert first.nodes["interactive:summary"].diagnostics["inputs"]["rows"][
        "content_hash"
    ] == run.outputs["source:raw/main"].content_hash


def test_server_interactive_timeout_and_cancel_are_process_hard_boundaries(
    tmp_path: Path,
):
    workspace = load_workspace(
        build_interactive_workspace(tmp_path / "workspace", timeout=0.15)
    )
    run = Executor(workspace).run("interactive")
    timeout_result = InteractionExecutor(workspace).execute(
        run,
        "summary",
        compute_parameters={"factor": 2, "delay": 2},
    )
    timeout_node = timeout_result.nodes["interactive:summary"]
    assert timeout_result.status == "error"
    assert timeout_node.status == "error"
    assert timeout_node.error["details"]["timeout_seconds"] == 0.15
    assert timeout_node.log is not None

    # Use a longer timeout for the explicit cancellation path.
    workspace = load_workspace(
        build_interactive_workspace(tmp_path / "cancel-workspace", timeout=5)
    )
    run = Executor(workspace).run("interactive")
    cancel_event = threading.Event()
    events = []
    holder = {}
    thread = threading.Thread(
        target=lambda: holder.setdefault(
            "result",
            InteractionExecutor(workspace).execute(
                run,
                "summary",
                compute_parameters={"factor": 2, "delay": 5},
                cancel_event=cancel_event,
                observer=events.append,
            ),
        )
    )
    thread.start()
    wait_for(lambda: any(event["event"] == "node_progress" for event in events))
    cancel_event.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert holder["result"].status == "cancelled"
    assert holder["result"].nodes["interactive:summary"].status == "cancelled"


def test_interaction_generations_are_isolated_by_tab_dashboard_and_query_run(
    tmp_path: Path,
):
    workspace = load_workspace(build_interactive_workspace(tmp_path / "workspace"))
    manager = RunManager(workspace)
    run_a = manager.start("interactive", {"batch": 1}, SESSION_A)
    run_b = manager.start("interactive", {"batch": 2}, SESSION_B)
    wait_for(lambda: run_a.result is not None and run_b.result is not None)

    first_a = manager.start_interaction(
        run_a.run_id,
        session_id=SESSION_A,
        target="summary",
        generation=1,
        compute_parameters={"factor": 2, "delay": 5},
        selections={"dashboard:interactive/region": ["north"]},
    )
    first_b = manager.start_interaction(
        run_b.run_id,
        session_id=SESSION_B,
        target="summary",
        generation=1,
        compute_parameters={"factor": 4, "delay": 0.2},
        selections={"dashboard:interactive/region": ["south"]},
    )
    wait_for(lambda: any(event["event"] == "node_progress" for event in first_a.events))
    second_a = manager.start_interaction(
        run_a.run_id,
        session_id=SESSION_A,
        target="summary",
        generation=2,
        compute_parameters={"factor": 3, "delay": 0},
        selections={"dashboard:interactive/region": ["north"]},
    )
    wait_for(
        lambda: all(
            item.status in {"ready", "error", "cancelled", "unavailable"}
            for item in (first_a, first_b, second_a)
        )
    )

    assert first_a.status == "cancelled"
    assert second_a.status == "ready"
    assert first_b.status == "ready"
    assert first_a.generation == 1
    assert second_a.generation == 2
    assert first_b.generation == 1
    assert manager.get_interaction(first_a.interaction_id, SESSION_B) is None
    store_a = ArtifactStore(workspace.root, run_a.run_id)
    store_b = ArtifactStore(workspace.root, run_b.run_id)
    assert store_a.read_value(second_a.result.outputs["interactive:summary/total"]) == 6
    assert store_b.read_value(first_b.result.outputs["interactive:summary/total"]) == 20


def test_server_interactive_dependency_is_reused_once_per_generation_chain(
    tmp_path: Path,
):
    root = build_interactive_workspace(tmp_path / "workspace")
    dashboard_root = root / "dashboards" / "interactive"
    dashboard_path = dashboard_root / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["interactive_transforms"].append("transforms/downstream.yaml")
    definition["views"].append(
        {
            "id": "downstream-total",
            "title": "Downstream total",
            "template": "metric",
            "input": "interactive:downstream/total",
        }
    )
    definition["sections"][0]["views"].append("downstream-total")
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    summary_path = dashboard_root / "transforms" / "summary.yaml"
    summary_path.write_text(
        summary_path.read_text(encoding="utf-8").replace(
            "cache: {mode: session}", "cache: {mode: none}"
        ),
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "downstream.yaml").write_text(
        """schema: dataviz/interactive-transform/v1
kind: interactive_transform
id: downstream
runtime: server-python
code: downstream.py
inputs: {rows: interactive:summary/main}
compute_params: [factor, delay]
selections: [dashboard:interactive/region]
trigger: apply
export: {mode: snapshot}
outputs: {total: {kind: scalar}}
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "downstream.py").write_text(
        """def transform(context):
    return {"total": int(context.table("rows")["value"].sum())}
""",
        encoding="utf-8",
    )
    workspace = load_workspace(root)
    assert validate_workspace(workspace) == []
    manager = RunManager(workspace)
    run = manager.start("interactive", {"batch": 7}, SESSION_A)
    wait_for(lambda: run.result is not None)

    upstream = manager.start_interaction(
        run.run_id,
        session_id=SESSION_A,
        target="summary",
        generation=1,
        compute_parameters={"factor": 2, "delay": 0},
        selections={"dashboard:interactive/region": ["north"]},
    )
    wait_for(lambda: upstream.status == "ready")
    downstream = manager.start_interaction(
        run.run_id,
        session_id=SESSION_A,
        target="downstream",
        generation=1,
        compute_parameters={"factor": 2, "delay": 0},
        selections={"dashboard:interactive/region": ["north"]},
    )
    wait_for(lambda: downstream.status == "ready")

    assert upstream.result.nodes["interactive:summary"].result_origin == "executed"
    reused = downstream.result.nodes["interactive:summary"]
    assert reused.result_origin == "generation"
    assert reused.diagnostics["reused_from_generation"] == 1
    store = ArtifactStore(workspace.root, run.run_id)
    assert store.read_value(downstream.result.outputs["interactive:downstream/total"]) == 4


def _start_query(client: TestClient, *, session_id: str = SESSION_A) -> str:
    run_id = client.post(
        "/api/dashboards/interactive/runs",
        json={"session_id": session_id, "query_parameters": {"batch": 7}},
    ).json()["run_id"]
    record = {}
    for _ in range(200):
        record = client.get(
            f"/api/runs/{run_id}", params={"session_id": session_id}
        ).json()
        if record["status"] in {"ready", "partial", "error", "cancelled"}:
            break
        time.sleep(0.02)
    assert record["status"] == "ready"
    return run_id


def test_server_report_materializes_server_python_snapshot(tmp_path: Path):
    root = build_interactive_workspace(tmp_path / "workspace")
    client = TestClient(create_app(root))
    run_id = _start_query(client)

    report = client.post(
        "/api/dashboards/interactive/report",
        json={
            "session_id": SESSION_A,
            "run_id": run_id,
            "compute_parameters": {"factor": 3, "delay": 0},
            "selections": {"dashboard:interactive/region": ["north"]},
        },
    )

    assert report.status_code == 200, report.text
    assert '"snapshot_interactions": ["summary"]' in report.text
    assert '"interactive:summary/main": [' in report.text
    assert '"value": 6' in report.text
    assert 'data-compute-frozen="true"' in report.text


def test_interaction_api_rejects_out_of_order_generation_without_cancelling_latest(
    tmp_path: Path,
):
    root = build_interactive_workspace(tmp_path / "workspace")
    client = TestClient(create_app(root))
    run_id = _start_query(client)
    request = {
        "session_id": SESSION_A,
        "transform_id": "summary",
        "compute_parameters": {"factor": 3, "delay": 0.2},
        "selections": {"dashboard:interactive/region": ["north"]},
    }

    latest = client.post(
        f"/api/runs/{run_id}/interactions",
        json={**request, "generation": 2},
    )
    stale = client.post(
        f"/api/runs/{run_id}/interactions",
        json={**request, "generation": 1},
    )

    assert latest.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "interaction_generation_stale"
    interaction_id = latest.json()["interaction_id"]
    payload = {}
    for _ in range(200):
        payload = client.get(
            f"/api/interactions/{interaction_id}",
            params={"session_id": SESSION_A},
        ).json()
        if payload["status"] in {"ready", "error", "cancelled", "unavailable"}:
            break
        time.sleep(0.02)
    assert payload["status"] == "ready"
    assert payload["generation"] == 2
    log = payload["result"]["nodes"]["interactive:summary"]["log"]
    artifact = client.get(
        f"/api/interactions/{interaction_id}/artifacts/{log['artifact_id']}",
        params={"session_id": SESSION_A},
    )
    assert artifact.status_code == 200
    assert artifact.json()["schema"] == "dataviz/execution-log/v1"
    assert any(
        item.get("message") == "applying region selection"
        for item in artifact.json()["records"]
    )
    assert client.get(
        f"/api/interactions/{interaction_id}/artifacts/{log['artifact_id']}",
        params={"session_id": SESSION_B},
    ).status_code == 404


def test_browser_snapshot_requires_current_canvas_outputs_and_embeds_them(
    tmp_path: Path,
):
    root = build_interactive_workspace(tmp_path / "workspace")
    transform_root = root / "dashboards" / "interactive" / "transforms"
    definition = (transform_root / "summary.yaml").read_text(encoding="utf-8")
    definition = definition.replace("runtime: server-python", "runtime: browser-js")
    definition = definition.replace("code: summary.py", "code: summary.js")
    (transform_root / "summary.yaml").write_text(definition, encoding="utf-8")
    (transform_root / "summary.js").write_text(
        "function transform(context) { return {main: [], total: 0}; }\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(root))
    run_id = _start_query(client)
    state = {
        "session_id": SESSION_A,
        "run_id": run_id,
        "compute_parameters": {"factor": 3, "delay": 0},
        "selections": {"dashboard:interactive/region": ["north"]},
    }

    missing = client.post(
        "/api/dashboards/interactive/report",
        json=state,
    )
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "snapshot_output_not_ready"

    report = client.post(
        "/api/dashboards/interactive/report",
        json={
            **state,
            "snapshot_outputs": {
                "interactive:summary/main": [
                    {"region": "north", "value": 999, "batch": 7}
                ],
                "interactive:summary/total": 999,
            },
        },
    )
    assert report.status_code == 200, report.text
    assert '"value": 999' in report.text
    assert '"interactive:summary/total": 999' in report.text
    assert '"snapshot_interactions": ["summary"]' in report.text
