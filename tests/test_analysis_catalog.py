from __future__ import annotations

import hashlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import shutil

import pytest
import yaml
from typer.testing import CliRunner

from dataviz.analysis import ensure_analysis_catalog
from dataviz.analysis.contracts import AnalysisCatalog, AnalysisEntry, AnalysisResult
from dataviz.cli import app
from dataviz.errors import ValidationFailure
from dataviz.workspace.models import OutputDefinition


FEATURE_SHOWCASE = Path("examples/feature-showcase")
SALES_WORKSPACE = Path("examples/sales-workspace")


def _build_server_derived_workspace(root: Path) -> Path:
    dashboard = root / "dashboards" / "analysis"
    (dashboard / "data").mkdir(parents=True)
    (dashboard / "transforms").mkdir()
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: analysis-tests
title: Analysis tests
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v9
kind: dashboard
id: analysis
title: Analysis
sources:
  - id: rows
    kind: source
    type: file
    path: data/rows.csv
    outputs: {main: {kind: table, description: 原始收入}}
interactive_transforms: [transforms/doubled.yaml]
views:
  - {id: result, title: 加倍收入, template: table, input: interactive:doubled/main}
sections:
  - {id: result, title: Result, views: [result]}
""",
        encoding="utf-8",
    )
    (dashboard / "data" / "rows.csv").write_text(
        "name,revenue\nA,10\nB,20\n", encoding="utf-8"
    )
    (dashboard / "transforms" / "doubled.yaml").write_text(
        """schema: dataviz/interactive-transform/v2
kind: interactive_transform
id: doubled
name: 加倍收入
description: 将当前收入乘以二。
runtime: server-python
code: doubled.py
inputs: {rows: source:rows/main}
export: {mode: snapshot}
outputs:
  main: {kind: table, description: 加倍后的收入明细}
""",
        encoding="utf-8",
    )
    (dashboard / "transforms" / "doubled.py").write_text(
        """def transform(context):
    frame = context.table("rows").copy()
    frame["revenue"] = frame["revenue"] * 2
    return {"main": frame}
""",
        encoding="utf-8",
    )
    return root


def test_analysis_catalog_is_incremental_atomic_and_alias_stable(isolated_workspace):
    workspace = isolated_workspace(FEATURE_SHOWCASE)
    first = ensure_analysis_catalog(workspace)
    target = next(
        entry
        for entry in first.entries
        if entry["reference"] == "date-parameter-lab::source:date-window/main"
    )
    first_alias = target["alias"]
    first_hash = target["definition_hash"]
    assert first_alias.startswith("base_")
    assert (workspace / ".dataviz/catalog/CURRENT.json").is_file()
    assert (
        workspace / ".dataviz/catalog/generations" / first.generation
    ).is_file()

    unchanged = ensure_analysis_catalog(workspace)
    assert unchanged.generation == first.generation

    definition = (
        workspace
        / "dashboards/功能示例##date-parameter-lab/sources/date-window.yaml"
    )
    definition.write_text(
        definition.read_text(encoding="utf-8") + "\n# catalog fingerprint change\n",
        encoding="utf-8",
    )
    changed = ensure_analysis_catalog(workspace)
    changed_target = changed.resolve(f"@{first_alias}")
    assert changed.generation != first.generation
    assert changed_target["alias"] == first_alias
    assert changed_target["definition_hash"] != first_hash


def test_analysis_catalog_supports_grep_like_regex(isolated_workspace):
    workspace = isolated_workspace(FEATURE_SHOWCASE)
    catalog = ensure_analysis_catalog(workspace)
    matches = catalog.select(query="日期|收入", regex=True)
    assert any(entry["dashboard"]["id"] == "date-parameter-lab" for entry in matches)
    assert any("收入" in json.dumps(entry, ensure_ascii=False) for entry in matches)

    with pytest.raises(ValidationFailure) as captured:
        catalog.select(query="[", regex=True)
    assert captured.value.details["code"] == "analysis_search_regex_invalid"


def test_analysis_contracts_publish_machine_json_schemas():
    assert AnalysisEntry.model_json_schema()["properties"]["schema"]["const"] == (
        "dataviz/analysis-entry/v1"
    )
    assert AnalysisCatalog.model_json_schema()["properties"]["schema"]["const"] == (
        "dataviz/analysis-catalog/v1"
    )
    assert AnalysisResult.model_json_schema()["properties"]["schema"]["const"] == (
        "dataviz/analysis-result/v1"
    )


def test_public_output_semantics_are_strict_and_internal_outputs_are_hidden(tmp_path: Path):
    with pytest.raises(ValueError, match="public Output semantics"):
        OutputDefinition.model_validate(
            {
                "kind": "table",
                "semantics": {
                    "visibility": "public",
                    "title": "Missing meaning",
                },
            }
        )

    workspace = _build_server_derived_workspace(tmp_path / "workspace")
    definition = workspace / "dashboards/analysis/dashboard.yaml"
    definition.write_text(
        definition.read_text(encoding="utf-8").replace(
            "outputs: {main: {kind: table, description: 原始收入}}",
            """outputs:
      main:
        kind: table
        semantics: {visibility: internal, title: 原始收入, purpose: 中间计算输入, grain: 每行一个主体}
