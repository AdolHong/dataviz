from __future__ import annotations

import json
import shlex

import pytest
from typer.testing import CliRunner

from dataviz.cli import app, parse_params
from dataviz.execution import Executor
from dataviz.documentation import resolve_authoring_route


@pytest.mark.parametrize("values", [["x=1", "x=2"], ["=1"], [" x=1"], ["x =1"]])
def test_invalid_assignments_are_rejected(values):
    with pytest.raises(Exception, match="Duplicate parameter|Parameter name"):
        parse_params(values)


def test_parameter_values_keep_json_strings_equals_and_empty_values():
    assert parse_params(['items=[1,2]', 'enabled=true', 'label=a=b', 'empty=', 'text="1"']) == {
        "items": [1, 2], "enabled": True, "label": "a=b", "empty": "", "text": "1",
    }


@pytest.mark.parametrize("flag", ["--query-param", "--control"])
def test_duplicate_assignments_fail_before_standalone_compilation(tmp_path, monkeypatch, flag):
    import dataviz.standalone
    def forbidden(*args, **kwargs):
        pytest.fail("Malformed arguments must not compile or run data")
    monkeypatch.setattr(dataviz.standalone, "prepare_input", forbidden)
    result = CliRunner().invoke(app, ["run", str(tmp_path), "sample", flag, "x=1", flag, "x=2"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "analysis_argument_invalid"
    assert "Duplicate parameter" in result.stdout


def test_result_next_actions_preserve_shell_sensitive_paths_and_do_not_requery(tmp_path, monkeypatch):
    runner = CliRunner()
    root = tmp_path / "owner's $sample `literal` folder"
    state_home = tmp_path / "owner's $state `literal` folder"
    monkeypatch.setenv('DATAVIZ_STATE_DIR', str(state_home))
    created = runner.invoke(app, ["scaffold", "--output", str(root)])
    assert created.exit_code == 0, created.output
    for command in json.loads(created.stdout)["next"]:
        result = runner.invoke(app, shlex.split(command)[1:])
        assert result.exit_code == 0, result.output
    published = json.loads(result.stdout)
    def forbidden(*args, **kwargs):
        pytest.fail("Inspecting a sealed Result must not requery")
    monkeypatch.setattr(Executor, "run", forbidden)
    for command in published["next_actions"]:
        parts = shlex.split(command)
        assert str(state_home) in parts[3]
        assert shlex.quote(parts[3]) in command
        read = runner.invoke(app, parts[1:])
        assert read.exit_code == 0, read.output


def test_run_help_separates_advanced_flags_without_requiring_them():
    result = CliRunner().invoke(app, ["run", "--help"], terminal_width=140)
    assert result.exit_code == 0
    assert "Multi-page and interaction" in result.stdout
    assert "Advanced analysis" in result.stdout
    assert "--query-param" in result.stdout
    assert "requires --overlay" in result.stdout


def test_minimal_task_commands_use_the_same_executable_single_file_start(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    route = resolve_authoring_route("minimal")
    assert route["scaffolds"][0] == "standalone"
    for command in route["commands"]:
        result = runner.invoke(app, shlex.split(command)[1:])
        assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "ready"


@pytest.mark.parametrize("arguments", [
    ["catalog", "list", "--format", "invalid"],
    ["catalog", "search", "[", "--format", "invalid"],
    ["result", "show", "missing_result"],
    ["result", "inspect", "missing_result"],
])
def test_analysis_argument_errors_always_use_the_analysis_contract(tmp_path, arguments):
    args = [*arguments[:2], str(tmp_path), *arguments[2:]]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["schema"] == "dataviz/analysis-result/v5"
    assert payload["status"] == "failed"
    assert payload["error"]["code"]
    assert payload["next_actions"]
