from __future__ import annotations


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


from dataviz.protocols import DASHBOARD_SCHEMA


from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _build_scale_workspace,
    _open_single_fixture_dashboard,
    _open_dashboard,
    _run_and_wait,
    SHOWCASE,
    REPEAT,
)

@pytest.mark.e2e
def test_server_only_large_input_stays_out_of_browser(page: Page, tmp_path: Path):
    from dataviz.standalone import prepare_input

    path = tmp_path / "slice.yaml"
    path.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "slice",
        "sources": [{"id": "full", "type": "python", "code": {"inline":
            "def load(context):\n    return [{'value': i} for i in range(100001)]\n"},
            "outputs": {"main": {"kind": "table"}}}],
        "interactive_transforms": [{"id": "small", "runtime": "server-python",
            "code": {"inline": "def transform(context):\n    return {'main': context.table('rows').head(2)}\n"},
            "inputs": {"rows": "source:full/main"},
            "outputs": {"main": {"kind": "table"}}, "export": {"mode": "snapshot"}}],
        "views": [{"id": "result", "template": "table", "input": "interactive:small/main"}],
    }))
    root, _ = prepare_input(path)
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    with _running_server(root) as url:
        _open_single_fixture_dashboard(page, url, root)
        _run_and_wait(page)
        frame = page.frame_locator('#canvas-frame')
        expect(frame.locator('[data-view-id="result"] tbody tr')).to_have_count(2, timeout=30_000)
        payload = frame.locator('body').evaluate("""() => ({
          outputs:Object.keys(window.dataviz.portable.outputs),
          transports:Object.keys(window.dataviz.portable.output_transports),
          server:window.dataviz.portable.server_outputs,
        })""")
        assert 'source:full/main' not in payload['outputs']
        assert 'source:full/main' not in payload['transports']
        assert payload['server']['source:full/main']['row_count'] == 100001
        assert not any('/outputs/source' in url for url in requests)
        # Exercise the normal Shell reload / Run path with cached Source data.
        page.reload()
        _run_and_wait(page)
        expect(frame.locator('[data-view-id="result"] tbody tr')).to_have_count(2, timeout=30_000)
        assert frame.locator('body').evaluate("() => 'source:full/main' in window.dataviz.portable.outputs") is False
        assert not any('/outputs/source' in url for url in requests)


