from __future__ import annotations

import json


import re


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _running_static_server,
    _open_dashboard,
    _run_and_wait,
    _export_html,
    ROOT,
    SHOWCASE,
    MINIMAL,
)

@pytest.mark.e2e
def test_plotly_defaults_to_page_wheel_and_allows_explicit_scroll_zoom(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "plotly-wheel")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    dashboard = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    explicit_view = next(view for view in dashboard["views"] if view["id"] == "region-comparison")
    explicit_view["config"] = {"scrollZoom": True}
    dashboard_path.write_text(
        yaml.safe_dump(dashboard, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        default_chart = frame.locator('[data-view-id="revenue-trend"] .dv-plotly')
        explicit_chart = frame.locator('[data-view-id="region-comparison"] .dv-plotly')
        expect(default_chart).to_be_visible(timeout=15_000)
        expect(explicit_chart).to_be_visible(timeout=15_000)

        expect(default_chart.locator(".modebar-btn")).to_have_count(0)
        expect(explicit_chart.locator(".modebar-btn")).to_have_count(0)
        assert default_chart.evaluate("node => node._context.scrollZoom") is False
        assert explicit_chart.evaluate("node => node._context.scrollZoom") is True

        default_chart.scroll_into_view_if_needed()
        before = default_chart.evaluate(
            """node => ({
              scrollY:window.scrollY,
              maxScrollY:Math.max(0, document.documentElement.scrollHeight - window.innerHeight),
              shellScrollY:window.parent.scrollY,
              shellMaxScrollY:Math.max(
                0,
                window.parent.document.documentElement.scrollHeight - window.parent.innerHeight,
              ),
              xRange:[...node._fullLayout.xaxis.range],
            })"""
        )
        drag_layer = default_chart.locator(".nsewdrag")
        can_scroll_down = (
            before["shellScrollY"] < before["shellMaxScrollY"] - 1
            or before["scrollY"] < before["maxScrollY"] - 1
        )
        wheel_delta = 500 if can_scroll_down else -500
        drag_layer.evaluate(
            """(node, deltaY) => node.dispatchEvent(new WheelEvent('wheel', {
              bubbles:true,
              cancelable:true,
              composed:true,
              deltaY,
            }))""",
            wheel_delta,
        )
        page.wait_for_function(
            "before => { const frame = document.querySelector('#canvas-frame').contentWindow; "
            "return window.scrollY + frame.scrollY !== before; }",
            arg=before['shellScrollY'] + before['scrollY'],
        )
        after = default_chart.evaluate(
            """node => ({
              scrollY:window.scrollY,
              shellScrollY:window.parent.scrollY,
              xRange:[...node._fullLayout.xaxis.range],
            })"""
        )
        before_scroll = before["shellScrollY"] + before["scrollY"]
        after_scroll = after["shellScrollY"] + after["scrollY"]
        if wheel_delta > 0:
            assert after_scroll > before_scroll
        else:
            assert after_scroll < before_scroll
        assert after["xRange"] == before["xRange"]


@pytest.mark.e2e
def test_plotly_control_binding_commits_once_and_keeps_bound_candidates(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / "bound-view")
    dashboard_path = workspace / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    bound_view = next(item for item in definition["views"] if item["id"] == "region-comparison")
    bound_view["control_binding"] = "dashboard.region"
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    report_path = tmp_path / "bound-view-report.html"

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        bound = frame.locator('[data-view-id="region-comparison"]')
        consumer = frame.locator('[data-view-id="sales-detail"]')
        expect(bound).to_have_attribute("data-view-status", "ready", timeout=20_000)
        chart = bound.locator(".dv-plotly")
        expect(chart).to_be_visible()
        assert chart.evaluate("node => node.data[0].x.length") == 3

        selected_values = chart.evaluate(
            """node => {
              const values = node.data[0].customdata.slice(0, 2);
              node.emit('plotly_selected', {
                points:values.map(customdata => ({customdata})),
              });
              return values;
            }"""
        )
        expect(consumer.locator("tbody tr")).to_have_count(8)
        assert (
            frame.locator("body").evaluate(
                "() => window.dataviz.control.state('dashboard:sales-overview/region').value"
            )
            == selected_values
        )

        # Plotly's double-click gesture belongs to chart navigation.  It must
        # never be overloaded as a Control reset because two rapid point
        # selections can also be classified as a double click.
        chart.evaluate("node => node.emit('plotly_doubleclick')")
        assert frame.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:sales-overview/region').value"
        ) == selected_values

        chart.locator('.modebar-btn[data-title="Restore default selection"]').click()
        expect(consumer.locator("tbody tr")).to_have_count(12)
        assert frame.locator("body").evaluate(
            "() => window.dataviz.control.state('dashboard:sales-overview/region').value"
        ) == ["华东", "华南", "华北"]

        chart.evaluate(
            """node => {
              node.emit('plotly_click', {
                points:[{customdata:node.data[0].customdata[0]}],
              });
              node.emit('plotly_selected', {points:[]});
            }"""
        )
        expect(consumer.locator("tbody tr")).to_have_count(4)
        assert chart.evaluate("node => node.data[0].x.length") == 3
        state = frame.locator("body").evaluate(
            """() => ({
              selection:window.dataviz.control.state('dashboard:sales-overview/region'),
              revision:window.dataviz.controlActions.revision,
            })"""
        )
        assert state["selection"]["intent"] == "explicit"
        assert state["selection"]["value"] == ["华东"]
        assert state["revision"] == 3

        no_op = chart.evaluate(
            """node => window.dataviz.controlActions.dispatch({
              action_id:'region-noop',
              source_view:'region-comparison',
              control:'dashboard:sales-overview/region',
              generation:document.querySelector('[data-view-id="region-comparison"]')
                ._datavizRenderGeneration,
              action:'select',
              data:{__datavizControlValue:'华东'},
            })"""
        )
        assert no_op == {
            "status": "noop",
            "revision": 3,
            "action_id": "region-noop",
            "source_view": "region-comparison",
        }
        assert frame.locator("body").evaluate("() => window.dataviz.controlActions.revision") == 3

        stale = frame.locator("body").evaluate(
            """() => window.dataviz.controlActions.dispatch({
              action_id:'region-stale',
              source_view:'region-comparison',
              control:'dashboard:sales-overview/region',
              generation:0,
              action:'select',
              data:{__datavizControlValue:'华南'},
            })"""
        )
        assert stale == {
            "status": "rejected",
            "code": "stale_view_generation",
            "action_id": "region-stale",
            "source_view": "region-comparison",
        }
        assert frame.locator("body").evaluate("() => window.dataviz.controlActions.revision") == 3

        frame.locator("body").evaluate(
            """() => window.dataviz.controlActions.dispatch({
              action_id:'region-clear',
              source_view:'region-comparison',
              control:'dashboard:sales-overview/region',
              generation:document.querySelector('[data-view-id="region-comparison"]')
                ._datavizRenderGeneration,
              action:'clear',
            })"""
        )
        expect(consumer).to_have_attribute("data-view-status", "empty")
        expect(consumer).to_contain_text("No rows match the current selections.")
        assert chart.evaluate("node => node.data[0].x.length") == 3

        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

    # The portable report uses the same View Adapter and canonical commit path;
    # it does not carry a server-only callback implementation.
    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        bound = page.locator('[data-view-id="region-comparison"]')
        consumer = page.locator('[data-view-id="sales-detail"]')
        expect(bound).to_have_attribute("data-view-status", "ready", timeout=20_000)
        chart = bound.locator(".dv-plotly")
        assert chart.evaluate("node => node.data[0].x.length") == 3
        chart.evaluate(
            """node => node.emit('plotly_click', {
              points:[{customdata:node.data[0].customdata[0]}],
            })"""
        )
        expect(consumer.locator("tbody tr")).to_have_count(4)


@pytest.mark.e2e
def test_queued_plotly_writer_actions_survive_source_view_rerender(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "rapid-view-writers", dashboards=('功能示例##chart-gallery',))

    def emit_plotly_click(chart, value) -> None:
        chart.evaluate(
            """(node, customdata) => node.emit('plotly_click', {
              points:[{customdata}],
            })""",
            value,
        )

    def arm_gate(frame) -> None:
        frame.evaluate(
            """() => {
              window.__writerActionTrace = [];
              window.__armWriterActionGate();
            }"""
        )

    def release_and_read(frame, expected_count: int) -> list[dict]:
        frame.evaluate("() => window.__releaseWriterActionGate()")
        frame.wait_for_function(
            "count => window.__writerActionTrace.length === count "
            "&& window.__writerActionTrace.every(item => item.result)",
            arg=expected_count,
            timeout=20_000,
        )
        return frame.evaluate("() => window.__writerActionTrace")

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame(name="canvas-frame")
        assert frame is not None
        for view_id in ("ranking", "scatter", "records"):
            expect(frame.locator(f'[data-view-id="{view_id}"]')).to_have_attribute(
                "data-view-status", "ready", timeout=20_000
            )

        frame.evaluate(
            """() => {
              const actions = window.dataviz.controlActions;
              const originalDispatch = actions.dispatch.bind(actions);
              const originalApply = window.dataviz.applyControls.bind(window.dataviz);
              window.__writerActionTrace = [];
              window.__writerActionGate = null;
              window.__armWriterActionGate = () => {
                let release;
                const promise = new Promise(resolve => { release = resolve; });
                window.__writerActionGate = {promise, release, entered:false};
                document.body.dataset.writerActionGate = 'armed';
              };
              window.__releaseWriterActionGate = () => {
                window.__writerActionGate?.release();
                document.body.dataset.writerActionGate = 'released';
              };
              actions.dispatch = event => {
                const record = {
                  action:event.action,
                  value:event.data?.__datavizControlValue,
                  generation:event.generation,
                };
                window.__writerActionTrace.push(record);
                return Promise.resolve(originalDispatch(event)).then(result => {
                  record.result = result;
                  return result;
                });
              };
              window.dataviz.applyControls = async options => {
                const gate = window.__writerActionGate;
                if (gate && !gate.entered) {
                  gate.entered = true;
                  document.body.dataset.writerActionGate = 'entered';
                  await gate.promise;
                }
                return originalApply(options);
              };
            }"""
        )

        ranking = frame.locator('[data-view-id="ranking"] .dv-plotly')
        ranking_points = ranking.locator(".bars .point")
        expect(ranking).to_be_visible()
        assert ranking_points.count() == 4
        ranking_values = ranking.evaluate("node => node.data[0].customdata.slice(0, 3)")

        arm_gate(frame)
        emit_plotly_click(ranking, ranking_values[0])
        expect(frame.locator("body")).to_have_attribute("data-writer-action-gate", "entered")
        emit_plotly_click(ranking, ranking_values[1])
        emit_plotly_click(ranking, ranking_values[2])
        ranking_trace = release_and_read(frame, 3)

        assert [item["value"] for item in ranking_trace] == ranking_values
        assert [item["result"]["status"] for item in ranking_trace] == [
            "committed",
            "committed",
            "committed",
        ]
        assert [item["result"]["revision"] for item in ranking_trace] == [1, 2, 3]

        scatter = frame.locator('[data-view-id="scatter"] .dv-plotly')
        expect(frame.locator('[data-view-id="scatter"]')).to_have_attribute(
            "data-view-status", "ready", timeout=20_000
        )
        scatter_traces = scatter.locator(".scatterlayer .trace")
        assert scatter_traces.count() >= 3
        scatter_values = scatter.evaluate(
            "node => node.data.slice(0, 3).map(trace => trace.customdata[0])"
        )

        arm_gate(frame)
        emit_plotly_click(scatter, scatter_values[0])
        expect(frame.locator("body")).to_have_attribute("data-writer-action-gate", "entered")
        emit_plotly_click(scatter, scatter_values[1])
        emit_plotly_click(scatter, scatter_values[2])
        scatter_trace = release_and_read(frame, 3)

        assert [item["value"] for item in scatter_trace] == scatter_values
        assert [item["result"]["status"] for item in scatter_trace] == [
            "committed",
            "committed",
            "committed",
        ]
        assert [item["result"]["revision"] for item in scatter_trace] == [4, 5, 6]
        assert frame.evaluate(
            "() => window.dataviz.control.state('dashboard:chart-gallery/province').value"
        ) == [scatter_values[-1]]

        search = frame.locator('[data-view-id="records"] input.dv-table-search')
        expect(search).to_have_attribute("id", re.compile(r"^dataviz-view-records-search-\d+$"))


@pytest.mark.e2e
def test_multi_view_linked_brushing_preserves_writer_provenance_across_runtime(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "multi-view-writers", dashboards=('功能示例##chart-gallery',))
    report_path = tmp_path / "multi-view-writers.html"
    scenario = json.loads(
        (ROOT / "tests" / "fixtures" / "p1d-linked-brushing.json").read_text(encoding="utf-8")
    )
    control_key = scenario["use_case"]["control"]

    def dispatch(frame, action):
        return frame.locator("body").evaluate(
            """async (_body, item) => {
              const root = document.querySelector(
                `.dv-view[data-view-id="${CSS.escape(item.source_view)}"]`
              );
              const data = item.action === 'select_many'
                ? item.payload.map(value => ({__datavizControlValue:value}))
                : item.action === 'select'
                  ? {__datavizControlValue:item.payload}
                  : null;
              return window.dataviz.controlActions.dispatch({
                action_id:item.action_id,
                source_view:item.source_view,
                control:item.control,
                generation:root._datavizRenderGeneration,
                action:item.action,
                data,
              });
            }""",
            {**action, "control": control_key},
        )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "chart-gallery")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        for view_id in ("ranking", "scatter", "trend", "records"):
            expect(frame.locator(f'[data-view-id="{view_id}"]')).to_have_attribute(
                "data-view-status", "ready", timeout=20_000
            )

        for item in scenario["actions"]:
            response = dispatch(frame, item)
            expected = item["expected"]
            assert response == {
                "status": "committed",
                "revision": expected["revision"],
                "action_revision": expected["revision"],
                "action_id": item["action_id"],
                "source_view": item["source_view"],
            }
            observed = frame.locator("body").evaluate(
                """(_body, key) => ({
                  state:window.dataviz.control.state(key),
                  provenance:window.dataviz.control_writer_provenance[key],
                })""",
                control_key,
            )
            assert observed["state"] == {
                "value": expected["value"],
                "intent": expected["intent"],
                "revision": expected["revision"],
            }
            assert observed["provenance"] == {
                "revision": expected["revision"],
                "action_id": item["action_id"],
                "source_view": expected["last_source_view"],
                "action": item["action"],
            }

        stale = frame.locator("body").evaluate(
            """(_body, key) => window.dataviz.controlActions.dispatch({
              action_id:'ranking-stale-generation',
              source_view:'ranking',
              control:key,
              generation:0,
              action:'select',
              data:{__datavizControlValue:'广东'},
            })""",
            control_key,
        )
        assert stale == {
            "status": "rejected",
            "code": "stale_view_generation",
            "action_id": "ranking-stale-generation",
            "source_view": "ranking",
        }
        forged = frame.locator("body").evaluate(
            """(_body, key) => window.dataviz.controlActions.dispatch({
              action_id:'trend-forged-writer',
              source_view:'trend',
              control:key,
              generation:document.querySelector('[data-view-id="trend"]')
                ._datavizRenderGeneration,
              action:'select',
              data:{__datavizControlValue:'广东'},
            })""",
            control_key,
        )
        assert forged == {
            "status": "rejected",
            "code": "control_action_binding_invalid",
            "action_id": "trend-forged-writer",
            "source_view": "trend",
        }

        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        download_info.value.save_as(report_path)

        page.locator("#share-button").click()
        expect(page.locator("#copy-share-link")).to_be_visible()
        with page.expect_response(
            lambda response: response.url.endswith("/api/dashboards/chart-gallery/share"),
            timeout=30_000,
        ) as share_response:
            page.locator("#copy-share-link").click()
        shared = share_response.value.json()
        manifest = json.loads(
            (workspace / ".dataviz" / "results" / shared["result_id"] / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        result = manifest["result"]
        assert result["schema"] == "dataviz/analysis-result/v5"
        records_evidence = result["consumer_revisions"]["views"]["records"]
        assert records_evidence["applied_writer_provenance"][control_key] == {
            "revision": 4,
            "action_id": "scatter-reset",
            "source_view": "scatter",
            "action": "reset",
        }

    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}", wait_until="domcontentloaded")
        expect(page.locator('[data-view-id="ranking"]')).to_have_attribute(
            "data-view-status", "ready", timeout=20_000
        )
        response = dispatch(
            page,
            {
                "action_id": "ranking-portable-select",
                "source_view": "ranking",
                "action": "select",
                "payload": "广东",
            },
        )
        assert response["status"] == "committed"
        assert response["revision"] == 5
        snapshot = page.locator("body").evaluate(
            """(_body, key) => ({
              schema:window.dataviz.stateSnapshot().schema,
              state:window.dataviz.control.state(key),
              provenance:window.dataviz.control_writer_provenance[key],
              records:window.dataviz.stateSnapshot()
                .consumer_revisions.views.records.applied_writer_provenance[key],
            })""",
            control_key,
        )
        assert snapshot["schema"] == "dataviz/state-snapshot/v6"
        assert snapshot["state"]["value"] == ["广东"]
        assert (
            snapshot["provenance"]
            == snapshot["records"]
            == {
                "revision": 5,
                "action_id": "ranking-portable-select",
                "source_view": "ranking",
                "action": "select",
            }
        )
