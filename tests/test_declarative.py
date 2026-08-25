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
from dataviz.errors import ValidationFailure
from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer, template_catalog
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.models import (
    ComputeControlDefinition,
    DashboardDefinition,
    InteractiveTransformDefinition,
    PresentationDefinition,
    PresentationControlComponentDefinition,
    QueryParameterDefinition,
    SelectionControlDefinition,
    WorkspaceDefinition,
)
from dataviz.workspace.controls import compile_control_contract
from dataviz.workspace.control_components import resolve_control_component
from typer.testing import CliRunner


WORKSPACE = Path(__file__).parents[1] / "examples" / "minimal-workspace"
SALES_WORKSPACE = Path(__file__).parents[1] / "examples" / "sales-workspace"
REPEAT_WORKSPACE = Path(__file__).parents[1] / "examples" / "repeat-workspace"
SHOWCASE_WORKSPACE = Path(__file__).parents[1] / "examples" / "feature-showcase"


@pytest.fixture(scope="module", autouse=True)
def _isolate_repository_workspaces(isolated_workspace):
    global WORKSPACE, SALES_WORKSPACE, REPEAT_WORKSPACE, SHOWCASE_WORKSPACE
    WORKSPACE = isolated_workspace(WORKSPACE)
    SALES_WORKSPACE = isolated_workspace(SALES_WORKSPACE)
    REPEAT_WORKSPACE = isolated_workspace(REPEAT_WORKSPACE)
    SHOWCASE_WORKSPACE = isolated_workspace(SHOWCASE_WORKSPACE)


def test_template_registry_is_ai_discoverable():
    catalog = template_catalog()

    assert {"metric", "line", "table", "perspective", "markdown"} <= set(catalog["views"])
    assert {"grid", "split", "chart-and-table", "band"} <= set(catalog["sections"])
    assert {"small-multiples", "selection-gallery"} <= set(catalog["sections"])
    result = CliRunner().invoke(app, ["components", "--format", "json"])
    assert result.exit_code == 0
    assert "view.stacked-bar" in json.loads(result.stdout)


def test_repeat_section_components_are_ai_discoverable():
    listing = CliRunner().invoke(app, ["components", "section.small-multiples", "--format", "json"])
    gallery = CliRunner().invoke(app, ["components", "section.selection-gallery", "--format", "json"])

    assert listing.exit_code == 0
    assert gallery.exit_code == 0
    assert json.loads(listing.stdout)["logic"]["template"] == "small-multiples"
    assert "control.cascader" in json.loads(gallery.stdout)["logic"]["recommended_components"]


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
    assert "global.dataviz?.repeat_specs" in report
    assert "typeof IntersectionObserver === 'undefined'" in report
    assert 'class DatavizArrowOutput' in report
    assert '"encoding": "arrow-ipc"' in report
    assert '"row_count": 1200' in report
    assert 'dv-repeat-toolbar' in report
    assert 'recycle_offscreen' in report
    assert "global.dataviz.renderRepeatedSection = renderRepeated" in report
    assert 'data-component-package="section.declarative"' in report
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
    detail = CliRunner().invoke(app, ["components", "control.cascader"])
    machine = CliRunner().invoke(
        app, ["components", "control.cascader", "--format", "json"]
    )

    assert listing.exit_code == 0
    assert "control.cascader" in listing.stdout
    assert detail.exit_code == 0
    assert "path_fields" in detail.stdout
    assert "Semantic DOM" in detail.stdout
    assert machine.exit_code == 0
    assert json.loads(machine.stdout)["presentation"]["component"] == "cascader"


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
    interpolation = CliRunner().invoke(
        app, ["docs", "interpolation", "--format", "json"]
    )
    assert interpolation.exit_code == 0
    interpolation_docs = json.loads(interpolation.stdout)
    assert interpolation_docs["topic"] == "dashboard"
    assert interpolation_docs["content_interpolation"]["parameter_syntax"] == (
        "{{ parameters.<id> }}"
    )
    assert "最近一次 Run query" in (
        interpolation_docs["content_interpolation"]["lifecycle"]["query_parameter"]
    )
    assert interpolation_docs["content_interpolation"]["control_syntax"]["section"] == (
        "{{ controls.section.<section-id>.<control-id> }}"
    )
    assert "即时更新" in (
        interpolation_docs["content_interpolation"]["lifecycle"]["selection_control"]
    )
    runtime_docs = CliRunner().invoke(app, ["docs", "runtime-limits", "--format", "json"])
    assert runtime_docs.exit_code == 0
    assert "Arrow IPC" in runtime_docs.stdout
    assert "Web Worker" in runtime_docs.stdout
    assert charts.exit_code == 0
    chart_docs = json.loads(charts.stdout)
    assert chart_docs["topic"] == "charts"
    assert chart_docs["field_matrix"]["heatmap"]["required"] == ["input", "x", "y", "z"]
    assert chart_docs["field_matrix"]["radar"]["required"] == [
        "input",
        "label",
        "columns",
    ]
    assert chart_docs["field_matrix"]["radar"]["engine"] == "echarts"
    strict = CliRunner().invoke(app, ["docs", "strict-schema", "--format", "json"])
    assert strict.exit_code == 0
    assert "不提供 deprecated 层" in json.loads(strict.stdout)["summary"]
    assert search.exit_code == 0
    assert "tables" in search.stdout
    assert failure.exit_code == 1
    failure_payload = json.loads(failure.stdout)
    assert failure_payload["help"]["command"] == "dataviz docs troubleshooting"


