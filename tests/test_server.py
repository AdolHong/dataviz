from __future__ import annotations

import json
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
        "density": "comfortable",
    }
    assert not [item for item in summary["diagnostics"] if item["level"] == "error"]


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
            "type": "date_range",
            "label": "Job date range",
            "required": True,
            "default": {
                "mode": "relative",
                "anchor": "today",
                "start_offset": "-3d",
                "end_offset": "-1d",
            },
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

    assert tuple(parameter["resolved_default"]) in expected
    assert parameter["default"] == {
        "mode": "relative",
        "anchor": "today",
        "start_offset": "-3d",
        "end_offset": "-1d",
    }

    started = client.post(
        "/api/dashboards/sales-overview/runs",
        json={"session_id": SESSION_A, "query_parameters": {"min_query_revenue": 0}},
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
    assert tuple(record["result"]["query_parameters"]["job_date_range"]) in expected


def test_server_never_serves_a_pyodide_bundle_outside_the_workspace(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, root)
    outside = tmp_path / "outside-pyodide"
    outside.mkdir()
    (outside / "runtime.js").write_text("outside", encoding="utf-8")
    workspace_path = root / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition["runtime"] = {
        **definition.get("runtime", {}),
        "pyodide_bundle_path": "../outside-pyodide",
    }
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    response = TestClient(create_app(root)).get("/runtime/pyodide/runtime.js")

    assert response.status_code == 404
    assert response.json()["detail"] == "Pyodide bundle is outside the Workspace"


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
            {"min_query_revenue": 0},
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
        json={"session_id": SESSION_A, "query_parameters": {}},
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
            "query_parameters": {"min_query_revenue": 0},
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
            "query_parameters": {"min_query_revenue": 0},
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
    assert {item["kind"] for item in summary["dashboards"][0]["controls"]} == {
        "selection"
    }
    assert all(
        "runtime_checked_views" in item
        and "declared_direct_views" in item
        for item in summary["dashboards"][0]["controls"]
    )
    started = client.post(
        "/api/dashboards/sales/runs",
        json={
            "session_id": SESSION_A,
            "query_parameters": {"target_factor": 1.0},
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
            "selection_state": {
                "dashboard:sales/region": {
                    "intent": "explicit",
                    "values": ["East"],
                }
            },
        },
    )
    assert report.status_code == 200
    assert "attachment" in report.headers["content-disposition"]
    assert '<option value="East" selected>' in report.text
    assert '<option value="West">' in report.text
    assert '"region": "West"' in report.text
    assert '"dashboard:sales/region": {"intent": "explicit", "values": ["East"]}' in report.text


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
        json={"session_id": SESSION_A, "query_parameters": {}, "refresh": True},
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


def test_server_app_selections_are_browser_only():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()
    query_block = script[script.index("async function runDashboard"):script.index("function listen")]
    assert "session_id: state.sessionId" in query_block
    assert "selections()" not in query_block
    assert "dataviz:set-selections" in script
    assert "dashboardStates: new Map()" in script
    assert "BroadcastChannel" in script
    assert "dataviz:canvas-interaction" in script
    assert "window.addEventListener('message'" in script
    assert "event.source === frame.contentWindow" in script
    assert "sameCanvasIdentity(event.data, identity)" in script
    assert "frame_id=" in script
    assert "closeHeaderPopovers();" in script
    assert "filter(([key]) => validKeys.has(key))" in script
    assert "state.selectionState = {...(event.data.selection_state || {})};" in script
    assert "state.canvasSelections" not in script
    assert "/static/app.js?v=" in template
    select_block = script[script.index("function selectDashboard"):script.index("function queryParameters")]
    assert "eventSource.close()" not in select_block


def test_query_parameters_are_an_inline_header_tray_owned_by_the_run_control():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()

    assert 'id="query-run-control"' in template
    assert 'id="query-parameters-toggle"' in template
    assert 'aria-controls="query-parameters-panel"' in template
    assert 'id="query-parameters-panel"' in template
    query_owner = template[
        template.index('id="query-parameters-control"'):
        template.index('</section>', template.index('id="query-parameters-control"'))
    ]
    assert "data-header-popover" not in query_owner
    assert "data-overlay-floating" not in query_owner
    assert "data-control-panel-body" in query_owner
    assert "queryParametersOpen" in script
    assert "toggleQueryParameters" in script
    assert "setQueryParametersOpen(true, {persist: true})" in script
    assert "Escape" not in script[
        script.index("function setQueryParametersOpen"):
        script.index("function dashboardSelectionState")
    ]


def test_server_sidebar_is_resizable_collapsible_and_tab_local():
    template = (ROOT / "src" / "dataviz" / "server" / "templates" / "index.html").read_text()
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()
    style = (ROOT / "src" / "dataviz" / "server" / "static" / "server.css").read_text()

    assert 'id="sidebar-toggle"' in template
    assert 'id="sidebar-resizer"' in template
    assert 'role="separator"' in template
    assert "sidebar: {width: state.sidebarWidth, collapsed: state.sidebarCollapsed}" in script
    assert "setPointerCapture" in script
    assert "['ArrowLeft', 'ArrowRight', 'Home', 'End']" in script
    assert "body.sidebar-collapsed" in style
    assert "--sidebar-width" in style


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


def test_run_ready_is_emitted_after_result_is_available():
    manager = RunManager(load_workspace(WORKSPACE))
    record = manager.start(
        "sales",
        {"target_factor": 1.0},
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
        "schema: dataviz/workspace/v1\nkind: workspace\nid: progressive\ntitle: Progressive\n",
        encoding="utf-8",
    )
    (dashboard_root / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v7
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
        """schema: dataviz/dataset-transform/v2
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
        """schema: dataviz/interactive-transform/v2
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
        json={"session_id": SESSION_A, "query_parameters": {}},
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
            "compute_parameters": {},
            "selection_state": {},
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
        "sales", {"target_factor": 1.0}, session_id=SESSION_A
    )
    second = manager.start(
        "sales", {"target_factor": 1.25}, session_id=SESSION_B
    )
    for _ in range(100):
        if first.result and second.result:
            break
        time.sleep(0.05)

    assert first.result and second.result
    assert first.result.query_parameters["target_factor"] == 1.0
    assert second.result.query_parameters["target_factor"] == 1.25
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
        json={"session_id": SESSION_A, "query_parameters": {"target_factor": 1.0}},
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
        "schema: dataviz/workspace/v1\nkind: workspace\nid: cancel\ntitle: Cancel\n",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v7
kind: dashboard
id: slow
title: Slow
query_parameters:
  - {id: delay, type: number, default: 2}
sources: [sources/slow.yaml]
views:
  - {id: result, title: Result, template: table, input: source:slow/main}
sections:
  - {id: result, title: Result, views: [result]}
""",
        encoding="utf-8",
    )
    (dashboard / "sources" / "slow.yaml").write_text(
        """schema: dataviz/source/v2
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
        json={"session_id": SESSION_A, "query_parameters": {"delay": 5}},
    ).json()["run_id"]
    first_b = client.post(
        "/api/dashboards/slow/runs",
        json={"session_id": SESSION_B, "query_parameters": {"delay": 0.2}},
    ).json()["run_id"]

    assert client.delete(
        f"/api/runs/{first_a}", params={"session_id": SESSION_B}
    ).status_code == 404

    second_a = client.post(
        "/api/dashboards/slow/runs",
        json={"session_id": SESSION_A, "query_parameters": {"delay": 0}},
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
    assert records["first_b"]["result"]["query_parameters"]["delay"] == 0.2
