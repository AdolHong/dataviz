from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from dataviz.artifacts.models import ArtifactDescriptor


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ArtifactStore:
    def __init__(self, workspace_root: Path, run_id: str):
        self.workspace_root = workspace_root
        self.run_id = run_id
        self.run_root = workspace_root / ".dataviz" / "runs" / run_id
        self.artifact_root = self.run_root / "artifacts"
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def _relative(self, path: Path) -> str:
        return str(path.relative_to(self.workspace_root))

    def resolve(self, descriptor: ArtifactDescriptor) -> Path | None:
        return (self.workspace_root / descriptor.path).resolve() if descriptor.path else None

    def write_json(
        self,
        artifact_id: str,
        data: Any,
        *,
        kind: str,
        format: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactDescriptor:
        content = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        path = self.artifact_root / f"{artifact_id}.json"
        path.write_bytes(content)
        return ArtifactDescriptor(
            artifact_id=artifact_id,
            kind=kind,
            format=format,
            path=self._relative(path),
            mime_type="application/json",
            metadata=metadata or {},
            content_hash=sha256_bytes(content),
        )

    def write_text(
        self,
        artifact_id: str,
        content: str,
        *,
        kind: str = "text",
        format: str = "markdown",
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactDescriptor:
        suffix = ".md" if format == "markdown" else ".html" if format == "html" else ".txt"
        raw = content.encode("utf-8")
        path = self.artifact_root / f"{artifact_id}{suffix}"
        path.write_bytes(raw)
        return ArtifactDescriptor(
            artifact_id=artifact_id,
            kind=kind,
            format=format,
            path=self._relative(path),
            mime_type=(
                "text/markdown"
                if format == "markdown"
                else "text/html"
                if format == "html"
                else "text/plain"
            ),
            metadata=metadata or {},
            content_hash=sha256_bytes(raw),
        )

    def write_scalar(
        self, artifact_id: str, value: Any, *, metadata: dict[str, Any] | None = None
    ) -> ArtifactDescriptor:
        return self.write_json(
            artifact_id,
            value,
            kind="scalar",
            format="json",
            metadata=metadata,
        )

    def write_object(
        self, artifact_id: str, value: Any, *, metadata: dict[str, Any] | None = None
    ) -> ArtifactDescriptor:
        return self.write_json(
            artifact_id,
            value,
            kind="object",
            format="json",
            metadata=metadata,
        )

    def write_bytes(
        self,
        artifact_id: str,
        content: bytes,
        *,
        kind: str,
        format: str,
        suffix: str,
        mime_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactDescriptor:
        path = self.artifact_root / f"{artifact_id}.{suffix.lstrip('.')}"
        path.write_bytes(content)
        return ArtifactDescriptor(
            artifact_id=artifact_id,
            kind=kind,
            format=format,
            path=self._relative(path),
            mime_type=mime_type,
            metadata=metadata or {},
            content_hash=sha256_bytes(content),
        )

    def write_table(
        self, artifact_id: str, dataframe: pd.DataFrame, *, metadata: dict[str, Any] | None = None
    ) -> ArtifactDescriptor:
        path = self.artifact_root / f"{artifact_id}.parquet"
        dataframe.to_parquet(path, index=False)
        content = path.read_bytes()
        schema = [{"name": str(name), "dtype": str(dtype)} for name, dtype in dataframe.dtypes.items()]
        preview = json.loads(dataframe.head(100).to_json(orient="records", date_format="iso"))
        return ArtifactDescriptor(
            artifact_id=artifact_id,
            kind="table",
            format="parquet",
            path=self._relative(path),
            mime_type="application/vnd.apache.parquet",
            schema=schema,
            preview=preview,
            metadata={"row_count": int(len(dataframe)), **(metadata or {})},
            content_hash=sha256_bytes(content),
        )

    def read_table(self, descriptor: ArtifactDescriptor) -> pd.DataFrame:
        path = self.resolve(descriptor)
        if not path:
            raise ValueError("Table artifact has no path")
        return pd.read_parquet(path)

    def read_arrow_table(self, descriptor: ArtifactDescriptor) -> pa.Table:
        """Read a table artifact without materializing a pandas/JSON copy."""
        path = self.resolve(descriptor)
        if not path:
            raise ValueError("Table artifact has no path")
        if descriptor.format == "parquet":
            return pq.read_table(path)
        return pa.Table.from_pandas(self.read_table(descriptor), preserve_index=False)

    def read_arrow_ipc(self, descriptor: ArtifactDescriptor) -> bytes:
        """Serialize a table artifact as an Arrow IPC stream for browsers."""
        table = self.read_arrow_table(descriptor)
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        return sink.getvalue().to_pybytes()

    def read_value(self, descriptor: ArtifactDescriptor) -> Any:
        path = self.resolve(descriptor)
        if descriptor.kind == "table":
            return self.read_table(descriptor)
        if descriptor.inline is not None:
            return descriptor.inline
        if not path:
            raise ValueError(f"Artifact {descriptor.artifact_id} has no readable value")
        if descriptor.kind in {"scalar", "object", "chart"} or descriptor.format.endswith("json"):
            return json.loads(path.read_text(encoding="utf-8"))
        if descriptor.kind in {"text", "html"}:
            return path.read_text(encoding="utf-8")
        return path

    def copy_into_run(self, descriptor: ArtifactDescriptor, source: Path) -> ArtifactDescriptor:
        destination = self.artifact_root / source.name
        shutil.copy2(source, destination)
        return descriptor.model_copy(update={"path": self._relative(destination)})