""".rstrip(),
        ),
        encoding="utf-8",
    )
    catalog = ensure_analysis_catalog(workspace)
    internal = next(
        item for item in catalog.entries if item["reference"] == "analysis::source:rows/main"
    )
    assert internal["visibility"] == "internal"
    assert internal not in catalog.select(kind="base_output")
    assert internal in catalog.select(
        kind="base_output", include_internal=True, include_untrusted=True
    )
    assert catalog.resolve(f"@{internal['alias']}")["reference"] == internal["reference"]


def test_catalog_concurrent_refresh_reuses_one_generation_and_failure_falls_back(
    tmp_path: Path, monkeypatch
):
    workspace = _build_server_derived_workspace(tmp_path / "workspace")
    first = ensure_analysis_catalog(workspace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        generations = list(
            pool.map(
                lambda _index: ensure_analysis_catalog(workspace, refresh=True).generation,
                range(2),
            )
        )
    assert generations[0] == generations[1]
    assert generations[0] != first.generation

    import dataviz.analysis.catalog as catalog_module

    monkeypatch.setattr(
        catalog_module,
        "_fingerprints",
        lambda _workspace: (_ for _ in ()).throw(RuntimeError("forced refresh failure")),
    )
    fallback = ensure_analysis_catalog(workspace, refresh=True)
    assert fallback.generation == generations[0]
    assert fallback.stale is True
    assert fallback.diagnostics[0]["code"] == (
        "analysis_catalog_refresh_failed_using_previous"
    )


def test_catalog_retries_unstable_snapshot_removes_deleted_dashboard_and_rebuilds(
    isolated_workspace,
    monkeypatch,
):
    workspace = isolated_workspace(FEATURE_SHOWCASE)
    first = ensure_analysis_catalog(workspace)
    import dataviz.analysis.catalog as catalog_module

    original = catalog_module._fingerprints
    calls = 0
    changed = (
        workspace
        / "dashboards/功能示例##date-parameter-lab/sources/date-window.yaml"
    )

    def unstable_once(loaded):
        nonlocal calls
        calls += 1
        if calls == 3:
            changed.write_text(
                changed.read_text(encoding="utf-8") + "\n# changed during build\n",
                encoding="utf-8",
            )
        return original(loaded)

    monkeypatch.setattr(catalog_module, "_fingerprints", unstable_once)
    retried = ensure_analysis_catalog(workspace, refresh=True)
    assert calls >= 5
    assert retried.generation != first.generation

    removed = workspace / "dashboards/功能示例##parameter-playground"
    outside = workspace / "removed-parameter-playground"
    removed.rename(outside)
    without_dashboard = ensure_analysis_catalog(workspace)
    assert not any(
        entry["dashboard"]["id"] == "parameter-playground"
        for entry in without_dashboard.entries
    )

    shutil.rmtree(workspace / ".dataviz/catalog")
    rebuilt = ensure_analysis_catalog(workspace)
    assert rebuilt.entries
    assert not any(
        entry["dashboard"]["id"] == "parameter-playground"
        for entry in rebuilt.entries
    )


def test_analysis_alias_collision_extends_only_colliding_hashes(monkeypatch):
    import dataviz.analysis.catalog as catalog_module

    entries = [
        {"kind": "base_output", "reference": "one::source:rows/main"},
        {"kind": "base_output", "reference": "two::source:rows/main"},
        {"kind": "derived_output", "reference": "three::interactive:x/main"},
    ]
    digests = {
        entries[0]["reference"]: "AAAAAAAAAA11" + "X" * 40,
        entries[1]["reference"]: "AAAAAAAAAA22" + "Y" * 40,
        entries[2]["reference"]: "BBBBBBBBBB33" + "Z" * 40,
    }
    monkeypatch.setattr(catalog_module, "_alias_digest", digests.__getitem__)
    catalog_module._assign_aliases(entries)
    assert entries[0]["alias"] == "base_AAAAAAAAAA11"
    assert entries[1]["alias"] == "base_AAAAAAAAAA22"
    assert entries[2]["alias"] == "drv_BBBBBBBBBB"


def test_analysis_cli_all_show_and_run_base_output(isolated_workspace):
    workspace = isolated_workspace(FEATURE_SHOWCASE)
    runner = CliRunner()
    overview = runner.invoke(
        app, ["analyze", "all", str(workspace), "--format", "json"]
    )
    assert overview.exit_code == 0, overview.output
    overview_payload = json.loads(overview.output)
    assert overview_payload["schema"] == "dataviz/analysis-catalog/v1"
    assert {entry["kind"] for entry in overview_payload["entries"]} == {"base_output"}
    target = next(
        entry
        for entry in overview_payload["entries"]
        if entry["reference"] == "date-parameter-lab::source:date-window/main"
    )

    shown = runner.invoke(
        app, ["analyze", "show", str(workspace), f"@{target['alias']}"]
    )
    assert shown.exit_code == 0, shown.output
    shown_payload = json.loads(shown.output)
    assert shown_payload["query_parameters"] == ["analysis_date", "report_range"]
    assert "code" not in shown_payload

    full = runner.invoke(
        app,
        [
            "analyze",
            "show",
            str(workspace),
            f"@{target['alias']}",
            "--detail",
            "full",
            "--include-code",
        ],
    )
    assert full.exit_code == 0, full.output
    closure = json.loads(full.output)["closure"]
    assert closure["node_count"] == 1
    assert closure["nodes"][0]["node_id"] == "source:date-window"
    assert "select" in closure["nodes"][0]["assets"][0]["content"].casefold()

    executed = runner.invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{target['alias']}",
            "--limit",
            "1",
            "--format",
            "json",
        ],
    )
    assert executed.exit_code == 0, executed.output
    result = json.loads(executed.output)
    assert result["schema"] == "dataviz/analysis-result/v1"
    assert result["status"] == "ready"
    assert result["outputs"][0]["rows"] == 1
    assert result["lineage"]["query_nodes"] == ["source:date-window"]
    assert result["provenance"]["query_contract_hash"]
    assert result["provenance"]["artifacts"][0]["content_hash"]
    assert result["next_actions"]

    arrow = runner.invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{target['alias']}",
            "--format",
            "arrow",
        ],
    )
    assert arrow.exit_code == 0, arrow.output
    import pyarrow as pa

    arrow_payload = json.loads(arrow.output)
    exported = arrow_payload["outputs"][0]["export"]
    exported_path = workspace / exported["path"]
    assert exported["format"] == "arrow"
    assert exported["size_bytes"] == exported_path.stat().st_size
    table = pa.ipc.open_stream(exported_path).read_all()
    assert table.num_rows == 1

    parquet_destination = workspace / "exports" / "dates.parquet"
    parquet = runner.invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{target['alias']}",
            "--format",
            "parquet",
            "--destination",
            str(parquet_destination),
        ],
    )
    assert parquet.exit_code == 0, parquet.output
    parquet_payload = json.loads(parquet.output)
    assert parquet_destination.is_file()
    assert parquet_payload["outputs"][0]["export"]["sha256"] == hashlib.sha256(
        parquet_destination.read_bytes()
    ).hexdigest()

    view = next(
        entry
        for entry in ensure_analysis_catalog(workspace).entries
        if entry["reference"] == "date-parameter-lab::view:resolved-dates"
    )
    viewed = runner.invoke(
        app,
        ["analyze", "run", str(workspace), f"@{view['alias']}", "--format", "json"],
    )
    assert viewed.exit_code == 0, viewed.output
    viewed_payload = json.loads(viewed.output)
    assert viewed_payload["target"]["kind"] == "view"
    assert viewed_payload["resolved_target"]["kind"] == "base_output"
    assert viewed_payload["presentation"]["template"] == "table"


def test_analysis_cli_executes_file_sql_and_dataset_transform(tmp_path: Path):
    workspace = tmp_path / "sales-workspace"
    shutil.copytree(SALES_WORKSPACE, workspace)
    catalog = ensure_analysis_catalog(workspace)
    entries = {entry["reference"]: entry for entry in catalog.entries}
    runner = CliRunner()

    file_source = runner.invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entries['sales::source:orders']['alias']}",
            "--output",
            "main",
            "--limit",
            "1",
            "--format",
            "json",
        ],
    )
    assert file_source.exit_code == 0, file_source.output
    assert json.loads(file_source.output)["outputs"][0]["rows"] > 1

    sql_source = runner.invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entries['sales::source:targets']['alias']}",
            "--output",
            "main",
            "--query-param",
            "target_factor=2",
            "--format",
            "json",
        ],
    )
    assert sql_source.exit_code == 0, sql_source.output
    sql_payload = json.loads(sql_source.output)
    assert sql_payload["query_parameters"]["target_factor"] == 2
    assert sql_payload["outputs"][0]["preview"][0]["target"] == 136000

    dataset_output = runner.invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{entries['sales::dataset:sales-metrics/trend']['alias']}",
            "--query-param",
            "target_factor=2",
            "--limit",
            "1",
            "--detail",
            "debug",
            "--format",
            "json",
        ],
    )
    assert dataset_output.exit_code == 0, dataset_output.output
    dataset_payload = json.loads(dataset_output.output)
    assert set(dataset_payload["lineage"]["query_nodes"]) == {
        "source:orders",
        "source:targets",
        "dataset:sales-metrics",
    }
    assert dataset_payload["outputs"][0]["preview"][0]["forecast_revenue"] > 0


def test_analysis_cli_runs_server_derived_output(tmp_path: Path):
    workspace = _build_server_derived_workspace(tmp_path / "workspace")
    catalog = ensure_analysis_catalog(workspace)
    derived = next(entry for entry in catalog.entries if entry["kind"] == "derived_output")
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{derived['alias']}",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ready"
    assert payload["target"]["runtime"] == "server-python"
    assert payload["outputs"][0]["preview"] == [
        {"name": "A", "revenue": 20},
        {"name": "B", "revenue": 40},
    ]
    assert payload["lineage"]["query_nodes"] == ["source:rows"]
    assert payload["lineage"]["interactive_nodes"] == ["interactive:doubled"]


def test_analysis_cli_batches_base_and_server_outputs_in_one_query_run(tmp_path: Path):
    workspace = _build_server_derived_workspace(tmp_path / "workspace")
    dashboard_path = workspace / "dashboards/analysis/dashboard.yaml"
    dashboard_path.write_text(
        dashboard_path.read_text(encoding="utf-8").replace(
            "interactive_transforms: [transforms/doubled.yaml]",
            "interactive_transforms: [transforms/doubled.yaml, transforms/tripled.yaml]",
        ),
        encoding="utf-8",
    )
    transform_root = workspace / "dashboards/analysis/transforms"
    (transform_root / "tripled.yaml").write_text(
        """schema: dataviz/interactive-transform/v2
