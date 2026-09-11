"""Use verified upstream assets for in-process CLI-owned browser contexts too."""
import hashlib
import os
from pathlib import Path

import pytest


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
    assets = [
        ('https://cdn.jsdelivr.net/npm/apache-arrow@21.1.0/Arrow.es2015.min.js', 'Arrow.es2015.min.js',
         'application/javascript', 'd3f0ded2a2bdd1208232b942f8e4810f7a402564fac3c78b4574158cd542acb9'),
        ('https://cdn.plot.ly/un/world_110m.json', 'world_110m.json', 'application/json',
         'e1bf51740ad28396265e52123ea7315d692f112664ab2cb0f1ea76a96fe1bb0a'),
    ]
    for _, name, _, digest in assets:
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    original = BrowserContext.new_page

    def new_page(context, *args, **kwargs):
        page = original(context, *args, **kwargs)
        # Exact page-level routes inject local bytes even when the analysis
        # runner blocks external network. Other URLs retain its network policy.
        for url, name, content_type, _ in assets:
            page.route(url, lambda route, *, name=name, content_type=content_type: route.fulfill(
                path=str(directory / name), content_type=content_type,
                headers={'Access-Control-Allow-Origin': '*'},
            ))
        return page

    monkeypatch.setattr(BrowserContext, 'new_page', new_page)
