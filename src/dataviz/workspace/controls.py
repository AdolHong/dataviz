from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from dataviz.errors import ExecutionFailure
from dataviz.value_contract import ValueContractViolation, normalize_control_value
from dataviz.workspace.models import (
    ComputeControlDefinition,
    DashboardDefinition,
    ScopedControlDefinition,
    SelectionBindingDefinition,
    SelectionControlDefinition,
)


ControlOrigin = Literal["dashboard", "section", "view"]
ControlKind = Literal["selection", "compute"]


@dataclass(frozen=True, slots=True)
class EffectiveControl:
    key: str
    id: str
    kind: ControlKind
    origin: ControlOrigin
    owner_id: str
    definition: ScopedControlDefinition
    binding: SelectionBindingDefinition | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "key": self.key,
            "id": self.id,
            "kind": self.kind,
            "origin": self.origin,
            "owner_id": self.owner_id,
            "definition": self.definition.model_dump(mode="json"),
        }
        if self.binding is not None:
            payload["binding"] = self.binding.model_dump(mode="json")
        return payload


def canonical_control_key(
    origin: ControlOrigin,
    owner_id: str,
    control_id: str,
) -> str:
    return f"{origin}:{owner_id}/{control_id}"


def _effective_control(
    definition: ScopedControlDefinition,
    origin: ControlOrigin,
    owner_id: str,
) -> EffectiveControl:
    binding = None
    if isinstance(definition, SelectionControlDefinition):
        binding = SelectionBindingDefinition(field=definition.field or definition.id)
    return EffectiveControl(
        key=canonical_control_key(origin, owner_id, definition.id),
        id=definition.id,
        kind=definition.kind,
        origin=origin,
        owner_id=owner_id,
        definition=definition,
        binding=binding,
    )


def scoped_control_registry(
    dashboard: DashboardDefinition,
    *,
    kind: ControlKind | None = None,
) -> dict[str, EffectiveControl]:
    controls: list[EffectiveControl] = [
        _effective_control(item, "dashboard", dashboard.id)
        for item in dashboard.controls
    ]
    for section in dashboard.sections:
        controls.extend(
            _effective_control(item, "section", section.id)
            for item in section.controls
        )
    for view in dashboard.views:
        controls.extend(
            _effective_control(item, "view", view.id)
            for item in view.controls
        )
    return {
        item.key: item
        for item in controls
        if kind is None or item.kind == kind
    }


def compile_control_contract(
    dashboard: DashboardDefinition,
) -> dict[str, list[EffectiveControl]]:
    """Expand Dashboard/Section/View inheritance into a per-View contract."""
    dashboard_controls = [
        _effective_control(item, "dashboard", dashboard.id)
        for item in dashboard.controls
    ]
    section_for_view = {
        view_id: section
        for section in dashboard.sections
        for view_id in section.views
    }
    contract: dict[str, list[EffectiveControl]] = {}
    for view in dashboard.views:
        controls = list(dashboard_controls)
        section = section_for_view.get(view.id)
        if section is not None:
            controls.extend(
                _effective_control(item, "section", section.id)
                for item in section.controls
            )
        controls.extend(
            _effective_control(item, "view", view.id)
            for item in view.controls
        )
        bindings = {
            name: SelectionBindingDefinition(field=value)
            if isinstance(value, str)
            else value
            for name, value in view.selection_bindings.items()
        }
        contract[view.id] = [
            EffectiveControl(
                key=item.key,
                id=item.id,
                kind=item.kind,
                origin=item.origin,
                owner_id=item.owner_id,
                definition=item.definition,
                binding=(
                    bindings.get(item.id, item.binding)
                    if item.kind == "selection"
                    else None
                ),
            )
            for item in controls
        ]
    return contract


def resolve_control_values(
    dashboard: DashboardDefinition,
    kind: ControlKind,
    provided: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize one semantic Control namespace using canonical scoped keys."""
    registry = scoped_control_registry(dashboard, kind=kind)
    supplied = provided or {}
    unknown = sorted(set(supplied) - set(registry))
    if unknown:
        raise ExecutionFailure(
            f"Unknown {kind.title()} Control key",
            details={"code": f"{kind}_control_unknown", "keys": unknown},
        )
    normalized: dict[str, Any] = {}
    for key, control in registry.items():
        raw = supplied.get(key, control.definition.default)
        try:
            normalized[key] = normalize_control_value(control.definition, raw)
        except ValueContractViolation as error:
            raise ExecutionFailure(
                f"Invalid {kind.title()} Control {key}: {error.message}",
                details={
                    "code": f"{kind}_control_{error.code}",
                    "key": key,
                    "reason": error.message,
                },
            ) from error
    return normalized


def resolve_selection_values(
    dashboard: DashboardDefinition,
    provided: dict[str, Any] | None,
) -> dict[str, Any]:
    return resolve_control_values(dashboard, "selection", provided)


def resolve_compute_values(
    dashboard: DashboardDefinition,
    provided: dict[str, Any] | None,
) -> dict[str, Any]:
    return resolve_control_values(dashboard, "compute", provided)


def control_definition(
    dashboard: DashboardDefinition,
    key: str,
    *,
    kind: ControlKind | None = None,
) -> SelectionControlDefinition | ComputeControlDefinition | None:
    item = scoped_control_registry(dashboard, kind=kind).get(key)
    return item.definition if item is not None else None
