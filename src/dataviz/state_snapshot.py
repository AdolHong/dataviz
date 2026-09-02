from __future__ import annotations

from copy import deepcopy
from typing import Any, TYPE_CHECKING

from dataviz.errors import ExecutionFailure, ValidationFailure
from dataviz.input_state import normalize_input_state_entry
from dataviz.protocols import STATE_SNAPSHOT_SCHEMA
from dataviz.workspace.controls import scoped_control_registry

if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard


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


def normalize_consumer_revision(
    effective: Any,
    applied: Any,
    *,
    path: str = "consumer_revision",
) -> dict[str, Any]:
    """Normalize one effective/applied pair for cross-Runtime conformance."""

    normalized_effective = _revision(effective, path=f"{path}.effective")
    normalized_applied = (
        None if applied is None else _revision(applied, path=f"{path}.applied")
    )
    if normalized_applied is not None and normalized_applied > normalized_effective:
        raise ValidationFailure(
            "Applied revision exceeds current revision",
            details={
                "code": "consumer_applied_revision_ahead",
                "applied_revision": normalized_applied,
                "effective_revision": normalized_effective,
            },
        )
    return {
        "effective_revision": normalized_effective,
        "applied_revision": normalized_applied,
        "stale": normalized_applied != normalized_effective,
    }


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


