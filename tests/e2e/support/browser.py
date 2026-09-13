from __future__ import annotations

import json

import os


import time


from collections import deque

from urllib.parse import urlsplit, urlunsplit

import pytest


from playwright.sync_api import (
    Browser,
    Page,
    sync_playwright,
)


@pytest.fixture(scope="module")
def browser() -> Browser:
    with sync_playwright() as playwright:
        # Browser availability is part of the P0 contract. CI installs Chromium
        # explicitly, so a missing or broken browser must fail instead of hiding
        # the regression behind a skipped test.
        browser_name = os.environ.get("DATAVIZ_BROWSER", "chromium")
        if browser_name not in {"chromium", "firefox", "webkit"}:
            raise RuntimeError(f"Unsupported DATAVIZ_BROWSER: {browser_name}")
        instance = getattr(playwright, browser_name).launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser: Browser, failure_artifacts, state_timeline) -> Page:
    context = failure_artifacts(browser.new_context(viewport={"width": 1440, "height": 900}))
    context.add_init_script(state_timeline)
    # Exact, checksum-verified upstream resources are shared by conftest.py.
    page = context.new_page()
    diagnostics = deque(maxlen=30)
    def safe_url(url):
        parts = urlsplit(url)
        # Query parameters and URL credentials may contain business values.
        return urlunsplit((parts.scheme, parts.hostname or '', parts.path, '', ''))
    pending_requests = {}
    page.on("request", lambda request: pending_requests.__setitem__(request, time.monotonic()))

    def finished(request):
        started = pending_requests.pop(request, None)
        if started is not None and time.monotonic() - started > 1:
            diagnostics.append({"url": safe_url(request.url), "resource_type": request.resource_type,
                                "elapsed_ms": round((time.monotonic() - started) * 1000)})

    page.on("requestfinished", finished)
    page.on("requestfailed", finished)
    page.on("console", lambda message: diagnostics.append({"console_error": True}) if message.type == "error" else None)
    page.on("pageerror", lambda error: diagnostics.append({"page_error": True}))
    page.on("requestfailed", lambda request: diagnostics.append({
        "url": safe_url(request.url), "failure": request.failure,
    }))
    page.on("response", lambda response: diagnostics.append({
        "url": safe_url(response.url), "status": response.status,
    }) if response.status >= 400 else None)
    yield page
    # Pytest displays captured teardown output on failure. Keep evidence bounded
    # and avoid serializing table data or the complete HTML document.
    frames = []
    for frame in page.frames:
        try:
            frames.append({
                "url": safe_url(frame.url),
                "state": frame.locator("body").evaluate("""body => ({
                  readyState:document.readyState,
                  controlPhase:typeof datavizControlChannel === 'undefined' ? null : datavizControlChannel.phase,
                  canvas: !!document.querySelector('.dv-canvas'),
                  error_count: body.querySelectorAll('.dv-view-error').length,
                  views: [...body.querySelectorAll('[data-view-id]')].map(n => ({
                    id:n.dataset.viewId, status:n.dataset.viewStatus,
                  })),
                  timeline: window.__datavizTestTimeline || [],
                })""", timeout=2000),
            })
        except Exception as error:
            frames.append({"url": safe_url(frame.url), "inspection_error": type(error).__name__})
    print("Browser evidence:", json.dumps({"events": list(diagnostics), "frames": frames,
        "pending_requests": [{"url": safe_url(request.url), "resource_type": request.resource_type,
                              "elapsed_ms": round((time.monotonic() - started) * 1000)}
                             for request, started in list(pending_requests.items())[-15:]],
    }, ensure_ascii=False))
    if not os.environ.get("DATAVIZ_E2E_ARTIFACT_DIR"):
        context.close()

