from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from typer.testing import CliRunner

from dataviz.analysis.catalog import ensure_analysis_catalog
from dataviz.cli import app
from dataviz.execution.interactive import compile_interactive_plan
from dataviz.execution.plan import compile_plan
from dataviz.workspace import load_workspace


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZATION = json.loads(
    (ROOT / "tests" / "fixtures" / "dependency-v11-characterization.json").read_text(
        encoding="utf-8"
    )
)


def _digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _query_plan_projection(dashboard) -> dict:
    plan = compile_plan(dashboard)
    return {
        "targets": sorted(plan.targets),
        "nodes": {
            node_id: {
                "kind": node.kind,
                "dependencies": sorted(node.dependencies),
                "inputs": {alias: reference.canonical for alias, reference in node.inputs.items()},
                "parameter_inputs": node.parameter_inputs,
            }
            for node_id, node in plan.nodes.items()
        },
    }


def _interactive_plan_projection(dashboard, target: str) -> list[dict]:
    return [
        {
            "id": node.id,
            "dependencies": sorted(node.dependencies),
            "inputs": {alias: reference.canonical for alias, reference in node.inputs.items()},
            "query_inputs": node.query_inputs,
            "control_inputs": node.control_inputs,
        }
        for node in compile_interactive_plan(dashboard, target)
    ]


def test_dependency_v11_contract_manifest_layout_and_plans_are_characterized():
    assert CHARACTERIZATION["schema"] == "dataviz/dependency-characterization/v1"
    for expected in CHARACTERIZATION["cases"].values():
        workspace = load_workspace(ROOT / expected["workspace"])
        dashboard = workspace.dashboard(expected["dashboard"])
        contract = dashboard.dependency_contract

        assert _digest(contract.as_dict()) == expected["contract_sha256"]
        assert _digest(contract.runtime_manifest()) == expected["runtime_manifest_sha256"]
        assert _digest(dashboard.layout_contract.as_dict()) == expected["layout_sha256"]
        assert _query_plan_projection(dashboard) == expected["query_plan"]
        assert {
            target: _interactive_plan_projection(dashboard, target)
            for target in contract.reachable_interactive_order
        } == expected["interactive_plans"]


def test_inspect_dependencies_is_the_exact_contract_projection():
    expected = CHARACTERIZATION["cases"]["chart-gallery"]
    workspace_path = ROOT / expected["workspace"]
    dashboard = load_workspace(workspace_path).dashboard(expected["dashboard"])
    result = CliRunner().invoke(
        app,
        [
            "inspect",
            "dependencies",
            str(workspace_path),
            expected["dashboard"],
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == dashboard.dependency_contract.as_dict()


def test_catalog_projection_is_unchanged_by_dependency_modularization(tmp_path: Path):
    expected = CHARACTERIZATION["cases"]["chart-gallery"]
    workspace_path = tmp_path / "workspace"
    shutil.copytree(
        ROOT / expected["workspace"],
        workspace_path,
        ignore=shutil.ignore_patterns(".dataviz", "__pycache__", "*.pyc"),
    )
    catalog = ensure_analysis_catalog(workspace_path)
    entries = [
        entry
        for entry in catalog.entries
        if entry.get("dashboard", {}).get("id") == expected["dashboard"]
    ]

    assert len(entries) == expected["catalog_entry_count"]
    assert _digest(entries) == expected["catalog_entries_sha256"]
