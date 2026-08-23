from __future__ import annotations

import json
import os
import time
from pathlib import Path

from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.maintenance import cleanup_workspace_storage
from dataviz.server.manager import RunManager, RunRecord
from dataviz.workspace import load_workspace


def _workspace(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v1\nkind: workspace\nid: cleanup\ntitle: Cleanup\n",
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

    preview = runner.invoke(app, ["clean", str(root), "--all"])
    assert preview.exit_code == 0, preview.output
    preview_payload = json.loads(preview.output)
    assert preview_payload["mode"] == "dry-run"
    assert preview_payload["candidate_count"] == 1
    assert (root / ".dataviz" / "runs" / "run_old").exists()

    applied = runner.invoke(app, ["clean", str(root), "--all", "--apply"])
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
