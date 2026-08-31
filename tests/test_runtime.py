from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
import yaml
from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.execution import Executor
from dataviz.execution.fingerprint import ensure_query_run_compatible
from dataviz.errors import ExecutionFailure, WorkspaceError
from dataviz.plotly_runtime import (
    PLOTLY_JS_SHA256,
    PLOTLY_JS_VERSION,
    get_plotlyjs,
)
from dataviz.rendering import CanvasRenderer
from dataviz.workspace import compile_control_contract, load_workspace, validate_workspace


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "examples" / "sales-workspace"
SHOWCASE_WORKSPACE = ROOT / "examples" / "feature-showcase"


@pytest.fixture(scope="module", autouse=True)
def _isolate_repository_workspaces(isolated_workspace):
    global WORKSPACE, SHOWCASE_WORKSPACE
    WORKSPACE = isolated_workspace(WORKSPACE)
    SHOWCASE_WORKSPACE = isolated_workspace(SHOWCASE_WORKSPACE)


def test_workspace_is_valid():
    workspace = load_workspace(WORKSPACE)
    diagnostics = validate_workspace(workspace)
    assert not [item for item in diagnostics if item.level == "error"]
    assert set(workspace.dashboards["sales"].sources) == {"orders", "targets"}
    assert set(workspace.dashboards["sales"].dataset_transforms) == {"sales-metrics"}


def test_plotly_runtime_is_the_pinned_direct_browser_asset():
    source = get_plotlyjs()

    assert PLOTLY_JS_VERSION == "4.0.0"
    assert PLOTLY_JS_SHA256 == (
        "14461f3b4c91c8bb590a99d6d03c3fd031ca40eec07ebab79a5e3eac107cd7ca"
    )
    assert source.startswith("/**\n* plotly.js v4.0.0")


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

    workspace = load_workspace(root)
    entries = {entry.id: entry for entry in workspace.catalog}
    assert entries["sales"].status == "ready"
    assert entries["sales"].relative_path == "dashboards/renamed-sales"
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


def test_dashboard_lookup_accepts_only_the_stable_dashboard_id():
    workspace = load_workspace(WORKSPACE)

    assert workspace.dashboard("sales").definition.id == "sales"
    with pytest.raises(WorkspaceError, match="Unknown dashboard"):
        workspace.dashboard("dashboards/sales")


def test_partial_report_omits_machine_local_debug_details(tmp_path: Path):
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales")
    result = Executor(workspace).run("sales")
    node = result.nodes["source:orders"]
    node.status = "error"
    node.error = {
        "code": "simulated_failure",
        "message": f"Failed in {workspace.root / 'private' / 'query.sql'}",
        "file": str(workspace.root / "private" / "query.sql"),
        "traceback": f"Traceback from {Path.home() / 'private-module.py'}",
        "log": {"path": str(workspace.root / ".dataviz" / "runs" / "secret.log")},
        "details": {
            "traceback": f"Nested traceback from {Path.home()}",
            "resolved_path": str(workspace.root / "private" / "query.sql"),
        },
    }
    node.outputs = {}
    result.outputs = {
        reference: artifact
        for reference, artifact in result.outputs.items()
        if not reference.startswith("source:orders/")
    }
    result.status = "partial"
    output = tmp_path / "partial.html"

    CanvasRenderer(workspace).write_report(dashboard, result, output)

    html = output.read_text(encoding="utf-8")
    manifest = output.with_suffix(".html.manifest.json").read_text(encoding="utf-8")
    for content in (html, manifest):
        assert str(workspace.root) not in content
        assert str(Path.home()) not in content
        assert "Traceback from" not in content
        assert "secret.log" not in content
        assert "debug_details_omitted" in content
        assert "simulated_failure" in content


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
    definition["canvas"]["template"] = None
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
    assert all(not entry.runnable for entry in conflicts)
    assert len({entry.id for entry in conflicts}) == 2
    assert "sales" not in workspace.dashboards
    invalid = next(entry for entry in workspace.catalog if entry.relative_path == "dashboards/broken")
    assert invalid.status == "invalid"
    assert not invalid.runnable
    conflicts = [
        item
        for item in validate_workspace(workspace)
        if item.code == "dashboard_id_conflict"
    ]
    assert len(conflicts) == 2
    assert all(item.level == "error" for item in conflicts)


def test_invalid_workspace_in_a_unicode_folder_uses_a_safe_fallback_id(tmp_path: Path):
    root = tmp_path / "中文 Workspace"
    root.mkdir()
    workspace = load_workspace(root)

    assert workspace.definition.id.startswith("workspace_")
    assert workspace.definition.title == "中文 Workspace"
    assert any(
        item.code == "workspace_definition_invalid"
        for item in workspace.load_diagnostics
    )


def test_query_targets_and_all_three_source_types():
    workspace = load_workspace(WORKSPACE)
    executor = Executor(workspace)
    for source in ("orders", "targets"):
        result = executor.run("sales", targets=[f"source:{source}/main"])
        assert result.status == "ready", result.model_dump_json(indent=2)
        node = result.nodes[f"source:{source}"]
        assert node.status == "ready"
        assert node.outputs["main"].kind == "table"

    showcase = load_workspace(SHOWCASE_WORKSPACE)
    assert showcase.dashboard("cascade-explorer").sources["bundled-file"][1].type == "file"
    assert showcase.dashboard("source-lab").sources["sql-grid"][1].type == "sql"
    assert showcase.dashboard("source-lab").sources["forecast"][1].type == "python"


