from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field


class ExecutionEvent(BaseModel):
    event: str
    run_id: str
    node_id: str | None = None
    node_type: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: int | None = None
    message: str | None = None
    error: dict[str, Any] | None = None
    data: dict[str, Any] = Field(default_factory=dict)


EventObserver = Callable[[ExecutionEvent], None]

