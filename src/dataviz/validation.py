from __future__ import annotations

from pathlib import Path
from typing import Any

from dataviz import __version__
from dataviz.errors import Diagnostic
from dataviz.semantic_validation import validate_workspace_semantics
from dataviz.workspace.loader import (
    DashboardCatalogEntry,
    LoadedWorkspace,
    load_workspace,
    validate_workspace,
)


VALIDATION_SCHEMA = "dataviz/validation/v3"

_CHECKS = (
    ("schema-contracts", "Workspace and Dashboard schemas"),
    ("adapter-bindings", "Adapter bindings and source compatibility"),
    ("sql-contracts", "SQL files and named parameter contracts"),
    ("data-graph", "Source, Dataset/Interactive Transform, Output and View references"),
    ("content-contracts", "Content interpolation and scoped Control contracts"),
    ("presentation-assets", "Presentation, Renderer and local assets"),
    ("runtime-dependencies", "Runtime, code and package dependencies"),
    ("semantic-effective-config", "Final effective configuration semantics"),
)


def _diagnostic_category(item: Diagnostic) -> str:
    code = item.code or "validation"
    field = item.field or ""
    message = item.message.lower()
    if code.startswith("semantic_") or code.startswith("layout_"):
        return "semantic-effective-config"
    if code.startswith("adapter_") or field == "adapter":
        return "adapter-bindings"
    if code.startswith("sql_"):
        return "sql-contracts"
    if code.startswith("source_asset_"):
        return "data-graph"
    if code.startswith("content_") or "selection" in field or "selection" in message:
        return "content-contracts"
    if (
        code.startswith("presentation_")
        or field.startswith("canvas")
        or "presentation" in message
        or "renderer" in message
    ):
        return "presentation-assets"
    if (
        code.startswith("pyodide_")
        or code.startswith("runtime_asset_")
        or "python_dependencies" in field
        or "code_dependencies" in field
        or "dependency" in message
    ):
        return "runtime-dependencies"
    if (
        field.startswith(("inputs", "views", "sections"))
        or " input" in message
        or "output" in message
        or "reference" in message
    ):
        return "data-graph"
    return "schema-contracts"


def _hint_for(item: Diagnostic) -> str:
    code = item.code or "validation"
    field = item.field or ""
    if code in {"workspace_definition_invalid", "dashboard_invalid"}:
        model = "workspace" if code.startswith("workspace") else "dashboard"
        return f"Compare this file with `dataviz schemas {model} --format json`; remove unknown or retired fields."
    if code == "dashboard_not_found":
        return "Run `dataviz list <workspace>` and use the stable Dashboard id shown there."
    if code == "sql_parameter_undeclared":
        return "Declare every named SQL placeholder as a local Source `query_inputs` key, then bind it to a Dashboard `query_parameters` id."
    if code == "sql_parameter_unused":
        return "Remove the unused Source `query_inputs` entry or reference its local alias as a named SQL placeholder."
    if code == "sql_file_unreadable":
        return "Save the SQL file as UTF-8 and verify that the current user can read it."
    if code == "source_asset_missing":
        return "Add the referenced data/code file, or correct the Source path or file Adapter root."
    if code in {"source_asset_invalid", "source_asset_outside_dashboard"}:
        return "Keep Source assets inside the Dashboard folder, or use a file Adapter whose root contains the data file."
    if code == "view_field_unknown":
        return "Fix the View field name or declare it in the main table Output schema; dynamic Outputs may omit schema only when static field checking is impossible."
    if code == "selection_field_unknown":
        return "Fix the Selection path/binding field or declare it in the selected View input table schema."
    if code.startswith("selection_option_domain_"):
        return (
            "Use `options: {mode: static, choices: [...]}` for a closed enum, or "
            "`options: {mode: infer, source: source:sales/main}` for a data-derived "
            "domain. Interactive Outputs are invalid because they may depend on this Selection."
        )
    if code.startswith("control_dependency_"):
        return (
            "Declare only direct Selection parents with scoped references such as "
            "`dashboard.province`, `section.city`, or `view.dow`. A child may only "
            "reference its current Dashboard, containing Section, or own View; its "
            "immutable option-domain table must expose the child and ancestor fields."
        )
    if code == "file_reader_dependency_unavailable":
        return "Install the Excel reader extra with `pip install 'ai-dataviz[excel]'`, then rerun validate."
    if code.startswith("adapter_") or field == "adapter":
        return "Bind the Dashboard Adapter reference to a Workspace Adapter and define credentials only in `auth/adapters.local.yaml` or environment variables."
    if code.startswith("content_"):
        return (
            "Use `{{ parameters.<id> }}` or a scoped Control reference: "
            "`{{ controls.dashboard.<id> }}`, "
            "`{{ controls.section.<section-id>.<id> }}`, or "
            "`{{ controls.view.<view-id>.<id> }}`. Arbitrary expressions and "
            "cross-scope Control dependencies are not supported."
        )
    if code.startswith("presentation_"):
        return "Fix the referenced id or asset in `presentation.yaml`; delete the override to fall back to the default Renderer."
    if "does not exist" in item.message:
        return "Fix the relative path or add the missing file, then run this preflight again."
    if "unknown query parameter" in item.message.lower():
        return "Bind this node's `query_inputs` entry to a declared Dashboard `query_parameters` id, or remove it."
    if code.startswith("pyodide_bundle_"):
        return (
            "Use the complete official Pyodide distribution at "
            "`runtime.pyodide_bundle_path`; it must include the core Runtime, "
            "matching package.json, pyodide-lock.json, and every locked package "
            "in the declared dependency closure."
        )
    if code.startswith("pyodide_"):
        return "Use a Pyodide/WASM or pure-Python dependency, switch to browser-js, or run the Interactive Transform as server-python."
    if code.startswith("runtime_asset_"):
        return "Use an http(s) URL, or keep the UTF-8 JavaScript file inside the Workspace and reference it with a relative path."
    if code in {"dataset_cycle", "interactive_cycle"}:
        return "Break the reported dependency cycle; every input must point to an earlier explicit Named Output."
    if code == "compute_trigger_ambiguous":
        return "Use one trigger policy for every Interactive Transform that consumes this Compute Control."
    if field.startswith(("inputs", "views", "sections")) or "reference" in item.message.lower():
        return "Use `dataviz context <workspace> <dashboard-id> --format json` to inspect valid node and Output ids."
    if "python_dependencies" in field:
        return "Add a valid requirement and install the Dashboard's declared Python dependencies before querying."
    return "Open the reported file and field, apply the smallest contract fix, then rerun `dataviz validate`."


