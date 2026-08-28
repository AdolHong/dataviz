from __future__ import annotations

from pathlib import Path

from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer
from dataviz.state_snapshot import build_state_snapshot
from dataviz.workspace import load_workspace


ROOT = Path(__file__).resolve().parents[1]
MINIMAL = ROOT / "examples" / "minimal-workspace"


def test_state_snapshot_separates_committed_and_draft_values():
    workspace = load_workspace(MINIMAL)
    dashboard = workspace.dashboard("sales-overview")

    snapshot = build_state_snapshot(
        dashboard,
        query_parameters={"min_query_revenue": 100},
        selection_state={
            "dashboard:sales-overview/region": {
                "intent": "explicit",
                "values": ["华东", "华南"],
            }
        },
        compute_parameters={},
    )

    assert snapshot["schema"] == "dataviz/state-snapshot/v1"
    parameter = next(item for item in snapshot["items"] if item["kind"] == "query")
    selection = next(item for item in snapshot["items"] if item["kind"] == "selection")
    assert parameter["committed"] == 100
    assert parameter["stale"] is False
    assert selection["committed"] == {
        "intent": "explicit",
        "values": ["华东", "华南"],
    }


def test_default_canvas_embeds_snapshot_and_summary_hosts():
    workspace = load_workspace(MINIMAL)
    dashboard = workspace.dashboard("sales-overview")
    result = Executor(workspace).run("sales-overview", refresh=True)

    rendered = CanvasRenderer(workspace).render(dashboard, result, asset_mode="inline")

    assert dashboard.presentation is not None
    assert dashboard.presentation.state_summary.enabled is False
    assert '"schema": "dataviz/state-snapshot/v1"' in rendered
    assert 'data-state-summary-scope="dashboard"' in rendered
    assert 'data-state-summary-scope="section"' in rendered
    assert 'data-state-summary-scope="view"' in rendered
    assert "renderDatavizStateSummaries" in rendered
