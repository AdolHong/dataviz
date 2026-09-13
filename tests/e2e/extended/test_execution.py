from __future__ import annotations


import re


from pathlib import Path


import pytest


from playwright.sync_api import (
    Page,
    expect,
)


from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _build_interactive_runtime_workspace,
    _open_dashboard,
    _run_and_wait,
    PROGRESSIVE,
    WORKER,
)

@pytest.mark.e2e
def test_browser_transform_session_cache_reuses_equivalent_control_state(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(WORKER, tmp_path / "worker-session-cache")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "worker-runtime")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        table = frame.locator('[data-view-id="scaled-table"]')
        expect(table).to_have_attribute("data-view-status", "ready", timeout=15_000)
        delay = page.locator('input[name="dashboard:worker-runtime/delay_ms"]')

        delay.evaluate(
            "input => { input.value = '6'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow.dataviz
              .control.value('dashboard:worker-runtime/delay_ms') === 6""",
            timeout=10_000,
        )
        delay.evaluate(
            "input => { input.value = '5'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_function(
            """() => {
              const runtime = document.querySelector('#canvas-frame').contentWindow.datavizRuntime;
              return runtime.interactiveTraces.get('scaled')?.cache?.status === 'hit';
            }""",
            timeout=10_000,
        )
        cache = frame.locator("body").evaluate(
            """() => ({
              metrics:window.datavizRuntime.metrics.interactiveTransforms,
              evidence:window.datavizRuntime.interactiveTraces.get('scaled').cache,
              entries:window.datavizRuntime.interactionCache.size,
              limit:window.datavizRuntime.interactionCacheLimit,
            })"""
        )
        assert cache["metrics"]["cacheHits"] >= 1
        assert cache["metrics"]["cacheMisses"] >= 1
        assert cache["evidence"]["status"] == "hit"
        assert cache["entries"] <= cache["limit"] == 64


@pytest.mark.e2e
def test_browser_js_interactive_worker_cancellation_timeout_and_serializable_error(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(WORKER, tmp_path / "worker")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "worker-runtime")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        table = frame.locator('[data-view-id="scaled-table"]')
        expect(table).to_have_attribute("data-view-status", "ready", timeout=15_000)
        expect(table).to_contain_text("20")
        metrics = frame.locator("body").evaluate(
            """() => ({
              worker: window.datavizRuntime.metrics.interactiveTransforms,
              leakedEntrypoint: typeof window.transform,
            })"""
        )
        assert metrics["worker"]["completed"] >= 1
        assert metrics["leakedEntrypoint"] == "undefined"

        delay = page.locator('input[name="dashboard:worker-runtime/delay_ms"]')
        completed_before_drift = frame.locator("body").evaluate(
            """() => {
              const runtime = window.datavizRuntime;
              // Registration payloads are drift assertions, not a second
              // dependency source. Runtime scheduling and declarative View
              // reads must continue to use the compiled contract.
              runtime.transforms.get('scaled').spec.inputs.rows = 'source:invalid/main';
              window.dataviz.view_specs.find(view => view.id === 'scaled-table').input = 'source:invalid/main';
              return runtime.metrics.interactiveTransforms.completed;
            }"""
        )
        delay.evaluate(
            "input => { input.value = '6'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_function(
            """completed => {
              const frame = document.querySelector('#canvas-frame').contentWindow;
              const output = frame.dataviz.portable.outputs['interactive:scaled/main'];
              return frame.datavizRuntime.metrics.interactiveTransforms.completed > completed
                && Array.isArray(output) && output.some(row => Number(row.value) === 20);
            }""",
            arg=completed_before_drift,
            timeout=10_000,
        )
        expect(table).to_have_attribute("data-view-status", "ready")
        expect(table).to_contain_text("20")

        delay.evaluate(
            "input => { input.value = '750'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_function(
            """() => {
              const runtime = document.querySelector('#canvas-frame').contentWindow.datavizRuntime;
              return runtime.activeTransforms.size === 1;
            }""",
            timeout=10_000,
        )
        expect(table).to_have_attribute("data-view-status", "ready")
        expect(table).to_have_attribute("data-view-updating", "true")
        expect(table).to_contain_text("20")
        delay.evaluate(
            "input => { input.value = '1'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        page.wait_for_function(
            """() => {
              const runtime = document.querySelector('#canvas-frame').contentWindow.datavizRuntime;
              return runtime.metrics.interactiveTransforms.cancelled >= 1
                && runtime.activeTransforms.size === 0;
            }""",
            timeout=10_000,
        )
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow.dataviz
              .control.value('dashboard:worker-runtime/delay_ms') === 1""",
            timeout=10_000,
        )
        expect(table).to_have_attribute("data-view-status", "ready")
        expect(table).not_to_have_attribute("data-view-updating", "true")
        applied_before_timeout = frame.locator("body").evaluate(
            """() => window.dataviz.stateSnapshot().consumer_revisions
              .transforms.scaled"""
        )
        applied_entry = applied_before_timeout["applied_control_state"][
            "dashboard:worker-runtime/delay_ms"
        ]
        assert applied_before_timeout["stale"] is False
        assert applied_entry["value"] == 1
        assert (
            applied_entry["revision"]
            == applied_before_timeout["controls"]["dashboard:worker-runtime/delay_ms"][
                "applied_revision"
            ]
        )

        delay.evaluate(
            "input => { input.value = '1500'; input.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
        expect(table).to_have_attribute("data-view-status", "error", timeout=10_000)
        error = frame.locator("body").evaluate(
            """() => {
              const value = window.datavizRuntime.transformErrors.get('scaled');
              return {code:value.code, name:value.name, message:value.message, worker:value.worker};
            }"""
        )
        assert error["code"] == "interactive_transform_timeout"
        assert error["name"] == "TimeoutError"
        assert error["worker"] is True
        failed_evidence = frame.locator("body").evaluate(
            """() => window.dataviz.stateSnapshot().consumer_revisions
              .transforms.scaled"""
        )
        assert failed_evidence["stale"] is True
        assert (
            failed_evidence["applied_control_state"]["dashboard:worker-runtime/delay_ms"]
            == applied_entry
        )
        assert (
            failed_evidence["controls"]["dashboard:worker-runtime/delay_ms"]["effective_revision"]
            > applied_entry["revision"]
        )


@pytest.mark.e2e
def test_server_python_and_browser_js_share_output_contract_and_block_html_export(
    page: Page, tmp_path: Path
):
    workspace = _build_interactive_runtime_workspace(tmp_path / "runtime-matrix")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "runtime-matrix")
        page.locator("#run-button").click()
        page.wait_for_function(
            """() => {
              const frame = document.querySelector('#canvas-frame');
              return frame?.dataset.runId
                && frame.contentWindow?.datavizRuntime
                && frame.contentWindow.dataviz.interaction
                && document.querySelector('#query-diagnostics-label')?.textContent === 'Loading';
            }""",
            timeout=20_000,
        )
        progressive_frame_id = page.locator("#canvas-frame").get_attribute("data-frame-id")
        frame = page.frame_locator("#canvas-frame")
        server_table = frame.locator('[data-view-id="server-table"]')
        browser_table = frame.locator('[data-view-id="browser-table"]')
        expect(server_table).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(browser_table).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(server_table).to_contain_text("104")
        expect(browser_table).to_contain_text("4")
        assert frame.locator("body").evaluate(
            """() => ({
              started:window.datavizRuntime.metrics.interactiveTransforms.started,
              completed:window.datavizRuntime.metrics.interactiveTransforms.completed,
              cancelled:window.datavizRuntime.metrics.interactiveTransforms.cancelled,
            })"""
        ) == {"started": 1, "completed": 1, "cancelled": 0}
        # The Server and Browser Interactive branches must publish before the
        # unrelated slow Query branch completes.
        expect(page.locator("#query-diagnostics-label")).to_have_text("Loading")
        (workspace / "dashboards" / "runtime-matrix" / "release-slow").write_text(
            "release\n", encoding="utf-8"
        )
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready", timeout=30_000)
        assert page.locator("#canvas-frame").get_attribute("data-frame-id") == progressive_frame_id
        original_run = page.locator("#canvas-frame").get_attribute("data-run-id")

        completed_before_selection = frame.locator("body").evaluate(
            "() => window.datavizRuntime.metrics.interactiveTransforms.completed"
        )
        frame.locator("body").evaluate(
            """async () => {
              window.dataviz.control.set(
                'dashboard:runtime-matrix/name', ['alpha'], {intent:'explicit'},
              );
              await window.dataviz.applyControls();
            }"""
        )
        expect(server_table).to_contain_text("alpha")
        expect(server_table).not_to_contain_text("beta")
        assert (
            frame.locator("body").evaluate(
                "() => window.datavizRuntime.metrics.interactiveTransforms.completed"
            )
            == completed_before_selection
        )

        page.locator("#dashboard-controls-toggle").click()
        factor = page.locator(
            '#dashboard-control-form input[name="dashboard:runtime-matrix/factor"]'
        )
        factor.fill("3")
        factor.dispatch_event("change")
        expect(server_table).to_contain_text("103", timeout=20_000)
        expect(browser_table).to_contain_text("3", timeout=20_000)
        assert page.locator("#canvas-frame").get_attribute("data-run-id") == original_run
        runtime_state = frame.locator("body").evaluate(
            """() => ({
              committed:window.dataviz.control.value('dashboard:runtime-matrix/factor'),
              browserWorkers:window.datavizRuntime.metrics.interactiveTransforms.completed,
              active:window.datavizRuntime.activeTransforms.size,
            })"""
        )
        assert runtime_state == {"committed": 3, "browserWorkers": 2, "active": 0}

        export = page.locator("#download-button")
        expect(export).to_be_disabled()
        expect(export).to_have_attribute("title", re.compile("Server Python"))

        page.locator("#share-button").click()
        with page.expect_response(
            lambda response: response.url.endswith("/api/dashboards/runtime-matrix/share"),
            timeout=30_000,
        ) as share_response:
            page.locator("#copy-share-link").click()
        shared = share_response.value.json()
        page.goto(f"{base_url}{shared['url']}", wait_until="domcontentloaded")
        shared_server = page.locator('[data-view-id="server-table"]')
        shared_browser = page.locator('[data-view-id="browser-table"]')
        expect(shared_server).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(shared_browser).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(shared_server).to_contain_text("103")
        expect(shared_browser).to_contain_text("3")


