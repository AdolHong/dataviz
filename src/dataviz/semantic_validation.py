from __future__ import annotations

import re

from dataviz.errors import Diagnostic
from dataviz.value_contract import static_control_choices
from dataviz.view_contracts import VIEW_TEMPLATE_CONTRACTS
from dataviz.workspace.controls import scoped_control_registry
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


def _sql_projects_wildcard(statement: str) -> bool:
    without_comments_or_strings = re.sub(
        r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'",
        " ",
        statement,
        flags=re.DOTALL,
    )
    for match in re.finditer(
        r"\bselect\b(?P<projection>.*?)\bfrom\b",
        without_comments_or_strings,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        projection = re.sub(
            r"^\s*(?:distinct|all)\b", "", match.group("projection"), flags=re.IGNORECASE
        )
        for item in projection.split(","):
            expression = item.strip()
            if expression == "*" or re.fullmatch(
                r"(?:[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\")\s*\.\s*\*",
                expression,
            ):
                return True
    return False


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
        consumers.update(edge.view_id for edge in control.writer_edges)
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

    analysis_outputs = [
        (f"source:{identifier}/{name}", output, source.description)
        for identifier, (_, source) in dashboard.sources.items()
        for name, output in source.outputs.items()
    ]
    analysis_outputs.extend(
        (f"dataset:{identifier}/{name}", output, transform.description)
        for identifier, (_, transform) in dashboard.dataset_transforms.items()
        for name, output in transform.outputs.items()
    )
    analysis_outputs.extend(
        (f"interactive:{identifier}/{name}", output, transform.description)
        for identifier, (_, transform) in dashboard.interactive_transforms.items()
        for name, output in transform.outputs.items()
    )
    for source_id, (definition_path, source) in dashboard.sources.items():
        if source.type != "sql":
            continue
        output = source.outputs["main"]
        semantics = output.semantics
        if semantics is None or not (
            semantics.visibility == "public"
            or semantics.assurance.status in {"reviewed", "certified"}
        ):
            continue
        code_path = (definition_path.parent / source.code).resolve()
        try:
            statement = code_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _sql_projects_wildcard(statement):
            diagnostics.append(
                _diagnostic(
                    dashboard,
                    "warning",
                    "analysis_sql_wildcard_output",
                    f"Reusable SQL Output source:{source_id}/main must list projected fields explicitly",
                    f"sources.{source_id}.code",
                    {
                        "reference": f"source:{source_id}/main",
                        "code": str(code_path),
                        "action": "Replace SELECT * or table.* with an explicit field list; count(*) is allowed.",
                    },
                )
            )
    for reference, output, _owner_description in analysis_outputs:
        semantics = output.semantics
        if semantics is None:
            continue
        declared_columns = {column.name for column in output.schema_}
        semantic_fields = set(semantics.measures)
        if semantics.time is not None:
            semantic_fields.add(semantics.time.field)
        for relationship in semantics.relationships:
            semantic_fields.update(relationship.fields)
        unknown_fields = sorted(semantic_fields - declared_columns) if declared_columns else []
        if unknown_fields:
            diagnostics.append(
                _diagnostic(
                    dashboard,
                    "error",
                    "analysis_semantics_field_unknown",
                    f"Output {reference} semantics references undeclared fields",
                    f"outputs.{reference}.semantics",
                    {"reference": reference, "fields": unknown_fields},
                )
            )
        missing_evidence = []
        for evidence in semantics.assurance.evidence:
            evidence_path = (dashboard.root / evidence).resolve()
            if not evidence_path.is_relative_to(dashboard.root.resolve()) or not evidence_path.is_file():
                missing_evidence.append(evidence)
        missing_evidence.sort()
        if missing_evidence:
            diagnostics.append(
                _diagnostic(
                    dashboard,
                    "error",
                    "analysis_assurance_evidence_missing",
                    f"Output {reference} assurance evidence cannot be located",
                    f"outputs.{reference}.semantics.assurance.evidence",
                    {"reference": reference, "paths": missing_evidence},
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
