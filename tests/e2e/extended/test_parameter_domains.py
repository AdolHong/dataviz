from __future__ import annotations


import re

import shutil


import sqlite3


import time




from pathlib import Path



import pytest



from playwright.sync_api import (
    Page,
    expect,
)


from dataviz.execution.parameter_materializations import ParameterMaterializationStore

import dataviz.execution.parameter_materializations as parameter_materializations

from dataviz.errors import ExecutionFailure


from dataviz.workspace import load_workspace

from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _open_dashboard,
    _run_and_wait,
    _export_html,
    SHOWCASE,
)

@pytest.mark.e2e
def test_parameter_lookup_does_not_reconcile_a_new_selection_with_old_operands(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / 'lookup-selection-race')
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, 'parameter-domain-lab')
        city = page.locator('select[name="cities"]')
        expect(city.locator('option')).to_have_count(2, timeout=20_000)
        control = page.locator('#parameter-form .dv-control').filter(has=city)
        control.locator('[data-control-trigger]').click()
        expect(control).to_have_attribute('aria-busy', 'false')
        pending = []
        def delay(route):
            if route.request.post_data_json.get('parameter') == 'cities' and not pending:
                pending.append(route)
            else:
                route.continue_()
        page.route('**/parameter-domains/lookup', delay)
        with page.expect_request(lambda request: '/parameter-domains/lookup' in request.url
                                 and request.post_data_json.get('parameter') == 'cities'):
            city.evaluate("input => { void input._remoteLookup({search:''}); }")
        expect(control).to_have_attribute('aria-busy', 'true')
        control.get_by_role('button', name='Clear', exact=True).click()
        control.locator('.dv-choice-option', has_text='深圳').click()
        expect(city).to_have_values(['SZ'])
        expect(city).to_have_attribute('data-query-selection', 'include')
        assert pending, 'City lookup must be held before editing'
        route = pending[0]
        route.fulfill(response=route.fetch())
        expect(control).to_have_attribute('aria-busy', 'false', timeout=20_000)
        expect(city).to_have_values(['SZ'])
        expect(city).to_have_attribute('data-query-selection', 'include')


