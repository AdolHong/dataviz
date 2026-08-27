from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from dataviz.execution.executor import Executor
from dataviz.rendering.canvas import CanvasRenderer
from dataviz.workspace.loader import load_workspace, validate_workspace


ROOT = Path(__file__).resolve().parents[1]
MINIMAL = ROOT / "examples" / "minimal-workspace"
CUSTOM = ROOT / "examples" / "sales-workspace"


def _copy_workspace(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _definition_path(workspace: Path, dashboard: str) -> Path:
    return workspace / "dashboards" / dashboard / "dashboard.yaml"


def test_layout_contract_is_the_only_declarative_structure_owner():
    dashboard = load_workspace(MINIMAL).dashboard("sales-overview")
    contract = dashboard.layout_contract

    assert contract.as_dict()["schema"] == "dataviz/layout-contract/v1"
    assert contract.mode == "declarative"
    assert [section.section_id for section in contract.sections] == [
        "pulse",
        "trend",
        "detail",
    ]
    assert [row.views for row in contract.sections[1].rows] == [
        ("revenue-trend", "region-comparison")
    ]
    assert [
        (item.view_id, item.span, item.source)
        for item in contract.sections[1].placements
    ] == [
        ("revenue-trend", 8, "view:revenue-trend.span"),
        ("region-comparison", 4, "view:region-comparison.span"),
    ]


def test_explicit_view_span_is_not_silently_overridden_by_section_template(
    tmp_path: Path,
):
    workspace_root = _copy_workspace(MINIMAL, tmp_path / "workspace")
    definition_path = _definition_path(workspace_root, "sales-overview")
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    trend = next(section for section in definition["sections"] if section["id"] == "trend")
    trend["template"] = "grid"
    revenue = next(view for view in definition["views"] if view["id"] == "revenue-trend")
    revenue["span"] = 5
    definition_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    dashboard = load_workspace(workspace_root).dashboard("sales-overview")
    placement = dashboard.layout_contract.placement("trend", "revenue-trend")

    assert placement is not None
    assert placement.span == 5
    assert placement.source == "view:revenue-trend.span"


def test_invalid_layout_is_reported_by_zero_query_validation(tmp_path: Path):
    workspace_root = _copy_workspace(MINIMAL, tmp_path / "workspace")
    definition_path = _definition_path(workspace_root, "sales-overview")
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["views"][0]["span"] = 13
    definition_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    diagnostics = validate_workspace(load_workspace(workspace_root))

    assert any(
        item.level == "error" and item.code == "layout_span_exceeds_columns"
        for item in diagnostics
    )


def test_presentation_structural_layout_fields_are_rejected(tmp_path: Path):
    workspace_root = _copy_workspace(MINIMAL, tmp_path / "workspace")
    presentation_path = (
        workspace_root / "dashboards" / "sales-overview" / "presentation.yaml"
    )
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation["layout"] = {"columns": 6}
    presentation["views"]["revenue-trend"]["span"] = 4
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    workspace = load_workspace(workspace_root)

    assert any(
        item.level == "error" and item.code == "presentation_invalid"
        for item in validate_workspace(workspace)
    )
    assert workspace.dashboard("sales-overview").presentation is None


def test_custom_canvas_contract_exposes_mount_points_without_fake_grid():
    dashboard = load_workspace(CUSTOM).dashboard("sales")
    contract = dashboard.layout_contract

    assert contract.mode == "custom"
    assert contract.sections == ()
    assert contract.mount_sections == ("pulse", "records")
    assert contract.mount_views == ("revenue", "target", "distribution", "detail")


def test_renderer_embeds_compiled_layout_contract():
    workspace = load_workspace(MINIMAL)
    dashboard = workspace.dashboard("sales-overview")
    html = CanvasRenderer(workspace).render(
        dashboard,
        Executor(workspace).run("sales-overview"),
    )

    assert '"schema": "dataviz/layout-contract/v1"' in html
    assert "--dv-span:8" in html
