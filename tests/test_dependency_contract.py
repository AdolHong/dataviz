from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import time

import pytest
from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.errors import ValidationFailure
from dataviz.execution.dependencies import (
    DEPENDENCY_CONTRACT_SCHEMA,
)
from dataviz.execution.plan import compile_plan
from dataviz.workspace import load_workspace
from dataviz.workspace import loader as loader_module


ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "examples" / "feature-showcase"
SALES = ROOT / "examples" / "sales-workspace"
WORKER = ROOT / "tests" / "fixtures" / "browser-worker-workspace"
PROGRESSIVE = ROOT / "tests" / "fixtures" / "progressive-workspace"


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
    assert set(compile_plan(dashboard, targets=["source:fast"]).nodes) == {
        "source:fast"
    }


def test_dependency_contract_compiles_once_under_concurrent_first_access(
    monkeypatch: pytest.MonkeyPatch,
):
    dashboard = load_workspace(PROGRESSIVE).dashboard("progressive")
    dashboard._dependency_contract = None
    original = loader_module.compile_dashboard_dependencies
    calls = 0

    def compile_once(item):
        nonlocal calls
        calls += 1
        time.sleep(0.02)
        return original(item)

    monkeypatch.setattr(loader_module, "compile_dashboard_dependencies", compile_once)
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
    assert province.cascade_upstream == ()
    assert province.cascade_downstream == (
        "section:geography/city",
        "view:city-detail/district",
    )
    assert city.option_domain_references == ("source:cities/main",)
    assert city.direct_views == ("city-detail", "map-bars")
    assert city.cascade_upstream == ("dashboard:cascade-explorer/province",)
    assert city.cascade_downstream == ("view:city-detail/district",)
    assert district.option_domain_references == ("source:cities/main",)
    assert district.direct_views == ("city-detail",)
    assert district.cascade_upstream == (
        "dashboard:cascade-explorer/province",
        "section:geography/city",
    )
    assert district.direct_view_bindings["city-detail"].fields == (
        "province",
        "city",
        "district",
    )
    assert district.direct_view_bindings["city-detail"].input_references == (
        "source:cities/main",
    )


def test_compute_and_selection_paths_distinguish_direct_and_derived_views():
    dashboard = load_workspace(FEATURES).dashboard("chart-gallery")
    contract = dashboard.dependency_contract

    assert contract.reachable_interactive_order == ("latest-metrics",)
    assert contract.base_output_roots == ("source:metrics/main",)
    assert contract.transform_direct_views["latest-metrics"] == ("radial",)
    assert contract.transform_downstream_views["latest-metrics"] == ("radial",)

    compute = contract.controls["dashboard:chart-gallery/radar_city_count"]
    assert compute.direct_views == ()
    assert compute.transform_consumers == ("latest-metrics",)
    assert compute.transform_inputs == {"latest-metrics": ("city_count",)}
    assert compute.derived_views == ("radial",)
    assert compute.affected_views == ("radial",)

    selection = contract.controls["dashboard:chart-gallery/province"]
    assert selection.transform_consumers == ("latest-metrics",)
    assert selection.transform_inputs == {"latest-metrics": ("province",)}
    assert selection.derived_views == ("radial",)
    assert selection.direct_views == tuple(sorted(contract.view_inputs))
    assert selection.affected_views == selection.direct_views


def test_runtime_manifest_is_a_projection_of_the_same_contract():
    dashboard = load_workspace(WORKER).dashboard("worker-runtime")
    contract = dashboard.dependency_contract
    manifest = contract.runtime_manifest()

    assert manifest["schema"] == DEPENDENCY_CONTRACT_SCHEMA
    assert manifest["interactive"]["order"] == ["scaled"]
    assert manifest["interactive"]["inputs"] == {
        "scaled": {"rows": "source:raw/main"}
    }
    assert manifest["interactive"]["outputs"] == {
        "scaled": ["interactive:scaled/main"]
    }
    assert manifest["interactive"]["dependencies"] == {"scaled": []}
    assert manifest["interactive"]["compute_inputs"] == {
        "scaled": {"delay_ms": "dashboard:worker-runtime/delay_ms"}
    }
    assert manifest["views"]["scaled-table"]["inputs"] == {
        "main": "interactive:scaled/main"
    }
    compute = manifest["controls"]["dashboard:worker-runtime/delay_ms"]
    assert compute["direct_views"] == []
    assert compute["derived_views"] == ["scaled-table"]
    assert compute["affected_views"] == ["scaled-table"]


def test_query_parameter_consumers_are_compiled_once():
    dashboard = load_workspace(SALES).dashboard("sales")
    contract = dashboard.dependency_contract

    assert contract.query_parameter_consumers["target_factor"] == (
        "source:targets",
    )
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
    assert target_factor.affected_option_controls == ("dashboard:sales/region",)
    assert target_factor.affected_views == (
        "detail",
        "distribution",
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
        ["dependencies", str(FEATURES), "chart-gallery", "--format", "json"],
    )
    human = CliRunner().invoke(
        app,
        ["dependencies", str(FEATURES), "chart-gallery"],
    )

    assert machine.exit_code == 0, machine.stdout
    assert machine.stdout.lstrip().startswith("{")
    assert '"schema": "dataviz/dependency-contract/v2"' in machine.stdout
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
        """schema: dataviz/interactive-transform/v2
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
      - {id: rogue, kind: compute, type: integer, default: 1}
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