@pytest.mark.e2e
def test_query_multiple_select_summary_prefers_the_human_scale(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-summary")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "parameter-domain-lab")
        city = page.locator('select[name="cities"]')
        control = page.locator("#parameter-form .dv-control").filter(has=city)
        summary = control.locator("[data-control-summary]")

        def set_state(mode: str, total: int, operands: list[int]) -> None:
            page.evaluate(
                """({mode, total, operands}) => {
                  const input = document.querySelector('select[name="cities"]');
                  const selected = new Set(operands);
                  const options = Array.from({length: total}, (_, index) => {
                    const option = document.createElement('option');
                    option.value = String(index);
                    option.textContent = index === total - 1 ? 'final' : `model-${index + 1}`;
                    option.selected = selected.has(index);
                    return option;
                  });
                  input.replaceChildren(...options);
                  input.dataset.querySelection = mode;
                  input.dataset.queryUniverseTotal = String(total);
                  input._syncChoiceControl();
                }""",
                {"mode": mode, "total": total, "operands": operands},
            )

        set_state("exclude", 19, list(range(18)))
        expect(summary).to_have_text("final")

        set_state("include", 19, list(range(4)))
        expect(summary).to_have_text("已选 4 项")

        set_state("exclude", 100, [0, 1])
        expect(summary).to_have_text("全部，排除 2 项")


@pytest.mark.e2e
def test_arrow_transport_and_repeat_thousand_group_search_lazy_budget(page: Page, tmp_path: Path):
    workspace = _copy_workspace(REPEAT, tmp_path / "repeat")
    sql = workspace / "dashboards" / "store-performance" / "sources" / "store-sales.sql"
    sql.write_text(
        sql.read_text(encoding="utf-8").replace("range(1, 101)", "range(1, 1001)"), encoding="utf-8"
    )
    dashboard = workspace / "dashboards" / "store-performance" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard.read_text(encoding="utf-8"))
    definition["sections"][1]["repeat"]["limit"] = 1000
    all_store_view = next(item for item in definition["views"] if item["id"] == "all-store-trend")
    all_store_view["description"] = "每家门店共享同一份 Dataset。"
    dashboard.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "store-performance")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        host = frame.locator('[data-repeat-section="all-stores"]')
        expect(host).to_have_attribute("data-repeat-count", "1000", timeout=30_000)
        expect(host).to_have_attribute("data-repeat-rendered-cards", "40")
        expect(
            host.locator(":scope > .dv-repeat-card").first.locator(".dv-view-description")
        ).to_have_text("每家门店共享同一份 Dataset。")
        assert frame.locator("body").evaluate(
            """() => {
              const output = window.dataviz.portable.outputs['source:store-sales/main'];
              return output?.__datavizArrowOutput === true
                && window.datavizRuntime.metrics.transports.arrowRows === 12000;
            }"""
        )
        assert host.locator(":scope > .dv-repeat-card").count() == 40

        search = host.locator(".dv-repeat-search input")
        search.fill("S1000")
        expect(host).to_have_attribute("data-repeat-filtered-count", "1")
        expect(host.locator(":scope > .dv-repeat-card")).to_have_count(1)
        expect(host).to_contain_text("门店 1000")

        search.fill("")
        expect(host).to_have_attribute("data-repeat-rendered-cards", "40")
        host.locator("[data-repeat-more]").click()
        expect(host).to_have_attribute("data-repeat-rendered-cards", "80")
        performance = host.evaluate(
            """host => ({
              reconcileMs:Number(host.dataset.repeatReconcileMs),
              mounted:window.datavizRuntime.metrics.repeat.mounted,
              maxMounted:window.datavizRuntime.metrics.repeat.maxMounted,
              cards:Number(host.dataset.repeatRenderedCards),
            })"""
        )
        assert performance["reconcileMs"] < 750
        assert performance["mounted"] < performance["cards"]
        assert performance["maxMounted"] < performance["cards"]


@pytest.mark.e2e
def test_large_aggregations_do_not_cross_the_javascript_argument_limit(page: Page, tmp_path: Path):
    workspace = _build_scale_workspace(tmp_path / "scale")
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "scale")
        _run_and_wait(page)
        frame = page.frame_locator("#canvas-frame")
        source = frame.locator('[data-view-id="source-maximum"]')
        worker = frame.locator('[data-view-id="worker-maximum"]')
        expect(source).to_have_attribute("data-view-status", "ready", timeout=30_000)
        expect(worker).to_have_attribute("data-view-status", "ready", timeout=30_000)
        expect(source).to_contain_text("150,000")
        expect(worker).to_contain_text("150,000")

        # Custom Canvas authors receive the same safe aggregation primitive.
        custom_peak = frame.locator("body").evaluate(
            """() => window.dataviz.data.frame(
              Array.from({length:150000}, (_, index) => ({bucket:0, value:index + 1}))
            ).groupBy('bucket').aggregate({
              peak:{field:'value', op:'max'},
            }).rows()[0].peak"""
        )
        assert custom_peak == 150_000
        runtime_metrics = frame.locator("body").evaluate(
            """() => ({
              arrowRows:window.datavizRuntime.metrics.transports.arrowRows,
              arrowBytes:window.datavizRuntime.metrics.transports.arrowBytes,
              rendererFailures:window.datavizRuntime.metrics.renderers.failed,
            })"""
        )
        assert runtime_metrics["arrowRows"] == 150_000
        assert runtime_metrics["arrowBytes"] > 0
        assert runtime_metrics["rendererFailures"] == 0

        # A renderer with no descriptor is a terminal empty state, not an
        # infinite "rendering" state.
        frame.locator("body").evaluate(
            "() => window.dataviz.renderView('source-maximum', () => null)"
        )
        expect(source).to_have_attribute("data-view-status", "empty")
        expect(source).to_contain_text("No data")

