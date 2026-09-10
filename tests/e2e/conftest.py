"""Use verified upstream assets for in-process CLI-owned browser contexts too."""
import hashlib
import os
from pathlib import Path

import pytest


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
