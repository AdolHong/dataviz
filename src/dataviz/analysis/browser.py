from __future__ import annotations

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from functools import partial
import base64
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
from typing import Any
from urllib.parse import urlparse

from dataviz.errors import ExecutionFailure
from dataviz.execution import InteractionExecutor
from dataviz.rendering import CanvasRenderer
from dataviz.state_snapshot import (
    applied_control_state_for_consumers,
    applied_revisions_for_consumers,
    merge_applied_control_state,
    merge_applied_revisions,
    merge_applied_writer_provenance,
    normalize_consumer_revisions,
)
from dataviz.value_contract import json_value_signature
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace
from dataviz.workspace.models import (
    CanvasDefinition,
    DeclarativeViewDefinition,
    InteractiveExportDefinition,
    LayoutDefinition,
    SectionDefinition,
)


def _analysis_dashboard(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
    *,
    target_references: tuple[str, ...],
    transform_ids: tuple[str, ...],
) -> LoadedDashboard:
    used_view_ids = set(dashboard.views)
    view_id = "analysis-output"
    suffix = 1
    while view_id in used_view_ids:
        suffix += 1
        view_id = f"analysis-output-{suffix}"
    used_section_ids = {section.id for section in dashboard.definition.sections}
    section_id = "analysis-result"
    suffix = 1
    while section_id in used_section_ids:
        suffix += 1
        section_id = f"analysis-result-{suffix}"

    # Keep scoped Control owners so canonical Control keys remain unchanged, but
    # remove their data inputs. Only the synthetic target View becomes a
    # Presentation root, keeping the temporary report and Query closure minimal.
    control_views = [
        view.model_copy(update={"input": None, "inputs": {}})
        for view in dashboard.definition.views
        if view.controls
    ]
    control_sections = [
        section.model_copy(update={"views": [], "repeat": None})
        for section in dashboard.definition.sections
        if section.controls
    ]
    target_views: list[DeclarativeViewDefinition] = []
    for index, target_reference in enumerate(target_references):
        target_view_id = view_id if index == 0 else f"{view_id}-{index + 1}"
        while target_view_id in used_view_ids:
            target_view_id += "-output"
        used_view_ids.add(target_view_id)
        target_views.append(
            DeclarativeViewDefinition(
                id=target_view_id,
                title=f"Analysis Output {index + 1}",
                template="table",
                input=target_reference,
            )
        )
    target_section = SectionDefinition(
        id=section_id,
        title="Analysis Result",
        views=[view.id for view in target_views],
    )
    definition = dashboard.definition.model_copy(
        update={
            "title": "Analysis Runtime",
            "subtitle": "",
            "description": "",
            "views": [*control_views, *target_views],
            "sections": [*control_sections, target_section],
            "layout": LayoutDefinition(),
            "canvas": CanvasDefinition(),
        }
    )

    transforms = dict(dashboard.interactive_transforms)
    for transform_id in transform_ids:
        path, transform = transforms[transform_id]
        if transform.runtime == "server-python":
            continue
        transforms[transform_id] = (
            path,
            transform.model_copy(
                update={
                    "export": InteractiveExportDefinition(mode="interactive")
                }
            ),
        )

    return replace(
        dashboard,
        definition=definition,
        logic_definition=definition,
        interactive_transforms=transforms,
        views={view.id: view for view in [*control_views, *target_views]},
        presentation_path=None,
        presentation=None,
        presentation_diagnostics=[],
    )


def _browser_dependency_error() -> ExecutionFailure:
    return ExecutionFailure(
        "Browser Analysis requires Playwright and Chromium",
        details={
            "code": "analysis_browser_dependency_missing",
            "install": [
                'pip install "ai-dataviz[visual-check]"',
                "python -m playwright install chromium",
            ],
        },
    )


