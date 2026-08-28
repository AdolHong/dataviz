from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil

import pytest
from typer.testing import CliRunner
import yaml

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
        """schema: dataviz/dashboard/v9
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
    dependency_yaml = json.dumps(dependency)
    (dashboard / "transforms" / "calculate.yaml").write_text(
        f"""schema: dataviz/interactive-transform/v2
kind: interactive_transform
id: calculate
runtime: browser-python
code: calculate.py
inputs: {{rows: source:raw/main}}
export: {{mode: interactive, assets: {assets}}}
outputs: {{main: {{kind: table}}}}
python_dependencies: [{dependency_yaml}]
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
    (bundle / "package.json").write_text(
        json.dumps({"name": "pyodide", "version": "314.0.4"}),
        encoding="utf-8",
    )
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
    assert "Source `query_inputs`" in diagnostics["sql_parameter_undeclared"]["hint"]


def test_validate_rejects_query_input_part_for_non_date_range(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["query_inputs"] = {
        "min_query_revenue": {
            "parameter": "min_query_revenue",
            "part": "start",
        }
    }
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "query_input_part_invalid"
    )

    assert report["status"] == "invalid"
    assert diagnostic["field"].endswith("query_inputs.min_query_revenue.part")
    assert "not range_input/date" in diagnostic["message"]


def test_validate_rejects_unknown_selection_option_domain(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"][0].pop("initial")
    definition["controls"][0]["options"] = {
        "mode": "infer",
        "source": "source:missing/main",
    }
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "selection_option_domain_invalid"
    )

    assert report["status"] == "invalid"
    assert "Unknown output node" in diagnostic["message"]
    assert "options" in diagnostic["hint"]


def test_validate_reports_control_dependency_cycles_before_runtime(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"][0]["depends_on"] = ["dashboard.day"]
    definition["controls"].append(
        {
            "id": "day",
            "kind": "selection",
            "field": "day",
            "type": "multiple_select", "value_type": "text",
            "depends_on": ["dashboard.region"],
            "options": {
                "mode": "infer",
                "source": "source:sales/main",
            },
        }
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "control_dependency_cycle"
    )

    assert report["status"] == "invalid"
    assert diagnostic["details"]["cycle"] == [
        "dashboard:sales-overview/day",
        "dashboard:sales-overview/region",
        "dashboard:sales-overview/day",
    ]
    assert "direct Selection parents" in diagnostic["hint"]


def test_validate_rejects_fields_outside_the_selected_source_variant(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["options"] = {"silently": "ignored"}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_invalid"
    )

    assert report["status"] == "invalid"
    assert diagnostic["category"] == "schema-contracts"
    assert any(
        item["loc"][-1] == "options" and item["type"] == "extra_forbidden"
        for item in diagnostic["details"]
    )
    assert all("input" not in item for item in diagnostic["details"])
    assert "silently" not in json.dumps(diagnostic, ensure_ascii=False)


def test_validate_reports_unreadable_yaml_without_echoing_file_bytes(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    dashboard_path.write_bytes(b"title: \xffcredential-secret\n")

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_invalid"
    )

    serialized = json.dumps(diagnostic, ensure_ascii=False)
    assert report["status"] == "invalid"
    assert diagnostic["message"] == "YAML file cannot be read as UTF-8"
    assert "UnicodeDecodeError" in serialized
    assert "credential-secret" not in serialized


def test_validate_rejects_impossible_sql_source_output_contract(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["outputs"] = {"result": {"kind": "table"}}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_invalid"
    )

    assert report["status"] == "invalid"
    assert any(
        "SQL Source outputs must be exactly main" in item["msg"]
        for item in diagnostic["details"]
    )


def test_validate_rejects_unknown_file_source_format_before_query(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"] = [
        {
            "id": "sales",
            "type": "file",
            "path": "data/sales.records",
            "outputs": {"main": {"kind": "table"}},
        }
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_invalid"
    )

    assert report["status"] == "invalid"
    assert any(
        "declare format explicitly" in item["msg"]
        for item in diagnostic["details"]
    )


def test_validate_reports_missing_excel_reader_before_query(
    tmp_path: Path,
    monkeypatch,
):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"] = [
        {
            "id": "sales",
            "type": "file",
            "path": "data/sales.xlsx",
            "outputs": {"main": {"kind": "table"}},
        }
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    excel_path = dashboard_path.parent / "data" / "sales.xlsx"
    excel_path.parent.mkdir(exist_ok=True)
    excel_path.write_bytes(b"fixture")
    original_version = importlib.metadata.version

    def version(name: str) -> str:
        if name == "openpyxl":
            raise importlib.metadata.PackageNotFoundError(name)
        return original_version(name)

    monkeypatch.setattr(importlib.metadata, "version", version)

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "file_reader_dependency_unavailable"
    )

    assert report["status"] == "invalid"
    assert diagnostic["category"] == "runtime-dependencies"
    assert "ai-dataviz[excel]" in diagnostic["hint"]


