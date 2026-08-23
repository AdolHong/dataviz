from pathlib import Path
import base64
import gzip
import json
import shutil

import pyarrow as pa
import yaml
import pytest
from pydantic import ValidationError

from dataviz.artifacts import ArtifactStore
from dataviz.cli import app
from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer, template_catalog
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.models import (
    DashboardDefinition,
    PresentationDefinition,
    SelectionDefinition,
    WorkspaceDefinition,
)
from dataviz.workspace.selections import compile_selection_contract
from dataviz.workspace.selector_templates import resolve_selector_presentation
from typer.testing import CliRunner


WORKSPACE = Path(__file__).parents[1] / "examples" / "minimal-workspace"
SALES_WORKSPACE = Path(__file__).parents[1] / "examples" / "sales-workspace"
REPEAT_WORKSPACE = Path(__file__).parents[1] / "examples" / "repeat-workspace"
SHOWCASE_WORKSPACE = Path(__file__).parents[1] / "examples" / "legacy-showcase"


def test_template_registry_is_ai_discoverable():
    catalog = template_catalog()

    assert {"metric", "line", "table", "perspective", "markdown"} <= set(catalog["views"])
    assert {"grid", "split", "chart-and-table", "band"} <= set(catalog["sections"])
    assert {"small-multiples", "selection-gallery"} <= set(catalog["sections"])
    result = CliRunner().invoke(app, ["templates"])
    assert result.exit_code == 0
    assert '"stacked-bar"' in result.stdout


def test_repeat_section_components_are_ai_discoverable():
    listing = CliRunner().invoke(app, ["components", "section.small-multiples", "--format", "json"])
    gallery = CliRunner().invoke(app, ["components", "section.selection-gallery", "--format", "json"])

    assert listing.exit_code == 0
    assert gallery.exit_code == 0
    assert json.loads(listing.stdout)["logic"]["template"] == "small-multiples"
    assert "cascader" in json.loads(gallery.stdout)["logic"]["selector_templates"]


def test_repeat_templates_share_one_dataset_and_render_dynamic_instances(tmp_path: Path):
    workspace = load_workspace(REPEAT_WORKSPACE)
    dashboard = workspace.dashboard("store-performance")
    diagnostics = validate_workspace(workspace)
    result = Executor(workspace).run("store-performance", refresh=True)
    artifact = result.nodes["source:store-sales"].outputs["main"]
    frame = ArtifactStore(workspace.root, result.run_id).read_table(artifact)
    renderer = CanvasRenderer(workspace)
    report = renderer.write_report(
        dashboard, result, tmp_path / "stores.html"
    ).read_text(encoding="utf-8")

    assert diagnostics == []
    assert set(result.nodes) == {"source:store-sales"}
    assert len(frame) == 1200
    assert frame["store_id"].nunique() == 100
    assert 'dv-section--small-multiples' in report
    assert 'dv-section--selection-gallery' in report
    assert 'data-repeat-section="all-stores"' in report
    assert 'data-cascader-view="selected-store-trend"' in report
    assert 'const datavizRepeatSpecs' in report
    assert 'const repeatObserver' in report
    assert 'class DatavizArrowOutput' in report
    assert '"encoding": "arrow-ipc"' in report
    assert '"row_count": 1200' in report
    assert 'dv-repeat-toolbar' in report
    assert 'recycle_offscreen' in report
    assert 'window.dataviz.renderRepeatedSection = renderRepeatedSection' in report
    assert '"by": ["store_id"]' in report
    assert '"store_id": "S001"' not in report

    bundle = renderer._portable_bundle(
        dashboard,
        result,
        ArtifactStore(workspace.root, result.run_id),
        asset_mode="inline",
    )
    descriptor = bundle["output_transports"]["source:store-sales/main"]
    compressed = b"".join(base64.b64decode(value) for value in descriptor["chunks"])
    table = pa.ipc.open_stream(gzip.decompress(compressed)).read_all()
    assert table.num_rows == 1200
    assert table.column_names == ["store_id", "store_name", "region", "city", "week", "revenue"]


def test_component_registry_has_human_and_ai_help():
    listing = CliRunner().invoke(app, ["components"])
    detail = CliRunner().invoke(app, ["components", "selector.cascader"])
    machine = CliRunner().invoke(
        app, ["components", "selector.cascader", "--format", "json"]
    )

    assert listing.exit_code == 0
    assert "selector.cascader" in listing.stdout
    assert detail.exit_code == 0
    assert "path_fields" in detail.stdout
    assert "Semantic DOM" in detail.stdout
    assert machine.exit_code == 0
    assert json.loads(machine.stdout)["presentation"]["template"] == "cascader"


