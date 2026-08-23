from __future__ import annotations

import mimetypes
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.errors import ExecutionFailure
from dataviz.workspace.models import ColumnDefinition, OutputDefinition


OutputBundle = dict[str, ArtifactDescriptor]


def _artifact_id(node_id: str, output_name: str) -> str:
    raw = node_id if output_name == "main" else f"{node_id}__{output_name}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)


def _table(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, pa.Table):
        return value.to_pandas()
    if not isinstance(value, (Mapping, list, tuple)):
        raise ExecutionFailure(
            "Table output must be a DataFrame, Arrow Table, rows[], or column mapping",
            details={"code": "output_kind_mismatch", "expected": "table"},
        )
    try:
        return pd.DataFrame(value)
    except Exception as exc:
        raise ExecutionFailure("Table output must be convertible to a DataFrame") from exc


def _require_json(value: Any, *, label: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ExecutionFailure(
            f"{label} must be strict JSON data: {error}",
            details={"code": "output_not_json_serializable", "label": label},
        ) from error


def _validate_declared_value(value: Any, definition: OutputDefinition, *, label: str) -> None:
    kind = definition.kind
    if kind == "table":
        return
    if kind == "scalar":
        if value is not None and (
            isinstance(value, (Mapping, list, tuple, set))
            or not isinstance(value, (str, int, float, bool))
        ):
            raise ExecutionFailure(
                f"{label} must be a JSON scalar",
                details={"code": "output_kind_mismatch", "expected": "scalar"},
            )
        if isinstance(value, float) and not math.isfinite(value):
            raise ExecutionFailure(
                f"{label} must be finite",
                details={"code": "output_not_json_serializable", "expected": "scalar"},
            )
        return
    if kind in {"text", "html"}:
        if not isinstance(value, str):
            raise ExecutionFailure(
                f"{label} must be a string",
                details={"code": "output_kind_mismatch", "expected": kind},
            )
        return
    if kind in {"object", "chart"}:
        if not isinstance(value, Mapping):
            raise ExecutionFailure(
                f"{label} must be a JSON object",
                details={"code": "output_kind_mismatch", "expected": kind},
            )
        _require_json(value, label=label)
        return
    if kind in {"image", "file"} and not isinstance(value, (str, Path)):
        raise ExecutionFailure(
            f"{label} must be a file path",
            details={"code": "output_kind_mismatch", "expected": kind},
        )


def validate_table_schema(
    frame: pd.DataFrame,
    schema: list[ColumnDefinition],
    *,
    label: str,
    code: str = "output_schema_mismatch",
) -> None:
    """Validate the stable, intentionally small table contract used by the DSL."""
    if not schema:
        return
    missing = [column.name for column in schema if column.required and column.name not in frame]
    if missing:
        raise ExecutionFailure(
            f"{label} is missing required columns: {', '.join(missing)}",
            details={"code": code, "missing": missing, "nulls": [], "dtypes": []},
        )
    errors: list[str] = []
    nulls: list[str] = []
    dtypes: list[dict[str, str]] = []
    for column in schema:
        if column.name not in frame:
            continue
        series = frame[column.name]
        if column.dtype and str(series.dtype) != column.dtype:
            dtypes.append(
                {
                    "column": column.name,
                    "actual": str(series.dtype),
                    "expected": column.dtype,
                }
            )
            errors.append(
                f"{column.name} has dtype {series.dtype}, expected {column.dtype}"
            )
        if column.nullable is False and series.isna().any():
            nulls.append(column.name)
            errors.append(f"{column.name} contains null values")
    if errors:
        raise ExecutionFailure(
            f"{label} schema mismatch: {'; '.join(errors)}",
            details={"code": code, "missing": [], "nulls": nulls, "dtypes": dtypes},
        )


def write_output(
    store: ArtifactStore,
    node_id: str,
    output_name: str,
    value: Any,
    definition: OutputDefinition | None = None,
    *,
    metadata: dict[str, Any] | None = None,
) -> ArtifactDescriptor:
    if isinstance(value, ArtifactDescriptor):
        if definition is not None and value.kind != definition.kind:
            raise ExecutionFailure(
                f"Output {output_name} references a {value.kind} Artifact, "
                f"but its declared kind is {definition.kind}",
                details={
                    "code": "output_kind_mismatch",
                    "output": output_name,
                    "actual": value.kind,
                    "expected": definition.kind,
                },
            )
        if definition is not None and definition.kind == "table":
            try:
                frame = store.read_table(value)
            except Exception as error:
                raise ExecutionFailure(
                    f"Output {output_name} references an unreadable table Artifact",
                    details={
                        "code": "output_contract_mismatch",
                        "output": output_name,
                        "artifact_id": value.artifact_id,
                    },
                ) from error
            validate_table_schema(
                frame,
                definition.schema_,
                label=f"Output {output_name}",
                code="output_schema_mismatch",
            )
        return value

    declared_kind = definition.kind if definition else None
    artifact_id = _artifact_id(node_id, output_name)
    details = {"output": output_name, **(metadata or {})}
    if definition is not None:
        _validate_declared_value(value, definition, label=f"Output {output_name}")

    if declared_kind == "table" or (declared_kind is None and isinstance(value, (pd.DataFrame, pa.Table))):
        frame = _table(value)
        validate_table_schema(
            frame,
            definition.schema_ if definition else [],
            label=f"Output {output_name}",
            code="output_schema_mismatch",
        )
        return store.write_table(artifact_id, frame, metadata=details)
    if declared_kind == "scalar" or (
        declared_kind is None and (value is None or isinstance(value, (bool, int, float)))
    ):
        return store.write_scalar(artifact_id, value, metadata=details)
    if declared_kind in {"text", "html"} or (declared_kind is None and isinstance(value, str)):
        kind = declared_kind or "text"
        return store.write_text(
            artifact_id,
            value,
            kind=kind,
            format=(definition.format if definition and definition.format else kind),
            metadata=details,
        )
    if declared_kind in {"object", "chart"}:
        return store.write_json(
            artifact_id,
            value,
            kind=declared_kind,
            format=(definition.format if definition and definition.format else "json"),
            metadata=details,
        )
    if declared_kind in {"image", "file"}:
        path = Path(value)
        if not path.exists() or not path.is_file():
            raise ExecutionFailure(f"{declared_kind.title()} output is not a file: {path}")
        raw = path.read_bytes()
        mime_type = (
            definition.mime_type if definition and definition.mime_type else mimetypes.guess_type(path.name)[0]
        ) or "application/octet-stream"
        return store.write_bytes(
            artifact_id,
            raw,
            kind=declared_kind,
            format=(definition.format if definition and definition.format else path.suffix.lstrip(".") or "binary"),
            suffix=path.suffix or ".bin",
            mime_type=mime_type,
            metadata=details,
        )
    return store.write_object(artifact_id, value, metadata=details)


def normalize_outputs(
    value: Any,
    *,
    store: ArtifactStore,
    node_id: str,
    declared: dict[str, OutputDefinition] | None = None,
    named: bool = False,
    metadata: dict[str, Any] | None = None,
) -> OutputBundle:
    definitions = declared or {}
    if named and isinstance(value, Mapping):
        raw_outputs = dict(value)
    else:
        raw_outputs = {"main": value}

    missing = [name for name, definition in definitions.items() if definition.required and name not in raw_outputs]
    if missing:
        raise ExecutionFailure(
            f"Required outputs are missing: {', '.join(sorted(missing))}",
            details={"code": "output_contract_mismatch", "missing": sorted(missing), "unknown": []},
        )
    unknown = set(raw_outputs) - set(definitions) if definitions else set()
    if definitions and unknown:
        raise ExecutionFailure(
            f"Undeclared outputs were returned: {', '.join(sorted(unknown))}",
            details={"code": "output_contract_mismatch", "missing": [], "unknown": sorted(unknown)},
        )

    return {
        name: write_output(
            store,
            node_id,
            name,
            item,
            definitions.get(name),
            metadata=metadata,
        )
        for name, item in raw_outputs.items()
    }
