from __future__ import annotations

import multiprocessing
import hashlib
import os
import re
import shutil
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from dataviz.errors import (
    ExecutionFailure,
    QueryConnectionFailure,
    QueryExecutionFailure,
    QueryTimeoutFailure,
    SourceFailure,
)
from dataviz.execution.parameters import query_input_contract
from dataviz.sources.base import SourceRequest
from dataviz.sql_contract import resolve_sql_preview
from dataviz.redaction import adapter_secret_values, redact_text, redact_value


_QUERY_TIMEOUT_CODES = {3024}  # MySQL ER_QUERY_TIMEOUT
_QUERY_TIMEOUT_CODE_STRINGS = {str(code) for code in _QUERY_TIMEOUT_CODES}
_QUERY_TIMEOUT_MARKERS = (
    "query timeout",
    "query timed out",
    "query exceeded timeout",
    "query exceeded time limit",
    "query execution timeout",
    "maximum statement execution time exceeded",
    "statement timeout",
    "deadline exceeded",
    "timeout exceeded",
    "timed out",
    "cancelled due to timeout",
    "canceled due to timeout",
)
_QUERY_FILTER_TOKEN = re.compile(
    r"\{\{\s*dataviz_filter:([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}"
)


def resolve_query_filter_tokens(
    query: str,
    declarations: dict[str, Any],
    states: dict[str, dict[str, Any]],
    *,
    adapter_type: str,
) -> tuple[str, dict[str, Any]]:
    """Resolve the only supported SQL template token into parameterized predicates."""

    tokens = _QUERY_FILTER_TOKEN.findall(query)
    unknown = sorted(set(tokens) - set(declarations))
    if unknown:
        raise ExecutionFailure(
            "SQL uses undeclared Dataviz query filters: " + ", ".join(unknown),
            details={"code": "query_filter_undeclared", "filters": unknown},
        )
    unused = sorted(set(declarations) - set(tokens))
    if unused:
        raise ExecutionFailure(
            "SQL declares unused Dataviz query filters: " + ", ".join(unused),
            details={"code": "query_filter_unused", "filters": unused},
        )
    parameters: dict[str, Any] = {}

    def replacement(match: re.Match[str]) -> str:
        name = match.group(1)
        declaration = declarations[name]
        state = states.get(declaration.parameter)
        if state is None:
            raise ExecutionFailure(
                f"Query filter {name} requires a multiple Query Parameter state",
                details={
                    "code": "query_filter_state_invalid",
                    "filter": name,
                    "parameter": declaration.parameter,
                },
            )
        selection = state.get("selection")
        if selection is None:
            values = state.get("value")
            if not isinstance(values, (list, tuple)):
                raise ExecutionFailure(
                    f"Query filter {name} requires a multiple_input value list",
                    details={
                        "code": "query_filter_state_invalid",
                        "filter": name,
                        "parameter": declaration.parameter,
                    },
                )
            if not values:
                return "TRUE" if declaration.empty == "passthrough" else "FALSE"
            selection = "include"
        elif selection not in {"all", "include", "exclude", "none"}:
            raise ExecutionFailure(
                f"Query filter {name} has an invalid multiple_select selection",
                details={
                    "code": "query_filter_state_invalid",
                    "filter": name,
                    "parameter": declaration.parameter,
                },
            )
        if selection == "all":
            return "TRUE"
        if selection == "none":
            return "TRUE" if declaration.empty == "passthrough" else "FALSE"
        values = list(state.get("value") or ())
        if not values:
            raise ExecutionFailure(
                f"Query filter {name} has no explicit operands",
                details={"code": "query_filter_operands_missing", "filter": name},
            )
        parameter = f"__dv_filter_{name}"
        parameters[parameter] = values
        if adapter_type == "duckdb":
            predicate = f"{declaration.field} = ANY(:{parameter})"
        else:
            predicate = f"{declaration.field} IN :{parameter}"
        return f"NOT ({predicate})" if selection == "exclude" else predicate

    return _QUERY_FILTER_TOKEN.sub(replacement, query), parameters


