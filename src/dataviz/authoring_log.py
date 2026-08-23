from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from dataviz import __version__
from dataviz.errors import ValidationFailure


AUTHORING_EVENT_SCHEMA = "dataviz/authoring-event/v1"
AUTHORING_LOG_REPORT_SCHEMA = "dataviz/authoring-log-report/v1"
AUTHORING_LOG_NAME = "dataviz-authoring.jsonl"


class AuthoringEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["dataviz/authoring-event/v1"] = Field(
        AUTHORING_EVENT_SCHEMA, alias="schema"
    )
    event: str
    session_id: str
    timestamp: datetime
    dataviz_version: str = __version__


class AuthoringStarted(AuthoringEvent):
    event: Literal["started"] = "started"
    task: str
    dashboard_id: str | None = None
    model: str | None = None
    tool: str | None = None
    notes: str = ""


class AuthoringFriction(AuthoringEvent):
    event: Literal["friction"] = "friction"
    category: Literal[
        "documentation",
        "schema",
        "component",
        "runtime",
        "tooling",
        "release",
        "other",
    ]
    message: str
    reference: str | None = None


class AuthoringFinished(AuthoringEvent):
    event: Literal["finished"] = "finished"
    outcome: Literal["success", "partial", "failed", "abandoned"]
    first_attempt_success: bool | None = None
    correction_rounds: int = Field(0, ge=0)
    elapsed_seconds: float = Field(ge=0)
    input_tokens: int | None = Field(None, ge=0)
    output_tokens: int | None = Field(None, ge=0)
    token_source: Literal["reported", "unknown"] = "unknown"
    docs_used: list[str] = Field(default_factory=list)
    notes: str = ""


AuthoringEventValue = Annotated[
    AuthoringStarted | AuthoringFriction | AuthoringFinished,
    Field(discriminator="event"),
]
EVENT_ADAPTER = TypeAdapter(AuthoringEventValue)


def authoring_log_path(workspace: Path) -> Path:
    root = workspace.resolve()
    if not root.is_dir() or not (root / "workspace.yaml").is_file():
        raise ValidationFailure(
            "Authoring log requires a Dataviz Workspace",
            file=root,
            details={"required": "workspace.yaml"},
        )
    return root / AUTHORING_LOG_NAME


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _append(path: Path, event: AuthoringEventValue) -> None:
    payload = EVENT_ADAPTER.dump_json(event, by_alias=True).decode("utf-8")
    # One append-only JSON object per line is deliberately Git-friendly and
    # avoids rewriting measurements from earlier authoring sessions.
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_authoring_events(
    workspace: Path,
) -> tuple[list[AuthoringEventValue], list[dict[str, Any]]]:
    path = authoring_log_path(workspace)
    if not path.exists():
        return [], []
    events: list[AuthoringEventValue] = []
    diagnostics: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            events.append(EVENT_ADAPTER.validate_json(raw))
        except Exception as error:
            diagnostics.append(
                {
                    "line": line_number,
                    "code": "invalid_authoring_event",
                    "message": str(error),
                }
            )
    return events, diagnostics


def _session_events(
    workspace: Path, session_id: str
) -> tuple[AuthoringStarted, list[AuthoringEventValue]]:
    events, diagnostics = read_authoring_events(workspace)
    matching = [event for event in events if event.session_id == session_id]
    start = next((event for event in matching if isinstance(event, AuthoringStarted)), None)
    if start is None:
        raise ValidationFailure(
            f"Unknown authoring session: {session_id}",
            details={"log_diagnostics": diagnostics},
        )
    return start, matching


def start_authoring_session(
    workspace: Path,
    *,
    task: str,
    dashboard_id: str | None = None,
    model: str | None = None,
    tool: str | None = None,
    notes: str = "",
) -> AuthoringStarted:
    if not task.strip():
        raise ValidationFailure("Authoring task cannot be empty")
    path = authoring_log_path(workspace)
    event = AuthoringStarted(
        session_id=f"authoring_{uuid4().hex[:12]}",
        timestamp=_now(),
        task=task.strip(),
        dashboard_id=dashboard_id.strip() if dashboard_id else None,
        model=model.strip() if model else None,
        tool=tool.strip() if tool else None,
        notes=notes.strip(),
    )
    _append(path, event)
    return event


def add_authoring_friction(
    workspace: Path,
    session_id: str,
    *,
    category: str,
    message: str,
    reference: str | None = None,
) -> AuthoringFriction:
    if not message.strip():
        raise ValidationFailure("Friction message cannot be empty")
    _, events = _session_events(workspace, session_id)
    if any(isinstance(event, AuthoringFinished) for event in events):
        raise ValidationFailure(f"Authoring session is already finished: {session_id}")
    try:
        event = AuthoringFriction(
            session_id=session_id,
            timestamp=_now(),
            category=category,
            message=message.strip(),
            reference=reference.strip() if reference else None,
        )
    except Exception as error:
        raise ValidationFailure(
            "Invalid authoring friction",
            details={"category": category, "error": str(error)},
        ) from error
    _append(authoring_log_path(workspace), event)
    return event


