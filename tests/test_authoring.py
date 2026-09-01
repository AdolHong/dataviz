from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner
import yaml

import dataviz.filesystem as filesystem
from dataviz.authoring import (
    build_context_payload,
    scaffold_catalog,
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
from dataviz.documentation import (
    AUTHORING_DOCUMENTS,
    AUTHORING_ROUTES,
    DOC_CATALOG_SCHEMA,
    DOC_PATHS,
    DOC_TOPICS,
    authoring_route_catalog,
    resolve_authoring_route,
)
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
    ControlDefinition,
    DatasetTransformDefinition,
    DeclarativeViewDefinition,
    InteractiveTransformDefinition,
    LayoutDefinition,
    PresentationDefinition,
    PresentationControlComponentDefinition,
    SectionDefinition,
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
    control_components = {
        identifier.removeprefix("control.")
        for identifier in component_catalog()
        if identifier.startswith("control.")
    }
    assert control_components == (
        enum_values(PresentationControlComponentDefinition, "component") - {"auto"}
    )


def test_business_is_the_default_theme_preset():
    assert ThemeDefinition().preset == "business"
    assert THEME_PRESETS["business"]["purpose"] == "Clean neutral analytical default"
    tokens = component_catalog()["theme.business"]["tokens"]
    assert {"--dv-overlay-surface", "--dv-chart-8", "--dv-shadow-float"} <= set(tokens)


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
        "dataviz/dashboard/v14": DashboardDefinition,
        "dataviz/source/v5": SOURCE_DEFINITION_ADAPTER,
        "dataviz/dataset-transform/v3": DatasetTransformDefinition,
        "dataviz/interactive-transform/v4": InteractiveTransformDefinition,
        "dataviz/presentation/v2": PresentationDefinition,
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


def test_every_documented_yaml_snippet_is_parseable():
    yaml_keys = {
        "minimal_example",
        "definition",
        "binding",
        "example",
        "dashboard_example",
        "interactive_input_example",
        "dynamic_option_example",
        "presentation_example",
    }
    snippets: list[tuple[str, str]] = []

    def collect(path: tuple[str, ...], value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                collect((*path, str(key)), item)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                collect((*path, str(index)), item)
            return
        if isinstance(value, str) and path[-1] in yaml_keys and "\n" in value:
            snippets.append((".".join(path), value))

    collect(("topics",), DOC_TOPICS)
    collect(("authoring",), AUTHORING_DOCUMENTS)

    assert snippets
    for path, snippet in snippets:
        try:
            parsed = yaml.safe_load(snippet)
        except yaml.YAMLError as error:  # pragma: no cover - assertion adds docs context
            raise AssertionError(f"Invalid YAML documentation snippet: {path}") from error
        assert parsed is not None, f"Empty YAML documentation snippet: {path}"


def test_documented_dataviz_commands_use_the_current_cli_tree():
    root_commands = {
        item.name or item.callback.__name__.replace("_", "-")
        for item in app.registered_commands
    }
    group_commands = {
        group.name: {
            item.name or item.callback.__name__.replace("_", "-")
            for item in group.typer_instance.registered_commands
        }
        for group in app.registered_groups
    }
    root_commands.update(group_commands)
    documented: list[tuple[str, str]] = []

    def collect(path: tuple[str, ...], value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                collect((*path, str(key)), item)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                collect((*path, str(index)), item)
            return
        if isinstance(value, str) and "dataviz " in value:
            documented.append((".".join(path), value))

    collect(("topics",), DOC_TOPICS)
    collect(("authoring_documents",), AUTHORING_DOCUMENTS)
    collect(("authoring_routes",), AUTHORING_ROUTES)
    collect(("paths",), DOC_PATHS)

    assert documented
    pattern = re.compile(r"\bdataviz\s+([a-z][a-z0-9-]*)(?:\s+([a-z][a-z0-9-]*))?")
    for path, value in documented:
        for root, child in pattern.findall(value):
            assert root in root_commands, f"Unknown documented command at {path}: {root}"
            if root in group_commands:
                assert child in group_commands[root], (
                    f"Unknown documented subcommand at {path}: {root} {child}"
                )

    corpus = "\n".join(value for _, value in documented)
    for stale in (
        "dataviz analyze ",
        "dataviz inspect-layout",
        "dataviz components --check",
        "dataviz clean ",
    ):
        assert stale not in corpus


def test_docs_catalog_exposes_both_progressive_product_paths():
    result = CliRunner().invoke(app, ["docs", "--format", "json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema"] == DOC_CATALOG_SCHEMA
    assert payload["start_here"] == {
        "build_dashboard": "quickstart",
        "explore_data": "analysis-quickstart",
    }
    assert set(payload["paths"]) == {
        "build-and-verify", "explore-and-execute", "operate-and-extend"
    }
    analysis_path = payload["paths"]["explore-and-execute"]
    assert analysis_path["workflow"] == [
        "analysis-quickstart",
        "catalog-discovery",
        "target-references",
        "results",
        "analysis-overlays",
        "evidence-promotion",
        "troubleshooting",
    ]

    quickstart = DOC_TOPICS["quickstart"]
    assert quickstart["workspace_start"]["starter_workspace"] == (
        "dataviz init <workspace>"
    )
    assert "hello Dashboard" in quickstart["workspace_start"]["rule"]


def test_docs_do_not_restore_removed_chart_cli_or_shell_contracts():
    corpus = json.dumps(DOC_TOPICS, ensure_ascii=False)

    for stale in (
        "ECharts",
        "Vega",
        "Plotly 6",
        "init 创建空的最小 Workspace",
        "Run query split control",
        "Perspective 用于排序、筛选和透视探索",
    ):
        assert stale not in corpus


def test_query_parameter_docs_keep_materialization_and_compact_state_explicit():
    query_docs = DOC_TOPICS["query-parameters"]
    rules = "\n".join(query_docs["dynamic_domains"]["rules"])
    skill = (ROOT / "dataviz-skill.md").read_text(encoding="utf-8")
    design = (ROOT / "DESIGN.md").read_text(encoding="utf-8")

    assert "共享 immutable generation" in rules
    assert "all/include/exclude/none" in rules
    assert "搜索、级联和 cursor 分页" in rules
    assert "不重新执行远端 SQL" in rules
    assert "city_selection" in query_docs["selection_binding"]
    assert "dataviz init <workspace>" in skill
    assert "intentionally empty Workspace" not in skill
    assert "canonical Query Parameter state" in skill
    assert "all/include/exclude/none" in skill
    assert "Workspace 共享物化" in design
    assert "generation-bound opaque cursor" in design

    public_docs = "\n".join(
        [
            json.dumps(DOC_TOPICS, ensure_ascii=False),
            skill,
            design,
            (ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "plan.md").read_text(encoding="utf-8"),
            (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
            *[
                path.read_text(encoding="utf-8")
                for path in sorted((ROOT / "docs").glob("*.md"))
            ],
        ]
    )
    for rejected_direction in (
        "远程搜索",
        "分页候选",
        "remote search",
        "paged candidates",
    ):
        assert rejected_direction not in public_docs


@pytest.mark.parametrize(
    ("alias", "topic"),
    [
        ("analysis", "analysis-quickstart"),
        ("catalog", "catalog-discovery"),
        ("target", "target-references"),
        ("result", "results"),
        ("evidence", "evidence-promotion"),
        ("overlay", "analysis-overlays"),
    ],
)
def test_cli_docs_resolves_analysis_plane_topics(alias: str, topic: str):
    result = CliRunner().invoke(app, ["docs", alias, "--format", "json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["topic"] == topic
    assert payload["summary"]


def test_chart_docs_expose_plotly_as_the_only_author_path():
    charts = DOC_TOPICS["charts"]
    wheel = DOC_TOPICS["charts"]["wheel_and_zoom"]
    service = DOC_TOPICS["renderers"]["chart_service"]

    assert "唯一" in charts["summary"]
    assert "数据口径" in charts["rule"]
    assert charts["official_gallery"] == "https://plotly.com/javascript/"
    assert charts["official_source"] == "https://github.com/plotly/plotly.js/"
    assert charts["plotly_runtime"]["version"] == "4.0.0"
    assert "不依赖 Python plotly" in charts["plotly_runtime"]["offline"]
    assert "canonical Named Output" in charts["ownership"]["data"]
    assert "Browser Runtime" in charts["ownership"]["layout"]
    assert "newPlot/react/resize/purge" in charts["ownership"]["render"]
    assert "Named Output" in charts["source_adaptation"]
    assert "不复制官方示例库" in charts["recipe_policy"]
    assert "完整 Plotly.js" in service["native_api"]
    assert "Plotly" in wheel["plotly_default"]
    assert "context.charts.plotly" in wheel["custom_renderer"]
    assert "底层" in service["escape_hatch"]
    author_payload = json.dumps({"charts": charts, "renderers": service}).lower()
    assert "plotly" in author_payload
    assert all(
        "engine" not in contract.get("optional", [])
        for contract in charts["field_matrix"].values()
    )


def test_table_docs_expose_tanstack_defaults_and_the_full_escape_hatch():
    tables = DOC_TOPICS["tables"]
    service = DOC_TOPICS["renderers"]["table_service"]

    assert tables["runtime"]["package"] == "@tanstack/table-core"
    assert tables["runtime"]["version"] == "9.2.4"
    assert "sorting" in tables["runtime"]["default_features"]
    assert "page_size" in tables["options"]["behavior"]
    assert "显式启用" in tables["options"]["rule"]
    assert "context.tables.tanstack.mount" in tables["custom_service"]["managed"]
    assert "context.tables.tanstack.core" in tables["custom_service"]["raw"]
    assert "完整 TanStack Table Core" in service["api"]
    assert "Perspective" in tables["decision_rule"]
    table_rules = DOC_TOPICS["design-language"]["component_rules"]["tables"]
    assert "TanStack Table" in table_rules[0]
    assert "临时重组、聚合或透视" in table_rules[0]


def test_version_docs_match_the_current_runtime_and_release_gate():
    strict = DOC_TOPICS["strict-schema"]
    release = DOC_TOPICS["versioning-release"]

    assert strict["current"]["layout_contract"] == "dataviz/layout-contract/v1"
    assert strict["current"]["state_snapshot"] == "dataviz/state-snapshot/v5"
    assert strict["browser_assets"] == {
        "plotly_js": "4.0.0（直接内置，不安装 Python plotly）",
        "tanstack_table_core": "9.2.4（直接内置）",
    }
    contract = "\n".join(release["release_contract"])
    assert "快速迭代默认运行完整 Chromium" in contract
    assert "稳定发布" in contract and "Firefox/WebKit" in contract
    assert "Python plotly 未安装" in contract


def test_component_registry_reports_package_owned_implementations():
    catalog = component_catalog()
    report = validate_component_packages(catalog)

    assert COMPONENT_REGISTRY_VERSION == "5.6.0"
    assert set(component_packages()) == {
        "control.auto-complete",
        "control.cascader",
        "control.checkbox",
        "control.checkbox-group",
        "control.date-picker",
        "control.input",
        "control.input-number",
        "control.multiple-input",
        "control.radio-group",
        "control.range-picker",
        "control.select",
        "control.slider",
        "control.switch",
        "control.tree-select",
        "data.pipeline",
        "presentation.shell",
        "renderer.custom",
        "runtime.control",
        "runtime.overlay",
        "section.declarative",
        "view.declarative",
    }
    assert {identifier for identifier in catalog if identifier.startswith("control.")} == {
        "control.auto-complete",
        "control.cascader",
        "control.checkbox",
        "control.checkbox-group",
        "control.date-picker",
        "control.input",
        "control.input-number",
        "control.multiple-input",
        "control.radio-group",
        "control.range-picker",
        "control.select",
        "control.slider",
        "control.switch",
        "control.tree-select",
    }

    assert report == {
        "schema": "dataviz/component-package-report/v3",
        "scope": "package-metadata-and-test-declarations",
        "behavior_tests_executed": False,
        "valid": True,
        "packages": 21,
        "package_implemented": 21,
        "bridge_implemented": 0,
        "components": 63,
        "stories": 38,
        "test_declarations": 75,
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


def test_component_package_cli_check_and_data_entry_scaffolds():
    check = CliRunner().invoke(app, ["components", "check", "--format", "json"])
    tree = CliRunner().invoke(
        app, ["scaffold", "control.tree-select", "--id", "location", "--format", "json"]
    )
    date = CliRunner().invoke(
        app, ["scaffold", "control.range-picker", "--id", "window", "--format", "json"]
    )
    flat = CliRunner().invoke(
        app, ["scaffold", "control.select", "--id", "region", "--format", "json"]
    )
    radio = CliRunner().invoke(
        app, ["scaffold", "control.radio-group", "--id", "status", "--format", "json"]
    )
    checkbox = CliRunner().invoke(
        app, ["scaffold", "control.checkbox-group", "--id", "channel", "--format", "json"]
    )
    docs = CliRunner().invoke(app, ["docs", "controls", "--format", "json"])
    component = CliRunner().invoke(
        app, ["components", "show", "control.select", "--format", "json"]
    )

    assert check.exit_code == 0, check.stdout
    assert json.loads(check.stdout)["valid"] is True
    tree_files = json.loads(tree.stdout)["files"]
    tree_selection = yaml.safe_load(tree_files["dashboard.control.snippet.yaml"])[0]
    assert tree_selection["path_fields"] == ["province", "city", "district"]
    date_selection = yaml.safe_load(json.loads(date.stdout)["files"]["dashboard.control.snippet.yaml"])[0]
    assert date_selection["type"] == "range_input"
    assert date_selection["value_type"] == "date"
    flat_selection = yaml.safe_load(json.loads(flat.stdout)["files"]["dashboard.control.snippet.yaml"])[0]
    assert flat_selection["type"] == "multiple_select"
    assert flat_selection["options"]["mode"] == "static"
    assert [item["value"] for item in flat_selection["options"]["choices"]] == [
        "alpha",
        "beta",
    ]
    radio_control = yaml.safe_load(
        json.loads(radio.stdout)["files"]["dashboard.control.snippet.yaml"]
    )[0]
    checkbox_selection = yaml.safe_load(
        json.loads(checkbox.stdout)["files"]["dashboard.control.snippet.yaml"]
    )[0]
    assert radio_control["type"] == "single_select"
    assert radio_control["initial"] == {"mode": "value", "value": "alpha"}
    assert checkbox_selection["type"] == "multiple_select"
    assert checkbox_selection["initial"] == {
        "mode": "values",
        "values": ["alpha"],
    }
    assert yaml.safe_load(
        json.loads(checkbox.stdout)["files"]["presentation.control-component.snippet.yaml"]
    )["control_components"]["view:view-id/channel"]["component"] == "checkbox-group"
    docs_payload = json.loads(docs.stdout)
    assert set(docs_payload["component_choice"]) == {
        "auto", "input", "input-number", "auto-complete", "checkbox", "switch",
        "radio-group", "select", "checkbox-group", "cascader", "tree-select",
        "date-picker", "range-picker", "slider",
    }
    assert "auto/always/never" in docs_payload["component_choice"]["select"]
    documented_controls = yaml.safe_load(docs_payload["dashboard_example"])["controls"]
    assert all("kind" not in item for item in documented_controls)
    assert [item["id"] for item in documented_controls] == ["region", "simulations"]
    documented_inputs = yaml.safe_load(docs_payload["interactive_input_example"])
    assert set(documented_inputs) == {"control_inputs"}
    assert json.loads(component.stdout)["id"] == "control.select"


def test_every_scaffold_recipe_matches_the_current_strict_models():
    recipes = scaffold_recipes()

    assert len(recipes) == len(set(recipes))
    for recipe in recipes:
        payload = scaffold_recipe(recipe, "sample")
        files = payload["files"]
        assert payload["schema"] == "dataviz/scaffold/v1"

        if recipe in {"minimal", "interactive", "custom-renderer"}:
            assert files["workspace.yaml"]
            assert files["dashboards/sample/dashboard.yaml"]
        elif recipe == "dashboard":
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
        elif recipe.startswith("control."):
            control = yaml.safe_load(files["dashboard.control.snippet.yaml"])[0]
            assert "kind" not in control
            ControlDefinition.model_validate(control)
            presentation = next(
                iter(
                    yaml.safe_load(files["presentation.control-component.snippet.yaml"])[
                        "control_components"
                    ].values()
                )
            )
            PresentationControlComponentDefinition.model_validate(presentation)
        else:  # pragma: no cover - the catalog and this contract must evolve together
            raise AssertionError(f"Unhandled Scaffold recipe: {recipe}")

    image_files = scaffold_recipe("view.image", "sample")["files"]
    assert image_files["assets/image.svg"].startswith("<svg")
    selection_gallery = yaml.safe_load(
        scaffold_recipe("section.selection-gallery", "sample")["files"][
            "dashboard.section.snippet.yaml"
        ]
    )[0]
    assert selection_gallery["controls"][0]["id"] == "groups"
    assert selection_gallery["repeat"]["control"] == "groups"


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
    assert json.loads(catalog_result.stdout) == scaffold_catalog()
    assert scaffold_catalog()["default"] == "minimal"
    assert scaffold_catalog()["profiles"] == [
        "minimal", "interactive", "custom-renderer"
    ]

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


def test_authoring_routes_expose_only_the_required_document_closure():
    catalog = authoring_route_catalog()
    minimal = resolve_authoring_route("minimal")
    interactive = resolve_authoring_route("interactive")
    renderer = resolve_authoring_route(component="view.custom")
    transform = resolve_authoring_route(component="interactive-transform.browser-js")

    assert catalog["default"] == "minimal"
    assert set(catalog["routes"]) == {
        "minimal",
        "interactive",
        "custom-renderer",
        "cascading-selection",
        "view-filter",
        "browser-compute",
    }
    assert minimal["closure"] == ["minimal"]
    assert minimal["concepts"] == [
        "adapter", "source", "view", "layout"
    ]
    minimal_documents = json.dumps(minimal["documents"], ensure_ascii=False).lower()
    assert "control" not in minimal_documents
    assert "interactive-transform" not in minimal_documents
    assert "renderer-contract" not in minimal_documents
    assert interactive["closure"] == ["minimal", "interactive"]
    assert "control" in interactive["concepts"]
    assert "interactive-transform" in interactive["concepts"]
    assert renderer["task"] == "custom-renderer"
    assert renderer["component"] == "view.custom"
    assert "renderer-contract" in renderer["concepts"]
    assert transform["task"] == "interactive"
    assert transform["component_definition"]["id"] == "interactive-transform.browser-js"
    for payload in (minimal, interactive, renderer):
        for document in payload["documents"].values():
            assert set(document["requires"]) <= set(payload["concepts"])


def test_cli_docs_routes_tasks_and_components_without_loading_every_topic():
    minimal_result = CliRunner().invoke(
        app, ["docs", "--task", "minimal", "--format", "json"]
    )
    control_result = CliRunner().invoke(
        app, ["docs", "--component", "control.select", "--format", "json"]
    )

    assert minimal_result.exit_code == 0, minimal_result.stdout
    assert control_result.exit_code == 0, control_result.stdout
    minimal = json.loads(minimal_result.stdout)
    control = json.loads(control_result.stdout)
    assert minimal["task"] == "minimal"
    assert list(minimal["documents"]) == ["minimal-dashboard"]
    assert control["task"] == "interactive"
    assert control["component"] == "control.select"
    assert control["component_definition"]["id"] == "control.select"


@pytest.mark.parametrize(
    ("task", "document", "required_concept"),
    [
        ("cascading-selection", "cascading-selection", "option-domain"),
        ("view-filter", "view-filter", "control"),
        ("browser-compute", "browser-compute", "interactive-transform"),
    ],
)
def test_cli_docs_exposes_focused_interaction_task_contracts(
    task: str,
    document: str,
    required_concept: str,
):
    result = CliRunner().invoke(
        app, ["docs", "--task", task, "--format", "json"]
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    focused = payload["documents"][document]
    assert payload["task"] == task
    assert required_concept in payload["concepts"]
    assert focused["minimal_example"]
    assert focused["allowed_fields"]
    assert focused["common_errors"]
    assert focused["validation_commands"][-1].startswith("dataviz visual-check")


@pytest.mark.parametrize("profile", ["minimal", "interactive", "custom-renderer"])
def test_scaffold_profiles_run_validate_and_report(profile: str, tmp_path: Path):
    item_id = f"{profile}-example"
    root = tmp_path / profile
    payload = scaffold_recipe(profile, item_id)
    for relative, content in payload["files"].items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    workspace = load_workspace(root)
    assert validate_workspace(workspace) == []
    result = Executor(workspace).run(item_id, refresh=True)
    report = CanvasRenderer(workspace).write_report(
        workspace.dashboard(item_id), result, tmp_path / f"{profile}.html"
    )

    assert result.status == "ready"
    assert report.is_file()
    assert payload["scope"] == "workspace"
    assert [command.split()[1] for command in payload["verify"]] == [
        "validate", "report", "visual-check"
    ]


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
    assert set(distribution["effective_controls"]) == {"distribution"}
    assert set(distribution["templates"]["views"]) == {"bar"}

    assert set(revenue["sources"]) == {"orders", "targets"}
    assert set(revenue["dataset_transforms"]) == {"sales-metrics"}
    assert revenue["dashboard_logic"]["query_parameters"][0]["id"] == "target_factor"
    distribution_size = len(
        json.dumps(distribution, ensure_ascii=False, sort_keys=True, default=str).encode()
    )
    full_size = len(
        json.dumps(full, ensure_ascii=False, sort_keys=True, default=str).encode()
    )
    assert distribution_size < full_size


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
            "inspect",
            "context",
            str(MINIMAL_WORKSPACE),
            "sales-overview",
            "--focus",
            "component:control.cascader",
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
    assert context_payload["focus"] == "component:control.cascader"
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


def test_product_benchmark_exposes_only_the_runtime_contract():
    help_result = CliRunner().invoke(app, ["benchmark", "runtime", "--help"])
    assert help_result.exit_code == 0
    assert "--browser-runtime" not in help_result.stdout
    assert "--browser" in help_result.stdout
    assert "--repeat" in help_result.stdout
    assert "--query-param" in help_result.stdout
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
    with pytest.raises(ValidationError) as failure:
        DashboardDefinition.model_validate(
            {
                "schema": "dataviz/dashboard/v14",
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
                "schema": "dataviz/presentation/v2",
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
    assert 'data-control-component="cascader"' in html
    assert 'data-control-component="range-picker"' in html
    assert 'data-control-component="tree-select"' in html
    assert 'data-control-component="select"' in html
    assert 'data-control-component="radio-group"' in html
    assert 'data-control-component="checkbox-group"' in html
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
    assert "context.charts.plotly" in script
    assert "context.tables.tanstack" in script
    assert ".renderer-team-spark" in style
    assets = yaml.safe_load((target / "presentation.asset.snippet.yaml").read_text())
    assert assets["assets"]["css"] == ["assets/team.spark.css"]


def test_gallery_cli_never_writes_runtime_artifacts_into_the_installed_package(
    tmp_path: Path,
):
    before = {path.relative_to(GALLERY_WORKSPACE) for path in GALLERY_WORKSPACE.rglob("*")}
    output = tmp_path / "gallery.html"

    result = CliRunner().invoke(app, ["components", "gallery", "--output", str(output)])

    after = {path.relative_to(GALLERY_WORKSPACE) for path in GALLERY_WORKSPACE.rglob("*")}
    assert result.exit_code == 0, result.stdout
    assert output.is_file()
    exported = output.read_text(encoding="utf-8")
    assert "window.datavizComponentStories = [" in exported
    assert '"id": "control.select.scale-10"' in exported
    assert '"id": "control.select.scale-100"' in exported
    assert '"id": "control.select.scale-1000"' in exported
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
    assert "if (changedControlKeys == null) return null" in runtime
    assert declarative.index("view.template === 'markdown'") < declarative.index(
        "let rows = preparedRows"
    )
    assert declarative.index("view.template === 'image'") < declarative.index(
        "let rows = preparedRows"
    )
    assert "type:view.renderer" in declarative
    assert "controlBinding:binding" in declarative
    assert "const traces = groups.flatMap" in declarative


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
    assert "Object.entries(spec.inputs || {})" not in runtime
    assert "Object.entries(this.transformInputs(id))" in runtime
    assert "this.views.set(id, {inputs: {...expectedInputs}" in runtime

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
        expected_presentation = {"min_height", "container", "css_class"}
        expected_presentation.update(
            field
            for field in ("options", "config")
            if field in contract["optional"]
        )
        assert set(component["presentation"]["options"]) == expected_presentation

    table = catalog["view.table"]
    line = catalog["view.line"]
    image = catalog["view.image"]
    radar = catalog["view.radar"]

    assert table["presentation"]["options"] == [
        "min_height",
        "container",
        "css_class",
        "options",
    ]
    assert {"options", "config"} <= set(line["presentation"]["options"])
    assert "engine" not in line["logic"]["optional"]
    assert "engine" not in line["presentation"]["options"]
    assert image["behavior"]["input"] == "Self-contained; consumes no Named Output"
    assert "engine" not in radar["logic"]
