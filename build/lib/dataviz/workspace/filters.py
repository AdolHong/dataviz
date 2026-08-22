from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from dataviz.errors import ExecutionFailure
from dataviz.workspace.models import (
    DashboardDefinition,
    FilterBindingDefinition,
    FilterDefinition,
    ViewDefinition,
)


FilterOrigin = Literal["dashboard", "section", "view"]


@dataclass(frozen=True, slots=True)
class EffectiveFilter:
    key: str
    id: str
    origin: FilterOrigin
    owner_id: str
    definition: FilterDefinition
    binding: FilterBindingDefinition

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "id": self.id,
            "origin": self.origin,
            "owner_id": self.owner_id,
            "definition": self.definition.model_dump(mode="json"),
            "binding": self.binding.model_dump(mode="json"),
        }


def view_definition(value: str | ViewDefinition) -> ViewDefinition:
    return ViewDefinition(widget=value) if isinstance(value, str) else value


def canonical_filter_key(origin: FilterOrigin, owner_id: str, filter_id: str) -> str:
    return f"{origin}:{owner_id}/{filter_id}"


def compile_filter_contract(dashboard: DashboardDefinition) -> dict[str, list[EffectiveFilter]]:
    """Expand dashboard/section/view inheritance into a per-widget contract."""
    dashboard_filters = [
        EffectiveFilter(
            key=canonical_filter_key("dashboard", dashboard.id, item.id),
            id=item.id,
            origin="dashboard",
            owner_id=dashboard.id,
            definition=item,
            binding=FilterBindingDefinition(field=item.id),
        )
        for item in dashboard.dashboard_filters
    ]
    contract: dict[str, list[EffectiveFilter]] = {}
    section_widgets: set[str] = set()

    for section in dashboard.sections:
        section_filters = [
            EffectiveFilter(
                key=canonical_filter_key("section", section.id, item.id),
                id=item.id,
                origin="section",
                owner_id=section.id,
                definition=item,
                binding=FilterBindingDefinition(field=item.id),
            )
            for item in section.filters
        ]
        for raw_view in section.views:
            view = view_definition(raw_view)
            section_widgets.add(view.widget)
            filters = list(dashboard_filters) + list(section_filters)
            filters.extend(
                EffectiveFilter(
                    key=canonical_filter_key("view", view.widget, item.id),
                    id=item.id,
                    origin="view",
                    owner_id=view.widget,
                    definition=item,
                    binding=FilterBindingDefinition(field=item.id),
                )
                for item in view.filters
            )
            bindings = {
                name: FilterBindingDefinition(field=value)
                if isinstance(value, str)
                else value
                for name, value in view.filter_bindings.items()
            }
            contract[view.widget] = [
                EffectiveFilter(
                    key=item.key,
                    id=item.id,
                    origin=item.origin,
                    owner_id=item.owner_id,
                    definition=item.definition,
                    binding=bindings.get(item.id, item.binding),
                )
                for item in filters
            ]

    for widget_path in dashboard.widgets:
        widget_id = widget_path.rsplit("/", 2)[-2] if "/" in widget_path else widget_path
        if widget_id not in section_widgets:
            contract.setdefault(widget_id, list(dashboard_filters))
    return contract


def resolve_filter_values(
    dashboard: DashboardDefinition, provided: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    contract = compile_filter_contract(dashboard)
    supplied = provided or {}
    all_filters = {item.key: item for values in contract.values() for item in values}
    short_keys: dict[str, list[str]] = {}
    for key, item in all_filters.items():
        short_keys.setdefault(item.id, []).append(key)

    normalized: dict[str, Any] = {}
    unknown = set(supplied)
    for key, item in all_filters.items():
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
        raise ExecutionFailure("Unknown or ambiguous filter", details=sorted(unknown))

    by_widget = {
        widget_id: {item.id: normalized[item.key] for item in values}
        for widget_id, values in contract.items()
    }
    return normalized, by_widget


def _coerce(definition: FilterDefinition, value: Any) -> Any:
    if definition.required and (value is None or value == "" or value == []):
        raise ExecutionFailure(f"Required filter is missing: {definition.id}")
    if definition.type == "boolean" and isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "on"}
    if definition.type == "number" and isinstance(value, str):
        return float(value) if "." in value else int(value)
    if definition.type == "multi_select" and isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if definition.type == "date_range" and isinstance(value, str):
        return [item.strip() for item in value.split(",", 1)]
    return value