@pytest.mark.e2e
def test_parameter_domain_cascade_reload_and_tab_restore(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain")
    with _running_server(workspace) as base_url:
        domain_requests: list[str] = []
        page.on(
            "request",
            lambda request: (
                domain_requests.append(request.url)
                if "/parameter-domains/lookup" in request.url
                else None
            ),
        )
        _open_dashboard(page, base_url, "parameter-domain-lab")
        reload_options = page.locator("#query-parameter-options-reload")
        province = page.locator('select[name="provinces"]')
        city = page.locator('select[name="cities"]')

        expect(reload_options).to_be_visible()
        expect(province).to_have_values(["GD"])
        expect(city.locator("option")).to_have_count(2, timeout=20_000)
        expect(city).to_have_values([])
        assert len(domain_requests) >= 2
        city_control = page.locator("#parameter-form .dv-control").filter(has=city)
        expect(city_control.locator("[data-control-summary]")).to_have_text("全部")

        _run_and_wait(page)
        expect(page.locator("#query-parameters-panel")).to_be_visible()
        expect(page.locator("#query-parameters-status")).to_have_text("Applied")
        remembered = page.evaluate(
            """async () => {
              const sessionId = sessionStorage.getItem('dataviz.tab-session.v2');
              const response = await fetch(`/api/session/runs?session_id=${encodeURIComponent(sessionId)}`);
              return response.json();
            }"""
        )
        initial_run = next(
            item for item in remembered["runs"] if item["dashboard_id"] == "parameter-domain-lab"
        )
        assert initial_run["query_parameter_state"] == {
            "provinces": {"selection": "include", "value": ["GD"]},
            "cities": {"selection": "all", "value": []},
        }
        committed_run_id = page.locator("#canvas-frame").get_attribute("data-run-id")

        # Compact all/exclude state is part of the committed snapshot. Deselecting
        # one visible member stores only that exception; Revert restores all
        # without enumerating the candidate generation or rerunning Query.
        city_trigger = city_control.locator("[data-control-trigger]")
        city_trigger.click()
        city_control.locator(".dv-choice-option", has_text="广州").click()
        expect(city_control.locator("[data-control-summary]")).to_have_text("深圳")
        revert = page.locator("#query-parameters-revert")
        expect(page.locator("#query-control-meta")).to_have_text("Unsaved changes")
        expect(revert).to_be_visible()
        revert.click()
        expect(page.locator("#query-control-meta")).to_have_text("Applied")
        expect(revert).to_be_hidden()
        expect(city_control.locator("[data-control-summary]")).to_have_text("全部")
        assert page.locator("#canvas-frame").get_attribute("data-run-id") == committed_run_id

        # A normal parent edit coordinates the child draft. An old operand
        # that is invalid in the new parent range must not be merged back into
        # the visible options as an unavailable pseudo-candidate. Revert is the
        # only path that deliberately preserves unavailable committed values.
        city_trigger.click()
        city_control.get_by_role("button", name="Clear").click()
        city_control.locator(".dv-choice-option", has_text="深圳").click()
        expect(city).to_have_values(["SZ"])

        # Parent changes issue local Lookup predicates against the same immutable
        # materialization generation. The visible custom controls remain usable.
        province_control = page.locator("#parameter-form .dv-control").filter(has=province)
        province_trigger = province_control.locator("[data-control-trigger]")
        expect(province_trigger).to_be_enabled()
        province_trigger.click()
        province_control.locator(".dv-choice-option", has_text="湖南").click()
        expect(province).to_have_values(["GD", "HN"])

        province.select_option(["HN"], force=True)
        expect(city.locator("option")).to_have_count(1, timeout=10_000)
        expect(city.locator("option")).to_have_text(["长沙"])
        expect(city.locator('option[data-unavailable="true"]')).to_have_count(0)
        expect(city).to_have_values([])
        expect(city).to_have_attribute("data-query-selection", "all")
        expect(page.locator("#run-button")).to_be_enabled()

        # Revert restores the parent then rehydrates the child atomically from
        # the current generation; it does not execute the analytical Query.
        expect(revert).to_be_visible()
        revert.click()
        expect(province).to_have_values(["GD"], timeout=10_000)
        expect(city.locator("option")).to_have_count(2, timeout=10_000)
        expect(city).to_have_values([])
        expect(page.locator("#query-control-meta")).to_have_text("Applied")
        assert page.locator("#canvas-frame").get_attribute("data-run-id") == committed_run_id

        requests_before_reload = len(domain_requests)
        reload_options.click()
        expect(reload_options).to_be_enabled(timeout=10_000)
        expect(city).to_have_values([])
        assert len(domain_requests) > requests_before_reload

        # A full page reload restores the exact compact draft before Domain
        # hydration. Lookup only supplies the selected label/availability; it
        # must not reinterpret restoration as a fresh parent edit and erase the
        # finite operand.
        city_trigger.click()
        city_control.get_by_role("button", name="Clear").click()
        city_control.locator(".dv-choice-option", has_text="深圳").click()
        expect(city).to_have_values(["SZ"])
        expect(city).to_have_attribute("data-query-selection", "include")
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)
        expect(province).to_have_values(["GD"])
        expect(city.locator("option")).to_have_count(2, timeout=20_000)
        expect(city).to_have_values(["SZ"])
        expect(city).to_have_attribute("data-query-selection", "include")

        _run_and_wait(page)
        with page.expect_download(timeout=20_000) as download_info:
            _export_html(page)
        report = Path(download_info.value.path()).read_text(encoding="utf-8")
        assert "parameter-domains/lookup" not in report
        assert "locations.sql" not in report
        assert '"provinces": {"selection": "include", "value": ["GD"]}' in report
        assert '"cities": {"selection": "include", "value": ["SZ"]}' in report


