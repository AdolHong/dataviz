from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import time

import pytest
import yaml
from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.errors import ValidationFailure
from dataviz.execution.dependencies import (
    DEPENDENCY_CONTRACT_SCHEMA,
)
from dataviz.execution.plan import compile_plan
from dataviz.workspace import load_workspace
from dataviz.workspace.loading import loaded_types


ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "examples" / "feature-showcase"
SALES = ROOT / "examples" / "sales-workspace"
WORKER = ROOT / "tests" / "fixtures" / "browser-worker-workspace"
PROGRESSIVE = ROOT / "tests" / "fixtures" / "progressive-workspace"
MINIMAL = ROOT / "examples" / "minimal-workspace"


def _copy_cascade_workspace(tmp_path: Path) -> tuple[Path, Path, dict]:
    workspace = tmp_path / "workspace"
    shutil.copytree(FEATURES, workspace)
    dashboard_path = workspace / "dashboards" / "功能示例##cascade-explorer" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    return workspace, dashboard_path, definition


def _city_detail(definition: dict) -> dict:
    return next(view for view in definition["views"] if view["id"] == "city-detail")


def _copy_bound_view_workspace(tmp_path: Path) -> tuple[Path, Path, dict]:
    workspace = tmp_path / "bound-view"
    shutil.copytree(MINIMAL, workspace)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    view = next(item for item in definition["views"] if item["id"] == "region-comparison")
    view["control_binding"] = "dashboard.region"
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return workspace, dashboard_path, definition


def test_query_graph_and_progressive_targets_share_one_compiled_closure():
    dashboard = load_workspace(PROGRESSIVE).dashboard("progressive")
    contract = dashboard.dependency_contract

    assert dashboard.dependency_contract is contract

    assert contract.query_order == ("source:fast", "source:slow")
    assert contract.base_output_roots == (
        "source:fast/main",
        "source:slow/main",
    )
    assert contract.query_closure(["source:fast"]) == {"source:fast"}
    assert set(compile_plan(dashboard, targets=["source:fast"]).nodes) == {"source:fast"}


def test_dependency_contract_compiles_once_under_concurrent_first_access(
    monkeypatch: pytest.MonkeyPatch,
):
    dashboard = load_workspace(PROGRESSIVE).dashboard("progressive")
    dashboard._dependency_contract = None
    original = loaded_types.compile_dashboard_dependencies
    calls = 0

    def compile_once(item):
        nonlocal calls
        calls += 1
        time.sleep(0.02)
        return original(item)

    monkeypatch.setattr(loaded_types, "compile_dashboard_dependencies", compile_once)
    with ThreadPoolExecutor(max_workers=8) as pool:
        contracts = list(pool.map(lambda _: dashboard.dependency_contract, range(16)))

    assert calls == 1
    assert all(contract is contracts[0] for contract in contracts)


def test_selection_domains_and_control_effects_are_explicit():
    dashboard = load_workspace(FEATURES).dashboard("cascade-explorer")
    contract = dashboard.dependency_contract

    province = contract.controls["dashboard:cascade-explorer/province"]
    city = contract.controls["section:geography/city"]
    district = contract.controls["view:city-detail/district"]

    assert province.scope_views == (
        "bundled-file",
        "city-detail",
        "map-bars",
        "uploaded-file",
    )
    assert province.direct_views == province.affected_views
    assert province.transform_consumers == ()
    assert province.depends_on == ()
    assert province.dependency_ancestors == ()
    assert province.dependency_descendants == (
        "section:geography/city",
        "view:city-detail/district",
    )
    assert city.option_domain_references == ("source:cities/main",)
    assert city.direct_views == ("city-detail", "map-bars")
    assert city.depends_on == ("dashboard:cascade-explorer/province",)
    assert city.dependency_ancestors == ("dashboard:cascade-explorer/province",)
    assert city.dependency_descendants == ("view:city-detail/district",)
    assert district.option_domain_references == ("source:cities/main",)
    assert district.direct_views == ("city-detail",)
    assert district.depends_on == ("section:geography/city",)
    assert district.dependency_ancestors == (
        "dashboard:cascade-explorer/province",
        "section:geography/city",
    )
    assert district.direct_view_bindings["city-detail"].fields == (
        "province",
        "city",
        "district",
    )
    assert district.direct_view_bindings["city-detail"].input_references == ("source:cities/main",)