kind: interactive_transform
id: tripled
name: 三倍收入
runtime: server-python
code: tripled.py
inputs: {rows: source:rows/main}
export: {mode: snapshot}
outputs:
  main: {kind: table, description: 三倍后的收入明细}
""",
        encoding="utf-8",
    )
    (transform_root / "tripled.py").write_text(
        """def transform(context):
    frame = context.table("rows").copy()
    frame["revenue"] = frame["revenue"] * 3
    return {"main": frame}
""",
        encoding="utf-8",
    )
    catalog = ensure_analysis_catalog(workspace)
    base = next(item for item in catalog.entries if item["kind"] == "base_output")
    base_batch = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{base['alias']}",
            "--also",
            f"@{base['alias']}",
            "--format",
            "json",
        ],
    )
    assert base_batch.exit_code == 0, base_batch.output
    base_payload = json.loads(base_batch.output)
    assert len(base_payload["outputs"]) == 2
    assert {item["run_id"] for item in base_payload["outputs"]} == {
        base_payload["outputs"][0]["run_id"]
    }

    derived = {
        item["node_id"]: item
        for item in ensure_analysis_catalog(workspace).entries
        if item["kind"] == "derived_output"
    }
    server_batch = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{derived['interactive:doubled']['alias']}",
            "--also",
            f"@{derived['interactive:tripled']['alias']}",
            "--format",
            "json",
        ],
    )
    assert server_batch.exit_code == 0, server_batch.output
    server_payload = json.loads(server_batch.output)
    assert [item["preview"][0]["revenue"] for item in server_payload["outputs"]] == [
        20,
        30,
    ]
    assert len({item["run_id"] for item in server_payload["outputs"]}) == 1
    assert server_payload["lineage"]["query_nodes"] == ["source:rows"]


def test_analysis_evidence_and_promote_preview_do_not_mutate_workspace(tmp_path: Path):
    workspace = _build_server_derived_workspace(tmp_path / "workspace")
    catalog = ensure_analysis_catalog(workspace)
    target = next(
        entry
        for entry in catalog.entries
        if entry["reference"] == "analysis::source:rows/main"
    )
    runner = CliRunner()
    executed = runner.invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{target['alias']}",
            "--format",
            "json",
        ],
    )
    assert executed.exit_code == 0, executed.output
    result_path = tmp_path / "result.json"
    result_path.write_text(executed.output, encoding="utf-8")

    evidence_result = runner.invoke(
        app,
        [
            "analyze",
            "evidence",
            str(workspace),
            str(result_path),
            "--question",
            "原始收入是否可作为断言基线？",
            "--conclusion",
            "当前两行收入可重现。",
            "--assertion",
            "输出保持两行。",
            "--generated-by",
            "pytest",
            "--status",
            "reviewed",
            "--reviewer",
            "test-reviewer",
            "--snapshot-rows",
            "2",
        ],
    )
    assert evidence_result.exit_code == 0, evidence_result.output
    evidence = json.loads(evidence_result.output)
    evidence_path = workspace / evidence["artifact"]
    assert evidence_path.is_file()
    assert evidence["status"] == "reviewed"
    assert evidence["snapshot"][0]["rows"] == [
        {"name": "A", "revenue": 10},
        {"name": "B", "revenue": 20},
    ]

    proposal = tmp_path / "proposal.yaml"
    proposal.write_text(
        f"""schema: dataviz/analysis-promote/v1
