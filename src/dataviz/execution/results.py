from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dataviz.artifacts import ArtifactDescriptor


class NodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: str
    status: Literal["not_run", "queued", "running", "succeeded", "failed", "blocked", "cancelled"]
    result_origin: Literal["executed", "cache"] | None = None
    freshness: Literal["current", "stale"] = "current"
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    outputs: dict[str, ArtifactDescriptor] = Field(default_factory=dict)
    log: ArtifactDescriptor | None = None
    error: dict[str, Any] | None = None

class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["running", "success", "partial", "failed", "cancelled"]
    workspace: str
    dashboard: str
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    selections: dict[str, Any] = Field(default_factory=dict)
    nodes: dict[str, NodeResult] = Field(default_factory=dict)
    outputs: dict[str, ArtifactDescriptor] = Field(default_factory=dict)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
