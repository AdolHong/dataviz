from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from dataviz.authoring_log import AUTHORING_LOG_NAME, authoring_log_report
from dataviz.cli import _require_remote_bind_opt_in, app
from dataviz.frontend_adapters import frontend_adapter_catalog, frontend_adapter_source
from dataviz.schema_docs import CURRENT_SCHEMAS, schema_catalog, schema_model_contract
from dataviz.workspace import load_workspace
from dataviz.workspace.models import (
    DashboardDefinition,
    RuntimeDefinition,
    SOURCE_DEFINITION_ADAPTER,
)


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_WORKSPACE = ROOT / "examples" / "minimal-workspace"
_RELEASE_SPEC = importlib.util.spec_from_file_location(
    "dataviz_release_zip",
    ROOT / "scripts" / "build_release_zip.py",
)
assert _RELEASE_SPEC is not None and _RELEASE_SPEC.loader is not None
release_zip = importlib.util.module_from_spec(_RELEASE_SPEC)
_RELEASE_SPEC.loader.exec_module(release_zip)


def test_unauthenticated_server_requires_explicit_remote_bind_opt_in():
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["serve", str(MINIMAL_WORKSPACE), "--host", "0.0.0.0"],
    )

    assert result.exit_code != 0
    assert "no authentication" in result.output
    _require_remote_bind_opt_in("localhost", allow_remote=False)
    _require_remote_bind_opt_in("::1", allow_remote=False)
    _require_remote_bind_opt_in("0.0.0.0", allow_remote=True)


def _init_workspace(path: Path) -> Path:
    result = CliRunner().invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output
    return path


def _prepared_trial(
    root: Path,
    *,
    task: str,
    approach: str,
    trial_id: str,
    pass_checks: bool = True,
) -> Path:
    runner = CliRunner()
    destination = root / approach
    prepared = runner.invoke(
        app,
        [
            "authoring",
            "prepare",
            task,
            str(destination),
            "--approach",
            approach,
            "--trial-id",
            trial_id,
        ],
    )
    assert prepared.exit_code == 0, prepared.output
    manifest = json.loads(prepared.output)
    if pass_checks:
        for check in manifest["acceptance"]:
            assessed = runner.invoke(
                app,
                [
                    "authoring",
                    "assess",
                    str(destination),
                    check["id"],
                    "--status",
                    "passed",
                    "--assessor",
                    "automation",
                    "--evidence",
                    f"test evidence for {check['id']}",
                ],
            )
            assert assessed.exit_code == 0, assessed.output
    return destination


def test_generated_schema_cli_uses_strict_installed_models():
    catalog = schema_catalog()
    dashboard = schema_model_contract("dashboard", full=True)
    result = CliRunner().invoke(
        app, ["schemas", "source", "--full", "--format", "json"]
    )

    assert catalog["models"]["dashboard"]["contract_schema"] == CURRENT_SCHEMAS["dashboard"]
    assert dashboard["json_schema"]["properties"]["schema"]["const"] == CURRENT_SCHEMAS["dashboard"]
    assert next(field for field in dashboard["fields"] if field["name"] == "schema")["required"] is True
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["contract_schema"] == CURRENT_SCHEMAS["source"]
    assert payload["discriminator"] == "type"
    assert {item["type"] for item in payload["variants"]} == {
        "file",
        "sql",
        "python",
    }
    definitions = payload["json_schema"]["$defs"]
    assert all(
        definitions[item["$ref"].rsplit("/", 1)[-1]]["additionalProperties"]
        is False
        for item in payload["json_schema"]["oneOf"]
    )

    view = schema_model_contract("view", full=True)
    assert view["template_contracts"]["table"]["required"] == ["input"]
    assert view["template_contracts"]["radar"]["engine"] == "echarts"
    assert (
        view["json_schema"]["x-dataviz-template-contracts"]
        == view["template_contracts"]
    )


def test_dsl_schema_versions_are_literals_not_descriptive_strings():
    assert DashboardDefinition.model_validate(
        {"schema": "dataviz/dashboard/v7", "kind": "dashboard", "id": "current"}
    ).id == "current"
    with pytest.raises(ValidationError):
        DashboardDefinition.model_validate(
            {"schema": "dataviz/dashboard/v1", "kind": "dashboard", "id": "old"}
        )
    with pytest.raises(ValidationError):
        SOURCE_DEFINITION_ADAPTER.validate_python(
            {
                "schema": "dataviz/source/v0",
                "kind": "source",
                "id": "old",
                "type": "file",
                "outputs": {"main": {"kind": "table"}},
            }
        )


