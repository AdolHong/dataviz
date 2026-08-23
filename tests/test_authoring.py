from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner
import yaml

from dataviz.authoring import (
    build_authoring_benchmark,
    build_context_payload,
    context_size,
)
from dataviz.cli import app
from dataviz.components import (
    component_index,
    component_packages,
    component_story_catalog,
    validate_component_packages,
)
from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer
from dataviz.templates import (
    COMPONENT_REGISTRY_VERSION,
    LAYOUT_TEMPLATES,
    SECTION_TEMPLATES,
    THEME_PRESETS,
    VIEW_TEMPLATES,
    component_catalog,
)
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.models import DashboardDefinition, PresentationDefinition


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_WORKSPACE = ROOT / "examples" / "minimal-workspace"
SALES_WORKSPACE = ROOT / "examples" / "sales-workspace"
GALLERY_WORKSPACE = ROOT / "src" / "dataviz" / "gallery"


def test_component_registry_covers_every_strict_template():
    catalog = component_catalog()

    assert {f"view.{value}" for value in VIEW_TEMPLATES} <= set(catalog)
    assert {f"section.{value}" for value in SECTION_TEMPLATES} <= set(catalog)
    assert {f"layout.{value}" for value in LAYOUT_TEMPLATES} <= set(catalog)
    assert {f"theme.{value}" for value in THEME_PRESETS} <= set(catalog)
    for identifier, definition in catalog.items():
        assert definition["schema"] == "dataviz/component/v1", identifier
        assert definition["id"] == identifier
        assert definition["version"]
        assert definition["implementation"]
        assert isinstance(definition["gallery"]["available"], bool)


def test_component_registry_is_backed_by_complete_physical_packages():
    catalog = component_catalog()
    report = validate_component_packages(catalog)

    assert COMPONENT_REGISTRY_VERSION == "3.0.0"
    assert set(component_packages()) == {
        "data.pipeline",
        "presentation.shell",
        "renderer.custom",
        "runtime.overlay",
        "runtime.selector",
        "section.declarative",
        "selector.cascader",
        "selector.checkbox-group",
        "selector.date-range",
        "selector.segmented",
        "selector.select",
        "selector.tree-select",
        "view.declarative",
    }
    assert {identifier for identifier in catalog if identifier.startswith("selector.")} == {
        "selector.select",
        "selector.segmented",
        "selector.checkbox-group",
        "selector.cascader",
        "selector.date-range",
        "selector.tree-select",
    }

    assert report == {
        "schema": "dataviz/component-package-report/v1",
        "valid": True,
        "packages": 13,
        "components": 47,
        "stories": 23,
        "tests": 56,
        "errors": [],
    }
    assert set(component_index()) == set(catalog)
    for package in component_packages().values():
        assert {
            "manifest.yaml",
            "controller.js",
            "adapter.js",
            "style.css",
            "story.yaml",
            "test.yaml",
        } <= {path.name for path in package.root.iterdir()}
    for identifier, definition in catalog.items():
        assert definition["package"]["package"]
        assert definition["implementation"]["controller"].endswith("controller.js")
        assert definition["tests"], identifier
        assert definition["gallery"]["available"] is any(
            story["component"] == identifier for story in component_story_catalog().values()
        )


def test_component_package_cli_check_and_new_selector_scaffolds():
    check = CliRunner().invoke(app, ["components", "--check", "--format", "json"])
    tree = CliRunner().invoke(
        app, ["scaffold", "selector.tree-select", "--id", "location", "--format", "json"]
    )
    date = CliRunner().invoke(
        app, ["scaffold", "selector.date-range", "--id", "window", "--format", "json"]
    )
    flat = CliRunner().invoke(
        app, ["scaffold", "selector.select", "--id", "region", "--format", "json"]
    )
    segmented = CliRunner().invoke(
        app, ["scaffold", "selector.segmented", "--id", "status", "--format", "json"]
    )
    checkbox = CliRunner().invoke(
        app, ["scaffold", "selector.checkbox-group", "--id", "channel", "--format", "json"]
    )
    docs = CliRunner().invoke(app, ["docs", "selections", "--format", "json"])
    component = CliRunner().invoke(
        app, ["components", "selector.select", "--format", "json"]
    )

    assert check.exit_code == 0, check.stdout
    assert json.loads(check.stdout)["valid"] is True
    tree_files = json.loads(tree.stdout)["files"]
    tree_selection = yaml.safe_load(tree_files["dashboard.selection.snippet.yaml"])[0]
    assert tree_selection["path_fields"] == ["province", "city", "district"]
    date_selection = yaml.safe_load(json.loads(date.stdout)["files"]["dashboard.selection.snippet.yaml"])[0]
    assert date_selection["type"] == "date_range"
    flat_selection = yaml.safe_load(json.loads(flat.stdout)["files"]["dashboard.selection.snippet.yaml"])[0]
    assert flat_selection["type"] == "multi_select"
    assert [item["value"] for item in flat_selection["choices"]] == ["alpha", "beta"]
    segmented_selection = yaml.safe_load(
        json.loads(segmented.stdout)["files"]["dashboard.selection.snippet.yaml"]
    )[0]
    checkbox_selection = yaml.safe_load(
        json.loads(checkbox.stdout)["files"]["dashboard.selection.snippet.yaml"]
    )[0]
    assert segmented_selection["type"] == "single_select"
    assert segmented_selection["default"] == "alpha"
    assert checkbox_selection["type"] == "multi_select"
    assert yaml.safe_load(
        json.loads(checkbox.stdout)["files"]["presentation.selector.snippet.yaml"]
    )["selectors"]["view:view-id/channel"]["template"] == "checkbox-group"
    docs_payload = json.loads(docs.stdout)
    assert set(docs_payload["selector_choice"]) == {
        "auto", "select", "segmented", "checkbox-group", "cascader", "tree-select", "date-range"
    }
    assert "auto/always/never" in docs_payload["selector_choice"]["select"]
    assert json.loads(component.stdout)["id"] == "selector.select"