kind: assertion
target: '@{target['alias']}'
include_snapshot: true
""",
        encoding="utf-8",
    )
    dashboard_before = (
        workspace / "dashboards/analysis/dashboard.yaml"
    ).read_bytes()
    promoted = runner.invoke(
        app,
        [
            "analyze",
            "promote",
            str(workspace),
            evidence["evidence_id"],
            str(proposal),
            "--dry-run",
        ],
    )
    assert promoted.exit_code == 0, promoted.output
    promotion = json.loads(promoted.output)
    assert promotion["schema"] == "dataviz/analysis-promotion/v1"
    assert promotion["status"] == "ready"
    assert promotion["kind"] == "assertion"
    assert promotion["mutated_workspace"] is False
    assert promotion["operations"][0]["action"] == "create"
    assert "analysis_contracts/" in promotion["operations"][0]["path"]
    assert not (workspace / promotion["operations"][0]["path"]).exists()
    assert (
        workspace / "dashboards/analysis/dashboard.yaml"
    ).read_bytes() == dashboard_before

    semantics_proposal = tmp_path / "semantics-proposal.json"
    semantics_proposal.write_text(
        json.dumps(
            {
                "schema": "dataviz/analysis-promote/v1",
                "kind": "semantics",
                "target": f"@{target['alias']}",
                "semantics": {
                    "visibility": "public",
                    "title": "原始收入明细",
                    "purpose": "作为收入分析的可复用基础数据。",
                    "grain": "每个主体一行。",
                    "caveats": ["测试数据。"],
                    "assurance": {"status": "draft"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    semantics_preview = runner.invoke(
        app,
        [
            "analyze",
            "promote",
            str(workspace),
            evidence["evidence_id"],
            str(semantics_proposal),
            "--dry-run",
        ],
    )
    assert semantics_preview.exit_code == 0, semantics_preview.output
    assert json.loads(semantics_preview.output)["kind"] == "semantics"

    dashboard_path = workspace / "dashboards/analysis/dashboard.yaml"
    dashboard_document = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    dashboard_document["sources"].insert(0, "sources/rows-copy.yaml")
    promoted_dashboard = yaml.safe_dump(
        dashboard_document, allow_unicode=True, sort_keys=False
    )
    new_output_proposal = tmp_path / "new-output-proposal.json"
    new_output_proposal.write_text(
        json.dumps(
            {
                "schema": "dataviz/analysis-promote/v1",
                "kind": "new_output",
                "files": {
                    "dashboards/analysis/dashboard.yaml": promoted_dashboard,
                    "dashboards/analysis/sources/rows-copy.yaml": (
                        "schema: dataviz/source/v2\n"
                        "kind: source\n"
                        "id: rows-copy\n"
                        "name: 收入副本\n"
                        "type: file\n"
                        "path: ../data/rows.csv\n"
                        "outputs:\n"
                        "  main:\n"
                        "    kind: table\n"
                        "    semantics:\n"
                        "      visibility: public\n"
                        "      title: 收入副本\n"
                        "      purpose: 验证新 Named Output Promotion。\n"
                        "      grain: 每个主体一行。\n"
                        "      assurance: {status: draft}\n"
                    ),
                },
                "expected_sha256": {
                    "dashboards/analysis/dashboard.yaml": hashlib.sha256(
                        dashboard_before
                    ).hexdigest()
                },
                "expected_new_references": ["analysis::source:rows-copy/main"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    new_output_preview = runner.invoke(
        app,
        [
            "analyze",
            "promote",
            str(workspace),
            evidence["evidence_id"],
            str(new_output_proposal),
            "--dry-run",
        ],
    )
    assert new_output_preview.exit_code == 0, new_output_preview.output
    new_output_promotion = json.loads(new_output_preview.output)
    assert new_output_promotion["kind"] == "new_output"
    assert new_output_promotion["status"] == "ready"
    assert not (workspace / "dashboards/analysis/sources/rows-copy.yaml").exists()


def test_analysis_overlay_replaces_file_without_mutating_dashboard(tmp_path: Path):
    workspace = _build_server_derived_workspace(tmp_path / "workspace")
    catalog = ensure_analysis_catalog(workspace)
    target = next(
        entry
        for entry in catalog.entries
        if entry["reference"] == "analysis::source:rows/main"
    )
    original_data = workspace / "dashboards/analysis/data/rows.csv"
    original_definition = workspace / "dashboards/analysis/dashboard.yaml"
    before = (original_data.read_bytes(), original_definition.read_bytes())

    experiment = tmp_path / "experiment"
    experiment.mkdir()
    (experiment / "replacement.csv").write_text(
        "name,revenue\nReplacement,99\n", encoding="utf-8"
    )
    overlay = experiment / "overlay.yaml"
    overlay.write_text(
        """schema: dataviz/analysis-overlay/v1
