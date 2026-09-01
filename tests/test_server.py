from __future__ import annotations

import json
import re
import time
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pytest
import yaml

from fastapi.testclient import TestClient

from dataviz.artifacts import ArtifactStore
from dataviz.server import create_app
from dataviz.server.manager import InteractionRecord, RunManager, RunRecord
from dataviz.execution.cache import NodeCache
import dataviz.execution.cache as cache_module
from dataviz.execution.events import ExecutionEvent
from dataviz.sources import SOURCE_RUNNERS
from dataviz.workspace import load_workspace
from dataviz.workspace.models import CacheDefinition
from dataviz.workspace.navigation import NavigationEditor


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "examples" / "sales-workspace"
MINIMAL_WORKSPACE = ROOT / "examples" / "minimal-workspace"
REPEAT_WORKSPACE = ROOT / "examples" / "repeat-workspace"
SESSION_A = "tab_session_a123"
SESSION_B = "tab_session_b456"


def _query_state(**values):
    return {name: {"value": value} for name, value in values.items()}


@pytest.fixture(scope="module", autouse=True)
def _isolate_repository_workspaces(isolated_workspace):
    global WORKSPACE, MINIMAL_WORKSPACE, REPEAT_WORKSPACE
    WORKSPACE = isolated_workspace(WORKSPACE)
    MINIMAL_WORKSPACE = isolated_workspace(MINIMAL_WORKSPACE)
    REPEAT_WORKSPACE = isolated_workspace(REPEAT_WORKSPACE)


def wait_for(predicate, *, timeout: float = 6) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition did not become true before timeout")


def test_server_exposes_active_presentation_contract():
    client = TestClient(create_app(MINIMAL_WORKSPACE))
    summary = client.get("/api/workspace").json()
    dashboard = next(item for item in summary["dashboards"] if item["id"] == "sales-overview")

    assert dashboard["presentation"]["active"] is True
    assert dashboard["presentation"]["file"].endswith("presentation.yaml")
    assert dashboard["presentation"]["diagnostics"] == []
    assert dashboard["presentation"]["control_panels"]["query"] == {
        "template": "auto",
        "width": "auto",
        "columns": None,
        "column_width": None,
        "density": "comfortable",
    }
    assert not [item for item in summary["diagnostics"] if item["level"] == "error"]


def test_server_exposes_the_pinned_direct_plotly_browser_runtime():
    client = TestClient(create_app(MINIMAL_WORKSPACE, watch=False))

    response = client.get("/runtime/plotly.js")

    assert response.status_code == 200
    assert response.headers["x-dataviz-plotly-version"] == "4.0.0"
    assert response.text.startswith("/**\n* plotly.js v4.0.0")


