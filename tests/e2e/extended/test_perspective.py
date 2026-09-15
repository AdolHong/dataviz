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
    _route_perspective_contract_runtime,
    _copy_workspace,
    _running_static_server,
    _open_dashboard,
    _run_and_wait,
    _export_html,
    MINIMAL,
)

@pytest.mark.e2e
def test_perspective_async_mount_has_bounded_table_fallback(page: Page, tmp_path: Path):
    """An unresolved external Renderer cannot leave a View permanently Loading."""
    workspace = _copy_workspace(MINIMAL, tmp_path / "perspective-bounded-fallback")
    page.add_init_script(
        """(() => {
          window.__datavizRendererOperationTimeoutMs = 100;
          Object.defineProperty(window, 'datavizPerspectiveReady', {
            configurable:true,
            get() { return new Promise(() => {}); },
            set(_value) {},
          });
        })();"""
    )
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        perspective = frame.locator('[data-view-id="sales-perspective"]')
        expect(perspective).to_have_count(1, timeout=20_000)
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=5_000)

        expect(perspective.locator("[data-view-status-label]")).to_have_text("table fallback")
        expect(perspective.locator("table")).to_have_count(1)
        assert (
            frame.locator("body").evaluate("window.datavizRuntime.metrics.perspective.failed") == 1
        )