replacements:
  source:rows:
    path: replacement.csv
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{target['alias']}",
            "--overlay",
            str(overlay),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["outputs"][0]["preview"] == [
        {"name": "Replacement", "revenue": 99}
    ]
    assert payload["overlay"]["overlay_hash"]
    manifest = Path(payload["overlay"]["manifest"])
    assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "ready"
    assert (original_data.read_bytes(), original_definition.read_bytes()) == before


def test_analysis_overlay_explains_and_replaces_server_transform(tmp_path: Path):
    workspace = _build_server_derived_workspace(tmp_path / "workspace")
    catalog = ensure_analysis_catalog(workspace)
    target = next(entry for entry in catalog.entries if entry["kind"] == "derived_output")
    experiment = tmp_path / "experiment"
    experiment.mkdir()
    (experiment / "tripled.py").write_text(
        """def transform(context):
    frame = context.table("rows").copy()
    frame["revenue"] = frame["revenue"] * 3
    return {"main": frame}
""",
        encoding="utf-8",
    )
    overlay = experiment / "overlay.yaml"
    overlay.write_text(
        """schema: dataviz/analysis-overlay/v1
replacements:
  interactive:doubled:
    code: tripled.py
""",
        encoding="utf-8",
    )
    runner = CliRunner()
    explained = runner.invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{target['alias']}",
            "--overlay",
            str(overlay),
            "--dry-run",
        ],
    )
    assert explained.exit_code == 0, explained.output
    explanation = json.loads(explained.output)
    assert explanation["reachable_nodes"] == ["interactive:doubled", "source:rows"]
    assert explanation["overlay"]["changes"][0]["target"] == "interactive:doubled"

    executed = runner.invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{target['alias']}",
            "--overlay",
            str(overlay),
            "--format",
            "json",
        ],
    )
    assert executed.exit_code == 0, executed.output
    payload = json.loads(executed.output)
    assert payload["outputs"][0]["preview"] == [
        {"name": "A", "revenue": 30},
        {"name": "B", "revenue": 60},
    ]