def test_validate_checks_file_source_paths_behind_workspace_adapters(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    adapter_path = workspace / "auth" / "adapters.yaml"
    adapters = yaml.safe_load(adapter_path.read_text(encoding="utf-8"))
    adapters["adapters"]["shared-files"] = {"type": "file", "root": "shared-data"}
    adapter_path.write_text(
        yaml.safe_dump(adapters, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["adapters"]["files"] = "shared-files"
    definition["sources"] = [
        {
            "id": "sales",
            "type": "file",
            "adapter": "files",
            "path": "missing.csv",
            "outputs": {"main": {"kind": "table"}},
        }
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "source_asset_missing"
    )

    assert report["status"] == "invalid"
    assert diagnostic["field"] == "path"
    assert diagnostic["file"].endswith("shared-data/missing.csv")


def test_validate_checks_runtime_credentials_for_referenced_sql_adapter(
    tmp_path: Path,
    monkeypatch,
):
    workspace = _copy_workspace(tmp_path)
    monkeypatch.delenv("DATAVIZ_TEST_MISSING_USER", raising=False)
    adapter_path = workspace / "auth" / "adapters.yaml"
    adapters = yaml.safe_load(adapter_path.read_text(encoding="utf-8"))
    adapters["adapters"]["demo-duckdb"] = {
        "type": "starrocks",
        "host": "warehouse.internal",
        "database": "analytics",
        "username_env": "DATAVIZ_TEST_MISSING_USER",
    }
    adapter_path.write_text(
        yaml.safe_dump(adapters, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "adapter_runtime_configuration_invalid"
    )

    assert report["status"] == "invalid"
    assert diagnostic["field"] == "adapter"
    assert "requires environment variable DATAVIZ_TEST_MISSING_USER" in diagnostic["message"]


def test_validate_loads_referenced_sqlalchemy_driver_without_connecting(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    adapter_path = workspace / "auth" / "adapters.yaml"
    adapters = yaml.safe_load(adapter_path.read_text(encoding="utf-8"))
    adapters["adapters"]["demo-duckdb"] = {
        "type": "sqlalchemy",
        "url": "dataviz_missing_driver://warehouse.invalid/analytics",
    }
    adapter_path.write_text(
        yaml.safe_dump(adapters, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "adapter_sql_driver_invalid"
    )

    assert report["status"] == "invalid"
    assert diagnostic["category"] == "adapter-bindings"
    assert "dataviz_missing_driver" in diagnostic["message"]


def test_validate_view_fields_against_declared_output_schema(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"] = []
    definition["sources"][0]["outputs"]["main"]["schema"] = [
        {"name": "day"},
        {"name": "revenue"},
        {"name": "orders"},
        {"name": "region"},
    ]
    trend = next(view for view in definition["views"] if view["id"] == "revenue-trend")
    trend["x"] = "missing_day"
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "view_field_unknown"
    )

    assert diagnostic["details"]["view"] == "revenue-trend"
    assert diagnostic["details"]["unknown"] == ["missing_day"]


def test_validate_rejects_python_attribute_names_as_dsl_aliases(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["outputs"]["main"]["schema_"] = [
        {"name": "revenue"}
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")

    assert report["status"] == "invalid"
    assert any(
        item["code"] == "dashboard_invalid"
        and "schema_" in json.dumps(item.get("details"), ensure_ascii=False)
        for item in report["diagnostics"]
    )


def test_validate_checks_local_browser_runtime_assets(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    workspace_path = workspace / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition["runtime"] = {
        **definition.get("runtime", {}),
        "echarts_js": "runtime/missing-echarts.js",
        "arrow_js": "../outside-arrow.js",
    }
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace)
    diagnostics = {item["code"]: item for item in report["diagnostics"]}

    assert diagnostics["runtime_asset_missing"]["field"] == "runtime.echarts_js"
    assert diagnostics["runtime_asset_outside_workspace"]["field"] == "runtime.arrow_js"


def test_validate_selection_binding_against_declared_output_schema(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["sources"][0]["outputs"]["main"]["schema"] = [
        {"name": "day"},
        {"name": "revenue"},
        {"name": "orders"},
    ]
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_preflight(workspace, dashboard_id="sales-overview")
    diagnostics = [
        item
        for item in report["diagnostics"]
        if item["code"] == "selection_field_unknown"
    ]

    assert diagnostics
    assert all(item["details"]["unknown"] == ["region"] for item in diagnostics)


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
        "schema: dataviz/dashboard/v9\nkind: dashboard\nid: broken\nretired_field: true\n",
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


def test_validate_dashboard_scope_does_not_accept_a_folder_path_alias(tmp_path: Path):
    workspace = _copy_workspace(tmp_path)
    source = workspace / "dashboards" / "sales-overview"
    destination = workspace / "dashboards" / "团队分析##销售看板"
    source.rename(destination)

    report = validate_preflight(workspace, dashboard_id="团队分析/销售看板")

    assert report["status"] == "invalid"
    diagnostic = next(
        item for item in report["diagnostics"] if item["code"] == "dashboard_not_found"
    )
    assert diagnostic["details"]["available"] == ["sales-overview"]


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
        "package.json",
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

    package_manifest = root / "pyodide" / "package.json"
    package_manifest.write_text(
        json.dumps({"name": "pyodide", "version": "0.29.4"}),
        encoding="utf-8",
    )
    mismatched = validate_preflight(root)
    diagnostic = next(
        item
        for item in mismatched["diagnostics"]
        if item["code"] == "pyodide_bundle_version_mismatch"
    )
    assert diagnostic["details"] == {"expected": "314.0.4", "actual": "0.29.4"}
    package_manifest.write_text(
        json.dumps({"name": "pyodide", "version": "314.0.4"}),
        encoding="utf-8",
    )

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


def test_validate_rejects_symlinks_in_portable_pyodide_bundle(tmp_path: Path):
    root = _browser_python_workspace(
        tmp_path / "symlink-bundle",
        assets="bundle",
        bundle_path="pyodide",
    )
    _write_pyodide_bundle(root)
    outside = tmp_path / "outside-runtime.bin"
    outside.write_bytes(b"outside")
    link = root / "pyodide" / "linked-runtime.bin"
    try:
        link.symlink_to(outside)
    except OSError as error:  # pragma: no cover - platform policy may forbid symlinks
        pytest.skip(f"Symlinks are unavailable: {error}")

    report = validate_preflight(root)
    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "pyodide_bundle_symlink_unsupported"
    )

    assert report["status"] == "invalid"
    assert diagnostic["details"]["symlinks"] == ["linked-runtime.bin"]


def test_validate_pyodide_bundle_uses_browser_markers_and_requires_hashes(
    tmp_path: Path,
):
    root = _browser_python_workspace(
        tmp_path / "bundle-markers",
        dependency='duckdb==1.5.1; sys_platform == "emscripten"',
        assets="bundle",
        bundle_path="pyodide",
    )
    _write_pyodide_bundle(root)
    lock_path = root / "pyodide" / "pyodide-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["packages"]["duckdb"].pop("sha256")
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    report = validate_preflight(root)

    diagnostic = next(
        item
        for item in report["diagnostics"]
        if item["code"] == "pyodide_bundle_wheel_hash_missing"
    )
    assert diagnostic["details"]["unhashed"] == [
        {"package": "duckdb", "file": "duckdb-1.5.1.whl"}
    ]