def test_parameter_editor_updates_only_defaults_static_choices_and_sibling_order(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples" / "feature-showcase", root)
    path = (
        root
        / "dashboards"
        / "功能示例##parameter-playground"
        / "dashboard.yaml"
    )
    path.write_text("# author note must survive\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    client = TestClient(create_app(root, watch=False))

    shell = client.get("/")
    assert shell.status_code == 200
    assert 'id="parameter-editor-dialog"' in shell.text
    assert 'id="run-button"' in shell.text
    assert 'id="dashboard-controls-control"' in shell.text
    assert "右键编辑" in shell.text

    contract = client.get(
        "/api/dashboards/parameter-playground/parameter-editor"
    )
    assert contract.status_code == 200
    editor = contract.json()
    groups = {group["owner"]: group for group in editor["groups"]}
    assert {"query", "dashboard", "section:experiment", "view:parameter-line", "view:parameter-table"} == set(groups)
    assert groups["view:parameter-line"]["items"] == []

    response = client.patch(
        "/api/dashboards/parameter-playground/parameter-editor",
        json={
            "revision": editor["revision"],
            "group": {
                "owner": "query",
                "order": ["row_count", "multiplier"],
                "items": [
                    {"id": "row_count", "default": 24},
                    {"id": "multiplier", "default": 3},
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    editor = response.json()["editor"]

    dashboard_group = next(
        group for group in editor["groups"] if group["owner"] == "dashboard"
    )
    response = client.patch(
        "/api/dashboards/parameter-playground/parameter-editor",
        json={
            "revision": editor["revision"],
            "group": {
                "owner": "dashboard",
                "order": ["segment"],
                "items": [
                    {
                        "id": "segment",
                        "initial": {
                            "mode": "values",
                            "values": ["Alpha", "Delta"],
                        },
                        "choices": [
                            {"label": "Alpha", "value": "Alpha"},
                            {"label": "Delta", "value": "Delta"},
                        ],
                    }
                ],
            },
        },
    )
    assert response.status_code == 200, response.text

    source = path.read_text(encoding="utf-8")
    saved = yaml.safe_load(source)
    assert source.startswith("# author note must survive")
    assert [item["id"] for item in saved["query_parameters"]] == [
        "row_count",
        "multiplier",
    ]
    assert [item["default"] for item in saved["query_parameters"]] == [24, 3]
    assert saved["controls"][0]["initial"] == {
        "mode": "values",
        "values": ["Alpha", "Delta"],
    }
    assert saved["controls"][0]["options"]["choices"] == [
        {"label": "Alpha", "value": "Alpha"},
        {"label": "Delta", "value": "Delta"},
    ]
    assert dashboard_group["items"][0]["choices_editable"] is True


def test_parameter_editor_exposes_nested_groups_and_rejects_stale_revisions(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples" / "feature-showcase", root)
    client = TestClient(create_app(root, watch=False))
    url = "/api/dashboards/cascade-explorer/parameter-editor"
    editor = client.get(url).json()
    groups = {group["owner"]: group for group in editor["groups"]}

    assert set(groups) == {
        "query",
        "dashboard",
        "section:geography",
        "section:files",
        "view:map-bars",
        "view:city-detail",
        "view:uploaded-file",
        "view:bundled-file",
    }
    assert groups["query"]["items"] == []
    assert groups["section:files"]["items"] == []
    assert groups["view:map-bars"]["items"] == []
    assert groups["section:geography"]["items"][0]["option_source"] == "infer"
    assert groups["section:geography"]["items"][0]["default_editable"] is False
    view = groups["view:city-detail"]

    response = client.patch(
        url,
        json={
            "revision": editor["revision"],
            "group": {
                "owner": "view:city-detail",
                "order": ["min_value", "district"],
                "items": [
                    {"id": "min_value", "default": 10},
                    {
                        "id": "district",
                        "initial": {"mode": "all"},
                        "choices": [],
                    },
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    saved = load_workspace(root).dashboard("cascade-explorer").definition
    city_detail = next(item for item in saved.views if item.id == "city-detail")
    assert [item.id for item in city_detail.controls] == ["min_value", "district"]
    assert city_detail.controls[0].default == 10

    stale = client.patch(
        url,
        json={
            "revision": editor["revision"],
            "group": {
                "owner": view["owner"],
                "order": view["order"],
                "items": [
                    {
                        "id": item["id"],
                        "default": item["default"],
                        "initial": item["initial"],
                        "choices": item["choices"] if item["choices_editable"] else [],
                    }
                    for item in view["items"]
                ],
            },
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["details"]["code"] == "parameter_editor_revision_conflict"


def test_parameter_editor_round_trips_relative_date_defaults(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples" / "feature-showcase", root)
    client = TestClient(create_app(root, watch=False))
    url = "/api/dashboards/date-parameter-lab/parameter-editor"
    editor = client.get(url).json()
    query = next(group for group in editor["groups"] if group["owner"] == "query")

    assert query["items"][0]["default"] == {
        "mode": "relative",
        "anchor": "today",
        "offset": "-1d",
    }
    assert query["items"][1]["default"] == [
        {"mode": "relative", "anchor": "today", "offset": "-7d"},
        {"mode": "relative", "anchor": "today", "offset": "-1d"},
    ]

    response = client.patch(
        url,
        json={
            "revision": editor["revision"],
            "group": {
                "owner": "query",
                "order": ["report_range", "analysis_date"],
                "items": [
                    {
                        "id": "report_range",
                        "default": [
                            {"mode": "relative", "anchor": "today", "offset": "-14d"},
                            {"mode": "relative", "anchor": "today", "offset": "-2d"},
                        ],
                    },
                    {
                        "id": "analysis_date",
                        "default": {
                            "mode": "relative",
                            "anchor": "today",
                            "offset": "-2d",
                        },
                    },
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    saved = yaml.safe_load(
        (
            root
            / "dashboards"
            / "功能示例##date-parameter-lab"
            / "dashboard.yaml"
        ).read_text(encoding="utf-8")
    )
    assert [item["id"] for item in saved["query_parameters"]] == [
        "report_range",
        "analysis_date",
    ]
    assert saved["query_parameters"][0]["default"][0]["offset"] == "-14d"
    assert saved["query_parameters"][1]["default"]["offset"] == "-2d"


def test_parameter_editor_can_mix_fixed_and_relative_range_endpoints(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples" / "feature-showcase", root)
    client = TestClient(create_app(root, watch=False))
    url = "/api/dashboards/date-parameter-lab/parameter-editor"
    editor = client.get(url).json()

    response = client.patch(
        url,
        json={
            "revision": editor["revision"],
            "group": {
                "owner": "query",
                "order": ["analysis_date", "report_range"],
                "items": [
                    {"id": "analysis_date", "default": "2026-08-20"},
                    {
                        "id": "report_range",
                        "default": [
                            "2026-08-01",
                            {"mode": "relative", "anchor": "today", "offset": "-1d"},
                        ],
                    },
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    saved = yaml.safe_load(
        (
            root
            / "dashboards"
            / "功能示例##date-parameter-lab"
            / "dashboard.yaml"
        ).read_text(encoding="utf-8")
    )
    assert saved["query_parameters"][0]["default"] == "2026-08-20"
    assert saved["query_parameters"][1]["default"] == [
        "2026-08-01",
        {"mode": "relative", "anchor": "today", "offset": "-1d"},
    ]


def test_nested_parameter_editor_actions_are_server_context_menus_only():
    renderer = (ROOT / "src" / "dataviz" / "rendering" / "canvas.py").read_text()
    runtime = (
        ROOT / "src" / "dataviz" / "server" / "static" / "canvas-runtime.js"
    ).read_text()
    server_app = (
        ROOT / "src" / "dataviz" / "server" / "static" / "app.js"
    ).read_text()

    assert "data-editor-owner" in renderer
    assert "右键编辑默认配置" in renderer
    assert "window.dataviz.asset_mode === 'server'" in runtime
    assert "addEventListener('contextmenu'" in runtime
    assert "dataviz:open-parameter-editor" in runtime
    assert "data-dv-author-control-editor" not in renderer
    assert "parameter-editor__drag-handle" in server_app
    assert "dataset.editorDateAtom" in server_app
    assert "dataset.editorDisclosure" in server_app
    assert "dataviz:editor-change" in server_app
    assert '<button type="submit" class="button button--run" disabled>保存</button>' in server_app
    assert "if (!dashboardControls().length) return" not in server_app


def test_workspace_api_resolves_relative_query_defaults_to_concrete_tab_values(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, root)
    dashboard_path = root / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["query_parameters"].append(
        {
            "id": "job_date_range",
            "type": "range_input", "value_type": "date",
            "label": "Job date range",
            "required": True,
            "default": [
                {"mode": "relative", "anchor": "today", "offset": "-3d"},
                {"mode": "relative", "anchor": "today", "offset": "-1d"},
            ],
        }
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    timezone = ZoneInfo("Asia/Shanghai")
    before = datetime.now(timezone).date()

    client = TestClient(create_app(root))
    summary = client.get("/api/workspace").json()
    after = datetime.now(timezone).date()
    dashboard = next(
        item for item in summary["dashboards"] if item["id"] == "sales-overview"
    )
    parameter = next(
        item for item in dashboard["query_parameters"] if item["id"] == "job_date_range"
    )
    expected = {
        tuple(
            (anchor + timedelta(days=offset)).isoformat()
            for offset in (-3, -1)
        )
        for anchor in {before, after}
    }

    assert tuple(parameter["resolved_default_state"]["value"]) in expected
    assert parameter["default"] == [
        {"mode": "relative", "anchor": "today", "offset": "-3d"},
        {"mode": "relative", "anchor": "today", "offset": "-1d"},
    ]

    started = client.post(
        "/api/dashboards/sales-overview/runs",
        json={"session_id": SESSION_A, "query_parameter_state": _query_state(min_query_revenue=0)},
    ).json()
    record = None
    for _ in range(100):
        record = client.get(
            f"/api/runs/{started['run_id']}", params={"session_id": SESSION_A}
        ).json()
        if record["status"] in {"ready", "partial", "error"}:
            break
        time.sleep(0.05)
    assert record and record["status"] == "ready", record
    assert tuple(record["result"]["query_parameter_state"]["job_date_range"]["value"]) in expected


def test_queued_query_can_be_cancelled_before_a_global_slot_is_available(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, root)
    workspace_path = root / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition["runtime"] = {"max_concurrent_runs": 1}
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    manager = RunManager(load_workspace(root))
    assert manager.run_slots.acquire(timeout=0.1)
    try:
        record = manager.start(
            "sales-overview",
            _query_state(min_query_revenue=0),
            SESSION_A,
        )
        wait_for(lambda: any(event.event == "run_queued" for event in record.events))
        manager.cancel(record.run_id, SESSION_A)
        wait_for(lambda: record.status == "cancelled", timeout=1)

        assert record.result is None
        assert record.finished_at is not None
        assert record.events[-1].event == "run_cancelled"
        assert record.events[-1].data["phase"] == "queued"
    finally:
        manager.run_slots.release()


def test_server_rejects_query_when_static_preflight_has_errors(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, root)
    presentation_path = root / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation.setdefault("assets", {}).setdefault("css", []).append(
        "assets/missing.css"
    )
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    client = TestClient(create_app(root))

    response = client.post(
        "/api/dashboards/sales-overview/runs",
        json={"session_id": SESSION_A, "query_parameter_state": {}},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "dashboard_preflight_failed"


def test_run_preflight_reloads_dashboard_files_changed_after_server_start(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, root)
    client = TestClient(create_app(root))
    presentation_path = root / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation.setdefault("assets", {}).setdefault("css", []).append(
        "assets/added-after-start.css"
    )
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    response = client.post(
        "/api/dashboards/sales-overview/runs",
        json={
            "session_id": SESSION_A,
            "query_parameter_state": _query_state(min_query_revenue=0),
        },
    )

    assert response.status_code == 422
    diagnostics = response.json()["detail"]["details"]["diagnostics"]
    assert any(item["code"] == "presentation_asset_missing" for item in diagnostics)
    assert response.json()["detail"]["details"]["diagnostics"][0]["level"] == "error"


def test_workspace_refresh_replaces_the_complete_snapshot(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, root)
    app = create_app(root)
    original = app.state.workspace
    workspace_path = root / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition["title"] = "Reloaded workspace"
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    response = TestClient(app).get("/api/workspace")

    assert response.status_code == 200
    assert response.json()["workspace"]["title"] == "Reloaded workspace"
    assert app.state.workspace is not original
    assert original.definition.title != "Reloaded workspace"


def test_workspace_refresh_rebinds_tab_executor_without_mutating_active_snapshot(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, root)
    first_workspace = load_workspace(root)
    manager = RunManager(first_workspace)
    first_executor = manager.executor_for(SESSION_A)
    workspace_path = root / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition["title"] = "Second snapshot"
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    second_workspace = load_workspace(root)

    manager.install_workspace_snapshot(second_workspace)
    second_executor = manager.executor_for(SESSION_A)

    assert second_executor is not first_executor
    assert second_executor.cache is first_executor.cache
    assert first_executor.workspace is first_workspace
    assert first_executor.workspace.definition.title != "Second snapshot"
    assert second_executor.workspace.definition.title == "Second snapshot"


def test_existing_run_allows_presentation_edits_but_rejects_query_logic_drift(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, root)
    client = TestClient(create_app(root))
    started = client.post(
        "/api/dashboards/sales-overview/runs",
        json={
            "session_id": SESSION_A,
            "query_parameter_state": _query_state(min_query_revenue=0),
        },
    ).json()
    run_id = started["run_id"]
    for _ in range(100):
        record = client.get(
            f"/api/runs/{run_id}", params={"session_id": SESSION_A}
        ).json()
        if record["status"] in {"ready", "partial", "error"}:
            break
        time.sleep(0.05)
    assert record["status"] == "ready"

    presentation_path = root / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation.setdefault("theme", {})["accent"] = "#123456"
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    presentation_only = client.get(
        "/api/dashboards/sales-overview/canvas",
        params={
            "session_id": SESSION_A,
            "run_id": run_id,
            "frame_id": "frame_presentation",
        },
    )
    assert presentation_only.status_code == 200

    sql_path = root / "dashboards" / "sales-overview" / "sources" / "sales.sql"
    sql_path.write_text(
        sql_path.read_text(encoding="utf-8") + "\n-- changed query contract\n",
        encoding="utf-8",
    )
    stale_canvas = client.get(
        "/api/dashboards/sales-overview/canvas",
        params={
            "session_id": SESSION_A,
            "run_id": run_id,
            "frame_id": "frame_stale",
        },
    )
    stale_report = client.post(
        "/api/dashboards/sales-overview/report",
        json={"session_id": SESSION_A, "run_id": run_id},
    )

    assert stale_canvas.status_code == 409
    assert "QUERY RUN OUTDATED" in stale_canvas.text
    assert "Run query" in stale_canvas.text
    assert stale_report.status_code == 409
    assert stale_report.json()["detail"]["code"] == "query_run_contract_changed"
    remembered = client.get(
        "/api/session/runs", params={"session_id": SESSION_A}
    ).json()["runs"]
    assert remembered[0]["run_id"] == run_id
    assert remembered[0]["query_outdated"] is True


def test_server_run_and_canvas():
    client = TestClient(create_app(WORKSPACE))
    assert client.get("/").status_code == 200
    summary = client.get("/api/workspace").json()
    assert summary["dashboards"][0]["id"] == "sales"
    assert summary["dashboards"][0]["canvas_name"] == "sales"
    assert summary["dashboards"][0]["query_parameters"][0]["id"] == "target_factor"
    assert {item["origin"] for item in summary["dashboards"][0]["controls"]} == {
        "dashboard",
        "section",
        "view",
    }
    assert all("kind" not in item for item in summary["dashboards"][0]["controls"])
    assert all(
        "runtime_checked_views" in item
        and "declared_direct_views" in item
        for item in summary["dashboards"][0]["controls"]
    )
    started = client.post(
        "/api/dashboards/sales/runs",
        json={
            "session_id": SESSION_A,
            "query_parameter_state": _query_state(target_factor=1.0),
            "refresh": True,
        },
    ).json()
    run_id = started["run_id"]
    record = None
    for _ in range(100):
        record = client.get(f"/api/runs/{run_id}", params={"session_id": SESSION_A}).json()
        if record["status"] in {"ready", "partial", "error"}:
            break
        time.sleep(0.05)
    assert record and record["status"] == "ready", record
    target_evidence = record["result"]["nodes"]["source:targets"]["diagnostics"]["query"]
    assert target_evidence["adapter_reference"] == "demo-sqlite"
    assert target_evidence["resolved_sql"]
    assert target_evidence["statement"]
    assert target_evidence["parameters"] == {"target_factor": 1.0}
    assert "url" not in target_evidence
    transform = record["result"]["nodes"]["dataset:sales-metrics"]
    assert transform["log"]["metadata"]["structured"] is True
    execution_log = client.get(
        f"/api/runs/{run_id}/artifacts/{transform['log']['artifact_id']}",
        params={"session_id": SESSION_A},
    )
    assert execution_log.status_code == 200
    assert execution_log.headers["cache-control"] == "private, no-store"
    assert execution_log.json()["schema"] == "dataviz/execution-log/v1"
    assert any(
        item.get("event") == "runtime_completed"
        for item in execution_log.json()["records"]
    )
    assert client.get(
        f"/api/runs/{run_id}/artifacts/{transform['log']['artifact_id']}",
        params={"session_id": SESSION_B},
    ).status_code == 404
    canvas = client.get(
        f"/api/dashboards/sales/canvas?run_id={run_id}",
        params={"session_id": SESSION_A, "frame_id": "frame_contract"},
    )
    assert canvas.status_code == 200
    assert "CUSTOM CANVAS" in canvas.text
    assert '"source:orders/main": [' in canvas.text
    assert '"dashboard_id": "sales"' in canvas.text
    assert '"frame_id": "frame_contract"' in canvas.text
    assert "PORTABLE ANALYSIS" not in canvas.text
    report = client.post(
        "/api/dashboards/sales/report",
        json={
            "session_id": SESSION_A,
            "run_id": run_id,
            "control_state": {
                "dashboard:sales/region": {
                    "intent": "explicit",
                    "value": ["East"],
                    "revision": 1,
                },
                "section:pulse/min_revenue": {"value": 0, "revision": 0},
                "view:detail/min_orders": {"value": 0, "revision": 0},
            },
        },
    )
    assert report.status_code == 200
    assert "attachment" in report.headers["content-disposition"]
    assert '<option value="East" selected>' in report.text
    assert '<option value="West">' in report.text
    assert '"region": "West"' in report.text
    assert '"dashboard:sales/region": {"value": ["East"], "revision": 1, "intent": "explicit"}' in report.text


def test_initial_canvas_uses_a_quiet_waiting_state():
    client = TestClient(create_app(WORKSPACE))

    canvas = client.get(
        "/api/dashboards/sales/canvas",
        params={"session_id": SESSION_A},
    )

    assert canvas.status_code == 200
    assert "设置参数后，点击 Run。" in canvas.text
    assert "Canvas waiting" not in canvas.text
    assert "linear-gradient" not in canvas.text
    assert "box-shadow" not in canvas.text
    assert "background:#fff" in canvas.text


def test_dashboard_has_a_shareable_shell_route():
    client = TestClient(create_app(WORKSPACE))

    routed = client.get("/dashboards/sales?target_factor=2")
    missing = client.get("/dashboards/not-a-dashboard")

    assert routed.status_code == 200
    assert 'id="canvas-frame"' in routed.text
    assert routed.headers["cache-control"] == "no-store"
    assert missing.status_code == 404


def test_shared_result_is_persisted_outside_dashboards_and_survives_restart(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(
        ROOT / "tests" / "fixtures" / "browser-worker-workspace",
        root,
        ignore=shutil.ignore_patterns(".dataviz", "shared_caches"),
    )
    session_id = "shared_result_session"

    with TestClient(create_app(root, watch=False)) as client:
        started = client.post(
            "/api/dashboards/worker-runtime/runs",
            json={
                "session_id": session_id,
                "query_parameter_state": {},
                "refresh": True,
            },
        )
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
        record = None
        for _ in range(200):
            record = client.get(
                f"/api/runs/{run_id}", params={"session_id": session_id}
            ).json()
            if record["status"] in {"ready", "partial", "error"}:
                break
            time.sleep(0.03)
        assert record and record["status"] == "ready", record

        shared = client.post(
            "/api/dashboards/worker-runtime/share",
            json={
                "session_id": session_id,
                "run_id": run_id,
                "control_state": {
                    "dashboard:worker-runtime/delay_ms": {
                        "value": 5,
                        "revision": 0,
                    }
                },
                "applied_revisions": {
                    "views": {},
                    "transforms": {
                        "scaled": {"dashboard:worker-runtime/delay_ms": 0}
                    },
                },
                "applied_control_state": {
                    "views": {},
                    "transforms": {
                        "scaled": {
                            "dashboard:worker-runtime/delay_ms": {
                                "value": 5,
                                "revision": 0,
                            }
                        }
                    },
                },
                "snapshot_outputs": {},
            },
        )
        assert shared.status_code == 200, shared.text
        payload = shared.json()

    cache = root / payload["path"]
    assert cache.parent == root / "shared_caches"
    assert payload["share_id"].startswith("worker-runtime_")
    assert payload["share_id"].endswith(f"_{run_id}")
    assert not (root / "dashboards" / "shared_caches").exists()
    assert not (cache / "index.html").exists()
    assert (cache / "manifest.json").is_file()
    assert (cache / "query-result.json").is_file()
    assert (cache / "artifacts").is_dir()
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "dataviz/shared-cache/v1"
    assert manifest["dashboard_id"] == "worker-runtime"
    assert manifest["run_id"] == run_id
    assert manifest["consumer_revisions"]["transforms"]["scaled"] == {
        "trigger": "auto",
        "stale": False,
        "controls": {
            "dashboard:worker-runtime/delay_ms": {
                "effective_revision": 0,
                "applied_revision": 0,
                "stale": False,
            }
        },
        "applied_control_state": {
            "dashboard:worker-runtime/delay_ms": {
                "value": 5,
                "revision": 0,
            }
        },
        "applied_writer_provenance": {},
    }
    sealed = json.loads(
        (
            root
            / ".dataviz"
            / "results"
            / payload["result_id"]
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert sealed["result"]["consumer_revisions"] == manifest["consumer_revisions"]

    # A new application instance has no in-memory Run, but the persistent
    # Query snapshot is rehydrated into an interactive shared page.
    with TestClient(create_app(root, watch=False)) as restarted:
        page = restarted.get(payload["url"])
        assert page.status_code == 200
        assert "window.datavizRuntime" in page.text
        assert "browser-js" in page.text
        assert 'title="导出报告已固化查询结果"' not in page.text
        assert restarted.get(f'{payload["url"]}/manifest.json').status_code == 200
        assert restarted.get("/shared/not-a-real-share").status_code == 404


def test_shared_result_adds_server_python_interaction_but_html_export_rejects_it(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(
        ROOT / "tests" / "fixtures" / "browser-worker-workspace",
        root,
        ignore=shutil.ignore_patterns(".dataviz", "shared_caches"),
    )
    transform_path = (
        root
        / "dashboards"
        / "worker-runtime"
        / "transforms"
        / "scaled.yaml"
    )
    transform = yaml.safe_load(transform_path.read_text(encoding="utf-8"))
    transform["runtime"] = "server-python"
    transform["code"] = "scaled.py"
    transform["export"] = {"mode": "snapshot"}
    transform_path.write_text(
        yaml.safe_dump(transform, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    transform_path.with_name("scaled.py").write_text(
        """def transform(context):
    frame = context.table("rows").copy()
    frame["value"] = frame["value"] * context.control_inputs["delay_ms"]
    return {"main": frame}
""",
        encoding="utf-8",
    )
    dashboard_path = root / "dashboards" / "worker-runtime" / "dashboard.yaml"
    dashboard = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    dashboard["query_parameters"] = [
        {
            "id": "batch",
            "type": "single_input",
            "value_type": "integer",
            "label": "Batch",
            "default": 3,
        }
    ]
    dashboard_path.write_text(
        yaml.safe_dump(dashboard, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    session_id = "shared_server_python"
    report_request = None
    with TestClient(create_app(root, watch=False)) as client:
        started = client.post(
            "/api/dashboards/worker-runtime/runs",
            json={
                "session_id": session_id,
                "query_parameter_state": _query_state(batch=3),
                "refresh": True,
            },
        )
        run_id = started.json()["run_id"]
        record = None
        for _ in range(200):
            record = client.get(
                f"/api/runs/{run_id}", params={"session_id": session_id}
            ).json()
            if record["status"] in {"ready", "partial", "error"}:
                break
            time.sleep(0.03)
        assert record and record["status"] == "ready", record
        report_request = {
            "session_id": session_id,
            "run_id": run_id,
            "control_state": {
                "dashboard:worker-runtime/delay_ms": {
                    "value": 5,
                    "revision": 0,
                }
            },
            "snapshot_outputs": {},
        }
        noncanonical_report = client.post(
            "/api/dashboards/worker-runtime/report",
            json={
                **report_request,
                "control_state": {
                    "dashboard:worker-runtime/delay_ms": {"value": 5}
                },
            },
        )
        assert noncanonical_report.status_code == 422
        assert (
            noncanonical_report.json()["detail"]["details"]["code"]
            == "control_state_not_canonical"
        )
        exported = client.post(
            "/api/dashboards/worker-runtime/report", json=report_request
        )
        assert exported.status_code == 409
        assert (
            exported.json()["detail"]["code"]
            == "html_export_server_runtime_unavailable"
        )
        shared = client.post(
            "/api/dashboards/worker-runtime/share", json=report_request
        )
        assert shared.status_code == 200, shared.text
        shared_payload = shared.json()

    with TestClient(create_app(root, watch=False)) as restarted:
        page = restarted.get(shared_payload["url"])
        assert page.status_code == 200
        assert "server-python" in page.text
        assert 'title="导出报告已固化查询结果"' in page.text
        assert '<output>3</output>' in page.text
        run_match = re.search(r'"run_id": "(run_shared_[^"]+)"', page.text)
        session_match = re.search(r'"session_id": "(shared_[^"]+)"', page.text)
        assert run_match and session_match
        restored_run_id = run_match.group(1)
        shared_session = session_match.group(1)
        noncanonical = restarted.post(
            f"/api/runs/{restored_run_id}/interactions",
            json={
                "session_id": shared_session,
                "transform_id": "scaled",
                "generation": 1,
                "control_state": {
                    "dashboard:worker-runtime/delay_ms": {"value": 6}
                },
            },
        )
        assert noncanonical.status_code == 422
        assert (
            noncanonical.json()["detail"]["details"]["code"]
            == "control_state_not_canonical"
        )
        started = restarted.post(
            f"/api/runs/{restored_run_id}/interactions",
            json={
                "session_id": shared_session,
                "transform_id": "scaled",
                "generation": 1,
                "control_state": {
                    "dashboard:worker-runtime/delay_ms": {
                        "value": 6,
                        "revision": 1,
                    }
                },
            },
        )
        assert started.status_code == 200, started.text
        interaction_id = started.json()["interaction_id"]
        interaction = None
        for _ in range(200):
            interaction = restarted.get(
                f"/api/interactions/{interaction_id}",
                params={"session_id": shared_session},
            ).json()
            if interaction["status"] in {"ready", "partial", "error", "cancelled"}:
                break
            time.sleep(0.03)
        assert interaction and interaction["status"] == "ready", interaction
        output = restarted.get(
            f"/api/interactions/{interaction_id}/outputs/interactive:scaled/main",
            params={"session_id": shared_session},
        )
        assert output.status_code == 200, output.text
        assert [row["value"] for row in output.json()["value"]] == [6, 12]


def test_server_shell_owns_dashboard_and_query_parameter_url_state():
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()

    assert "function dashboardIdFromLocation" in script
    assert "function queryParameterStateFromLocation" in script
    assert "function dashboardLocation" in script
    assert "window.history[method]" in script
    assert "window.addEventListener('popstate'" in script
    assert "const button = document.createElement('a')" in script


def test_server_shell_exposes_source_evidence_inspector():
    client = TestClient(create_app(MINIMAL_WORKSPACE))

    shell = client.get("/")

    assert shell.status_code == 200
    assert 'id="node-inspector"' in shell.text
    assert 'id="node-inspector-body"' in shell.text
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "function showNodeInspector(node)" in script.text
    assert "Resolved SQL" in script.text
    assert "Driver statement & bound parameters" in script.text
    assert "Structured node log" in script.text
    assert "async function appendNodeLog" in script.text


def test_server_streams_large_tables_as_gzipped_arrow_without_json_materialization():
    client = TestClient(create_app(REPEAT_WORKSPACE))
    started = client.post(
        "/api/dashboards/store-performance/runs",
        json={"session_id": SESSION_A, "query_parameter_state": {}, "refresh": True},
    ).json()
    run_id = started["run_id"]
    for _ in range(120):
        record = client.get(
            f"/api/runs/{run_id}", params={"session_id": SESSION_A}
        ).json()
        if record["status"] in {"ready", "partial", "error"}:
            break
        time.sleep(0.05)
    assert record["status"] == "ready"

    metadata = client.get(
        f"/api/runs/{run_id}/outputs/source:store-sales/main",
        params={"session_id": SESSION_A},
    )
    assert metadata.status_code == 200
    transport = metadata.json()["transport"]
    assert transport["encoding"] == "arrow-ipc"
    assert transport["row_count"] == 1200
    assert "value" not in metadata.json()

    arrow = client.get(transport["url"])
    assert arrow.status_code == 200
    assert arrow.headers["content-type"].startswith("application/vnd.apache.arrow.stream")
    assert arrow.headers["content-encoding"] == "gzip"
    table = pa.ipc.open_stream(arrow.content).read_all()
    assert table.num_rows == 1200

    canvas = client.get(
        f"/api/dashboards/store-performance/canvas?run_id={run_id}",
        params={"session_id": SESSION_A},
    )
    assert '"output_transports": {"source:store-sales/main": {' in canvas.text
    assert '"store_id": "S001"' not in canvas.text


def test_server_rescans_physical_dashboard_names_without_aliases(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    client = TestClient(create_app(root))

    original = root / "dashboards" / "sales"
    renamed = root / "dashboards" / "团队分析##销售看板"
    original.rename(renamed)

    # The app was created before the external rename. Canvas resolution and
    # navigation must still recover from the filesystem without a restart.
    canvas = client.get(
        "/api/dashboards/sales/canvas",
        params={"session_id": SESSION_A},
    )
    assert canvas.status_code == 200
    assert "销售脉搏" in canvas.text

    summary = client.get("/api/workspace").json()
    dashboard = next(item for item in summary["dashboards"] if item["id"] == "sales")
    assert dashboard["canvas_name"] == "销售看板"
    assert dashboard["logical_path"] == "团队分析/销售看板"
    assert dashboard["path"].endswith("团队分析##销售看板")


def test_server_app_controls_are_browser_only():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()
    query_block = script[script.index("async function runDashboard"):script.index("function listen")]
    assert "session_id: state.sessionId" in query_block
    assert "selections()" not in query_block
    assert "dataviz:control-action" in script
    assert "dataviz:control-apply" in script
    assert "dataviz:control-hello" in script
    assert "dataviz:restore-checkpoint" in script
    assert "dataviz:control-snapshot" in script
    assert "dataviz:set-controls" not in script
    assert "dashboardStates: new Map()" in script
    assert "BroadcastChannel" in script
    assert "dataviz:canvas-interaction" in script
    assert "window.addEventListener('message'" in script
    assert "event.source === frame.contentWindow" in script
    assert "sameCanvasIdentity(event.data, identity)" in script
    assert "frame_id=" in script
    assert "closeHeaderPopovers();" in script
    assert "overlay.closeAll({group: 'data-entry'});" in script
    assert "controlCheckpoint: null" in script
    assert "base_control_version:runtime.controlVersion" in script
    assert "controlStateFromValue" not in script
    assert "Number(local[key].revision || 0)" not in script
    assert "state.canvasSelections" not in script
    assert "/static/app.js?v=" in template
    select_block = script[script.index("function selectDashboard"):script.index("function queryParameterStates")]
    assert "eventSource.close()" not in select_block


def test_query_parameters_are_an_inline_query_card_toggled_by_the_header_run_control():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()

    assert 'id="query-run-control"' in template
    assert 'id="query-parameters-toggle"' in template
    assert 'aria-controls="query-parameters-panel"' in template
    assert 'id="query-parameters-panel"' in template
    assert 'id="query-parameter-count"' not in template
    assert 'id="query-state"' not in template
    assert "Loaded dataset ·" not in script
    assert 'class="workbench-header"' not in template
    assert template.index('class="topbar dv-shell-header"') < template.index('id="query-parameters-control"')
    assert template.index('class="topbar dv-shell-header"') < template.index('id="dashboard-sidebar"')
    assert template.index('id="dashboard-sidebar"') < template.index('class="workbench"')
    assert template.index('class="workbench"') < template.index('id="query-parameters-control"')
    query_owner = template[
        template.index('id="query-parameters-control"'):
        template.index('id="workspace-update"')
    ]
    query_owner_tag = query_owner[:query_owner.index(">")]
    assert "data-header-popover" not in query_owner_tag
    assert "data-overlay-floating" not in query_owner_tag
    assert "data-control-panel-body" in query_owner
    assert 'class="dv-query-card"' in query_owner
    assert '<h2>查询参数</h2>' in query_owner
    assert 'id="dashboard-controls-control"' not in query_owner
    assert 'id="query-run-control"' not in query_owner
    assert 'id="run-button"' not in query_owner
    assert "queryParametersOpen" in script
    assert "toggleQueryParameters" in script
    assert "setQueryParametersOpen(true, {persist: true})" in script
    assert "Escape" not in script[
        script.index("function setQueryParametersOpen"):
        script.index("function dashboardControl(")
    ]


def test_control_trays_show_business_fields_without_runtime_taxonomy():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()
    canvas_renderer = (ROOT / "src" / "dataviz" / "rendering" / "canvas.py").read_text()
    package_style = (
        ROOT / "src" / "dataviz" / "components" / "packages"
        / "presentation.shell" / "style.css"
    ).read_text()

    assert '<header><span>DATA</span>' not in template
    assert '<header><span>DATA</span>' not in canvas_renderer
    assert '<header><span>LOGIC</span>' not in canvas_renderer
    assert "<span hidden data-control-impact-count>" in script
    assert "grid-template-rows: minmax(0, 1fr) auto" in package_style
    assert "background: transparent;\n  border: 0;" in package_style


def test_server_and_portable_html_share_one_shell_visual_contract():
    package_style = (
        ROOT
        / "src"
        / "dataviz"
        / "components"
        / "packages"
        / "presentation.shell"
        / "style.css"
    ).read_text()

    assert '--dv-shell-header-height: 58px' in package_style
    assert ':where(.topbar, .dv-runtime-header)' in package_style
    assert ':where(.topbar-actions, .dv-runtime-actions)' in package_style
    assert ':where(.header-control__popover, .dv-runtime-popover)' in package_style
    assert (
        '.dv-runtime-query-tray > .dv-runtime-query-panel,\n'
        '.query-parameters-control .query-parameters-panel'
    ) in package_style
    assert ':where(.field, .dv-report-selection, .dv-compute-control)' in package_style
    assert '.dv-query-card-host' in package_style
    assert 'padding: 24px clamp(22px, 3vw, 48px) 0;' in package_style
    query_card_block = package_style[
        package_style.index('.dv-query-card {'):
        package_style.index('.dv-query-card__header {')
    ]
    assert 'max-width' not in query_card_block


def test_header_uses_node_signal_lights_and_ends_with_share_controls_then_run():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()
    style = (ROOT / "src" / "dataviz" / "server" / "static" / "server.css").read_text()
    canvas_renderer = (ROOT / "src" / "dataviz" / "rendering" / "canvas.py").read_text()

    brand_end = template.index(
        "</button>", template.index('class="brand dv-runtime-brand dv-shell-brand"')
    )
    signals = template.index('id="query-diagnostics"')
    actions = template.index('class="topbar-actions dv-shell-header-actions"')
    share = template.index('id="share-control"')
    controls = template.index('id="dashboard-controls-control"')
    run = template.index('id="query-run-control"')
    query_card = template.index('id="query-parameters-control"')
    assert brand_end < signals < actions < share < controls < run < query_card
    assert '<strong>SHARE</strong>' in template
    assert 'id="copy-share-link" type="button">分享链接</button>' in template
    assert 'id="download-button" type="button" disabled>导出 HTML</button>' in template
    assert "shared_caches" not in template
    assert '<strong data-run-label>查询</strong>' in template
    assert 'class="button-light"' not in template
    assert ".query-parameters-control{" in style
    assert ".topbar-actions>.button{width:84px;height:40px;padding:0 14px}" in style
    assert "min-width:84px;\n  min-height:40px;" in style
    assert ".query-run-control__copy{display:grid;gap:1px;min-width:0;text-align:center}" in style
    assert 'class="pipeline-signal-list"' in template
    assert 'id="query-diagnostics-label" aria-live="polite" hidden' in template
    assert 'id="run-message" hidden' in template
    assert "className = 'node pipeline-signal'" in script
    assert "item.blur();\n    showNodeInspector(node);" in script
    assert "node.type === 'source' || node.type === 'dataset_transform'" in script
    assert "dataviz:view-pipeline-inspect" in script
    assert 'class="pipeline-signal__tooltip"' in script
    assert "data-node-status-label" not in script
    assert ".pipeline-signal-list{display:flex;align-items:center;gap:8px" in style
    assert ".pipeline-signal:hover{background:transparent}" in style
    assert ".pipeline-signal:focus-visible .pipeline-signal__tooltip" not in style
    assert 'class="header-control__chevron dv-shell-control__chevron"' in template
    assert (
        'class="header-control__mark dv-shell-control__mark" '
        'aria-hidden="true">C</span>' in template
    )
    assert (
        '<strong class="header-control__label dv-shell-control__label">'
        'DASHBOARD CONTROLS</strong>' in template
    )
    assert '<small id="dashboard-control-meta" hidden>' in template
    assert 'class="dv-control-chevron dv-shell-control__chevron"' in canvas_renderer
    assert '<strong class="dv-shell-control__label">DASHBOARD CONTROLS</strong>' in canvas_renderer
    assert '#dashboard-controls-control>.header-control__trigger{' not in style
    assert 'Dashboard Control visuals are owned by presentation.shell' in style
    assert '.button--run{color:#fff;background:#25282d;border-color:#25282d' in style
    assert 'background:#303a78' not in style[style.index('.query-run-control__toggle{'):style.index('.query-run-control__chevron{')]
    assert "<i>⌄</i>" not in canvas_renderer
    assert "PARAMETERS" not in canvas_renderer


def test_keyboard_shortcuts_are_cross_platform_guarded_and_cross_frame():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()
    runtime = (
        ROOT / "src" / "dataviz" / "server" / "static" / "canvas-runtime.js"
    ).read_text()
    renderer = (ROOT / "src" / "dataviz" / "rendering" / "canvas.py").read_text()

    assert 'aria-keyshortcuts="B"' in template
    assert 'aria-keyshortcuts="Q"' in template
    assert 'aria-keyshortcuts="Control+Enter Meta+Enter"' in template
    assert 'id="keyboard-shortcuts-dialog"' in template
    assert 'id="shortcut-toast"' in template
    assert "event.repeat || event.isComposing || event.keyCode === 229" in script
    assert "(event.ctrlKey || event.metaKey) && !event.altKey && event.key === 'Enter'" in script
    assert "event.key.toLowerCase() === 'q'" in script
    assert "event.key.toLowerCase() === 'b'" in script
    assert "event.key.toLowerCase() === 'r'" not in script
    assert "keyboardTargetIsEditable(event.target)" in script
    assert "showShortcutToast('当前看板没有查询参数')" in script
    assert "dataviz:keyboard-shortcut" in script
    assert "dataviz:keyboard-shortcut" in runtime
    assert "window.parent !== window" in runtime
    assert 'data-runtime-shortcut-help' in renderer
    assert 'data-runtime-shortcut-toast' in renderer
    assert 'aria-keyshortcuts="Q"' in renderer
    assert "showDatavizRuntimeShortcutToast('当前报告没有查询参数')" in runtime


def test_server_sidebar_is_resizable_collapsible_and_tab_local():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()
    style = (ROOT / "src" / "dataviz" / "server" / "static" / "server.css").read_text()

    assert 'id="sidebar-toggle"' in template
    assert '<button id="sidebar-toggle" class="brand dv-runtime-brand dv-shell-brand"' in template
    assert '<h1 id="workspace-title">Dashboards</h1>' not in template
    assert 'class="sidebar-toggle"' not in template
    assert 'id="add-root-folder"' not in template
    assert "$('#add-root-folder')" not in script
    assert 'id="sidebar-resizer"' in template
    assert 'role="separator"' in template
    assert "width: state.sidebarWidth" in script
    assert "customized: state.sidebarWidthCustomized" in script
    assert "sidebarWidth: 250" in script
    assert "state.sidebarWidth = 250" in script
    assert "bindOverflowTitle" in script
    assert "label.scrollWidth > label.clientWidth + 1" in script
    assert "bindOverflowTitle(label, label, item.title)" in script
    assert "setPointerCapture" in script
    assert "['ArrowLeft', 'ArrowRight', 'Home', 'End']" in script
    assert "body.sidebar-collapsed" in style
    assert "transform:rotate(-3deg)" not in style
    assert "button.brand:active .brand-mark" not in style
    assert "body.sidebar-collapsed #sidebar-toggle span{transform:rotate(180deg)}" not in style
    assert "body.sidebar-collapsed .brand-mark{transform:rotate(360deg)}" in style
    assert "@media(prefers-reduced-motion:reduce){.brand-mark{transition:none}}" in style
    assert "--sidebar-width" in style
    assert "--sidebar-width:250px" in style
    assert "text-overflow:ellipsis;white-space:nowrap" in style
    assert ".nav-button:visited,.nav-button:hover,.nav-button:focus,.nav-button:active{text-decoration:none}" in style
    assert ".rail{padding:0 14px 18px;color:var(--ink);background:#fff" in style
    assert "border-right:1px solid #eceeea;box-shadow:none" in style
    assert "--shell-header-height:58px" in style
    assert "grid-template-rows:var(--shell-header-height) minmax(0,1fr)" in style
    assert "grid-column:1 / -1" in style
    assert "top:var(--shell-header-height)" in style
    assert "height:calc(100vh - var(--shell-header-height))" in style
    assert "button.brand" in style
    assert ".workspace-meta" not in style
    assert ".topbar{min-height:var(--shell-header-height)" in style
    assert ".nav-button.active{color:#28305e;background:#f0f1f8" in style
    assert "Quiet white shell" in style


def test_empty_trash_is_inert_and_keeps_sidebar_geometry_stable():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()
    style = (ROOT / "src" / "dataviz" / "server" / "static" / "server.css").read_text()

    assert 'class="nav-trash__chevron"' in template
    assert "<i>›</i>" not in template
    assert "暂无项目" not in script
    assert "trash.dataset.empty = records.length === 0 ? 'true' : 'false';" in script
    assert "if (!records.length) trash.open = false;" in script
    assert "event.preventDefault();" in script[
        script.index("$('#nav-trash > summary').addEventListener"):
        script.index("$('#nav-root-drop').addEventListener")
    ]
    assert '.nav-trash[data-empty="true"] .nav-trash__list{display:none}' in style
    assert ".nav-trash__chevron{display:grid;flex:0 0 16px" in style


def test_server_diagnoses_removed_navigation_field_and_exposes_physical_dashboards(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    shutil.copytree(root / "dashboards" / "sales", root / "dashboards" / "local-copy")
    copied_path = root / "dashboards" / "local-copy" / "dashboard.yaml"
    copied = yaml.safe_load(copied_path.read_text(encoding="utf-8"))
    copied["id"] = "local-copy"
    copied["title"] = "Local copy"
    copied_path.write_text(yaml.safe_dump(copied, allow_unicode=True, sort_keys=False), encoding="utf-8")

    workspace_path = root / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition.setdefault("navigation", []).append(
        {"id": "gone", "title": "Gone", "dashboard": "dashboards/gone", "order": 20}
    )
    workspace_path.write_text(yaml.safe_dump(definition, allow_unicode=True, sort_keys=False), encoding="utf-8")

    client = TestClient(create_app(root))
    response = client.get("/api/workspace")
    assert response.status_code == 200
    payload = response.json()
    dashboards = {item["id"]: item for item in payload["dashboards"]}
    assert "gone" not in dashboards
    assert dashboards["local-copy"]["discovered"] is True
    assert dashboards["local-copy"]["canvas_name"] == "local-copy"
    assert dashboards["local-copy"]["title"] == "Local copy"
    assert dashboards["local-copy"]["logical_path"] == "local-copy"
    assert any(
        item["code"] == "workspace_definition_invalid"
        for item in payload["diagnostics"]
    )


def test_server_recovers_from_invalid_workspace_yaml(tmp_path: Path):
    root = tmp_path / "recoverable-workspace"
    shutil.copytree(WORKSPACE, root)
    (root / "workspace.yaml").write_text("navigation: [broken", encoding="utf-8")

    client = TestClient(create_app(root))
    response = client.get("/api/workspace")
    assert response.status_code == 200
    summary = response.json()
    assert summary["workspace"]["title"] == "recoverable-workspace"
    assert summary["dashboards"][0]["title"] == "销售脉搏"
    assert summary["dashboards"][0]["runnable"] is True
    assert any(item["code"] == "workspace_definition_invalid" for item in summary["diagnostics"])


def test_navigation_does_not_overwrite_invalid_workspace_yaml(tmp_path: Path):
    root = tmp_path / "recoverable-workspace"
    shutil.copytree(WORKSPACE, root)
    workspace_path = root / "workspace.yaml"
    broken = "navigation: [broken"
    workspace_path.write_text(broken, encoding="utf-8")
    client = TestClient(create_app(root))

    response = client.post("/api/navigation/folders", json={"title": "经营分析"})

    assert response.status_code == 409
    assert workspace_path.read_text(encoding="utf-8") == broken


def test_folder_move_rolls_back_dashboard_names_when_metadata_write_fails(
    tmp_path: Path,
    monkeypatch,
):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    editor = NavigationEditor(root)
    folder_identifier = editor.create_folder("旧目录")
    entry = load_workspace(root).catalog_entry("sales")
    editor.place_dashboard(entry, folder_identifier)
    old_path = root / "dashboards" / "旧目录##sales"
    new_path = root / "dashboards" / "新目录##sales"

    def fail_write(*_args, **_kwargs):
        raise OSError("simulated workspace metadata failure")

    monkeypatch.setattr(editor, "_write", fail_write)
    with pytest.raises(OSError, match="simulated workspace metadata failure"):
        editor.rename_folder(folder_identifier, "新目录")

    assert old_path.is_dir()
    assert not new_path.exists()


def test_navigation_folders_can_be_created_nested_and_removed_safely(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    client = TestClient(create_app(root))

    created = client.post("/api/navigation/folders", json={"title": "经营分析"})
    assert created.status_code == 200
    parent_id = created.json()["result"]["folder_id"]
    child = client.post(
        "/api/navigation/folders", json={"title": "周报", "parent_id": parent_id}
    )
    assert child.status_code == 200
    child_id = child.json()["result"]["folder_id"]

    cycle = client.patch(
        f"/api/navigation/folders/{parent_id}/placement", json={"parent_id": child_id}
    )
    assert cycle.status_code == 409
    moved_to_root = client.patch(
        f"/api/navigation/folders/{child_id}/placement", json={"parent_id": None}
    )
    assert moved_to_root.status_code == 200
    child_id = moved_to_root.json()["result"]["folder_id"]
    moved_back = client.patch(
        f"/api/navigation/folders/{child_id}/placement", json={"parent_id": parent_id}
    )
    assert moved_back.status_code == 200
    child_id = moved_back.json()["result"]["folder_id"]

    moved = client.patch("/api/navigation/dashboards/sales", json={"parent_id": child_id})
    assert moved.status_code == 200
    summary = client.get("/api/workspace").json()
    dashboard = next(item for item in summary["dashboards"] if item["id"] == "sales")
    assert dashboard["parent_id"] == child_id
    assert dashboard["path"] == "dashboards/经营分析##周报##sales"
    assert (root / "dashboards" / "经营分析##周报##sales" / "dashboard.yaml").exists()
    assert {parent_id, child_id} <= {item["id"] for item in summary["folders"]}

    renamed = client.patch(
        f"/api/navigation/folders/{child_id}", json={"title": "月度复盘"}
    )
    assert renamed.status_code == 200
    child_id = renamed.json()["result"]["folder_id"]
    folders = client.get("/api/workspace").json()["folders"]
    assert next(item for item in folders if item["id"] == child_id)["title"] == "月度复盘"
    active_path = root / "dashboards" / "经营分析##月度复盘##sales"
    assert (active_path / "dashboard.yaml").exists()

    removed = client.delete(f"/api/navigation/folders/{child_id}")
    assert removed.status_code == 200
    trash_id = removed.json()["result"]["trash_id"]
    summary = client.get("/api/workspace").json()
    assert not [item for item in summary["dashboards"] if item["id"] == "sales"]
    assert next(item for item in summary["trash"] if item["trash_id"] == trash_id)["item"]["id"] == child_id
    trashed_path = root / "dashboards" / "__TRASH__##经营分析##月度复盘##sales"
    assert (trashed_path / "dashboard.yaml").exists()

    restored = client.post(f"/api/navigation/trash/{trash_id}/restore")
    assert restored.status_code == 200
    summary = client.get("/api/workspace").json()
    dashboard = next(item for item in summary["dashboards"] if item["id"] == "sales")
    assert dashboard["parent_id"] == child_id
    assert not summary["trash"]
    assert (active_path / "dashboard.yaml").exists()

    dashboard_trashed = client.delete("/api/navigation/dashboards/sales")
    assert dashboard_trashed.status_code == 200
    dashboard_trash_id = dashboard_trashed.json()["result"]["trash_id"]
    assert not [
        item
        for item in client.get("/api/workspace").json()["dashboards"]
        if item["id"] == "sales"
    ]
    assert client.post(f"/api/navigation/trash/{dashboard_trash_id}/restore").status_code == 200
    dashboard = next(
        item
        for item in client.get("/api/workspace").json()["dashboards"]
        if item["id"] == "sales"
    )
    assert dashboard["parent_id"] == child_id

    saved = yaml.safe_load((root / "workspace.yaml").read_text(encoding="utf-8"))
    assert "trash" not in saved
    assert "navigation" not in saved
    assert {item["path"] for item in saved["folders"]} == {"经营分析", "经营分析/月度复盘"}


def test_empty_folders_are_deleted_and_trashed_dashboards_can_be_purged(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    client = TestClient(create_app(root))

    empty = client.post("/api/navigation/folders", json={"title": "临时空目录"})
    empty_id = empty.json()["result"]["folder_id"]
    deleted = client.delete(f"/api/navigation/folders/{empty_id}")

    assert deleted.status_code == 200
    assert deleted.json()["result"] == {
        "trash_id": None,
        "deleted": True,
        "path": "临时空目录",
    }
    assert not client.get("/api/workspace").json()["trash"]
    saved = yaml.safe_load((root / "workspace.yaml").read_text(encoding="utf-8"))
    assert "临时空目录" not in {item["path"] for item in saved["folders"]}

    folder = client.post("/api/navigation/folders", json={"title": "shein"})
    folder_id = folder.json()["result"]["folder_id"]
    assert client.patch(
        "/api/navigation/dashboards/sales", json={"parent_id": folder_id}
    ).status_code == 200
    trashed = client.delete("/api/navigation/dashboards/sales")
    trash_id = trashed.json()["result"]["trash_id"]
    trashed_path = root / "dashboards" / "__TRASH__##shein##sales"

    trash = client.get("/api/workspace").json()["trash"]
    assert len(trash) == 1
    assert trash[0]["trash_id"] == trash_id
    assert trash[0]["item"]["title"] == "shein##sales"
    assert trashed_path.is_dir()

    purged = client.delete(f"/api/navigation/trash/{trash_id}")
    assert purged.status_code == 200
    assert purged.json()["result"] == {"kind": "dashboard", "path": "shein##sales"}
    assert not trashed_path.exists()
    assert not client.get("/api/workspace").json()["trash"]
    assert client.post(f"/api/navigation/trash/{trash_id}/restore").status_code == 409


def test_run_ready_is_emitted_after_result_is_available():
    manager = RunManager(load_workspace(WORKSPACE))
    record = manager.start(
        "sales",
        _query_state(target_factor=1.0),
        session_id=SESSION_A,
    )
    for _ in range(100):
        if record.status in {"ready", "partial", "error"}:
            break
        time.sleep(0.05)
    assert record.result is not None
    names = [event.event for event in record.events]
    assert "run_started" in names
    assert names[-1] == "run_ready"


def test_fast_dag_branch_publishes_output_before_slow_branch_finishes(
    tmp_path: Path, monkeypatch
):
    root = tmp_path / "progressive"
    dashboard_root = root / "dashboards" / "progressive"
    (dashboard_root / "data").mkdir(parents=True)
    (dashboard_root / "transforms").mkdir()
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v2\nkind: workspace\nid: progressive\ntitle: Progressive\n",
        encoding="utf-8",
    )
    (dashboard_root / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v17
kind: dashboard
id: progressive
title: Progressive branches
sources:
  - {id: fast, kind: source, type: file, path: data/fast.csv, format: csv, outputs: {main: {kind: table}}}
  - {id: slow-left, kind: source, type: file, path: data/slow-left.csv, format: csv, outputs: {main: {kind: table}}}
  - {id: slow-right, kind: source, type: file, path: data/slow-right.csv, format: csv, outputs: {main: {kind: table}}}
  - {id: unused, kind: source, type: file, path: data/unused.csv, format: csv, outputs: {main: {kind: table}}}
dataset_transforms: [transforms/combine.yaml]
interactive_transforms: [transforms/fast-summary.yaml]
views:
  - {id: fast-view, title: Fast, template: table, input: source:fast/main}
  - {id: slow-view, title: Slow, template: table, input: dataset:combine/main}
  - {id: fast-summary, title: Fast summary, template: metric, input: interactive:fast-summary/total}
sections:
  - {id: results, title: Results, template: stack, views: [fast-view, fast-summary, slow-view]}
""",
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "combine.yaml").write_text(
        """schema: dataviz/dataset-transform/v3
kind: dataset_transform
id: combine
runtime: server-python
code: combine.py
entrypoint: transform
inputs:
  left: source:slow-left/main
  right: source:slow-right/main
outputs:
  main: {kind: table}
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "combine.py").write_text(
        """import pandas as pd

def transform(context):
    return {"main": pd.concat([context.table("left"), context.table("right")])}
""",
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "fast-summary.yaml").write_text(
        """schema: dataviz/interactive-transform/v4
kind: interactive_transform
id: fast-summary
runtime: server-python
code: fast_summary.py
inputs: {rows: source:fast/main}
trigger: auto
export: {mode: snapshot}
outputs: {total: {kind: scalar}}
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "fast_summary.py").write_text(
        """def transform(context):
    return {"total": int(len(context.table("rows")))}
""",
        encoding="utf-8",
    )
    for name in ("fast", "slow-left", "slow-right", "unused"):
        (dashboard_root / "data" / f"{name}.csv").write_text(
            f"branch,value\n{name},1\n", encoding="utf-8"
        )

    class DelayedFileRunner:
        def execute(self, request):
            if request.definition.id in {"slow-left", "slow-right"}:
                time.sleep(1.5)
            elif request.definition.id == "fast":
                time.sleep(0.02)
            else:
                raise AssertionError("Unused source must not execute")
            return pd.DataFrame([{"branch": request.definition.id, "value": 1}])

    monkeypatch.setitem(SOURCE_RUNNERS, "file", DelayedFileRunner())
    client = TestClient(create_app(root))
    started = client.post(
        "/api/dashboards/progressive/runs",
        json={"session_id": SESSION_A, "query_parameter_state": {}},
    )
    assert started.status_code == 200
    run_id = started.json()["run_id"]

    canvas = client.get(
        "/api/dashboards/progressive/canvas",
        params={"session_id": SESSION_A, "run_id": run_id},
    )
    assert canvas.status_code == 200
    assert '"live": {' in canvas.text
    assert "window.dataviz.connectLive?.()" in canvas.text

    fast_snapshot = None
    for _ in range(60):
        record = client.get(
            f"/api/runs/{run_id}", params={"session_id": SESSION_A}
        ).json()
        snapshot = record["snapshot"]
        if snapshot and "source:fast/main" in snapshot["outputs"]:
            fast_snapshot = snapshot
            assert record["status"] == "loading"
            assert record["server_interactive_inputs"] == ["source:fast/main"]
            break
        time.sleep(0.01)
    assert fast_snapshot is not None
    assert "source:slow-left/main" not in fast_snapshot["outputs"]
    assert "source:slow-right/main" not in fast_snapshot["outputs"]
    assert "dataset:combine/main" not in fast_snapshot["outputs"]
    assert set(fast_snapshot["nodes"]) == {
        "source:fast",
        "source:slow-left",
        "source:slow-right",
        "dataset:combine",
    }

    interaction = client.post(
        f"/api/runs/{run_id}/interactions",
        json={
            "session_id": SESSION_A,
            "transform_id": "fast-summary",
            "generation": 1,
            "control_state": {},
        },
    )
    assert interaction.status_code == 200, interaction.text
    interaction_id = interaction.json()["interaction_id"]
    interaction_record = None
    for _ in range(200):
        interaction_record = client.get(
            f"/api/interactions/{interaction_id}",
            params={"session_id": SESSION_A},
        ).json()
        if interaction_record["status"] in {"ready", "error", "cancelled"}:
            break
        time.sleep(0.01)
    assert interaction_record and interaction_record["status"] == "ready"
    assert interaction_record["result"]["outputs"][
        "interactive:fast-summary/total"
    ]["kind"] == "scalar"
    during_interaction = client.get(
        f"/api/runs/{run_id}", params={"session_id": SESSION_A}
    ).json()
    assert during_interaction["status"] == "loading"
    assert during_interaction["result"] is None

    output = client.get(
        f"/api/runs/{run_id}/outputs/source:fast/main",
        params={"session_id": SESSION_A},
    )
    assert output.status_code == 200
    assert output.json()["value"] == [{"branch": "fast", "value": 1}]

    for _ in range(300):
        record = client.get(
            f"/api/runs/{run_id}", params={"session_id": SESSION_A}
        ).json()
        if record["result"]:
            break
        time.sleep(0.02)
    assert record["result"]["status"] == "ready"
    event_names = [event["event"] for event in record["events"]]
    fast_ready = next(
        index
        for index, event in enumerate(record["events"])
        if event["event"] == "output_ready"
        and event["data"].get("reference") == "source:fast/main"
    )
    combined_ready = next(
        index
        for index, event in enumerate(record["events"])
        if event["event"] == "output_ready"
        and event["data"].get("reference") == "dataset:combine/main"
    )
    assert fast_ready < combined_ready < event_names.index("run_ready")


def test_runs_and_session_cache_are_isolated_per_browser_tab():
    manager = RunManager(load_workspace(WORKSPACE))
    first = manager.start(
        "sales", _query_state(target_factor=1.0), session_id=SESSION_A
    )
    second = manager.start(
        "sales", _query_state(target_factor=1.25), session_id=SESSION_B
    )
    for _ in range(100):
        if first.result and second.result:
            break
        time.sleep(0.05)

    assert first.result and second.result
    assert first.result.query_parameter_state["target_factor"] == {"value": 1.0}
    assert second.result.query_parameter_state["target_factor"] == {"value": 1.25}
    assert manager.latest_for(SESSION_A, "sales") is first
    assert manager.latest_for(SESSION_B, "sales") is second
    assert manager.get(first.run_id, SESSION_B) is None
    assert manager.executors[SESSION_A] is not manager.executors[SESSION_B]
    assert manager.executors[SESSION_A].cache.memory is not manager.executors[SESSION_B].cache.memory
    persistent_policy = manager.workspace.dashboard("sales").sources["orders"][1].cache
    assert persistent_policy.mode == "persistent"
    assert persistent_policy.scope == "tab"
    assert (
        manager.executors[SESSION_A].cache.policy_root(persistent_policy)
        != manager.executors[SESSION_B].cache.policy_root(persistent_policy)
    )


def test_run_api_rejects_cross_tab_and_cross_dashboard_access():
    client = TestClient(create_app(WORKSPACE))
    started = client.post(
        "/api/dashboards/sales/runs",
        json={"session_id": SESSION_A, "query_parameter_state": _query_state(target_factor=1.0)},
    )
    assert started.status_code == 200
    run_id = started.json()["run_id"]

    assert client.get(
        f"/api/runs/{run_id}", params={"session_id": SESSION_B}
    ).status_code == 404
    assert client.get(
        "/api/dashboards/sales/canvas",
        params={"session_id": SESSION_B, "run_id": run_id},
    ).status_code == 404
    own_runs = client.get(
        "/api/session/runs", params={"session_id": SESSION_A}
    ).json()["runs"]
    other_runs = client.get(
        "/api/session/runs", params={"session_id": SESSION_B}
    ).json()["runs"]
    assert [item["run_id"] for item in own_runs] == [run_id]
    assert other_runs == []


def test_workspace_cache_scope_is_explicit_opt_in(tmp_path: Path):
    first = NodeCache(tmp_path, namespace=SESSION_A)
    second = NodeCache(tmp_path, namespace=SESSION_B)
    tab_policy = CacheDefinition(mode="persistent")
    shared_policy = CacheDefinition(mode="ttl", scope="workspace", ttl_seconds=60)

    assert first.policy_root(tab_policy) != second.policy_root(tab_policy)
    assert first.policy_root(shared_policy) == second.policy_root(shared_policy)


def test_cache_hits_are_materialized_into_the_current_run(tmp_path: Path):
    cache = NodeCache(tmp_path, namespace=SESSION_A)
    key = cache.key({"node": "source:rows"})

    for mode in ("session", "persistent"):
        policy = CacheDefinition(mode=mode)
        original_store = ArtifactStore(tmp_path, f"run_{mode}_original")
        original = original_store.write_scalar(f"rows_{mode}", 7)
        cache.save(key, policy, {"main": original}, original_store)

        current_store = ArtifactStore(tmp_path, f"run_{mode}_current")
        loaded = cache.load(key, policy, current_store)

        assert loaded is not None
        materialized = loaded["main"]
        assert Path(materialized.path or "").parts[:3] == (
            ".dataviz",
            "runs",
            f"run_{mode}_current",
        )
        assert current_store.read_value(materialized) == 7
        try:
            original_store.read_value(materialized)
        except ValueError as error:
            assert "does not belong" in str(error)
        else:
            raise AssertionError("A cached Artifact leaked across Query Runs")


def test_failed_persistent_cache_publish_preserves_the_previous_entry(
    tmp_path: Path,
    monkeypatch,
):
    cache = NodeCache(tmp_path, namespace=SESSION_A)
    policy = CacheDefinition(mode="persistent")
    key = cache.key({"node": "source:rows"})
    first_store = ArtifactStore(tmp_path, "run_cache_first")
    cache.save(key, policy, {"main": first_store.write_scalar("rows", 7)}, first_store)

    def fail_publish(*_args, **_kwargs):
        raise OSError("simulated metadata publish failure")

    monkeypatch.setattr(cache_module, "atomic_write_text", fail_publish)
    second_store = ArtifactStore(tmp_path, "run_cache_second")
    cache.save(key, policy, {"main": second_store.write_scalar("rows", 9)}, second_store)

    current_store = ArtifactStore(tmp_path, "run_cache_current")
    loaded = NodeCache(tmp_path, namespace=SESSION_A).load(key, policy, current_store)
    assert loaded is not None
    assert current_store.read_value(loaded["main"]) == 7


def test_corrupt_persistent_cache_is_evicted_and_treated_as_a_miss(tmp_path: Path):
    cache = NodeCache(tmp_path, namespace=SESSION_A)
    policy = CacheDefinition(mode="persistent")
    store = ArtifactStore(tmp_path, "run_cache")
    key = cache.key({"node": "source:rows"})
    cache.save(key, policy, {"main": store.write_scalar("rows", 7)}, store)
    entry = cache.policy_root(policy) / key

    (entry / "result.json").write_text("{broken", encoding="utf-8")
    fresh = NodeCache(tmp_path, namespace=SESSION_A)

    assert fresh.load(key, policy, store) is None
    assert not entry.exists()


def test_persistent_cache_rejects_artifact_paths_outside_managed_storage(
    tmp_path: Path,
):
    cache = NodeCache(tmp_path, namespace=SESSION_A)
    policy = CacheDefinition(mode="persistent")
    store = ArtifactStore(tmp_path, "run_cache")
    key = cache.key({"node": "source:rows"})
    cache.save(key, policy, {"main": store.write_scalar("rows", 7)}, store)
    entry = cache.policy_root(policy) / key
    raw = json.loads((entry / "result.json").read_text(encoding="utf-8"))
    raw["main"]["path"] = str(tmp_path.parent / "outside.json")
    (entry / "result.json").write_text(json.dumps(raw), encoding="utf-8")

    assert NodeCache(tmp_path, namespace=SESSION_A).load(key, policy, store) is None
    assert not entry.exists()


def test_persistent_cache_evicts_artifacts_with_wrong_content_hash(tmp_path: Path):
    cache = NodeCache(tmp_path, namespace=SESSION_A)
    policy = CacheDefinition(mode="persistent")
    store = ArtifactStore(tmp_path, "run_cache")
    key = cache.key({"node": "source:rows"})
    cache.save(key, policy, {"main": store.write_scalar("rows", 7)}, store)
    entry = cache.policy_root(policy) / key
    metadata = json.loads((entry / "result.json").read_text(encoding="utf-8"))
    cached_artifact = tmp_path / metadata["main"]["path"]
    cached_artifact.write_text("8", encoding="utf-8")

    assert NodeCache(tmp_path, namespace=SESSION_A).load(key, policy, store) is None
    assert not entry.exists()


def test_manager_bounds_event_history_with_monotonic_offsets_and_cleans_generations(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    manager = RunManager(load_workspace(root))
    run = RunRecord("run_keep", SESSION_A, "sales", status="loading")
    interaction = InteractionRecord(
        "ix_keep",
        1,
        run.run_id,
        SESSION_A,
        "sales",
        "summary",
        status="loading",
    )

    for index in range(15):
        manager._append_bounded_event(
            run,
            ExecutionEvent(event="node_progress", run_id=run.run_id, data={"index": index}),
            10,
        )
        manager._append_bounded_event(
            interaction,
            {"event": "node_progress", "index": index},
            10,
        )

    assert run.event_offset == interaction.event_offset == 5
    assert [event.data["index"] for event in run.events] == list(range(5, 15))
    assert [event["index"] for event in interaction.events] == list(range(5, 15))

    manager.records[run.run_id] = run
    manager.generations = {
        (SESSION_A, "sales", run.run_id, "summary"): 1,
        (SESSION_A, "sales", "run_gone", "summary"): 4,
    }
    manager.latest_interactive_nodes = {
        (SESSION_A, run.run_id, "interactive:summary"): object(),
        (SESSION_A, "run_gone", "interactive:summary"): object(),
    }

    manager.cleanup()

    assert set(manager.generations) == {
        (SESSION_A, "sales", run.run_id, "summary")
    }
    assert set(manager.latest_interactive_nodes) == {
        (SESSION_A, run.run_id, "interactive:summary")
    }


def test_query_cancel_is_tab_scoped_and_same_dashboard_run_supersedes(tmp_path: Path):
    root = tmp_path / "query-cancel"
    dashboard = root / "dashboards" / "slow"
    (dashboard / "sources").mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v2\nkind: workspace\nid: cancel\ntitle: Cancel\n",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v17
kind: dashboard
id: slow
title: Slow
query_parameters:
  - {id: delay, type: single_input, value_type: number, default: 2}
sources: [sources/slow.yaml]
views:
  - {id: result, title: Result, template: table, input: source:slow/main}
sections:
  - {id: result, title: Result, views: [result]}
""",
        encoding="utf-8",
    )
    (dashboard / "sources" / "slow.yaml").write_text(
        """schema: dataviz/source/v6
kind: source
id: slow
type: python
code: slow.py
query_inputs: {delay: delay}
outputs: {main: {kind: table}}
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (dashboard / "sources" / "slow.py").write_text(
        """import time
import pandas as pd

def load(context):
    time.sleep(float(context.query_inputs["delay"]))
    return {"main": pd.DataFrame([{"delay": context.query_inputs["delay"]}])}
""",
        encoding="utf-8",
    )

    client = TestClient(create_app(root))
    first_a = client.post(
        "/api/dashboards/slow/runs",
        json={"session_id": SESSION_A, "query_parameter_state": _query_state(delay=5)},
    ).json()["run_id"]
    first_b = client.post(
        "/api/dashboards/slow/runs",
        json={"session_id": SESSION_B, "query_parameter_state": _query_state(delay=0.2)},
    ).json()["run_id"]

    assert client.delete(
        f"/api/runs/{first_a}", params={"session_id": SESSION_B}
    ).status_code == 404

    second_a = client.post(
        "/api/dashboards/slow/runs",
        json={"session_id": SESSION_A, "query_parameter_state": _query_state(delay=0)},
    ).json()["run_id"]

    records = {}
    for _ in range(200):
        records = {
            "first_a": client.get(
                f"/api/runs/{first_a}", params={"session_id": SESSION_A}
            ).json(),
            "second_a": client.get(
                f"/api/runs/{second_a}", params={"session_id": SESSION_A}
            ).json(),
            "first_b": client.get(
                f"/api/runs/{first_b}", params={"session_id": SESSION_B}
            ).json(),
        }
        if all(
            value["status"] in {"ready", "partial", "error", "cancelled"}
            for value in records.values()
        ):
            break
        time.sleep(0.03)

    assert records["first_a"]["status"] == "cancelled"
    assert records["second_a"]["result"]["status"] == "ready"
    assert records["first_b"]["result"]["status"] == "ready"
    assert records["first_b"]["result"]["query_parameter_state"]["delay"] == {"value": 0.2}
