"""Project a Page onto the existing single-entry compiler, without shared state."""

from __future__ import annotations

from typing import Any

from dataviz.errors import WorkspaceError
from dataviz.execution.references import parse_output_reference
from dataviz.workspace.models import DashboardDefinition


def page_definition(project: DashboardDefinition, page_id: str | None) -> DashboardDefinition:
    if not project.pages:
        if page_id is not None:
            raise WorkspaceError(f"Dashboard {project.id} has no Page: {page_id}")
        return project.model_copy(deep=True)
    page = next((page for page in project.pages if page.id == (page_id or project.pages[0].id)), None)
    if page is None:
        raise WorkspaceError(f"Unknown Page in Dashboard {project.id}: {page_id}")
    # Copy, never mutate the project or a sibling's parameter definitions.
    definition = project.model_copy(deep=True)
    definition.pages = []
    for name in ("query_parameters", "controls", "sections", "views", "layout"):
        setattr(definition, name, getattr(page.model_copy(deep=True), name))
    definition.title = page.title or project.title
    definition.subtitle = page.subtitle
    definition.description = page.description
    return definition


def page_nodes(definition: DashboardDefinition, registries: dict[str, dict]) -> dict[str, dict]:
    """Keep only the dependency closure of this Page's visual/option consumers.

    Traverse typed input fields, not arbitrary strings in titles or Plotly options.
    The normal compiler remains responsible for output/schema/control validation.
    """
    roots: list[str] = []
    controls: list[Any] = list(definition.controls)
    for section in definition.sections:
        controls.extend(section.controls)
    for view in definition.views:
        roots.extend(view.input_refs.values())
        controls.extend(view.controls)
    for control in controls:
        options = control.options
        if options is not None and getattr(options, "mode", None) == "infer":
            if options.source:
                roots.append(options.source)

    selected: dict[str, dict] = {kind: {} for kind in registries}

    def include(reference: str) -> None:
        parsed = parse_output_reference(reference)
        kind, local_id = parsed.node_id.split(":", 1)
        if local_id in selected[kind]:
            return
        entry = registries[kind].get(local_id)
        if entry is None:
            raise WorkspaceError(f"Page references unknown output: {reference}")
        selected[kind][local_id] = entry
        for upstream in getattr(entry[1], "inputs", {}).values():
            include(upstream)

    for reference in roots:
        include(reference)
    return selected
