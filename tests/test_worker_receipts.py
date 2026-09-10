"""Deterministically exercise send/exit between a pipe poll and liveness check."""
from types import SimpleNamespace

import pytest

from dataviz.errors import ExecutionFailure
from dataviz.execution.python_process import execute_python_node
from test_server_actions import executor_fixture


@pytest.mark.parametrize("worker", ["query", "action"])
@pytest.mark.parametrize("has_result", [True, False])
def test_worker_exit_drains_final_message_without_replaying(tmp_path, monkeypatch, worker, has_result):
    polls = []
    starts = []

    def poll(timeout):
        polls.append(timeout)
        # First poll times out; then the child has exited and a final frame
        # (or EOF) becomes visible. No real-time sleeps make this test flaky.
        return len(polls) > 1

    def recv():
        if not has_result:
            raise EOFError
        return {"ok": True, "outputs": {}} if worker == "query" else {
            "status": "succeeded", "result": {"saved": True}, "invalidations": [],
        }

    pipe = SimpleNamespace(poll=poll, recv=recv, close=lambda: None)
    process = SimpleNamespace(start=lambda: starts.append(True), is_alive=lambda: False,
                              exitcode=0, join=lambda **kwargs: None, close=lambda: None)
    runtime = SimpleNamespace(Pipe=lambda **kwargs: (pipe, pipe), Process=lambda *args, **kwargs: process)
    monkeypatch.setattr("multiprocessing.get_context", lambda mode: runtime)
    if worker == "query":
        context = SimpleNamespace(workspace_root=tmp_path, dashboard_root=tmp_path, run_id="test",
                                  query_parameter_state={}, query_inputs={}, control_inputs={},
                                  control_state={}, control_filters={}, inputs={}, adapter=None)
        def execute():
            return execute_python_node(definition=SimpleNamespace(timeout_seconds=5),
                                       definition_path=tmp_path / "source.yaml", context=context,
                                       node_id="source:test", node_kind="source")
        if has_result:
            assert execute() == {}
        else:
            with pytest.raises(ExecutionFailure, match="exited without a result"):
                execute()
    else:
        execute, journal = executor_fixture(tmp_path, "def execute(context): return {}")
        receipt = execute({})
        assert receipt["status"] == ("succeeded" if has_result else "unknown")
        assert execute({}) == receipt  # Receipt replay must not restart writes.
    assert starts == [True]
    assert polls[1] == 0  # Explicit final drain after confirmed process exit.
