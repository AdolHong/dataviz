import json
from pathlib import Path
import sqlite3
import subprocess

import pytest
import yaml

from dataviz.action_examples import annotation_recipe
from dataviz.actions import ActionResources
from dataviz.auth import AdapterResolver
from dataviz.execution.action_journal import ActionJournal
from dataviz.execution.action_process import execute_action
from dataviz.execution import Executor
from dataviz.artifacts import ArtifactStore
from dataviz.standalone import prepare_input
from dataviz.workspace import load_workspace
from dataviz.validation import validate_workspace


def test_action_queue_is_serial_and_preserves_submission_boundaries():
    script = Path(__file__).parent / "js" / "action-queue.mjs"
    completed = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_cli_recipe_validates_and_persists_with_conflict_recovery(tmp_path, monkeypatch):
    recipe = annotation_recipe()
    monkeypatch.chdir(tmp_path)
    exec(compile(recipe["setup.py"], "setup.py", "exec"), {})
    for filename in ("connections.yaml", "annotation.yaml"):
        (tmp_path / filename).write_text(yaml.safe_dump(recipe[filename]))
    root, _ = prepare_input(tmp_path / "annotation.yaml", auth=tmp_path / "connections.yaml")
    workspace = load_workspace(root)
    assert not [item for item in validate_workspace(workspace) if item.severity == "error"]
    dashboard = workspace.dashboard("annotation-demo")
    path, definition = dashboard.server_actions["save_label"]
    journal = ActionJournal(tmp_path / "receipts.sqlite")
    resources = ActionResources(AdapterResolver(root), definition.resources, dashboard.definition.adapters)

    def save(request_id, revision, label):
        return execute_action(journal=journal, scope="recipe", request_id=request_id,
                              definition=definition, definition_path=path, resources=resources,
                              dashboard_root=dashboard.root,
                              payload={"id": "apple", "revision": revision, "label": label})

    first = save("first", 0, "sensitive")
    assert first["status"] == "succeeded", first
    assert first["invalidations"] == ["source:annotations"]
    assert save("first", 0, "sensitive") == first  # Includes original timings, never replayed.
    stale = save("stale", 0, "negative")
    assert stale["status"] == "failed"
    assert stale["timings"]["python_execute_ms"] >= 0
    assert save("second", 1, "negative")["status"] == "succeeded"
    assert save("clear", 2, None)["status"] == "succeeded"
    with sqlite3.connect(tmp_path / "annotations.sqlite") as db:
        assert db.execute("select label, revision from annotations").fetchone() == (None, 3)
    result = Executor(workspace).run("annotation-demo")
    assert result.status == "ready"
    rows = ArtifactStore(root, result.run_id).read_table(result.outputs["source:annotations/main"])
    assert rows.iloc[0]["id"] == "apple" and rows.iloc[0]["revision"] == 3


@pytest.mark.parametrize("scenario", ["fast", "pending", "transport_failure", "refresh_failure"])
def test_saved_progress_precedes_client_refresh_and_keeps_outcome(scenario):
    script = Path(__file__).parent / "js" / "action-save-feedback.mjs"
    completed = subprocess.run(["node", str(script), scenario], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["scenario"] == scenario
