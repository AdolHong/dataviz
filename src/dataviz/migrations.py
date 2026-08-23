from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import yaml

from dataviz.errors import ValidationFailure


MIGRATION_REPORT_SCHEMA = "dataviz/migration-report/v1"
CURRENT_SCHEMAS = {
    "workspace": "dataviz/workspace/v1",
    "dashboard": "dataviz/dashboard/v1",
    "presentation": "dataviz/presentation/v1",
    "source": "dataviz/source/v1",
    "server_transform": "dataviz/server-transform/v1",
    "browser_transform": "dataviz/browser-transform/v1",
}


@dataclass(frozen=True, slots=True)
class MigrationStep:
    source: str
    target: str
    transform: Callable[[dict[str, Any]], dict[str, Any]]
    description: str


MIGRATIONS: dict[str, MigrationStep] = {}


def register_migration(
    source: str, target: str, *, description: str
) -> Callable[[Callable[[dict[str, Any]], dict[str, Any]]], Callable[[dict[str, Any]], dict[str, Any]]]:
    """Register an offline migration without adding a Runtime compatibility path."""

    def decorator(
        transform: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        if source in MIGRATIONS:
            raise RuntimeError(f"Duplicate migration source: {source}")
        MIGRATIONS[source] = MigrationStep(source, target, transform, description)
        return transform

    return decorator


def _definition_kind(path: Path, value: dict[str, Any]) -> str | None:
    kind = value.get("kind")
    if kind in CURRENT_SCHEMAS:
        return str(kind)
    if path.name == "workspace.yaml":
        return "workspace"
    if path.name == "dashboard.yaml":
        return "dashboard"
    if path.name == "presentation.yaml":
        return "presentation"
    return None


def _definition_files(workspace: Path) -> list[Path]:
    ignored = {".dataviz", "dist", ".venv", "__pycache__"}
    return sorted(
        path
        for path in workspace.rglob("*.yaml")
        if not ignored.intersection(path.relative_to(workspace).parts)
        and not (
            "auth" in path.relative_to(workspace).parts
            or path.name in {"adapters.local.yaml", "adapters.example.yaml"}
        )
    )


def _migration_path(source: str, current_schemas: set[str]) -> list[MigrationStep] | None:
    path: list[MigrationStep] = []
    visited: set[str] = set()
    value = source
    while value not in current_schemas:
        if value in visited or value not in MIGRATIONS:
            return None
        visited.add(value)
        step = MIGRATIONS[value]
        path.append(step)
        value = step.target
    return path


def inspect_workspace_migrations(workspace: Path) -> dict[str, Any]:
    root = workspace.resolve()
    if not (root / "workspace.yaml").is_file():
        raise ValidationFailure("Migration requires a Workspace with workspace.yaml", file=root)
    documents: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    current = set(CURRENT_SCHEMAS.values())
    for path in _definition_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as error:
            blockers.append(
                {"file": relative, "code": "invalid_yaml", "message": str(error)}
            )
            continue
        if not isinstance(value, dict):
            continue
        kind = _definition_kind(path, value)
        if kind is None:
            continue
        expected = CURRENT_SCHEMAS[kind]
        schema = value.get("schema")
        document = {"file": relative, "kind": kind, "schema": schema, "expected": expected}
        documents.append(document)
        if schema is None:
            changes.append(
                {
                    **document,
                    "code": "add_schema_header",
                    "description": f"Add explicit {expected}",
                    "steps": [],
                }
            )
        elif schema == expected:
            continue
        else:
            steps = _migration_path(str(schema), current)
            if steps is None or (steps and steps[-1].target != expected):
                blockers.append(
                    {
                        **document,
                        "code": "unsupported_schema_version",
                        "message": (
                            f"No registered offline migration from {schema} to {expected}"
                        ),
                    }
                )
            else:
                changes.append(
                    {
                        **document,
                        "code": "registered_migration",
                        "description": " → ".join(
                            [str(schema), *(step.target for step in steps)]
                        ),
                        "steps": [step.source for step in steps],
                    }
                )
    return {
        "schema": MIGRATION_REPORT_SCHEMA,
        "workspace": str(root),
        "mode": "dry-run",
        "current_schemas": CURRENT_SCHEMAS,
        "documents": documents,
        "changes": changes,
        "blockers": blockers,
        "changed": [],
        "ready": not blockers,
    }


def _add_schema_header(text: str, schema: str) -> str:
    lines = text.splitlines(keepends=True)
    index = 0
    while index < len(lines) and (not lines[index].strip() or lines[index].lstrip().startswith("#")):
        index += 1
    if index < len(lines) and lines[index].strip() == "---":
        index += 1
    lines.insert(index, f"schema: {schema}\n")
    return "".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.dataviz-migrate-{uuid4().hex}")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def migrate_workspace(workspace: Path, *, apply: bool = False) -> dict[str, Any]:
    report = inspect_workspace_migrations(workspace)
    if not apply or report["blockers"]:
        return report
    root = Path(report["workspace"])
    changed: list[dict[str, Any]] = []
    for change in report["changes"]:
        path = root / change["file"]
        text = path.read_text(encoding="utf-8")
        if change["code"] == "add_schema_header":
            _atomic_write(path, _add_schema_header(text, change["expected"]))
        else:
            value = yaml.safe_load(text)
            for source in change["steps"]:
                step = MIGRATIONS[source]
                value = step.transform(value)
                value["schema"] = step.target
            _atomic_write(
                path,
                yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
            )
        changed.append(
            {"file": change["file"], "schema": change["expected"], "code": change["code"]}
        )
    report["mode"] = "apply"
    report["changed"] = changed
    return report
