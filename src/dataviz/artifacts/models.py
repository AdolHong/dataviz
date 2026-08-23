from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ArtifactKind = Literal["table", "scalar", "object", "text", "chart", "image", "html", "file"]


class ArtifactDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    artifact_id: str
    kind: ArtifactKind
    format: str
    path: str | None = None
    inline: Any = None
    mime_type: str | None = None
    schema_: list[dict[str, Any]] | None = Field(None, alias="schema")
    preview: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str

