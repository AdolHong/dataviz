from __future__ import annotations


import sqlite3


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


from dataviz.execution import Executor


from dataviz.protocols import DASHBOARD_SCHEMA

from dataviz.rendering import CanvasRenderer

from dataviz.workspace import load_workspace

from e2e.support.runtime import (
    _running_server,
    _running_static_server,
    _open_single_fixture_dashboard,
    _run_and_wait,
)

@pytest.mark.e2e
def test_shared_action_marks_sibling_page_without_querying(page: Page, tmp_path: Path):
    from dataviz.standalone import prepare_input

    database = tmp_path / "shared.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("create table labels (value integer)")
        connection.execute("insert into labels values (1)")
    auth = tmp_path / "auth.yaml"
    auth.write_text(yaml.safe_dump({"adapters": {"db": {"type": "sqlalchemy", "url": f"sqlite:///{database}"}}}))
    source = tmp_path / "review.yaml"
    source.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "review", "title": "Review",
        "sources": [{"id": name, "type": "sql", "adapter": "db", "code": {"inline": sql},
                     "outputs": {"main": {"kind": "table"}}}
                    for name, sql in [("labels", "select value from labels"), ("sales", "select 42 as value")]],
        "server_actions": [{"id": "save", "resources": {"db": "db"}, "invalidates": ["source:labels"],
                            "code": {"inline": '''
from sqlalchemy import create_engine, text
def execute(context):
    import time
    time.sleep(context.payload.get('delay', 0))
    engine = create_engine(context.resources.config('db')['url'])
    try:
        with engine.begin() as connection:
            connection.execute(text('update labels set value=value+1'))
        context.invalidate('source:labels')
        return {'saved': True}
    finally:
        engine.dispose()
'''}}],
        "pages": [{"id": name, "title": name, "server_actions": ["save"] if name == "edit" else [],
                   "views": [{"id": "value", "template": "custom", "renderer": "review.value",
                              "input": f"source:{'sales' if name == 'isolated' else 'labels'}/main"}]}
                  for name in ["edit", "history", "isolated"]],
        "canvas": {"scripts": [{"inline": '''
window.datavizRuntime.registerRenderer('review.value', {
  mount(context, descriptor) {
    const value = document.createElement('output'); value.className = 'review-value';
    const feedback = document.createElement('output'); feedback.className = 'review-feedback';
    const save = document.createElement('button'); save.textContent = 'Save';
    save.disabled = !context.actions.available;
    save.onclick = async () => {
      try { await context.actions.invoke('save', {}); feedback.textContent = 'Saved'; }
      catch (error) { feedback.textContent = error.message; }
    };
    value.textContent = descriptor.rows[0]?.value;
    context.body.append(value, save, feedback);
    return {value};
  },
  update(context, descriptor, state) { state.value.textContent = descriptor.rows[0]?.value; return state; },
  dispose() {},
});
'''}]},
    }))
    root, _ = prepare_input(source, auth=auth)
    queries = []
    writes = []
    page.on("request", lambda request: queries.append(request.post_data_json)
            if request.method == "POST" and request.url.endswith("/runs") else None)
    page.on("request", lambda request: writes.append(request.post_data_json)
            if request.method == "POST" and "/actions/save" in request.url else None)
    with _running_server(root, watch=False) as url:
        _open_single_fixture_dashboard(page, url, root)
        frame = page.frame_locator("#canvas-frame")
        tab = lambda name: page.locator(f'#page-navigation-list button[data-page-id="{name}"]')
        for name in ["edit", "history", "isolated"]:
            tab(name).click()
            _run_and_wait(page)
            assert queries[-1]["page_id"] == name
            expect(frame.locator('.review-value')).to_have_text("42" if name == "isolated" else "1", timeout=30_000)
        tab("edit").click()
        expect(frame.get_by_role("button", name="Save", exact=True)).to_be_enabled(timeout=15_000)
        frame.get_by_role("button", name="Save", exact=True).click()
        expect(frame.locator('.review-feedback')).to_have_text("Saved", timeout=30_000)
        expect(frame.locator('.review-value')).to_have_text("2")
        expect(tab("history")).to_contain_text("Data changed", timeout=10_000)
        expect(tab("isolated")).not_to_contain_text("Data changed")
        expect(tab("edit")).not_to_contain_text("Data changed")
        assert len(queries) == 3 and len(writes) == 1
        with sqlite3.connect(database) as connection:
            assert connection.execute("select value from labels").fetchone()[0] == 2
        tab("history").click()
        expect(frame.locator('.review-value')).to_have_text("1", timeout=15_000)
        expect(page.locator('#workspace-update-title')).to_have_text("Shared data changed")
        assert len(queries) == 3
        page.reload()
        expect(tab("history")).to_contain_text("Data changed", timeout=15_000)
        # Resolve the current iframe document after top-level navigation. Firefox
        # can paint the restored frame before its old FrameLocator target is
        # reattached; the value/no-query assertion must not depend on that target.
        page.wait_for_function("""() => document.querySelector('#canvas-frame')
          ?.contentDocument?.querySelector('.review-value')?.textContent === '1'""", timeout=15_000)
        frame = page.frame_locator('#canvas-frame')
        page.locator('#workspace-update-action').click()
        expect(frame.locator('.review-value')).to_have_text("2", timeout=30_000)
        expect(tab("history")).not_to_contain_text("Data changed")
        expect(page.locator('#workspace-update')).to_be_hidden()
        assert len(queries) == 4 and len(writes) == 1

        # A write already submitted may finish after navigation; a second
        # queued write must never be retargeted to the newly selected Page.
        tab("edit").click()
        expect(frame.get_by_role("button", name="Save", exact=True)).to_be_enabled(timeout=15_000)
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/actions/save")):
            with page.expect_request(lambda request: request.method == "POST" and request.url.endswith("/actions/save")) as first_write:
                frame.locator('body').evaluate("""() => {
                  window.dataviz.serverActions.invoke('save', {delay:1}, {requestId:'leaving-first'}).catch(() => {});
                  window.dataviz.serverActions.invoke('save', {}, {requestId:'leaving-second'}).catch(() => {});
                }""")
            tab("isolated").click()
            expect(tab("isolated")).to_have_attribute("aria-current", "page")
        expect(frame.locator('.review-value')).to_have_text("42", timeout=15_000)
        expect(tab("history")).to_contain_text("Data changed", timeout=10_000)
        assert len(writes) == 2 and writes[-1]["request_id"] == "leaving-first"
        assert len(queries) == 4
        session_id = first_write.value.post_data_json["session_id"]
        not_sent = page.request.get(f"{url}/api/dashboards/review/actions/save/leaving-second", params={"session_id": session_id})
        assert not_sent.status == 404
        with sqlite3.connect(database) as connection:
            assert connection.execute("select value from labels").fetchone()[0] == 3