def _relative_debug_path(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return str(path)


def _terminate_process(process: multiprocessing.Process) -> None:
    """Stop a query process, escalating when a driver ignores termination."""
    if not process.is_alive():
        process.join(timeout=0.1)
        return
    process.terminate()
    process.join(timeout=1)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=1)


def _is_query_timeout_error(error: BaseException) -> bool:
    """Recognize server/driver timeout errors without retrying other SQL failures."""
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        for value in getattr(current, "args", ()):
            normalized = str(value).strip().lower()
            if (
                isinstance(value, int) and value in _QUERY_TIMEOUT_CODES
            ) or (
                normalized in _QUERY_TIMEOUT_CODE_STRINGS
                or normalized == "timeout"
            ):
                return True
        message = str(current).lower()
        if any(marker in message for marker in _QUERY_TIMEOUT_MARKERS):
            return True
        for related in (
            getattr(current, "orig", None),
            current.__cause__,
            current.__context__,
        ):
            if isinstance(related, BaseException):
                pending.append(related)
    return False


def _configure_statement_timeout(connection: Any, adapter_type: str, timeout: float | None) -> None:
    """Ask supported servers to enforce the same deadline as the parent process."""
    if timeout is None:
        return
    if adapter_type == "mysql":
        milliseconds = max(1, int(timeout * 1000))
        connection.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {milliseconds}")
    elif adapter_type == "starrocks":
        seconds = max(1, int(timeout + 0.999999))
        connection.exec_driver_sql(f"SET query_timeout = {seconds}")


