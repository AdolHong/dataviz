from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from dataviz.errors import ExecutionFailure
from dataviz.execution.node_support import hash_path
from dataviz.execution.plan import compile_plan
from dataviz.execution.results import RunResult
from dataviz.workspace.loader import LoadedDashboard


QUERY_CONTRACT_VERSION = "dataviz/query-contract/v1"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ExecutionFailure(
            "Query dependency escapes the Dashboard folder",
            details={
                "code": "query_run_contract_changed",
                "path": str(path),
                "action": "Run dataviz validate, then run query again",
            },
        ) from error


def _analysis_asset_reference(dashboard: LoadedDashboard, path: Path) -> str | None:
    overlay = dashboard.analysis_overlay or {}
    for asset in overlay.get("assets", ()):
        if Path(asset.get("resolved_path", "")).resolve() == path.resolve():
            return f"@analysis-overlay/{asset['target']}/{asset['field']}"
    return None


def _asset_fingerprints(
    dashboard: LoadedDashboard,
    definition_path: Path,
    definition: Any,
) -> dict[str, str]:
    values: list[str] = []
    code = getattr(definition, "code", None)
    if code:
        values.append(code)
    values.extend(getattr(definition, "code_dependencies", []))
    result: dict[str, str] = {}
    for value in values:
        path = (definition_path.parent / value).resolve()
        try:
            relative = _relative(path, dashboard.root)
        except ExecutionFailure:
            relative = _analysis_asset_reference(dashboard, path)
            if relative is None:
                raise
        try:
            result[relative] = hash_path(path)
        except (OSError, ValueError) as error:
            raise ExecutionFailure(
                "Query dependency is unavailable",
                details={
                    "code": "query_run_contract_changed",
                    "path": relative,
                    "action": "Run dataviz validate, then run query again",
                },
            ) from error
    return result


def query_contract_fingerprint(
    dashboard: LoadedDashboard,
    node_ids: Iterable[str],
) -> str:
    """Fingerprint the Query semantics that produced a Run's Base Outputs."""
    entries: list[dict[str, Any]] = []
    for node_id in sorted(set(node_ids)):
        if node_id.startswith("source:"):
            local_id = node_id.split(":", 1)[1]
            item = dashboard.sources.get(local_id)
        elif node_id.startswith("dataset:"):
            local_id = node_id.split(":", 1)[1]
            item = dashboard.dataset_transforms.get(local_id)
        else:
            item = None
        if item is None:
            raise ExecutionFailure(
                "Query Run references a node no longer present in the Dashboard",
                details={
                    "code": "query_run_contract_changed",
                    "dashboard": dashboard.definition.id,
                    "node_id": node_id,
                    "action": "Run query again",
                },
            )
        definition_path, definition = item
        entries.append(
            {
                "node_id": node_id,
                "definition_path": _relative(definition_path, dashboard.root),
                "definition": definition.model_dump(mode="json", by_alias=True),
                "code_assets": _asset_fingerprints(
                    dashboard,
                    definition_path,
                    definition,
                ),
            }
        )
    payload = {
        "schema": QUERY_CONTRACT_VERSION,
        "dashboard": dashboard.definition.id,
        "adapters": dashboard.definition.adapters,
        "query_parameters": [
            item.model_dump(mode="json", by_alias=True)
            for item in dashboard.definition.query_parameters
        ],
        "nodes": entries,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ensure_query_run_compatible(
    dashboard: LoadedDashboard,
    result: RunResult,
) -> None:
    """Reject a Run when the current Dashboard would interpret it differently."""
    if result.dashboard != dashboard.definition.id:
        raise ExecutionFailure(
            "Query Run belongs to another Dashboard",
            details={
                "code": "query_run_dashboard_mismatch",
                "run_dashboard": result.dashboard,
                "dashboard": dashboard.definition.id,
            },
        )
    current_plan = compile_plan(
        dashboard,
        targets=(result.query_targets if result.query_scope == "targets" else None),
    )
    missing_nodes = sorted(set(current_plan.nodes) - set(result.query_nodes))
    current_hash = query_contract_fingerprint(dashboard, result.query_nodes)
    if missing_nodes or current_hash != result.query_contract_hash:
        raise ExecutionFailure(
            "Dashboard query logic changed after this Query Run was created",
            details={
                "code": "query_run_contract_changed",
                "run_id": result.run_id,
                "dashboard": result.dashboard,
                "missing_nodes": missing_nodes,
                "run_contract_hash": result.query_contract_hash,
                "current_contract_hash": current_hash,
                "action": "Run query again",
            },
        )
