from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from dataviz.analysis import ensure_analysis_catalog
from dataviz.cli import app


@pytest.mark.e2e
def test_analysis_cli_reuses_browser_runtime_for_derived_output(isolated_workspace):
    workspace = isolated_workspace(Path("tests/fixtures/browser-worker-workspace"))
    catalog = ensure_analysis_catalog(workspace)
    entry = next(
        item
        for item in catalog.entries
        if item["reference"] == "worker-runtime::interactive:scaled/main"
    )
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entry['alias']}",
            "--control",
            "dashboard:worker-runtime/delay_ms=0",
            "--limit",
            "1",
            "--detail",
            "debug",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ready"
    assert payload["target"]["runtime"] == "browser-js"
    assert payload["effective_controls"]["compute"] == {
        "dashboard:worker-runtime/delay_ms": 0
    }
    assert payload["outputs"][0]["kind"] == "table"
    assert payload["outputs"][0]["rows"] == 2
    assert payload["outputs"][0]["preview"] == [{"name": "alpha", "value": 10}]
    assert payload["outputs"][0]["truncated"] is True
    assert payload["browser"]["metrics"]["interactiveTransforms"]["completed"] == 1
    assert payload["timing"]["browser_launch_ms"] >= 0
    assert payload["timing"]["runtime_ready_ms"] >= 0
    assert payload["timing"]["transform_ms"] >= 0
    assert payload["timing"]["extraction_ms"] >= 0


@pytest.mark.e2e
def test_analysis_cli_batches_outputs_in_one_browser_session(tmp_path: Path):
    workspace = tmp_path / "browser-worker-workspace"
    shutil.copytree(Path("tests/fixtures/browser-worker-workspace"), workspace)
    transform_root = workspace / "dashboards/worker-runtime/transforms"
    definition = transform_root / "scaled.yaml"
    definition.write_text(
        definition.read_text(encoding="utf-8").replace(
            "timeout_seconds: 1",
            """  secondary:
    kind: table
    schema:
      - {name: name}
      - {name: value}
timeout_seconds: 1""",
        ),
        encoding="utf-8",
    )
    code = transform_root / "scaled.js"
    code.write_text(
        code.read_text(encoding="utf-8").replace(
            "  };\n}",
            """    secondary: context.inputs.rows.map(row => ({
      name: row.name,
      value: Number(row.value) * 20,
    })),
  };
}""",
        ),
        encoding="utf-8",
    )
    catalog = ensure_analysis_catalog(workspace)
    entry = next(
        item
        for item in catalog.entries
        if item["reference"] == "worker-runtime::interactive:scaled/main"
    )
    secondary = next(
        item
        for item in catalog.entries
        if item["reference"] == "worker-runtime::interactive:scaled/secondary"
    )
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entry['alias']}",
            "--also",
            f"@{secondary['alias']}",
            "--control",
            "dashboard:worker-runtime/delay_ms=0",
            "--detail",
            "debug",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["outputs"]) == 2
    assert payload["outputs"][0]["preview"][0]["value"] == 10
    assert payload["outputs"][1]["preview"][0]["value"] == 20
    assert payload["browser"]["metrics"]["interactiveTransforms"]["completed"] == 1


@pytest.mark.e2e
def test_analysis_cli_exports_browser_output_to_arrow_file(isolated_workspace):
    workspace = isolated_workspace(Path("tests/fixtures/browser-worker-workspace"))
    catalog = ensure_analysis_catalog(workspace)
    entry = next(
        item
        for item in catalog.entries
        if item["reference"] == "worker-runtime::interactive:scaled/main"
    )
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entry['alias']}",
            "--control",
            "dashboard:worker-runtime/delay_ms=0",
            "--format",
            "arrow",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    exported = payload["outputs"][0]["export"]
    exported_path = workspace / exported["path"]
    assert exported_path.is_file()
    assert payload["outputs"][0]["rows"] == 2
    assert payload["outputs"][0]["truncated"] is False

    import pyarrow as pa

    assert pa.ipc.open_stream(exported_path).read_all().num_rows == 2


@pytest.mark.e2e
def test_analysis_overlay_replaces_browser_js_in_existing_runtime(
    isolated_workspace,
    tmp_path: Path,
):
    workspace = isolated_workspace(Path("tests/fixtures/browser-worker-workspace"))
    catalog = ensure_analysis_catalog(workspace)
    entry = next(
        item
        for item in catalog.entries
        if item["reference"] == "worker-runtime::interactive:scaled/main"
    )
    replacement = tmp_path / "replacement.js"
    replacement.write_text(
        """async function transform(context) {
  return {
    main: context.inputs.rows.map(row => ({
      name: row.name,
      value: Number(row.value) * 7,
    })),
  };
}
""",
        encoding="utf-8",
    )
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        """schema: dataviz/analysis-overlay/v1
replacements:
  interactive:scaled:
    code: replacement.js
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entry['alias']}",
            "--overlay",
            str(overlay),
            "--control",
            "dashboard:worker-runtime/delay_ms=0",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["outputs"][0]["preview"] == [
        {"name": "alpha", "value": 7},
        {"name": "beta", "value": 14},
    ]
    assert payload["overlay"]["changes"][0]["target"] == "interactive:scaled"


@pytest.mark.e2e
def test_analysis_cli_executes_browser_python_in_bundled_runtime(isolated_workspace):
    workspace = isolated_workspace(
        Path("tests/fixtures/browser-python-analysis-workspace")
    )
    catalog = ensure_analysis_catalog(workspace)
    entry = next(
        item
        for item in catalog.entries
        if item["reference"] == "browser-python::interactive:scaled/main"
    )
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entry['alias']}",
            "--control",
            "dashboard:browser-python/factor=4",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["target"]["runtime"] == "browser-python"
    assert payload["outputs"][0]["preview"] == [
        {"name": "alpha", "value": 4},
        {"name": "beta", "value": 8},
    ]


@pytest.mark.e2e
def test_analysis_cli_explains_blocked_cdn_browser_python(tmp_path: Path):
    workspace = tmp_path / "browser-python-analysis-workspace"
    shutil.copytree(Path("tests/fixtures/browser-python-analysis-workspace"), workspace)
    workspace_path = workspace / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition["runtime"] = {
        "pyodide_asset_policy": "cdn",
        "browser_table_transport": "json",
    }
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    catalog = ensure_analysis_catalog(workspace)
    entry = next(
        item
        for item in catalog.entries
        if item["reference"] == "browser-python::interactive:scaled/main"
    )

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entry['alias']}",
            "--control",
            "dashboard:browser-python/factor=4",
            "--timeout",
            "5",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert "--allow-network" in json.dumps(payload, ensure_ascii=False)
    assert "bundled Pyodide" in json.dumps(payload, ensure_ascii=False)


@pytest.mark.e2e
def test_analysis_cli_returns_stable_browser_timeout_error(tmp_path: Path):
    workspace = tmp_path / "browser-worker-workspace"
    shutil.copytree(Path("tests/fixtures/browser-worker-workspace"), workspace)
    catalog = ensure_analysis_catalog(workspace)
    entry = next(
        item
        for item in catalog.entries
        if item["reference"] == "worker-runtime::interactive:scaled/main"
    )

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entry['alias']}",
            "--control",
            "dashboard:worker-runtime/delay_ms=1500",
            "--timeout",
            "5",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert payload["error"]["code"] in {
        "interactive_transform_timeout",
        "interactive_transform_error",
    }
    assert payload["error"]["type"] == "execution_error"