@pytest.mark.e2e
def test_perspective_fills_view_uses_opaque_settings_and_releases_page_wheel(
    page: Page, tmp_path: Path
):
    _route_perspective_contract_runtime(page)
    workspace = _copy_workspace(MINIMAL, tmp_path / "minimal")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    dashboard_path.write_text(
        dashboard_path.read_text(encoding="utf-8").replace("settings: false", "settings: true"),
        encoding="utf-8",
    )
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        perspective = frame.locator('[data-view-id="sales-perspective"]')
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
        viewer = perspective.locator("perspective-viewer")
        expect(viewer).to_have_count(1, timeout=30_000)

        dimensions = viewer.evaluate(
            """viewer => ({
              body: viewer.closest('.dv-view-body').getBoundingClientRect().height,
              viewer: viewer.getBoundingClientRect().height,
            })"""
        )
        assert dimensions["body"] >= 320
        assert abs(dimensions["body"] - dimensions["viewer"]) <= 1

        settings_surface = viewer.evaluate(
            """viewer => {
              const panel = viewer.shadowRoot.querySelector('#settings_panel');
              const style = getComputedStyle(panel);
              return {
                color: style.backgroundColor,
                image: style.backgroundImage,
              };
            }"""
        )
        assert settings_surface["color"] == "rgb(255, 255, 255)"
        assert settings_surface["image"] == "none"

        plugin_choice = viewer.locator('.plugin-select-item[data-plugin="Datagrid"]')
        expect(plugin_choice).to_be_visible(timeout=10_000)
        plugin_choice.click()
        expect(viewer.locator("#plugin_selector_container")).to_have_class(re.compile(r"\bopen\b"))

        identity = viewer.evaluate("viewer => (viewer.__datavizTestIdentity = crypto.randomUUID())")
        dashboard_select = page.locator('select[name="dashboard:sales-overview/region"]')
        dashboard_select.select_option(["华东"], force=True)
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .datavizRuntime.metrics.perspective.updated >= 1"""
        )
        assert viewer.evaluate("viewer => viewer.__datavizTestIdentity") == identity

        scroll_state = viewer.evaluate(
            """viewer => {
              window.scrollTo(0, 0);
              const before = window.parent.scrollY + window.scrollY;
              viewer.dispatchEvent(new WheelEvent('wheel', {
                deltaY: 500, bubbles: true, cancelable: true, composed: true
              }));
              return {before, after:window.parent.scrollY + window.scrollY};
            }"""
        )
        assert scroll_state["after"] > scroll_state["before"]

        disposed = frame.locator("body").evaluate(
            """async () => {
              window.datavizRuntime.dispose();
              await new Promise(resolve => setTimeout(resolve, 100));
              return window.datavizRuntime.metrics.perspective.disposed;
            }"""
        )
        assert disposed >= 1


@pytest.mark.e2e
@pytest.mark.parametrize('real_runtime', [False, True], ids=['contract', 'real'])
def test_perspective_enters_empty_state_immediately_after_last_selection_is_cleared(
    page: Page,
    tmp_path: Path,
    real_runtime: bool,
):
    if not real_runtime:
        _route_perspective_contract_runtime(page)
    report_path = tmp_path / "perspective-empty-selection.html"
    workspace = _copy_workspace(MINIMAL, tmp_path / 'perspective-empty')
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        perspective = frame.locator('[data-view-id="sales-perspective"]')
        detail = frame.locator('[data-view-id="sales-detail"]')
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)

        page.locator("#dashboard-controls-toggle").click()
        options = page.locator(
            '#dashboard-control-form [data-control-component="checkbox-group"] .dv-checkbox-option'
        )
        expect(options).to_have_count(3)
        selection = page.locator('select[name="dashboard:sales-overview/region"]')
        # This regression is about empty rendering, not racing three checkbox
        # commits. Establish one committed remaining value before clearing it.
        selection.select_option(['华北'], force=True)
        page.wait_for_function("""() => {
          const value = document.querySelector('#canvas-frame').contentWindow
            .dataviz.control.state('dashboard:sales-overview/region').value;
          return value.length === 1 && value[0] === '华北';
        }""")
        expect(detail.locator('tbody tr')).to_have_count(4)
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=5_000)
        configured = perspective.locator('perspective-viewer').evaluate("""async viewer => {
          viewer.__retainedIdentity = 'selection-roundtrip';
          await viewer.restore({group_by:['day'], columns:['orders', 'revenue'], sort:[['revenue', 'desc']]});
          await viewer.flush();
          return await viewer.save();
        }""")
        assert configured['group_by'] == ['day'], configured

        selection.evaluate("""input => {
          window.datavizComponents.controls.clearOptions(input);
          window.datavizComponents.controls.markSelectionIntent(input, 'explicit');
          window.datavizComponents.controls.emitChange(input);
        }""")
        expect(detail).to_contain_text("No rows match the current selections.", timeout=2_000)
        expect(perspective).to_have_attribute("data-view-status", "empty", timeout=2_000)
        expect(perspective).to_contain_text("No rows match the current selections.", timeout=2_000)

        # Empty does not discard the user's analysis or recreate the worker.
        selection.select_option(['华东'], force=True)
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
        expect(perspective.locator("perspective-viewer")).to_have_count(1)
        retained = perspective.locator('perspective-viewer').evaluate("""async viewer => ({
          identity:viewer.__retainedIdentity, config:await viewer.save(),
        })""")
        assert retained['identity'] == 'selection-roundtrip'
        assert retained['config']['group_by'] == ['day']
        assert retained['config']['columns'] == ['orders', 'revenue']
        assert retained['config']['sort'] == [['revenue', 'desc']]
        saved = perspective.locator('perspective-viewer').evaluate("""async viewer => {
          viewer.dispatchEvent(new Event('perspective-config-update'));
          const mounted = [...window.datavizRuntime.viewAdapter.states.values()]
            .find(item => item.state.viewer === viewer);
          await mounted.state.preferencesSaving;
          return JSON.parse(sessionStorage.getItem(mounted.state.preferenceKey));
        }""")
        assert saved['group_by'] == ['day']
        assert 'table' not in saved
        _run_and_wait(page)
        expect(perspective).to_have_attribute('data-view-status', 'ready', timeout=30_000)
        restored = perspective.locator('perspective-viewer').evaluate('async viewer => await viewer.save()')
        assert restored['group_by'] == ['day']
        assert restored['columns'] == ['orders', 'revenue']
        assert restored['sort'] == [['revenue', 'desc']]

        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

    # Portable reports use the same View Package lifecycle. Clearing the last
    # selected value must therefore publish Empty immediately without waiting
    # for Perspective's internal flush timeout.
    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        perspective = page.locator('[data-view-id="sales-perspective"]')
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
        selection = page.locator(
            '[data-control-key="dashboard:sales-overview/region"] select[data-control-input]'
        )
        expect(selection).to_have_count(1)

        selection.evaluate(
            """input => {
              window.datavizComponents.controls.clearOptions(input);
              window.datavizComponents.controls.markSelectionIntent(input, 'explicit');
              window.datavizComponents.controls.emitChange(input);
            }"""
        )
        expect(perspective).to_have_attribute("data-view-status", "empty", timeout=2_000)
        expect(perspective).to_contain_text("No rows match the current selections.", timeout=2_000)

        selection.evaluate(
            """input => {
              input.options[0].selected = true;
              window.datavizComponents.controls.markSelectionIntent(input, 'explicit');
              window.datavizComponents.controls.emitChange(input);
            }"""
        )
        expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
        expect(perspective.locator("perspective-viewer")).to_have_count(1)


@pytest.mark.e2e
def test_cross_browser_perspective_repeated_dispose_and_restore(page: Page, tmp_path: Path):
    _route_perspective_contract_runtime(page)
    workspace = _copy_workspace(MINIMAL, tmp_path / "perspective-restore-matrix")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        # Two cycles prove that disposal/restoration is repeatable; the third
        # duplicated the same state transition. Synchronize on readiness below.
        for _cycle in range(2):
            frame = page.frame_locator("#canvas-frame")
            perspective = frame.locator('[data-view-id="sales-perspective"]')
            expect(perspective).to_have_attribute("data-view-status", "ready", timeout=30_000)
            viewer = perspective.locator("perspective-viewer")
            expect(viewer).to_be_visible(timeout=30_000)
            scroll_state = viewer.evaluate(
                """viewer => {
                  window.scrollTo(0, 0);
                  const before = window.parent.scrollY + window.scrollY;
                  viewer.dispatchEvent(new WheelEvent('wheel', {
                    deltaY:500, bubbles:true, cancelable:true, composed:true,
                  }));
                  return {before, after:window.parent.scrollY + window.scrollY};
                }"""
            )
            assert scroll_state["after"] > scroll_state["before"]
            frame_id = page.locator("#canvas-frame").get_attribute("data-frame-id")
            disposed = frame.locator("body").evaluate(
                """async () => {
                  const runtime = window.datavizRuntime;
                  runtime.dispose();
                  const deadline = performance.now() + 5000;
                  while (
                    runtime.metrics.perspective.disposed < runtime.metrics.perspective.created
                    && performance.now() < deadline
                  ) await new Promise(resolve => setTimeout(resolve, 20));
                  return structuredClone(runtime.metrics.perspective);
                }"""
            )
            assert disposed["created"] >= 1
            assert disposed["disposed"] == disposed["created"]
            page.locator("#dashboard-reload").evaluate("button => button.click()")
            page.wait_for_function(
                """previous => {
                  const frame = document.querySelector('#canvas-frame');
                  const id = frame?.dataset.frameId;
                  const active = frame?.contentWindow;
                  return Boolean(id && id !== previous && active?.dataviz?.frame_id === id
                    && active?.datavizRuntime?.metrics?.perspective?.created > 0);
                }""",
                arg=frame_id,
                timeout=15_000,
            )
        expect(page.locator("#query-diagnostics-label")).to_have_text("Ready")