def test_plotly_runtime_is_explicitly_bundled_not_a_ignored_asset_setting():
    assert RuntimeDefinition.model_validate({"plotly_js": "bundled"}).plotly_js == "bundled"
    with pytest.raises(ValidationError):
        RuntimeDefinition.model_validate({"plotly_js": "https://example.invalid/plotly.js"})


@pytest.mark.parametrize(
    "identifier",
    ["has space", "中文", "a/b", "ends-with-dot.", "CON", "nul.txt"],
)
def test_machine_identifiers_are_portable_and_unambiguous(identifier: str):
    with pytest.raises(ValidationError):
        DashboardDefinition.model_validate(
            {
                "schema": "dataviz/dashboard/v7",
                "kind": "dashboard",
                "id": identifier,
            }
        )


def test_old_dashboard_is_rejected_and_no_migration_command_is_exposed(tmp_path: Path):
    root = tmp_path / "workspace"
    dashboard = root / "dashboards" / "hello"
    dashboard.mkdir(parents=True)
    (root / "workspace.yaml").write_text(
        "kind: workspace\nid: migration\ntitle: Migration\n", encoding="utf-8"
    )
    (dashboard / "dashboard.yaml").write_text(
        "schema: dataviz/dashboard/v1\nkind: dashboard\nid: hello\n",
        encoding="utf-8",
    )
    workspace = load_workspace(root)
    entry = next(item for item in workspace.catalog if item.id == "hello")
    assert entry.status == "invalid"
    assert any(
        "dataviz/dashboard/v7" in str(item.details)
        for item in workspace.load_diagnostics
        if item.code == "dashboard_invalid"
    )

    result = CliRunner().invoke(app, ["migrate", str(root)])
    assert result.exit_code != 0
    assert "No such command" in result.output

    templates = CliRunner().invoke(app, ["templates"])
    assert templates.exit_code != 0
    assert "No such command" in templates.output


