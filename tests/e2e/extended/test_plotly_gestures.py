from __future__ import annotations



import re


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
)


from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _running_static_server,
    _open_dashboard,
    _run_and_wait,
    _export_html,
    _plotly_writer_targets,
    SHOWCASE,
)

@pytest.mark.e2e
@pytest.mark.parametrize(
    ("view_id", "point_kind"),
    [
        pytest.param("ranking", "bar", id="bar"),
        pytest.param("scatter", "scatter", id="scatter"),
    ],
)
def test_plotly_writer_real_mouse_gestures_commit_at_human_cadence(
    page: Page,
    tmp_path: Path,
    view_id: str,
    point_kind: str,
):
    """One physical gesture must become one correct action across real timing windows."""

    workspace = _copy_workspace(SHOWCASE, tmp_path / f"natural-{point_kind}-writer", dashboards=('功能示例##chart-gallery',))
    control_key = "dashboard:chart-gallery/province"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame(name="canvas-frame")
        assert frame is not None
        view = frame.locator(f'[data-view-id="{view_id}"]')
        chart = view.locator(".dv-plotly")
        expect(view).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(chart).to_be_visible()
        values, target_boxes = _plotly_writer_targets(chart, point_kind)
        baseline_revision = frame.evaluate("() => window.dataviz.controlActions.revision")

        # This observer is intentionally passive: wrapping Plotly.react/restyle
        # changes the microtask timing this regression is supposed to exercise.
        frame.evaluate(
            """viewId => {
              const trace = window.__plotlyNaturalMouseRegression = {
                pointers:[], raw:[], actions:[], afterplots:[],
              };
              const pointerTarget = target => ({
                tag:target?.tagName || null,
                class_name:typeof target?.className === 'object'
                  ? target.className.baseVal
                  : target?.className || null,
                view:target?.closest?.('[data-view-id]')?.dataset.viewId || null,
              });
              let pointerStartedInView = false;
              document.addEventListener('pointerdown', event => {
                if (!event.target?.closest?.(`[data-view-id="${CSS.escape(viewId)}"]`)) return;
                pointerStartedInView = true;
                trace.pointers.push({
                  at:performance.now(), type:'pointerdown',
                  x:event.clientX, y:event.clientY,
                  ...pointerTarget(event.target),
                });
              }, true);
              document.addEventListener('pointerup', event => {
                if (!pointerStartedInView) return;
                pointerStartedInView = false;
                trace.pointers.push({
                  at:performance.now(), type:'pointerup',
                  x:event.clientX, y:event.clientY,
                  ...pointerTarget(event.target),
                });
              }, true);
              const actions = window.dataviz.controlActions;
              const originalDispatch = actions.dispatch.bind(actions);
              actions.dispatch = event => {
                const record = {
                  at:performance.now(), action_id:event.action_id,
                  source_view:event.source_view, action:event.action,
                  value:event.data?.__datavizControlValue,
                };
                trace.actions.push(record);
                const outcome = originalDispatch(event);
                Promise.resolve(outcome).then(
                  result => { record.result = result; },
                  error => { record.error = String(error); },
                );
                return outcome;
              };
              const node = document.querySelector(
                `[data-view-id="${CSS.escape(viewId)}"] .dv-plotly`
              );
              node.on('plotly_click', event => trace.raw.push({
                at:performance.now(),
                values:(event?.points || []).map(point => point.customdata),
              }));
              node.on('plotly_afterplot', () => {
                trace.afterplots.push({at:performance.now()});
              });
            }""",
            view_id,
        )

        # Representative quick/intermediate/slow gaps, four distinct values and
        # a return to earlier values. Eighteen permutations added no contract.
        order = (0, 1, 2, 3, 1, 0)
        cadences_ms = (80, 260, 650, 80, 260, 650)
        travels = ((0, 0), (2, 1), (4, 3)) * 2
        for gesture_index, point_index in enumerate(order):
            target_box = target_boxes[point_index]
            assert target_box is not None
            x = target_box["x"] + target_box["width"] / 2
            y_fraction = (0.28, 0.5, 0.72)[gesture_index % 3] if point_kind == "bar" else 0.5
            y = target_box["y"] + target_box["height"] * y_fraction
            dx, dy = travels[gesture_index]
            page.mouse.move(x, y, steps=4)
            page.mouse.down()
            if dx or dy:
                page.mouse.move(x + dx, y + dy)
            page.mouse.up()
            page.wait_for_timeout(cadences_ms[gesture_index])

        try:
            frame.wait_for_function(
                """expected => {
                  const actions = window.__plotlyNaturalMouseRegression.actions;
                  return actions.length === expected
                    && actions.every(item => Boolean(item.result || item.error));
                }""",
                arg=len(order),
                timeout=10_000,
            )
        except PlaywrightTimeoutError:
            diagnostics = frame.evaluate("() => window.__plotlyNaturalMouseRegression")
            pytest.fail(f"{point_kind} natural gestures were lost or duplicated: {diagnostics}")

        diagnostics = frame.evaluate("() => window.__plotlyNaturalMouseRegression")
        expected_values = [values[index] for index in order]
        assert [item["type"] for item in diagnostics["pointers"]] == [
            event_type for _ in order for event_type in ("pointerdown", "pointerup")
        ]
        pointer_pairs = list(
            zip(diagnostics["pointers"][::2], diagnostics["pointers"][1::2], strict=True)
        )
        for (pointer_down, pointer_up), (expected_dx, expected_dy) in zip(
            pointer_pairs, travels, strict=True
        ):
            assert pointer_down["view"] == view_id
            assert pointer_up["x"] - pointer_down["x"] == pytest.approx(expected_dx, abs=0.5)
            assert pointer_up["y"] - pointer_down["y"] == pytest.approx(expected_dy, abs=0.5)

        # Assert actions, ordering and visual state below, not a machine-speed
        # ceiling on Playwright's wall-clock intervals under parallel CI load.

        actions = diagnostics["actions"]
        assert len({item["action_id"] for item in actions}) == len(order)
        assert [item["source_view"] for item in actions] == [view_id] * len(order)
        assert [item["action"] for item in actions] == ["select"] * len(order)
        assert [item["value"] for item in actions] == expected_values
        assert [item.get("error") for item in actions] == [None] * len(order)
        assert [item["result"]["status"] for item in actions] == ["committed"] * len(order)
        assert [item["result"]["revision"] for item in actions] == list(
            range(baseline_revision + 1, baseline_revision + len(order) + 1)
        )

        final_value = expected_values[-1]
        frame.wait_for_function(
            """settings => {
              const state = window.dataviz.control.state(settings.controlKey);
              const cells = [...document.querySelectorAll(
                '[data-view-id="records"] tbody tr td:first-child'
              )].map(cell => cell.textContent.trim());
              return state.value.length === 1 && state.value[0] === settings.value
                && cells.length > 0 && cells.every(value => value === settings.value);
            }""",
            arg={"controlKey": control_key, "value": final_value},
            timeout=10_000,
        )
        expect(page.locator(f'select[name="{control_key}"]')).to_have_values(
            [final_value], timeout=5_000
        )
        visual = chart.evaluate(
            """(node, settings) => {
              if (settings.kind === 'bar') {
                const points = [...node.querySelectorAll('.barlayer .point')];
                return points.map((point, index) => ({
                  value:node.data[0].customdata[index],
                  opacities:[Number(getComputedStyle(point.querySelector('path')).opacity)],
                }));
              }
              const traces = [...node.querySelectorAll('.scatterlayer .trace')];
              return traces.map((traceNode, index) => ({
                value:node.data[index].customdata[0],
                opacities:[...traceNode.querySelectorAll('.point')]
                  .map(point => Number(getComputedStyle(point).opacity)),
              }));
            }""",
            {"kind": point_kind},
        )
        selected_opacities = [
            opacity
            for item in visual
            if item["value"] == final_value
            for opacity in item["opacities"]
        ]
        unselected_opacities = [
            opacity
            for item in visual
            if item["value"] != final_value
            for opacity in item["opacities"]
        ]
        assert selected_opacities and unselected_opacities, visual
        assert min(selected_opacities) > max(unselected_opacities), visual


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("view_id", "point_kind"),
    [
        pytest.param("ranking", "bar", id="bar"),
        pytest.param("scatter", "scatter", id="scatter"),
    ],
)
def test_plotly_writer_recovers_wrong_or_missing_raw_click(
    page: Page,
    tmp_path: Path,
    view_id: str,
    point_kind: str,
):
    """Removing the Dataviz point candidate/fallback must make this test fail."""

    workspace = _copy_workspace(SHOWCASE, tmp_path / f"fault-{point_kind}-writer", dashboards=('功能示例##chart-gallery',))
    control_key = "dashboard:chart-gallery/province"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame(name="canvas-frame")
        assert frame is not None
        view = frame.locator(f'[data-view-id="{view_id}"]')
        chart = view.locator(".dv-plotly")
        expect(view).to_have_attribute("data-view-status", "ready", timeout=20_000)
        expect(chart).to_be_visible()
        values, target_boxes = _plotly_writer_targets(chart, point_kind)
        intended_indices = (1, 2)
        expected_values = [values[index] for index in intended_indices]

        frame.evaluate(
            """viewId => {
              const trace = window.__plotlyFaultRegression = {
                raw:[], actions:[], dropped_raw_clicks:0,
              };
              const actions = window.dataviz.controlActions;
              const originalDispatch = actions.dispatch.bind(actions);
              actions.dispatch = event => {
                const record = {
                  action_id:event.action_id, source_view:event.source_view,
                  action:event.action, value:event.data?.__datavizControlValue,
                };
                trace.actions.push(record);
                const outcome = originalDispatch(event);
                Promise.resolve(outcome).then(
                  result => { record.result = result; },
                  error => { record.error = String(error); },
                );
                return outcome;
              };
              const node = document.querySelector(
                `[data-view-id="${CSS.escape(viewId)}"] .dv-plotly`
              );
              node.on('plotly_click', event => trace.raw.push(
                (event?.points || []).map(point => point.customdata)
              ));
            }""",
            view_id,
        )

        def wait_for_action(action_count: int, value) -> None:
            frame.wait_for_function(
                """settings => {
                  const trace = window.__plotlyFaultRegression;
                  const state = window.dataviz.control.state(settings.controlKey);
                  return trace.actions.length === settings.actionCount
                    && Boolean(trace.actions.at(-1)?.result)
                    && state.value.length === 1
                    && state.value[0] === settings.value;
                }""",
                arg={
                    "actionCount": action_count,
                    "controlKey": control_key,
                    "value": value,
                },
                timeout=10_000,
            )

        # Reproduce Plotly 4.0.0's stale-hover path without changing its event
        # emitter: move to the intended point, then establish a different
        # Plotly hover immediately before the physical click. Fx.click can read
        # the throttled old _hoverdata, while Dataviz must use the down target.
        first_box = target_boxes[intended_indices[0]]
        assert first_box is not None
        first_x = first_box["x"] + first_box["width"] / 2
        first_y = first_box["y"] + first_box["height"] / 2
        page.mouse.move(first_x, first_y, steps=4)
        stale_hover = chart.evaluate(
            """(node, intendedValue) => {
              const candidates = (node.data || []).flatMap((trace, curveNumber) => (
                (trace.customdata || []).map((_value, pointNumber) => ({
                  curveNumber, pointNumber,
                }))
              ));
              for (const candidate of candidates) {
                window.Plotly.Fx.unhover(node);
                window.Plotly.Fx.hover(node, [candidate]);
                const values = (node._hoverdata || []).map(item => item.customdata);
                if (values.length && values[0] !== intendedValue) {
                  return {candidate, values};
                }
              }
              return null;
            }""",
            expected_values[0],
        )
        assert stale_hover is not None
        wrong_value = stale_hover["values"][0]
        assert wrong_value != expected_values[0]
        frame.evaluate(
            """([viewId, wrongValue]) => {
              const node = document.querySelector(
                `[data-view-id="${CSS.escape(viewId)}"] .dv-plotly`
              );
              const originalEmit = node.emit.bind(node);
              let pendingWrongRaw = true;
              node.emit = (name, ...args) => {
                if (name === 'plotly_click' && pendingWrongRaw) {
                  pendingWrongRaw = false;
                  const event = args[0] || {};
                  event.points = (event.points || []).map(point => ({
                    ...point,
                    customdata:wrongValue,
                  }));
                }
                return originalEmit(name, ...args);
              };
            }""",
            [view_id, wrong_value],
        )
        page.mouse.down()
        page.mouse.up()
        wait_for_action(1, expected_values[0])
        page.wait_for_timeout(400)

        # A missing raw event is a separate failure mode. Drop exactly the next
        # Plotly click at its emitter, then use another physical micro-jitter
        # gesture. Without the Dataviz fallback this produces no action.
        frame.evaluate(
            """viewId => {
              const trace = window.__plotlyFaultRegression;
              const node = document.querySelector(
                `[data-view-id="${CSS.escape(viewId)}"] .dv-plotly`
              );
              const originalEmit = node.emit.bind(node);
              let pendingDrop = true;
              node.emit = (name, ...args) => {
                if (name === 'plotly_click' && pendingDrop) {
                  pendingDrop = false;
                  trace.dropped_raw_clicks += 1;
                  return node;
                }
                return originalEmit(name, ...args);
              };
            }""",
            view_id,
        )
        second_box = target_boxes[intended_indices[1]]
        assert second_box is not None
        second_x = second_box["x"] + second_box["width"] / 2
        second_y = second_box["y"] + second_box["height"] / 2
        page.mouse.move(second_x, second_y, steps=4)
        page.mouse.down()
        page.mouse.move(second_x + 4, second_y + 3)
        page.mouse.up()
        wait_for_action(2, expected_values[1])
        page.wait_for_timeout(400)

        diagnostics = frame.evaluate("() => window.__plotlyFaultRegression")
        assert diagnostics["dropped_raw_clicks"] == 1
        assert diagnostics["raw"] == [[wrong_value]]
        actions = diagnostics["actions"]
        assert len(actions) == len(expected_values)
        assert len({item["action_id"] for item in actions}) == len(expected_values)
        assert [item["source_view"] for item in actions] == [view_id] * len(expected_values)
        assert [item["action"] for item in actions] == ["select"] * len(expected_values)
        assert [item["value"] for item in actions] == expected_values
        assert [item.get("error") for item in actions] == [None] * len(expected_values)
        assert [item["result"]["status"] for item in actions] == [
            "committed"
        ] * len(expected_values)
        assert frame.evaluate(
            "key => window.dataviz.control.state(key).value", control_key
        ) == [expected_values[-1]]


