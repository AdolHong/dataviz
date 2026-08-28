from __future__ import annotations

from copy import deepcopy
from typing import Any, TYPE_CHECKING

from dataviz.value_contract import initial_control_value
from dataviz.workspace.controls import scoped_control_registry
if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard


STATE_SNAPSHOT_SCHEMA = "dataviz/state-snapshot/v1"


def build_state_snapshot(
    dashboard: "LoadedDashboard",
    *,
    query_parameters: dict[str, Any],
    selection_state: dict[str, dict[str, Any]],
    compute_parameters: dict[str, Any],
    draft_compute_parameters: dict[str, Any] | None = None,
    query_stale: bool = False,
) -> dict[str, Any]:
    """Build the initial committed analysis-state evidence for one Canvas."""

    items: list[dict[str, Any]] = []
    for definition in dashboard.definition.query_parameters:
        value = deepcopy(query_parameters.get(definition.id))
        items.append(
            {
                "key": f"parameter:{definition.id}",
                "id": definition.id,
                "kind": "query",
                "origin": "dashboard",
                "owner_id": dashboard.definition.id,
                "label": definition.label or definition.id,
                "type": definition.type,
                "committed": value,
                "draft": deepcopy(value),
                "stale": query_stale,
                "definition": definition.model_dump(mode="json"),
            }
        )

    drafts = draft_compute_parameters or compute_parameters
    for key, control in scoped_control_registry(dashboard.definition).items():
        if control.kind == "selection":
            committed = deepcopy(
                selection_state.get(key, {"intent": "explicit", "values": []})
            )
            draft = deepcopy(committed)
            stale = False
        else:
            committed = deepcopy(
                compute_parameters.get(key, initial_control_value(control.definition))
            )
            draft = deepcopy(drafts.get(key, committed))
            stale = committed != draft
        items.append(
            {
                "key": key,
                "id": control.id,
                "kind": control.kind,
                "origin": control.origin,
                "owner_id": control.owner_id,
                "label": control.definition.label or control.id,
                "type": control.definition.type,
                "committed": committed,
                "draft": draft,
                "stale": stale,
                "definition": control.definition.model_dump(mode="json"),
            }
        )

    return {
        "schema": STATE_SNAPSHOT_SCHEMA,
        "dashboard": dashboard.definition.id,
        "query_stale": query_stale,
        "items": items,
    }


__all__ = ["STATE_SNAPSHOT_SCHEMA", "build_state_snapshot"]
