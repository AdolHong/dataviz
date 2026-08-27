from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Literal, TYPE_CHECKING

from dataviz.errors import ValidationFailure

if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard


LAYOUT_CONTRACT_SCHEMA = "dataviz/layout-contract/v1"


@dataclass(frozen=True, slots=True)
class LayoutPlacement:
    view_id: str
    row: int
    column: int
    span: int
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "view": self.view_id,
            "row": self.row,
            "column": self.column,
            "span": self.span,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class LayoutRow:
    index: int
    views: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"index": self.index, "views": list(self.views)}


@dataclass(frozen=True, slots=True)
class LayoutSection:
    section_id: str
    template: str
    columns: int
    placements: tuple[LayoutPlacement, ...]
    rows: tuple[LayoutRow, ...]
    repeat_columns: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.section_id,
            "template": self.template,
            "columns": self.columns,
            "repeat_columns": self.repeat_columns,
            "placements": [item.as_dict() for item in self.placements],
            "rows": [item.as_dict() for item in self.rows],
        }


@dataclass(frozen=True, slots=True)
class DashboardLayoutContract:
    dashboard_id: str
    mode: Literal["declarative", "custom"]
    template: str
    columns: int
    gap: int
    sections: tuple[LayoutSection, ...]
    mount_sections: tuple[str, ...] = ()
    mount_views: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": LAYOUT_CONTRACT_SCHEMA,
            "dashboard": self.dashboard_id,
            "mode": self.mode,
            "template": self.template,
            "columns": self.columns,
            "gap": self.gap,
            "sections": [section.as_dict() for section in self.sections],
            "mount_points": {
                "sections": list(self.mount_sections),
                "views": list(self.mount_views),
            },
        }

    def placement(self, section_id: str, view_id: str) -> LayoutPlacement | None:
        for section in self.sections:
            if section.section_id != section_id:
                continue
            return next(
                (item for item in section.placements if item.view_id == view_id),
                None,
            )
        return None


def _template_span(template: str, index: int, columns: int) -> int:
    if template in {"single", "stack", "small-multiples", "selection-gallery"}:
        return columns
    if template in {"split", "chart-and-table"}:
        return max(1, ceil(columns * 2 / 3)) if index == 0 else max(1, columns // 3)
    if template == "comparison":
        return max(1, columns // 2)
    if template == "hero-metrics":
        return columns if index == 0 else max(1, columns // 4)
    if template == "band":
        return max(1, columns // 4)
    return max(1, columns // 2)


def _validate_cardinality(section_id: str, template: str, count: int) -> None:
    exact = {"single": 1, "split": 2, "comparison": 2, "chart-and-table": 2}
    if template in exact and count != exact[template]:
        raise ValidationFailure(
            f"Section {section_id} template {template} requires {exact[template]} Views",
            details={
                "code": "layout_template_cardinality",
                "section": section_id,
                "template": template,
                "expected": exact[template],
                "actual": count,
            },
        )
    if template == "hero-metrics" and count < 2:
        raise ValidationFailure(
            f"Section {section_id} template hero-metrics requires at least 2 Views",
            details={
                "code": "layout_template_cardinality",
                "section": section_id,
                "template": template,
                "expected": ">=2",
                "actual": count,
            },
        )
    if template in {"small-multiples", "selection-gallery"} and count != 1:
        raise ValidationFailure(
            f"Section {section_id} template {template} requires one blueprint View",
            details={
                "code": "layout_template_cardinality",
                "section": section_id,
                "template": template,
                "expected": 1,
                "actual": count,
            },
        )


def _compile_section(section: Any, views: dict[str, Any], columns: int) -> LayoutSection:
    _validate_cardinality(section.id, section.template, len(section.views))
    placements: list[LayoutPlacement] = []
    rows: list[LayoutRow] = []
    current: list[str] = []
    occupied = 0
    row_index = 0
    for index, view_id in enumerate(section.views):
        if view_id not in views:
            raise ValidationFailure(
                f"Section {section.id} references unknown View: {view_id}",
                details={
                    "code": "layout_view_unknown",
                    "section": section.id,
                    "view": view_id,
                },
            )
        view = views[view_id]
        span = view.span or _template_span(section.template, index, columns)
        source = f"view:{view_id}.span" if view.span else f"template:{section.template}"
        if span > columns:
            raise ValidationFailure(
                f"View {view_id} span {span} exceeds Section columns {columns}",
                details={
                    "code": "layout_span_exceeds_columns",
                    "section": section.id,
                    "view": view_id,
                    "span": span,
                    "columns": columns,
                },
            )
        if current and occupied + span > columns:
            rows.append(LayoutRow(index=row_index, views=tuple(current)))
            current = []
            occupied = 0
            row_index += 1
        placements.append(
            LayoutPlacement(
                view_id=view_id,
                row=row_index,
                column=occupied + 1,
                span=span,
                source=source,
            )
        )
        current.append(view_id)
        occupied += span
    if current:
        rows.append(LayoutRow(index=row_index, views=tuple(current)))
    return LayoutSection(
        section_id=section.id,
        template=section.template,
        columns=columns,
        placements=tuple(placements),
        rows=tuple(rows),
        repeat_columns=(section.columns or 1) if section.repeat else None,
    )


def compile_layout_contract(dashboard: "LoadedDashboard") -> DashboardLayoutContract:
    definition = dashboard.definition
    views = {view.id: view for view in definition.views}
    if definition.canvas.template:
        return DashboardLayoutContract(
            dashboard_id=definition.id,
            mode="custom",
            template=definition.layout.template,
            columns=definition.layout.columns,
            gap=definition.layout.gap,
            sections=(),
            mount_sections=tuple(section.id for section in definition.sections),
            mount_views=tuple(views),
        )

    assigned: set[str] = set()
    sections: list[LayoutSection] = []
    for section in definition.sections:
        duplicates = assigned.intersection(section.views)
        if duplicates:
            raise ValidationFailure(
                "A View can belong to only one Section: " + ", ".join(sorted(duplicates)),
                details={
                    "code": "layout_view_assigned_twice",
                    "views": sorted(duplicates),
                },
            )
        assigned.update(section.views)
        sections.append(
            _compile_section(
                section,
                views,
                section.columns or definition.layout.columns,
            )
        )

    remaining = [view_id for view_id in views if view_id not in assigned]
    if remaining:
        synthetic = type(
            "SyntheticSection",
            (),
            {
                "id": "overview",
                "template": "stack",
                "views": remaining,
                "columns": None,
                "repeat": None,
            },
        )()
        sections.append(_compile_section(synthetic, views, definition.layout.columns))

    return DashboardLayoutContract(
        dashboard_id=definition.id,
        mode="declarative",
        template=definition.layout.template,
        columns=definition.layout.columns,
        gap=definition.layout.gap,
        sections=tuple(sections),
    )
