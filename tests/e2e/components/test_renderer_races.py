"""Real renderer adapter with explicitly released async hook boundaries."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def renderer_page(page):
    page.set_content('<section class="dv-view" data-view-id="probe"><div class="dv-view-body"></div></section>')
    page.evaluate('''() => {
      window.dataviz = {};
      window.datavizComponents = {viewDeclarative:{registerViews() {}}};
      window.datavizRuntimeServices = {valueProfile:() => ({}), escape:String};
      window.datavizRuntime = {
        renderers:new Map(), rendererLifecycleEvidence:new Map(),
        rendererErrors:new Map(), viewRenderEvidence:new Map(),
        metrics:{renderers:{mounts:0, updates:0, disposes:0, empty:0, failed:0, totalMs:0}},
        registerRenderer(name, value) { this.renderers.set(name, value); }
      };
    }''')
    page.add_script_tag(path=str(ROOT / 'src/dataviz/components/packages/view.declarative/adapter.js'))
    return page


@pytest.mark.parametrize('transition', ['waiting', 'cancelled', 'unavailable', 'dispose'])
@pytest.mark.parametrize('outcome', ['resolve', 'reject'])
def test_late_renderer_mount_cannot_overwrite_terminal_state(renderer_page, transition, outcome):
    result = renderer_page.evaluate('''async ({transition, outcome}) => {
      const runtime = window.datavizRuntime;
      const adapter = runtime.viewAdapter;
      const root = document.querySelector('.dv-view');
      let release, entered, cleaned = 0;
      const started = new Promise(resolve => { entered = resolve; });
      runtime.registerRenderer('probe', {
        async mount(context) {
          await new Promise((resolve, reject) => {
            release = () => outcome === 'resolve' ? resolve() : reject(new Error('late failure'));
            entered();
          });
          const node = document.createElement('span');
          node.textContent = 'old mount';
          context.body.replaceChildren(node);
          return {node};
        },
        dispose(context, state) { cleaned++; state.node.remove(); }
      });
      adapter.renderInto(root, 'probe', () => ({type:'probe'}));
      const old = adapter.completion(root, root._datavizRenderGeneration);
      await started;
      if (transition === 'dispose') adapter.dispose();
      else adapter[transition](root, 'probe', 'new state');
      const status = root.dataset.viewStatus;
      const text = root.textContent;
      release();
      const completion = await old;
      return {before:status, after:root.dataset.viewStatus, status:completion.status,
        cleaned, registered:adapter.states.has('probe'), errors:runtime.rendererErrors.size,
        oldNodes:root.querySelectorAll('span').length,
        preservedText:transition === 'dispose' || root.textContent === text};
    }''', {'transition': transition, 'outcome': outcome})
    assert result['status'] == 'superseded', result
    assert result['before'] == result['after'], result
    assert not result['registered'] and result['errors'] == 0, result
    assert result['cleaned'] == (1 if outcome == 'resolve' else 0), result
    assert result['preservedText'], result


def test_mount_pending_rejection_releases_created_state(renderer_page):
    result = renderer_page.evaluate('''async () => {
      const runtime = window.datavizRuntime, adapter = runtime.viewAdapter;
      const root = document.querySelector('.dv-view');
      let cleaned = 0;
      runtime.registerRenderer('probe', {
        mount(context) {
          return {pending:Promise.reject(new Error('resource initialization failed'))};
        },
        dispose(context, state) { cleaned++; }
      });
      adapter.renderInto(root, 'probe', () => ({type:'probe'}));
      const outcome = await adapter.completion(root, root._datavizRenderGeneration);
      return {cleaned, status:outcome.status, registered:adapter.states.has('probe')};
    }''')
    assert result == {'cleaned': 1, 'status': 'error', 'registered': False}


def test_dispose_during_update_cleans_final_state_once(renderer_page):
    result = renderer_page.evaluate('''async () => {
      const runtime = window.datavizRuntime, adapter = runtime.viewAdapter;
      const root = document.querySelector('.dv-view');
      let entered, release;
      const started = new Promise(resolve => { entered = resolve; });
      const cleaned = [];
      runtime.registerRenderer('probe', {
        mount() { return {revision:1}; },
        async update(context, descriptor, state) {
          await new Promise(resolve => { release = resolve; entered(); });
          context.body.textContent = 'late update';
          state.revision = 2;
          return state;
        },
        dispose(context, state) { cleaned.push(state.revision); context.body.replaceChildren(); }
      });
      adapter.renderInto(root, 'probe', () => ({type:'probe'}));
      await adapter.completion(root, root._datavizRenderGeneration);
      adapter.renderInto(root, 'probe', () => ({type:'probe'}));
      const pending = adapter.completion(root, root._datavizRenderGeneration);
      await started;
      adapter.waiting(root, 'probe');
      const expected = root.textContent;
      release();
      await pending;
      // Allow disposal chained to the settled update to finish, no timer.
      await Promise.resolve(); await Promise.resolve();
      return {cleaned, preserved:root.textContent === expected, active:adapter.states.size};
    }''')
    assert result == {'cleaned': [2], 'preserved': True, 'active': 0}


@pytest.mark.parametrize('outcome', ['resolve', 'reject'])
def test_new_render_wins_over_late_mount(renderer_page, outcome):
    result = renderer_page.evaluate('''async outcome => {
      const runtime = window.datavizRuntime, adapter = runtime.viewAdapter;
      const root = document.querySelector('.dv-view');
      let release, entered;
      const started = new Promise(resolve => { entered = resolve; });
      runtime.registerRenderer('probe', {
        async mount(context, descriptor) {
          if (descriptor.label === 'A') await new Promise((resolve, reject) => {
            release = () => outcome === 'resolve' ? resolve() : reject(new Error('old A'));
            entered();
          });
          const node = document.createElement('span');
          node.textContent = descriptor.label;
          context.body.append(node);
          return {node};
        },
        dispose(context, state) { state.node.remove(); }
      });
      adapter.renderInto(root, 'probe', () => ({type:'probe', label:'A'}));
      const old = adapter.completion(root, root._datavizRenderGeneration);
      await started;
      adapter.renderInto(root, 'probe', () => ({type:'probe', label:'B'}));
      const current = adapter.completion(root, root._datavizRenderGeneration);
      release();
      const a = await old, b = await current;
      return {a:a.status, b:b.status, text:root.textContent, errors:runtime.rendererErrors.size};
    }''', outcome)
    assert result == {'a': 'superseded', 'b': 'ready', 'text': 'B', 'errors': 0}


def test_disposed_renderer_context_cannot_invoke_action(renderer_page):
    result = renderer_page.evaluate('''async () => {
      let captured, calls = 0;
      window.dataviz.serverActions = {available:true, invoke() { calls++; return Promise.resolve(); }};
      const adapter = window.datavizRuntime.viewAdapter;
      window.datavizRuntime.registerRenderer('probe', {
        mount(context) { captured = context; return {}; }, dispose() {}
      });
      const root = document.querySelector('.dv-view');
      adapter.renderInto(root, 'probe', () => ({type:'probe'}));
      await adapter.completion(root, root._datavizRenderGeneration);
      adapter.dispose();
      let rejected = false;
      try { await captured.actions.invoke('save'); } catch (_) { rejected = true; }
      return {available:captured.actions.available, rejected, calls};
    }''')
    assert result == {'available': False, 'rejected': True, 'calls': 0}


def test_bootstrap_plotly_pending_mount_is_disposed(renderer_page):
    page = renderer_page
    page.add_script_tag(path=str(ROOT / 'src/dataviz/vendor/plotly/plotly-4.1.0.min.js'))
    page.evaluate('''() => {
      delete window.datavizRuntime.viewAdapter;
      document.querySelector('.dv-view-body').innerHTML = '<div class="dv-plotly" data-spec="fixture"></div>';
      window.datavizRuntimeServices.decodeSpec = () => ({data:[{x:[1], y:[2]}]});
      window.__purges = 0;
      const mount = Plotly.newPlot, purge = Plotly.purge;
      Plotly.newPlot = async (...args) => {
        await new Promise(resolve => { window.__releaseBootstrap = resolve; });
        return mount(...args);
      };
      Plotly.purge = (...args) => { window.__purges++; return purge(...args); };
    }''')
    page.add_script_tag(path=str(ROOT / 'src/dataviz/components/packages/view.declarative/adapter.js'))
    page.wait_for_function('typeof window.__releaseBootstrap === "function"')
    result = page.evaluate('''async () => {
      const adapter = window.datavizRuntime.viewAdapter;
      const pending = document.querySelector('.dv-view')._datavizRendererPending;
      adapter.dispose();
      window.__releaseBootstrap();
      await pending;
      return {states:adapter.states.size, purges:window.__purges};
    }''')
    assert result == {'states': 0, 'purges': 1}