def _run_sql_query(
    connection,
    *,
    adapter: dict[str, Any],
    query: str,
    parameters: dict[str, Any],
    expanding_parameters: list[str],
    timeout_seconds: float | None,
    result_path: str,
) -> None:
    """Spawn child entrypoint; only a small status payload crosses the pipe."""
    database_connection = None
    engine = None
    phase = "connect"
    try:
        adapter_type = str(adapter["type"])
        if adapter_type == "duckdb":
            import duckdb

            database = str(adapter.get("database") or ":memory:")
            options = dict(adapter.get("options") or {})
            database_connection = duckdb.connect(
                database,
                read_only=bool(options.get("read_only", False)),
            )
            phase = "query"
            duck_query = re.sub(r":([A-Za-z_]\w*)", r"$\1", query)
            frame = database_connection.execute(duck_query, parameters).fetchdf()
        else:
            from sqlalchemy import bindparam, create_engine, text

            url = adapter.get("url")
            if not url:
                raise ValueError("SQL Adapter has no resolved URL")
            engine_options: dict[str, Any] = {}
            if adapter_type == "sqlalchemy" and adapter.get("options"):
                engine_options["connect_args"] = dict(adapter["options"])
            engine = create_engine(str(url), **engine_options)
            database_connection = engine.connect()
            _configure_statement_timeout(database_connection, adapter_type, timeout_seconds)
            phase = "query"
            statement = text(query)
            if expanding_parameters:
                statement = statement.bindparams(
                    *(bindparam(name, expanding=True) for name in expanding_parameters)
                )
            frame = pd.read_sql_query(statement, database_connection, params=parameters)

        Path(result_path).parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(result_path, index=False)
        connection.send({"ok": True})
    except BaseException as exc:  # process boundary must serialize every driver failure
        error_code = "query_connection_error"
        if phase == "query":
            error_code = (
                "query_timeout"
                if _is_query_timeout_error(exc)
                else "query_execution_error"
            )
        connection.send(
            {
                "ok": False,
                "error": {
                    "code": error_code,
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            }
        )
    finally:
        if database_connection is not None:
            try:
                database_connection.close()
            except Exception:
                pass
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass
        connection.close()


def execute_sql_query(
    *,
    adapter: dict[str, Any],
    query: str,
    parameters: dict[str, Any],
    expanding_parameters: list[str] | None = None,
    timeout_seconds: float | None,
    workspace_root: Path,
    run_id: str,
    node_id: str,
    definition_path: Path,
    cancel_event: Any | None = None,
) -> pd.DataFrame:
    """Execute SQL in a disposable process so timeout means actual cancellation."""
    safe_node_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", node_id)
    temporary_root = workspace_root / ".dataviz" / "runs" / run_id / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    file_descriptor, raw_path = tempfile.mkstemp(
        prefix=f"{safe_node_id}-",
        suffix=".parquet",
        dir=temporary_root,
    )
    os.close(file_descriptor)
    result_path = Path(raw_path)
    result_path.unlink(missing_ok=True)

    process_context = multiprocessing.get_context("spawn")
    parent, child = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_run_sql_query,
        kwargs={
            "connection": child,
            "adapter": adapter,
            "query": query,
            "parameters": parameters,
            "expanding_parameters": list(expanding_parameters or ()),
            "timeout_seconds": timeout_seconds,
            "result_path": str(result_path),
        },
        name=f"dataviz-{safe_node_id}",
    )
    process_started = False
    payload: dict[str, Any] | None = None
    try:
        try:
            process.start()
            process_started = True
        except Exception as exc:
            raise QueryExecutionFailure(
                "SQL query process could not start",
                file=definition_path,
                details={"node_id": node_id, "remote_type": type(exc).__name__},
            ) from exc
        finally:
            child.close()

        deadline = time.monotonic() + timeout_seconds if timeout_seconds else None
        while payload is None:
            if parent.poll(0.05):
                try:
                    payload = parent.recv()
                except EOFError:
                    payload = None
                if payload is not None:
                    break
            if cancel_event is not None and cancel_event.is_set():
                _terminate_process(process)
                raise ExecutionFailure(
                    "SQL query was cancelled",
                    file=definition_path,
                    details={
                        "code": "cancelled",
                        "node_id": node_id,
                        "adapter_type": adapter.get("type"),
                    },
                )
            if deadline is not None and time.monotonic() >= deadline:
                _terminate_process(process)
                raise QueryTimeoutFailure(
                    f"SQL query exceeded {timeout_seconds:g} seconds",
                    file=definition_path,
                    details={
                        "timeout_seconds": timeout_seconds,
                        "node_id": node_id,
                        "adapter_type": adapter.get("type"),
                        "cancelled": True,
                        "timeout_origin": "client_deadline",
                    },
                )
            if not process.is_alive():
                raise QueryExecutionFailure(
                    "SQL query process exited without a result",
                    file=definition_path,
                    details={"exit_code": process.exitcode, "node_id": node_id},
                )

        process.join(timeout=1)
        if not payload["ok"]:
            remote = redact_value(
                payload["error"], adapter_secret_values(adapter)
            )
            error_type = {
                "query_connection_error": QueryConnectionFailure,
                "query_timeout": QueryTimeoutFailure,
                "query_execution_error": QueryExecutionFailure,
            }.get(remote["code"], QueryExecutionFailure)
            details = {
                "remote_type": remote["type"],
                "traceback": remote["traceback"],
                "node_id": node_id,
                "adapter_type": adapter.get("type"),
            }
            if remote["code"] == "query_timeout":
                details.update(
                    {
                        "timeout_seconds": timeout_seconds,
                        "cancelled": True,
                        "timeout_origin": "server_deadline",
                    }
                )
            raise error_type(
                (
                    f"SQL query timed out: {remote['message']}"
                    if remote["code"] == "query_timeout"
                    else f"SQL query failed: {remote['message']}"
                ),
                file=definition_path,
                details=details,
            )
        if not result_path.exists():
            raise QueryExecutionFailure(
                "SQL query completed without a result artifact",
                file=definition_path,
                details={"node_id": node_id},
            )
        return pd.read_parquet(result_path)
    finally:
        parent.close()
        if process_started:
            _terminate_process(process)
        result_path.unlink(missing_ok=True)
        if temporary_root.exists() and not any(temporary_root.iterdir()):
            shutil.rmtree(temporary_root, ignore_errors=True)


