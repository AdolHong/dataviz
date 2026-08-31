from __future__ import annotations

import json
import shutil
from pathlib import Path

from dataviz.workspace import load_workspace


ROOT = Path(__file__).resolve().parents[1]
FEATURE_SHOWCASE = ROOT / "examples" / "feature-showcase"
SCENARIO = ROOT / "tests" / "fixtures" / "p1d-linked-brushing.json"


def _copy_chart_gallery(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "linked-brushing"
    workspace.mkdir()
    shutil.copy2(FEATURE_SHOWCASE / "workspace.yaml", workspace / "workspace.yaml")
    shutil.copytree(FEATURE_SHOWCASE / "auth", workspace / "auth")
    source = FEATURE_SHOWCASE / "dashboards" / "功能示例##chart-gallery"
    dashboard = workspace / "dashboards" / source.name
    dashboard.parent.mkdir()
    shutil.copytree(source, dashboard)
    return workspace, dashboard / "dashboard.yaml"


def test_real_linked_brushing_compiles_ordered_writer_edges(
    tmp_path: Path,
):
    workspace, _dashboard_path = _copy_chart_gallery(tmp_path)
    dashboard = load_workspace(workspace).dashboard("chart-gallery")
    contract = dashboard.dependency_contract
    control = contract.controls["dashboard:chart-gallery/province"]
    assert [edge.view_id for edge in control.writer_edges] == ["ranking", "scatter"]
    assert [edge.fields for edge in control.writer_edges] == [
        ("province",),
        ("province",),
    ]
    assert set(control.affected_views) >= {"ranking", "scatter"}


def test_linked_brushing_design_corpus_is_deterministic_and_versioned():
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))

    assert scenario["schema"] == "dataviz/p1d-linked-brushing-characterization/v1"
    assert scenario["status"] == "implemented"
    assert [writer["view"] for writer in scenario["use_case"]["writers"]] == [
        "ranking",
        "scatter",
    ]
    assert scenario["invariants"]["select_semantics"] == "replace"
    assert scenario["invariants"]["implicit_union"] is False

    actions = scenario["actions"]
    assert len({action["action_id"] for action in actions}) == len(actions)
    assert [action["expected"]["revision"] for action in actions] == [1, 2, 3, 4]
    assert all(
        action["source_view"] == action["expected"]["last_source_view"]
        for action in actions
    )

    versions = scenario["version_decision"]
    for boundary in (
        "dashboard",
        "dependency_contract",
        "runtime",
        "state_snapshot",
        "analysis_result",
        "analysis_evidence",
    ):
        assert versions[boundary]["to"] == versions[boundary]["from"] + 1
