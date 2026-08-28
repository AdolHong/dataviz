from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from dataviz.auth import AdapterResolver
from dataviz.execution.node_support import hash_path
from dataviz.redaction import redact_text
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


MAX_INLINE_CODE_BYTES = 262_144


def analysis_reference_closure(
    dashboard: LoadedDashboard,
    references: Iterable[str],
) -> set[str]:
    contract = dashboard.dependency_contract
    query_nodes: set[str] = set()
    interactive_nodes: set[str] = set()
    pending = [value.split("::", 1)[-1] for value in references]
    while pending:
        reference = pending.pop()
        node_id = reference.split("/", 1)[0]
        if node_id.startswith(("source:", "dataset:")):
            query_nodes.add(node_id)
            continue
        if not node_id.startswith("interactive:"):
            continue
        transform_id = node_id.split(":", 1)[1]
        for identifier in contract.interactive_closure(transform_id):
            interactive_nodes.add(f"interactive:{identifier}")
            pending.extend(contract.interactive_inputs[identifier].values())
    if query_nodes:
        query_nodes = set(contract.query_closure(query_nodes))
    return query_nodes | interactive_nodes


def _display_path(workspace_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(workspace_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _asset(
    workspace_root: Path,
    definition_path: Path,
    value: str,
    *,
    role: str,
    include_code: bool,
    secrets: tuple[str, ...],
) -> dict[str, Any]:
    path = (definition_path.parent / value).resolve()
    result: dict[str, Any] = {
        "role": role,
        "path": _display_path(workspace_root, path),
        "exists": path.is_file(),
    }
    if not path.is_file():
        return result
    result.update(content_hash=hash_path(path), bytes=path.stat().st_size)
    if role == "data" or not include_code:
        return result
    if path.stat().st_size > MAX_INLINE_CODE_BYTES:
        result["content_omitted"] = "asset exceeds 262144 bytes"
        return result
    try:
        result["content"] = redact_text(path.read_text(encoding="utf-8"), secrets)
    except (OSError, UnicodeError):
        result["content_omitted"] = "asset is not readable UTF-8 text"
    return result


def inspect_analysis_closure(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
    references: Iterable[str],
    *,
    include_code: bool = False,
) -> dict[str, Any]:
    nodes = analysis_reference_closure(dashboard, references)
    try:
        secrets = AdapterResolver(workspace.root).all_redaction_values()
    except Exception:
        secrets = ()
    inspected: list[dict[str, Any]] = []
    for node_id in sorted(nodes):
        kind, identifier = node_id.split(":", 1)
        if kind == "source":
            definition_path, definition = dashboard.sources[identifier]
        elif kind == "dataset":
            definition_path, definition = dashboard.dataset_transforms[identifier]
        else:
            definition_path, definition = dashboard.interactive_transforms[identifier]
        assets: list[dict[str, Any]] = []
        code = getattr(definition, "code", None)
        if code:
            assets.append(
                _asset(
                    workspace.root,
                    definition_path,
                    code,
                    role="code",
                    include_code=include_code,
                    secrets=secrets,
                )
            )
        for dependency in getattr(definition, "code_dependencies", ()):
            assets.append(
                _asset(
                    workspace.root,
                    definition_path,
                    dependency,
                    role="code_dependency",
                    include_code=include_code,
                    secrets=secrets,
                )
            )
        data_path = getattr(definition, "path", None)
        if data_path:
            assets.append(
                _asset(
                    workspace.root,
                    definition_path,
                    data_path,
                    role="data",
                    include_code=False,
                    secrets=secrets,
                )
            )
        inspected.append(
            {
                "node_id": node_id,
                "node_kind": getattr(definition, "type", None) or kind,
                "runtime": getattr(definition, "runtime", "server"),
                "definition_path": _display_path(workspace.root, definition_path),
                "definition": definition.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
                "assets": assets,
            }
        )
    return {
        "nodes": inspected,
        "node_count": len(inspected),
        "code_included": include_code,
        "max_inline_code_bytes": MAX_INLINE_CODE_BYTES,
    }
