from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import builtins
import tomllib

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from dataviz.cli import _require_remote_bind_opt_in, app
from dataviz.frontend_adapters import frontend_adapter_catalog, frontend_adapter_source
from dataviz.protocols import CURRENT_PROTOCOL_SCHEMAS
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


def test_visual_check_has_a_dedicated_extra_and_copyable_missing_dependency_hint(
    monkeypatch,
):
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["optional-dependencies"]["visual-check"] == [
        "playwright>=1.55"
    ]
    original_import = builtins.__import__

    def without_playwright(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("simulated missing Playwright")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_playwright)
    result = CliRunner().invoke(
        app,
        ["visual-check", str(MINIMAL_WORKSPACE), "sales-overview"],
    )

    assert result.exit_code != 0
    assert "pip install" in result.output
    assert "ai-dataviz[visual-check]" in result.output


def test_plotly_is_a_direct_browser_asset_not_a_python_dependency():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = metadata["project"]["dependencies"]

    assert not any(requirement.lower().startswith("plotly") for requirement in dependencies)
    result = CliRunner().invoke(app, ["version", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["plotly_js"] == "4.0.0"
    assert payload["protocols"] == CURRENT_PROTOCOL_SCHEMAS


def _init_workspace(path: Path) -> Path:
    result = CliRunner().invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output
    return path


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
    assert "engine" not in view["template_contracts"]["radar"]
    assert (
        view["json_schema"]["x-dataviz-template-contracts"]
        == view["template_contracts"]
    )


def test_dsl_schema_versions_are_literals_not_descriptive_strings():
    assert DashboardDefinition.model_validate(
        {"schema": "dataviz/dashboard/v17", "kind": "dashboard", "id": "current"}
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
                "schema": "dataviz/dashboard/v17",
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
        "dataviz/dashboard/v17" in str(item.details)
        for item in workspace.load_diagnostics
        if item.code == "dashboard_invalid"
    )

    result = CliRunner().invoke(app, ["migrate", str(root)])
    assert result.exit_code != 0
    assert "No such command" in result.output

    templates = CliRunner().invoke(app, ["templates"])
    assert templates.exit_code != 0
    assert "No such command" in templates.output


def test_authoring_evaluation_is_not_exposed_or_shipped_by_the_product():
    assert "authoring" not in {group.name for group in app.registered_groups}
    assert importlib.util.find_spec("dataviz.authoring_evaluation") is None
    assert importlib.util.find_spec("dataviz.authoring_log") is None
    included = {path.as_posix() for path in release_zip.included_files()}
    assert not any("authoring_evaluation" in path for path in included)
    assert not any(path.startswith("tools/authoring-evaluation/") for path in included)


def test_current_design_and_plan_only_document_the_current_cli_contract():
    documents = {
        name: (ROOT / name).read_text(encoding="utf-8")
        for name in ("DESIGN.md", "plan.md")
    }
    forbidden = (
        "0.11.0",
        "analyze_run_succeeded",
        "`analyze all",
        "`analyze search",
        "`analyze run",
        "`analyze result",
        "`inspect-layout`",
        "`components --check`",
    )
    for name, content in documents.items():
        assert not any(term in content for term in forbidden), name
    design = documents["DESIGN.md"]
    assert "catalog search" in design
    assert "catalog describe" in design
    assert "run_succeeded" in design
    package_version = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    assert package_version in documents["plan.md"]


def test_current_user_docs_do_not_advertise_removed_cli_surfaces():
    documents = [
        (ROOT / "README.md").read_text(encoding="utf-8"),
        (ROOT / "docs/analysis-plane.md").read_text(encoding="utf-8"),
    ]
    forbidden = ("dataviz analyze ", "`inspect-layout`", "--compact")
    for content in documents:
        assert not any(term in content for term in forbidden)


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
        "dataviz-skill.md",
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


def test_release_source_archives_include_the_skill_and_browser_runtimes():
    included = {path.relative_to(ROOT).as_posix() for path in release_zip.included_files()}
    assert "dataviz-skill.md" in included
    assert "src/dataviz/vendor/plotly/plotly-4.0.0.min.js" in included
    assert "src/dataviz/vendor/plotly/LICENSE" in included


def test_reference_frontend_adapter_is_exportable_and_has_no_canvas_runtime_dependency(
    tmp_path: Path,
):
    catalog = frontend_adapter_catalog()
    source = frontend_adapter_source("web-component")
    output = tmp_path / "adapter.js"
    result = CliRunner().invoke(
        app, ["frontend-adapters", "web-component", "--output", str(output)]
    )

    assert catalog["web-component"]["protocol"] == "dataviz/runtime/v13"
    assert catalog["web-component"]["dependency"] == "none"
    assert "DatavizRuntimeV3Client" in source
    assert "datavizRuntime." not in source
    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8") == source
