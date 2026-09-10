"""Explicit Action HTTP client; the Server remains the single execution owner."""

from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import typer

from dataviz.actions import json_object


actions_app = typer.Typer(
    help="Explicitly invoke trusted Server Python Actions or inspect their receipts. No automatic write retry.",
    no_args_is_help=True,
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward payloads or turn a mutation into another request.
        return None


def request_action(*, server: str, dashboard: str, action: str, session_id: str,
                   request_id: str, operation: str, run_id: str | None = None,
                   payload: dict | None = None, timeout: float = 150) -> dict:
    parsed = urlsplit(server)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError("--server must be an HTTP(S) base URL without credentials, query or fragment")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("--timeout must be finite and positive")
    if not request_id or len(request_id) > 128:
        raise ValueError("--request-id must contain 1–128 characters; retain it when checking an uncertain outcome")
    if not all((dashboard, action, session_id)):
        raise ValueError("Dashboard, Action and session ID must not be empty")
    base = server.rstrip("/") + "/api/dashboards/" + quote(dashboard, safe="")
    base += "/actions/" + quote(action, safe="")
    body = None
    if operation == "invoke":
        if not run_id:
            raise ValueError("--run-id must identify the current completed applied Server Run")
        body = {"session_id": session_id, "run_id": run_id, "request_id": request_id,
                "payload": json_object(payload if payload is not None else {}, label="Action payload")}
    elif operation in {"status", "refresh"}:
        base += "/" + quote(request_id, safe="")
        if operation == "refresh":
            base += "/refresh"
            body = {"session_id": session_id}
        else:
            base += "?" + urlencode({"session_id": session_id})
    else:
        raise ValueError("Unknown Action operation")
    request = Request(base, method="GET" if body is None else "POST",
                      data=None if body is None else json.dumps(body, allow_nan=False).encode(),
                      headers={"Accept": "application/json", "Content-Type": "application/json"})
    # Use the explicitly chosen Server directly, not an ambient proxy or redirects.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(2_097_153)
            if len(raw) > 2_097_152:
                raise ValueError("Action response exceeds the client size limit")
            receipt = json.loads(raw)
            if (not isinstance(receipt, dict)
                    or receipt.get("status") not in {"running", "succeeded", "failed", "unknown"}
                    or not isinstance(receipt.get("refresh", {}), dict)):
                raise ValueError("Server did not return an Action receipt object")
            return receipt
    except HTTPError as error:
        # The HTTP code alone does not prove whether an upstream write committed.
        raise ValueError(
            f"Server returned HTTP {error.code}; request_id={request_id}. "
            "Inspect the receipt before retrying; this client did not repeat the request."
        ) from error
    except (URLError, TimeoutError, OSError, ValueError, RecursionError) as error:
        raise ValueError(
            f"Action response unavailable or invalid; request_id={request_id}. "
            "The outcome may be unknown. Inspect status; do not automatically issue a new write."
        ) from error


def _execute(**kwargs) -> None:
    try:
        receipt = request_action(**kwargs)
    except (ValueError, TypeError) as error:
        typer.echo(json.dumps({"status": "error", "message": str(error),
                               "request_id": kwargs["request_id"]}, ensure_ascii=False))
        raise typer.Exit(1) from error
    typer.echo(json.dumps(receipt, ensure_ascii=False, indent=2))
    if receipt.get("status") in {"failed", "unknown"} or receipt.get("refresh", {}).get("status") == "failed":
        # Keep the entire receipt on stdout, including saved-but-refresh-failed.
        raise typer.Exit(1)


@actions_app.command("invoke")
def invoke(
    dashboard: str, action: str,
    server: str = typer.Option(..., "--server", help="Explicit trusted Dataviz Server base URL"),
    session_id: str = typer.Option(..., "--session-id"),
    run_id: str = typer.Option(..., "--run-id", help="Current completed applied Server Run, not a Result ID"),
    request_id: str = typer.Option(..., "--request-id", help="Caller-owned idempotency ID; retain for retries"),
    payload: str | None = typer.Option(None, "--payload", help="JSON object; mutually exclusive with --payload-file"),
    payload_file: Path | None = typer.Option(None, "--payload-file", exists=True, dir_okay=False),
    timeout: float = typer.Option(150, "--timeout", help="HTTP timeout seconds; never causes an automatic retry"),
) -> None:
    """Execute Python once for this request ID; returns a receipt, not a write queue."""
    if payload is not None and payload_file is not None:
        raise typer.BadParameter("Use only one of --payload and --payload-file")
    try:
        if payload_file:
            with payload_file.open("r", encoding="utf-8") as stream:
                raw = stream.read(1_048_577)
        else:
            raw = payload
        if raw is not None and len(raw.encode("utf-8")) > 1_048_576:
            raise ValueError("Action payload exceeds 1048576 bytes")
        value = json_object(json.loads(raw) if raw is not None else {}, label="Action payload")
    except (ValueError, OSError, RecursionError) as error:
        raise typer.BadParameter(str(error)) from error
    _execute(server=server, dashboard=dashboard, action=action, session_id=session_id,
             run_id=run_id, request_id=request_id, operation="invoke", payload=value, timeout=timeout)


@actions_app.command("status")
def status(
    dashboard: str, action: str,
    server: str = typer.Option(..., "--server"),
    session_id: str = typer.Option(..., "--session-id"),
    request_id: str = typer.Option(..., "--request-id"),
    timeout: float = typer.Option(150, "--timeout"),
) -> None:
    """Read a receipt and refresh progress without running Python."""
    _execute(server=server, dashboard=dashboard, action=action, session_id=session_id,
             request_id=request_id, operation="status", timeout=timeout)


@actions_app.command("refresh")
def refresh(
    dashboard: str, action: str,
    server: str = typer.Option(..., "--server"),
    session_id: str = typer.Option(..., "--session-id"),
    request_id: str = typer.Option(..., "--request-id"),
    timeout: float = typer.Option(150, "--timeout"),
) -> None:
    """Retry only the refresh for an existing receipt; never repeat Python writes."""
    _execute(server=server, dashboard=dashboard, action=action, session_id=session_id,
             request_id=request_id, operation="refresh", timeout=timeout)
