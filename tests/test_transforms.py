from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pandas as pd
import pytest

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.execution import Executor
from dataviz.execution.outputs import normalize_outputs, write_output
from dataviz.errors import ExecutionFailure
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.models import ColumnDefinition, OutputDefinition


def build_workspace(
    root: Path,
    code: str,
    *,
    timeout: float | None = None,
    code_dependencies: list[str] | None = None,
    python_dependencies: list[str] | None = None,
    output_schema: str = "",
) -> Path:
    dashboard = root / "dashboards" / "transform-contract"
    (dashboard / "sources").mkdir(parents=True)
    (dashboard / "transforms").mkdir()
    (root / "workspace.yaml").write_text(
        """schema: dataviz/workspace/v1
kind: workspace
id: transform-tests
title: Transform tests
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v2
kind: dashboard
id: transform-contract
title: Transform contract
sources: [sources/raw.yaml]
dataset_transforms: [transforms/metrics.yaml]
views: []
""",
        encoding="utf-8",
    )
    (dashboard / "sources" / "raw.yaml").write_text(
        """schema: dataviz/source/v1
kind: source
id: raw
type: file
path: rows.csv
format: csv
outputs:
  main:
    kind: table
    schema:
      - {name: key, dtype: str}
      - {name: value, dtype: int64, nullable: false}
""",
        encoding="utf-8",
    )
    (dashboard / "sources" / "rows.csv").write_text(
        "key,value\na,2\nb,3\n", encoding="utf-8"
    )
    dependency_lines = "\n".join(
        f"  - {value}" for value in (code_dependencies or [])
    )
    package_lines = "\n".join(
        f"  - {value}" for value in (python_dependencies or [])
    )
    schema_lines = output_schema or """    schema:
      - {name: key}
      - {name: doubled, dtype: int64}"""
    transform_yaml = f"""schema: dataviz/dataset-transform/v1
kind: dataset_transform
id: metrics
runtime: server-python
code: metrics.py
entrypoint: transform
inputs:
  rows: source:raw/main
input_schemas:
  rows:
    - {{name: key, dtype: str}}
    - {{name: value, dtype: int64, nullable: false}}
outputs:
  doubled:
    kind: table
{schema_lines}
  total: {{kind: scalar}}
  note: {{kind: text}}
  metadata: {{kind: object}}
code_dependencies:
{dependency_lines or '  []'}
python_dependencies:
{package_lines or '  []'}
cache: {{mode: session}}
"""
    if timeout is not None:
        transform_yaml += f"timeout_seconds: {timeout}\n"
    (dashboard / "transforms" / "metrics.yaml").write_text(
        transform_yaml, encoding="utf-8"
    )
    (dashboard / "transforms" / "metrics.py").write_text(code, encoding="utf-8")
    return root


MULTI_OUTPUT_CODE = """def transform(context):
    frame = context.table("rows").copy()
    frame["doubled"] = frame["value"] * 2
    return {
        "doubled": frame[["key", "doubled"]],
        "total": int(frame["value"].sum()),
        "note": "computed",
        "metadata": {"rows": len(frame)},
    }
"""


def test_dataset_transform_writes_typed_named_outputs_and_validates_boundaries(tmp_path: Path):
    workspace = load_workspace(build_workspace(tmp_path / "workspace", MULTI_OUTPUT_CODE))
    assert validate_workspace(workspace) == []

    result = Executor(workspace).run("transform-contract", refresh=True)
    store = ArtifactStore(workspace.root, result.run_id)

    assert result.status == "ready"
    assert set(result.nodes["dataset:metrics"].outputs) == {
        "doubled",
        "total",
        "note",
        "metadata",
    }
    assert store.read_value(result.outputs["dataset:metrics/total"]) == 5
    assert store.read_value(result.outputs["dataset:metrics/note"]) == "computed"
    assert store.read_value(result.outputs["dataset:metrics/metadata"]) == {"rows": 2}
    assert store.read_table(result.outputs["dataset:metrics/doubled"])["doubled"].tolist() == [4, 6]


