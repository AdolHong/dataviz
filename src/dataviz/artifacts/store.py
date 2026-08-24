from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from dataviz.artifacts.models import ArtifactDescriptor
from dataviz.filesystem import atomic_copy_file, atomic_write_bytes, sha256_file


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ArtifactStore:
    def __init__(self, workspace_root: Path, run_id: str):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9._-]{0,127}", run_id):
            raise ValueError("Invalid Run id")
        self.workspace_root = workspace_root.resolve()
        self.run_id = run_id
        self.state_root = self.workspace_root / ".dataviz"
        self.run_root = self.workspace_root / ".dataviz" / "runs" / run_id
        self.artifact_root = self.run_root / "artifacts"
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def _artifact_path(self, artifact_id: str, suffix: str) -> Path:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9._-]{0,255}", artifact_id):
            raise ValueError("Invalid Artifact id")
        return self.artifact_root / f"{artifact_id}{suffix}"

    def _relative(self, path: Path) -> str:
        return str(path.relative_to(self.workspace_root))

    def resolve_managed(self, descriptor: ArtifactDescriptor) -> Path:
        """Resolve any trusted Dataviz-managed Artifact, including a cache entry."""
        path = (self.workspace_root / descriptor.path).resolve()
        state_root = self.state_root.resolve()
        if not path.is_relative_to(state_root):
            raise ValueError(
                f"Artifact path escapes managed Dataviz storage: {descriptor.artifact_id}"
            )
        return path

    def resolve(self, descriptor: ArtifactDescriptor) -> Path:
        """Resolve an Artifact only when it belongs to this Query Run."""
        path = self.resolve_managed(descriptor)
        if not path.is_relative_to(self.run_root.resolve()):
            raise ValueError(
                f"Artifact does not belong to Run {self.run_id}: {descriptor.artifact_id}"
            )
        return path

    def verify_owned(self, descriptor: ArtifactDescriptor) -> Path:
        """Verify a returned descriptor is a complete Artifact of this Run."""
        path = self.resolve(descriptor)
        if not path.is_file():
            raise ValueError(f"Artifact is not a readable Run file: {descriptor.artifact_id}")
        if sha256_file(path) != descriptor.content_hash:
            raise ValueError(f"Artifact content hash does not match: {descriptor.artifact_id}")
        return path

    def materialize(self, descriptor: ArtifactDescriptor) -> ArtifactDescriptor:
        """Copy a verified cache Artifact into this Run before publishing it."""
        source = self.resolve_managed(descriptor)
        if not source.is_file():
            raise ValueError(f"Artifact is not readable: {descriptor.artifact_id}")
        destination = self._artifact_path(
            descriptor.artifact_id,
            source.suffix or ".bin",
        )
        if source != destination.resolve():
            try:
                atomic_copy_file(
                    source,
                    destination,
                    expected_sha256=descriptor.content_hash,
                )
            except ValueError as error:
                raise ValueError(
                    f"Artifact content hash does not match: {descriptor.artifact_id}"
                ) from error
        elif sha256_file(source) != descriptor.content_hash:
            raise ValueError(f"Artifact content hash does not match: {descriptor.artifact_id}")
        return descriptor.model_copy(
            deep=True,
            update={"path": self._relative(destination)},
        )

    def write_run_document(self, filename: str, content: str) -> Path:
        """Atomically persist one machine-readable Run document."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9._-]{0,255}\.json", filename):
            raise ValueError("Invalid Run document name")
        path = self.run_root / filename
        atomic_write_bytes(path, content.encode("utf-8"))
        return path

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
        path = self._artifact_path(artifact_id, ".json")
        atomic_write_bytes(path, content)
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
        path = self._artifact_path(artifact_id, suffix)
        atomic_write_bytes(path, raw)
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
        path = self._artifact_path(artifact_id, f".{suffix.lstrip('.')}")
        atomic_write_bytes(path, content)
        return ArtifactDescriptor(
            artifact_id=artifact_id,
            kind=kind,
            format=format,
            path=self._relative(path),
            mime_type=mime_type,
            metadata=metadata or {},
            content_hash=sha256_bytes(content),
        )

    def write_file(
        self,
        artifact_id: str,
        source: Path,
        *,
        kind: str,
        format: str,
        suffix: str,
        mime_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactDescriptor:
        """Copy a file output into the Run store without buffering it in memory."""
        path = self._artifact_path(artifact_id, f".{suffix.lstrip('.')}")
        content_hash = atomic_copy_file(source, path)
        return ArtifactDescriptor(
            artifact_id=artifact_id,
            kind=kind,
            format=format,
            path=self._relative(path),
            mime_type=mime_type,
            metadata=metadata or {},
            content_hash=content_hash,
        )

    def write_table(
        self, artifact_id: str, dataframe: pd.DataFrame, *, metadata: dict[str, Any] | None = None
    ) -> ArtifactDescriptor:
        path = self._artifact_path(artifact_id, ".parquet")
        temporary = path.parent / f".{path.stem}.{uuid.uuid4().hex}.tmp.parquet"
        try:
            dataframe.to_parquet(temporary, index=False)
            content_hash = sha256_file(temporary)
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
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
            metadata={"row_count": len(dataframe), **(metadata or {})},
            content_hash=content_hash,
        )

    def read_table(self, descriptor: ArtifactDescriptor) -> pd.DataFrame:
        path = self.resolve(descriptor)
        return pd.read_parquet(path)

    def read_arrow_table(self, descriptor: ArtifactDescriptor) -> pa.Table:
        """Read a table artifact without materializing a pandas/JSON copy."""
        path = self.resolve(descriptor)
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
        if descriptor.kind in {"scalar", "object", "chart"} or descriptor.format.endswith("json"):
            return json.loads(path.read_text(encoding="utf-8"))
        if descriptor.kind in {"text", "html"}:
            return path.read_text(encoding="utf-8")
        return path
