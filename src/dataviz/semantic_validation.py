from __future__ import annotations

from dataviz.errors import Diagnostic
from dataviz.value_contract import static_control_choices
from dataviz.view_contracts import VIEW_TEMPLATE_CONTRACTS
from dataviz.workspace.controls import scoped_control_registry
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


def _diagnostic(
    dashboard: LoadedDashboard,
    level: str,
    code: str,
    message: str,
    field: str,
    details: dict | None = None,
) -> Diagnostic:
    return Diagnostic(
        level,
        message,
        str(dashboard.definition_path),
        field,
        code,
        details,
    )


def validate_dashboard_semantics(dashboard: LoadedDashboard) -> list[Diagnostic]:
    """Inspect the final compiled Dashboard without rebuilding its graphs.

    Layout and dependency correctness belong to their compilers.  This pass only
    combines those immutable contracts with the effective Presentation in order
    to report deterministic no-ops and explicitly non-blocking authoring advice.
    """

    diagnostics: list[Diagnostic] = []
    definition = dashboard.definition
    dependency = dashboard.dependency_contract
    layout = dashboard.layout_contract
    presentation = dashboard.presentation

    placed = {
        placement.view_id
        for section in layout.sections
        for placement in section.placements
    } | set(layout.mount_views)
    for view in definition.views:
        if view.id not in placed:
            diagnostics.append(
                _diagnostic(
                    dashboard,
                    "warning",
                    "semantic_view_unplaced",
                    f"View {view.id} has no compiled Layout placement or custom mount point",
                    f"views.{view.id}",
                    {"view": view.id},
                )
            )

    for key, control in dependency.controls.items():
        consumers = set(control.affected_views) | set(control.transform_consumers)
        consumers.update(control.content_fields)
        consumers.update(control.dependency_descendants)
        if control.writer_view:
            consumers.add(control.writer_view)
        if consumers:
            continue
        diagnostics.append(
            _diagnostic(
                dashboard,
                "warning",
                "semantic_control_unused",
                f"Control {key} has no View, Transform, content, binding, or dependent Control consumer",
                f"controls.{key}",
                {"control": key},
            )
        )

    if presentation:
        control_definitions = {
            f"query:{item.id}": item for item in definition.query_parameters
        }
        control_definitions.update(
            {
                key: control.definition
                for key, control in scoped_control_registry(definition).items()
            }
        )
        for control_key, visual in presentation.control_components.items():
            if visual.component != "checkbox-group":
                continue
            definition_for_control = control_definitions.get(control_key)
            if definition_for_control is None:
                continue
            choices = static_control_choices(definition_for_control)
            if choices and not 2 <= len(choices) <= 5:
                diagnostics.append(
                    _diagnostic(
                        dashboard,
                        "warning",
                        "semantic_checkbox_group_option_count",
                        f"Checkbox Group {control_key} has {len(choices)} static options; use it only for 2–5 peer choices and use Select for larger flat domains",
                        f"presentation.control_components.{control_key}.component",
                        {"control": control_key, "option_count": len(choices)},
                    )
                )

        views = {view.id: view for view in definition.views}
        for view_id, visual in presentation.views.items():
            view = views.get(view_id)
            if view is None:
                continue
            contract = VIEW_TEMPLATE_CONTRACTS[view.template]
            allowed = set(contract.get("optional", ()))
            if visual.config and "config" not in allowed:
                diagnostics.append(
                    _diagnostic(
                        dashboard,
                        "warning",
                        "semantic_renderer_config_noop",
                        f"View {view_id} template {view.template} does not consume Presentation config",
                        f"presentation.views.{view_id}.config",
                        {"view": view_id, "template": view.template},
                    )
                )
            if visual.options and "options" not in allowed:
                diagnostics.append(
                    _diagnostic(
                        dashboard,
                        "warning",
                        "semantic_renderer_options_noop",
                        f"View {view_id} template {view.template} does not consume Presentation options",
                        f"presentation.views.{view_id}.options",
                        {"view": view_id, "template": view.template},
                    )
                )
            if visual.engine and "engine" not in allowed and visual.engine != view.engine:
                diagnostics.append(
                    _diagnostic(
                        dashboard,
                        "warning",
                        "semantic_renderer_engine_noop",
                        f"View {view_id} template {view.template} has a fixed Renderer engine",
                        f"presentation.views.{view_id}.engine",
                        {"view": view_id, "template": view.template, "engine": visual.engine},
                    )
                )
            if visual.min_height and visual.min_height >= 900:
                diagnostics.append(
                    _diagnostic(
                        dashboard,
                        "advice",
                        "semantic_min_height_large",
                        f"View {view_id} min_height={visual.min_height}px may create unnecessary empty space",
                        f"presentation.views.{view_id}.min_height",
                        {"view": view_id, "min_height": visual.min_height},
                    )
                )

    views = {view.id: view for view in definition.views}
    for section in definition.sections:
        if section.template != "band":
            continue
        details = [
            view_id
            for view_id in section.views
            if views[view_id].template in {"table", "perspective"}
        ]
        if details:
            diagnostics.append(
                _diagnostic(
                    dashboard,
                    "advice",
                    "semantic_band_detail_view",
                    "Band sections are compact; detail tables may be easier to read in grid or stack",
                    f"sections.{section.id}.template",
                    {"section": section.id, "views": details},
                )
            )

    for transform_id, (_, transform) in dashboard.interactive_transforms.items():
        if transform.runtime.startswith("browser-") and transform.trigger == "apply":
            diagnostics.append(
                _diagnostic(
                    dashboard,
                    "advice",
                    "semantic_browser_transform_apply",
                    f"Browser Transform {transform_id} uses apply; use auto unless the calculation is intentionally expensive",
                    f"interactive_transforms.{transform_id}.trigger",
                    {"transform": transform_id, "runtime": transform.runtime},
                )
            )
    return diagnostics


def validate_workspace_semantics(workspace: LoadedWorkspace) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for dashboard in workspace.dashboards.values():
        try:
            diagnostics.extend(validate_dashboard_semantics(dashboard))
        except Exception:
            # Contract compilation failures are already emitted by the owning
            # compiler in validate_workspace.  Semantic validation never creates
            # a second, less precise diagnostic for the same broken graph.
            continue
    return diagnostics


__all__ = ["validate_dashboard_semantics", "validate_workspace_semantics"]
