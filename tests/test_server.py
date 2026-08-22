from __future__ import annotations

import time
import shutil
from pathlib import Path

import yaml

from fastapi.testclient import TestClient

from dataviz.server import create_app
from dataviz.server.manager import RunManager
from dataviz.execution.cache import NodeCache
from dataviz.workspace import load_workspace
from dataviz.workspace.models import CacheDefinition


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "examples" / "sales-workspace"
MINIMAL_WORKSPACE = ROOT / "examples" / "minimal-workspace"
SESSION_A = "tab_session_a123"
SESSION_B = "tab_session_b456"


def test_server_exposes_active_presentation_contract():
    client = TestClient(create_app(MINIMAL_WORKSPACE))
    summary = client.get("/api/workspace").json()
    dashboard = next(item for item in summary["dashboards"] if item["id"] == "sales-overview")

    assert dashboard["presentation"]["active"] is True
    assert dashboard["presentation"]["file"].endswith("presentation.yaml")
    assert dashboard["presentation"]["diagnostics"] == []
    assert not [item for item in summary["diagnostics"] if item["level"] == "error"]


def test_server_run_and_canvas():
    client = TestClient(create_app(WORKSPACE))
    assert client.get("/").status_code == 200
    summary = client.get("/api/workspace").json()
    assert summary["dashboards"][0]["id"] == "sales"
    assert summary["dashboards"][0]["canvas_name"] == "sales"
    assert summary["dashboards"][0]["query_parameters"][0]["id"] == "target_factor"
    assert {item["origin"] for item in summary["dashboards"][0]["selections"]} == {
        "dashboard",
        "section",
        "view",
    }
    started = client.post(
        "/api/dashboards/sales/runs",
        json={"session_id": SESSION_A, "parameters": {"target_factor": 1.0}},
    ).json()
    run_id = started["run_id"]
    record = None
    for _ in range(100):
        record = client.get(f"/api/runs/{run_id}", params={"session_id": SESSION_A}).json()
        if record["status"] in {"success", "partial", "failed"}:
            break
        time.sleep(0.05)
    assert record and record["status"] == "success", record
    assert record["result"]["selections"]["dashboard:sales/region"] == [
        "North",
        "South",
        "East",
        "West",
    ]
    canvas = client.get(
        f"/api/dashboards/sales/canvas?run_id={run_id}",
        params={"session_id": SESSION_A},
    )
    assert canvas.status_code == 200
    assert "FIELD NOTE / 026" in canvas.text
    assert '"portable": {"sources": {"orders": [' in canvas.text
    assert "PORTABLE ANALYSIS" not in canvas.text
    report = client.get(
        f"/api/dashboards/sales/report?run_id={run_id}",
        params={
            "session_id": SESSION_A,
            "selections": '{"dashboard:sales/region":["East"]}',
        },
    )
    assert report.status_code == 200
    assert "attachment" in report.headers["content-disposition"]
    assert '<option value="East" selected>' in report.text
    assert '<option value="West">' in report.text
    assert '"region": "West"' in report.text


def test_server_app_selections_are_browser_only():
    script = (ROOT / "src" / "dataviz" / "server" / "static" / "app.js").read_text()
    query_block = script[script.index("async function runDashboard"):script.index("function listen")]
    assert "session_id: state.sessionId" in query_block
    assert "selections()" not in query_block
    assert "dataviz:set-selections" in script
    assert "dashboardStates: new Map()" in script
    assert "BroadcastChannel" in script
    select_block = script[script.index("function selectDashboard"):script.index("function parameters")]
    assert "eventSource.close()" not in select_block


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


def test_server_ignores_stale_legacy_entries_and_exposes_local_additions(tmp_path: Path):
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
    dashboards = {item["id"]: item for item in response.json()["dashboards"]}
    assert "gone" not in dashboards
    assert dashboards["local-copy"]["discovered"] is True
    assert dashboards["local-copy"]["canvas_name"] == "local-copy"
    assert dashboards["local-copy"]["title"] == "Local copy"
    assert dashboards["local-copy"]["logical_path"] == "local-copy"


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
        {"region": ["North"], "target_factor": 1.0},
        session_id=SESSION_A,
    )
    for _ in range(100):
        if record.status in {"success", "partial", "failed"}:
            break
        time.sleep(0.05)
    assert record.result is not None
    names = [event.event for event in record.events]
    assert "run_completed" in names
    assert names[-1] == "run_ready"


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
    assert first.result.parameters["target_factor"] == 1.0
    assert second.result.parameters["target_factor"] == 1.25
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
        json={"session_id": SESSION_A, "parameters": {"target_factor": 1.0}},
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