@pytest.mark.e2e
def test_analysis_stability_workflow(page: Page, stable_analysis):
    root, database = stable_analysis
    requests = []
    page.on('request', lambda request: requests.append((request.method, request.url)))
    with _running_server(root) as url:
        _open_single_fixture_dashboard(page, url, root)
        _run_and_wait(page)
        frame = page.frame_locator('#canvas-frame')
        table = frame.locator('[data-view-id="items"]')
        chart = frame.locator('[data-view-id="detail"] .dv-plotly')

        def category(value):
            frame.locator('body').evaluate("""async (_body, value) => {
              window.dataviz.control.set('dashboard:stability/category', value);
              await window.dataviz.applyControls({keys:['dashboard:stability/category']});
            }""", value)

        for c in ['A', 'B', 'A']:
            category(c)
            expect(table.locator('tbody tr')).to_have_count(3, timeout=30_000)
            for item in [f'{c}{n}' for n in range(1, 4)]:
                row = table.locator('tbody tr').filter(has_text=item)
                row.click()
                expect(row).to_have_attribute('aria-selected', 'true')
                expect(chart).to_be_visible()
                next(item for item in page.frames if '/canvas?' in item.url).wait_for_function(
                    "item => JSON.stringify(document.querySelector('[data-view-id=\"detail\"] .dv-plotly')?.data?.[0]?.x) === JSON.stringify([item])",
                    arg=item,
                )
                assert chart.evaluate('node => node.data[0].x') == [item]
                assert frame.locator('body').evaluate("() => window.dataviz.control.state('dashboard:stability/item').value") == item

        editor = frame.locator('[data-view-id="editor"]')
        editor.get_by_label('Manual label').select_option('sensitive')
        editor.get_by_role('button', name='Save', exact=True).click()
        expect(editor).to_contain_text('Saved; page synced', timeout=30_000)
        with sqlite3.connect(database) as db:
            assert db.execute("select label, revision from annotations where id='A3'").fetchone() == ('sensitive', 1)
        # No new Query request for any of the local selection commits or writeback.
        assert len([url for method, url in requests if method == 'POST' and '/dashboards/stability/runs' in url]) == 1
        assert not any('/outputs/source%3Afacts' in url for _, url in requests)
        category('EMPTY')
        expect(table.locator('tbody tr')).to_have_count(0)
        assert frame.locator('body').evaluate("() => window.dataviz.control.state('dashboard:stability/item').value") is None
        category('FAIL')
        expect(table).to_have_attribute('data-view-status', 'error', timeout=30_000)
        category('B')
        expect(table.locator('tbody tr')).to_have_count(3, timeout=30_000)
        frame.locator('body').evaluate("""async () => {
          window.dataviz.control.set('dashboard:stability/item', null);
          await window.dataviz.applyControls({keys:['dashboard:stability/item']});
        }""")
        assert frame.locator('body').evaluate("() => window.dataviz.control.state('dashboard:stability/item').value") is None
        assert table.locator('tbody tr[aria-selected="true"]').count() == 0
        # Rapid commits: only the final canonical state may reach the views.
        frame.locator('body').evaluate("""async () => {
          const key = 'dashboard:stability/category';
          const jobs = ['A','B','A'].map(value => {
            window.dataviz.control.set(key, value);
            return window.dataviz.applyControls({keys:[key]});
          });
          await Promise.all(jobs);
        }""")
        expect(table.locator('tbody tr').first).to_contain_text('A1', timeout=30_000)
        # Reload exactly the same Run, retaining server-side generation guards.
        canvas = next(item for item in page.frames if '/canvas?' in item.url)
        canvas.goto(canvas.url)
        expect(table).to_have_attribute('data-view-status', 'ready', timeout=30_000)
        assert not any('/outputs/source%3Afacts' in url for _, url in requests)