def test_view_control_binding_compiles_one_writer_and_projection_edge(tmp_path: Path):
    workspace, _, _ = _copy_bound_view_workspace(tmp_path)
    contract = load_workspace(workspace).dashboard("sales-overview").dependency_contract

    binding = contract.view_control_bindings["region-comparison"]
    assert binding.control == "dashboard:sales-overview/region"
    assert binding.fields == ("region",)
    assert binding.renderer == "plotly"
    control = contract.controls["dashboard:sales-overview/region"]
    assert control.writer_view == "region-comparison"
    assert control.writer_fields == ("region",)
    assert "region-comparison" in control.affected_views
    assert contract.runtime_manifest()["views"]["region-comparison"]["control_binding"][
        "actions"
    ] == ["select", "select_many", "clear", "reset"]


def test_view_control_binding_rejects_a_second_writer(tmp_path: Path):
    workspace, dashboard_path, definition = _copy_bound_view_workspace(tmp_path)
    second = next(item for item in definition["views"] if item["id"] == "revenue-trend")
    second["control_binding"] = "dashboard.region"
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ValidationFailure) as caught:
        _ = load_workspace(workspace).dashboard("sales-overview").dependency_contract
    assert caught.value.as_dict()["code"] == "view_control_binding_writer_conflict"


def test_view_control_binding_rejects_narrower_candidate_selection(tmp_path: Path):
    workspace, dashboard_path, definition = _copy_bound_view_workspace(tmp_path)
    view = next(item for item in definition["views"] if item["id"] == "region-comparison")
    view["controls"] = [
        {
            "id": "city",

            "type": "single_select",
            "value_type": "text",
            "field": "city",
            "initial": {"mode": "empty"},
            "options": {"mode": "infer"},
        }
    ]
    view.setdefault("control_inputs", {})["city"] = {
        "mode": "filter",
        "control": "view.city",
        "field": "city",
        "inputs": ["main"],
        "empty": "passthrough",
    }
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ValidationFailure) as caught:
        _ = load_workspace(workspace).dashboard("sales-overview").dependency_contract
    assert caught.value.as_dict()["code"] == "view_control_binding_reverse_scope"