def test_focused_context_contains_only_the_view_dependency_closure():
    workspace = load_workspace(SALES_WORKSPACE)
    dashboard = workspace.dashboard("sales")

    distribution = build_context_payload(
        workspace, dashboard, focus="view:distribution"
    )
    revenue = build_context_payload(workspace, dashboard, focus="view:revenue")
    full = build_context_payload(workspace, dashboard)

    assert distribution["mode"] == "focused"
    assert set(distribution["views"]) == {"distribution"}
    assert set(distribution["sources"]) == {"orders"}
    assert distribution["dataset_transforms"] == {}
    assert set(distribution["effective_selections"]) == {"distribution"}
    assert set(distribution["templates"]["views"]) == {"bar"}

    assert set(revenue["sources"]) == {"orders", "targets"}
    assert set(revenue["dataset_transforms"]) == {"sales-metrics"}
    assert revenue["dashboard_logic"]["query_parameters"][0]["id"] == "target_factor"
    assert context_size(distribution)["utf8_bytes"] < context_size(full)["utf8_bytes"]


def test_context_does_not_embed_file_dataset_rows():
    workspace = load_workspace(MINIMAL_WORKSPACE)
    payload = build_context_payload(
        workspace,
        workspace.dashboard("sales-overview"),
        focus="source:sales",
    )

    # The SQL source remains reviewable. File sources use data_file metadata instead
    # of copying potentially large CSV/Parquet contents into AI context.
    assert "select" in payload["sources"]["sales"]["code"].lower()

    gallery = load_workspace(GALLERY_WORKSPACE)
    file_payload = build_context_payload(
        gallery,
        gallery.dashboard("component-gallery"),
        focus="source:gallery-data",
    )
    source = file_payload["sources"]["gallery-data"]
    assert source["code"] is None
    assert source["data_file"]["path"] == "data/gallery.csv"
    assert source["data_file"]["bytes"] > 0


def test_component_focus_and_scaffold_are_machine_readable(tmp_path: Path):
    context_result = CliRunner().invoke(
        app,
        [
            "context",
            str(MINIMAL_WORKSPACE),
            "sales-overview",
            "--focus",
            "component:selector.cascader",
            "--format",
            "json",
        ],
    )
    scaffold_result = CliRunner().invoke(
        app,
        [
            "scaffold",
            "dashboard",
            "--id",
            "generated",
            "--output",
            str(tmp_path / "generated"),
        ],
    )

    assert context_result.exit_code == 0, context_result.stdout
    context_payload = json.loads(context_result.stdout)
    assert context_payload["focus"] == "component:selector.cascader"
    assert "workspace" not in context_payload
    assert context_payload["component"]["logic"]["fields"] == ["path_fields"]

    assert scaffold_result.exit_code == 0, scaffold_result.stdout
    dashboard = DashboardDefinition.model_validate(
        yaml.safe_load(
            (tmp_path / "generated" / "dashboard.yaml").read_text(encoding="utf-8")
        )
    )
    assert dashboard.id == "generated"
    assert dashboard.views[0].template == "table"


