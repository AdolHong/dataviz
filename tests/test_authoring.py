from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner
import yaml

import dataviz.filesystem as filesystem
from dataviz.authoring import (
    build_authoring_benchmark,
    build_context_payload,
    context_size,
    scaffold_recipe,
    scaffold_recipes,
)
from dataviz.cli import app
from dataviz.components import (
    component_index,
    component_packages,
    component_story_catalog,
    validate_component_packages,
)
from dataviz.documentation import DOC_TOPICS
from dataviz.execution import Executor
from dataviz.execution.references import parse_output_reference
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
from dataviz.workspace.models import (
    DashboardDefinition,
    DatasetTransformDefinition,
    DeclarativeViewDefinition,
    InteractiveTransformDefinition,
    LayoutDefinition,
    PresentationDefinition,
    PresentationSelectorDefinition,
    SectionDefinition,
    SelectionDefinition,
    SOURCE_DEFINITION_ADAPTER,
    ThemeDefinition,
)


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_WORKSPACE = ROOT / "examples" / "minimal-workspace"
SALES_WORKSPACE = ROOT / "examples" / "sales-workspace"
GALLERY_WORKSPACE = ROOT / "src" / "dataviz" / "gallery"


@pytest.fixture(scope="module", autouse=True)
def _isolate_repository_workspaces(isolated_workspace):
    global MINIMAL_WORKSPACE, SALES_WORKSPACE
    MINIMAL_WORKSPACE = isolated_workspace(MINIMAL_WORKSPACE)
    SALES_WORKSPACE = isolated_workspace(SALES_WORKSPACE)


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


def test_template_catalog_matches_strict_model_enums():
    def enum_values(model, field: str) -> set[str]:
        return set(model.model_json_schema()["properties"][field]["enum"])

    assert set(VIEW_TEMPLATES) == enum_values(DeclarativeViewDefinition, "template")
    assert set(SECTION_TEMPLATES) == enum_values(SectionDefinition, "template")
    assert set(LAYOUT_TEMPLATES) == enum_values(LayoutDefinition, "template")
    assert set(THEME_PRESETS) == enum_values(ThemeDefinition, "preset")
    selector_templates = {
        identifier.removeprefix("selector.")
        for identifier in component_catalog()
        if identifier.startswith("selector.")
    }
    assert selector_templates == (
        enum_values(PresentationSelectorDefinition, "template") - {"auto"}
    )


