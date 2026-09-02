from __future__ import annotations

from pathlib import Path

import pytest

from dataviz.errors import ValidationFailure
from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer
from dataviz.state_snapshot import build_state_snapshot, normalize_consumer_revisions
from dataviz.workspace import load_workspace


ROOT = Path(__file__).resolve().parents[1]
MINIMAL = ROOT / "examples" / "minimal-workspace"
SHOWCASE = ROOT / "examples" / "feature-showcase"


def test_state_snapshot_separates_committed_and_draft_values():
    workspace = load_workspace(MINIMAL)
    dashboard = workspace.dashboard("sales-overview")

    snapshot = build_state_snapshot(
        dashboard,
        query_parameter_state={"min_query_revenue": {"value": 100}},
        control_state={
            "dashboard:sales-overview/region": {
                "intent": "explicit",
                "value": ["华东", "华南"],
                "revision": 3,
            }
        },
    )

    assert snapshot["schema"] == "dataviz/state-snapshot/v6"
    parameter = next(
        item for item in snapshot["items"] if item["entry_type"] == "query_parameter"
    )
    control = next(
        item for item in snapshot["items"] if item["entry_type"] == "control"
    )
    assert parameter["committed"] == {"value": 100}
    assert parameter["stale"] is False
    assert control["committed"] == {
        "intent": "explicit",
        "value": ["华东", "华南"],
        "revision": 3,
    }


def test_default_canvas_embeds_snapshot_and_summary_hosts():
    workspace = load_workspace(MINIMAL)
    dashboard = workspace.dashboard("sales-overview")
    result = Executor(workspace).run("sales-overview", refresh=True)

    rendered = CanvasRenderer(workspace).render(dashboard, result, asset_mode="inline")

    assert dashboard.presentation is not None
    assert dashboard.presentation.state_summary.enabled is False
    assert '"schema": "dataviz/state-snapshot/v6"' in rendered
    assert 'data-state-summary-scope="dashboard"' in rendered
    assert 'data-state-summary-scope="section"' in rendered
    assert 'data-state-summary-scope="view"' in rendered
    assert "renderDatavizStateSummaries" in rendered


def test_consumer_revisions_distinguish_effective_and_applied_state():
    dashboard = load_workspace(MINIMAL).dashboard("sales-overview")
    control_state = {
        "dashboard:sales-overview/region": {
            "intent": "explicit",
            "value": ["华东"],
            "revision": 3,
        }
    }

    evidence = normalize_consumer_revisions(
        dashboard,
        control_state,
        {
            "views": {
                "revenue-trend": {
                    "dashboard:sales-overview/region": 2,
                },
                "unknown-view": {"unknown-control": 999},
            },
            "transforms": {},
        },
        {
            "views": {
                "revenue-trend": {
                    "dashboard:sales-overview/region": {
                        "intent": "explicit",
                        "value": ["华南"],
                        "revision": 2,
                    }
                }
            },
            "transforms": {},
        },
    )

    trend = evidence["views"]["revenue-trend"]
    assert trend == {
        "trigger": "auto",
        "stale": True,
        "controls": {
            "dashboard:sales-overview/region": {
                "effective_revision": 3,
                "applied_revision": 2,
                "stale": True,
            }
        },
        "applied_control_state": {
            "dashboard:sales-overview/region": {
                "intent": "explicit",
                "value": ["华南"],
                "revision": 2,
            }
        },
        "applied_writer_provenance": {},
    }
    assert "unknown-view" not in evidence["views"]
    assert evidence["views"]["total-revenue"]["controls"][
        "dashboard:sales-overview/region"
    ]["applied_revision"] is None


def test_consumer_revision_cannot_be_ahead_of_effective_state():
    dashboard = load_workspace(MINIMAL).dashboard("sales-overview")

    with pytest.raises(ValidationFailure) as raised:
        normalize_consumer_revisions(
            dashboard,
            {
                "dashboard:sales-overview/region": {
                    "intent": "explicit",
                    "value": ["华东"],
                    "revision": 3,
                }
            },
            {
                "views": {
                    "revenue-trend": {
                        "dashboard:sales-overview/region": 4,
                    }
                },
                "transforms": {},
            },
            {
                "views": {
                    "revenue-trend": {
                        "dashboard:sales-overview/region": {
                            "intent": "explicit",
                            "value": ["华东"],
                            "revision": 4,
                        }
                    }
                },
                "transforms": {},
            },
        )

    assert raised.value.details["code"] == "consumer_applied_revision_ahead"


def test_consumer_revision_seals_valid_writer_provenance():
    dashboard = load_workspace(SHOWCASE).dashboard("chart-gallery")
    key = "dashboard:chart-gallery/province"
    state = {"value": ["广东"], "intent": "explicit", "revision": 1}
    evidence = normalize_consumer_revisions(
        dashboard,
        {key: state},
        {"views": {"trend": {key: 1}}, "transforms": {}},
        {"views": {"trend": {key: state}}, "transforms": {}},
        {
            "views": {
                "trend": {
                    key: {
                        "revision": 1,
                        "action_id": "ranking-select-guangdong",
                        "source_view": "ranking",
                        "action": "select",
                    }
                }
            },
            "transforms": {},
        },
    )

    assert evidence["views"]["trend"]["applied_writer_provenance"][key] == {
        "revision": 1,
        "action_id": "ranking-select-guangdong",
        "source_view": "ranking",
        "action": "select",
    }


def test_consumer_revision_seals_map_layer_writer_provenance():
    dashboard = load_workspace(SHOWCASE).dashboard("map-lab")
    key = "dashboard:map-lab/store"
    state = {"value": "SZ-001", "revision": 2}
    evidence = normalize_consumer_revisions(
        dashboard,
        {key: state},
        {"views": {"region-table": {key: 2}}, "transforms": {}},
        {"views": {"region-table": {key: state}}, "transforms": {}},
        {
            "views": {
                "region-table": {
                    key: {
                        "revision": 2,
                        "action_id": "region-map-store-select",
                        "source_view": "region-revenue",
                        "source_layer": "stores",
                        "action": "select",
                    }
                }
            },
            "transforms": {},
        },
    )

    assert evidence["views"]["region-table"]["applied_writer_provenance"][key] == {
        "revision": 2,
        "action_id": "region-map-store-select",
        "source_view": "region-revenue",
        "source_layer": "stores",
        "action": "select",
    }


def test_consumer_revision_rejects_unbound_writer_source_view():
    dashboard = load_workspace(SHOWCASE).dashboard("chart-gallery")
    key = "dashboard:chart-gallery/province"
    state = {"value": ["广东"], "intent": "explicit", "revision": 1}

    with pytest.raises(ValidationFailure) as raised:
        normalize_consumer_revisions(
            dashboard,
            {key: state},
            {"views": {"trend": {key: 1}}, "transforms": {}},
            {"views": {"trend": {key: state}}, "transforms": {}},
            {
                "views": {
                    "trend": {
                        key: {
                            "revision": 1,
                            "action_id": "forged",
                            "source_view": "trend",
                            "action": "select",
                        }
                    }
                },
                "transforms": {},
            },
        )

    assert raised.value.details["code"] == "control_writer_source_view_invalid"
