from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

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
        suffix = ".md" if format == "markdown" else ".txt"
        raw = content.encode("utf-8")
        path = self.artifact_root / f"{artifact_id}{suffix}"
        path.write_bytes(raw)
        return ArtifactDescriptor(
            artifact_id=artifact_id,
            kind=kind,
            format=format,
            path=self._relative(path),
            mime_type="text/markdown" if format == "markdown" else "text/plain",
            metadata=metadata or {},
            content_hash=sha256_bytes(raw),
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

    def copy_into_run(self, descriptor: ArtifactDescriptor, source: Path) -> ArtifactDescriptor:
        destination = self.artifact_root / source.name
        shutil.copy2(source, destination)
        return descriptor.model_copy(update={"path": self._relative(destination)})