def test_cli_docs_provide_onboarding_chart_recipes_and_error_recovery():
    listing = CliRunner().invoke(app, ["docs"])
    quickstart = CliRunner().invoke(app, ["docs", "quickstart"])
    charts = CliRunner().invoke(app, ["docs", "chart", "--format", "json"])
    search = CliRunner().invoke(app, ["docs", "--search", "Perspective"])
    failure = CliRunner().invoke(
        app, ["context", str(WORKSPACE), "missing-dashboard", "--format", "json"]
    )

    assert listing.exit_code == 0
    assert "dataviz docs quickstart" in listing.stdout
    assert "troubleshooting" in listing.stdout
    assert quickstart.exit_code == 0
    assert "dataviz query" in quickstart.stdout
    assert "不要从自定义 HTML/CSS/JS 开始" in quickstart.stdout
    runtime_docs = CliRunner().invoke(app, ["docs", "runtime-limits", "--format", "json"])
    assert runtime_docs.exit_code == 0
    assert "Arrow IPC" in runtime_docs.stdout
    assert "Web Worker" in runtime_docs.stdout
    assert charts.exit_code == 0
    chart_docs = json.loads(charts.stdout)
    assert chart_docs["topic"] == "charts"
    assert chart_docs["field_matrix"]["heatmap"]["required"] == ["input", "x", "y", "z"]
    strict = CliRunner().invoke(app, ["docs", "strict-schema", "--format", "json"])
    assert strict.exit_code == 0
    assert "不提供 deprecated 层" in json.loads(strict.stdout)["summary"]
    assert search.exit_code == 0
    assert "tables" in search.stdout
    assert failure.exit_code == 1
    failure_payload = json.loads(failure.stdout)
    assert failure_payload["help"]["command"] == "dataviz docs troubleshooting"


def test_init_creates_declarative_dashboard_without_frontend_scaffold(tmp_path: Path):
    destination = tmp_path / "workspace"
    result = CliRunner().invoke(app, ["init", str(destination)])
    workspace = load_workspace(destination)
    dashboard = workspace.dashboard("hello")

    assert result.exit_code == 0
    assert dashboard.definition.views[0].template == "bar"
    assert dashboard.definition.canvas.script is None
    assert not (dashboard.root / "canvas").exists()
    assert not (dashboard.root / "widgets").exists()
    assert validate_workspace(workspace) == []


def test_inline_sources_and_views_load_without_frontend_files():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")

    assert set(dashboard.sources) == {"sales"}
    assert set(dashboard.views) == {
        "total-revenue",
        "total-orders",
        "revenue-trend",
        "region-comparison",
        "sales-detail",
        "sales-perspective",
    }
    assert dashboard.definition.canvas.script is None
    assert dashboard.definition.canvas.style is None
    assert validate_workspace(workspace) == []


def test_optional_presentation_overrides_ids_without_changing_logic():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")

    assert dashboard.presentation is not None
    assert dashboard.logic_definition.theme.preset == "plain"
    assert all(section.template == "stack" for section in dashboard.logic_definition.sections)
    assert dashboard.definition.theme.preset == "business"
    assert [section.template for section in dashboard.definition.sections] == [
        "band",
        "split",
        "comparison",
    ]
    assert dashboard.presentation.views["revenue-trend"].span == 8
    assert dashboard.presentation.views["revenue-trend"].min_height == 420
    assert dashboard.definition.views[0].input == dashboard.logic_definition.views[0].input
    assert validate_workspace(workspace) == []


def test_selector_presentation_templates_are_visual_only():
    presentation = PresentationDefinition.model_validate(
        {
            "schema": "dataviz/presentation/v1",
            "dashboard": "sales-overview",
            "selectors": {
                "dashboard:sales-overview/region": {"template": "checkbox-group", "variant": "tags"},
                "view:sales-detail/product": {
                    "template": "select",
                    "search": "always",
                    "select_all_label": "Choose all",
                    "invert_label": "Invert values",
                    "show_unavailable": False,
                    "search_placeholder": "Search products…",
                    "css_class": "product-picker",
                },
            },
        }
    )

    assert presentation.selectors["dashboard:sales-overview/region"].template == "checkbox-group"
    assert presentation.selectors["dashboard:sales-overview/region"].variant == "tags"
    product = presentation.selectors["view:sales-detail/product"]
    assert product.template == "select"
    assert product.search == "always"
    assert product.select_all_label == "Choose all"
    assert product.invert_label == "Invert values"
    assert product.show_unavailable is False
    assert product.css_class == "product-picker"