@pytest.mark.e2e
def test_plotly_native_double_click_restores_zoom_without_resetting_control(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "plotly-native-double-click", dashboards=('功能示例##chart-gallery',))
    control_key = "dashboard:chart-gallery/province"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame(name="canvas-frame")
        assert frame is not None
        scatter = frame.locator('[data-view-id="scatter"] .dv-plotly')
        expect(scatter).to_be_visible()
        scatter.scroll_into_view_if_needed()

        selected_value = scatter.evaluate("node => node.data[0].customdata[0]")
        scatter.evaluate(
            """(node, customdata) => node.emit('plotly_click', {
              points:[{customdata}],
            })""",
            selected_value,
        )
        frame.wait_for_function(
            """expected => {
              const state = window.dataviz.control.state(
                'dashboard:chart-gallery/province'
              );
              return state.value.length === 1 && state.value[0] === expected;
            }""",
            arg=selected_value,
            timeout=5_000,
        )
        before = frame.evaluate(
            """key => ({
              control:window.dataviz.control.state(key),
              revision:window.dataviz.controlActions.revision,
              provenance:structuredClone(window.dataviz.control_writer_provenance),
            })""",
            control_key,
        )
        zoomed_range = scatter.evaluate(
            """async node => {
              const values = node.data.flatMap(trace => trace.x).map(Number);
              const minimum = Math.min(...values);
              const maximum = Math.max(...values);
              const range = [minimum, minimum + (maximum - minimum) / 3];
              window.__plotlyDoubleClicks = 0;
              node.on('plotly_doubleclick', () => { window.__plotlyDoubleClicks += 1; });
              await window.Plotly.relayout(node, {
                'xaxis.autorange':false,
                'xaxis.range':range,
              });
              return range;
            }"""
        )
        assert scatter.evaluate("node => node._fullLayout.xaxis.autorange") is False

        drag_surface = scatter.locator(".nsewdrag")
        expect(drag_surface).to_be_visible()
        drag_box = drag_surface.bounding_box()
        assert drag_box is not None
        occluders = scatter.locator(".scatterlayer .point, .legend, .modebar")
        occluder_boxes = [
            box
            for index in range(occluders.count())
            if (box := occluders.nth(index).bounding_box()) is not None
        ]
        candidates = [
            (
                drag_box["x"] + drag_box["width"] * x_fraction,
                drag_box["y"] + drag_box["height"] * y_fraction,
            )
            for y_fraction in (0.18, 0.38, 0.62, 0.82)
            for x_fraction in (0.12, 0.32, 0.52, 0.72, 0.88)
        ]
        background = next(
            (x, y)
            for x, y in candidates
            if not any(
                box["x"] - 6 <= x <= box["x"] + box["width"] + 6
                and box["y"] - 6 <= y <= box["y"] + box["height"] + 6
                for box in occluder_boxes
            )
        )
        # Locator.dblclick() performs an actionability check against Plotly's
        # intentional SVG overlays; a real mouse gesture should target a
        # verified empty coordinate in the rendered plotting rectangle.
        page.mouse.dblclick(
            *background,
            delay=80,
        )
        frame.wait_for_function(
            """() => {
              const node = document.querySelector('[data-view-id="scatter"] .dv-plotly');
              return window.__plotlyDoubleClicks === 1
                && node._fullLayout.xaxis.autorange === true;
            }""",
            timeout=5_000,
        )
        assert scatter.evaluate("node => node._fullLayout.xaxis.range") != zoomed_range
        after = frame.evaluate(
            """key => ({
              control:window.dataviz.control.state(key),
              revision:window.dataviz.controlActions.revision,
              provenance:structuredClone(window.dataviz.control_writer_provenance),
            })""",
            control_key,
        )
        assert after == before