def test_machine_readable_component_examples_use_canonical_output_references():
    references: list[tuple[str, str]] = []

    def collect(identifier: str, value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "input" and isinstance(item, str):
                    references.append((identifier, item))
                elif key == "inputs" and isinstance(item, dict):
                    references.extend(
                        (identifier, reference)
                        for reference in item.values()
                        if isinstance(reference, str)
                    )
                else:
                    collect(identifier, item)
        elif isinstance(value, list):
            for item in value:
                collect(identifier, item)

    for identifier, definition in component_catalog().items():
        collect(identifier, definition.get("example", {}))

    assert references
    for identifier, reference in references:
        try:
            parse_output_reference(reference)
        except Exception as error:  # pragma: no cover - assertion adds component context
            raise AssertionError(
                f"Component {identifier} publishes an invalid Output reference: {reference}"
            ) from error


def test_machine_readable_documentation_examples_match_current_schemas():
    providers = {
        "dataviz/dashboard/v2": DashboardDefinition,
        "dataviz/source/v1": SOURCE_DEFINITION_ADAPTER,
        "dataviz/dataset-transform/v1": DatasetTransformDefinition,
        "dataviz/interactive-transform/v1": InteractiveTransformDefinition,
        "dataviz/presentation/v1": PresentationDefinition,
    }
    examples: list[tuple[str, dict[str, object]]] = []

    def collect(path: tuple[str, ...], value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                collect((*path, str(key)), item)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                collect((*path, str(index)), item)
            return
        if not isinstance(value, str):
            return
        try:
            parsed = yaml.safe_load(value)
        except yaml.YAMLError:
            return
        if isinstance(parsed, dict) and isinstance(parsed.get("schema"), str):
            examples.append((".".join(path), parsed))

    collect(("docs",), DOC_TOPICS)

    assert examples
    for path, example in examples:
        schema = str(example["schema"])
        assert schema in providers, f"No documentation contract test for {path}: {schema}"
        provider = providers[schema]
        try:
            if hasattr(provider, "validate_python"):
                provider.validate_python(example)
            else:
                provider.model_validate(example)
        except ValidationError as error:  # pragma: no cover - assertion adds docs context
            raise AssertionError(f"Invalid built-in documentation example: {path}") from error


def test_component_registry_reports_package_owned_implementations():
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
        "schema": "dataviz/component-package-report/v3",
        "scope": "package-metadata-and-test-declarations",
        "behavior_tests_executed": False,
        "valid": True,
        "packages": 13,
        "package_implemented": 13,
        "bridge_implemented": 0,
        "components": 50,
        "stories": 29,
        "test_declarations": 60,
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
        assert definition["implementation"]["mode"] == "package"
        assert definition["implementation"]["assets"]["controller"].endswith(
            "controller.js"
        )
        assert definition["tests"], identifier
        assert definition["gallery"]["available"] is any(
            story["component"] == identifier for story in component_story_catalog().values()
        )
    assert not {
        package.name
        for package in component_packages().values()
        if package.manifest["implementation"]["mode"] == "bridge"
    }


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


def test_every_scaffold_recipe_matches_the_current_strict_models():
    recipes = scaffold_recipes()

    assert len(recipes) == len(set(recipes))
    for recipe in recipes:
        payload = scaffold_recipe(recipe, "sample")
        files = payload["files"]
        assert payload["schema"] == "dataviz/scaffold/v1"

        if recipe == "dashboard":
            DashboardDefinition.model_validate(yaml.safe_load(files["dashboard.yaml"]))
        elif recipe.startswith("source."):
            SOURCE_DEFINITION_ADAPTER.validate_python(
                yaml.safe_load(files["sample.yaml"])
            )
        elif recipe.startswith("dataset-transform."):
            DatasetTransformDefinition.model_validate(yaml.safe_load(files["sample.yaml"]))
        elif recipe.startswith("interactive-transform."):
            InteractiveTransformDefinition.model_validate(
                yaml.safe_load(files["sample.yaml"])
            )
        elif recipe.startswith("view.") or recipe == "renderer.custom":
            DeclarativeViewDefinition.model_validate(
                yaml.safe_load(files["dashboard.view.snippet.yaml"])[0]
            )
        elif recipe.startswith("section."):
            SectionDefinition.model_validate(
                yaml.safe_load(files["dashboard.section.snippet.yaml"])[0]
            )
        elif recipe.startswith("selector."):
            SelectionDefinition.model_validate(
                yaml.safe_load(files["dashboard.selection.snippet.yaml"])[0]
            )
            selector = next(
                iter(
                    yaml.safe_load(files["presentation.selector.snippet.yaml"])[
                        "selectors"
                    ].values()
                )
            )
            PresentationSelectorDefinition.model_validate(selector)
        else:  # pragma: no cover - the catalog and this contract must evolve together
            raise AssertionError(f"Unhandled Scaffold recipe: {recipe}")

    image_files = scaffold_recipe("view.image", "sample")["files"]
    assert image_files["assets/image.svg"].startswith("<svg")
    selection_gallery = yaml.safe_load(
        scaffold_recipe("section.selection-gallery", "sample")["files"][
            "dashboard.section.snippet.yaml"
        ]
    )[0]
    assert selection_gallery["selections"][0]["id"] == "groups"
    assert selection_gallery["repeat"]["selection"] == "groups"


def test_selection_gallery_scaffold_composes_into_a_valid_dashboard(tmp_path: Path):
    root = tmp_path / "workspace"
    dashboard_root = root / "dashboards" / "generated"
    dashboard_root.mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v1\nkind: workspace\nid: generated\ntitle: Generated\n",
        encoding="utf-8",
    )
    dashboard_files = scaffold_recipe("dashboard", "generated")["files"]
    for relative, content in dashboard_files.items():
        destination = dashboard_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    section = yaml.safe_load(
        scaffold_recipe("section.selection-gallery", "entities")["files"][
            "dashboard.section.snippet.yaml"
        ]
    )[0]
    section["views"] = ["overview"]
    section["repeat"]["view"] = "overview"
    definition_path = dashboard_root / "dashboard.yaml"
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["sections"] = [section]
    definition_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (dashboard_root / "data" / "data.csv").write_text(
        "entity_id,value\nA,12\nB,19\n",
        encoding="utf-8",
    )

    assert validate_workspace(load_workspace(root)) == []


def test_scaffold_materialization_rolls_back_every_file_on_failure(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "renderer"
    target.mkdir()
    existing = target / "dashboard.view.snippet.yaml"
    existing.write_text("original\n", encoding="utf-8")
    original_write = filesystem.atomic_write_text

    def fail_javascript(path: Path, content: str, *, encoding: str = "utf-8"):
        if path.suffix == ".js":
            raise OSError("simulated scaffold publish failure")
        return original_write(path, content, encoding=encoding)

    monkeypatch.setattr(filesystem, "atomic_write_text", fail_javascript)
    result = CliRunner().invoke(
        app,
        [
            "scaffold",
            "renderer.custom",
            "--id",
            "team.spark",
            "--output",
            str(target),
            "--force",
        ],
    )

    assert result.exit_code == 1
    assert existing.read_text(encoding="utf-8") == "original\n"
    assert not (target / "assets").exists()


def test_scaffold_catalog_is_machine_readable_and_dashboard_recipe_runs(tmp_path: Path):
    catalog_result = CliRunner().invoke(
        app, ["scaffold", "--list", "--format", "json"]
    )
    assert catalog_result.exit_code == 0, catalog_result.stdout
    assert json.loads(catalog_result.stdout) == {
        "schema": "dataviz/scaffold-catalog/v1",
        "recipes": list(scaffold_recipes()),
    }

    root = tmp_path / "workspace"
    dashboard_root = root / "dashboards" / "generated"
    dashboard_root.mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v1\nkind: workspace\nid: generated\ntitle: Generated\n",
        encoding="utf-8",
    )
    for relative, content in scaffold_recipe("dashboard", "generated")["files"].items():
        destination = dashboard_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    workspace = load_workspace(root)
    assert validate_workspace(workspace) == []
    result = Executor(workspace).run("generated", refresh=True)
    report = CanvasRenderer(workspace).write_report(
        workspace.dashboard("generated"), result, tmp_path / "generated.html"
    )
    assert result.status == "ready"
    assert report.is_file()


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

    docs_result = CliRunner().invoke(
        app, ["docs", "ai-authoring", "--format", "json"]
    )
    assert docs_result.exit_code == 0
    docs = json.loads(docs_result.stdout)
    assert docs["runtime_benchmark"]["schema"] == "dataviz/browser-runtime-benchmark/v2"
    assert any("--browser-runtime" in command for command in docs["commands"])


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
    with pytest.raises(ValidationError) as failure:
        DashboardDefinition.model_validate(
            {
                "schema": "dataviz/dashboard/v2",
                "kind": "dashboard",
                "id": "strict",
                "layout": layout,
            }
        )
    assert any(error["type"] == "extra_forbidden" for error in failure.value.errors())


@pytest.mark.parametrize("field", ["width", "height", "x", "y"])
def test_coordinate_presentation_fields_are_strictly_rejected(field):
    with pytest.raises(ValidationError) as failure:
        PresentationDefinition.model_validate(
            {
                "schema": "dataviz/presentation/v1",
                "kind": "presentation",
                "dashboard": "strict",
                "views": {"chart": {field: 6}},
            }
        )
    assert failure.value.errors()[0]["type"] == "extra_forbidden"
    assert failure.value.errors()[0]["loc"] == ("views", "chart", field)


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
    assert '"id": "selector.select.scale-10"' in exported
    assert '"id": "selector.select.scale-100"' in exported
    assert '"id": "selector.select.scale-1000"' in exported
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
        / "components"
        / "packages"
        / "view.declarative"
        / "controller.js"
    ).read_text(encoding="utf-8")

    # The first render is a full render. Otherwise Markdown/Image Views without
    # an input stay in a permanent waiting state because no Output can wake them.
    assert "if (changedSelectionKeys == null) return null" in runtime
    assert declarative.index("view.template === 'markdown'") < declarative.index(
        "let rows = preparedRows"
    )
    assert declarative.index("view.template === 'image'") < declarative.index(
        "let rows = preparedRows"
    )
    assert "return {type:view.renderer, rows, inputs, view" in declarative
    assert "series:groups.map(group =>" in declarative


