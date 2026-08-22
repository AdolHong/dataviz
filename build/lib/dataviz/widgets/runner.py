from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from dataviz.artifacts import ArtifactDescriptor, EChartsOutput, TextOutput
from dataviz.errors import WidgetFailure
from dataviz.execution.context import ExecutionContext
from dataviz.execution.imports import load_entrypoint
from dataviz.workspace.models import WidgetDefinition


def safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "artifact"


def _convert(value: Any, artifact_id: str, context: ExecutionContext, title: str) -> ArtifactDescriptor:
    if not context.store:
        raise WidgetFailure("Artifact store is unavailable")
    store = context.store
    metadata = {"title": title}

    if isinstance(value, ArtifactDescriptor):
        return value
    if isinstance(value, pd.DataFrame):
        return store.write_table(artifact_id, value, metadata=metadata)
    if isinstance(value, EChartsOutput):
        return store.write_json(
            artifact_id, value.options, kind="chart", format="echarts-json", metadata=metadata
        )
    if isinstance(value, TextOutput):
        return store.write_text(
            artifact_id, value.content, kind="text", format=value.format, metadata=metadata
        )

    try:
        from plotly.basedatatypes import BaseFigure

        if isinstance(value, BaseFigure):
            return store.write_json(
                artifact_id,
                json.loads(value.to_json()),
                kind="chart",
                format="plotly-json",
                metadata=metadata,
            )
    except ImportError:
        pass

    try:
        from matplotlib.figure import Figure

        if isinstance(value, Figure):
            buffer = io.BytesIO()
            value.savefig(buffer, format="svg", bbox_inches="tight")
            return store.write_bytes(
                artifact_id,
                buffer.getvalue(),
                kind="image",
                format="svg",
                suffix="svg",
                mime_type="image/svg+xml",
                metadata=metadata,
            )
    except ImportError:
        pass

    if isinstance(value, Path):
        suffix = value.suffix.lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(
            suffix, "application/octet-stream"
        )
        kind = "image" if mime.startswith("image/") else "file"
        return store.write_bytes(
            artifact_id,
            value.read_bytes(),
            kind=kind,
            format=suffix or "binary",
            suffix=suffix or "bin",
            mime_type=mime,
            metadata=metadata,
        )
    if isinstance(value, str):
        return store.write_text(artifact_id, value, metadata=metadata)
    if isinstance(value, (int, float, bool)) or value is None:
        return store.write_json(artifact_id, value, kind="scalar", format="json", metadata=metadata)
    if isinstance(value, dict):
        if value.get("kind") == "echarts" and isinstance(value.get("options"), dict):
            return store.write_json(
                artifact_id,
                value["options"],
                kind="chart",
                format="echarts-json",
                metadata=metadata,
            )
        return store.write_json(artifact_id, value, kind="scalar", format="json", metadata=metadata)
    raise WidgetFailure(f"Unsupported widget output: {type(value).__name__}")


def execute_widget(
    definition_path: Path, definition: WidgetDefinition, context: ExecutionContext
) -> list[ArtifactDescriptor]:
    if definition.output.type == "matplotlib":
        import matplotlib

        matplotlib.use("Agg", force=True)
    code_path = (definition_path.parent / definition.code).resolve()
    function = load_entrypoint(code_path, definition.entrypoint)
    try:
        output = function(context)
    except Exception as exc:
        raise WidgetFailure(f"Widget execution failed: {exc}", file=code_path) from exc

    values = output if isinstance(output, (list, tuple)) else [output]
    result: list[ArtifactDescriptor] = []
    for index, value in enumerate(values):
        suffix = f"-{index + 1}" if len(values) > 1 else ""
        result.append(_convert(value, safe_id(f"{definition.id}{suffix}"), context, definition.title))
    return result
