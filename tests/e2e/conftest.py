"""Use verified upstream assets for in-process CLI-owned browser contexts too."""
import hashlib
import json
import os
import faulthandler
import time
from contextlib import contextmanager
from pathlib import Path

import pytest


def _watchdog_state(nodeid, phase):
    path = os.environ.get('DATAVIZ_E2E_PROGRESS')
    if not path or os.environ.get('DATAVIZ_E2E_WATCHDOG_OWNER') != str(os.getpid()):
        return None
    destination = Path(path)
    payload = {'pid':os.getpid(), 'nodeid':nodeid, 'phase':phase, 'at':time.monotonic()}
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload))
    temporary.replace(destination)
    with destination.with_suffix('.events.jsonl').open('a') as stream:
        stream.write(json.dumps(payload) + '\n')
    return destination


def pytest_configure(config):
    if os.environ.get('DATAVIZ_E2E_PROGRESS') and not os.environ.get('DATAVIZ_E2E_WATCHDOG_OWNER'):
        os.environ['DATAVIZ_E2E_WATCHDOG_OWNER'] = str(os.getpid())
        _watchdog_state('', 'collection')


@pytest.fixture
def browser_step(request):
    """Leave small checkpoints even when Playwright's greenlet never returns.

    Use static step names only, never URLs, arguments or business values.
    This separate journal does not renew the phase watchdog deadline.
    """
    def record(name, status):
        path = os.environ.get('DATAVIZ_E2E_PROGRESS')
        if not path or os.environ.get('DATAVIZ_E2E_WATCHDOG_OWNER') != str(os.getpid()):
            return
        payload = {'nodeid': request.node.nodeid, 'step': name,
                   'status': status, 'at': time.monotonic()}
        with Path(path).with_suffix('.steps.jsonl').open('a') as stream:
            stream.write(json.dumps(payload) + '\n')

    @contextmanager
    def step(name):
        record(name, 'started')
        try:
            yield
        except BaseException:
            record(name, 'failed')
            raise
        else:
            record(name, 'completed')
    return step


def _bounded_phase(item, phase):
    destination = _watchdog_state(item.nodeid, phase)
    if destination is None:
        yield
        return
    with destination.with_suffix('.stacks.log').open('a') as stacks:
        stacks.write(f'\n{item.nodeid} [{phase}]\n')
        stacks.flush()
        faulthandler.dump_traceback_later(float(os.environ['DATAVIZ_E2E_PHASE_TIMEOUT']), file=stacks, exit=True)
        try:
            yield
        finally:
            faulthandler.cancel_dump_traceback_later()
            _watchdog_state(item.nodeid, f'{phase}_complete')


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection(session):
    yield from _bounded_phase(session, 'collection')


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_sessionfinish(session):
    yield from _bounded_phase(session, 'sessionfinish')


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_setup(item):
    yield from _bounded_phase(item, 'setup')


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    yield from _bounded_phase(item, 'call')


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item):
    yield from _bounded_phase(item, 'teardown')

# The artifact self-test copies this file into an isolated synthetic harness.
# There it supplies its own page/engine fixtures and has no support package.
if Path(__file__).with_name('support').is_dir():
    from e2e.support.browser import browser, page  # noqa: F401


STATE_TIMELINE = """(() => {
  const events = [];
  let signature = '';
  const capture = () => {
    let phase = null;
    try { phase = typeof datavizControlChannel === 'undefined' ? null : datavizControlChannel.phase; } catch (_) {}
    const state = {
      phase,
      ready:document.readyState,
      views:[...document.querySelectorAll('[data-view-id]')].slice(0,50).map(node => ({
        id:node.dataset.viewId, status:node.dataset.viewStatus || null,
      })),
    };
    const next = JSON.stringify(state);
    if (next === signature) return;
    signature = next;
    events.push({at_ms:Math.round(performance.now()), ...state});
    if (events.length > 60) events.shift();
  };
  window.__datavizTestTimeline = events;
  document.addEventListener('DOMContentLoaded', () => {
    new MutationObserver(capture).observe(document.documentElement, {
      subtree:true,childList:true,attributes:true,attributeFilter:['data-view-status'],
    });
    capture();
  });
  document.addEventListener('readystatechange', capture);
})();"""


