from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.validation import VALIDATION_SCHEMA, validate_preflight


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_WORKSPACE = ROOT / "examples" / "minimal-workspace"


def _copy_workspace(tmp_path: Path) -> Path:
    destination = tmp_path / "workspace"
    shutil.copytree(MINIMAL_WORKSPACE, destination)
    return destination


def _browser_python_workspace(
    root: Path,
    *,
    dependency: str = "duckdb==1.5.1",
    assets: str = "cdn",
    bundle_path: str | None = None,
) -> Path:
    dashboard = root / "dashboards" / "browser-python"
    (dashboard / "data").mkdir(parents=True)
    (dashboard / "transforms").mkdir()
    runtime = f"\n  pyodide_bundle_path: {bundle_path}" if bundle_path else ""
    (root / "workspace.yaml").write_text(
        f"""schema: dataviz/workspace/v1
kind: workspace
id: browser-python
title: Browser Python
runtime:{runtime or ' {}'}
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v2
kind: dashboard
id: browser-python
title: Browser Python
sources:
  - id: raw
    type: file
    path: data/rows.csv
    format: csv
    outputs: {main: {kind: table}}
interactive_transforms: [transforms/calculate.yaml]
views:
  - {id: result, template: table, input: interactive:calculate/main}
sections:
  - {id: result, title: Result, views: [result]}
""",
        encoding="utf-8",
    )
    (dashboard / "data" / "rows.csv").write_text("value\n1\n", encoding="utf-8")
    (dashboard / "transforms" / "calculate.yaml").write_text(
        f"""schema: dataviz/interactive-transform/v1
kind: interactive_transform
id: calculate
runtime: browser-python
code: calculate.py
inputs: {{rows: source:raw/main}}
export: {{mode: interactive, assets: {assets}}}
outputs: {{main: {{kind: table}}}}
python_dependencies: [{dependency}]
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "calculate.py").write_text(
        "def transform(context):\n    return {'main': context.inputs['rows']}\n",
        encoding="utf-8",
    )
    return root


def _write_pyodide_bundle(root: Path) -> None:
    bundle = root / "pyodide"
    bundle.mkdir(exist_ok=True)
    for name in (
        "pyodide.mjs",
        "pyodide.asm.mjs",
        "pyodide.asm.wasm",
        "python_stdlib.zip",
    ):
        (bundle / name).write_bytes(f"fixture:{name}".encode())
    packages = {}
    for name, version, dependencies in (
        ("micropip", "0.11.1", []),
        ("duckdb", "1.5.1", ["numpy"]),
        ("numpy", "2.4.3", []),
    ):
        filename = f"{name}-{version}.whl"
        content = f"fixture:{name}:{version}".encode()
        (bundle / filename).write_bytes(content)
        packages[name] = {
            "name": name,
            "version": version,
            "depends": dependencies,
            "file_name": filename,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    (bundle / "pyodide-lock.json").write_text(
        json.dumps({"info": {"python": "3.14.0"}, "packages": packages}),
        encoding="utf-8",
    )


def test_validate_preflight_has_stable_ai_contract_and_dashboard_scope(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)

    report = validate_preflight(workspace, dashboard_id="sales-overview")

    assert report["schema"] == VALIDATION_SCHEMA
    assert report["mode"] == "static-preflight"
    assert report["queries_executed"] == 0
    assert report["status"] == "valid"
    assert report["passed"] is True
    assert report["scope"] == {
        "dashboard": "sales-overview",
        "path": "dashboards/sales-overview",
    }
    assert report["summary"]["dashboards_checked"] == 1
    assert {item["id"] for item in report["checks"]} >= {
        "schema-contracts",
        "sql-contracts",
        "data-graph",
    }


def test_validate_detects_undeclared_and_unused_sql_parameters(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    sql = workspace / "dashboards" / "sales-overview" / "sources" / "sales.sql"
    sql.write_text(sql.read_text(encoding="utf-8").replace("$min_query_revenue", "$minimum"), encoding="utf-8")

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostics = {item["code"]: item for item in report["diagnostics"]}

    assert report["status"] == "invalid"
    assert report["passed"] is False
    assert diagnostics["sql_parameter_undeclared"]["details"]["parameters"] == ["minimum"]
    assert diagnostics["sql_parameter_unused"]["details"]["parameters"] == ["min_query_revenue"]
    assert diagnostics["sql_parameter_undeclared"]["category"] == "sql-contracts"
    assert "Source `query_params`" in diagnostics["sql_parameter_undeclared"]["hint"]


def test_validate_strict_turns_warning_into_nonzero_cli_exit(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    sql = workspace / "dashboards" / "sales-overview" / "sources" / "sales.sql"
    sql.write_text(
        sql.read_text(encoding="utf-8").replace(
            "where revenue >= $min_query_revenue\n", ""
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    normal = runner.invoke(app, ["validate", str(workspace), "--format", "json"])
    strict = runner.invoke(
        app,
        ["validate", str(workspace), "--format", "json", "--strict"],
    )

    assert normal.exit_code == 0, normal.output
    assert json.loads(normal.output)["status"] == "valid_with_warnings"
    assert strict.exit_code == 1, strict.output
    strict_report = json.loads(strict.output)
    assert strict_report["status"] == "valid_with_warnings"
    assert strict_report["passed"] is False
    assert strict_report["exit_code"] == 1


def test_validate_focus_excludes_another_broken_dashboard(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    broken = workspace / "dashboards" / "broken"
    broken.mkdir()
    (broken / "dashboard.yaml").write_text(
        "schema: dataviz/dashboard/v2\nkind: dashboard\nid: broken\nretired_field: true\n",
        encoding="utf-8",
    )

    full = validate_preflight(workspace)
    focused = validate_preflight(workspace, dashboard_id="sales-overview")

    assert full["status"] == "invalid"
    invalid = next(item for item in full["diagnostics"] if item["code"] == "dashboard_invalid")
    assert invalid["file"] == "dashboards/broken/dashboard.yaml"
    assert invalid["field"] == "retired_field"
    assert invalid["details"]
    assert focused["status"] == "valid"
    assert focused["diagnostics"] == []


def test_validate_unknown_dashboard_is_structured_json(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "validate",
            str(workspace),
            "--dashboard",
            "missing",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1, result.output
    report = json.loads(result.output)
    diagnostic = next(item for item in report["diagnostics"] if item["code"] == "dashboard_not_found")
    assert report["schema"] == VALIDATION_SCHEMA
    assert report["queries_executed"] == 0
    assert diagnostic["details"]["available"] == ["sales-overview"]
    assert "dataviz list" in diagnostic["hint"]


def test_cli_docs_publish_the_validation_workflow():
    result = CliRunner().invoke(
        app,
        ["docs", "validation", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    topic = json.loads(result.output)
    assert topic["topic"] == "validation"
    assert "--dashboard" in topic["recommended_command"]
    assert topic["json_contract"]["queries_executed"].startswith("固定为 0")
    assert "sql_parameter_undeclared" in topic["sql_parameter_example"]["errors"]


def test_validate_uses_the_pinned_pyodide_package_catalog(tmp_path: Path):
    supported = validate_preflight(
        _browser_python_workspace(tmp_path / "supported")
    )
    assert not [
        item
        for item in supported["diagnostics"]
        if item["code"].startswith("pyodide_dependency_")
    ]

    mismatched = validate_preflight(
        _browser_python_workspace(
            tmp_path / "mismatched", dependency="duckdb==1.4.0"
        )
    )
    diagnostic = next(
        item
        for item in mismatched["diagnostics"]
        if item["code"] == "pyodide_dependency_version_mismatch"
    )
    assert "duckdb==1.5.1" in diagnostic["message"]


def test_validate_checks_export_only_pyodide_bundle_contents(tmp_path: Path):
    root = _browser_python_workspace(
        tmp_path / "bundle",
        assets="bundle",
        bundle_path="pyodide",
    )
    (root / "pyodide").mkdir()

    report = validate_preflight(root)

    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "pyodide_bundle_incomplete"
    )
    assert diagnostic["field"] == "runtime.pyodide_bundle_path"
    assert diagnostic["category"] == "runtime-dependencies"
    assert "complete official Pyodide distribution" in diagnostic["hint"]
    assert diagnostic["details"]["missing"] == [
        "pyodide.mjs",
        "pyodide.asm.mjs",
        "pyodide.asm.wasm",
        "python_stdlib.zip",
        "pyodide-lock.json",
    ]


def test_validate_checks_pyodide_bundle_dependency_closure_and_hashes(tmp_path: Path):
    root = _browser_python_workspace(
        tmp_path / "bundle",
        assets="bundle",
        bundle_path="pyodide",
    )
    _write_pyodide_bundle(root)

    valid = validate_preflight(root)
    assert not [
        item
        for item in valid["diagnostics"]
        if item["code"].startswith("pyodide_bundle_")
    ]

    (root / "pyodide" / "numpy-2.4.3.whl").unlink()
    missing = validate_preflight(root)
    diagnostic = next(
        item
        for item in missing["diagnostics"]
        if item["code"] == "pyodide_bundle_wheels_missing"
    )
    assert diagnostic["details"]["missing"] == [
        {"package": "numpy", "file": "numpy-2.4.3.whl"}
    ]

    (root / "pyodide" / "numpy-2.4.3.whl").write_bytes(b"corrupt")
    corrupt = validate_preflight(root)
    diagnostic = next(
        item
        for item in corrupt["diagnostics"]
        if item["code"] == "pyodide_bundle_wheel_hash_mismatch"
    )
    assert diagnostic["details"]["corrupt"] == [
        {"package": "numpy", "file": "numpy-2.4.3.whl"}
    ]
