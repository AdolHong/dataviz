from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from dataviz.input_state import (
    control_values,
    initial_input_state,
    resolve_control_state,
)
from dataviz.workspace.models import (
    ControlDefinition,
    DashboardDefinition,
    ScopedControlDefinition,
)


ControlOrigin = Literal["dashboard", "section", "view"]
ControlResolutionPhase = Literal["execution", "canvas-hydration"]


@dataclass(frozen=True, slots=True)
class EffectiveControl:
    key: str
    id: str
    origin: ControlOrigin
    owner_id: str
    definition: ScopedControlDefinition

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "id": self.id,
            "origin": self.origin,
            "owner_id": self.owner_id,
            "definition": self.definition.model_dump(mode="json"),
            "initial_state": initial_input_state(
                self.definition,
                allow_unresolved_inferred=True,
            ).as_dict(),
        }


def canonical_control_key(
    origin: ControlOrigin,
    owner_id: str,
    control_id: str,
) -> str:
    return f"{origin}:{owner_id}/{control_id}"


def resolve_dashboard_control_reference(reference: str, dashboard_id: str) -> str:
    """Resolve the author-facing ``dashboard.<id>`` spelling when no View owns it."""

    if reference.startswith("dashboard."):
        return canonical_control_key(
            "dashboard",
            dashboard_id,
            reference.split(".", 1)[1],
        )
    return reference


def _effective_control(
    definition: ScopedControlDefinition,
    origin: ControlOrigin,
    owner_id: str,
) -> EffectiveControl:
    return EffectiveControl(
        key=canonical_control_key(origin, owner_id, definition.id),
        id=definition.id,
        origin=origin,
        owner_id=owner_id,
        definition=definition,
    )


def scoped_control_registry(
    dashboard: DashboardDefinition,
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
    return {item.key: item for item in controls}


def compile_control_contract(
    dashboard: DashboardDefinition,
) -> dict[str, list[EffectiveControl]]:
    """Expand Dashboard/Section/View visibility into a per-View contract."""

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
        contract[view.id] = controls
    return contract


def resolve_control_states(
    dashboard: DashboardDefinition,
    provided: dict[str, dict[str, Any]] | None,
    *,
    phase: ControlResolutionPhase = "execution",
) -> dict[str, dict[str, Any]]:
    return resolve_control_state(dashboard, provided, phase=phase)


def project_control_values(
    dashboard: DashboardDefinition,
    state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return control_values(dashboard, state)


def control_definition(
    dashboard: DashboardDefinition,
    key: str,
) -> ControlDefinition | None:
    item = scoped_control_registry(dashboard).get(key)
    return item.definition if item is not None else None


__all__ = [
    "ControlOrigin",
    "ControlResolutionPhase",
    "EffectiveControl",
    "canonical_control_key",
    "compile_control_contract",
    "control_definition",
    "project_control_values",
    "resolve_control_states",
    "resolve_dashboard_control_reference",
    "scoped_control_registry",
]