@pytest.fixture
def state_timeline():
    return STATE_TIMELINE


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, f"report_{call.when}", outcome.get_result())


@pytest.fixture
def failure_artifacts(request):
    """Raw traces are opt-in and only suitable for synthetic fixture data."""
    directory = os.environ.get("DATAVIZ_E2E_ARTIFACT_DIR")
    contexts = []
    if directory:
        name = hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:16]
        destination = Path(directory) / os.environ.get("DATAVIZ_BROWSER", "chromium") / name
    else:
        destination = None

    def attach(context):
        if destination is not None:
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
            contexts.append(context)
        return context

    yield attach
    failed = any(getattr(request.node, f"report_{phase}", None) and
                 getattr(request.node, f"report_{phase}").failed for phase in ("setup", "call"))
    for index, context in enumerate(contexts):
        if failed:
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "test.txt").write_text(request.node.nodeid, encoding="utf-8")
            for page_index, page in enumerate(context.pages):
                try:
                    page.screenshot(path=str(destination / f"{index}-{page_index}.png"), timeout=3000)
                except Exception as error:
                    (destination / f"{index}-{page_index}-screenshot-error.txt").write_text(type(error).__name__)
            context.tracing.stop(path=str(destination / f"{index}-trace.zip"))
            print(f"Browser failure artifacts: {destination}")
        else:
            context.tracing.stop()
        context.close()


@pytest.fixture(autouse=True)
def cached_browser_assets(monkeypatch):
    from playwright.sync_api import BrowserContext

    root = Path(__file__).resolve().parents[2]
    directory = Path(os.environ.get('DATAVIZ_E2E_ASSET_DIR', root / '.browser-test-assets'))
    if not directory.is_dir() and 'DATAVIZ_E2E_ASSET_DIR' not in os.environ:
        return
    manifest = Path(__file__).with_name('assets.json')
    # The synthetic failure-artifact harness copies this fixture in isolation.
    if not manifest.is_file():
        return
    assets = [(a['url'], a['file'], a['content_type'], a['sha256'])
              for a in json.loads(manifest.read_text())]
    for _, name, _, digest in assets:
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    original = BrowserContext.new_page

    def new_page(context, *args, **kwargs):
        page = original(context, *args, **kwargs)
        # Firefox does not reliably route imports originating in a dedicated
        # module Worker. Inline only our exact bootstrap import with the same
        # checksum-verified upstream bytes; retain native Worker execution,
        # transport, WASM, lifecycle and errors (not a contract stub).
        if context.browser and context.browser.browser_type.name == 'firefox':
            worker_sources = {
                f'import "{url}";': (directory / name).read_text()
                for url, name, _, _ in assets if name == 'perspective/worker.js'
            }
            page.add_init_script("""sources => {}""" if not worker_sources else
                """(() => {
                  const sources = %s;
                  const NativeBlob = window.Blob;
                  window.Blob = class extends NativeBlob {
                    constructor(parts, options) {
                      if (parts?.length === 1 && typeof parts[0] === 'string'
                          && Object.hasOwn(sources, parts[0])) parts = [sources[parts[0]]];
                      super(parts, options);
                    }
                  };
                })();""" % json.dumps(worker_sources))
        # Exact page-level routes inject local bytes even when the analysis
        # runner blocks external network. Other URLs retain its network policy.
        for url, name, content_type, _ in assets:
            def fulfill(route, *, name=name, content_type=content_type):
                return route.fulfill(
                path=str(directory / name), content_type=content_type,
                headers={'Access-Control-Allow-Origin': '*'},
                )
            # Context routes also cover real dedicated Worker module requests.
            context.route(url, fulfill)
            page.route(url, fulfill)
        return page

    monkeypatch.setattr(BrowserContext, 'new_page', new_page)