def test_cli_docs_publish_machine_readable_design_language_contract():
    result = CliRunner().invoke(app, ["docs", "visual", "--format", "json"])

    assert result.exit_code == 0
    topic = json.loads(result.stdout)
    assert topic["topic"] == "design-language"
    assert topic["default_direction"]["default_preset"] == "business"
    assert topic["core_tokens"]["surfaces"]["--dv-overlay-surface"].startswith(
        "必须不透明"
    )
    assert topic["core_tokens"]["semantic"]["--dv-green"].startswith("Ready")
    assert topic["customization_order"][0].startswith("先选择")
    assert "schema: dataviz/presentation/v1" in topic["presentation_example"]
    PresentationDefinition.model_validate(yaml.safe_load(topic["presentation_example"]))
    assert "--dv-chart-1" in topic["css_example"]
    assert any("Perspective" in item for item in topic["acceptance_checklist"])


def test_init_creates_declarative_dashboard_without_frontend_scaffold(tmp_path: Path):
    destination = tmp_path / "workspace"
    result = CliRunner().invoke(app, ["init", str(destination)])
    workspace = load_workspace(destination)
    dashboard = workspace.dashboard("hello")

    assert result.exit_code == 0
    assert dashboard.definition.views[0].template == "bar"
    assert dashboard.definition.canvas.scripts == []
    assert not (dashboard.root / "canvas").exists()
    assert not (dashboard.root / "widgets").exists()
    assert (destination / "auth" / "adapters.yaml").read_text(encoding="utf-8") == "adapters: {}\n"
    assert "auth/adapters.local.yaml" in (destination / ".gitignore").read_text(
        encoding="utf-8"
    )
    assert validate_workspace(workspace) == []