def test_same_view_dependencies_compile_direct_edges_transitive_closure_and_order(
    tmp_path: Path,
):
    workspace, dashboard_path, definition = _copy_cascade_workspace(tmp_path)
    controls = _city_detail(definition)["controls"]
    controls[0:0] = [
        {
            "id": "dow",

            "field": "city",
            "type": "single_select",
            "value_type": "text",
            "depends_on": ["section.city"],
            "options": {
                "mode": "static",
                "choices": [
                    {"label": "深圳", "value": "深圳"},
                    {"label": "厦门", "value": "厦门"},
                ],
            },
        },
        {
            "id": "dates",

            "field": "district",
            "type": "multiple_select",
            "value_type": "text",
            "depends_on": ["view.dow"],
            "options": {"mode": "infer", "source": "source:cities/main"},
        },
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    contract = load_workspace(workspace).dashboard("cascade-explorer").dependency_contract
    dow_key = "view:city-detail/dow"
    dates_key = "view:city-detail/dates"
    province_key = "dashboard:cascade-explorer/province"
    city_key = "section:geography/city"

    assert contract.controls[dow_key].depends_on == (city_key,)
    assert contract.controls[dates_key].depends_on == (dow_key,)
    assert contract.controls[dates_key].dependency_ancestors == (
        province_key,
        city_key,
        dow_key,
    )
    assert contract.controls[province_key].dependency_descendants == (
        city_key,
        dates_key,
        "view:city-detail/district",
        dow_key,
    )
    positions = {key: index for index, key in enumerate(contract.control_order)}
    assert positions[province_key] < positions[city_key] < positions[dow_key] < positions[dates_key]


@pytest.mark.parametrize(
    ("reference", "expected_code"),
    [
        ("section.city", "control_dependency_scope_invalid"),
        ("dashboard.missing", "control_dependency_unknown"),
    ],
)
def test_control_dependencies_reject_invalid_scope_and_unknown_parent(
    tmp_path: Path,
    reference: str,
    expected_code: str,
):
    workspace, dashboard_path, definition = _copy_cascade_workspace(tmp_path)
    definition["controls"][0]["depends_on"] = [reference]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    dashboard = load_workspace(workspace).dashboard("cascade-explorer")
    with pytest.raises(ValidationFailure) as caught:
        _ = dashboard.dependency_contract
    assert caught.value.as_dict()["code"] == expected_code


def test_control_dependencies_accept_typed_parent_and_report_full_cycle(
    tmp_path: Path,
):
    workspace, dashboard_path, definition = _copy_cascade_workspace(tmp_path)
    controls = _city_detail(definition)["controls"]
    controls.extend(
        [
            {
                "id": "seed",

                "type": "single_input",
                "value_type": "integer",
                "default": 42,
            },
            {
                "id": "dow",

                "field": "city",
                "type": "multiple_select",
                "value_type": "text",
                "depends_on": ["view.seed"],
                "options": {"mode": "infer", "source": "source:cities/main"},
            },
        ]
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    dashboard = load_workspace(workspace).dashboard("cascade-explorer")
    contract = dashboard.dependency_contract
    assert contract.controls["view:city-detail/dow"].depends_on == (
        "view:city-detail/seed",
    )

    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    controls = _city_detail(definition)["controls"]
    controls.pop()  # dow from the typed-parent case
    controls.extend(
        [
            {
                "id": "first",

                "field": "city",
                "type": "multiple_select",
                "value_type": "text",
                "depends_on": ["view.second"],
                "options": {"mode": "infer", "source": "source:cities/main"},
            },
            {
                "id": "second",

                "field": "district",
                "type": "multiple_select",
                "value_type": "text",
                "depends_on": ["view.first"],
                "options": {"mode": "infer", "source": "source:cities/main"},
            },
        ]
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    dashboard = load_workspace(workspace).dashboard("cascade-explorer")
    with pytest.raises(ValidationFailure) as caught:
        _ = dashboard.dependency_contract
    payload = caught.value.as_dict()
    assert payload["code"] == "control_dependency_cycle"
    assert payload["details"]["cycle"] == [
        "view:city-detail/first",
        "view:city-detail/second",
        "view:city-detail/first",
    ]


def test_control_paths_distinguish_direct_and_derived_consumers():
    dashboard = load_workspace(FEATURES).dashboard("chart-gallery")
    contract = dashboard.dependency_contract

    assert contract.reachable_interactive_order == ("latest-metrics",)
    assert contract.base_output_roots == ("source:metrics/main",)
    assert contract.transform_direct_views["latest-metrics"] == ("radial",)
    assert contract.transform_downstream_views["latest-metrics"] == ("radial",)

    city_count = contract.controls["dashboard:chart-gallery/radar_city_count"]
    assert city_count.direct_views == ()
    assert city_count.transform_consumers == ("latest-metrics",)
    assert city_count.transform_inputs == {"latest-metrics": ("city_count",)}
    assert city_count.derived_views == ("radial",)
    assert city_count.affected_views == ("radial",)

    province = contract.controls["dashboard:chart-gallery/province"]
    assert province.transform_consumers == ("latest-metrics",)
    assert province.transform_inputs == {"latest-metrics": ("province",)}
    assert province.derived_views == ("radial",)
    assert province.direct_views == tuple(
        sorted(set(contract.view_inputs) - {"radial"})
    )
    assert province.affected_views == tuple(sorted(contract.view_inputs))


def test_runtime_manifest_is_a_projection_of_the_same_contract():
    dashboard = load_workspace(WORKER).dashboard("worker-runtime")
    contract = dashboard.dependency_contract
    manifest = contract.runtime_manifest()

    assert manifest["schema"] == DEPENDENCY_CONTRACT_SCHEMA
    assert manifest["interactive"]["order"] == ["scaled"]
    assert manifest["interactive"]["inputs"] == {"scaled": {"rows": "source:raw/main"}}
    assert manifest["interactive"]["outputs"] == {"scaled": ["interactive:scaled/main"]}
    assert manifest["interactive"]["dependencies"] == {"scaled": []}
    assert manifest["interactive"]["control_inputs"] == {
        "scaled": {
            "delay_ms": {
                "control": "dashboard:worker-runtime/delay_ms",
                "mode": "value",
                "projection": "value",
            }
        }
    }
    assert manifest["views"]["scaled-table"]["inputs"] == {"main": "interactive:scaled/main"}
    assert manifest["views"]["scaled-table"]["pipeline_nodes"] == [
        "source:raw",
        "interactive:scaled",
    ]
    assert contract.view_pipeline_nodes("scaled-table") == (
        "source:raw",
        "interactive:scaled",
    )
    delay = manifest["controls"]["dashboard:worker-runtime/delay_ms"]
    assert delay["direct_views"] == []
    assert delay["derived_views"] == ["scaled-table"]
    assert delay["affected_views"] == ["scaled-table"]


def test_query_parameter_consumers_are_compiled_once():
    dashboard = load_workspace(SALES).dashboard("sales")
    contract = dashboard.dependency_contract

    assert contract.query_parameter_consumers["target_factor"] == ("source:targets",)
    assert contract.parameter_inputs["source:targets"] == {
        "target_factor": {"parameter": "target_factor"}
    }
    assert contract.parameter_inputs["source:orders"] == {}
    target_factor = contract.query_parameters["target_factor"]
    assert target_factor.direct_query_nodes == ("source:targets",)
    assert target_factor.affected_query_nodes == (
        "dataset:sales-metrics",
        "source:targets",
    )
    assert target_factor.affected_option_controls == ()
    assert target_factor.affected_views == (
        "revenue",
        "target",
    )
    assert contract.query_node_downstream_views["source:orders"] == (
        "detail",
        "distribution",
        "revenue",
        "target",
    )
    plan = compile_plan(dashboard)
    assert set(plan.nodes["source:targets"].parameter_inputs) == {"target_factor"}
    assert plan.nodes["source:orders"].parameter_inputs == {}
    assert contract.query_closure(["dataset:sales-metrics"]) == {
        "source:orders",
        "source:targets",
        "dataset:sales-metrics",
    }


def test_dependency_contract_is_directly_inspectable_by_ai_and_humans():
    machine = CliRunner().invoke(
        app,
        ["inspect", "dependencies", str(FEATURES), "chart-gallery", "--format", "json"],
    )
    human = CliRunner().invoke(
        app,
        ["inspect", "dependencies", str(FEATURES), "chart-gallery"],
    )

    assert machine.exit_code == 0, machine.stdout
    assert machine.stdout.lstrip().startswith("{")
    assert '"schema": "dataviz/dependency-contract/v7"' in machine.stdout
    assert human.exit_code == 0, human.stdout
    assert "Query DAG" in human.stdout
    assert "Query Parameters" in human.stdout
    assert "Interactive DAG" in human.stdout
    assert "radar_city_count" in human.stdout


def test_dependency_contract_rejects_server_runtime_after_browser_runtime(
    tmp_path: Path,
):
    workspace = tmp_path / "workspace"
    shutil.copytree(WORKER, workspace)
    dashboard_root = workspace / "dashboards" / "worker-runtime"
    dashboard_path = dashboard_root / "dashboard.yaml"
    dashboard_path.write_text(
        dashboard_path.read_text(encoding="utf-8").replace(
            "  - transforms/scaled.yaml\n",
            "  - transforms/scaled.yaml\n  - transforms/server.yaml\n",
        ),
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "server.yaml").write_text(
        """schema: dataviz/interactive-transform/v3
kind: interactive_transform
id: server
runtime: server-python
code: server.py
inputs: {rows: interactive:scaled/main}
export: {mode: snapshot}
outputs: {main: {kind: table}}
""",
        encoding="utf-8",
    )
    (dashboard_root / "transforms" / "server.py").write_text(
        "def transform(context):\n    return {'main': context.inputs['rows']}\n",
        encoding="utf-8",
    )

    dashboard = load_workspace(workspace).dashboard("worker-runtime")
    with pytest.raises(ValidationFailure) as caught:
        _ = dashboard.dependency_contract

    assert caught.value.as_dict()["code"] == "server_interactive_depends_on_browser"


def test_dependency_contract_rejects_control_consumed_outside_its_scope(
    tmp_path: Path,
):
    workspace = tmp_path / "workspace"
    shutil.copytree(WORKER, workspace)
    dashboard_root = workspace / "dashboards" / "worker-runtime"
    dashboard_path = dashboard_root / "dashboard.yaml"
    dashboard_path.write_text(
        dashboard_path.read_text(encoding="utf-8")
        + """
  - id: hidden-controls
    title: Hidden controls
    controls:
      - {id: rogue, type: single_input, value_type: integer, default: 1}
""",
        encoding="utf-8",
    )
    transform_path = dashboard_root / "transforms" / "scaled.yaml"
    transform_path.write_text(
        transform_path.read_text(encoding="utf-8").replace(
            "dashboard:worker-runtime/delay_ms",
            "section:hidden-controls/rogue",
        ),
        encoding="utf-8",
    )

    dashboard = load_workspace(workspace).dashboard("worker-runtime")
    with pytest.raises(ValidationFailure) as caught:
        _ = dashboard.dependency_contract

    assert caught.value.as_dict()["code"] == "interactive_control_out_of_scope"
