from __future__ import annotations

from copy import deepcopy
from typing import Any, TYPE_CHECKING

from dataviz.errors import ValidationFailure
from dataviz.workspace.controls import scoped_control_registry

if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard


STATE_SNAPSHOT_SCHEMA = "dataviz/state-snapshot/v2"


def _revision(value: Any, *, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationFailure(
            f"Invalid applied Control revision at {path}",
            details={
                "code": "consumer_applied_revision_invalid",
                "path": path,
                "revision": value,
            },
        )
    return value


def applied_revisions_for_consumers(
    dashboard: "LoadedDashboard",
    control_state: dict[str, dict[str, Any]],
    *,
    view_ids: set[str] | None = None,
    transform_ids: set[str] | None = None,
) -> dict[str, dict[str, dict[str, int]]]:
    """Record current revisions for consumers known to have completed."""

    contract = dashboard.dependency_contract
    selected_views = view_ids or set()
    selected_transforms = transform_ids or set()

    def revisions(bindings: dict[str, dict[str, Any]]) -> dict[str, int]:
        return {
            key: _revision(
                control_state.get(key, {}).get("revision", 0),
                path=f"control_state.{key}.revision",
            )
            for key in sorted(
                {
                    str(binding["control"])
                    for binding in bindings.values()
                }
            )
        }

    return {
        "views": {
            view_id: revisions(contract.view_control_inputs.get(view_id, {}))
            for view_id in sorted(selected_views)
            if contract.view_control_inputs.get(view_id)
        },
        "transforms": {
            transform_id: revisions(
                contract.interactive_control_inputs.get(transform_id, {})
            )
            for transform_id in sorted(selected_transforms)
            if contract.interactive_control_inputs.get(transform_id)
        },
    }


def merge_applied_revisions(
    *values: dict[str, dict[str, dict[str, int]]] | None,
) -> dict[str, dict[str, dict[str, int]]]:
    """Merge browser/server observations without mutating either snapshot."""

    merged: dict[str, dict[str, dict[str, int]]] = {
        "views": {},
        "transforms": {},
    }
    for value in values:
        if not value:
            continue
        for consumer_type in ("views", "transforms"):
            consumers = value.get(consumer_type, {})
            if not isinstance(consumers, dict):
                raise ValidationFailure(
                    f"Invalid applied revisions collection: {consumer_type}",
                    details={
                        "code": "consumer_applied_revisions_invalid",
                        "consumer_type": consumer_type,
                    },
                )
            for consumer_id, revisions in consumers.items():
                if not isinstance(revisions, dict):
                    raise ValidationFailure(
                        f"Invalid applied revisions for {consumer_type}.{consumer_id}",
                        details={
                            "code": "consumer_applied_revisions_invalid",
                            "consumer_type": consumer_type,
                            "consumer_id": consumer_id,
                        },
                    )
                merged[consumer_type][str(consumer_id)] = deepcopy(revisions)
    return merged


def normalize_consumer_revisions(
    dashboard: "LoadedDashboard",
    control_state: dict[str, dict[str, Any]],
    applied_revisions: dict[str, dict[str, dict[str, int]]] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Project raw Runtime revisions onto compiler-known consumer bindings."""

    contract = dashboard.dependency_contract
    raw = merge_applied_revisions(applied_revisions)

    def project(
        consumer_type: str,
        consumer_id: str,
        bindings: dict[str, dict[str, Any]],
        *,
        trigger: str,
    ) -> dict[str, Any] | None:
        control_keys = sorted(
            {str(binding["control"]) for binding in bindings.values()}
        )
        if not control_keys:
            return None
        observed = raw[consumer_type].get(consumer_id, {})
        controls: dict[str, dict[str, Any]] = {}
        for key in control_keys:
            effective = _revision(
                control_state.get(key, {}).get("revision", 0),
                path=f"control_state.{key}.revision",
            )
            applied_value = observed.get(key)
            applied = (
                None
                if applied_value is None
                else _revision(
                    applied_value,
                    path=f"applied_revisions.{consumer_type}.{consumer_id}.{key}",
                )
            )
            if applied is not None and applied > effective:
                raise ValidationFailure(
                    f"Applied revision exceeds current revision for {consumer_id}",
                    details={
                        "code": "consumer_applied_revision_ahead",
                        "consumer_type": consumer_type,
                        "consumer_id": consumer_id,
                        "control": key,
                        "applied_revision": applied,
                        "effective_revision": effective,
                    },
                )
            controls[key] = {
                "effective_revision": effective,
                "applied_revision": applied,
                "stale": applied != effective,
            }
        return {
            "trigger": trigger,
            "stale": any(item["stale"] for item in controls.values()),
            "controls": controls,
        }

    views: dict[str, dict[str, Any]] = {}
    for view_id, bindings in sorted(contract.view_control_inputs.items()):
        value = project("views", view_id, bindings, trigger="auto")
        if value is not None:
            views[view_id] = value
    transforms: dict[str, dict[str, Any]] = {}
    for transform_id, bindings in sorted(
        contract.interactive_control_inputs.items()
    ):
        value = project(
            "transforms",
            transform_id,
            bindings,
            trigger=dashboard.interactive_transforms[transform_id][1].trigger,
        )
        if value is not None:
            transforms[transform_id] = value
    return {"views": views, "transforms": transforms}


def build_state_snapshot(
    dashboard: "LoadedDashboard",
    *,
    query_parameters: dict[str, Any],
    control_state: dict[str, dict[str, Any]],
    draft_control_state: dict[str, dict[str, Any]] | None = None,
    applied_revisions: dict[str, dict[str, dict[str, int]]] | None = None,
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
                "entry_type": "query_parameter",
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

    drafts = draft_control_state or control_state
    for key, control in scoped_control_registry(dashboard.definition).items():
        committed = deepcopy(control_state[key])
        draft = deepcopy(drafts.get(key, committed))
        stale = committed != draft
        items.append(
            {
                "key": key,
                "id": control.id,
                "entry_type": "control",
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
        "applied_revisions": deepcopy(applied_revisions or {}),
        "consumer_revisions": normalize_consumer_revisions(
            dashboard,
            control_state,
            applied_revisions,
        ),
    }


__all__ = [
    "STATE_SNAPSHOT_SCHEMA",
    "applied_revisions_for_consumers",
    "build_state_snapshot",
    "merge_applied_revisions",
    "normalize_consumer_revisions",
]