def test_targeted_query_run_tracks_only_its_original_dependency_closure(
    tmp_path: Path,
):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    workspace = load_workspace(root)
    result = Executor(workspace).run("sales", targets=["source:orders"])

    assert result.query_scope == "targets"
    assert result.query_targets == ["source:orders"]
    assert result.query_nodes == ["source:orders"]

    unrelated_sql = root / "dashboards" / "sales" / "sources" / "targets.sql"
    unrelated_sql.write_text(
        unrelated_sql.read_text(encoding="utf-8") + "\n-- unrelated edit\n",
        encoding="utf-8",
    )
    ensure_query_run_compatible(load_workspace(root).dashboard("sales"), result)

    source_path = root / "dashboards" / "sales" / "sources" / "orders.yaml"
    source = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    source["options"] = {"keep_default_na": False}
    source_path.write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    with pytest.raises(ExecutionFailure) as failure:
        ensure_query_run_compatible(load_workspace(root).dashboard("sales"), result)
    assert failure.value.details["code"] == "query_run_contract_changed"


def test_missing_query_asset_returns_a_stable_contract_error(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    result = Executor(load_workspace(root)).run(
        "sales", targets=["source:targets"]
    )
    (root / "dashboards" / "sales" / "sources" / "targets.sql").unlink()

    with pytest.raises(ExecutionFailure) as failure:
        ensure_query_run_compatible(load_workspace(root).dashboard("sales"), result)

    assert failure.value.details["code"] == "query_run_contract_changed"
    assert failure.value.details["action"].startswith("Run dataviz validate")


def test_default_run_executes_sources_and_dataset_transforms():
    workspace = load_workspace(WORKSPACE)
    result = Executor(workspace).run("sales")
    assert result.status == "ready", result.model_dump_json(indent=2)
    assert set(result.nodes) == {
        "source:orders",
        "source:targets",
        "dataset:sales-metrics",
    }
    assert set(result.outputs) == {
        "source:orders/main",
        "source:targets/main",
        "dataset:sales-metrics/trend",
        "dataset:sales-metrics/completion",
    }


def test_three_level_controls_are_browser_state_and_do_not_enter_query_run():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales")
    contract = compile_control_contract(dashboard.definition)
    assert [item.origin for item in contract["revenue"]] == ["dashboard", "section"]
    assert [item.origin for item in contract["detail"]] == ["dashboard", "view"]

    executor = Executor(workspace)
    executor.run("sales")
    filtered = executor.run("sales")
    assert filtered.status == "ready"
    assert not hasattr(filtered, "selections")
    assert all(
        filtered.nodes[f"source:{source_id}"].result_origin == "cache"
        for source_id in ("orders", "targets")
    )
    assert filtered.nodes["dataset:sales-metrics"].result_origin == "cache"

    report = CanvasRenderer(workspace).render(
        dashboard,
        filtered,
        control_state={
            "dashboard:sales/region": {
                "intent": "explicit",
                "value": ["North"],
                "revision": 1,
            },
            "section:pulse/min_revenue": {
                "value": 15000,
                "revision": 1,
            },
            "view:detail/min_orders": {
                "value": 120,
                "revision": 1,
            },
        },
    )
    assert '"dashboard:sales/region": {"value": ["North"], "revision": 1, "intent": "explicit"}' in report


def test_custom_canvas_and_report(tmp_path: Path):
    workspace = load_workspace(WORKSPACE)
    result = Executor(workspace).run("sales")
    renderer = CanvasRenderer(workspace)
    html = renderer.render(workspace.dashboard("sales"), result, asset_mode="server")
    assert "CUSTOM CANVAS" in html
    assert "dv-plotly" in html
    assert '<script src="/static/tanstack-table-runtime.js"></script>' in html
    assert '<script src="/runtime/plotly.js"></script>' in html
    output = renderer.write_report(workspace.dashboard("sales"), result, tmp_path / "report.html")
    assert output.exists()
    manifest_path = output.with_suffix(".html.manifest.json")
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["portable_without_network"] is True
    assert manifest["portability_scope"] == "declared-runtime-and-view-assets"
    assert manifest["network_dependencies"] == []
    report = output.read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in report
    assert "@import url(" not in report
    assert '"tanstack_table": "9.2.4"' in report
    assert '"plotly_js": "4.0.0"' in report
    assert "plotly.js v4.0.0" in report
    assert "globalThis.datavizTanStackTable" in report
    assert "PORTABLE ANALYSIS" not in report
    assert ">Query snapshot<" not in report
    assert 'data-runtime-query-toggle' in report
    assert 'id="dv-runtime-query-panel"' in report
    assert 'class="dv-runtime-query-tray dv-query-card-host"' in report
    assert 'aria-expanded="false"' in report
    assert 'data-control-panel-body hidden' in report
    assert '<div class="dv-runtime-brand dv-shell-brand" aria-label="Dataviz">' in report
    assert '</nav></header><section class="dv-runtime-query-tray dv-query-card-host"' in report
    assert 'class="query-run-control dv-runtime-query-run-control"' in report
    assert "PARAMETERS" not in report
    assert 'class="dv-runtime-shell"' not in report
    assert report.count('name="dv-runtime-header-control"') == 1
    assert report.count('data-overlay-group="runtime-header"') == 1
    assert "--dv-shell-bg: #ffffff" in report
    assert "background: var(--dv-header-bg)" not in report[
        report.index(".dv-runtime-header {") : report.index(".dv-runtime-actions")
    ]
    assert "data-dv-control-panel" in report
    assert 'data-control-role="dashboard"' in report
    assert 'data-control-role="dashboard" data-control-count="1" data-control-template="stack"' in report
    assert 'data-control-column-width="240"' in report
    assert "Section controls" in report
    assert "View controls" in report
    assert "Section controls</strong><small>" not in report
    assert "View controls</strong><small>" not in report
    assert 'data-control-origin="section"' in report
    assert 'data-control-origin="view"' in report
    assert "data-control-state-input=\"dashboard:sales/region\"" in report
    assert 'data-component-package="runtime.overlay"' in report
    assert "installDatavizOverlay" in report
    assert "typeof event.composedPath === 'function'" in report
    assert "root.overlay = {register, registerDetails, hydrate, open, close, closeAll" in report
    assert "if (isOpen(record)) open(record);" in report
    assert "routeDatavizCanvasWheelToShell" in report
    assert "shellTop < shellMax - 1" in report
    assert "canvasTop <= 1 && shellTop > 1" in report
    assert '"dependency_contract": {' in report
    assert '"views": {"revenue": {"inputs":' in report
    assert "const refreshControlOptionDomains = () =>" in report
    assert "dependency_contract?.control_order" in report
    assert "dependency_ancestors" in report
    assert "Commit each compiled Control" in report
    assert "function position(record)" in report
    assert "if (!activePath.length && selectedValues.size)" in report
    assert "viewport.width - gutter * 2" in report
    assert "record.panel.getBoundingClientRect().height" in report
    assert "option.selected = !option.selected;" in report
    assert "dv-checkbox-group__toolbar" not in report
    assert "normalizeAll" not in report
    assert "await datavizRuntime.runTransforms(changed, [], {" in report
    assert "changedControlKeys:changed || Object.keys(current)" in report
    assert "if (!relevant && missingOutput && this.activeTransforms.has(id)) return;" in report
    assert "refreshControlOptionDomains();\n  readControlInputs(" in report
    assert "affectedViews(changed, new Set())" in report
    assert "changedControlKeys == null" in report
    assert "datavizControlCanApply" in report
    assert "dataset does not expose the selected field" in report
    assert "state.control.state(controlKey)" in report
    assert "document.documentElement.dataset.selecting" not in report
    assert '"source:orders/main": [' in report
    assert '"dataset:sales-metrics/trend": [' in report
    assert "runtime.registerView(view.id" in report
    assert "window.datavizClient" not in report
    assert "@perspective-dev/viewer@5.2.0" not in report
    assert "perspective-viewer-datagrid.js" not in report
    assert "perspective-viewer-charts.js" not in report
    assert "runtime.registerRenderer('table'" in report
    assert "context.tables.tanstack" not in report
    assert "global.dataviz.tables = tableService" in report
    assert "const mountTanStackTable" in report
    assert "renderPlainTable" not in report
    assert "runtime.registerRenderer('perspective'" in report
    assert "dv-view--table" in report
    assert "const createPerspective" in report
    assert "const syncPlotlyInteractions =" in report
    assert "plotly_selected" in report
    assert "plotly_doubleclick" in report
    assert "state.table.replace(state.latestRows)" in report


def test_declarative_charts_load_the_plotly_runtime():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales")
    result = Executor(workspace).run("sales")

    html = CanvasRenderer(workspace).render(dashboard, result, asset_mode="server")

    assert '<script src="/runtime/plotly.js"></script>' in html


def test_report_cli_exposes_the_scoped_portability_claim(tmp_path: Path):
    output = tmp_path / "report.html"
    result = CliRunner().invoke(
        app,
        [
            "report",
            str(WORKSPACE),
            "sales",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["portability_scope"] == "declared-runtime-and-view-assets"


def test_report_control_is_initial_state_not_an_export_cut(tmp_path: Path):
    workspace = load_workspace(WORKSPACE)
    result = Executor(workspace).run("sales")
    output = CanvasRenderer(workspace).write_report(
        workspace.dashboard("sales"),
        result,
        tmp_path / "interactive.html",
        control_state={
            "dashboard:sales/region": {
                "intent": "explicit",
                "value": ["East"],
                "revision": 1,
            }
        },
    )
    report = output.read_text(encoding="utf-8")
    assert '<option value="East" selected>' in report
    assert '<option value="West">' in report
    assert '"region": "West"' in report
    assert "PORTABLE ANALYSIS" not in report