@pytest.mark.e2e
@pytest.mark.parametrize("transport", ["json", "arrow"])
def test_server_action_updates_canvas_in_place_and_preserves_query_draft(page: Page, tmp_path: Path, transport):
    from dataviz.standalone import prepare_input

    database = tmp_path / "facts.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("create table facts (value integer)")
        connection.execute("insert into facts values (1)")
    auth = tmp_path / "connections.yaml"
    auth.write_text(yaml.safe_dump({"adapters": {"db": {
        "type": "sqlalchemy", "url": f"sqlite:///{database}",
    }}}))
    source = tmp_path / "actions.yaml"
    source.write_text(yaml.safe_dump({
        "schema": DASHBOARD_SCHEMA, "id": "action-demo",
        "query_parameters": [{"id": "label", "type": "single_input", "value_type": "text", "default": "applied"}],
        "sources": [
            {"id": "labels", "type": "sql", "adapter": "db",
             "code": {"inline": "select value from facts where :label = 'applied'"},
             "query_inputs": {"label": "label"}, "outputs": {"main": {"kind": "table"}}},
            {"id": "sales", "type": "sql", "adapter": "db", "code": {"inline": "select 42 as value"},
             "outputs": {"main": {"kind": "table"}}},
        ],
        "interactive_transforms": [{"id": "double", "runtime": "browser-js",
            "code": {"inline": "function transform(context) { return {main: context.inputs.rows.map(row => ({value: row.value * 10}))}; }"},
            "inputs": {"rows": "source:labels/main"}, "outputs": {"main": {"kind": "table"}},
            "export": {"mode": "interactive"}}],
        "server_actions": [{"id": "save", "resources": {"db": "db"},
            "invalidates": ["source:labels", "view:sales"], "code": {"inline": '''
from sqlalchemy import create_engine, text
def execute(context):
    if context.payload.get("view_only"):
        context.invalidate("view:sales")
        return {"saved": False}
    engine = create_engine(context.resources.config("db")["url"])
    try:
        with engine.begin() as connection:
            connection.execute(text("update facts set value=value+1"))
    finally:
        engine.dispose()
    context.invalidate("source:labels")
    return {"saved": True}
'''}}],
        "views": [{"id": name, "template": "custom", "renderer": "action.demo", "input": f"source:{name}/main"}
                  for name in ["labels", "sales"]] + [{"id": "summary", "template": "metric", "value": "value", "input": "interactive:double/main"}],
        "canvas": {"scripts": [{"inline": '''
window.actionMounts = {};
window.actionUpdates = {};
window.datavizRuntime.registerRenderer('action.demo', {
  mount(context, descriptor) {
    window.actionMounts[context.key] = (window.actionMounts[context.key] || 0) + 1;
    const value = document.createElement('span');
    value.className = 'action-value';
    value.textContent = String(descriptor.rows[0]?.value ?? 'empty');
    const feedback = document.createElement('output');
    feedback.className = 'action-feedback';
    context.body.append(value, feedback);
    if (context.key === 'labels') {
      const save = document.createElement('button');
      save.textContent = 'Save annotation';
      save.disabled = !context.actions.available;
      const retry = document.createElement('button');
      retry.textContent = 'Retry refresh';
      retry.hidden = true;
      let failedRequestId = null;
      retry.onclick = async () => {
        retry.disabled = true;
        try {
          window.lastActionReceipt = await context.actions.refresh('save', failedRequestId);
          feedback.textContent = 'Saved';
          retry.hidden = true;
        } catch (error) { feedback.textContent = 'Saved; refresh failed'; }
        finally { retry.disabled = false; }
      };
      save.onclick = async () => {
        save.disabled = true;
        feedback.textContent = 'Saving';
        try {
          window.lastActionReceipt = await context.actions.invoke('save', {});
          feedback.textContent = 'Saved';
        } catch (error) {
          window.lastActionError = {message:error.message, code:error.code, receipt:error.receipt};
          if (error.receipt?.status === 'succeeded') {
            feedback.textContent = 'Saved; refresh failed';
            failedRequestId = error.requestId;
            retry.hidden = false;
          } else feedback.textContent = 'Failed: ' + error.message;
        } finally { save.disabled = !context.actions.available; }
      };
      context.body.append(save, retry);
    }
    return {value, feedback};
  },
  update(context, descriptor, state) {
    window.actionUpdates[context.key] = (window.actionUpdates[context.key] || 0) + 1;
    state.value.textContent = String(descriptor.rows[0]?.value ?? 'empty');
    return state;
  },
  dispose() {},
});
'''}]},
    }))
    root, _ = prepare_input(source, auth=auth)
    workspace_path = root / "workspace.yaml"
    workspace = yaml.safe_load(workspace_path.read_text())
    workspace["runtime"] = {"browser_table_transport": transport}
    workspace_path.write_text(yaml.safe_dump(workspace))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    if transport == 'json':
        page.add_init_script('''(() => {
          window.__heldActionContexts = [];
          window.__holdActionContext = true;
          window.addEventListener('message', event => {
            if (window.__holdActionContext && event.data?.type === 'dataviz:set-interaction') {
              event.stopImmediatePropagation();
              window.__heldActionContexts.push(event);
            }
          }, true);
        })();''')
    with _running_server(root) as url:
        _open_single_fixture_dashboard(page, url, root)
        expect(page.locator("#run-button")).to_be_enabled(timeout=10_000)
        page.locator("#run-button").click()
        frame = page.frame_locator("#canvas-frame")
        expect(frame.locator('[data-view-id="labels"] .action-value')).to_have_text("1", timeout=30_000)
        expect(frame.locator('[data-view-id="summary"]')).to_contain_text("10", timeout=30_000)
        expect(page.locator("#query-parameters-toggle")).to_have_attribute("aria-expanded", "true", timeout=10_000)
        original_run = page.locator("#canvas-frame").get_attribute("data-run-id")
        original_frame = page.locator("#canvas-frame").get_attribute("data-frame-id")
        before = frame.locator("body").evaluate("""() => {
          window.actionSentinel = 'same-document';
          return {mounts:{...window.actionMounts}, updates:{...window.actionUpdates}};
        }""")
        page.locator('#parameter-form input[name="label"]').fill("draft-not-applied")
        interrupted = []
        if transport == "json":
            def fail_first_refresh_transport(route):
                if "labels/main" in route.request.url and not interrupted:
                    interrupted.append(route.request.url)
                    route.fulfill(status=503, content_type="application/json", body='{"detail":"deliberate transport interruption"}')
                else:
                    route.continue_()
            page.route("**/api/runs/*/outputs/**", fail_first_refresh_transport)
        if transport == 'json':
            # Data can render before the host has committed the query. Hold
            # its readiness handshake even after Ready to make this ordering
            # deterministic rather than relying on machine/load timing.
            expect(page.locator('#query-diagnostics-label')).to_have_text('Ready')
            page.wait_for_function("document.querySelector('#canvas-frame').contentWindow.__heldActionContexts.length > 0")
        frame.get_by_role("button", name="Save annotation").click()
        if transport == 'json':
            assert frame.locator('body').evaluate('datavizServerActionQueue.length') == 1
            frame.locator('body').evaluate('''() => {
              window.__holdActionContext = false;
              window.__heldActionContexts.splice(0).forEach(event => {
                window.dispatchEvent(new MessageEvent('message', {
                  data:event.data, origin:event.origin, source:event.source,
                }));
              });
            }''')
        if transport == "json":
            expect(frame.locator('[data-view-id="labels"] .action-feedback')).to_have_text("Saved; refresh failed", timeout=30_000)
            assert interrupted
            expect(frame.locator('[data-view-id="labels"] .action-value')).to_have_text("1")
            assert page.locator("#canvas-frame").get_attribute("data-run-id") == original_run
            with sqlite3.connect(database) as connection:
                assert connection.execute("select value from facts").fetchone()[0] == 2
            frame.get_by_role("button", name="Retry refresh").click()
        expect(frame.locator('[data-view-id="labels"] .action-feedback')).to_have_text("Saved", timeout=30_000)
        expect(frame.locator('[data-view-id="labels"] .action-value')).to_have_text("2")
        expect(frame.locator('[data-view-id="summary"]')).to_contain_text("20", timeout=15_000)
        expect(frame.locator('[data-view-id="sales"] .action-value')).to_have_text("42")
        assert page.locator("#canvas-frame").get_attribute("data-frame-id") == original_frame
        assert page.locator("#canvas-frame").get_attribute("data-run-id") != original_run
        expect(page.locator('#parameter-form input[name="label"]')).to_have_value("draft-not-applied")
        after = frame.locator("body").evaluate("""() => ({
          sentinel:window.actionSentinel, mounts:window.actionMounts, updates:window.actionUpdates,
          run:window.dataviz.run_id, receipt:window.lastActionReceipt,
          draft:window.dataviz.draft_query_parameter_state.label,
          applied:window.dataviz.query_parameter_state.label,
        })""")
        assert after["sentinel"] == "same-document"
        assert after["mounts"] == before["mounts"]
        assert after["updates"].get("sales", 0) == before["updates"].get("sales", 0)
        assert after["applied"]["value"] == "applied"
        assert after["draft"]["value"] == "draft-not-applied"
        assert after["run"] == page.locator("#canvas-frame").get_attribute("data-run-id")
        view_result = frame.locator("body").evaluate("""async () => (
          window.dataviz.serverActions.invoke('save', {view_only:true})
        )""")
        assert view_result["refresh"]["query_executed"] is False
        assert frame.locator("body").evaluate("window.actionUpdates.sales") == before["updates"].get("sales", 0) + 1
        # Repeated clicks use the new Run without a frame reload.
        frame.get_by_role("button", name="Save annotation").click()
        expect(frame.locator('[data-view-id="labels"] .action-value')).to_have_text("3", timeout=30_000)
        expect(frame.locator('[data-view-id="labels"] .action-feedback')).to_have_text("Saved", timeout=30_000)
        queued = frame.locator("body").evaluate("""async () => {
          const progress = [];
          const receipts = await Promise.all([1, 2, 3].map(row =>
            window.dataviz.serverActions.invoke('save', {row}, {
              onProgress:r => progress.push({row, status:r.status}),
            })));
          return {statuses:receipts.map(r => r.status), progress};
        }""")
        assert queued["statuses"] == ["succeeded"] * 3
        assert sum(item["status"] == "queued" for item in queued["progress"]) == 3
        expect(frame.locator('[data-view-id="labels"] .action-value')).to_have_text("6", timeout=30_000)
        assert errors == []

    loaded = load_workspace(root)
    result = Executor(loaded).run("action-demo")
    report_path = CanvasRenderer(loaded).write_report(loaded.dashboard("action-demo"), result, tmp_path / "action-report.html")
    with _running_static_server(report_path.parent) as report_url:
        page.goto(f"{report_url}/{report_path.name}")
        expect(page.get_by_role("button", name="Save annotation")).to_be_disabled(timeout=15_000)
        assert page.evaluate("window.dataviz.serverActions.available") is False
        outcome = page.evaluate("""async () => {
          try { await window.dataviz.serverActions.invoke('save', {}); return 'unexpected'; }
          catch (error) { return error.code; }
        }""")
        assert outcome == "server_action_unavailable"
    with sqlite3.connect(database) as connection:
        assert connection.execute("select value from facts").fetchone()[0] == 6
