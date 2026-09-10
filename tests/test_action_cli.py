import io
import json
from urllib.error import URLError

import pytest
from typer.testing import CliRunner

from dataviz.cli import app
from dataviz import cli_actions


def arguments(operation="invoke"):
    args = ["actions", operation, "test", "save", "--server", "http://localhost:8888",
            "--session-id", "session", "--request-id", "write-1"]
    if operation == "invoke":
        args += ["--run-id", "run-1"]
    return args


def test_cli_requires_caller_request_identity_and_rejects_bad_payloads(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli_actions, "request_action", lambda **kw: calls.append(kw) or {"status": "succeeded"})
    runner = CliRunner()
    for payload in ["[]", "null", '{"x": NaN}', "invalid"]:
        assert runner.invoke(app, arguments() + ["--payload", payload]).exit_code != 0
    path = tmp_path / "payload.json"
    path.write_text('{"key":"apple"}')
    assert runner.invoke(app, arguments() + ["--payload", "{}", "--payload-file", str(path)]).exit_code != 0
    assert calls == []
    result = runner.invoke(app, arguments() + ["--payload-file", str(path)])
    assert result.exit_code == 0, result.output
    assert calls[0]["payload"] == {"key": "apple"}
    assert calls[0]["request_id"] == "write-1"


@pytest.mark.parametrize("operation,method,suffix", [
    ("invoke", "POST", "/actions/save"),
    ("status", "GET", "/actions/save/write-1?session_id=session"),
    ("refresh", "POST", "/actions/save/write-1/refresh"),
])
def test_cli_uses_one_request_and_preserves_server_receipt(monkeypatch, operation, method, suffix):
    calls = []
    receipt = {"status": "succeeded", "result": {"saved": True}, "refresh": {"status": "running"}}

    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            return io.BytesIO(json.dumps(receipt).encode())

    monkeypatch.setattr(cli_actions, "build_opener", lambda *handlers: Opener())
    response = CliRunner().invoke(app, arguments(operation))
    assert response.exit_code == 0, response.output
    assert json.loads(response.output) == receipt
    assert len(calls) == 1
    assert calls[0].get_method() == method
    assert calls[0].full_url.endswith(suffix)
    if operation == "invoke":
        assert json.loads(calls[0].data)["run_id"] == "run-1"
    if operation == "refresh":
        assert json.loads(calls[0].data) == {"session_id": "session"}


def test_transport_failure_never_retries_and_retains_identity(monkeypatch):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            raise URLError("connection lost")

    monkeypatch.setattr(cli_actions, "build_opener", lambda *handlers: Opener())
    response = CliRunner().invoke(app, arguments())
    assert response.exit_code == 1
    assert len(calls) == 1
    payload = json.loads(response.output)
    assert payload["request_id"] == "write-1"
    assert "unknown" in payload["message"]


def test_saved_but_refresh_failed_is_not_disguised_as_unsaved(monkeypatch):
    receipt = {"status": "succeeded", "result": {"saved": True}, "refresh": {"status": "failed"}}
    monkeypatch.setattr(cli_actions, "request_action", lambda **kw: receipt)
    response = CliRunner().invoke(app, arguments())
    assert response.exit_code == 1
    assert json.loads(response.output) == receipt


@pytest.mark.parametrize("server", ["file:///tmp/test", "http://user:pass@localhost", "http://localhost?x=1"])
def test_client_rejects_unsafe_server_urls_before_transport(server):
    with pytest.raises(ValueError, match="base URL"):
        cli_actions.request_action(server=server, dashboard="test", action="save", session_id="s",
                                   request_id="r", operation="status")


def test_client_does_not_follow_redirects():
    assert cli_actions._NoRedirect().redirect_request(None, None, 307, "", {}, "http://other") is None
