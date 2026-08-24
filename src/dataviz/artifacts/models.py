from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dataviz.identifiers import StableId


ArtifactKind = Literal["table", "scalar", "object", "text", "chart", "image", "html", "file"]


class ArtifactDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    artifact_id: StableId
    kind: ArtifactKind
    format: str
    path: str
    mime_type: str | None = None
    schema_: list[dict[str, Any]] | None = Field(None, alias="schema")
    preview: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def require_managed_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            path.is_absolute()
            or ".." in path.parts
            or len(path.parts) < 3
            or path.parts[0] != ".dataviz"
        ):
            raise ValueError("artifact path must be relative to managed .dataviz storage")
        return path.as_posix()
