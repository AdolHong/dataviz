from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from dataviz.errors import ExecutionFailure
from dataviz.workspace.models import DashboardDefinition, SelectionBindingDefinition, SelectionDefinition, ViewDefinition

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

def view_definition(value: str | ViewDefinition) -> ViewDefinition:
    return ViewDefinition(widget=value) if isinstance(value, str) else value

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
    contract: dict[str, list[EffectiveSelection]] = {}
    section_views: set[str] = set()
    declarative_views = {item.id: item for item in dashboard.views}
    for section in dashboard.sections:
        section_selections = [
            EffectiveSelection(canonical_selection_key("section", section.id, item.id), item.id,
                               "section", section.id, item,
                               SelectionBindingDefinition(field=item.field or item.id))
            for item in section.selections
        ]
        for raw_view in section.views:
            view = view_definition(raw_view)
            declarative = declarative_views.get(view.widget)
            section_views.add(view.widget)
            selections = list(dashboard_selections) + list(section_selections)
            local = list(declarative.selections) if declarative else []
            local.extend(view.selections)
            selections.extend(
                EffectiveSelection(canonical_selection_key("view", view.widget, item.id), item.id,
                                   "view", view.widget, item,
                                   SelectionBindingDefinition(field=item.field or item.id))
                for item in local
            )
            bindings = {
                name: SelectionBindingDefinition(field=value) if isinstance(value, str) else value
                for name, value in {**(declarative.selection_bindings if declarative else {}),
                                    **view.selection_bindings}.items()
            }
            contract[view.widget] = [
                EffectiveSelection(item.key, item.id, item.origin, item.owner_id, item.definition,
                                   bindings.get(item.id, item.binding))
                for item in selections
            ]
    for widget_path in dashboard.widgets:
        view_id = Path(widget_path).parent.name
        if view_id not in section_views:
            contract.setdefault(view_id, list(dashboard_selections))
    for view in dashboard.views:
        if view.id in section_views:
            continue
        selections = list(dashboard_selections)
        selections.extend(
            EffectiveSelection(canonical_selection_key("view", view.id, item.id), item.id,
                               "view", view.id, item,
                               SelectionBindingDefinition(field=item.field or item.id))
            for item in view.selections
        )
        bindings = {name: SelectionBindingDefinition(field=value) if isinstance(value, str) else value
                    for name, value in view.selection_bindings.items()}
        contract[view.id] = [
            EffectiveSelection(item.key, item.id, item.origin, item.owner_id, item.definition,
                               bindings.get(item.id, item.binding))
            for item in selections
        ]
    return contract

def resolve_selection_values(
    dashboard: DashboardDefinition, provided: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    contract = compile_selection_contract(dashboard)
    supplied = provided or {}
    all_selections = {item.key: item for values in contract.values() for item in values}
    short_keys: dict[str, list[str]] = {}
    for key, item in all_selections.items():
        short_keys.setdefault(item.id, []).append(key)
    normalized: dict[str, Any] = {}
    unknown = set(supplied)
    for key, item in all_selections.items():
        if key in supplied:
            raw = supplied[key]
            unknown.discard(key)
        elif item.id in supplied and len(short_keys[item.id]) == 1:
            raw = supplied[item.id]
            unknown.discard(item.id)
        else:
            raw = item.definition.default
        normalized[key] = _coerce(item.definition, raw)
    if unknown:
        raise ExecutionFailure("Unknown or ambiguous selection", details=sorted(unknown))
    by_view = {view_id: {item.id: normalized[item.key] for item in values}
               for view_id, values in contract.items()}
    return normalized, by_view

def _coerce(definition: SelectionDefinition, value: Any) -> Any:
    if definition.required and (value is None or value == "" or value == []):
        raise ExecutionFailure(f"Required selection is missing: {definition.id}")
    if definition.type == "boolean" and isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "on"}
    if definition.type == "number" and isinstance(value, str):
        return float(value) if "." in value else int(value)
    if definition.type == "multi_select" and isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if definition.type == "date_range" and isinstance(value, str):
        return [item.strip() for item in value.split(",", 1)]
    return value