def applied_control_state_for_consumers(
    dashboard: "LoadedDashboard",
    control_state: dict[str, dict[str, Any]],
    *,
    view_ids: set[str] | None = None,
    transform_ids: set[str] | None = None,
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """Capture the exact canonical Control state consumed by completed nodes."""

    contract = dashboard.dependency_contract
    selected_views = view_ids or set()
    selected_transforms = transform_ids or set()

    def states(bindings: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        keys = sorted({str(binding["control"]) for binding in bindings.values()})
        missing = [key for key in keys if key not in control_state]
        if missing:
            raise ValidationFailure(
                "Completed consumer is missing captured Control state",
                details={
                    "code": "consumer_applied_control_state_missing",
                    "controls": missing,
                },
            )
        return {key: deepcopy(control_state[key]) for key in keys}

    return {
        "views": {
            view_id: states(contract.view_control_inputs.get(view_id, {}))
            for view_id in sorted(selected_views)
            if contract.view_control_inputs.get(view_id)
        },
        "transforms": {
            transform_id: states(
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


def merge_applied_control_state(
    *values: dict[str, dict[str, dict[str, dict[str, Any]]]] | None,
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """Merge immutable per-consumer start snapshots without interpreting them."""

    merged: dict[str, dict[str, dict[str, dict[str, Any]]]] = {
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
                    f"Invalid applied Control state collection: {consumer_type}",
                    details={
                        "code": "consumer_applied_control_state_invalid",
                        "consumer_type": consumer_type,
                    },
                )
            for consumer_id, states in consumers.items():
                if not isinstance(states, dict):
                    raise ValidationFailure(
                        f"Invalid applied Control state for {consumer_type}.{consumer_id}",
                        details={
                            "code": "consumer_applied_control_state_invalid",
                            "consumer_type": consumer_type,
                            "consumer_id": consumer_id,
                        },
                    )
                merged[consumer_type][str(consumer_id)] = deepcopy(states)
    return merged


def merge_applied_writer_provenance(
    *values: dict[str, dict[str, dict[str, dict[str, Any]]]] | None,
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """Merge immutable per-consumer writer evidence without interpreting it."""

    merged: dict[str, dict[str, dict[str, dict[str, Any]]]] = {
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
                    f"Invalid applied writer provenance collection: {consumer_type}",
                    details={
                        "code": "consumer_applied_writer_provenance_invalid",
                        "consumer_type": consumer_type,
                    },
                )
            for consumer_id, provenance in consumers.items():
                if not isinstance(provenance, dict):
                    raise ValidationFailure(
                        f"Invalid applied writer provenance for {consumer_type}.{consumer_id}",
                        details={
                            "code": "consumer_applied_writer_provenance_invalid",
                            "consumer_type": consumer_type,
                            "consumer_id": consumer_id,
                        },
                    )
                merged[consumer_type][str(consumer_id)] = deepcopy(provenance)
    return merged


def _normalize_writer_provenance(
    dashboard: "LoadedDashboard",
    control: str,
    value: Any,
    *,
    expected_revision: int,
    path: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationFailure(
            f"Writer provenance at {path} must be an object",
            details={"code": "control_writer_provenance_invalid", "path": path},
        )
    revision = _revision(value.get("revision"), path=f"{path}.revision")
    if revision != expected_revision:
        raise ValidationFailure(
            f"Writer provenance at {path} does not match its Control revision",
            details={
                "code": "control_writer_provenance_revision_mismatch",
                "path": path,
                "revision": revision,
                "expected_revision": expected_revision,
            },
        )
    action_id = value.get("action_id")
    source_view = value.get("source_view")
    source_layer = value.get("source_layer")
    action = value.get("action")
    if not isinstance(action_id, str) or not action_id.strip() or len(action_id) > 128:
        raise ValidationFailure(
            f"Writer provenance at {path} has an invalid action_id",
            details={"code": "control_writer_action_id_invalid", "path": path},
        )
    allowed_sources = {
        (edge.view_id, edge.source_layer)
        for edge in dashboard.dependency_contract.controls[control].writer_edges
    }
    source = (source_view, source_layer)
    if (
        not isinstance(source_view, str)
        or (source_layer is not None and not isinstance(source_layer, str))
        or source not in allowed_sources
    ):
        raise ValidationFailure(
            f"Writer provenance at {path} has an invalid source View/Layer",
            details={
                "code": "control_writer_source_view_invalid",
                "path": path,
                "control": control,
                "source_view": source_view,
                "source_layer": source_layer,
                "allowed_sources": [
                    {"source_view": view, "source_layer": layer}
                    for view, layer in sorted(
                        allowed_sources,
                        key=lambda item: (item[0], item[1] or ""),
                    )
                ],
            },
        )
    if action not in {"select", "select_many", "clear", "reset"}:
        raise ValidationFailure(
            f"Writer provenance at {path} has an invalid action",
            details={
                "code": "control_writer_action_invalid",
                "path": path,
                "action": action,
            },
        )
    return {
        "revision": revision,
        "action_id": action_id,
        "source_view": source_view,
        **({"source_layer": source_layer} if source_layer is not None else {}),
        "action": action,
    }


def normalize_consumer_revisions(
    dashboard: "LoadedDashboard",
    control_state: dict[str, dict[str, Any]],
    applied_revisions: dict[str, dict[str, dict[str, int]]] | None = None,
    applied_control_state: (
        dict[str, dict[str, dict[str, dict[str, Any]]]] | None
    ) = None,
    applied_writer_provenance: (
        dict[str, dict[str, dict[str, dict[str, Any]]]] | None
    ) = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Project raw Runtime revisions onto compiler-known consumer bindings."""

    contract = dashboard.dependency_contract
    raw = merge_applied_revisions(applied_revisions)
    raw_states = merge_applied_control_state(applied_control_state)
    raw_writer_provenance = merge_applied_writer_provenance(
        applied_writer_provenance
    )
    registry = scoped_control_registry(dashboard.definition)

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
        observed_states = raw_states[consumer_type].get(consumer_id, {})
        observed_writer_provenance = raw_writer_provenance[consumer_type].get(
            consumer_id, {}
        )
        controls: dict[str, dict[str, Any]] = {}
        captured: dict[str, dict[str, Any]] = {}
        captured_writer_provenance: dict[str, dict[str, Any]] = {}
        for key in control_keys:
            effective = control_state.get(key, {}).get("revision", 0)
            applied_value = observed.get(key)
            raw_state = observed_states.get(key)
            normalized_state: dict[str, Any] | None = None
            if raw_state is not None:
                if not isinstance(raw_state, dict):
                    raise ValidationFailure(
                        "Consumer applied Control state must be an object",
                        details={
                            "code": "consumer_applied_control_state_invalid",
                            "consumer_type": consumer_type,
                            "consumer_id": consumer_id,
                            "control": key,
                        },
                    )
                try:
                    normalized_state = normalize_input_state_entry(
                        registry[key].definition,
                        raw_state,
                        allow_unresolved_inferred=True,
                    ).as_dict()
                except ExecutionFailure as error:
                    details = (
                        dict(error.details)
                        if isinstance(error.details, dict)
                        else {}
                    )
                    details.update(
                        {
                            "consumer_type": consumer_type,
                            "consumer_id": consumer_id,
                            "control": key,
                        }
                    )
                    raise ValidationFailure(error.message, details=details) from error
                state_revision = normalized_state["revision"]
                if applied_value is None:
                    applied_value = state_revision
                elif applied_value != state_revision:
                    raise ValidationFailure(
                        "Applied revision and captured Control state disagree",
                        details={
                            "code": "consumer_applied_control_state_revision_mismatch",
                            "consumer_type": consumer_type,
                            "consumer_id": consumer_id,
                            "control": key,
                            "applied_revision": applied_value,
                            "state_revision": state_revision,
                        },
                    )
                captured[key] = normalized_state
            elif applied_value is not None:
                raise ValidationFailure(
                    "Applied revision has no self-contained Control state",
                    details={
                        "code": "consumer_applied_control_state_missing",
                        "consumer_type": consumer_type,
                        "consumer_id": consumer_id,
                        "control": key,
                    },
                )
            controls[key] = normalize_consumer_revision(
                effective,
                applied_value,
                path=f"applied_revisions.{consumer_type}.{consumer_id}.{key}",
            )
            raw_provenance = observed_writer_provenance.get(key)
            if raw_provenance is not None:
                if normalized_state is None:
                    raise ValidationFailure(
                        "Applied writer provenance has no captured Control state",
                        details={
                            "code": "consumer_applied_writer_provenance_without_state",
                            "consumer_type": consumer_type,
                            "consumer_id": consumer_id,
                            "control": key,
                        },
                    )
                captured_writer_provenance[key] = _normalize_writer_provenance(
                    dashboard,
                    key,
                    raw_provenance,
                    expected_revision=normalized_state["revision"],
                    path=(
                        f"applied_writer_provenance.{consumer_type}."
                        f"{consumer_id}.{key}"
                    ),
                )
        return {
            "trigger": trigger,
            "stale": any(item["stale"] for item in controls.values()),
            "controls": controls,
            "applied_control_state": captured,
            "applied_writer_provenance": captured_writer_provenance,
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
    query_parameter_state: dict[str, dict[str, Any]],
    control_state: dict[str, dict[str, Any]],
    draft_control_state: dict[str, dict[str, Any]] | None = None,
    applied_revisions: dict[str, dict[str, dict[str, int]]] | None = None,
    applied_control_state: (
        dict[str, dict[str, dict[str, dict[str, Any]]]] | None
    ) = None,
    control_writer_provenance: dict[str, dict[str, Any]] | None = None,
    applied_writer_provenance: (
        dict[str, dict[str, dict[str, dict[str, Any]]]] | None
    ) = None,
    query_stale: bool = False,
) -> dict[str, Any]:
    """Build the initial committed analysis-state evidence for one Canvas."""

    items: list[dict[str, Any]] = []
    for definition in dashboard.definition.query_parameters:
        state = deepcopy(query_parameter_state.get(definition.id, {"value": None}))
        items.append(
            {
                "key": f"parameter:{definition.id}",
                "id": definition.id,
                "entry_type": "query_parameter",
                "origin": "dashboard",
                "owner_id": dashboard.definition.id,
                "label": definition.label or definition.id,
                "type": definition.type,
                "committed": state,
                "draft": deepcopy(state),
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

    consumer_revisions = normalize_consumer_revisions(
        dashboard,
        control_state,
        applied_revisions,
        applied_control_state,
        applied_writer_provenance,
    )
    normalized_applied_state = {
        consumer_type: {
            consumer_id: deepcopy(consumer["applied_control_state"])
            for consumer_id, consumer in consumers.items()
            if consumer["applied_control_state"]
        }
        for consumer_type, consumers in consumer_revisions.items()
    }
    normalized_applied_writer_provenance = {
        consumer_type: {
            consumer_id: deepcopy(consumer["applied_writer_provenance"])
            for consumer_id, consumer in consumers.items()
            if consumer["applied_writer_provenance"]
        }
        for consumer_type, consumers in consumer_revisions.items()
    }
    unknown_writer_controls = sorted(
        set(control_writer_provenance or {})
        - set(dashboard.dependency_contract.controls)
    )
    if unknown_writer_controls:
        raise ValidationFailure(
            "Current writer provenance references unknown Controls",
            details={
                "code": "control_writer_provenance_unknown_control",
                "controls": unknown_writer_controls,
            },
        )
    normalized_current_writer_provenance = {
        key: _normalize_writer_provenance(
            dashboard,
            key,
            value,
            expected_revision=_revision(
                control_state.get(key, {}).get("revision", 0),
                path=f"control_state.{key}.revision",
            ),
            path=f"control_writer_provenance.{key}",
        )
        for key, value in (control_writer_provenance or {}).items()
    }
    return {
        "schema": STATE_SNAPSHOT_SCHEMA,
        "dashboard": dashboard.definition.id,
        "query_stale": query_stale,
        "items": items,
        "applied_revisions": deepcopy(applied_revisions or {}),
        "applied_control_state": normalized_applied_state,
        "control_writer_provenance": normalized_current_writer_provenance,
        "applied_writer_provenance": normalized_applied_writer_provenance,
        "consumer_revisions": consumer_revisions,
    }


__all__ = [
    "STATE_SNAPSHOT_SCHEMA",
    "applied_control_state_for_consumers",
    "applied_revisions_for_consumers",
    "build_state_snapshot",
    "merge_applied_revisions",
    "merge_applied_control_state",
    "merge_applied_writer_provenance",
    "normalize_consumer_revisions",
    "normalize_consumer_revision",
]