def test_analysis_overlay_rejects_nodes_outside_target_closure(tmp_path: Path):
    workspace = _build_server_derived_workspace(tmp_path / "workspace")
    catalog = ensure_analysis_catalog(workspace)
    target = next(
        entry
        for entry in catalog.entries
        if entry["reference"] == "analysis::source:rows/main"
    )
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        """schema: dataviz/analysis-overlay/v1
replacements:
  interactive:doubled:
    code: missing.py
""",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{target['alias']}",
            "--overlay",
            str(overlay),
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "cannot affect the requested target" in result.output


def test_analysis_overlay_executes_external_sql_with_original_contract(
    isolated_workspace,
    tmp_path: Path,
):
    workspace = isolated_workspace(FEATURE_SHOWCASE)
    catalog = ensure_analysis_catalog(workspace)
    target = next(
        entry
        for entry in catalog.entries
        if entry["reference"] == "date-parameter-lab::source:date-window/main"
    )
    (tmp_path / "replacement.sql").write_text(
        """select
  cast('2099-01-01' as date) as analysis_date,
  cast('2099-01-02' as date) as range_start,
  cast('2099-01-03' as date) as range_end,
  2 as range_days
where :analysis_date is not null
  and :range_start is not null
  and :range_end is not null
""",
        encoding="utf-8",
    )
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        """schema: dataviz/analysis-overlay/v1
replacements:
  source:date-window:
    code: replacement.sql
""",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "run",
            str(workspace),
            f"@{target['alias']}",
            "--overlay",
            str(overlay),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)["outputs"][0]["preview"]
    assert preview[0]["analysis_date"].startswith("2099-01-01")
    assert preview[0]["range_days"] == 2