def test_authoring_log_records_real_cost_friction_and_unknown_measurements(tmp_path: Path):
    root = _init_workspace(tmp_path / "workspace")
    runner = CliRunner()
    started = runner.invoke(
        app,
        [
            "authoring",
            "start",
            str(root),
            "--dashboard",
            "hello",
            "--task",
            "Add a line View",
            "--model",
            "test-model",
        ],
    )
    assert started.exit_code == 0, started.output
    session_id = json.loads(started.output)["session_id"]

    note = runner.invoke(
        app,
        [
            "authoring",
            "note",
            str(root),
            session_id,
            "--category",
            "documentation",
            "--reference",
            "docs charts",
            "--message",
            "The aggregation default was unclear",
        ],
    )
    assert note.exit_code == 0, note.output
    finished = runner.invoke(
        app,
        [
            "authoring",
            "finish",
            str(root),
            session_id,
            "--outcome",
            "success",
            "--first-attempt",
            "failure",
            "--correction-rounds",
            "2",
            "--input-tokens",
            "3100",
            "--output-tokens",
            "900",
            "--docs-used",
            "quickstart",
            "--docs-used",
            "charts",
        ],
    )
    assert finished.exit_code == 0, finished.output

    lines = (root / AUTHORING_LOG_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert all(json.loads(line)["schema"] == "dataviz/authoring-event/v3" for line in lines)
    report = authoring_log_report(root)
    assert report["metrics"]["first_attempt_success_rate"] == 0.0
    assert report["metrics"]["mean_correction_rounds"] == 2
    assert report["metrics"]["reported_input_tokens"] == 3100
    assert report["metrics"]["friction_by_category"] == {"documentation": 1}
    assert report["sessions"][0]["docs_used"] == ["charts", "quickstart"]

    second = runner.invoke(
        app,
        ["authoring", "start", str(root), "--task", "Unknown-token task"],
    )
    second_id = json.loads(second.output)["session_id"]
    unknown = runner.invoke(
        app,
        ["authoring", "finish", str(root), second_id, "--outcome", "partial"],
    )
    assert unknown.exit_code == 0, unknown.output
    assert json.loads(unknown.output)["token_source"] == "unknown"


def test_focused_context_prompts_ai_to_leave_shareable_feedback():
    result = CliRunner().invoke(
        app,
        [
            "context",
            str(MINIMAL_WORKSPACE),
            "sales-overview",
            "--focus",
            "view:revenue-trend",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    prompt = json.loads(result.output)["authoring_feedback"]
    assert prompt["log"] == AUTHORING_LOG_NAME
    assert "authoring start" in prompt["start"]
    assert "Report real measurements only" in prompt["rule"]


def test_paired_authoring_evaluation_uses_real_measurements_only(tmp_path: Path):
    root = _init_workspace(tmp_path / "evaluation")
    runner = CliRunner()
    session_ids = {}
    for approach in ("dataviz", "standalone-html"):
        trial = _prepared_trial(
            tmp_path / f"trial-{approach}",
            task="default-dashboard",
            approach=approach,
            trial_id="trial-001",
        )
        started = runner.invoke(
            app,
            [
                "authoring",
                "start",
                str(root),
                "--trial-dir",
                str(trial),
                "--model",
                "same-model",
                "--tool",
                "same-client",
            ],
        )
        assert started.exit_code == 0, started.output
        started_payload = json.loads(started.output)
        assert "--trial-dir" in started_payload["next_steps"][-1]
        assert "authoring assess" in started_payload["next_steps"][0]
        session_ids[approach] = started_payload["session_id"]
        session_ids[f"{approach}-trial"] = trial

    dataviz_finished = runner.invoke(
        app,
        [
            "authoring",
            "finish",
            str(root),
            session_ids["dataviz"],
            "--outcome",
            "success",
            "--first-attempt",
            "success",
            "--correction-rounds",
            "0",
            "--input-tokens",
            "2000",
            "--output-tokens",
            "500",
            "--trial-dir",
            str(session_ids["dataviz-trial"]),
        ],
    )
    html_finished = runner.invoke(
        app,
        [
            "authoring",
            "finish",
            str(root),
            session_ids["standalone-html"],
            "--outcome",
            "success",
            "--first-attempt",
            "failure",
            "--correction-rounds",
            "2",
            "--input-tokens",
            "800",
            "--output-tokens",
            "3200",
            "--trial-dir",
            str(session_ids["standalone-html-trial"]),
        ],
    )
    assert dataviz_finished.exit_code == 0, dataviz_finished.output
    assert html_finished.exit_code == 0, html_finished.output

    tasks = runner.invoke(app, ["authoring", "tasks", "--format", "json"])
    protocol = runner.invoke(app, ["authoring", "protocol", "--format", "json"])
    compared = runner.invoke(
        app, ["authoring", "compare", str(root), "--format", "json"]
    )

    assert tasks.exit_code == 0, tasks.output
    assert set(json.loads(tasks.output)["tasks"]) == {
        "default-dashboard",
        "three-level-selection",
        "dataset-multi-output",
        "interactive-runtime-matrix",
        "custom-renderer",
    }
    assert protocol.exit_code == 0, protocol.output
    assert "Never estimate" in json.loads(protocol.output)["token_rule"]
    assert compared.exit_code == 0, compared.output
    report = json.loads(compared.output)
    assert report["complete_pairs"] == 1
    assert report["comparable_pairs"] == 1
    assert report["quality_pairs"] == 1
    assert report["diagnostics"] == []
    pair = report["paired_trials"][0]
    assert pair["task_match"] is True
    assert pair["model_match"] is True
    assert pair["tool_match"] is True
    assert pair["task_contract_match"] is True
    assert pair["fixture_match"] is True
    assert pair["comparable"] is True
    assert pair["quality_passed"] is True
    assert pair["metrics"]["input_tokens"]["delta_dataviz_minus_html"] == 1200
    assert pair["metrics"]["output_tokens"]["dataviz_reduction_percent"] == 84.4
    assert report["approaches"]["dataviz"]["first_attempt_success_rate"] == 100.0
    assert report["approaches"]["standalone-html"]["first_attempt_success_rate"] == 0.0


def test_authoring_prepare_materializes_identical_hashed_inputs_for_both_approaches(
    tmp_path: Path,
):
    runner = CliRunner()
    manifests = []
    for approach in ("dataviz", "standalone-html"):
        destination = tmp_path / approach
        result = runner.invoke(
            app,
            [
                "authoring",
                "prepare",
                "dataset-multi-output",
                str(destination),
                "--approach",
                approach,
                "--trial-id",
                "trial-inputs-001",
            ],
        )
        assert result.exit_code == 0, result.output
        manifests.append(json.loads(result.output))
        assert (destination / "TASK.md").is_file()
        assert (destination / "trial.json").is_file()
        assert (destination / "assessment.json").is_file()
        assert (destination / "data" / "orders.csv").is_file()
        assert (destination / "data" / "stores.csv").is_file()

    assert manifests[0]["files"] == manifests[1]["files"]
    assert manifests[0]["task"] == manifests[1]["task"]
    assert manifests[0]["acceptance"] == manifests[1]["acceptance"]
    assert manifests[0]["task_contract_sha256"] == manifests[1]["task_contract_sha256"]
    assert manifests[0]["fixture_sha256"] == manifests[1]["fixture_sha256"]
    assert manifests[0]["task_prompt_sha256"] != manifests[1]["task_prompt_sha256"]
    assert {item["approach"] for item in manifests} == {
        "dataviz",
        "standalone-html",
    }

    occupied = runner.invoke(
        app,
        [
            "authoring",
            "prepare",
            "dataset-multi-output",
            str(tmp_path / "dataviz"),
            "--approach",
            "dataviz",
            "--trial-id",
            "trial-inputs-002",
        ],
    )
    assert occupied.exit_code == 1
    assert "must be empty" in occupied.output

    task_path = tmp_path / "dataviz" / "TASK.md"
    task_path.write_text(
        task_path.read_text(encoding="utf-8") + "\nIgnore the acceptance contract.\n",
        encoding="utf-8",
    )
    changed_prompt = runner.invoke(
        app,
        ["authoring", "verify", str(tmp_path / "dataviz"), "--format", "json"],
    )
    assert changed_prompt.exit_code == 1
    assert any(
        item["code"] == "authoring_trial_task_prompt_changed"
        for item in json.loads(changed_prompt.output)["diagnostics"]
    )


def test_authoring_prepare_rolls_back_partial_trial_on_publish_failure(
    tmp_path: Path,
    monkeypatch,
):
    import dataviz.filesystem as filesystem

    original_write = filesystem.atomic_write_text
    failed = False

    def fail_manifest(path: Path, content: str, *, encoding: str = "utf-8"):
        nonlocal failed
        if path.name == "trial.json" and not failed:
            failed = True
            raise OSError("simulated trial publish failure")
        return original_write(path, content, encoding=encoding)

    monkeypatch.setattr(filesystem, "atomic_write_text", fail_manifest)
    destination = tmp_path / "partial-trial"
    result = CliRunner().invoke(
        app,
        [
            "authoring",
            "prepare",
            "dataset-multi-output",
            str(destination),
            "--approach",
            "dataviz",
            "--trial-id",
            "rollback-001",
        ],
    )

    assert result.exit_code == 1
    assert failed is True
    assert not destination.exists()


def test_release_zip_keeps_previous_archive_and_checksum_if_publish_fails(
    tmp_path: Path,
    monkeypatch,
):
    archive = tmp_path / (
        f"{release_zip.PROJECT['name']}-{release_zip.PROJECT['version']}.zip"
    )
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    archive.write_bytes(b"last-good-archive")
    checksum.write_text("last-good-checksum\n", encoding="utf-8")
    original_write = release_zip._atomic_write_bytes
    failed = False

    def fail_checksum(path: Path, content: bytes):
        nonlocal failed
        if path == checksum and not failed:
            failed = True
            raise OSError("simulated checksum publish failure")
        return original_write(path, content)

    monkeypatch.setattr(release_zip, "_atomic_write_bytes", fail_checksum)

    with pytest.raises(OSError, match="checksum publish failure"):
        release_zip.build_release_zip(tmp_path)

    assert failed is True
    assert archive.read_bytes() == b"last-good-archive"
    assert checksum.read_text(encoding="utf-8") == "last-good-checksum\n"


def test_release_inputs_exclude_local_credentials_and_reject_symlinks(
    tmp_path: Path,
    monkeypatch,
):
    root = tmp_path / "project"
    package = root / "src" / "dataviz"
    package.mkdir(parents=True)
    (root / "docs").mkdir()
    for relative in (
        "pyproject.toml",
        "setup.py",
        "README.md",
        "DESIGN.md",
        "plan.md",
        "MANIFEST.in",
        "CHANGELOG.md",
    ):
        (root / relative).write_text("placeholder\n", encoding="utf-8")
    (package / "__init__.py").write_text('__version__ = "0.1.4"\n', encoding="utf-8")
    auth = package / "gallery" / "auth"
    auth.mkdir(parents=True)
    local_credentials = auth / "adapters.local.yaml"
    local_credentials.write_text("password: secret\n", encoding="utf-8")
    monkeypatch.setattr(release_zip, "ROOT", root)

    assert local_credentials not in release_zip.included_files()

    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = True\n", encoding="utf-8")
    (package / "linked.py").symlink_to(outside)
    with pytest.raises(RuntimeError, match="symbolic links"):
        release_zip.included_files()


def test_release_version_sources_match():
    release_zip.verify_release_version()


def test_authoring_comparison_handles_an_empty_measurement_workspace(tmp_path: Path):
    root = _init_workspace(tmp_path / "empty-evaluation")

    result = CliRunner().invoke(
        app, ["authoring", "compare", str(root), "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["sessions"] == 0
    assert payload["complete_pairs"] == 0
    assert payload["approaches"]["dataviz"]["success_rate"] is None
    assert payload["approaches"]["standalone-html"]["success_rate"] is None


def test_authoring_trial_detects_changed_inputs_and_requires_acceptance_evidence(
    tmp_path: Path,
):
    workspace = _init_workspace(tmp_path / "measurement")
    trial = _prepared_trial(
        tmp_path / "unassessed",
        task="default-dashboard",
        approach="dataviz",
        trial_id="quality-001",
        pass_checks=False,
    )
    runner = CliRunner()
    verified = runner.invoke(
        app, ["authoring", "verify", str(trial), "--format", "json"]
    )
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.output)["quality_passed"] is False

    started = runner.invoke(
        app,
        [
            "authoring",
            "start",
            str(workspace),
            "--trial-dir",
            str(trial),
            "--model",
            "same-model",
            "--tool",
            "same-client",
        ],
    )
    assert started.exit_code == 0, started.output
    wrong_approach = _prepared_trial(
        tmp_path / "wrong-approach",
        task="default-dashboard",
        approach="standalone-html",
        trial_id="quality-001",
    )
    wrong_finish = runner.invoke(
        app,
        [
            "authoring",
            "finish",
            str(workspace),
            json.loads(started.output)["session_id"],
            "--outcome",
            "failed",
            "--trial-dir",
            str(wrong_approach),
        ],
    )
    assert wrong_finish.exit_code == 1
    assert "same verified trial" in wrong_finish.output
    rejected = runner.invoke(
        app,
        [
            "authoring",
            "finish",
            str(workspace),
            json.loads(started.output)["session_id"],
            "--outcome",
            "success",
            "--trial-dir",
            str(trial),
        ],
    )
    assert rejected.exit_code == 1
    assert "every acceptance check" in rejected.output

    (trial / "data" / "sales.csv").write_text("changed\n", encoding="utf-8")
    changed = runner.invoke(
        app, ["authoring", "verify", str(trial), "--format", "json"]
    )
    assert changed.exit_code == 1
    payload = json.loads(changed.output)
    assert payload["integrity_passed"] is False
    assert any(
        item["code"] == "authoring_trial_fixture_changed"
        for item in payload["diagnostics"]
    )


def test_authoring_comparison_does_not_claim_a_win_for_mismatched_pairs(
    tmp_path: Path,
):
    root = _init_workspace(tmp_path / "mismatched-evaluation")
    runner = CliRunner()
    sessions = []
    for approach, model in (("dataviz", "model-a"), ("standalone-html", "model-b")):
        trial = _prepared_trial(
            tmp_path / f"mismatch-{approach}",
            task="default-dashboard",
            approach=approach,
            trial_id="mismatch-001",
        )
        started = runner.invoke(
            app,
            [
                "authoring",
                "start",
                str(root),
                "--trial-dir",
                str(trial),
                "--model",
                model,
                "--tool",
                "same-client",
            ],
        )
        assert started.exit_code == 0, started.output
        sessions.append((json.loads(started.output)["session_id"], trial))
    for session_id, trial in sessions:
        finished = runner.invoke(
            app,
            [
                "authoring",
                "finish",
                str(root),
                session_id,
                "--outcome",
                "success",
                "--first-attempt",
                "success",
                "--correction-rounds",
                "0",
                "--input-tokens",
                "100",
                "--output-tokens",
                "100",
                "--trial-dir",
                str(trial),
            ],
        )
        assert finished.exit_code == 0, finished.output

    compared = runner.invoke(
        app, ["authoring", "compare", str(root), "--format", "json"]
    )
    report = json.loads(compared.output)
    assert report["complete_pairs"] == 1
    assert report["comparable_pairs"] == 0
    assert report["quality_pairs"] == 0
    assert report["paired_aggregate"]["input_tokens"]["paired_samples"] == 0
    assert report["diagnostics"][0]["code"] == "authoring_trial_identity_mismatch"


def test_reference_frontend_adapter_is_exportable_and_has_no_canvas_runtime_dependency(
    tmp_path: Path,
):
    catalog = frontend_adapter_catalog()
    source = frontend_adapter_source("web-component")
    output = tmp_path / "adapter.js"
    result = CliRunner().invoke(
        app, ["frontend-adapters", "web-component", "--output", str(output)]
    )

    assert catalog["web-component"]["protocol"] == "dataviz/runtime/v5"
    assert catalog["web-component"]["dependency"] == "none"
    assert "DatavizRuntimeV3Client" in source
    assert "datavizRuntime." not in source
    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8") == source