def test_selector_auto_resolution_is_deterministic_and_unknown_names_are_rejected():
    choices = [{"label": str(index), "value": index} for index in range(9)]
    assert resolve_selector_presentation(
        SelectionDefinition(id="status", type="single_select", choices=choices[:4])
    )["template"] == "segmented"
    assert resolve_selector_presentation(
        SelectionDefinition(id="region", type="multi_select", choices=choices[:8])
    )["template"] == "checkbox-group"
    flat = resolve_selector_presentation(
        SelectionDefinition(id="store", type="multi_select", choices=choices)
    )
    assert flat["template"] == "select"
    assert flat["virtual"] == "auto"
    assert resolve_selector_presentation(
        SelectionDefinition(
            id="district",
            type="multi_select",
            path_fields=["province", "city", "district"],
        )
    )["template"] == "cascader"
    with pytest.raises(ValidationError):
        PresentationDefinition.model_validate(
            {
                "schema": "dataviz/presentation/v1",
                "dashboard": "sales-overview",
                "selectors": {"dashboard:sales-overview/region": {"template": "unknown"}},
            }
        )


def test_portable_selector_markup_supports_search_and_hidden_unavailable_options():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")
    definition = dashboard.definition.dashboard_selections[0]
    markup = CanvasRenderer(workspace)._portable_field(
        "dashboard:sales-overview/region",
        definition,
        definition.default,
        {
            "template": "select",
            "search": "always",
            "show_unavailable": False,
            "search_placeholder": "Search regions…",
            "empty_text": "No regions",
            "css_class": "region-picker",
        },
    )

    assert 'data-selector-template="select"' in markup
    assert 'data-search-mode="always"' in markup
    assert 'data-show-unavailable="false"' in markup
    assert 'data-search-placeholder="Search regions…"' in markup
    assert 'class="dv-selector region-picker"' in markup


def test_portable_cascader_declares_data_driven_path_levels():
    workspace = load_workspace(WORKSPACE)
    definition = SelectionDefinition(
        id="district",
        label="District",
        type="multi_select",
        path_fields=["province", "city", "district"],
        default=[],
    )
    markup = CanvasRenderer(workspace)._portable_field(
        "view:detail/district",
        definition,
        [],
        {
            "template": "cascader",
            "level_labels": ["Province", "City", "District"],
            "search_placeholder": "Search paths…",
        },
        "detail",
    )

    assert 'data-selector-template="cascader"' in markup
    assert 'data-cascader-view="detail"' in markup
    assert "province" in markup
    assert "Province" in markup


def test_showcase_view_selection_uses_data_driven_cascader():
    workspace = load_workspace(SHOWCASE_WORKSPACE)
    dashboard = workspace.dashboard("cascade-explorer")
    result = Executor(workspace).run("cascade-explorer")
    report = CanvasRenderer(workspace).render(dashboard, result)

    detail = dashboard.views["city-detail"]
    district = next(item for item in detail.selections if item.id == "district")
    assert district.path_fields == ["province", "city", "district"]
    assert 'data-selector-template="cascader"' in report
    assert 'data-cascader-view="city-detail"' in report


def test_presentation_is_included_in_ai_context():
    result = CliRunner().invoke(
        app, ["context", str(WORKSPACE), "sales-overview", "--format", "json"]
    )
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["dashboard_logic"]["theme"]["preset"] == "plain"
    assert payload["dashboard"]["theme"]["preset"] == "business"
    assert payload["presentation"]["dashboard"] == "sales-overview"
    assert payload["presentation_file"].endswith("presentation.yaml")