class SqlSourceRunner:
    def diagnostics(self, request: SourceRequest) -> dict[str, Any]:
        definition = request.definition
        code_path = (request.definition_path.parent / definition.code).resolve()
        query = code_path.read_text(encoding="utf-8")
        parameters = dict(request.context.query_inputs)
        adapter_reference = definition.adapter or ""
        adapter_name = request.adapter_bindings.get(
            adapter_reference, adapter_reference
        )
        adapter_type = "unknown"
        inspection_warning = None
        secrets = request.adapters.redaction_values(
            adapter_reference,
            request.adapter_bindings,
        )
        try:
            adapter = request.adapters.runtime_config(
                adapter_reference,
                request.adapter_bindings,
            )
            adapter_type = str(adapter.get("type") or "unknown")
            query, filter_parameters = resolve_query_filter_tokens(
                query,
                definition.query_filters,
                request.context.query_parameter_state,
                adapter_type=adapter_type,
            )
            parameters.update(filter_parameters)
        except Exception as error:
            inspection_warning = redact_text(error, secrets)
        statement = (
            re.sub(r":([A-Za-z_]\w*)", r"$\1", query)
            if adapter_type == "duckdb"
            else query
        )
        timeout_seconds = definition.timeout_seconds
        timeout_retries = definition.timeout_retries
        return {
            "query": {
                "kind": "sql",
                "source_file": _relative_debug_path(
                    code_path,
                    request.context.workspace_root,
                ),
                "adapter_reference": adapter_reference,
                "adapter_name": adapter_name,
                "adapter_type": adapter_type,
                "statement": statement,
                "resolved_sql": resolve_sql_preview(statement, parameters),
                "parameters": parameters,
                "input_bindings": {
                    alias: query_input_contract(binding)
                    for alias, binding in definition.query_inputs.items()
                },
                "query_filters": {
                    key: value.model_dump(mode="json")
                    for key, value in definition.query_filters.items()
                },
                "timeout_seconds": timeout_seconds,
                "timeout_retries": timeout_retries,
                "query_hash": hashlib.sha256(
                    statement.encode("utf-8")
                ).hexdigest(),
                "inspection_warning": inspection_warning,
            }
        }

    def execute(self, request: SourceRequest) -> pd.DataFrame:
        definition = request.definition
        adapter_name = definition.adapter
        code_path = (request.definition_path.parent / definition.code).resolve()
        if not code_path.exists():
            raise SourceFailure("SQL file does not exist", file=code_path)
        query = code_path.read_text(encoding="utf-8")
        parameters = dict(request.context.query_inputs)
        adapter = request.adapters.runtime_config(adapter_name, request.adapter_bindings)
        query, filter_parameters = resolve_query_filter_tokens(
            query,
            definition.query_filters,
            request.context.query_parameter_state,
            adapter_type=str(adapter.get("type") or "sqlalchemy"),
        )
        parameters.update(filter_parameters)
        timeout_seconds = definition.timeout_seconds
        timeout_retries = definition.timeout_retries
        max_attempts = timeout_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                return execute_sql_query(
                    adapter=adapter,
                    query=query,
                    parameters=parameters,
                    expanding_parameters=list(filter_parameters),
                    timeout_seconds=timeout_seconds,
                    workspace_root=request.context.workspace_root,
                    run_id=request.context.run_id,
                    node_id=request.node_id,
                    definition_path=code_path,
                    cancel_event=request.cancel_event,
                )
            except QueryTimeoutFailure as exc:
                details = dict(exc.details or {})
                details.update(
                    {
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "timeout_retries": timeout_retries,
                    }
                )
                exc.details = details
                if attempt >= max_attempts:
                    raise
                if request.on_retry:
                    request.on_retry(
                        {
                            "reason": "query_timeout",
                            "completed_attempt": attempt,
                            "next_attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "timeout_seconds": timeout_seconds,
                            "retries_remaining": max_attempts - attempt,
                        }
                    )
        raise AssertionError("SQL retry loop exited without a result")