def test_authoring_benchmark_is_deterministic_and_does_not_guess_tokens():
    workspace = load_workspace(MINIMAL_WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")

    first = build_authoring_benchmark(workspace, dashboard)
    second = build_authoring_benchmark(workspace, dashboard)

    assert first == second
    assert first["validation"]["valid"] is True
    assert first["context"]["focused_summary"]["median_reduction_percent"] > 0
    assert "estimated_tokens" not in json.dumps(first)
    assert "model-specific input/output tokens" in first["not_measured"]

    help_result = CliRunner().invoke(app, ["benchmark", "--help"])
    assert help_result.exit_code == 0
    assert "--browser-runtime" in help_result.stdout
    assert "--timeout-seconds" in help_result.stdout


@pytest.mark.parametrize(
    "layout",
    [
        {"items": [{"view": "chart"}]},
        {"row_height": 90},
        {"x": 0},
        {"y": 0},
        {"height": 4},
    ],
)
def test_coordinate_layout_fields_are_strictly_rejected(layout):
    with pytest.raises(ValidationError):
        DashboardDefinition.model_validate({"id": "strict", "layout": layout})


@pytest.mark.parametrize("field", ["width", "height", "x", "y"])
def test_coordinate_presentation_fields_are_strictly_rejected(field):
    with pytest.raises(ValidationError):
        PresentationDefinition.model_validate(
            {"dashboard": "strict", "views": {"chart": {field: 6}}}
        )


def test_functional_css_survives_when_default_visual_style_is_disabled():
    workspace = load_workspace(MINIMAL_WORKSPACE)
    dashboard = workspace.dashboard("sales-overview")
    dashboard.definition.canvas.use_default_style = False
    result = Executor(workspace).run("sales-overview")

    report = CanvasRenderer(workspace).render(dashboard, result)

    assert "Runtime-critical component structure" in report
    assert ".dv-cascader-panel" in report
    assert "The unconfigured Canvas is deliberately" not in report


def test_builtin_gallery_is_a_valid_real_workspace_and_exports(tmp_path: Path):
    gallery_root = tmp_path / "gallery"
    shutil.copytree(GALLERY_WORKSPACE, gallery_root, ignore=shutil.ignore_patterns(".dataviz"))
    workspace = load_workspace(gallery_root)

    assert validate_workspace(workspace) == []
    result = Executor(workspace).run("component-gallery", refresh=True)
    report = CanvasRenderer(workspace).write_report(
        workspace.dashboard("component-gallery"), result, tmp_path / "gallery.html"
    )

    assert result.status == "ready"
    html = report.read_text(encoding="utf-8")
    assert "Component Gallery" in html
    assert "registerRenderer('gallery.spark'" in html
    assert "dv-section--small-multiples" in html
    assert 'data-selector-template="cascader"' in html
    assert 'data-selector-template="date-range"' in html
    assert 'data-selector-template="tree-select"' in html
    assert 'data-selector-template="select"' in html
    assert 'data-selector-template="segmented"' in html
    assert 'data-selector-template="checkbox-group"' in html
    assert 'data-component-package="runtime.overlay"' in html


def test_custom_renderer_scaffold_includes_style_and_contract(tmp_path: Path):
    target = tmp_path / "renderer"
    result = CliRunner().invoke(
        app,
        ["scaffold", "renderer.custom", "--id", "team.spark", "--output", str(target)],
    )

    assert result.exit_code == 0, result.stdout
    contract = json.loads((target / "assets" / "team.spark.contract.json").read_text())
    assert contract["schema"] == "dataviz/renderer-contract/v1"
    assert contract["renderer"] == "team.spark"
    script = (target / "assets" / "team.spark.js").read_text()
    style = (target / "assets" / "team.spark.css").read_text()
    assert 'node.className = "renderer-team-spark"' in script
    assert ".renderer-team-spark" in style
    assets = yaml.safe_load((target / "presentation.asset.snippet.yaml").read_text())
    assert assets["assets"]["css"] == ["assets/team.spark.css"]


def test_gallery_cli_never_writes_runtime_artifacts_into_the_installed_package(
    tmp_path: Path,
):
    before = {path.relative_to(GALLERY_WORKSPACE) for path in GALLERY_WORKSPACE.rglob("*")}
    output = tmp_path / "gallery.html"

    result = CliRunner().invoke(app, ["gallery", "--output", str(output)])

    after = {path.relative_to(GALLERY_WORKSPACE) for path in GALLERY_WORKSPACE.rglob("*")}
    assert result.exit_code == 0, result.stdout
    assert output.is_file()
    exported = output.read_text(encoding="utf-8")
    assert "window.datavizComponentStories = [" in exported
    assert '"id": "selector.select.scale"' in exported
    assert "runtime specimens" in exported
    assert after == before


def test_initial_runtime_render_includes_input_free_content_views():
    runtime = (
        ROOT / "src" / "dataviz" / "server" / "static" / "canvas-runtime.js"
    ).read_text(encoding="utf-8")
    declarative = (
        ROOT
        / "src"
        / "dataviz"
        / "server"
        / "static"
        / "declarative-runtime.js"
    ).read_text(encoding="utf-8")

    # The first render is a full render. Otherwise Markdown/Image Views without
    # an input stay in a permanent waiting state because no Output can wake them.
    assert "if (changedSelectionKeys == null) return null" in runtime
    assert declarative.index("view.template === 'markdown'") < declarative.index(
        "const rows = preparedRows"
    )
    assert declarative.index("view.template === 'image'") < declarative.index(
        "const rows = preparedRows"
    )