@contextmanager
def _local_report_server(directory: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(QuietHandler, directory=str(directory)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


def _run_browser_outputs_sync(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
    run_result,
    *,
    targets: list[tuple[str, str]],
    control_state: dict[str, dict[str, Any]],
    refresh: bool,
    allow_network: bool,
    timeout_seconds: float,
    cache_salt: str | None = None,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise _browser_dependency_error() from error

    if not targets:
        raise ValueError("Browser Analysis requires at least one target")
    original_contract = dashboard.dependency_contract
    transform_ids = tuple(
        dict.fromkeys(
            identifier
            for transform_id, _output_name in targets
            for identifier in original_contract.interactive_closure(transform_id)
        )
    )
    derived_outputs = {}
    snapshot_interactions: set[str] = set()
    server_interaction_ids: list[str] = []
    interaction_executor = InteractionExecutor(workspace, cache_salt=cache_salt)
    for identifier in transform_ids:
        transform = dashboard.interactive_transforms[identifier][1]
        if transform.runtime != "server-python":
            continue
        interaction = interaction_executor.execute(
            run_result,
            identifier,
            control_state=control_state,
            refresh=refresh,
            _dashboard=dashboard,
        )
        if interaction.status != "ready":
            node = interaction.nodes.get(f"interactive:{identifier}")
            raise ExecutionFailure(
                f"Server Interactive dependency {identifier} is unavailable",
                details={
                    "code": "analysis_server_dependency_unavailable",
                    "transform": identifier,
                    "status": interaction.status,
                    "error": node.error if node else None,
                },
            )
        derived_outputs.update(interaction.outputs)
        snapshot_interactions.add(identifier)
        server_interaction_ids.append(identifier)

    target_references = tuple(
        f"interactive:{transform_id}/{output_name}"
        for transform_id, output_name in targets
    )
    analysis_dashboard = _analysis_dashboard(
        workspace,
        dashboard,
        target_references=target_references,
        transform_ids=transform_ids,
    )
    started = time.perf_counter()
    with TemporaryDirectory(prefix="dataviz-analysis-browser-") as directory:
        report = CanvasRenderer(workspace).write_report(
            analysis_dashboard,
            run_result,
            Path(directory) / "analysis.html",
            control_state=control_state,
            derived_outputs=derived_outputs,
            snapshot_interactions=snapshot_interactions,
        )
        report_ms = round((time.perf_counter() - started) * 1000, 2)
        browser_started = time.perf_counter()
        with _local_report_server(Path(directory)) as report_origin, sync_playwright() as playwright:
            launch_started = time.perf_counter()
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as error:
                raise _browser_dependency_error() from error
            launch_ms = round((time.perf_counter() - launch_started) * 1000, 2)
            context = browser.new_context()
            if not allow_network:
                def route_request(route):
                    parsed = urlparse(route.request.url)
                    if parsed.scheme in {"http", "https"} and parsed.hostname not in {
                        "127.0.0.1",
                        "localhost",
                    }:
                        route.abort()
                    else:
                        route.continue_()

                context.route(
                    "**/*",
                    route_request,
                )
            page = context.new_page()
            console_errors: list[str] = []
            page_errors: list[str] = []
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page_started = time.perf_counter()
            page.goto(f"{report_origin}/{report.name}", wait_until="load")
            timeout_ms = max(1, int(timeout_seconds * 1000))
            page.wait_for_function(
                "window.datavizRuntime && window.datavizRuntime.initializationPromise",
                timeout=timeout_ms,
            )
            page_ready_ms = round((time.perf_counter() - page_started) * 1000, 2)
            runtime_timing = page.evaluate(
                """async ({targets}) => {
                  const readyStarted = performance.now();
                  await window.datavizRuntime.initializationPromise;
                  const runtimeReadyMs = performance.now() - readyStarted;
                  const transformStarted = performance.now();
                  await window.datavizRuntime.runTransforms([], [], {
                    changedComputeKeys:null,
                    targets,
                    apply:true,
                    manualTargets:targets,
                  });
                  return {
                    runtimeReadyMs,
                    transformMs:performance.now() - transformStarted,
                  };
                }""",
                {"targets": list(dict.fromkeys(item[0] for item in targets))},
            )
            extraction_started = time.perf_counter()
            extracted = page.evaluate(
                """({targets}) => targets.map(({reference, transformId, outputName}) => {
                  const runtime = window.datavizRuntime;
                  const error = runtime.outputErrors.get(reference)
                    || runtime.transformErrors.get(transformId);
                  if (error) return {reference, error:{
                    code:error.code || error.details?.code || 'interactive_transform_error',
                    message:error.message || String(error),
                    stack:error.stack || null,
                  }};
                  if (!Object.prototype.hasOwnProperty.call(window.dataviz.portable.outputs, reference)) {
                    return {reference, error:{code:'analysis_browser_output_missing', message:`Missing ${reference}`}};
                  }
                  const declared = runtime.transforms.get(transformId)?.spec?.outputs?.[outputName] || {};
                  const kind = window.dataviz.portable.output_kinds?.[reference]
                    || declared.kind
                    || 'object';
                  const raw = window.dataviz.portable.outputs[reference];
                  let value = kind === 'table'
                    ? window.datavizRuntimeServices.tableRows(raw)
                    : raw;
                  let transport = 'json';
                  let arrowIpc = null;
                  if (kind === 'table' && raw?.__datavizArrowOutput && raw.bytes) {
                    const bytes = new Uint8Array(raw.bytes);
                    const chunks = [];
                    const size = 0x8000;
                    for (let index = 0; index < bytes.length; index += size) {
                      chunks.push(String.fromCharCode(...bytes.subarray(index, index + size)));
                    }
                    arrowIpc = btoa(chunks.join(''));
                    value = null;
                    transport = 'arrow-ipc';
                  }
                  return {
                    reference,
                    kind,
                    value,
                    transport,
                    arrowIpc,
                    schema:window.dataviz.portable.output_schemas?.[reference]
                      || declared.schema
                      || [],
                    metrics:runtime.metrics,
                  };
                })""",
                {
                    "targets": [
                        {
                            "reference": reference,
                            "transformId": transform_id,
                            "outputName": output_name,
                        }
                        for (transform_id, output_name), reference in zip(
                            targets, target_references, strict=True
                        )
                    ]
                },
            )
            state_snapshot = page.evaluate("datavizBuildStateSnapshot()")
            extraction_ms = round((time.perf_counter() - extraction_started) * 1000, 2)
            context.close()
            browser.close()
        browser_ms = round((time.perf_counter() - browser_started) * 1000, 2)

    failed = next((item for item in extracted if item.get("error")), None)
    if failed is not None:
        error = failed["error"]
        raise ExecutionFailure(
            f"Browser Analysis failed: {error.get('message', 'unknown error')}",
            details={
                "code": error.get("code"),
                "runtime_error": error,
                "console_errors": console_errors,
                "page_errors": page_errors,
            },
        )

    outputs = []
    for item in extracted:
        transport = item.get("transport", "json")
        if transport == "arrow-ipc":
            import pyarrow as pa

            arrow_bytes = base64.b64decode(item["arrowIpc"])
            value = pa.ipc.open_stream(arrow_bytes).read_all().to_pylist()
        else:
            value = item["value"]
        content_hash = hashlib.sha256(
            json_value_signature(value).encode("utf-8")
        ).hexdigest()
        outputs.append(
            {
                "reference": item["reference"],
                "kind": item["kind"],
                "schema": item.get("schema", []),
                "value": value,
                "rows": len(value) if item["kind"] == "table" else None,
                "content_hash": content_hash,
                "transport": transport,
            }
        )
    applied_revisions = merge_applied_revisions(
        state_snapshot.get("applied_revisions", {}),
        applied_revisions_for_consumers(
            dashboard,
            control_state,
            transform_ids=set(server_interaction_ids),
        ),
    )
    applied_control_state = merge_applied_control_state(
        state_snapshot.get("applied_control_state", {}),
        applied_control_state_for_consumers(
            dashboard,
            control_state,
            transform_ids=set(server_interaction_ids),
        ),
    )
    applied_writer_provenance = merge_applied_writer_provenance(
        state_snapshot.get("applied_writer_provenance", {})
    )
    return {
        "outputs": outputs,
        "duration_ms": round(report_ms + browser_ms, 2),
        "timing": {
            "report_ms": report_ms,
            "browser_ms": browser_ms,
            "browser_launch_ms": launch_ms,
            "page_ready_ms": page_ready_ms,
            "runtime_ready_ms": round(runtime_timing["runtimeReadyMs"], 2),
            "transform_ms": round(runtime_timing["transformMs"], 2),
            "extraction_ms": extraction_ms,
        },
        "metrics": extracted[-1].get("metrics", {}) if extracted else {},
        "console_errors": console_errors,
        "server_interactions": server_interaction_ids,
        "applied_revisions": applied_revisions,
        "applied_control_state": applied_control_state,
        "applied_writer_provenance": applied_writer_provenance,
        "consumer_revisions": normalize_consumer_revisions(
            dashboard,
            control_state,
            applied_revisions,
            applied_control_state,
            applied_writer_provenance,
        ),
    }


def run_browser_outputs(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
    run_result,
    *,
    targets: list[tuple[str, str]],
    control_state: dict[str, dict[str, Any]],
    refresh: bool,
    allow_network: bool,
    timeout_seconds: float,
    cache_salt: str | None = None,
) -> dict[str, Any]:
    """Run the synchronous Playwright session outside any caller event loop.

    ``run_analysis`` is deliberately a synchronous application boundary, but it
    can be reused by async hosts and by processes that already own a Playwright
    loop. Playwright's Sync API rejects those callers when entered on the same
    thread, so the browser session has one explicit thread boundary here.
    """

    with ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="dataviz-browser-analysis",
    ) as executor:
        future = executor.submit(
            _run_browser_outputs_sync,
            workspace,
            dashboard,
            run_result,
            targets=targets,
            control_state=control_state,
            refresh=refresh,
            allow_network=allow_network,
            timeout_seconds=timeout_seconds,
            cache_salt=cache_salt,
        )
        return future.result()