@pytest.mark.e2e
def test_progressive_failure_and_consecutive_run_are_isolated(page: Page, tmp_path: Path):
    workspace = _copy_workspace(PROGRESSIVE, tmp_path / "progressive")
    slow_code = workspace / "dashboards" / "progressive" / "sources" / "slow.py"
    slow_code.write_text(
        # Leave a deterministic observation window after the fast branch is
        # visible, even on a cold browser/CI worker.
        "import time\n\ndef load(context):\n    time.sleep(4)\n    raise RuntimeError('expected branch failure')\n",
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "progressive")
        page.locator("#run-button").click()
        frame = page.frame_locator("#canvas-frame")
        fast = frame.locator('[data-view-id="fast-view"]')
        slow = frame.locator('[data-view-id="slow-view"]')
        expect(fast).to_have_attribute("data-view-status", "ready", timeout=15_000)
        expect(slow).to_have_attribute("data-view-status", "loading")
        first_run_id = page.locator("#canvas-frame").get_attribute("data-run-id")
        expect(slow).to_have_attribute("data-view-status", "error", timeout=15_000)
        expect(page.locator("#query-diagnostics-label")).to_have_text("Partial")

        slow_code.write_text(
            "def load(context):\n    return [{'branch': 'slow-second', 'value': 2}]\n",
            encoding="utf-8",
        )
        page.locator("#run-button").click()
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready", timeout=20_000)
        second_run_id = page.locator("#canvas-frame").get_attribute("data-run-id")
        assert first_run_id and second_run_id and first_run_id != second_run_id
        expect(slow).to_have_attribute("data-view-status", "ready", timeout=15_000)
        expect(slow).to_contain_text(re.compile("slow-second"))

