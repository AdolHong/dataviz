from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ArtifactKind = Literal["table", "scalar", "text", "chart", "image", "html", "file"]


class ArtifactDescriptor(BaseModel):
    model_config = ConfigDict(extra="allow")

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


class EChartsOutput:
    def __init__(self, options: dict[str, Any]):
        self.options = options


class TextOutput:
    def __init__(self, content: str, *, format: str = "markdown"):
        self.content = content
        self.format = format


def echarts(options: dict[str, Any]) -> EChartsOutput:
    return EChartsOutput(options)


def markdown(content: str) -> TextOutput:
    return TextOutput(content, format="markdown")