def test_stale_presentation_references_warn_and_do_not_break_dashboard(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    presentation_path = root / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation["views"]["deleted-view"] = {"span": 12}
    presentation["sections"]["deleted-section"] = {"template": "single"}
    presentation["selectors"] = {"view:deleted-view/region": {"template": "select"}}
    presentation["assets"]["css"].append("assets/missing.css")
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales-overview")
    diagnostics = validate_workspace(workspace)

    assert dashboard.definition.theme.preset == "business"
    assert not [item for item in diagnostics if item.level == "error"]
    assert {item.code for item in diagnostics} >= {
        "presentation_unknown_view",
        "presentation_unknown_section",
        "presentation_unknown_selector",
        "presentation_asset_missing",
    }


def test_invalid_presentation_falls_back_to_logic_definition(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    presentation_path = root / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation_path.write_text("views: [invalid", encoding="utf-8")

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales-overview")
    diagnostics = validate_workspace(workspace)

    assert dashboard.presentation is None
    assert dashboard.definition.theme.preset == "plain"
    assert not [item for item in diagnostics if item.level == "error"]
    assert any(item.code == "presentation_invalid" for item in diagnostics)


def test_presentation_can_place_file_based_views(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(SALES_WORKSPACE, root)
    dashboard_root = root / "dashboards" / "sales"
    (dashboard_root / "presentation.yaml").write_text(
        """schema: dataviz/presentation/v1
dashboard: sales
views:
  revenue:
    span: 9
    min_height: 360
    container: chart
""",
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales")
    revenue_layout = dashboard.presentation.views["revenue"]

    assert revenue_layout.span == 9
    assert revenue_layout.min_height == 360
    assert revenue_layout.container == "chart"
    assert not [
        item
        for item in validate_workspace(workspace)
        if item.code == "presentation_unknown_view"
    ]


def test_declarative_selection_contract_uses_field_binding():
    dashboard = load_workspace(WORKSPACE).dashboard("sales-overview")
    contract = compile_selection_contract(dashboard.definition)

    assert set(contract) == set(dashboard.views)
    assert all(selections[0].binding.field == "region" for selections in contract.values())
    assert all(selections[0].origin == "dashboard" for selections in contract.values())


def test_declarative_renderer_limits_selection_redraw_to_affected_views():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")
    result = Executor(workspace).run("sales-overview")
    rendered = CanvasRenderer(workspace).render(dashboard, result, asset_mode="server")

    assert "affected.has(id)" in rendered
    assert "affectedViews(changedSelectionKeys, changedOutputs)" in rendered
    assert "datavizRuntime.renderViews" in rendered
    assert "window.datavizClient" not in rendered


@pytest.mark.parametrize(
    "removed_fragment",
    [
        {"dashboard_filters": [{"id": "region"}]},
        {"sections": [{"id": "main", "title": "Main", "filters": []}]},
        {"canvas": {"client_filters": True}},
        {"layout": {"items": [{"widget": "detail"}]}},
        {"views": [{"id": "detail", "template": "table", "source": "sales"}]},
    ],
)
def test_removed_schema_fields_are_rejected(removed_fragment):
    with pytest.raises(ValidationError):
        DashboardDefinition.model_validate({"id": "strict", **removed_fragment})


@pytest.mark.parametrize("field", ["navigation", "trash"])
def test_removed_workspace_tree_fields_are_rejected(field):
    with pytest.raises(ValidationError):
        WorkspaceDefinition.model_validate(
            {"id": "strict", "title": "Strict", field: []}
        )


def test_selection_contract_is_include_only():
    with pytest.raises(ValidationError):
        SelectionDefinition.model_validate(
            {"id": "region", "type": "multi_select", "mode": "exclude"}
        )


def test_query_parameter_changes_inline_sql_dataset():
    workspace = load_workspace(WORKSPACE)
    result = Executor(workspace).run(
        "sales-overview", params={"min_query_revenue": 150000}, refresh=True
    )
    artifact = result.nodes["source:sales"].outputs["main"]
    frame = ArtifactStore(workspace.root, result.run_id).read_table(artifact)

    assert result.status == "success"
    assert frame["revenue"].tolist() == [151000, 164000]


def test_default_renderer_builds_templates_and_portable_report(tmp_path: Path):
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")
    result = Executor(workspace).run("sales-overview")
    renderer = CanvasRenderer(workspace)
    report_path = renderer.write_report(dashboard, result, tmp_path / "report.html")
    report = report_path.read_text(encoding="utf-8")

    assert "dv-section--band" in report
    assert "dv-section--split" in report
    assert "dv-theme--business" in report
    assert "presentation-kpi-band" in report
    assert "presentation-detail-table" in report
    assert "Optional presentation-only polish" in report
    assert "min-height:420px" in report
    assert "const datavizViewSpecs" in report
    assert '"schema": "dataviz/runtime/v1"' in report
    assert "window.datavizRuntime.registerView" in report
    assert "window.datavizClient" not in report
    assert '"source:sales/main": [' in report
    assert "dvSelectRows" in report
    assert "operator === 'gte'" in report
    assert "view.template === 'heatmap' ? [view.z]" in report
    assert "view.template === 'metric'" in report
    assert "dvPlotlyDescriptor" in report
    assert "createPerspectiveState" in report
    assert "updatePerspectiveState" in report
    assert "disposePerspectiveState" in report
    assert "state.mode === 'empty' && state.latestRows.length" in report
    assert "if (typeof state.viewer?.flush === 'function') await state.viewer.flush()" in report
    assert "setViewStatus(root, 'ready', 'perspective')" in report
    assert "viewer.delete" in report
    assert "@perspective-dev/viewer@5.2.0" in report
    assert '"template": "table"' in report
    assert "formatTableValue" in report
    assert "dv-table--striped" in report
    assert "releaseWheelAtBoundary(wrap)" in report
    assert "releaseWheelAtBoundary(viewer)" in report
    assert "event.composedPath()" in report
    assert "page.scrollTop += event.deltaY * multiplier" in report
    assert "overscroll-behavior:auto" in report
    assert "canvas/script.js" not in report
