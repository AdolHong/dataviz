from __future__ import annotations

import mimetypes
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
    try:
        return pd.DataFrame(value)
    except Exception as exc:
        raise ExecutionFailure("Table output must be convertible to a DataFrame") from exc


def validate_table_schema(
    frame: pd.DataFrame,
    schema: list[ColumnDefinition],
    *,
    label: str,
) -> None:
    """Validate the stable, intentionally small table contract used by the DSL."""
    if not schema:
        return
    missing = [column.name for column in schema if column.required and column.name not in frame]
    if missing:
        raise ExecutionFailure(
            f"{label} is missing required columns: {', '.join(missing)}"
        )
    errors: list[str] = []
    for column in schema:
        if column.name not in frame:
            continue
        series = frame[column.name]
        if column.dtype and str(series.dtype) != column.dtype:
            errors.append(
                f"{column.name} has dtype {series.dtype}, expected {column.dtype}"
            )
        if column.nullable is False and series.isna().any():
            errors.append(f"{column.name} contains null values")
    if errors:
        raise ExecutionFailure(f"{label} schema mismatch: {'; '.join(errors)}")


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
        return value

    declared_kind = definition.kind if definition else None
    artifact_id = _artifact_id(node_id, output_name)
    details = {"output": output_name, **(metadata or {})}

    if declared_kind == "table" or (declared_kind is None and isinstance(value, (pd.DataFrame, pa.Table))):
        frame = _table(value)
        validate_table_schema(
            frame,
            definition.schema_ if definition else [],
            label=f"Output {output_name}",
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
            str(value),
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
        raise ExecutionFailure(f"Required outputs are missing: {', '.join(sorted(missing))}")
    unknown = set(raw_outputs) - set(definitions) if definitions else set()
    if definitions and unknown:
        raise ExecutionFailure(f"Undeclared outputs were returned: {', '.join(sorted(unknown))}")

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