def test_python_transform_timeout_is_hard_and_writes_traceback_log(tmp_path: Path):
    code = """import time

def transform(context):
    time.sleep(2)
    return {"doubled": context.table("rows"), "total": 0, "note": "late", "metadata": {}}
"""
    workspace = load_workspace(
        build_workspace(tmp_path / "workspace", code, timeout=0.1)
    )
    result = Executor(workspace).run("transform-contract", refresh=True)
    node = result.nodes["dataset:metrics"]

    assert result.status == "partial"
    assert node.status == "error"
    assert "exceeded 0.1 seconds" in node.error["message"]
    assert "execute_python_node" in node.error["traceback"]
    assert node.log is not None
    assert (workspace.root / node.log.path).is_file()


def test_dataset_transform_logs_and_tracebacks_redact_all_workspace_credentials(
    tmp_path: Path,
    monkeypatch,
):
    code = """def transform(context):
    context.progress(0.2, "loading direct-secret")
    context.log("using direct-user and direct-secret", token="token-secret")
    raise RuntimeError("failed with direct-user, direct-secret and token-secret")
"""
    root = build_workspace(tmp_path / "workspace", code)
    auth = root / "auth"
    auth.mkdir()
    (auth / "adapters.local.yaml").write_text(
        """adapters:
  private-api:
    type: python
    username: direct-user
    password: direct-secret
    secrets:
      api_token: DATAVIZ_TEST_DATASET_TOKEN
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATAVIZ_TEST_DATASET_TOKEN", "token-secret")
    workspace = load_workspace(root)
    events = []

    result = Executor(workspace).run(
        "transform-contract",
        refresh=True,
        observer=events.append,
    )

    serialized = result.model_dump_json()
    assert result.status == "partial"
    for secret in ("direct-user", "direct-secret", "token-secret"):
        assert secret not in serialized
    assert "[REDACTED]" in serialized
    log = result.nodes["dataset:metrics"].log
    assert log is not None
    log_value = ArtifactStore(root, result.run_id).read_value(log)
    for secret in ("direct-user", "direct-secret", "token-secret"):
        assert secret not in json.dumps(log_value)
        assert all(secret not in event.model_dump_json() for event in events)


def test_python_transform_abrupt_process_exit_is_structured(tmp_path: Path):
    code = """import os

def transform(context):
    os._exit(7)
"""
    workspace = load_workspace(build_workspace(tmp_path / "workspace", code))

    result = Executor(workspace).run("transform-contract", refresh=True)
    node = result.nodes["dataset:metrics"]

    assert result.status == "partial"
    assert node.status == "error"
    assert node.error["details"]["code"] == "python_process_exited"
    assert node.error["details"]["exit_code"] == 7
    assert node.log is not None


def test_code_dependency_hash_invalidates_transform_cache_and_isolates_imports(tmp_path: Path):
    code = """from helper import FACTOR

def transform(context):
    assert context.adapter is None
    frame = context.table("rows").copy()
    frame["doubled"] = frame["value"] * FACTOR
    return {"doubled": frame[["key", "doubled"]], "total": int(frame["value"].sum()), "note": "ok", "metadata": {}}
"""
    root = build_workspace(
        tmp_path / "workspace", code, code_dependencies=["helper.py"]
    )
    helper = root / "dashboards" / "transform-contract" / "transforms" / "helper.py"
    helper.write_text("FACTOR = 2\n", encoding="utf-8")
    workspace = load_workspace(root)
    executor = Executor(workspace)

    first = executor.run("transform-contract", refresh=True)
    second = executor.run("transform-contract")
    helper.write_text("FACTOR = 3\n", encoding="utf-8")
    third = executor.run("transform-contract")

    assert first.nodes["dataset:metrics"].result_origin == "executed"
    assert second.nodes["dataset:metrics"].result_origin == "cache"
    assert third.nodes["source:raw"].result_origin == "cache"
    assert third.nodes["dataset:metrics"].result_origin == "executed"
    frame = ArtifactStore(workspace.root, third.run_id).read_table(
        third.outputs["dataset:metrics/doubled"]
    )
    assert frame["doubled"].tolist() == [6, 9]


def test_output_schema_failure_is_node_local_and_has_diagnostic_artifact(tmp_path: Path):
    workspace = load_workspace(
        build_workspace(
            tmp_path / "workspace",
            MULTI_OUTPUT_CODE,
            output_schema="    schema:\n      - {name: missing_column}",
        )
    )
    result = Executor(workspace).run("transform-contract", refresh=True)
    node = result.nodes["dataset:metrics"]

    assert result.status == "partial"
    assert "missing required columns: missing_column" in node.error["message"]
    assert node.error["details"]["code"] == "output_schema_mismatch"
    assert node.error["details"]["missing"] == ["missing_column"]
    assert node.error["details"]["nulls"] == []
    assert node.error["details"]["dtypes"] == []
    assert node.error["details"]["remote_type"] == "ExecutionFailure"
    assert node.log and (workspace.root / node.log.path).exists()


def test_named_output_kinds_are_strict_and_machine_diagnosable(tmp_path: Path):
    code = """def transform(context):
    frame = context.table("rows").copy()
    frame["doubled"] = frame["value"] * 2
    return {
        "doubled": frame[["key", "doubled"]],
        "total": [1, 2],
        "note": "computed",
        "metadata": {"rows": len(frame)},
    }
"""
    workspace = load_workspace(build_workspace(tmp_path / "workspace", code))

    result = Executor(workspace).run("transform-contract", refresh=True)
    node = result.nodes["dataset:metrics"]

    assert result.status == "partial"
    assert node.status == "error"
    assert node.error["details"]["code"] == "output_kind_mismatch"
    assert node.error["details"]["expected"] == "scalar"


def test_named_output_bundle_rolls_back_partial_and_replaced_artifacts(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path, "run_bundle")
    previous = write_output(store, "dataset:metrics", "first", 7)

    with pytest.raises(ExecutionFailure, match="Output second must be a JSON scalar"):
        normalize_outputs(
            {"first": 9, "second": [1, 2]},
            store=store,
            node_id="dataset:metrics",
            declared={
                "first": OutputDefinition(kind="scalar"),
                "second": OutputDefinition(kind="scalar"),
            },
            named=True,
        )

    assert store.read_value(previous) == 7
    assert sorted(path.name for path in store.artifact_root.iterdir()) == [
        Path(previous.path).name
    ]


def test_existing_artifact_cannot_bypass_output_kind_or_schema_contract(tmp_path: Path):
    store = ArtifactStore(tmp_path, "run_contract")
    scalar = store.write_scalar("scalar", 7)

    with pytest.raises(ExecutionFailure) as kind_error:
        write_output(
            store,
            "dataset:result",
            "main",
            scalar,
            OutputDefinition(kind="table"),
        )
    assert kind_error.value.details == {
        "code": "output_kind_mismatch",
        "output": "main",
        "actual": "scalar",
        "expected": "table",
    }

    table = store.write_table(
        "rows",
        pd.DataFrame({"actual": [1]}),
    )
    with pytest.raises(ExecutionFailure) as schema_error:
        write_output(
            store,
            "dataset:result",
            "main",
            table,
            OutputDefinition(
                kind="table",
                schema=[ColumnDefinition(name="expected")],
            ),
        )
    assert schema_error.value.details["code"] == "output_schema_mismatch"
    assert schema_error.value.details["missing"] == ["expected"]

    other_store = ArtifactStore(tmp_path, "run_other")
    foreign = other_store.write_scalar("foreign", 9)
    with pytest.raises(ExecutionFailure) as ownership_error:
        write_output(store, "dataset:result", "main", foreign)
    assert ownership_error.value.details == {
        "code": "output_artifact_run_mismatch",
        "output": "main",
        "artifact_id": "foreign",
    }


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        ({"kind": "table", "format": "csv"}, "stored as format=parquet"),
        ({"kind": "scalar", "mime_type": "text/plain"}, "application/json"),
        ({"kind": "object", "schema": [{"name": "ignored"}]}, "only valid for kind=table"),
        ({"kind": "html", "format": "markdown"}, "stored as format=html"),
        ({"kind": "text", "format": "json"}, "supports format text, plain, or markdown"),
        (
            {"kind": "table", "schema": [{"name": "value"}, {"name": "value"}]},
            "duplicate columns: value",
        ),
    ],
)
def test_output_definition_rejects_storage_metadata_the_runtime_would_ignore(
    definition: dict[str, object],
    message: str,
):
    with pytest.raises(ValueError, match=message):
        OutputDefinition.model_validate(definition)


def test_artifact_names_are_collision_safe_and_paths_stay_in_managed_storage(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path, "run_contract")
    first = write_output(store, "source:a__b", "main", 1)
    second = write_output(store, "source:a", "b", 2)

    assert first.artifact_id != second.artifact_id
    assert first.path != second.path
    assert store.read_value(first) == 1
    assert store.read_value(second) == 2

    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="managed .dataviz storage"):
        ArtifactDescriptor(
            artifact_id="escaped",
            kind="object",
            format="json",
            path=str(outside),
            content_hash="0" * 64,
        )
    # Storage keeps the same defense when a descriptor bypasses normal model
    # validation (for example, untrusted persisted metadata).
    escaped = ArtifactDescriptor.model_construct(
        artifact_id="escaped",
        kind="object",
        format="json",
        path=str(outside),
        content_hash="0" * 64,
    )
    with pytest.raises(ValueError, match="managed Dataviz storage"):
        store.resolve(escaped)
    with pytest.raises(ValueError, match="Invalid Artifact id"):
        store.write_scalar("../escaped", 1)
    with pytest.raises(ValueError, match="Invalid Run id"):
        ArtifactStore(tmp_path, "../escaped")


def test_artifact_files_are_hashed_and_copied_without_whole_file_reads(
    tmp_path: Path,
    monkeypatch,
):
    store = ArtifactStore(tmp_path, "run_streaming")
    source = tmp_path / "source.bin"
    source.write_bytes(b"streamed-file-payload")

    def reject_read_bytes(_path):
        raise AssertionError(
            "Artifact persistence must not buffer whole files with Path.read_bytes"
        )

    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)
    table = store.write_table("table", pd.DataFrame({"value": [1, 2, 3]}))
    copied = store.write_file(
        "binary",
        source,
        kind="file",
        format="bin",
        suffix="bin",
        mime_type="application/octet-stream",
    )

    store.verify_owned(table)
    store.verify_owned(copied)
    materialized = ArtifactStore(tmp_path, "run_materialized").materialize(copied)
    assert materialized.content_hash == copied.content_hash


def test_declared_python_dependency_is_validated_before_execution(tmp_path: Path):
    workspace = load_workspace(
        build_workspace(
            tmp_path / "workspace",
            MULTI_OUTPUT_CODE,
            python_dependencies=["definitely-not-a-real-dataviz-package>=99"],
        )
    )
    diagnostics = validate_workspace(workspace)

    assert any(
        item.code == "validation"
        and "is not installed" in item.message
        and item.field == "python_dependencies"
        for item in diagnostics
    )


def test_query_cancellation_terminates_dataset_transform_process(tmp_path: Path):
    code = """import time

def transform(context):
    context.progress(0.1, "started")
    time.sleep(5)
    return {"doubled": context.table("rows"), "total": 0, "note": "late", "metadata": {}}
"""
    workspace = load_workspace(build_workspace(tmp_path / "workspace", code))
    executor = Executor(workspace)
    cancel_event = threading.Event()
    snapshots = []
    events = []
    holder = {}

    worker = threading.Thread(
        target=lambda: holder.setdefault(
            "result",
            executor.run(
                "transform-contract",
                refresh=True,
                cancel_event=cancel_event,
                snapshot_observer=snapshots.append,
                observer=events.append,
            ),
        )
    )
    started = time.monotonic()
    worker.start()
    for _ in range(200):
        if any(
            event.event == "node_progress"
            and event.node_id == "dataset:metrics"
            for event in events
        ):
            break
        time.sleep(0.02)
    cancel_event.set()
    worker.join(timeout=3)

    assert not worker.is_alive()
    assert time.monotonic() - started < 3
    result = holder["result"]
    assert result.status == "cancelled"
    assert result.nodes["dataset:metrics"].status == "cancelled"
    assert result.nodes["dataset:metrics"].error["code"] == "cancelled"
    assert any(
        event.event == "node_progress"
        and event.node_id == "dataset:metrics"
        and event.data["value"] == 0.1
        for event in events
    )
