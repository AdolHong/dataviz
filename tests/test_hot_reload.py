from __future__ import annotations

import shutil
import time
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from dataviz.server import create_app


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_WORKSPACE = ROOT / "examples" / "minimal-workspace"
WORKER_WORKSPACE = ROOT / "tests" / "fixtures" / "browser-worker-workspace"


def wait_for_event(app, after: int, *, timeout: float = 5):
    deadline = time.monotonic() + timeout
    journal = app.state.workspace_change_journal
    while time.monotonic() < deadline:
        events = journal.after(after)
        if events:
            return events[-1]
        time.sleep(0.03)
    raise AssertionError("workspace watcher did not publish a change event")


def impact_for(event, dashboard_id: str) -> str | None:
    return event.changes.get(dashboard_id)


def test_watcher_classifies_canvas_and_query_changes_without_restart(tmp_path: Path):
    workspace = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, workspace)
    app = create_app(workspace, watch=True)

    with TestClient(app) as client:
        assert app.state.workspace_watcher.running is True
        summary = client.get("/api/workspace").json()
        assert summary["hot_reload"] == {
            "enabled": True,
            "revision": 0,
            "last_event": None,
        }

        revision = app.state.workspace_change_journal.revision
        unrelated = workspace / "dashboards" / "sales-overview" / "editor-note.tmp"
        unrelated.write_text("not a Dashboard dependency\n", encoding="utf-8")
        unrelated_event = wait_for_event(app, revision)

        assert unrelated_event.status == "ready"
        assert unrelated_event.changes == {}

        revision = unrelated_event.revision
        css = workspace / "dashboards" / "sales-overview" / "assets" / "presentation.css"
        css.write_text(css.read_text(encoding="utf-8") + "\n/* hot canvas */\n", encoding="utf-8")
        canvas_event = wait_for_event(app, revision)

        assert canvas_event.status == "ready"
        assert impact_for(canvas_event, "sales-overview") == "canvas"

        revision = canvas_event.revision
        sql = workspace / "dashboards" / "sales-overview" / "sources" / "sales.sql"
        sql.write_text(sql.read_text(encoding="utf-8") + "\n-- hot query\n", encoding="utf-8")
        query_event = wait_for_event(app, revision)

        assert query_event.status == "ready"
        assert impact_for(query_event, "sales-overview") == "query"

        revision = query_event.revision
        workspace_path = workspace / "workspace.yaml"
        definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
        definition.setdefault("runtime", {})["max_workers"] = 3
        workspace_path.write_text(
            yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        server_event = wait_for_event(app, revision)

        assert server_event.status == "ready"
        assert impact_for(server_event, "sales-overview") == "server"

    assert app.state.workspace_watcher.running is False


def test_watcher_classifies_browser_transform_as_analysis(tmp_path: Path):
    workspace = tmp_path / "workspace"
    shutil.copytree(WORKER_WORKSPACE, workspace)
    app = create_app(workspace, watch=True)

    with TestClient(app):
        revision = app.state.workspace_change_journal.revision
        transform = workspace / "dashboards" / "worker-runtime" / "transforms" / "scaled.js"
        transform.write_text(
            transform.read_text(encoding="utf-8") + "\n// hot analysis\n",
            encoding="utf-8",
        )
        event = wait_for_event(app, revision)

        revision = event.revision
        data = workspace / "dashboards" / "worker-runtime" / "data" / "rows.csv"
        data.write_text(
            data.read_text(encoding="utf-8") + "\nnew,9\n",
            encoding="utf-8",
        )
        data_event = wait_for_event(app, revision)

    assert event.status == "ready"
    assert impact_for(event, "worker-runtime") == "analysis"
    assert data_event.status == "ready"
    assert impact_for(data_event, "worker-runtime") == "query"


def test_invalid_edit_publishes_diagnostic_and_recovery_event(tmp_path: Path):
    workspace = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, workspace)
    app = create_app(workspace, watch=True)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    original = dashboard_path.read_text(encoding="utf-8")

    with TestClient(app) as client:
        revision = app.state.workspace_change_journal.revision
        dashboard_path.write_text("schema: [broken", encoding="utf-8")

        # A manual refresh can race the watcher while an editor has only
        # written half a YAML document. It must retain the last valid snapshot
        # instead of leaking a transient 500 response.
        retained_during_write = client.get("/api/workspace")
        assert retained_during_write.status_code == 200
        assert next(
            item
            for item in retained_during_write.json()["dashboards"]
            if item["id"] == "sales-overview"
        )["runnable"] is True

        invalid = wait_for_event(app, revision)

        assert invalid.status == "invalid"
        assert invalid.diagnostics
        assert app.state.workspace.dashboard("sales-overview").title == "销售概览"
        retained = client.get("/api/workspace").json()
        assert next(
            item for item in retained["dashboards"] if item["id"] == "sales-overview"
        )["runnable"] is True
        assert retained["hot_reload"]["last_event"]["status"] == "invalid"

        revision = invalid.revision
        dashboard_path.write_text(original, encoding="utf-8")
        recovered = wait_for_event(app, revision)

    assert recovered.status == "ready"
    # Returning to the exact previous definition clears the invalid revision
    # without needlessly replacing the Canvas that remained mounted.
    assert recovered.changes == {}


def test_no_watch_mode_keeps_request_time_reload_fallback(tmp_path: Path):
    workspace = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, workspace)
    app = create_app(workspace, watch=False)
    workspace_path = workspace / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition["title"] = "Manually reloaded"
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    response = TestClient(app).get("/api/workspace")

    assert response.status_code == 200
    assert response.json()["workspace"]["title"] == "Manually reloaded"
    assert response.json()["hot_reload"]["enabled"] is False
    assert app.state.workspace_watcher.running is False


def test_run_flushes_saved_query_definition_before_capturing_revision(tmp_path: Path):
    workspace = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, workspace)
    app = create_app(workspace, watch=True)

    with TestClient(app) as client:
        before = app.state.workspace_change_journal.revision
        sql = workspace / "dashboards" / "sales-overview" / "sources" / "sales.sql"
        sql.write_text(sql.read_text(encoding="utf-8") + "\n-- saved then run\n", encoding="utf-8")

        response = client.post(
            "/api/dashboards/sales-overview/runs",
            json={
                "session_id": "tab_hot_reload",
                "query_parameters": {"min_query_revenue": 0},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["workspace_revision"] > before
        event = app.state.workspace_change_journal.latest
        assert event is not None
        assert impact_for(event, "sales-overview") == "query"
