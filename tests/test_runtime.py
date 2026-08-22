from __future__ import annotations

from pathlib import Path
import shutil

import yaml

from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer
from dataviz.workspace import compile_selection_contract, load_workspace, validate_workspace


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "examples" / "sales-workspace"


def test_workspace_is_valid():
    workspace = load_workspace(WORKSPACE)
    diagnostics = validate_workspace(workspace)
    assert not [item for item in diagnostics if item.level == "error"]
    assert set(workspace.dashboards["sales"].sources) == {"orders", "targets", "forecast"}


def test_workspace_uses_physical_names_for_renamed_copied_and_deleted_dashboards(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    original = root / "dashboards" / "sales"
    renamed = root / "dashboards" / "renamed-sales"
    original.rename(renamed)

    copied = root / "dashboards" / "copied-analysis"
    shutil.copytree(renamed, copied)
    copied_definition_path = copied / "dashboard.yaml"
    copied_definition = yaml.safe_load(copied_definition_path.read_text(encoding="utf-8"))
    copied_definition["id"] = "copied-analysis"
    copied_definition["title"] = "复制的分析"
    copied_definition_path.write_text(
        yaml.safe_dump(copied_definition, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    workspace_path = root / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition.setdefault("navigation", []).append(
        {"id": "deleted", "title": "已删除看板", "dashboard": "dashboards/deleted", "order": 20}
    )
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    workspace = load_workspace(root)
    entries = {entry.id: entry for entry in workspace.catalog}
    assert entries["sales"].status == "ready"
    assert entries["sales"].relative_path == "dashboards/renamed-sales"
    assert "deleted" not in entries
    assert entries["copied-analysis"].status == "ready"
    assert entries["copied-analysis"].discovered
    assert entries["copied-analysis"].canvas_name == "copied-analysis"
    assert entries["copied-analysis"].title == "复制的分析"
    assert workspace.dashboard("copied-analysis").definition.title == "复制的分析"

    renamed.rename(root / "dashboards" / "经营分析##renamed-sales")
    workspace = load_workspace(root)
    sales = next(entry for entry in workspace.catalog if entry.id == "sales")
    assert sales.logical_path == "经营分析/renamed-sales"
    assert sales.canvas_name == "renamed-sales"
    assert sales.parent_id is not None


def test_content_title_is_optional_and_falls_back_to_canvas_name(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    original = root / "dashboards" / "sales"
    renamed = root / "dashboards" / "经营分析##销售看板"
    original.rename(renamed)
    definition_path = renamed / "dashboard.yaml"
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition.pop("title", None)
    definition["subtitle"] = "华东经营专题"
    definition_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales")
    entry = next(item for item in workspace.catalog if item.id == "sales")
    assert dashboard.canvas_name == "销售看板"
    assert dashboard.title == "销售看板"
    assert dashboard.definition.subtitle == "华东经营专题"
    assert entry.canvas_name == "销售看板"
    assert entry.title == "销售看板"

    result = Executor(workspace).run("sales")
    dashboard.definition.canvas.template = None
    rendered = CanvasRenderer(workspace).render(dashboard, result)
    assert "<title>销售看板</title>" in rendered
    assert "<h1>销售看板</h1>" in rendered
    assert "华东经营专题" in rendered


def test_workspace_keeps_duplicate_and_invalid_dashboards_visible(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    shutil.copytree(root / "dashboards" / "sales", root / "dashboards" / "sales-copy")
    broken = root / "dashboards" / "broken"
    broken.mkdir()
    (broken / "dashboard.yaml").write_text("kind: [broken", encoding="utf-8")

    workspace = load_workspace(root)
    conflicts = [entry for entry in workspace.catalog if entry.status == "conflict"]
    assert len(conflicts) == 2
    assert all(entry.runnable for entry in conflicts)
    assert len({entry.id for entry in conflicts}) == 2
    invalid = next(entry for entry in workspace.catalog if entry.relative_path == "dashboards/broken")
    assert invalid.status == "invalid"
    assert not invalid.runnable
    assert any(item.code == "dashboard_id_conflict" for item in validate_workspace(workspace))


def test_query_all_three_source_types():
    workspace = load_workspace(WORKSPACE)
    executor = Executor(workspace)
    for source in ("orders", "targets", "forecast"):
        result = executor.run("sales", source_targets=[source])
        assert result.status == "success", result.model_dump_json(indent=2)
        node = result.nodes[f"source:{source}"]
        assert node.status == "succeeded"
        assert node.artifacts[0].kind == "table"


def test_default_run_queries_sources_only():
    workspace = load_workspace(WORKSPACE)
    result = Executor(workspace).run("sales")
    assert result.status == "success", result.model_dump_json(indent=2)
    assert set(result.nodes) == {"source:orders", "source:targets", "source:forecast"}
    assert result.outputs == {}


def test_three_level_selections_compile_and_do_not_invalidate_sources():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales")
    contract = compile_selection_contract(dashboard.definition)
    assert [item.origin for item in contract["revenue"]] == ["dashboard", "section"]
    assert [item.origin for item in contract["detail"]] == ["dashboard", "view"]

    executor = Executor(workspace)
    executor.run("sales")
    filtered = executor.run(
        "sales",
        selections={"region": ["North"], "min_revenue": 15000, "min_orders": 120},
    )
    assert filtered.status == "success"
    assert filtered.selections == {
        "dashboard:sales/region": ["North"],
        "section:pulse/min_revenue": 15000,
        "view:detail/min_orders": 120,
    }
    assert all(
        filtered.nodes[f"source:{source_id}"].result_origin == "cache"
        for source_id in ("orders", "targets", "forecast")
    )
    assert filtered.outputs == {}


def test_custom_canvas_and_report(tmp_path: Path):
    workspace = load_workspace(WORKSPACE)
    result = Executor(workspace).run("sales")
    renderer = CanvasRenderer(workspace)
    html = renderer.render(workspace.dashboard("sales"), result, asset_mode="server")
    assert "FIELD NOTE / 026" in html
    assert "dv-plotly" in html
    assert "dv-echarts" in html
    output = renderer.write_report(workspace.dashboard("sales"), result, tmp_path / "report.html")
    assert output.exists()
    assert output.with_suffix(".html.manifest.json").exists()
    report = output.read_text(encoding="utf-8")
    assert "Plotly" in report
    assert "PORTABLE ANALYSIS" in report
    assert "Query snapshot" in report
    assert "Dashboard selections" in report
    assert "Section selection" in report
    assert "View selection" in report
    assert 'data-selection-origin="section"' in report
    assert 'data-selection-origin="view"' in report
    assert "data-selection-input=\"dashboard:sales/region\"" in report
    assert "closeContextSelectionPopovers" in report
    assert "event.composedPath()" in report
    assert "pathContains('.dv-context-selections')" in report
    assert '"view_sources": {' in report
    assert "const refreshCascadingSelections = () =>" in report
    assert "[0, 1, 2].forEach(rank =>" in report
    assert "Commit each scope before deriving the next one" in report
    assert "const datavizPositionFloatingPanel =" in report
    assert "if (!activePath.length && selected.size)" in report
    assert "viewportWidth - gutter * 2" in report
    assert "option.selected = !option.disabled" in report
    assert "readSelectionInputs();\n  refreshCascadingSelections();\n  readSelectionInputs();" in report
    assert "const datavizAffectedViewIds = changedKeys =>" in report
    assert "changedSelectionKeys?.length === 0" in report
    assert "document.documentElement.dataset.selecting" not in report
    assert '"sources": {"orders": [' in report
    assert "window.datavizClient" in report
    assert "@perspective-dev/viewer@5.2.0" not in report
    assert "perspective-viewer-datagrid.js" not in report
    assert "perspective-viewer-charts.js" not in report
    assert "if (type === 'table')" in report
    assert "dv-widget--table" in report
    assert "renderPerspectiveInto" in report
    assert "const bindEchartsLegendInteraction =" in report
    assert "descriptor.legendInteraction !== 'filter'" in report
    assert "replaceMerge:['xAxis', 'series']" in report
    assert "table.replace(existing.latestRows)" in report


def test_report_selection_is_initial_state_not_an_export_cut(tmp_path: Path):
    workspace = load_workspace(WORKSPACE)
    result = Executor(workspace).run("sales", selections={"region": ["East"]})
    output = CanvasRenderer(workspace).write_report(
        workspace.dashboard("sales"), result, tmp_path / "interactive.html"
    )
    report = output.read_text(encoding="utf-8")
    assert '<option value="East" selected>' in report
    assert '<option value="West">' in report
    assert '"region": "West"' in report
    assert "PORTABLE ANALYSIS" in report