def test_feature_showcase_analysis_evidence_promote_dry_run_flow(
    isolated_workspace,
    tmp_path: Path,
):
    workspace = isolated_workspace(FEATURE_SHOWCASE)
    runner = CliRunner()
    searched = runner.invoke(
        app,
        [
            "analyze",
            "search",
            str(workspace),
            "日期参数",
            "--kind",
            "base",
            "--format",
            "json",
        ],
    )
    assert searched.exit_code == 0, searched.output
    entry = json.loads(searched.output)["entries"][0]
    executed = runner.invoke(
        app,
        ["analyze", "run", str(workspace), f"@{entry['alias']}", "--format", "json"],
    )
    assert executed.exit_code == 0, executed.output
    result_path = tmp_path / "feature-result.json"
    result_path.write_text(executed.output, encoding="utf-8")
    evidence_result = runner.invoke(
        app,
        [
            "analyze",
            "evidence",
            str(workspace),
            str(result_path),
            "--question",
            "日期参数解析是否可重现？",
            "--conclusion",
            "解析结果可作为契约断言。",
            "--assertion",
            "输出保持一行。",
            "--generated-by",
            "feature-showcase-test",
            "--status",
            "reviewed",
            "--reviewer",
            "dataviz-test",
            "--snapshot-rows",
            "1",
        ],
    )
    assert evidence_result.exit_code == 0, evidence_result.output
    evidence = json.loads(evidence_result.output)
    proposal = tmp_path / "feature-proposal.yaml"
    proposal.write_text(
        f"""schema: dataviz/analysis-promote/v1
kind: assertion
target: '@{entry['alias']}'
include_snapshot: true
""",
        encoding="utf-8",
    )
    promoted = runner.invoke(
        app,
        [
            "analyze",
            "promote",
            str(workspace),
            evidence["evidence_id"],
            str(proposal),
            "--dry-run",
        ],
    )
    assert promoted.exit_code == 0, promoted.output
    promotion = json.loads(promoted.output)
    assert promotion["status"] == "ready"
    assert promotion["mutated_workspace"] is False
