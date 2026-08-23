from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from dataviz.errors import ExecutionFailure
from dataviz.value_contract import ValueContractViolation, normalize_control_value
from dataviz.workspace.models import DashboardDefinition, SelectionBindingDefinition, SelectionDefinition

SelectionOrigin = Literal["dashboard", "section", "view"]

@dataclass(frozen=True, slots=True)
class EffectiveSelection:
    key: str
    id: str
    origin: SelectionOrigin
    owner_id: str
    definition: SelectionDefinition
    binding: SelectionBindingDefinition

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "id": self.id, "origin": self.origin, "owner_id": self.owner_id,
                "definition": self.definition.model_dump(mode="json"),
                "binding": self.binding.model_dump(mode="json")}

def canonical_selection_key(origin: SelectionOrigin, owner_id: str, selection_id: str) -> str:
    return f"{origin}:{owner_id}/{selection_id}"

def compile_selection_contract(dashboard: DashboardDefinition) -> dict[str, list[EffectiveSelection]]:
    """Expand dashboard/section/view inheritance into a per-view contract."""
    dashboard_selections = [
        EffectiveSelection(canonical_selection_key("dashboard", dashboard.id, item.id), item.id,
                           "dashboard", dashboard.id, item,
                           SelectionBindingDefinition(field=item.field or item.id))
        for item in dashboard.dashboard_selections
    ]
    section_for_view = {
        view_id: section
        for section in dashboard.sections
        for view_id in section.views
    }
    contract: dict[str, list[EffectiveSelection]] = {}
    for view in dashboard.views:
        selections = list(dashboard_selections)
        section = section_for_view.get(view.id)
        if section:
            selections.extend(
                EffectiveSelection(
                    canonical_selection_key("section", section.id, item.id),
                    item.id,
                    "section",
                    section.id,
                    item,
                    SelectionBindingDefinition(field=item.field or item.id),
                )
                for item in section.selections
            )
        selections.extend(
            EffectiveSelection(
                canonical_selection_key("view", view.id, item.id),
                item.id,
                "view",
                view.id,
                item,
                SelectionBindingDefinition(field=item.field or item.id),
            )
            for item in view.selections
        )
        bindings = {
            name: SelectionBindingDefinition(field=value) if isinstance(value, str) else value
            for name, value in view.selection_bindings.items()
        }
        contract[view.id] = [
            EffectiveSelection(
                item.key,
                item.id,
                item.origin,
                item.owner_id,
                item.definition,
                bindings.get(item.id, item.binding),
            )
            for item in selections
        ]
    return contract

def resolve_selection_values(
    dashboard: DashboardDefinition, provided: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    contract = compile_selection_contract(dashboard)
    supplied = provided or {}
    all_selections = {item.key: item for values in contract.values() for item in values}
    normalized: dict[str, Any] = {}
    unknown = set(supplied)
    for key, item in all_selections.items():
        if key in supplied:
            raw = supplied[key]
            unknown.discard(key)
        else:
            raw = item.definition.default
        try:
            normalized[key] = normalize_control_value(item.definition, raw)
        except ValueContractViolation as error:
            raise ExecutionFailure(
                f"Invalid Selection {key}: {error.message}",
                details={
                    "code": f"selection_{error.code}",
                    "key": key,
                    "reason": error.message,
                },
            ) from error
    if unknown:
        raise ExecutionFailure(
            "Unknown Selection key",
            details={"code": "selection_unknown", "keys": sorted(unknown)},
        )
    by_view = {view_id: {item.id: normalized[item.key] for item in values}
               for view_id, values in contract.items()}
    return normalized, by_view