@pytest.mark.e2e
@pytest.mark.parametrize("dragmode", ["select", "lasso"])
def test_plotly_area_selection_gesture_commits_the_bound_control(
    page: Page, tmp_path: Path, dragmode: str
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / f"plotly-{dragmode}", dashboards=('功能示例##chart-gallery',))
    report_path = tmp_path / f"plotly-{dragmode}-toggle.html"
    dashboard_path = workspace / "dashboards" / "功能示例##chart-gallery" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["controls"][0]["initial"] = {"mode": "empty"}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        view = frame.locator('[data-view-id="scatter"]')
        chart = view.locator(".dv-plotly")
        expect(view).to_have_attribute("data-view-status", "ready", timeout=20_000)
        chart.scroll_into_view_if_needed()
        modebar_titles = chart.locator(".modebar-btn").evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('data-title'))"
        )
        assert set(modebar_titles) == {
            "Box Select",
            "Lasso Select",
            "Restore default selection",
        }
        expect(chart.locator(".modebar-group")).to_have_count(1)
        chart.evaluate(
            "(node, mode) => window.Plotly.relayout(node, {dragmode:mode})",
            dragmode,
        )
        drag_layer = chart.locator(".nsewdrag")
        box = drag_layer.bounding_box()
        assert box is not None

        points = [
            (box["x"] + box["width"] * 0.05, box["y"] + box["height"] * 0.45),
            (box["x"] + box["width"] * 0.58, box["y"] + box["height"] * 0.45),
            (box["x"] + box["width"] * 0.58, box["y"] + box["height"] * 0.95),
            (box["x"] + box["width"] * 0.05, box["y"] + box["height"] * 0.95),
        ]
        page.mouse.move(*points[0])
        page.mouse.down()
        if dragmode == "select":
            page.mouse.move(*points[2], steps=20)
        else:
            for point in [*points[1:], points[0]]:
                page.mouse.move(*point, steps=8)
        page.mouse.up()

        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .dataviz.control.state('dashboard:chart-gallery/province')
              .value.length > 0""",
            timeout=10_000,
        )
        selection = frame.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        )
        assert selection["intent"] == "explicit"
        assert 0 < len(selection["value"]) < 4

        page.wait_for_function(
            """() => {
              const node = document.querySelector('#canvas-frame').contentWindow
                .document.querySelector('[data-view-id="scatter"] .dv-plotly');
              return (node.layout?.selections || []).length === 0
                && !node.querySelector('.select-outline');
            }""",
            timeout=10_000,
        )

        mode_title = "Box Select" if dragmode == "select" else "Lasso Select"
        active_tool = chart.locator(f'.modebar-btn[data-title="{mode_title}"]')
        expect(active_tool).to_have_class(re.compile(r"\bactive\b"))
        active_tool.click()
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .document.querySelector('[data-view-id="scatter"] .dv-plotly')
              ._fullLayout.dragmode === 'zoom'""",
            timeout=10_000,
        )
        expect(active_tool).not_to_have_class(re.compile(r"\bactive\b"))
        assert frame.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        ) == selection

        # Seal the selected state before Reset so portable HTML proves the same
        # click-active-tool-again behavior with no Server callback.
        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

        chart.locator('.modebar-btn[data-title="Restore default selection"]').click()
        page.wait_for_function(
            """() => document.querySelector('#canvas-frame').contentWindow
              .dataviz.control.state('dashboard:chart-gallery/province')
              .value.length === 0""",
            timeout=10_000,
        )

    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        view = page.locator('[data-view-id="scatter"]')
        expect(view).to_have_attribute("data-view-status", "ready", timeout=20_000)
        chart = view.locator(".dv-plotly")
        active_tool = chart.locator(
            f'.modebar-btn[data-title="{"Box Select" if dragmode == "select" else "Lasso Select"}"]'
        )
        portable_selection = page.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        )
        assert portable_selection == selection
        chart.evaluate("""node => {
          node.__selectionPointCounts = [];
          node.on('plotly_selected', event => node.__selectionPointCounts.push(event?.points?.length || 0));
        }""")
        active_tool.click()
        expect(active_tool).to_have_class(re.compile(r"\bactive\b"))
        chart.scroll_into_view_if_needed()
        drag_layer = chart.locator(".nsewdrag")
        box = drag_layer.bounding_box()
        assert box is not None
        points = [
            (box["x"] + box["width"] * 0.05, box["y"] + box["height"] * 0.45),
            (box["x"] + box["width"] * 0.95, box["y"] + box["height"] * 0.45),
            (box["x"] + box["width"] * 0.95, box["y"] + box["height"] * 0.95),
            (box["x"] + box["width"] * 0.05, box["y"] + box["height"] * 0.95),
        ]
        page.mouse.move(*points[0])
        page.mouse.down()
        # Start a real sibling chart while the portable selection is held.
        # Plotly.newPlot otherwise clears the pending selection throttle.
        page.evaluate("""() => {
          const host = document.createElement('div');
          host.style.cssText = 'position:fixed;left:-1000px;width:100px;height:100px';
          document.body.append(host);
          window.__siblingPlot = {host, ready:false};
          window.__siblingPlot.promise = window.dataviz.charts.plotly.mount(host, {
            data:[{x:[1,2], y:[1,2], type:'scatter'}]
          }).then(state => { window.__siblingPlot.state = state; window.__siblingPlot.ready = true; });
        }""")
        assert page.evaluate('() => !window.__siblingPlot.host.classList.contains("js-plotly-plot")')
        if dragmode == "select":
            page.mouse.move(*points[2], steps=20)
        else:
            for point in [*points[1:], points[0]]:
                page.mouse.move(*point, steps=8)
        page.mouse.up()
        try:
            page.wait_for_function(
                """() => {
                  const node = document.querySelector('[data-view-id="scatter"] .dv-plotly');
                  return (node.layout?.selections || []).length === 0
                    && !node.querySelector('.select-outline');
                }""",
                timeout=20_000,
            )
        finally:
            print('Portable selection diagnostic:', chart.evaluate("node => ({events:node.__selectionPointCounts, selections:node.layout?.selections?.length, outlines:node.querySelectorAll('.select-outline').length, mode:node._fullLayout?.dragmode})"))
        assert chart.evaluate('node => node.__selectionPointCounts.some(count => count > 0)')
        page.evaluate("""async () => {
          await window.__siblingPlot.promise;
          window.dataviz.charts.plotly.dispose(window.__siblingPlot.state);
          window.__siblingPlot.host.remove();
        }""")
        expect(active_tool).to_have_class(re.compile(r"\bactive\b"))
        portable_selection_after_gesture = page.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        )
        assert portable_selection_after_gesture["value"]
        active_tool.click()
        page.wait_for_function(
            """() => document.querySelector('[data-view-id="scatter"] .dv-plotly')
              ._fullLayout.dragmode === 'zoom'""",
            timeout=10_000,
        )
        expect(active_tool).not_to_have_class(re.compile(r"\bactive\b"))
        assert page.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province')"
        ) == portable_selection_after_gesture
