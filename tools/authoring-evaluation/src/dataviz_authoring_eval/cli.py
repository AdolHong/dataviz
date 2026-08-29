from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from .benchmark import build_context_benchmark
from .evaluation import (
    AUTHORING_APPROACHES,
    authoring_evaluation_protocol,
    authoring_task_catalog,
    build_authoring_evaluation_report,
    inspect_authoring_trial,
    prepare_authoring_trial,
    record_authoring_assessment,
)
from .log import (
    AUTHORING_LOG_NAME,
    add_authoring_friction,
    authoring_log_report,
    finish_authoring_session,
    start_authoring_session,
)


app = typer.Typer(
    name="dataviz-authoring-eval",
    help="Repository-only paired AI authoring evaluation.",
    no_args_is_help=True,
)


def emit(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def first_attempt(value: str) -> bool | None:
    normalized = value.casefold().strip()
    if normalized in {"success", "yes", "true"}:
        return True
    if normalized in {"failure", "failed", "no", "false"}:
        return False
    if normalized in {"unknown", "unmeasured", "none"}:
        return None
    raise typer.BadParameter("--first-attempt must be success, failure, or unknown")


@app.command("tasks")
def tasks(task: str | None = typer.Argument(None)) -> None:
    """List fixed paired-evaluation tasks."""
    emit(authoring_task_catalog(task))


@app.command("protocol")
def protocol(task: str | None = typer.Option(None, "--task")) -> None:
    """Show the reproducible paired-evaluation protocol."""
    emit(authoring_evaluation_protocol(task))


@app.command("prepare")
def prepare(
    task: str,
    destination: Path,
    approach: str = typer.Option(..., "--approach"),
    trial_id: str = typer.Option(..., "--trial-id"),
) -> None:
    """Prepare one neutral fixed-task trial directory."""
    emit(prepare_authoring_trial(task, destination, approach=approach, trial_id=trial_id))


@app.command("verify")
def verify(trial_directory: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Verify task/input hashes and acceptance evidence."""
    value = inspect_authoring_trial(trial_directory)
    emit(value)
    if not value["integrity_passed"] or not value["assessment_valid"]:
        raise typer.Exit(1)


@app.command("assess")
def assess(
    trial_directory: Path = typer.Argument(..., exists=True, file_okay=False),
    check_id: str = typer.Argument(...),
    status: str = typer.Option(..., "--status"),
    assessor: str | None = typer.Option(None, "--assessor"),
    evidence: str = typer.Option("", "--evidence"),
) -> None:
    """Record evidence for one fixed acceptance check."""
    emit(record_authoring_assessment(
        trial_directory, check_id, status=status, assessor=assessor, evidence=evidence
    ))


@app.command("start")
def start(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False),
    task: str | None = typer.Option(None, "--task"),
    dashboard: str | None = typer.Option(None, "--dashboard"),
    model: str | None = typer.Option(None, "--model"),
    client: str | None = typer.Option(None, "--client"),
    trial_directory: Path | None = typer.Option(None, "--trial-dir", exists=True, file_okay=False),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Start one append-only measured authoring session."""
    trial = inspect_authoring_trial(trial_directory) if trial_directory else None
    if trial:
        if not trial["integrity_passed"] or not trial["assessment_valid"]:
            raise typer.BadParameter("Prepared trial is invalid; run verify first")
        task = trial["task"]
    if not task:
        raise typer.BadParameter("Provide --task or --trial-dir")
    event = start_authoring_session(
        workspace,
        task=task,
        dashboard_id=dashboard,
        model=model,
        tool=client,
        benchmark_task=trial["benchmark_task"] if trial else None,
        approach=trial["approach"] if trial else None,
        trial_id=trial["trial_id"] if trial else None,
        task_contract_sha256=trial["task_contract_sha256"] if trial else None,
        task_prompt_sha256=trial["task_prompt_sha256"] if trial else None,
        fixture_sha256=trial["fixture_sha256"] if trial else None,
        notes=notes,
    )
    emit({"status": "started", "session_id": event.session_id, "log": str(workspace / AUTHORING_LOG_NAME)})


@app.command("note")
def note(
    workspace: Path,
    session_id: str,
    category: str = typer.Option(..., "--category"),
    message: str = typer.Option(..., "--message"),
    reference: str | None = typer.Option(None, "--reference"),
) -> None:
    """Append one authoring friction observation."""
    emit(add_authoring_friction(
        workspace, session_id, category=category, message=message, reference=reference
    ))


@app.command("finish")
def finish(
    workspace: Path,
    session_id: str,
    outcome: str = typer.Option("success", "--outcome"),
    first_attempt_value: str = typer.Option("unknown", "--first-attempt"),
    correction_rounds: int = typer.Option(0, "--correction-rounds", min=0),
    input_tokens: int | None = typer.Option(None, "--input-tokens", min=0),
    output_tokens: int | None = typer.Option(None, "--output-tokens", min=0),
    docs_used: list[str] | None = typer.Option(None, "--docs-used"),
    trial_directory: Path | None = typer.Option(None, "--trial-dir", exists=True, file_okay=False),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Finish a session with measured quality, retries, elapsed time, and tokens."""
    trial = inspect_authoring_trial(trial_directory) if trial_directory else None
    emit(finish_authoring_session(
        workspace,
        session_id,
        outcome=outcome,
        first_attempt_success=first_attempt(first_attempt_value),
        correction_rounds=correction_rounds,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        docs_used=docs_used,
        trial_integrity_passed=trial["integrity_passed"] if trial else None,
        acceptance_passed=trial["quality_passed"] if trial else None,
        acceptance_results=trial["checks"] if trial else None,
        benchmark_task=trial["benchmark_task"] if trial else None,
        approach=trial["approach"] if trial else None,
        trial_id=trial["trial_id"] if trial else None,
        task_contract_sha256=trial["task_contract_sha256"] if trial else None,
        task_prompt_sha256=trial["task_prompt_sha256"] if trial else None,
        fixture_sha256=trial["fixture_sha256"] if trial else None,
        notes=notes,
    ))


@app.command("show")
def show(
    workspace: Path,
    session_id: str | None = typer.Option(None, "--session"),
) -> None:
    """Show measured authoring sessions without inventing missing values."""
    emit(authoring_log_report(workspace, session_id=session_id))


@app.command("compare")
def compare(workspace: Path, task: str | None = typer.Option(None, "--task")) -> None:
    """Compare identity-matched Dataviz and standalone-HTML trial pairs."""
    sessions = authoring_log_report(workspace)["sessions"]
    payload = build_authoring_evaluation_report(sessions, task_id=task)
    payload["approaches_order"] = list(AUTHORING_APPROACHES)
    emit(payload)


@app.command("benchmark-context")
def benchmark_context(workspace: Path, dashboard: str) -> None:
    """Measure deterministic focused-context size for maintainers."""
    emit(build_context_benchmark(workspace, dashboard))