@pytest.mark.e2e
def test_parameter_domain_lookup_search_and_cursor_pagination(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-pagination")
    dashboard_root = workspace / "dashboards" / "功能示例##parameter-domain-lab"
    domain_path = dashboard_root / "parameter_domains" / "locations.yaml"
    domain_path.write_text(
        domain_path.read_text(encoding="utf-8").replace("max_rows: 100", "max_rows: 700"),
        encoding="utf-8",
    )
    rows = ",\n".join(
        f"  ('GD', '广东', 1, 'C{index:03d}', '城市 {index:03d}', {index})"
        for index in range(1, 621)
    )
    (dashboard_root / "parameter_domains" / "locations.sql").write_text(
        "select * from (values\n"
        + rows
        + "\n) as locations("
        "province_code, province_name, province_order, city_code, city_name, city_order)\n",
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        requests = []
        ready_responses: list[dict] = []

        def record_request(request):
            if "/parameter-domains/lookup" in request.url:
                requests.append(request)

        def record_response(response):
            if "/parameter-domains/lookup" not in response.url or response.status != 200:
                return
            payload = response.json()
            if payload.get("status") == "ready":
                ready_responses.append(payload)

        page.on("request", record_request)
        page.on("response", record_response)
        _open_dashboard(page, base_url, "parameter-domain-lab")
        city = page.locator('select[name="cities"]')
        expect(city.locator("option")).to_have_count(500, timeout=20_000)
        city_control = page.locator("#parameter-form .dv-control").filter(has=city)
        city_control.locator("[data-control-trigger]").click()
        search = city_control.locator(".dv-choice-search")
        expect(city_control.locator(".dv-select-options")).not_to_have_class(
            re.compile(r"\bis-virtual\b")
        )

        # This member is outside the first page, so finding it proves that the
        # Picker used remote Lookup search rather than filtering only loaded DOM.
        search.fill("城市 619")
        expect(city_control.locator(".dv-choice-option")).to_have_count(1, timeout=10_000)
        expect(city_control.locator(".dv-choice-option")).to_contain_text("城市 619")
        expect(city_control.locator("[data-control-trigger]")).to_have_attribute(
            "aria-expanded", "true"
        )
        expect(city_control.locator(".dv-select-panel")).to_be_visible()
        expect(search).to_be_focused()

        # A realistic broad CJK lookup returns multiple rows rather than one
        # exact hit. The open Top Layer must consume the same option generation
        # as the native Select without a close/reopen cycle.
        search.fill("城市 6")
        expect(city.locator("option")).to_have_count(135, timeout=10_000)
        expect(city_control.locator(".dv-choice-option")).to_have_count(135)
        native_labels = city.locator("option").all_text_contents()
        visible_labels = city_control.locator(
            ".dv-choice-option .dv-select-option__copy strong"
        ).all_text_contents()
        assert visible_labels == native_labels
        expect(city_control.locator("[data-control-trigger]")).to_have_attribute(
            "aria-expanded", "true"
        )
        expect(city_control.locator(".dv-select-panel")).to_be_visible()
        expect(search).to_be_focused()

        # Real Chinese text entry uses an IME composition lifecycle. Remote
        # Lookup must not rebuild the open picker for an intermediate composing
        # value; it runs after compositionend and paints the committed result
        # without requiring the user to close and reopen the Select.
        requests_before_composition = len(requests)
        search.dispatch_event("compositionstart", {"data": ""})
        search.evaluate(
            """node => {
              node.value = '城市 618';
              node.dispatchEvent(new InputEvent('input', {
                bubbles: true,
                data: '城市 618',
                inputType: 'insertCompositionText',
                isComposing: true,
              }));
            }"""
        )
        page.wait_for_timeout(300)
        assert len(requests) == requests_before_composition
        search.dispatch_event("compositionend", {"data": "城市 618"})
        expect(city_control.locator(".dv-choice-option")).to_have_count(1, timeout=10_000)
        expect(city_control.locator(".dv-choice-option")).to_contain_text("城市 618")
        expect(city_control.locator("[data-control-trigger]")).to_have_attribute(
            "aria-expanded", "true"
        )
        expect(city_control.locator(".dv-select-panel")).to_be_visible()
        expect(search).to_be_focused()

        search.fill("")
        expect(city.locator("option")).to_have_count(500, timeout=10_000)
        viewport = city_control.locator(".dv-select-options")
        viewport.evaluate(
            "node => { node.scrollTop = node.scrollHeight; node.dispatchEvent(new Event('scroll')); }"
        )
        expect(city.locator("option")).to_have_count(620, timeout=10_000)

        payloads = [request.post_data_json for request in requests if request.post_data]
        assert any(payload.get("search") == "城市 619" for payload in payloads)
        assert any(payload.get("search") == "城市 618" for payload in payloads)
        assert any(payload.get("search") == "城市 6" for payload in payloads)
        assert all(payload.get("limit") == 500 for payload in payloads)
        assert any(payload.get("cursor") for payload in payloads)
        assert all("sql" not in payload and "adapter" not in payload for payload in payloads)
        generations = {payload["generation"] for payload in ready_responses}
        assert len(generations) == 1

        # Search-scoped actions preserve the compact all/exclude semantics and
        # exceptions outside the current server-side matching domain.
        search.fill("城市 619")
        clear_results = city_control.get_by_role("button", name="Clear results", exact=True)
        expect(clear_results).to_be_enabled()
        clear_results.click()
        expect(city).to_have_attribute("data-query-selection", "exclude")
        expect(city).to_have_values(["C619"])
        search.fill("城市 618")
        expect(city_control.locator(".dv-choice-option")).to_have_count(1)
        expect(clear_results).to_be_enabled()
        clear_results.click()
        expect(city).to_have_values(["C619", "C618"])
        city_control.get_by_role("button", name="Select results", exact=True).click()
        expect(city).to_have_values(["C619"])
        search.fill("")
        city_control.get_by_role("button", name="Clear", exact=True).click()
        expect(city).to_have_attribute("data-query-selection", "none")
        search.fill("城市 619")
        select_results = city_control.get_by_role("button", name="Select results", exact=True)
        expect(select_results).to_be_enabled()
        select_results.click()
        expect(city).to_have_attribute("data-query-selection", "include")
        expect(city).to_have_values(["C619"])


@pytest.mark.e2e
def test_remote_lookup_late_failure_cannot_replace_newer_success(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-late-failure")
    dashboard_root = workspace / "dashboards" / "功能示例##parameter-domain-lab"
    domain_path = dashboard_root / "parameter_domains" / "locations.yaml"
    domain_path.write_text(
        domain_path.read_text(encoding="utf-8").replace("max_rows: 100", "max_rows: 700"),
        encoding="utf-8",
    )
    rows = ",\n".join(
        f"  ('GD', '广东', 1, 'C{index:03d}', '城市 {index:03d}', {index})"
        for index in range(1, 621)
    )
    (dashboard_root / "parameter_domains" / "locations.sql").write_text(
        "select * from (values\n"
        + rows
        + "\n) as locations("
        "province_code, province_name, province_order, city_code, city_name, city_order)\n",
        encoding="utf-8",
    )
    page.add_init_script(
        """(() => {
          const nativeFetch = window.fetch.bind(window);
          window.__datavizLookupSearches = [];
          window.fetch = async (input, init = {}) => {
            const url = String(input);
            let search = null;
            if (url.includes('/parameter-domains/lookup') && init.body) {
              search = JSON.parse(init.body).search;
              window.__datavizLookupSearches.push(search);
            }
            const response = await nativeFetch(input, init);
            if (search === '城市 61') {
              await new Promise(resolve => { window.__releaseOldLookup = resolve; });
              throw new Error('simulated late lookup failure');
            }
            return response;
          };
        })();"""
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "parameter-domain-lab")
        city = page.locator('select[name="cities"]')
        expect(city.locator("option")).to_have_count(500, timeout=20_000)
        control = page.locator("#parameter-form .dv-control").filter(has=city)
        control.locator("[data-control-trigger]").click()
        search = control.locator(".dv-choice-search")

        search.fill("城市 61")
        page.wait_for_function(
            "window.__datavizLookupSearches.includes('城市 61')"
        )
        search.fill("城市 619")
        expect(control.locator(".dv-choice-option", has_text="城市 619")).to_have_count(
            1, timeout=10_000
        )
        # Release the obsolete failure only after the newer success is visible;
        # a fixed delay races slow CI machines and needlessly stalls fast ones.
        page.wait_for_function("typeof window.__releaseOldLookup === 'function'")
        page.evaluate("() => window.__releaseOldLookup()")
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        expect(control.locator(".dv-choice-option", has_text="城市 619")).to_have_count(1)
        expect(control).to_have_attribute("aria-busy", "false")

        page.locator("#query-parameter-author-mode").click()
        evidence = page.locator('[data-query-parameter-evidence="cities"]')
        expect(evidence).to_contain_text("lookup=ready")
        expect(evidence).to_contain_text("request_ms=")
        expect(evidence).to_contain_text("visible_refresh_ms=")
        expect(page.locator('[data-query-parameter-evidence-copy="cities"]')).to_be_visible()


@pytest.mark.e2e
def test_parameter_domain_failure_does_not_trap_dashboard_navigation(page: Page, tmp_path: Path):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-failure")
    domain_sql = (
        workspace
        / "dashboards"
        / "功能示例##parameter-domain-lab"
        / "parameter_domains"
        / "locations.sql"
    )
    domain_sql.write_text("select * from missing_parameter_domain_table", encoding="utf-8")

    with _running_server(workspace) as base_url:
        page.goto(
            f"{base_url}/dashboards/parameter-domain-lab",
            wait_until="domcontentloaded",
        )
        # Candidate failure does not invalidate a canonical all/include state;
        # users who already know the value may still run the analytical Query.
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)

        # A reload may retry the broken Domain, but it must not make the Shell
        # or another Dashboard unreachable.
        page.reload(wait_until="domcontentloaded")
        target = page.locator('[data-nav-type="dashboard"][data-id="chart-gallery"]')
        expect(target).to_be_visible(timeout=10_000)
        target.click()
        expect(target).to_have_class(re.compile(r"\bactive\b"))
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)
        expect(page).to_have_url(re.compile(r"/dashboards/chart-gallery"))


@pytest.mark.e2e
def test_parameter_domain_generation_is_scoped_per_dashboard(
    page: Page, tmp_path: Path
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-scoped")
    original = workspace / "dashboards" / "功能示例##parameter-domain-lab"
    copied = workspace / "dashboards" / "功能示例##parameter-domain-lab-copy"
    shutil.copytree(original, copied)
    copied_dashboard = copied / "dashboard.yaml"
    copied_dashboard.write_text(
        copied_dashboard.read_text(encoding="utf-8").replace(
            "id: parameter-domain-lab", "id: parameter-domain-lab-copy", 1
        ),
        encoding="utf-8",
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "parameter-domain-lab")
        expect(page.locator('select[name="cities"] option')).to_have_count(2, timeout=20_000)
        second_context = page.context.browser.new_context(viewport={"width": 1440, "height": 900})
        second_page = second_context.new_page()
        try:
            _open_dashboard(second_page, base_url, "parameter-domain-lab-copy")
            expect(second_page.locator('select[name="cities"] option')).to_have_count(
                2, timeout=20_000
            )
            index = workspace / ".dataviz" / "parameter-materializations" / "index.sqlite"
            with sqlite3.connect(index) as connection:
                rows = connection.execute(
                    "SELECT generation, status FROM materializations"
                ).fetchall()
            assert len(rows) == 2
            assert all(generation and status == "ready" for generation, status in rows)
        finally:
            second_context.close()


@pytest.mark.e2e
def test_hard_expired_parameter_domain_disables_only_its_pickers(
    page: Page, tmp_path: Path, monkeypatch
):
    workspace = _copy_workspace(SHOWCASE, tmp_path / "parameter-domain-expired")
    loaded = load_workspace(workspace)
    dashboard = loaded.dashboard("parameter-domain-lab")
    store = ParameterMaterializationStore(loaded)
    record = store.build(dashboard, "locations")
    with sqlite3.connect(store.index_path) as connection:
        connection.execute(
            "UPDATE materializations SET refresh_due_at=?, expires_at=? "
            "WHERE materialization_key=?",
            (time.time() - 2, time.time() - 1, record.key),
        )

    def fail_rebuild(**_kwargs):
        raise ExecutionFailure(
            "benchmark warehouse unavailable",
            details={"code": "parameter_materialization_test_failure"},
        )

    monkeypatch.setattr(parameter_materializations, "execute_sql_query", fail_rebuild)
    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "parameter-domain-lab")
        province = page.locator('select[name="provinces"]')
        city = page.locator('select[name="cities"]')
        expect(province).to_be_disabled(timeout=20_000)
        expect(city).to_be_disabled(timeout=20_000)
        expect(city.locator("option")).to_have_count(0)
        expect(page.locator("#run-button")).to_be_enabled()
        expect(
            page.locator('[data-nav-type="dashboard"][data-id="chart-gallery"]')
        ).to_be_visible()