def _relative_file(root: Path, value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _entry_for_scope(
    workspace: LoadedWorkspace,
    identifier: str,
) -> tuple[DashboardCatalogEntry | None, Diagnostic | None]:
    direct = [entry for entry in workspace.catalog if entry.id == identifier]
    if len(direct) == 1:
        return direct[0], None
    return None, Diagnostic(
        "error",
        f"Unknown dashboard: {identifier}",
        str(workspace.definition_path),
        code="dashboard_not_found",
        details={"available": [entry.id for entry in workspace.catalog]},
    )


def _path_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _filter_scope(
    workspace: LoadedWorkspace,
    diagnostics: list[Diagnostic],
    entry: DashboardCatalogEntry | None,
) -> list[Diagnostic]:
    if entry is None:
        return diagnostics
    other_roots = [item.path for item in workspace.catalog if item.path != entry.path]
    selected: list[Diagnostic] = []
    for item in diagnostics:
        if not item.file:
            selected.append(item)
            continue
        raw = Path(item.file).expanduser()
        path = raw if raw.is_absolute() else workspace.root / raw
        if _path_within(path, entry.path):
            selected.append(item)
        elif not any(_path_within(path, root) for root in other_roots):
            selected.append(item)
    return selected


def _dashboard_for_diagnostic(
    workspace: LoadedWorkspace,
    item: Diagnostic,
) -> str | None:
    if not item.file:
        return None
    raw = Path(item.file).expanduser()
    path = raw if raw.is_absolute() else workspace.root / raw
    matches = [entry for entry in workspace.catalog if _path_within(path, entry.path)]
    if not matches:
        return None
    return max(matches, key=lambda entry: len(entry.path.parts)).id


def _check_report(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reports = []
    for check_id, title in _CHECKS:
        related = [item for item in diagnostics if item["category"] == check_id]
        errors = sum(item["level"] == "error" for item in related)
        warnings = sum(item["level"] == "warning" for item in related)
        advice = sum(item["level"] == "advice" for item in related)
        status = "failed" if errors else "warning" if warnings else "passed"
        reports.append(
            {
                "id": check_id,
                "title": title,
                "status": status,
                "errors": errors,
                "warnings": warnings,
                "advice": advice,
            }
        )
    return reports


def validate_preflight(
    workspace_path: Path | str,
    *,
    dashboard_id: str | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Run deterministic static checks without querying data or starting a Server."""
    root = Path(workspace_path).expanduser().resolve()
    workspace = load_workspace(root)
    scope_entry = None
    scope_error = None
    if dashboard_id:
        scope_entry, scope_error = _entry_for_scope(workspace, dashboard_id)

    raw_diagnostics = validate_workspace(workspace)
    raw_diagnostics.extend(validate_workspace_semantics(workspace))
    raw_diagnostics = _filter_scope(workspace, raw_diagnostics, scope_entry)
    if scope_error:
        raw_diagnostics.append(scope_error)

    diagnostics: list[dict[str, Any]] = []
    for item in raw_diagnostics:
        value = item.as_dict()
        value.update(
            {
                "category": _diagnostic_category(item),
                "dashboard": _dashboard_for_diagnostic(workspace, item),
                "file": _relative_file(root, item.file),
                "hint": _hint_for(item),
            }
        )
        diagnostics.append(value)
    diagnostics.sort(
        key=lambda item: (
            {"error": 0, "warning": 1, "advice": 2}.get(item["level"], 3),
            item["dashboard"] or "",
            item["file"] or "",
            item["field"] or "",
            item["code"],
        )
    )

    errors = sum(item["level"] == "error" for item in diagnostics)
    warnings = sum(item["level"] == "warning" for item in diagnostics)
    advice = sum(item["level"] == "advice" for item in diagnostics)
    status = "invalid" if errors else "valid_with_warnings" if warnings else "valid"
    exit_code = 1 if errors or (strict and warnings) else 0
    scope_id = scope_entry.id if scope_entry else dashboard_id
    rerun = f"dataviz validate {root}"
    if scope_id:
        rerun += f" --dashboard {scope_id}"
    rerun += " --format json"
    if strict:
        rerun += " --strict"
    if exit_code:
        next_actions = [
            "Fix error diagnostics before running a query or exporting HTML.",
            "Apply one contract-level change at a time; do not hide errors in Presentation code.",
            f"Rerun: {rerun}",
        ]
    elif warnings:
        next_actions = [
            "The Dashboard can run, but review warnings before sharing it.",
            f"Rerun after cleanup: {rerun}",
        ]
    else:
        next_actions = [
            "Static contracts are valid; query only the Source or Dashboard branch you need next.",
            (
                f"Next: dataviz query {root} {scope_id} --format json"
                if scope_id
                else "Next: choose a Dashboard from `dataviz list <workspace>`."
            ),
        ]

    checked_count = 1 if scope_entry else len(workspace.catalog) if not dashboard_id else 0
    return {
        "schema": VALIDATION_SCHEMA,
        "tool_version": __version__,
        "mode": "static-preflight",
        "queries_executed": 0,
        "status": status,
        "passed": exit_code == 0,
        "strict": strict,
        "exit_code": exit_code,
        "workspace": {
            "id": workspace.definition.id,
            "path": str(root),
        },
        "scope": {
            "dashboard": scope_id,
            "path": _relative_file(root, str(scope_entry.path)) if scope_entry else None,
        },
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "advice": advice,
            "dashboards_checked": checked_count,
            "checks_passed": sum(item["status"] == "passed" for item in _check_report(diagnostics)),
            "checks_total": len(_CHECKS),
        },
        "checks": _check_report(diagnostics),
        "diagnostics": diagnostics,
        "next_actions": next_actions,
    }


def format_validation_text(report: dict[str, Any]) -> str:
    """Render a compact human view while JSON remains the stable AI contract."""
    icon = "✓" if report["passed"] else "✕"
    summary = report["summary"]
    lines = [
        f"{icon} Dataviz preflight: {report['status']}",
        (
            f"  {summary['dashboards_checked']} dashboard(s) · "
            f"{summary['errors']} error(s) · {summary['warnings']} warning(s) · "
            f"{summary.get('advice', 0)} advice · no queries executed"
        ),
        "",
    ]
    check_icons = {"passed": "✓", "warning": "!", "failed": "✕"}
    for check in report["checks"]:
        lines.append(
            f"{check_icons[check['status']]} {check['title']}"
            + (
                f" ({check['errors']} errors, {check['warnings']} warnings)"
                if check["status"] != "passed"
                else ""
            )
        )
    if report["diagnostics"]:
        lines.extend(["", "Diagnostics"])
    for item in report["diagnostics"]:
        location = item["file"] or "workspace"
        if item["field"]:
            location += f":{item['field']}"
        lines.extend(
            [
                f"[{item['level'].upper()}] {item['code']} · {location}",
                f"  {item['message']}",
                f"  Hint: {item['hint']}",
            ]
        )
    lines.extend(["", "Next"])
    lines.extend(f"- {item}" for item in report["next_actions"])
    return "\n".join(lines)


__all__ = [
    "VALIDATION_SCHEMA",
    "format_validation_text",
    "validate_preflight",
]
