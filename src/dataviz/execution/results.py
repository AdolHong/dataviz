from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field

from dataviz.artifacts import ArtifactDescriptor


class NodeResult(BaseModel):
    node_id: str
    node_type: str
    status: Literal["not_run", "queued", "running", "succeeded", "failed", "blocked", "cancelled"]
    result_origin: Literal["executed", "cache"] | None = None
    freshness: Literal["current", "stale"] = "current"
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    artifacts: list[ArtifactDescriptor] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class RunResult(BaseModel):
    run_id: str
    status: Literal["running", "success", "partial", "failed", "cancelled"]
    workspace: str
    dashboard: str
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    selections: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("selections", "filters"),
    )
    nodes: dict[str, NodeResult] = Field(default_factory=dict)
    outputs: dict[str, list[ArtifactDescriptor]] = Field(default_factory=dict)
    warnings: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def filters(self) -> dict[str, Any]:
        """Deprecated compatibility alias for persisted pre-selection runs."""
        return self.selections
