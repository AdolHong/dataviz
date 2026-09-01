from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.maintenance import cleanup_workspace_storage
from dataviz.server.manager import InteractionRecord, RunManager, RunRecord
from dataviz.workspace import load_workspace


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "builder",
    [
        "tools/build_canvas_runtime.py",
        "tools/build_tanstack_table_runtime.py",
    ],
)
def test_generated_browser_asset_is_current(builder: str):
    completed = subprocess.run(
        [sys.executable, builder, "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def _workspace(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v2\nkind: workspace\nid: cleanup\ntitle: Cleanup\n",
        encoding="utf-8",
    )
    return root


def _entry(path: Path, modified_at: float) -> None:
    path.mkdir(parents=True)
    (path / "payload.txt").write_text("payload", encoding="utf-8")
    os.utime(path, (modified_at, modified_at))


def _cache_entry(path: Path, modified_at: float) -> None:
    path.mkdir(parents=True)
    (path / "result.json").write_text("{}", encoding="utf-8")
    os.utime(path / "result.json", (modified_at, modified_at))
    os.utime(path, (modified_at, modified_at))


def test_cleanup_is_dry_run_by_default_and_respects_protected_runs(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    now = time.time()
    runs = root / ".dataviz" / "runs"
    _entry(runs / "run_new", now)
    _entry(runs / "run_old", now - 100)
    _entry(runs / "run_active", now - 200)
    cache = root / ".dataviz" / "cache" / "workspace"
    _cache_entry(cache / "new", now)
    _cache_entry(cache / "old", now - 100)

    preview = cleanup_workspace_storage(
        root,
        max_runs=1,
        run_max_age_seconds=None,
        max_cache_entries=1,
        cache_max_age_seconds=None,
        protected_run_ids={"run_active"},
        now=now,
    )

    assert preview["mode"] == "dry-run"
    assert {item["relative_path"] for item in preview["runs"]} == {"run_old"}
    assert {item["relative_path"] for item in preview["cache"]} == {
        "workspace/old"
    }
    assert (runs / "run_old").exists()
    assert (runs / "run_active").exists()

    applied = cleanup_workspace_storage(
        root,
        max_runs=1,
        run_max_age_seconds=None,
        max_cache_entries=1,
        cache_max_age_seconds=None,
        protected_run_ids={"run_active"},
        now=now,
        apply=True,
    )
    assert applied["deleted_count"] == 2
    assert not (runs / "run_old").exists()
    assert not (cache / "old").exists()
    assert (runs / "run_active").exists()


def test_cleanup_removes_empty_tab_cache_namespaces(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    cache_namespace = root / ".dataviz" / "cache" / "tabs" / "tab-hash"
    _cache_entry(cache_namespace / "old-entry", time.time() - 100)

    applied = cleanup_workspace_storage(
        root,
        max_runs=None,
        run_max_age_seconds=None,
        max_cache_entries=0,
        cache_max_age_seconds=None,
        apply=True,
    )

    assert applied["deleted_count"] == 1
    assert not cache_namespace.exists()
    assert not (root / ".dataviz" / "cache" / "tabs").exists()
    assert (root / ".dataviz" / "cache").exists()


def test_clean_cli_previews_then_applies_all_state(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    _entry(root / ".dataviz" / "runs" / "run_old", time.time() - 100)
    runner = CliRunner()

    preview = runner.invoke(app, ["prune", str(root), "--all"])
    assert preview.exit_code == 0, preview.output
    preview_payload = json.loads(preview.output)
    assert preview_payload["mode"] == "dry-run"
    assert preview_payload["candidate_count"] == 1
    assert (root / ".dataviz" / "runs" / "run_old").exists()

    applied = runner.invoke(app, ["prune", str(root), "--all", "--apply"])
    assert applied.exit_code == 0, applied.output
    applied_payload = json.loads(applied.output)
    assert applied_payload["mode"] == "apply"
    assert applied_payload["deleted_count"] == 1
    assert not (root / ".dataviz" / "runs" / "run_old").exists()


def test_run_manager_bounds_completed_records_and_their_artifacts(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    workspace.definition.runtime.max_retained_runs = 1
    workspace.definition.runtime.run_retention_seconds = None
    manager = RunManager(workspace)
    now = time.time()

    for index in range(3):
        run_id = f"run_{index}"
        _entry(root / ".dataviz" / "runs" / run_id, now - (3 - index))
        manager.records[run_id] = RunRecord(
            run_id=run_id,
            session_id="tab-a",
            dashboard_id="dashboard-a",
            status="success",
            created_at=now - (3 - index),
            finished_at=now - (3 - index),
        )
    manager.latest[("tab-a", "dashboard-a")] = "run_2"

    report = manager.cleanup()

    assert set(manager.records) == {"run_2"}
    assert manager.latest == {("tab-a", "dashboard-a"): "run_2"}
    assert report["deleted_count"] == 2
    assert (root / ".dataviz" / "runs" / "run_2").exists()


def test_run_retention_limit_is_applied_per_browser_session(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    workspace.definition.runtime.max_retained_runs = 1
    workspace.definition.runtime.run_retention_seconds = None
    manager = RunManager(workspace)
    now = time.time()

    for session, offset in (("tab-a", 0), ("tab-b", 10)):
        for index in range(2):
            run_id = f"run_{session[-1]}_{index}"
            timestamp = now - offset - (2 - index)
            _entry(root / ".dataviz" / "runs" / run_id, timestamp)
            manager.records[run_id] = RunRecord(
                run_id=run_id,
                session_id=session,
                dashboard_id="dashboard-a",
                status="success",
                created_at=timestamp,
                finished_at=timestamp,
            )
        manager.latest[(session, "dashboard-a")] = f"run_{session[-1]}_1"

    report = manager.cleanup()

    assert set(manager.records) == {"run_a_1", "run_b_1"}
    assert set(manager.latest.values()) == {"run_a_1", "run_b_1"}
    assert report["deleted_count"] == 2
    assert (root / ".dataviz" / "runs" / "run_a_1").exists()
    assert (root / ".dataviz" / "runs" / "run_b_1").exists()


def test_active_interaction_protects_its_query_run_and_cache_from_cleanup(
    tmp_path: Path,
):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    workspace.definition.runtime.max_retained_runs = 1
    workspace.definition.runtime.max_retained_cache_entries = 0
    workspace.definition.runtime.run_retention_seconds = None
    workspace.definition.runtime.cache_retention_seconds = None
    manager = RunManager(workspace)
    now = time.time()

    _entry(root / ".dataviz" / "runs" / "run_active", now - 100)
    _entry(root / ".dataviz" / "runs" / "run_new", now)
    cache_entry = root / ".dataviz" / "cache" / "workspace" / "old"
    _cache_entry(cache_entry, now - 100)
    manager.records["run_active"] = RunRecord(
        run_id="run_active",
        session_id="tab-a",
        dashboard_id="dashboard-a",
        status="ready",
        created_at=now - 100,
        finished_at=now - 100,
    )
    manager.records["run_new"] = RunRecord(
        run_id="run_new",
        session_id="tab-a",
        dashboard_id="dashboard-a",
        status="ready",
        created_at=now,
        finished_at=now,
    )
    interaction = InteractionRecord(
        interaction_id="ix_active",
        generation=1,
        run_id="run_active",
        session_id="tab-a",
        dashboard_id="dashboard-a",
        target="summary",
        status="loading",
    )
    manager.interactions[interaction.interaction_id] = interaction

    active_report = manager.cleanup()

    assert set(manager.records) == {"run_active", "run_new"}
    assert active_report["deleted_count"] == 0
    assert cache_entry.exists()

    interaction.status = "ready"
    completed_report = manager.cleanup()

    assert set(manager.records) == {"run_new"}
    assert completed_report["deleted_count"] == 2
    assert not cache_entry.exists()
