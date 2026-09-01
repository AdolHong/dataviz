from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import yaml
import pytest

from dataviz.artifacts import ArtifactStore
from dataviz.execution import Executor, InteractionExecutor
from dataviz.execution.interactive import load_run_result
from dataviz.errors import ExecutionFailure
from dataviz.server.manager import RunManager
from dataviz.server import create_app
from dataviz.sources import SOURCE_RUNNERS
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.models import InteractiveTransformDefinition
from fastapi.testclient import TestClient


SESSION_A = "interactive-tab-a"
SESSION_B = "interactive-tab-b"


def query_state(*, batch: int = 7) -> dict[str, dict[str, object]]:
    return {
        "batch": {"value": batch},
        "items": {"selection": "all", "value": []},
    }


def test_interactive_trigger_defaults_follow_runtime():
    base = {
        "schema": "dataviz/interactive-transform/v4",
        "id": "runtime-default",
        "code": "transform.py",
        "export": {"mode": "snapshot"},
        "outputs": {"main": {"kind": "table"}},
    }
    browser = InteractiveTransformDefinition.model_validate(
        base | {"runtime": "browser-js", "code": "transform.js", "export": {"mode": "interactive"}}
    )
    server = InteractiveTransformDefinition.model_validate(base | {"runtime": "server-python"})

    assert browser.trigger == "auto"
    assert server.trigger == "apply"


def test_interactive_transform_rejects_retired_browser_python_runtime():
    with pytest.raises(ValueError, match="browser-python"):
        InteractiveTransformDefinition.model_validate(
            {
                "schema": "dataviz/interactive-transform/v4",
                "id": "retired-runtime",
                "runtime": "browser-python",
                "code": "transform.py",
                "export": {"mode": "interactive"},
                "outputs": {"main": {"kind": "table"}},
            }
        )


def interaction_state(
    *, factor: int = 2, delay: float = 0, region: str = "north"
) -> dict[str, dict[str, object]]:
    return {
        "dashboard:interactive/factor": {"value": factor, "revision": 0},
        "dashboard:interactive/delay": {"value": delay, "revision": 0},
        "dashboard:interactive/region": {
            "intent": "explicit",
            "value": [region],
            "revision": 0,
        }
    }