def test_runtime_v2_has_one_owner_for_each_migrated_behavior():
    runtime = (
        ROOT / "src" / "dataviz" / "server" / "static" / "canvas-runtime.js"
    ).read_text(encoding="utf-8")
    static_root = ROOT / "src" / "dataviz" / "server" / "static"

    assert not (static_root / "declarative-runtime.js").exists()
    for implementation in (
        "class DatavizFrame",
        "class DatavizGroupedFrame",
        "createInteractiveAdapters",
        "createPerspective",
        "renderPlainTable",
        "renderRepeatedSection",
    ):
        assert implementation not in runtime
    assert "window.datavizRuntimeServices = Object.freeze" in runtime
    assert "dataviz:runtime-ready" in runtime

    owners = {
        "data.pipeline": "createInteractiveAdapters",
        "view.declarative": "createPerspective",
        "section.declarative": "renderRepeatedSection",
        "presentation.shell": "component-state",
    }
    for package, marker in owners.items():
        package_root = ROOT / "src" / "dataviz" / "components" / "packages" / package
        source = "\n".join(
            (package_root / name).read_text(encoding="utf-8")
            for name in ("controller.js", "adapter.js")
        )
        assert marker in source


def test_component_docs_only_offer_fields_consumed_by_each_view_path():
    catalog = component_catalog()

    for template, contract in VIEW_TEMPLATES.items():
        component = catalog[f"view.{template}"]
        assert component["logic"]["fields"] == contract["fields"]
        assert set(component["logic"]["optional"]) == set(contract["optional"])
        expected_presentation = {"span", "min_height", "container", "css_class"}
        expected_presentation.update(
            field
            for field in ("engine", "options", "config")
            if field in contract["optional"]
            and not (field == "engine" and contract.get("engine"))
        )
        assert set(component["presentation"]["options"]) == expected_presentation

    table = catalog["view.table"]
    line = catalog["view.line"]
    image = catalog["view.image"]
    radar = catalog["view.radar"]

    assert table["presentation"]["options"] == [
        "span",
        "min_height",
        "container",
        "css_class",
        "options",
    ]
    assert {"engine", "options", "config"} <= set(
        line["presentation"]["options"]
    )
    assert image["behavior"]["input"] == "Self-contained; consumes no Named Output"
    assert radar["logic"]["engine"] == "echarts"