def test_query_cli_reads_an_explicit_named_source_output():
    result = CliRunner().invoke(
        app,
        [
            "query",
            str(WORKSPACE),
            "sales-overview",
            "--source",
            "sales",
            "--output-name",
            "main",
            "--limit",
            "1",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["reference"] == "source:sales/main"
    assert len(payload["value"]) == 1
    assert payload["truncated"] is True


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
    assert dashboard.definition.canvas.scripts == []
    assert dashboard.definition.canvas.styles == ["assets/presentation.css"]
    assert validate_workspace(workspace) == []


def test_local_image_view_assets_are_validated_and_embedded(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    dashboard_root = root / "dashboards" / "sales-overview"
    definition_path = dashboard_root / "dashboard.yaml"
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["views"].append(
        {
            "id": "local-image",
            "title": "Local image",
            "template": "image",
            "url": "assets/local.svg",
        }
    )
    definition["sections"].append(
        {"id": "image", "title": "Image", "views": ["local-image"]}
    )
    definition_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    image_path = dashboard_root / "assets" / "local.svg"
    image_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>',
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales-overview")
    views, _ = CanvasRenderer(workspace)._declarative_manifest(
        dashboard, dashboard.definition
    )
    image = next(item for item in views if item["id"] == "local-image")

    assert image["url"].startswith("data:image/svg+xml;base64,")
    assert validate_workspace(workspace) == []
    result = Executor(workspace).run("sales-overview")
    report = CanvasRenderer(workspace).write_report(
        dashboard, result, tmp_path / "local-image-report.html"
    )
    report_text = report.read_text(encoding="utf-8")
    manifest = json.loads(
        report.with_suffix(".html.manifest.json").read_text(encoding="utf-8")
    )
    assert image["url"] in report_text
    assert not [
        item
        for item in manifest["network_dependencies"]
        if item["library"] == "view-image:local-image"
    ]

    image_path.unlink()
    broken = load_workspace(root)
    entry = next(item for item in broken.catalog if item.canvas_name == "sales-overview")
    assert entry.status == "invalid"
    assert "does not exist" in (entry.message or "")


def test_remote_image_view_is_declared_as_report_network_dependency(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    dashboard_root = root / "dashboards" / "sales-overview"
    definition_path = dashboard_root / "dashboard.yaml"
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["views"].append(
        {
            "id": "remote-image",
            "title": "Remote image",
            "template": "image",
            "url": "https://assets.example.test/chart.png",
        }
    )
    definition["sections"].append(
        {"id": "remote", "title": "Remote", "views": ["remote-image"]}
    )
    definition_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales-overview")
    result = Executor(workspace).run("sales-overview")
    report = CanvasRenderer(workspace).write_report(
        dashboard, result, tmp_path / "remote-image-report.html"
    )
    manifest = json.loads(
        report.with_suffix(".html.manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["portable_without_network"] is False
    assert manifest["portability_scope"] == "declared-runtime-and-view-assets"
    assert {
        (item["library"], item["source"])
        for item in manifest["network_dependencies"]
    } >= {
        ("view-image:remote-image", "https://assets.example.test/chart.png")
    }


def test_optional_presentation_overrides_ids_without_changing_logic():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")

    assert dashboard.presentation is not None
    assert dashboard.logic_definition.theme.preset == "business"
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


def test_presentation_cannot_inject_fields_ignored_by_a_view_template(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    presentation_path = root / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation["views"]["sales-detail"]["config"] = {"plugin": "Datagrid"}
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales-overview")
    diagnostics = validate_workspace(workspace)

    assert dashboard.views["sales-detail"].config == {}
    assert any(
        item.level == "error"
        and item.code == "presentation_view_contract_invalid"
        and "does not use fields: config" in item.message
        for item in diagnostics
    )


def test_control_component_presentation_is_visual_only():
    presentation = PresentationDefinition.model_validate(
        {
            "schema": "dataviz/presentation/v1",
            "dashboard": "sales-overview",
            "control_components": {
                "dashboard:sales-overview/region": {"component": "checkbox-group"},
                "view:sales-detail/product": {
                    "component": "select",
                    "search": "always",
                    "select_all_label": "Choose all",
                    "invert_label": "Invert values",
                    "show_unavailable": False,
                    "search_placeholder": "Search products…",
                    "css_class": "product-picker",
                },
            },
            "control_panels": {
                "query": {
                    "template": "grid",
                    "width": "wide",
                    "columns": 3,
                    "density": "compact",
                },
                "dashboard": {
                    "template": "stack",
                    "width": "regular",
                },
            },
        }
    )

    assert presentation.control_components["dashboard:sales-overview/region"].component == "checkbox-group"
    product = presentation.control_components["view:sales-detail/product"]
    assert product.component == "select"
    assert product.search == "always"
    assert product.select_all_label == "Choose all"
    assert product.invert_label == "Invert values"
    assert product.show_unavailable is False
    assert product.css_class == "product-picker"
    assert presentation.control_panels.query.template == "grid"
    assert presentation.control_panels.query.columns == 3
    assert presentation.control_panels.query.density == "compact"
    assert presentation.control_panels.dashboard.template == "stack"

    with pytest.raises(ValidationError):
        PresentationDefinition.model_validate(
            {
                "schema": "dataviz/presentation/v1",
                "dashboard": "sales-overview",
                "control_panels": {"query": {"template": "stack", "columns": 2}},
            }
        )


def test_control_component_auto_resolution_is_deterministic_and_unknown_names_are_rejected():
    choices = [{"label": str(index), "value": index} for index in range(9)]
    assert resolve_control_component(
        SelectionControlDefinition(
            id="status", kind="selection", type="single_select",
            options={"mode": "static", "choices": choices[:4]},
        )
    )["component"] == "radio-group"
    assert resolve_control_component(
        SelectionControlDefinition(
            id="region", kind="selection", type="multi_select",
            options={"mode": "static", "choices": choices[:8]},
        )
    )["component"] == "checkbox-group"
    flat = resolve_control_component(
        SelectionControlDefinition(
            id="store", kind="selection", type="multi_select",
            options={"mode": "static", "choices": choices},
        )
    )
    assert flat["component"] == "select"
    assert flat["virtual"] == "auto"
    assert resolve_control_component(
        SelectionControlDefinition(
            id="district",
            kind="selection",
            type="multi_select",
            path_fields=["province", "city", "district"],
            options={"mode": "infer"},
        )
    )["component"] == "cascader"
    with pytest.raises(ValidationError):
        PresentationDefinition.model_validate(
            {
                "schema": "dataviz/presentation/v1",
                "dashboard": "sales-overview",
                "control_components": {
                    "dashboard:sales-overview/region": {"component": "unknown"}
                },
            }
        )


@pytest.mark.parametrize(
    ("definition", "configured", "expected"),
    [
        (QueryParameterDefinition(id="note", type="string"), None, "input"),
        (
            QueryParameterDefinition(
                id="scenario",
                type="string",
                suggestions=[{"label": "Base", "value": "base"}],
            ),
            None,
            "auto-complete",
        ),
        (ComputeControlDefinition(id="count", kind="compute", type="integer"), None, "input-number"),
        (ComputeControlDefinition(id="enabled", kind="compute", type="boolean"), None, "checkbox"),
        (
            ComputeControlDefinition(id="live", kind="compute", type="boolean"),
            PresentationControlComponentDefinition(component="switch"),
            "switch",
        ),
        (
            SelectionControlDefinition(
                id="mode",
                kind="selection",
                type="single_select",
                options={"mode": "static", "choices": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]},
            ),
            None,
            "radio-group",
        ),
        (
            SelectionControlDefinition(
                id="store",
                kind="selection",
                type="single_select",
                options={"mode": "static", "choices": [{"label": str(index), "value": index} for index in range(5)]},
            ),
            None,
            "select",
        ),
        (
            SelectionControlDefinition(
                id="regions",
                kind="selection",
                type="multi_select",
                options={"mode": "static", "choices": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]},
            ),
            None,
            "checkbox-group",
        ),
        (
            SelectionControlDefinition(
                id="district",
                kind="selection",
                type="multi_select",
                path_fields=["province", "city", "district"],
                options={"mode": "infer"},
            ),
            None,
            "cascader",
        ),
        (
            SelectionControlDefinition(
                id="tree",
                kind="selection",
                type="multi_select",
                path_fields=["province", "city"],
                options={"mode": "infer"},
            ),
            PresentationControlComponentDefinition(component="tree-select"),
            "tree-select",
        ),
        (QueryParameterDefinition(id="day", type="date"), None, "date-picker"),
        (QueryParameterDefinition(id="period", type="date_range"), None, "range-picker"),
        (
            ComputeControlDefinition(id="threshold", kind="compute", type="number"),
            PresentationControlComponentDefinition(component="slider"),
            "slider",
        ),
    ],
)
def test_every_data_entry_component_has_one_strict_value_semantics(
    definition, configured, expected
):
    resolved = resolve_control_component(definition, configured)
    assert resolved["component"] == expected
    assert "template" not in resolved


def test_data_entry_components_reject_semantically_incompatible_configuration():
    with pytest.raises(ValueError, match="select cannot render control type string"):
        resolve_control_component(
            QueryParameterDefinition(id="note", type="string"),
            PresentationControlComponentDefinition(component="select"),
        )
    with pytest.raises(ValueError, match="auto-complete requires suggestions"):
        resolve_control_component(
            QueryParameterDefinition(id="scenario", type="string"),
            PresentationControlComponentDefinition(component="auto-complete"),
        )
    with pytest.raises(ValueError, match="require cascader or tree-select"):
        resolve_control_component(
            SelectionControlDefinition(
                id="district",
                kind="selection",
                type="multi_select",
                path_fields=["province", "city", "district"],
                options={"mode": "infer"},
            ),
            PresentationControlComponentDefinition(component="select"),
        )
    with pytest.raises(ValidationError, match="does not accept presentation options"):
        PresentationControlComponentDefinition(component="radio-group", search="always")


def test_portable_control_markup_supports_search_and_hidden_unavailable_options():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")
    definition = dashboard.definition.controls[0]
    markup = CanvasRenderer(workspace)._portable_field(
        "dashboard:sales-overview/region",
        definition,
        definition.default,
        {
            "component": "select",
            "search": "always",
            "show_unavailable": False,
            "search_placeholder": "Search regions…",
            "empty_text": "No regions",
            "css_class": "region-picker",
        },
    )

    assert 'data-control-component="select"' in markup
    assert 'data-search-mode="always"' in markup
    assert 'data-show-unavailable="false"' in markup
    assert 'data-search-placeholder="Search regions…"' in markup
    assert 'class="dv-control region-picker"' in markup


def test_portable_cascader_declares_data_driven_path_levels():
    workspace = load_workspace(WORKSPACE)
    definition = SelectionControlDefinition(
        id="district",
        kind="selection",
        label="District",
        type="multi_select",
        path_fields=["province", "city", "district"],
        options={"mode": "infer"},
    )
    markup = CanvasRenderer(workspace)._portable_field(
        "view:detail/district",
        definition,
        [],
        {
            "component": "cascader",
            "level_labels": ["Province", "City", "District"],
            "search_placeholder": "Search paths…",
        },
        "detail",
    )

    assert 'data-control-component="cascader"' in markup
    assert 'data-cascader-view="detail"' in markup
    assert "province" in markup
    assert "Province" in markup


def test_showcase_view_selection_uses_data_driven_cascader():
    workspace = load_workspace(SHOWCASE_WORKSPACE)
    dashboard = workspace.dashboard("cascade-explorer")
    result = Executor(workspace).run("cascade-explorer")
    report = CanvasRenderer(workspace).render(dashboard, result)

    detail = dashboard.views["city-detail"]
    district = next(item for item in detail.controls if item.id == "district")
    assert district.path_fields == ["province", "city", "district"]
    assert 'data-control-component="cascader"' in report
    assert 'data-cascader-view="city-detail"' in report


def test_presentation_is_included_in_ai_context():
    result = CliRunner().invoke(
        app, ["context", str(WORKSPACE), "sales-overview", "--format", "json"]
    )
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["dashboard_logic"]["theme"]["preset"] == "business"
    assert payload["dashboard"]["theme"]["preset"] == "business"
    assert payload["presentation"]["dashboard"] == "sales-overview"
    assert payload["presentation_file"].endswith("presentation.yaml")


def test_stale_presentation_references_fail_preflight_but_runtime_falls_back(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    presentation_path = root / "dashboards" / "sales-overview" / "presentation.yaml"
    presentation = yaml.safe_load(presentation_path.read_text(encoding="utf-8"))
    presentation["views"]["deleted-view"] = {"span": 12}
    presentation["sections"]["deleted-section"] = {"template": "single"}
    presentation["control_components"] = {
        "view:deleted-view/region": {"component": "select"}
    }
    presentation["assets"]["css"].append("assets/missing.css")
    presentation_path.write_text(
        yaml.safe_dump(presentation, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales-overview")
    diagnostics = validate_workspace(workspace)

    assert dashboard.definition.theme.preset == "business"
    errors = {item.code for item in diagnostics if item.level == "error"}
    assert errors >= {
        "presentation_unknown_view",
        "presentation_unknown_section",
        "presentation_unknown_control",
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
    assert dashboard.definition.theme.preset == "business"
    assert any(
        item.level == "error" and item.code == "presentation_invalid"
        for item in diagnostics
    )
    with pytest.raises(ValidationFailure) as failure:
        Executor(workspace).run("sales-overview")
    assert failure.value.details["code"] == "dashboard_preflight_failed"


def test_dashboard_definition_assets_cannot_escape_dashboard_folder(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, root)
    dashboard_root = root / "dashboards" / "sales-overview"
    outside = root / "outside-source.yaml"
    outside.write_text(
        """schema: dataviz/source/v1
kind: source
id: outside
type: file
path: rows.csv
outputs: {main: {kind: table}}
""",
        encoding="utf-8",
    )
    definition_path = dashboard_root / "dashboard.yaml"
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["sources"] = ["../../outside-source.yaml"]
    definition_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    entry = next(item for item in workspace.catalog if item.canvas_name == "sales-overview")

    assert entry.status == "invalid"
    assert entry.runnable is False
    assert any(
        item.level == "error"
        and item.code == "dashboard_invalid"
        and "must stay inside" in item.message
        for item in validate_workspace(workspace)
    )


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


def test_declarative_control_contract_uses_field_binding():
    dashboard = load_workspace(WORKSPACE).dashboard("sales-overview")
    contract = compile_control_contract(dashboard.definition)

    assert set(contract) == set(dashboard.views)
    assert all(selections[0].binding.field == "region" for selections in contract.values())
    assert all(selections[0].origin == "dashboard" for selections in contract.values())


def test_declarative_renderer_limits_selection_redraw_to_affected_views():
    workspace = load_workspace(WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")
    result = Executor(workspace).run("sales-overview")
    rendered = CanvasRenderer(workspace).render(dashboard, result, asset_mode="server")

    assert "affected.has(id)" in rendered
    assert "affectedViews(changedSelectionKeys, new Set())" in rendered
    assert "datavizRuntime.renderViews" in rendered
    assert "window.datavizClient" not in rendered


@pytest.mark.parametrize(
    "removed_fragment",
    [
        {"dashboard_filters": [{"id": "region"}]},
        {"dashboard_selections": [{"id": "region"}]},
        {"compute_parameters": [{"id": "seed"}]},
        {"sections": [{"id": "main", "title": "Main", "filters": []}]},
        {"sections": [{"id": "main", "title": "Main", "selections": []}]},
        {"canvas": {"client_filters": True}},
        {"canvas": {"style": "canvas/style.css"}},
        {"canvas": {"script": "canvas/script.js"}},
        {"layout": {"items": [{"widget": "detail"}]}},
        {"views": [{"id": "detail", "template": "table", "source": "sales"}]},
        {"views": [{"id": "detail", "template": "table", "selections": []}]},
    ],
)
def test_removed_schema_fields_are_rejected(removed_fragment):
    with pytest.raises(ValidationError) as failure:
        DashboardDefinition.model_validate(
            {
                "schema": "dataviz/dashboard/v4",
                "kind": "dashboard",
                "id": "strict",
                **removed_fragment,
            }
        )
    assert any(error["type"] == "extra_forbidden" for error in failure.value.errors())


@pytest.mark.parametrize("removed_field", ["compute_params", "selections"])
def test_interactive_transform_rejects_old_unscoped_input_maps(removed_field):
    with pytest.raises(ValidationError) as failure:
        InteractiveTransformDefinition.model_validate(
            {
                "schema": "dataviz/interactive-transform/v1",
                "kind": "interactive_transform",
                "id": "strict",
                "runtime": "browser-js",
                "code": "transform.js",
                "export": {"mode": "interactive"},
                "outputs": {"main": {"kind": "table"}},
                removed_field: {"value": "dashboard:strict/value"},
            }
        )
    assert any(error["type"] == "extra_forbidden" for error in failure.value.errors())


@pytest.mark.parametrize("field", ["navigation", "trash"])
def test_removed_workspace_tree_fields_are_rejected(field):
    with pytest.raises(ValidationError) as failure:
        WorkspaceDefinition.model_validate(
            {
                "schema": "dataviz/workspace/v1",
                "kind": "workspace",
                "id": "strict",
                "title": "Strict",
                field: [],
            }
        )
    assert failure.value.errors()[0]["type"] == "extra_forbidden"
    assert failure.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize(
    ("fragment", "location"),
    [
        ({"sections": [{"id": "main", "title": "Main", "columns": 0}]}, ("sections", 0, "columns")),
        ({"sections": [{"id": "main", "title": "Main", "columns": 25}]}, ("sections", 0, "columns")),
        ({"layout": {"columns": 0}}, ("layout", "columns")),
        ({"layout": {"columns": 25}}, ("layout", "columns")),
        ({"layout": {"gap": -1}}, ("layout", "gap")),
        (
            {"views": [{"id": "detail", "template": "table", "limit": 0}]},
            ("views", 0, "limit"),
        ),
    ],
)
def test_layout_and_view_bounds_are_enforced(fragment, location):
    with pytest.raises(ValidationError) as failure:
        DashboardDefinition.model_validate(
            {
                "schema": "dataviz/dashboard/v4",
                "kind": "dashboard",
                "id": "strict",
                **fragment,
            }
        )
    assert any(error["loc"] == location for error in failure.value.errors())


def test_selection_contract_is_include_only():
    with pytest.raises(ValidationError):
        SelectionControlDefinition.model_validate(
            {"id": "region", "kind": "selection", "type": "multi_select", "mode": "exclude"}
        )


def test_query_parameter_changes_inline_sql_dataset():
    workspace = load_workspace(WORKSPACE)
    result = Executor(workspace).run(
        "sales-overview", query_parameters={"min_query_revenue": 150000}, refresh=True
    )
    artifact = result.nodes["source:sales"].outputs["main"]
    frame = ArtifactStore(workspace.root, result.run_id).read_table(artifact)

    assert result.status == "ready"
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
    assert "global.dataviz?.view_specs" in report
    assert '"schema": "dataviz/runtime/v2"' in report
    assert "runtime.registerView(view.id" in report
    assert "window.datavizClient" not in report
    assert '"source:sales/main": [' in report
    assert "const selectRows =" in report
    assert "operator === 'gte'" in report
    assert "const valueFields = view.template === 'heatmap'" in report
    assert "view.template === 'metric'" in report
    assert "const plotlyDescriptor" in report
    assert "const plotlyConfig = (config = {})" in report
    assert "scrollZoom:false" in report
    assert "plotlyConfig(descriptor.config)" in report
    assert "plotlyConfig(spec.config)" in report
    assert "const createPerspective" in report
    assert "const updatePerspective" in report
    assert "const disposePerspective" in report
    assert "state.mode === 'empty' && state.latestRows.length" in report
    assert "if (typeof state.viewer?.flush === 'function') await state.viewer.flush()" in report
    assert "applyStatus(root, 'ready', 'perspective')" in report
    assert "viewer.delete" in report
    assert "@perspective-dev/viewer@5.2.0" in report
    assert '"template": "table"' in report
    assert "formatTableValue" in report
    assert "dv-table--striped" in report
    assert "releaseWheelAtBoundary(wrap)" in report
    assert "releaseWheelAtBoundary(viewer)" in report
    assert "wheelEvent.composedPath()" in report
    assert "page.scrollTop += wheelEvent.deltaY * multiplier" in report
    assert "overscroll-behavior: auto" in report
    assert ".dv-view--perspective .dv-view-body { position: relative" in report
    assert ".dv-perspective {" in report and "position: absolute" in report
    assert "--psp-sidebar--background: var(--psp--background-color, #fff)" in report
    assert "canvas/script.js" not in report