def build_interactive_workspace(
    root: Path,
    *,
    timeout: float = 5,
    max_concurrent_interactions: int = 4,
) -> Path:
    dashboard = root / "dashboards" / "interactive"
    (dashboard / "data").mkdir(parents=True)
    (dashboard / "transforms").mkdir()
    (root / "workspace.yaml").write_text(
        f"""schema: dataviz/workspace/v2
kind: workspace
id: interactive-tests
title: Interactive tests
runtime:
  max_workers: 3
  max_concurrent_interactions: {max_concurrent_interactions}
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v16
kind: dashboard
id: interactive
title: Interactive contract
query_parameters:
  - {id: batch, type: single_input, value_type: integer, default: 7}
  - id: items
    type: multiple_select
    value_type: text
    options:
      mode: static
      choices: [{label: A, value: a}, {label: B, value: b}]
controls:
  - {id: factor, type: single_input, value_type: integer, default: 2}
  - {id: delay, type: single_input, value_type: number, default: 0}
  - id: region
    type: multiple_select
    value_type: text
    field: region
    options:
      mode: static
      choices:
        - {label: North, value: north}
        - {label: South, value: south}
sources:
  - id: raw
    kind: source
    type: file
    path: data/rows.csv
    format: csv
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
        f"""schema: dataviz/interactive-transform/v4
kind: interactive_transform
id: summary
runtime: server-python
code: summary.py
inputs:
  rows: source:raw/main
query_inputs:
  batch: batch
  items_active: {{parameter: items, projection: active}}
  items_selection: {{parameter: items, projection: selection}}
control_inputs:
  factor: {{mode: value, control: dashboard.factor}}
  delay: {{mode: value, control: dashboard.delay}}
  region: {{mode: filter, control: dashboard.region, field: region, inputs: [rows], empty: match_none}}
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
    time.sleep(float(context.control_inputs["delay"]))
    frame = context.table("rows").copy()
    assert context.query_inputs["items_active"] is False
    assert context.query_inputs["items_selection"] == "all"
    selected = context.control_inputs["region"]
    context.log("applying region selection", selected=selected)
    if selected:
        assert frame["region"].tolist() == selected
    frame["value"] = frame["value"] * int(context.control_inputs["factor"])
    frame["batch"] = int(context.query_inputs["batch"])
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


def test_one_control_can_feed_auto_and_apply_consumers(tmp_path: Path):
    root = build_interactive_workspace(tmp_path / "workspace")
    dashboard_root = root / "dashboards" / "interactive"
    dashboard_path = dashboard_root / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["interactive_transforms"].append("transforms/preview.yaml")
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "preview.yaml").write_text(
        """schema: dataviz/interactive-transform/v4
kind: interactive_transform
id: preview
runtime: browser-js
code: preview.js
inputs: {rows: source:raw/main}
control_inputs:
  factor: {mode: value, control: dashboard.factor}
trigger: auto
export: {mode: interactive}
outputs: {main: {kind: table}}
""",
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "preview.js").write_text(
        "export default context => ({main: context.inputs.rows});\n",
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    assert validate_workspace(workspace) == []
    control = workspace.dashboard("interactive").dependency_contract.controls[
        "dashboard:interactive/factor"
    ]
    assert control.transform_consumers == (
        "preview",
        "summary",
    )


def test_server_interactive_transform_has_isolated_context_named_outputs_and_cache(
    tmp_path: Path,
):
    workspace = load_workspace(build_interactive_workspace(tmp_path / "workspace"))
    assert validate_workspace(workspace) == []
    query_executor = Executor(workspace, cache_namespace=SESSION_A)
    run = query_executor.run("interactive", query_parameter_state=query_state(batch=11))
    events = []
    executor = InteractionExecutor(workspace, cache=query_executor.cache)

    first = executor.execute(
        run,
        "summary",
        control_state=interaction_state(factor=3, delay=0, region="north"),
        observer=events.append,
    )
    second = executor.execute(
        run,
        "summary",
        control_state=interaction_state(factor=3, delay=0, region="north"),
    )

    store = ArtifactStore(workspace.root, run.run_id)
    frame = store.read_table(first.outputs["interactive:summary/main"])
    assert first.status == "ready"
    assert first.query_parameter_state == query_state(batch=11)
    assert first.control_state == interaction_state(factor=3, delay=0, region="north")
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


def test_server_interactive_inputs_are_classified_and_reuse_the_tab_run_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    workspace = load_workspace(build_interactive_workspace(tmp_path / "workspace"))
    dashboard = workspace.dashboard("interactive")
    assert dashboard.dependency_contract.server_interactive_base_references() == {
        "source:raw/main"
    }

    manager = RunManager(workspace)
    run = manager.start("interactive", query_state(batch=11), SESSION_A)
    wait_for(lambda: run.result is not None)

    assert run.status == "ready"
    assert run.server_interactive_inputs == ["source:raw/main"]
    descriptor = run.result.outputs["source:raw/main"]
    assert descriptor.path.startswith(
        f".dataviz/runs/{run.run_id}/artifacts/"
    )

    class SourceMustNotRunAgain:
        def run(self, request):  # pragma: no cover - failure path documents the contract
            raise AssertionError("Interactive computation must not re-run its Source")

    monkeypatch.setitem(SOURCE_RUNNERS, "file", SourceMustNotRunAgain())

    with pytest.raises(ValueError, match="browser-tab session"):
        manager.start_interaction(
            run.run_id,
            session_id=SESSION_B,
            target="summary",
            generation=1,
            control_state=interaction_state(factor=4, delay=0, region="north"),
        )

    interaction = manager.start_interaction(
        run.run_id,
        session_id=SESSION_A,
        target="summary",
        generation=1,
        control_state=interaction_state(factor=4, delay=0, region="north"),
    )
    wait_for(lambda: interaction.status in {"ready", "error", "cancelled"})

    assert interaction.status == "ready"
    store = ArtifactStore(workspace.root, run.run_id)
    assert store.read_value(
        interaction.result.outputs["interactive:summary/total"]
    ) == 8


def test_browser_only_interactive_branch_does_not_pin_server_inputs(tmp_path: Path):
    workspace = load_workspace(build_interactive_workspace(tmp_path / "workspace"))
    dashboard = workspace.dashboard("interactive")
    dashboard.interactive_transforms["summary"][1].runtime = "browser-js"

    assert dashboard.dependency_contract.server_interactive_base_references() == set()


def test_server_interactive_logs_and_tracebacks_redact_workspace_credentials(
    tmp_path: Path,
    monkeypatch,
):
    root = build_interactive_workspace(tmp_path / "workspace")
    auth = root / "auth"
    auth.mkdir()
    (auth / "adapters.local.yaml").write_text(
        """adapters:
  private-api:
    type: python
    password: password-secret
    secrets:
      api_token: DATAVIZ_TEST_API_TOKEN
""",
        encoding="utf-8",
    )
    transform = root / "dashboards" / "interactive" / "transforms" / "summary.py"
    transform.write_text(
        """def transform(context):
    context.log("using password-secret", token="token-secret")
    raise RuntimeError("failed with password-secret and token-secret")
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATAVIZ_TEST_API_TOKEN", "token-secret")
    workspace = load_workspace(root)
    run = Executor(workspace).run("interactive")
    events: list[dict] = []
    result = InteractionExecutor(workspace).execute(
        run,
        "summary",
        observer=events.append,
    )

    serialized = result.model_dump_json()
    assert result.status == "error"
    assert "password-secret" not in serialized
    assert "token-secret" not in serialized
    assert "[REDACTED]" in serialized
    log = result.nodes["interactive:summary"].log
    assert log is not None
    log_value = ArtifactStore(root, run.run_id).read_value(log)
    assert "password-secret" not in json.dumps(log_value)
    assert "token-secret" not in json.dumps(log_value)
    assert all(
        "password-secret" not in json.dumps(event)
        and "token-secret" not in json.dumps(event)
        for event in events
    )


def test_targeted_query_run_must_contain_interactive_base_inputs(tmp_path: Path):
    root = build_interactive_workspace(tmp_path / "workspace")
    dashboard_path = root / "dashboards" / "interactive" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"].append(
        {
            "id": "other",
            "kind": "source",
            "type": "file",
            "path": "data/other.csv",
            "outputs": {"main": {"kind": "table"}},
        }
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (root / "dashboards" / "interactive" / "data" / "other.csv").write_text(
        "value\n1\n", encoding="utf-8"
    )
    workspace = load_workspace(root)
    run = Executor(workspace).run("interactive", targets=["source:other"])

    with pytest.raises(ExecutionFailure) as failure:
        InteractionExecutor(workspace).execute(run, "summary")

    assert failure.value.details == {
        "code": "query_run_missing_interactive_inputs",
        "references": ["source:raw/main"],
        "required_targets": ["source:raw"],
        "status": "ready",
        "action": "Run query again with the required targets",
    }


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
        control_state=interaction_state(factor=2, delay=2),
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
                control_state=interaction_state(factor=2, delay=5),
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
    run_a = manager.start("interactive", query_state(batch=1), SESSION_A)
    run_b = manager.start("interactive", query_state(batch=2), SESSION_B)
    wait_for(lambda: run_a.result is not None and run_b.result is not None)

    first_a = manager.start_interaction(
        run_a.run_id,
        session_id=SESSION_A,
        target="summary",
        generation=1,
        control_state=interaction_state(factor=2, delay=5, region="north"),
    )
    first_b = manager.start_interaction(
        run_b.run_id,
        session_id=SESSION_B,
        target="summary",
        generation=1,
        control_state=interaction_state(factor=4, delay=0.2, region="south"),
    )
    wait_for(lambda: any(event["event"] == "node_progress" for event in first_a.events))
    second_a = manager.start_interaction(
        run_a.run_id,
        session_id=SESSION_A,
        target="summary",
        generation=2,
        control_state=interaction_state(factor=3, delay=0, region="north"),
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


def test_server_interactions_are_globally_bounded_on_one_machine(tmp_path: Path):
    workspace = load_workspace(
        build_interactive_workspace(
            tmp_path / "workspace",
            max_concurrent_interactions=1,
        )
    )
    manager = RunManager(workspace)
    run_a = manager.start("interactive", query_state(batch=1), SESSION_A)
    run_b = manager.start("interactive", query_state(batch=2), SESSION_B)
    wait_for(lambda: run_a.result is not None and run_b.result is not None)

    first = manager.start_interaction(
        run_a.run_id,
        session_id=SESSION_A,
        target="summary",
        generation=1,
        control_state=interaction_state(factor=2, delay=0.4, region="north"),
    )
    wait_for(lambda: first.status == "loading")
    second = manager.start_interaction(
        run_b.run_id,
        session_id=SESSION_B,
        target="summary",
        generation=1,
        control_state=interaction_state(factor=3, delay=0, region="south"),
    )

    time.sleep(0.08)
    assert second.status == "queued"
    wait_for(lambda: first.status == "ready" and second.status == "ready")


def test_queued_server_interaction_can_be_cancelled_before_slot_is_available(
    tmp_path: Path,
):
    workspace = load_workspace(
        build_interactive_workspace(
            tmp_path / "workspace",
            max_concurrent_interactions=1,
        )
    )
    manager = RunManager(workspace)
    run = manager.start("interactive", query_state(batch=1), SESSION_A)
    wait_for(lambda: run.result is not None)
    assert manager.interaction_slots.acquire(timeout=0.1)
    try:
        interaction = manager.start_interaction(
            run.run_id,
            session_id=SESSION_A,
            target="summary",
            generation=1,
            control_state=interaction_state(factor=2, delay=0, region="north"),
        )
        manager.cancel_interaction(interaction.interaction_id, SESSION_A)
        wait_for(lambda: interaction.status == "cancelled", timeout=1)

        assert interaction.result is None
        assert interaction.finished_at is not None
        assert interaction.events[-1]["event"] == "interaction_cancelled"
        assert interaction.events[-1]["phase"] == "queued"
    finally:
        manager.interaction_slots.release()


def test_server_rejects_interaction_when_query_contract_changed(
    tmp_path: Path,
):
    root = build_interactive_workspace(tmp_path / "workspace")
    client = TestClient(create_app(root))
    started = client.post(
        "/api/dashboards/interactive/runs",
        json={"session_id": SESSION_A, "query_parameter_state": query_state()},
    ).json()
    run_id = started["run_id"]

    def ready() -> bool:
        response = client.get(
            f"/api/runs/{run_id}", params={"session_id": SESSION_A}
        )
        return response.json()["status"] in {"ready", "partial", "error"}

    wait_for(ready)
    dashboard_path = root / "dashboards" / "interactive" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["options"] = {"keep_default_na": False}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    response = client.post(
        f"/api/runs/{run_id}/interactions",
        json={
            "session_id": SESSION_A,
            "transform_id": "summary",
            "generation": 1,
            "control_state": interaction_state(factor=2, delay=0),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "query_run_contract_changed"
    assert response.json()["detail"]["details"]["action"] == "Run query again"


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
        """schema: dataviz/interactive-transform/v4
kind: interactive_transform
id: downstream
runtime: server-python
code: downstream.py
inputs: {rows: interactive:summary/main}
control_inputs:
  factor: {mode: value, control: dashboard.factor}
  delay: {mode: value, control: dashboard.delay}
  region: {mode: filter, control: dashboard.region, field: region, inputs: [rows], empty: match_none}
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
    run = manager.start("interactive", query_state(), SESSION_A)
    wait_for(lambda: run.result is not None)

    upstream = manager.start_interaction(
        run.run_id,
        session_id=SESSION_A,
        target="summary",
        generation=1,
        control_state=interaction_state(factor=2, delay=0, region="north"),
    )
    wait_for(lambda: upstream.status == "ready")
    downstream = manager.start_interaction(
        run.run_id,
        session_id=SESSION_A,
        target="downstream",
        generation=1,
        control_state=interaction_state(factor=2, delay=0, region="north"),
    )
    wait_for(lambda: downstream.status == "ready")

    assert upstream.result.nodes["interactive:summary"].result_origin == "executed"
    reused = downstream.result.nodes["interactive:summary"]
    assert reused.result_origin == "generation"
    assert reused.diagnostics["reused_from_generation"] == 1
    store = ArtifactStore(workspace.root, run.run_id)
    assert store.read_value(downstream.result.outputs["interactive:downstream/total"]) == 4

    corrupt = store.resolve(
        downstream.result.outputs["interactive:summary/main"]
    )
    corrupt.write_bytes(b"corrupt generation artifact")
    recovered = manager.start_interaction(
        run.run_id,
        session_id=SESSION_A,
        target="downstream",
        generation=2,
        control_state=interaction_state(factor=2, delay=0, region="north"),
    )
    wait_for(lambda: recovered.status == "ready")

    assert recovered.result.nodes["interactive:summary"].result_origin == "executed"
    assert store.read_value(recovered.result.outputs["interactive:downstream/total"]) == 4


def _start_query(client: TestClient, *, session_id: str = SESSION_A) -> str:
    run_id = client.post(
        "/api/dashboards/interactive/runs",
        json={"session_id": session_id, "query_parameter_state": query_state()},
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


def test_server_report_rejects_server_python_and_recommends_share(tmp_path: Path):
    root = build_interactive_workspace(tmp_path / "workspace")
    client = TestClient(create_app(root))
    run_id = _start_query(client)

    report = client.post(
        "/api/dashboards/interactive/report",
        json={
            "session_id": SESSION_A,
            "run_id": run_id,
            "control_state": interaction_state(factor=3, delay=0, region="north"),
        },
    )

    assert report.status_code == 409, report.text
    detail = report.json()["detail"]
    assert detail["code"] == "html_export_server_runtime_unavailable"
    assert detail["transforms"] == ["summary"]
    assert "shared link" in detail["message"]


def test_interaction_api_rejects_out_of_order_generation_without_cancelling_latest(
    tmp_path: Path,
):
    root = build_interactive_workspace(tmp_path / "workspace")
    client = TestClient(create_app(root))
    run_id = _start_query(client)
    request = {
        "session_id": SESSION_A,
        "transform_id": "summary",
        "control_state": interaction_state(factor=3, delay=0.2, region="north"),
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
        "control_state": interaction_state(factor=3, delay=0, region="north"),
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


def test_corrupt_query_run_metadata_has_a_stable_error(tmp_path: Path):
    run_root = tmp_path / ".dataviz" / "runs" / "run_corrupt"
    run_root.mkdir(parents=True)
    (run_root / "result.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(ExecutionFailure) as failure:
        load_run_result(tmp_path, "run_corrupt")

    assert failure.value.details["code"] == "query_run_corrupt"
    assert failure.value.details["run_id"] == "run_corrupt"


def test_persisted_query_run_verifies_artifact_ownership_and_content(tmp_path: Path):
    root = build_interactive_workspace(tmp_path / "artifact-integrity")
    workspace = load_workspace(root)
    result = Executor(workspace).run("interactive")
    descriptor = result.outputs["source:raw/main"]
    artifact_path = root / descriptor.path
    artifact_path.write_bytes(artifact_path.read_bytes() + b"corrupt")

    with pytest.raises(ExecutionFailure) as failure:
        load_run_result(root, result.run_id)

    assert failure.value.details["code"] == "query_run_artifact_corrupt"
    assert failure.value.details["run_id"] == result.run_id
    assert failure.value.details["artifact_id"] == descriptor.artifact_id
    persisted = (root / ".dataviz" / "runs" / result.run_id / "result.json").read_text(
        encoding="utf-8"
    )
    assert '"schema": "dataviz/query-result/v1"' in persisted