def finish_authoring_session(
    workspace: Path,
    session_id: str,
    *,
    outcome: str,
    first_attempt_success: bool | None,
    correction_rounds: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    docs_used: list[str] | None = None,
    notes: str = "",
) -> AuthoringFinished:
    start, events = _session_events(workspace, session_id)
    if any(isinstance(event, AuthoringFinished) for event in events):
        raise ValidationFailure(f"Authoring session is already finished: {session_id}")
    if first_attempt_success is True and correction_rounds != 0:
        raise ValidationFailure(
            "A first-attempt success cannot have correction rounds",
            details={"correction_rounds": correction_rounds},
        )
    measured_tokens = input_tokens is not None or output_tokens is not None
    finished_at = _now()
    try:
        event = AuthoringFinished(
            session_id=session_id,
            timestamp=finished_at,
            outcome=outcome,
            first_attempt_success=first_attempt_success,
            correction_rounds=correction_rounds,
            elapsed_seconds=max(0.0, (finished_at - start.timestamp).total_seconds()),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            token_source="reported" if measured_tokens else "unknown",
            docs_used=sorted({value.strip() for value in docs_used or [] if value.strip()}),
            notes=notes.strip(),
        )
    except Exception as error:
        raise ValidationFailure(
            "Invalid authoring result",
            details={"outcome": outcome, "error": str(error)},
        ) from error
    _append(authoring_log_path(workspace), event)
    return event


def authoring_log_report(
    workspace: Path, *, session_id: str | None = None
) -> dict[str, Any]:
    path = authoring_log_path(workspace)
    events, diagnostics = read_authoring_events(workspace)
    sessions: dict[str, dict[str, Any]] = {}
    for event in events:
        if session_id is not None and event.session_id != session_id:
            continue
        record = sessions.setdefault(
            event.session_id,
            {"session_id": event.session_id, "frictions": [], "status": "orphaned"},
        )
        if isinstance(event, AuthoringStarted):
            record.update(
                {
                    "status": "running",
                    "task": event.task,
                    "dashboard_id": event.dashboard_id,
                    "model": event.model,
                    "tool": event.tool,
                    "started_at": event.timestamp.isoformat(),
                    "start_notes": event.notes,
                    "dataviz_version": event.dataviz_version,
                }
            )
        elif isinstance(event, AuthoringFriction):
            record["frictions"].append(
                {
                    "category": event.category,
                    "reference": event.reference,
                    "message": event.message,
                    "timestamp": event.timestamp.isoformat(),
                }
            )
        elif isinstance(event, AuthoringFinished):
            record.update(
                {
                    "status": "finished",
                    "outcome": event.outcome,
                    "first_attempt_success": event.first_attempt_success,
                    "correction_rounds": event.correction_rounds,
                    "elapsed_seconds": event.elapsed_seconds,
                    "input_tokens": event.input_tokens,
                    "output_tokens": event.output_tokens,
                    "token_source": event.token_source,
                    "docs_used": event.docs_used,
                    "finish_notes": event.notes,
                    "finished_at": event.timestamp.isoformat(),
                }
            )

    ordered = sorted(sessions.values(), key=lambda value: value.get("started_at", ""))
    finished = [value for value in ordered if value["status"] == "finished"]
    measured_first = [
        value for value in finished if value.get("first_attempt_success") is not None
    ]
    token_measured = [
        value
        for value in finished
        if value.get("input_tokens") is not None or value.get("output_tokens") is not None
    ]
    correction_values = [value["correction_rounds"] for value in finished]
    elapsed_values = [value["elapsed_seconds"] for value in finished]
    friction_counts: dict[str, int] = {}
    for value in ordered:
        for friction in value["frictions"]:
            friction_counts[friction["category"]] = (
                friction_counts.get(friction["category"], 0) + 1
            )
    return {
        "schema": AUTHORING_LOG_REPORT_SCHEMA,
        "log_file": str(path),
        "sessions": ordered,
        "metrics": {
            "sessions": len(ordered),
            "finished": len(finished),
            "successful": sum(value.get("outcome") == "success" for value in finished),
            "first_attempt_measured": len(measured_first),
            "first_attempt_success_rate": (
                round(
                    100
                    * sum(value["first_attempt_success"] is True for value in measured_first)
                    / len(measured_first),
                    1,
                )
                if measured_first
                else None
            ),
            "mean_correction_rounds": (
                round(mean(correction_values), 2) if correction_values else None
            ),
            "mean_elapsed_seconds": (
                round(mean(elapsed_values), 2) if elapsed_values else None
            ),
            "token_measured_sessions": len(token_measured),
            "reported_input_tokens": sum(
                value.get("input_tokens") or 0 for value in token_measured
            ),
            "reported_output_tokens": sum(
                value.get("output_tokens") or 0 for value in token_measured
            ),
            "friction_by_category": friction_counts,
        },
        "diagnostics": diagnostics,
        "measurement_note": (
            "Token values are only stored when reported by the authoring client; "
            "Dataviz never estimates them from bytes."
        ),
    }


def authoring_prompt(dashboard_id: str | None = None) -> dict[str, Any]:
    dashboard = f" --dashboard {dashboard_id}" if dashboard_id else ""
    return {
        "schema": AUTHORING_EVENT_SCHEMA,
        "log": AUTHORING_LOG_NAME,
        "start": f'dataviz authoring start <workspace>{dashboard} --task "<task>"',
        "friction": (
            "dataviz authoring note <workspace> <session-id> "
            '--category documentation --message "<unclear point>"'
        ),
        "finish": (
            "dataviz authoring finish <workspace> <session-id> --outcome success "
            "--first-attempt success --correction-rounds 0"
        ),
        "rule": "Report real measurements only; leave unavailable token counts unknown.",
    }
