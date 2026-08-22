from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from dataviz.errors import Diagnostic, WorkspaceError
from dataviz.workspace.models import (
    DashboardDefinition,
    SourceDefinition,
    WidgetDefinition,
    WorkspaceDefinition,
)
from dataviz.workspace.filters import compile_filter_contract, view_definition


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise WorkspaceError("Required YAML file does not exist", file=path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorkspaceError(f"Invalid YAML: {exc}", file=path) from exc
    if not isinstance(data, dict):
        raise WorkspaceError("YAML document must be an object", file=path)
    return data


def parse_model(model_type, path: Path):
    try:
        return model_type.model_validate(read_yaml(path))
    except ValidationError as exc:
        raise WorkspaceError("Schema validation failed", file=path, details=exc.errors()) from exc


@dataclass(slots=True)
class LoadedDashboard:
    root: Path
    definition_path: Path
    definition: DashboardDefinition
    sources: dict[str, tuple[Path, SourceDefinition]]
    widgets: dict[str, tuple[Path, WidgetDefinition]]
    readme: str = ""

    def resolve(self, relative: str | None) -> Path | None:
        return (self.root / relative).resolve() if relative else None


@dataclass(slots=True)
class LoadedWorkspace:
    root: Path
    definition_path: Path
    definition: WorkspaceDefinition
    dashboards: dict[str, LoadedDashboard]
    readme: str = ""

    @property
    def state_dir(self) -> Path:
        return self.root / ".dataviz"

    def dashboard(self, identifier: str) -> LoadedDashboard:
        if identifier in self.dashboards:
            return self.dashboards[identifier]
        normalized = identifier.rstrip("/")
        for dashboard in self.dashboards.values():
            if str(dashboard.root.relative_to(self.root)) == normalized:
                return dashboard
        raise WorkspaceError(f"Unknown dashboard: {identifier}")


def load_dashboard(path: Path) -> LoadedDashboard:
    root = path.resolve()
    definition_path = root / "dashboard.yaml"
    definition = parse_model(DashboardDefinition, definition_path)
    sources: dict[str, tuple[Path, SourceDefinition]] = {}
    widgets: dict[str, tuple[Path, WidgetDefinition]] = {}

    for relative in definition.sources:
        source_path = (root / relative).resolve()
        source = parse_model(SourceDefinition, source_path)
        if source.id in sources:
            raise WorkspaceError(f"Duplicate source id: {source.id}", file=source_path)
        sources[source.id] = (source_path, source)

    for relative in definition.widgets:
        widget_path = (root / relative).resolve()
        widget = parse_model(WidgetDefinition, widget_path)
        if widget.id in widgets:
            raise WorkspaceError(f"Duplicate widget id: {widget.id}", file=widget_path)
        widgets[widget.id] = (widget_path, widget)

    readme_path = root / "README.md"
    return LoadedDashboard(
        root=root,
        definition_path=definition_path,
        definition=definition,
        sources=sources,
        widgets=widgets,
        readme=readme_path.read_text(encoding="utf-8") if readme_path.exists() else "",
    )


def load_workspace(path: Path | str) -> LoadedWorkspace:
    root = Path(path).expanduser().resolve()
    definition_path = root / "workspace.yaml"
    definition = parse_model(WorkspaceDefinition, definition_path)
    dashboards: dict[str, LoadedDashboard] = {}
    for item in sorted(definition.navigation, key=lambda value: value.order):
        dashboard = load_dashboard(root / item.dashboard)
        if dashboard.definition.id in dashboards:
            raise WorkspaceError(
                f"Duplicate dashboard id: {dashboard.definition.id}", file=dashboard.definition_path
            )
        dashboards[dashboard.definition.id] = dashboard
    readme_path = root / "README.md"
    return LoadedWorkspace(
        root=root,
        definition_path=definition_path,
        definition=definition,
        dashboards=dashboards,
        readme=readme_path.read_text(encoding="utf-8") if readme_path.exists() else "",
    )


def validate_workspace(workspace: LoadedWorkspace) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not workspace.dashboards:
        diagnostics.append(Diagnostic("warning", "Workspace has no dashboards", str(workspace.definition_path)))

    for dashboard in workspace.dashboards.values():
        parameter_ids = {item.id for item in dashboard.definition.query_parameters}
        node_ids = set(dashboard.sources) | set(dashboard.widgets)
        for source_path, source in dashboard.sources.values():
            if source.type == "file" and not source.path:
                diagnostics.append(Diagnostic("error", "File source requires path", str(source_path), "path"))
            if source.type in {"sql", "python"} and not source.code:
                diagnostics.append(Diagnostic("error", f"{source.type} source requires code", str(source_path), "code"))
            if source.type == "sql" and not source.connection:
                diagnostics.append(Diagnostic("error", "SQL source requires connection", str(source_path), "connection"))
            for dependency in source.depends_on:
                if dependency not in dashboard.sources:
                    diagnostics.append(Diagnostic("error", f"Unknown source dependency: {dependency}", str(source_path), "depends_on"))
            for parameter in source.params:
                if parameter not in parameter_ids:
                    diagnostics.append(Diagnostic("error", f"Unknown parameter: {parameter}", str(source_path), "params"))

        for widget_path, widget in dashboard.widgets.values():
            code_path = widget_path.parent / widget.code
            if not code_path.exists():
                diagnostics.append(Diagnostic("error", "Widget code does not exist", str(code_path), "code"))
            for dependency in widget.depends_on:
                if dependency not in node_ids:
                    diagnostics.append(Diagnostic("error", f"Unknown widget dependency: {dependency}", str(widget_path), "depends_on"))
            for parameter in widget.params:
                if parameter not in parameter_ids:
                    diagnostics.append(Diagnostic("error", f"Unknown parameter: {parameter}", str(widget_path), "params"))

        layout_widgets = {item.widget for item in dashboard.definition.layout.items}
        for widget_id in layout_widgets - set(dashboard.widgets):
            diagnostics.append(Diagnostic("error", f"Layout references unknown widget: {widget_id}", str(dashboard.definition_path), "layout.items"))

        section_ids: set[str] = set()
        section_widgets: set[str] = set()
        for section in dashboard.definition.sections:
            if section.id in section_ids:
                diagnostics.append(Diagnostic("error", f"Duplicate section id: {section.id}", str(dashboard.definition_path), "sections"))
            section_ids.add(section.id)
            for raw_view in section.views:
                view = view_definition(raw_view)
                if view.widget not in dashboard.widgets:
                    diagnostics.append(Diagnostic("error", f"Section references unknown widget: {view.widget}", str(dashboard.definition_path), "sections.views"))
                if view.widget in section_widgets:
                    diagnostics.append(Diagnostic("error", f"Widget belongs to more than one section: {view.widget}", str(dashboard.definition_path), "sections.views"))
                section_widgets.add(view.widget)

        contract = compile_filter_contract(dashboard.definition)
        for widget_id, filters in contract.items():
            ids = [item.id for item in filters]
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            if duplicates:
                diagnostics.append(Diagnostic("error", f"Filter ids shadow each other for view {widget_id}: {', '.join(duplicates)}", str(dashboard.definition_path), "sections"))
            raw_view = next(
                (
                    view_definition(value)
                    for section in dashboard.definition.sections
                    for value in section.views
                    if view_definition(value).widget == widget_id
                ),
                None,
            )
            if raw_view:
                unknown_bindings = set(raw_view.filter_bindings) - set(ids)
                for filter_id in sorted(unknown_bindings):
                    diagnostics.append(Diagnostic("error", f"View {widget_id} binds unknown filter: {filter_id}", str(dashboard.definition_path), "filter_bindings"))

        canvas = dashboard.definition.canvas
        for field in ("template", "style", "script"):
            value = getattr(canvas, field)
            if value and not (dashboard.root / value).exists():
                diagnostics.append(Diagnostic("error", f"Canvas {field} does not exist", str(dashboard.root / value), f"canvas.{field}"))
    return diagnostics
