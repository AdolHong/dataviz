"""Use verified upstream assets for in-process CLI-owned browser contexts too."""
import hashlib
import json
import os
from pathlib import Path

import pytest

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
