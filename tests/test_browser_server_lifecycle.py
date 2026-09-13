"""The test host must terminate even while a page keeps an SSE stream open."""
import asyncio
import threading
import time

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from e2e.support import runtime
import pytest


def test_test_server_closes_live_stream_on_exit(tmp_path, monkeypatch):
    app = FastAPI()
    connected = threading.Event()
    cancelled = threading.Event()
    release_client = threading.Event()
    errors = []
    worker = None

    @app.get('/events')
    async def events():
        async def stream():
            try:
                yield 'data: ready\n\n'
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return StreamingResponse(stream(), media_type='text/event-stream')

    monkeypatch.setattr(runtime, 'create_app', lambda *args, **kwargs: app)

    def client(url):
        try:
            with httpx.stream('GET', url + '/events', timeout=5) as response:
                lines = response.iter_lines()
                assert next(lines) == 'data: ready'
                connected.set()
                release_client.wait(15)
        except Exception as error:
            errors.append(error)

    try:
        with runtime._running_server(tmp_path) as url:
            worker = threading.Thread(target=client, args=(url,), daemon=True)
            worker.start()
            assert connected.wait(5), errors
            started = time.monotonic()
        assert time.monotonic() - started < 3, 'Test teardown waited on a live SSE client'
        assert cancelled.wait(1), 'SSE task leaked beyond server teardown'
    finally:
        release_client.set()
        if worker is not None:
            worker.join(timeout=5)
    assert not errors


def test_workspace_subset_preserves_shared_resources_and_rejects_missing_target(tmp_path):
    target = runtime._copy_workspace(runtime.SHOWCASE, tmp_path / 'one-chart',
                                     dashboards=('功能示例##chart-gallery',))
    assert [p.name for p in (target / 'dashboards').iterdir()] == ['功能示例##chart-gallery']
    assert (target / 'workspace.yaml').read_bytes() == (runtime.SHOWCASE / 'workspace.yaml').read_bytes()
    assert (target / 'assets/maps/demo-regions.geojson').is_file()
    with pytest.raises(ValueError, match='does not exist'):
        runtime._copy_workspace(runtime.SHOWCASE, tmp_path / 'missing', dashboards=('missing',))
