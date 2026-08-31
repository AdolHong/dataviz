from __future__ import annotations

import base64
import gzip
import html
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote, unquote, urlparse

from jinja2 import Environment, StrictUndefined
from markupsafe import Markup

from dataviz.artifacts import ArtifactStore
from dataviz.components import component_runtime_assets
from dataviz.content_templates import (
    build_content_bindings,
    content_template_fields,
    interpolate_dashboard_content,
)
from dataviz.errors import ExecutionFailure
from dataviz.execution.dependencies import (
    DashboardDependencyContract,
)
from dataviz.execution.results import RunResult
from dataviz.execution.fingerprint import ensure_query_run_compatible
from dataviz.filesystem import atomic_write_bytes, atomic_write_text
from dataviz.plotly_runtime import PLOTLY_JS_VERSION, get_plotlyjs
from dataviz.state_snapshot import build_state_snapshot, normalize_consumer_revisions
from dataviz.templates import COMPONENT_REGISTRY_VERSION, RUNTIME_PROTOCOL_SCHEMA
from dataviz.value_contract import initial_control_value, static_control_choices
from dataviz.workspace.models import DashboardDefinition, DeclarativeViewDefinition
from dataviz.workspace.controls import (
    resolve_control_states,
    scoped_control_registry,
)
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace
from dataviz.workspace.control_components import resolve_control_component


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TANSTACK_TABLE_RUNTIME_VERSION = "9.2.4"
VIEW_PIPELINE_VISIBLE_STATUSES = {
    "queued",
    "loading",
    "stale",
    "error",
    "cancelled",
    "unavailable",
}


def _scrub_portable_paths(value: Any, workspace_root: Path) -> Any:
    """Remove machine-specific absolute roots from a shareable report payload."""
    if isinstance(value, str):
        replacements = (
            (str(workspace_root.resolve()), "<workspace>"),
            (str(PACKAGE_ROOT.resolve()), "<dataviz>"),
            (str(Path.home().resolve()), "~"),
        )
        result = value
        for source, replacement in sorted(
            replacements,
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if source and source != "/":
                result = result.replace(source, replacement)
        return result
    if isinstance(value, dict):
        return {
            key: _scrub_portable_paths(item, workspace_root)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_portable_paths(item, workspace_root) for item in value]
    return value


def _portable_failure(value: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    """Keep actionable failure evidence without exporting local tracebacks or logs."""
    omitted = any(key in value for key in ("traceback", "log"))
    portable = {
        key: item
        for key, item in value.items()
        if key not in {"traceback", "log"}
    }
    if isinstance(portable.get("details"), dict):
        details = dict(portable["details"])
        nested_omitted = any(key in details for key in ("traceback", "log"))
        for key in ("traceback", "log"):
            details.pop(key, None)
        portable["details"] = details
        omitted = omitted or nested_omitted
    if omitted:
        portable["debug_details_omitted"] = True
    return _scrub_portable_paths(portable, workspace_root)


def _portable_run_result(result: RunResult, workspace_root: Path) -> dict[str, Any]:
    payload = result.model_dump(mode="json", by_alias=True)
    for node in payload.get("nodes", {}).values():
        if not isinstance(node, dict):
            continue
        node.pop("log", None)
        if isinstance(node.get("error"), dict):
            node["error"] = _portable_failure(node["error"], workspace_root)
    return _scrub_portable_paths(payload, workspace_root)


class CanvasRenderer:
    def __init__(self, workspace: LoadedWorkspace):
        self.workspace = workspace

    def _workspace_runtime_asset(
        self,
        configured: str,
        *,
        field: str,
        directory: bool = False,
    ) -> Path:
        root = self.workspace.root.resolve()
        path = (root / configured).resolve()
        if not path.is_relative_to(root):
            raise ExecutionFailure(
                f"Local Runtime asset must stay inside the Workspace: {configured}",
                file=self.workspace.definition_path,
                details={
                    "code": "runtime_asset_outside_workspace",
                    "field": field,
                    "asset": configured,
                },
            )
        exists = path.is_dir() if directory else path.is_file()
        if not exists:
            expected = "directory" if directory else "file"
            raise ExecutionFailure(
                f"Configured Runtime {expected} does not exist: {configured}",
                file=path,
                details={
                    "code": "runtime_asset_missing",
                    "field": field,
                    "asset": configured,
                },
            )
        return path

    def _runtime_asset_usage(
        self,
        dashboard: LoadedDashboard,
        outputs: dict[str, Any],
        *,
        dependency_contract: DashboardDependencyContract,
        live: dict[str, str] | None,
        asset_mode: str,
        snapshot_interactions: set[str],
    ) -> dict[str, Any]:
        """Resolve the exact built-in browser assets needed by one report."""
        declarative_views = dashboard.definition.views
        chart_views = [
            view
            for view in declarative_views
            if view.template
            in {
                "line",
                "bar",
                "stacked-bar",
                "pie",
                "scatter",
                "heatmap",
                "radar",
            }
        ]
        formats = {artifact.format for artifact in outputs.values()}
        needs_plotly = (
            "plotly-json" in formats
            or "plotly" in dashboard.definition.canvas.client_libraries
            or bool(chart_views)
        )
        needs_perspective = (
            "perspective" in dashboard.definition.canvas.client_libraries
            or any(view.template == "perspective" for view in declarative_views)
        )
        runtime = self.workspace.definition.runtime
        reachable_interactive_ids = dependency_contract.reachable_interactive_order
        interactive_table_outputs = any(
            output.kind == "table"
            for transform_id in reachable_interactive_ids
            for output in dashboard.interactive_transforms[transform_id][1].outputs.values()
        )
        needs_arrow = (
            runtime.browser_table_transport != "json"
            and (
                live is not None
                or interactive_table_outputs
                or any(
                    artifact.kind == "table"
                    and (
                        runtime.browser_table_transport == "arrow"
                        or int(artifact.metadata.get("row_count", 0))
                        >= runtime.arrow_min_rows
                    )
                    for artifact in outputs.values()
                )
            )
        )
        active_browser_interactions = self._active_browser_interactions(
            dashboard,
            dependency_contract=dependency_contract,
            asset_mode=asset_mode,
            snapshot_interactions=snapshot_interactions,
        )
        network_dependencies: list[dict[str, str]] = []

        def add_remote(library: str, source: str) -> None:
            if urlparse(source).scheme in {"http", "https"}:
                network_dependencies.append({"library": library, "source": source})

        if needs_arrow:
            add_remote("apache-arrow", runtime.arrow_js)
        if needs_perspective:
            add_remote(
                "perspective",
                "https://cdn.jsdelivr.net/npm/@perspective-dev/",
            )
        for view in declarative_views:
            if view.template == "image" and view.url:
                add_remote(f"view-image:{view.id}", view.url)
        return {
            "plotly": needs_plotly,
            "arrow": needs_arrow,
            "perspective": needs_perspective,
            "active_browser_interactions": active_browser_interactions,
            "network_dependencies": network_dependencies,
        }

    def render(
        self,
        dashboard: LoadedDashboard,
        result: RunResult,
        *,
        asset_mode: str = "server",
        title: str | None = None,
        live: dict[str, str] | None = None,
        interaction: dict[str, Any] | None = None,
        session_id: str | None = None,
        control_state: dict[str, dict[str, Any]] | None = None,
        applied_revisions: dict[str, dict[str, dict[str, int]]] | None = None,
        applied_control_state: (
            dict[str, dict[str, dict[str, dict[str, Any]]]] | None
        ) = None,
        control_writer_provenance: dict[str, dict[str, Any]] | None = None,
        applied_writer_provenance: (
            dict[str, dict[str, dict[str, dict[str, Any]]]] | None
        ) = None,
        derived_outputs: dict[str, Any] | None = None,
        snapshot_interactions: set[str] | None = None,
        frame_id: str | None = None,
        dependency_contract: DashboardDependencyContract | None = None,
    ) -> str:
        ensure_query_run_compatible(dashboard, result)
        dependency_contract = dependency_contract or dashboard.dependency_contract
        server_interactions = sorted(
            identifier
            for identifier in dependency_contract.reachable_interactive_order
            if dashboard.interactive_transforms[identifier][1].runtime
            == "server-python"
        )
        if asset_mode == "inline" and interaction is None and server_interactions:
            raise ExecutionFailure(
                "HTML Export cannot execute Server Python Interactive Transforms; "
                "create a shared link from Dataviz Server instead",
                details={
                    "code": "html_export_server_runtime_unavailable",
                    "transforms": server_interactions,
                },
            )
        resolved_control_state = resolve_control_states(
            dashboard.definition,
            control_state,
            phase="canvas-hydration",
        )
        merged_outputs = {**result.outputs, **(derived_outputs or {})}
        render_state = SimpleNamespace(
            run_id=result.run_id,
            status=result.status,
            query_parameters=result.query_parameters,
            control_state=resolved_control_state,
            outputs=merged_outputs,
            nodes=result.nodes,
            snapshot_interactions=set(snapshot_interactions or set()),
        )
        try:
            content_bindings = build_content_bindings(
                dashboard.definition,
                result.query_parameters,
            )
            content_definition = interpolate_dashboard_content(
                dashboard.definition,
                result.query_parameters,
                resolved_control_state,
                fallback_title=dashboard.canvas_name,
            )
        except ValueError as error:
            raise ExecutionFailure(f"Invalid content template: {error}") from error
        store = ArtifactStore(self.workspace.root, result.run_id)
        binding_fields = set(content_bindings)
        declarative_views = {item.id: item for item in content_definition.views}
        view_html = {
            view_id: self._client_view_html(
                dashboard,
                view_id,
                render_state,
                declarative=declarative_views.get(view_id),
                binding_fields=binding_fields,
            )
            for view_id in dashboard.views
        }

        def view(view_id: str) -> str:
            return view_html.get(
                view_id,
                self._client_view_html(
                    dashboard,
                    view_id,
                    render_state,
                    declarative=declarative_views.get(view_id),
                    binding_fields=binding_fields,
                ),
            )

        canvas = content_definition.canvas
        if canvas.template:
            template_text = (dashboard.root / canvas.template).read_text(encoding="utf-8")
            environment = Environment(autoescape=True, undefined=StrictUndefined)
            template = environment.from_string(template_text)
            content_values = dict(content_template_fields(content_definition))

            def content(field: str) -> Markup:
                if field not in content_values:
                    raise ValueError(f"Unknown content field: {field}")
                value = html.escape(content_values[field])
                if field not in binding_fields:
                    return Markup(value)
                return Markup(
                    f'<span data-dv-content-field="{html.escape(field, quote=True)}">'
                    f"{value}</span>"
                )

            body = template.render(
                workspace=self.workspace.definition,
                dashboard=content_definition,
                parameters=result.query_parameters,
                controls={
                    key: entry.get("value")
                    for key, entry in resolved_control_state.items()
                },
                run=result,
                view=lambda value: Markup(view(value)),
                section_controls=lambda value: Markup(
                    self._context_controls(dashboard, render_state, "section", value)
                ),
                content=content,
                views=view_html,
            )
        else:
            body = self._default_body(
                dashboard,
                content_definition,
                view_html,
                result.query_parameters,
                resolved_control_state,
                binding_fields,
            )

        functional_style = (PACKAGE_ROOT / "server" / "static" / "canvas-functional.css").read_text(encoding="utf-8")
        component_assets = component_runtime_assets()
        component_style = component_assets["style"]
        component_scripts = "\n".join(
            f'<script data-component-package="{html.escape(item["package"])}" '
            f'data-component-asset="{html.escape(item["kind"])}">{item["source"]}</script>'
            for item in component_assets["scripts"]
        )
        base_style = ""
        if canvas.use_default_style:
            base_style = (PACKAGE_ROOT / "server" / "static" / "canvas.css").read_text(encoding="utf-8")
        style_paths = list(canvas.styles)
        script_paths = list(canvas.scripts)
        custom_style = "\n".join(
            path.read_text(encoding="utf-8")
            for relative in style_paths
            if (path := dashboard.root / relative).is_file()
        )
        custom_script = "\n".join(
            path.read_text(encoding="utf-8")
            for relative in script_paths
            if (path := dashboard.root / relative).is_file()
        )
        asset_usage = self._runtime_asset_usage(
            dashboard,
            merged_outputs,
            dependency_contract=dependency_contract,
            live=live,
            asset_mode=asset_mode,
            snapshot_interactions=snapshot_interactions or set(),
        )
        needs_plotly = asset_usage["plotly"]
        needs_arrow = asset_usage["arrow"]
        needs_perspective = asset_usage["perspective"]
        plotly_script = self._plotly_script(asset_mode) if needs_plotly else ""
        tanstack_table_script = self._tanstack_table_script(asset_mode)
        arrow_script = self._arrow_script() if needs_arrow else ""
        perspective_script = self._perspective_script() if needs_perspective else ""
        runtime = self._runtime_script()
        frozen_interactions = snapshot_interactions or set()
        active_browser_interactions = asset_usage["active_browser_interactions"]
        worker_source = self._interactive_worker_sources(
            dashboard,
            active_ids=active_browser_interactions,
        )
        interactive_transform_script = self._interactive_transform_script(
            dashboard,
            dependency_contract=dependency_contract,
            asset_mode=asset_mode,
            snapshot_interactions=frozen_interactions,
        )
        view_specs, repeat_specs = self._declarative_manifest(
            dashboard, content_definition
        )
        document_title = title or content_definition.title
        portable = (
            asset_mode in {"inline", "server"}
            and (
                bool(merged_outputs)
                or live is not None
                or render_state.status in {"partial", "error", "cancelled"}
            )
        )
        portable_bundle = (
            self._portable_bundle(
                dashboard,
                render_state,
                store,
                dependency_contract=dependency_contract,
                allow_missing=(
                    live is not None
                    or render_state.status in {"partial", "error", "cancelled"}
                ),
                asset_mode=asset_mode,
                session_id=session_id,
                snapshot_interactions=snapshot_interactions or set(),
            )
            if portable
            else None
        )
        portable_controls = (
            self._portable_controls(
                dashboard,
                render_state,
                dependency_contract=dependency_contract,
                snapshot_interactions=snapshot_interactions or set(),
            )
            if portable and asset_mode == "inline"
            else ""
        )
        state_summary = (
            dashboard.presentation.state_summary.model_dump(mode="json")
            if dashboard.presentation
            else {"enabled": False, "max_values": 3, "items": {}}
        )
        state_snapshot = build_state_snapshot(
            dashboard,
            query_parameters=result.query_parameters,
            control_state=resolved_control_state,
            draft_control_state=resolved_control_state,
            applied_revisions=applied_revisions,
            applied_control_state=applied_control_state,
            control_writer_provenance=control_writer_provenance,
            applied_writer_provenance=applied_writer_provenance,
        )
        meta = {
            "protocol": {
                "schema": RUNTIME_PROTOCOL_SCHEMA,
                "component_registry_version": COMPONENT_REGISTRY_VERSION,
            },
            "run_id": result.run_id,
            "dashboard_id": dashboard.definition.id,
            "frame_id": frame_id,
            "status": result.status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "query_parameters": result.query_parameters,
            "query_parameter_intents": result.query_parameter_intents,
            "control_state": resolved_control_state,
            "control_definitions": {
                item.key: item.definition.model_dump(mode="json")
                for item in scoped_control_registry(dashboard.definition).values()
            },
            "draft_control_state": dict(resolved_control_state),
            "applied_revisions": applied_revisions
            or {"views": {}, "transforms": {}},
            "consumer_applied_control_state": applied_control_state
            or {"views": {}, "transforms": {}},
            "control_writer_provenance": control_writer_provenance or {},
            "consumer_applied_writer_provenance": applied_writer_provenance
            or {"views": {}, "transforms": {}},
            "state_snapshot": state_snapshot,
            "state_summary": state_summary,
            "dependency_contract": dependency_contract.runtime_manifest(),
            "layout_contract": dashboard.layout_contract.as_dict(),
            "content_bindings": content_bindings,
            "portable": portable_bundle,
            "live": live,
            "interaction": interaction,
            "asset_mode": asset_mode,
            "snapshot_interactions": sorted(snapshot_interactions or set()),
            "view_specs": view_specs,
            "repeat_specs": repeat_specs,
            "runtime_versions": {
                **({"plotly_js": PLOTLY_JS_VERSION} if needs_plotly else {}),
                "tanstack_table": TANSTACK_TABLE_RUNTIME_VERSION,
                **(
                    {"perspective": self.workspace.definition.runtime.perspective_version}
                    if needs_perspective
                    else {}
                ),
            },
            "network_dependencies": asset_usage["network_dependencies"],
        }
        meta_json = json.dumps(meta, ensure_ascii=False, default=str).replace("</", "<\\/")
        return f"""<!doctype html>
<html lang="{html.escape(self.workspace.definition.context.language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(document_title)}</title>
  <style>{functional_style}\n{base_style}\n{component_style}\n{custom_style}</style>
  {plotly_script}
  {tanstack_table_script}
  {arrow_script}
  {perspective_script}
</head>
<body>
  {portable_controls}
  <main class="dv-canvas dv-layout--{html.escape(dashboard.definition.layout.template)} dv-theme--{html.escape(dashboard.definition.theme.preset)} dv-density--{html.escape(dashboard.definition.theme.density)}" data-dashboard="{html.escape(dashboard.definition.id)}" style="{self._theme_style(dashboard)}">
    {body}
  </main>
  <script>window.dataviz = {meta_json};</script>
  {worker_source}
  {component_scripts}
  <script>{runtime}</script>
  <script>{interactive_transform_script}</script>
  <script>{custom_script}</script>
  <script>if (window.dataviz.live) window.dataviz.connectLive?.(); if (window.dataviz.portable) {{ window.datavizRuntime.initializePortable().catch(error => console.error('[dataviz:init]', error)); }}</script>
</body>
</html>"""

    def _client_view_html(
        self,
        dashboard: LoadedDashboard,
        view_id: str,
        result: RunResult,
        *,
        declarative: DeclarativeViewDefinition | None = None,
        binding_fields: set[str] | None = None,
    ) -> str:
        declarative = declarative or dashboard.views.get(view_id)
        title = (declarative.title or declarative.id) if declarative else view_id
        description = (declarative.description or "") if declarative else ""
        status = declarative.template if declarative else "browser"
        chart_templates = {
            "line",
            "bar",
            "stacked-bar",
            "pie",
            "scatter",
            "heatmap",
            "radar",
        }
        renderer_label = (
            "plotly"
            if declarative and declarative.template in chart_templates
            else status
        )
        controls = self._context_controls(dashboard, result, "view", view_id)
        binding_fields = binding_fields or set()
        title_field = f"views.{view_id}.title"
        title_binding = (
            f' data-dv-content-field="{html.escape(title_field, quote=True)}"'
            if title_field in binding_fields
            else ""
        )
        description_field = f"views.{view_id}.description"
        description_binding = (
            f' data-dv-content-field="{html.escape(description_field, quote=True)}"'
            if description_field in binding_fields
            else ""
        )
        description_html = (
            f'<p class="dv-view-description"{description_binding}>{html.escape(description)}</p>'
            if description or description_binding
            else ""
        )
        pipeline = self._view_pipeline_signals(
            dashboard, view_id, result, renderer_label
        )
        return (
            f'<article class="dv-view dv-view--client" data-view-id="{html.escape(view_id)}" '
            'data-view-status="loading">'
            '<header class="dv-view-header"><div class="dv-view-heading">'
            f'<span class="dv-view-title" role="heading" aria-level="3"{title_binding}>{html.escape(title)}</span>'
            f'{description_html}</div>'
            f'<div class="dv-view-actions">{controls}{pipeline}'
            f'<small class="dv-view-type-label">{html.escape(renderer_label)}</small>'
            f'<small data-view-status-label hidden>{html.escape(status)}</small></div></header>'
            f'<div class="dv-state-summary dv-state-summary--view" data-state-summary-scope="view" '
            f'data-state-summary-owner="{html.escape(view_id, quote=True)}" hidden></div>'
            '<div class="dv-view-body"><div class="dv-view-placeholder">Waiting for dataset</div></div>'
            '</article>'
        )

    @staticmethod
    def _pipeline_node_title(dashboard: LoadedDashboard, node_id: str) -> str:
        kind, _, identifier = node_id.partition(":")
        if kind == "source" and identifier in dashboard.sources:
            definition = dashboard.sources[identifier][1]
            return definition.name or identifier
        if kind == "dataset" and identifier in dashboard.dataset_transforms:
            definition = dashboard.dataset_transforms[identifier][1]
            return definition.name or identifier
        if kind == "interactive" and identifier in dashboard.interactive_transforms:
            definition = dashboard.interactive_transforms[identifier][1]
            return definition.name or identifier
        return identifier or node_id

    def _view_pipeline_signals(
        self,
        dashboard: LoadedDashboard,
        view_id: str,
        result: RunResult | SimpleNamespace,
        renderer: str,
    ) -> str:
        nodes = getattr(result, "nodes", {}) or {}
        signals: list[str] = []
        for node_id in dashboard.dependency_contract.view_pipeline_nodes(view_id):
            node_result = nodes.get(node_id)
            if isinstance(node_result, dict):
                node_status = str(node_result.get("status") or "not_run")
            else:
                node_status = str(getattr(node_result, "status", "not_run"))
            title = self._pipeline_node_title(dashboard, node_id)
            hidden = "" if node_status in VIEW_PIPELINE_VISIBLE_STATUSES else " hidden"
            signals.append(
                '<button type="button" class="dv-view-pipeline-signal" '
                'data-view-pipeline-signal '
                f'data-view-pipeline-node="{html.escape(node_id, quote=True)}" '
                f'data-status="{html.escape(node_status, quote=True)}"{hidden} '
                f'title="{html.escape(title, quote=True)}" '
                f'aria-label="{html.escape(f"{title}: {node_status}", quote=True)}">'
                '<span class="dv-view-pipeline-light" aria-hidden="true"></span>'
                '<span class="dv-view-pipeline-tooltip" role="tooltip">'
                f'<strong>{html.escape(title)}</strong></span></button>'
            )
        renderer_title = f"{renderer} renderer"
        signals.append(
            '<span class="dv-view-pipeline-signal dv-view-renderer-signal" '
            f'data-view-renderer-signal data-status="not_run" hidden aria-hidden="true" '
            f'title="{html.escape(renderer_title, quote=True)}">'
            '<span class="dv-view-pipeline-light" aria-hidden="true"></span>'
            '<span class="dv-view-pipeline-tooltip" role="tooltip">'
            f'<strong>{html.escape(renderer_title)}</strong></span></span>'
        )
        return (
            '<span class="dv-view-pipeline" data-view-pipeline '
            'aria-label="View pipeline status">'
            + "".join(signals)
            + "</span>"
        )

    def _control_consumers(
        self,
        dashboard: LoadedDashboard,
        *,
        dependency_contract: DashboardDependencyContract | None = None,
    ) -> dict[str, list[SimpleNamespace]]:
        dependency_contract = dependency_contract or dashboard.dependency_contract
        return {
            key: [
                SimpleNamespace(
                    id=transform_id,
                    definition=dashboard.interactive_transforms[transform_id][1],
                )
                for transform_id in dependency.transform_consumers
            ]
            for key, dependency in dependency_contract.controls.items()
        }

    def _context_controls(
        self,
        dashboard: LoadedDashboard,
        result: RunResult,
        origin: str,
        owner_id: str,
    ) -> str:
        contract = dashboard.dependency_contract.view_control_contract
        controls = {}
        for effective_controls in contract.values():
            for item in effective_controls:
                if item.origin == origin and item.owner_id == owner_id:
                    controls.setdefault(item.key, item)
        if not controls:
            return ""
        control_view_id = owner_id if origin == "view" else None
        if origin == "section":
            section = next((item for item in dashboard.definition.sections if item.id == owner_id), None)
            if section and section.views:
                control_view_id = section.views[0]
        consumers_by_control = self._control_consumers(dashboard)
        control_fields = []
        manual_targets: set[str] = set()
        actionable = False
        for key, item in controls.items():
            definition = item.definition
            consumers = consumers_by_control.get(key, [])
            actionable = actionable or any(
                item.definition.trigger in {"apply", "manual"}
                for item in consumers
            )
            manual_targets.update(
                item.id
                for item in consumers
                if item.definition.trigger == "manual"
            )
            triggers = {consumer.definition.trigger for consumer in consumers}
            trigger = next(iter(triggers), "manual")
            frozen = any(
                consumer.id in set(getattr(result, "snapshot_interactions", set()))
                for consumer in consumers
            )
            control_fields.append(
                self._control_html(
                    dashboard,
                    key,
                    definition,
                    result.control_state.get(key, {}).get(
                        "value", initial_control_value(definition)
                    ),
                    view_id=control_view_id,
                    trigger=trigger,
                    frozen=frozen,
                )
            )
        scope = "Section" if origin == "section" else "View"
        groups = [
            '<section class="dv-context-controls__group">'
            f'<div>{"".join(control_fields)}</div></section>'
        ] if control_fields else []
        footer = ""
        if actionable:
            targets = html.escape(
                json.dumps(sorted(manual_targets), ensure_ascii=False),
                quote=True,
            )
            control_keys = html.escape(
                json.dumps(sorted(controls), ensure_ascii=False),
                quote=True,
            )
            footer = (
                '<footer class="dv-context-controls__footer">'
                '<span data-control-dirty-label>Results are current</span>'
                f'<button type="button" data-control-apply data-control-keys="{control_keys}" '
                f'data-analysis-always="true" data-manual-targets="{targets}">RUN</button>'
                '</footer>'
            )
        panel_attributes = self._control_panel_attributes(
            dashboard,
            origin,
            len(controls),
            owner_id,
        )
        editor_owner = f"{origin}:{owner_id}"
        return (
            f'<details class="dv-context-controls" data-control-origin="{html.escape(origin)}" '
            f'data-editor-owner="{html.escape(editor_owner, quote=True)}" '
            f'data-overlay-floating="true" {panel_attributes}>'
            '<summary title="左键打开控件，右键编辑默认配置">'
            '<span class="dv-context-controls__mark">C</span>'
            f'<strong>{scope} controls</strong>'
            '<span class="dv-control-chevron" aria-hidden="true"><svg viewBox="0 0 16 16">'
            '<path d="m4 6 4 4 4-4"/></svg></span></summary>'
            f'<div class="dv-context-controls__panel">{"".join(groups)}{footer}</div></details>'
        )

    def _theme_style(self, dashboard: LoadedDashboard) -> str:
        theme = dashboard.definition.theme
        values = {
            "--dv-accent": theme.accent,
            "--dv-paper": theme.background,
            "--dv-panel": theme.panel,
            "--dv-ink": theme.ink,
        }
        return ";".join(
            f"{name}:{html.escape(value, quote=True)}"
            for name, value in values.items()
            if value
        )

    def _declarative_manifest(
        self,
        dashboard: LoadedDashboard,
        definition: DashboardDefinition,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        view_specs = [item.model_dump(mode="json") for item in definition.views]
        for view in view_specs:
            if view["template"] != "image" or not view.get("url"):
                continue
            parsed = urlparse(view["url"])
            if parsed.scheme or parsed.netloc:
                continue
            path = (dashboard.root / unquote(parsed.path)).resolve()
            if not path.is_relative_to(dashboard.root) or not path.is_file():
                # Loader/preflight owns the user-facing diagnostic. Keep this
                # defensive branch from publishing an unsafe or broken URL.
                raise ExecutionFailure(
                    f"Image View asset is unavailable: {view['url']}",
                    details={
                        "code": "view_image_asset_unavailable",
                        "view": view["id"],
                        "url": view["url"],
                    },
                )
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            payload = base64.b64encode(path.read_bytes()).decode("ascii")
            view["url"] = f"data:{mime_type};base64,{payload}"
        repeat_specs: list[dict[str, Any]] = []
        for section in definition.sections:
            if not section.repeat:
                continue
            view_ids = list(section.views)
            repeat_specs.append(
                {
                    "section": section.id,
                    "template": section.template,
                    **section.repeat.model_dump(mode="json"),
                    "view": section.repeat.view or (view_ids[0] if view_ids else None),
                }
            )
        return view_specs, repeat_specs

    def _active_browser_interactions(
        self,
        dashboard: LoadedDashboard,
        *,
        dependency_contract: DashboardDependencyContract,
        asset_mode: str,
        snapshot_interactions: set[str],
    ) -> set[str]:
        return {
            identifier
            for identifier in dependency_contract.reachable_interactive_order
            if dashboard.interactive_transforms[identifier][1].runtime == "browser-js"
            and not (
                asset_mode == "inline"
                and (
                    identifier in snapshot_interactions
                    or dashboard.interactive_transforms[identifier][1].export.mode
                    == "unavailable"
                )
            )
        }

    def _interactive_transform_script(
        self,
        dashboard: LoadedDashboard,
        *,
        dependency_contract: DashboardDependencyContract,
        asset_mode: str,
        snapshot_interactions: set[str],
    ) -> str:
        registrations = []
        for transform_id in dependency_contract.reachable_interactive_order:
            transform_path, definition = dashboard.interactive_transforms[transform_id]
            code = "null"
            dependencies = "{}"
            needs_browser_code = definition.runtime != "server-python" and not (
                asset_mode == "inline"
                and (
                    transform_id in snapshot_interactions
                    or definition.export.mode == "unavailable"
                )
            )
            if needs_browser_code:
                code_path = (transform_path.parent / definition.code).resolve()
                code = json.dumps(
                    code_path.read_text(encoding="utf-8"), ensure_ascii=False
                ).replace("</", "<\\/")
                dependencies = json.dumps(
                    self._browser_dependency_sources(transform_path, definition),
                    ensure_ascii=False,
                ).replace("</", "<\\/")
            spec_payload = definition.model_dump(mode="json", by_alias=True)
            spec = json.dumps(
                spec_payload,
                ensure_ascii=False,
                default=str,
            ).replace("</", "<\\/")
            entrypoint = json.dumps(definition.entrypoint)
            registrations.append(
                f"window.datavizRuntime.registerInteractiveTransform({spec}, "
                f"{{code:{code},entrypoint:{entrypoint},dependencies:{dependencies}}});"
            )
        registrations.append("window.datavizRuntime.configureSnapshotControls();")
        return "\n".join(registrations)

    def _browser_dependency_sources(self, definition_path: Path, definition) -> dict[str, str]:
        """Embed explicitly declared browser-runtime files under stable relative names."""
        root = definition_path.parent.resolve()
        sources: dict[str, str] = {}
        for value in definition.code_dependencies:
            path = (root / value).resolve()
            candidates = [path] if path.is_file() else sorted(
                item for item in path.rglob("*") if item.is_file()
            )
            for candidate in candidates:
                relative = candidate.relative_to(root).as_posix()
                try:
                    sources[relative] = candidate.read_text(encoding="utf-8")
                except UnicodeError as error:
                    raise ExecutionFailure(
                        "Browser Runtime code dependencies must be UTF-8 text",
                        file=candidate,
                    ) from error
        return sources

    def _interactive_worker_sources(
        self,
        dashboard: LoadedDashboard,
        *,
        active_ids: set[str],
    ) -> str:
        if not active_ids:
            return ""
        source = (
            PACKAGE_ROOT / "server" / "static" / "interactive-js-worker.js"
        ).read_text(encoding="utf-8")
        encoded = json.dumps(source, ensure_ascii=False).replace("</", "<\\/")
        return f"<script>window.datavizInteractiveJsWorkerSource={encoded};</script>"

    def _portable_bundle(
        self,
        dashboard: LoadedDashboard,
        result: RunResult,
        store: ArtifactStore,
        *,
        dependency_contract: DashboardDependencyContract | None = None,
        allow_missing: bool = False,
        asset_mode: str = "inline",
        session_id: str | None = None,
        snapshot_interactions: set[str] | None = None,
    ) -> dict[str, Any]:
        dependency_contract = dependency_contract or dashboard.dependency_contract
        outputs: dict[str, Any] = {}
        output_transports: dict[str, Any] = {}
        output_kinds: dict[str, str] = {}
        output_schemas: dict[str, list[dict[str, Any]]] = {}
        output_errors: dict[str, Any] = {}
        reachable = set(dependency_contract.base_output_roots)
        for transform_id in snapshot_interactions or set():
            definition = dashboard.interactive_transforms[transform_id][1]
            reachable.update(
                f"interactive:{transform_id}/{name}"
                for name in definition.outputs
            )
        runtime = self.workspace.definition.runtime
        row_count = 0
        payload_bytes = 0
        pending_outputs: list[str] = []
        for reference in sorted(reachable):
            artifact = result.outputs.get(reference)
            if artifact is None:
                if allow_missing:
                    node_id = reference.rsplit("/", 1)[0]
                    node = result.nodes.get(node_id)
                    if node and node.status in {"error", "cancelled", "unavailable"}:
                        failure = dict(node.error or {})
                        failure.setdefault("code", node.status)
                        failure.setdefault(
                            "message",
                            f"{node_id} ended with status {node.status}",
                        )
                        output_errors[reference] = _portable_failure(
                            failure,
                            self.workspace.root,
                        )
                    else:
                        pending_outputs.append(reference)
                    continue
                raise ExecutionFailure(f"Report input is unavailable: {reference}")
            if artifact.kind == "table":
                table_rows = int(artifact.metadata.get("row_count", 0))
                row_count += table_rows
                output_schemas[reference] = artifact.schema_ or []
                use_arrow = runtime.browser_table_transport == "arrow" or (
                    runtime.browser_table_transport == "auto"
                    and table_rows >= runtime.arrow_min_rows
                )
                if use_arrow:
                    if asset_mode == "server" and session_id:
                        encoded_reference = "/".join(
                            quote(part, safe="") for part in reference.split("/")
                        )
                        output_transports[reference] = {
                            "encoding": "arrow-ipc",
                            "compression": "http",
                            "url": (
                                f"/api/runs/{quote(result.run_id, safe='')}/outputs/"
                                f"{encoded_reference}?session_id={quote(session_id, safe='')}&format=arrow"
                            ),
                            "row_count": table_rows,
                            "schema": artifact.schema_ or [],
                            "content_hash": artifact.content_hash,
                        }
                    else:
                        arrow = store.read_arrow_ipc(artifact)
                        compressed = gzip.compress(arrow, compresslevel=6)
                        chunk_size = runtime.arrow_chunk_bytes
                        chunks = [
                            base64.b64encode(compressed[index:index + chunk_size]).decode("ascii")
                            for index in range(0, len(compressed), chunk_size)
                        ]
                        output_transports[reference] = {
                            "encoding": "arrow-ipc",
                            "compression": "gzip",
                            "chunks": chunks,
                            "row_count": table_rows,
                            "byte_count": len(arrow),
                            "compressed_bytes": len(compressed),
                            "schema": artifact.schema_ or [],
                            "content_hash": artifact.content_hash,
                        }
                        payload_bytes += sum(len(chunk.encode("ascii")) for chunk in chunks)
                    output_kinds[reference] = artifact.kind
                    continue
                value = store.read_value(artifact)
                value = json.loads(value.to_json(orient="records", date_format="iso"))
            else:
                value = store.read_value(artifact)
                if isinstance(value, Path):
                    continue
            payload_bytes += len(
                json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
            outputs[reference] = value
            output_kinds[reference] = artifact.kind
        if row_count > runtime.max_embedded_rows:
            raise ExecutionFailure(
                f"Browser payload has {row_count:,} rows; limit is {runtime.max_embedded_rows:,}",
                details={
                    "hint": "Aggregate with a Dataset Transform or raise runtime.max_embedded_rows explicitly.",
                    "references": sorted(reachable),
                },
            )
        if payload_bytes > runtime.max_embedded_bytes:
            raise ExecutionFailure(
                f"Browser payload is {payload_bytes:,} bytes; limit is {runtime.max_embedded_bytes:,}",
                details={
                    "hint": "Reduce the Named Outputs used by Views or raise runtime.max_embedded_bytes explicitly.",
                    "references": sorted(reachable),
                },
            )
        return {
            "outputs": outputs,
            "output_transports": output_transports,
            "output_kinds": output_kinds,
            "output_schemas": output_schemas,
            "output_errors": output_errors,
            "pending_outputs": pending_outputs,
        }

    def _control_panel_attributes(
        self,
        dashboard: LoadedDashboard,
        role: str,
        count: int,
        owner_id: str | None = None,
    ) -> str:
        presentation = dashboard.presentation
        config = None
        if presentation is not None:
            if role in {"query", "dashboard"}:
                config = getattr(presentation.control_panels, role)
            elif role == "section" and owner_id is not None:
                section = presentation.sections.get(owner_id)
                config = section.controls if section is not None else None
            elif role == "view" and owner_id is not None:
                view = presentation.views.get(owner_id)
                config = view.controls if view is not None else None
        requested_template = config.template if config is not None else "auto"
        template = (
            ("stack" if count <= 1 else "grid")
            if requested_template == "auto" and role == "query"
            else "stack"
            if requested_template == "auto"
            else requested_template
        )
        width_name = config.width if config is not None else "auto"
        widths = {"compact": 460, "regular": 680, "wide": 880}
        if width_name in widths:
            width = widths[width_name]
        elif template == "stack" or count <= 1:
            width = 560 if role == "dashboard" else 480
        elif count <= 4:
            width = 680
        else:
            width = 880
        columns = (
            1
            if template == "stack"
            else (config.columns if config else None) or (6 if role == "query" else 1)
        )
        column_width = (
            (config.column_width if config is not None else None)
            or (280 if role == "query" else 240)
        )
        density = config.density if config is not None else "comfortable"
        effective_columns = 1 if template == "stack" else max(1, min(count or 1, columns))
        return (
            'data-dv-control-panel '
            f'data-control-role="{html.escape(role, quote=True)}" '
            f'data-control-count="{count}" '
            f'data-control-template="{html.escape(template, quote=True)}" '
            f'data-control-columns="{columns}" '
            f'data-control-column-width="{column_width}" '
            f'data-control-effective-columns="{effective_columns}" '
            f'data-control-density="{html.escape(density, quote=True)}" '
            f'data-control-width="{html.escape(width_name, quote=True)}" '
            f'data-overlay-width="{width}" '
            f'style="--dv-control-column-width:{column_width}px;'
            f'--dv-control-columns:{effective_columns}"'
        )

    def _portable_controls(
        self,
        dashboard: LoadedDashboard,
        result,
        *,
        dependency_contract: DashboardDependencyContract,
        snapshot_interactions: set[str],
    ) -> str:
        contract = dependency_contract.view_control_contract
        controls: dict[str, dict[str, Any]] = {}
        for view_id, effective_controls in contract.items():
            for item in effective_controls:
                control = controls.setdefault(
                    item.key,
                    {"control": item, "views": []},
                )
                control["views"].append(view_id)

        consumers_by_control = self._control_consumers(
            dashboard,
            dependency_contract=dependency_contract,
        )
        control_items: list[str] = []
        dashboard_control_keys: list[str] = []
        for key, control in controls.items():
            item = control["control"]
            if item.origin != "dashboard":
                continue
            dashboard_control_keys.append(key)
            definition = item.definition
            consumers = consumers_by_control.get(key, [])
            triggers = {consumer.definition.trigger for consumer in consumers}
            trigger = next(iter(triggers), "manual")
            frozen = any(
                consumer.id in snapshot_interactions
                for consumer in consumers
            )
            control_items.append(
                self._control_html(
                    dashboard,
                    key,
                    definition,
                    result.control_state.get(key, {}).get(
                        "value", initial_control_value(definition)
                    ),
                    view_id=(control["views"][0] if control["views"] else None),
                    trigger=trigger,
                    frozen=frozen,
                )
            )
        def query_value_text(value: Any) -> str:
            if isinstance(value, list):
                separator = " → " if len(value) == 2 else "、"
                return separator.join(str(item) for item in value)
            if value is None:
                return "—"
            return str(value)

        query_items = "".join(
            '<div class="dv-query-value field">'
            f'<label>{html.escape(item.label or item.id)}</label>'
            f'<output>{html.escape(query_value_text(result.query_parameters.get(item.id)))}</output>'
            '</div>'
            for item in dashboard.definition.query_parameters
        )
        actionable = [
            transform_id
            for transform_id in dependency_contract.reachable_interactive_order
            for transform in [dashboard.interactive_transforms[transform_id][1]]
            if transform.trigger in {"apply", "manual"}
            and transform_id not in snapshot_interactions
            and (
                not dependency_contract.interactive_control_inputs[transform_id]
                or any(
                    key in dashboard_control_keys
                    for key in {
                        binding["control"]
                        for binding in dependency_contract.interactive_control_inputs[
                            transform_id
                        ].values()
                    }
                )
            )
        ]
        manual_targets = [
            transform_id
            for transform_id in actionable
            if dashboard.interactive_transforms[transform_id][1].trigger == "manual"
        ]
        query_panel_attributes = self._control_panel_attributes(
            dashboard, "query", len(dashboard.definition.query_parameters)
        )
        control_panel_attributes = self._control_panel_attributes(
            dashboard,
            "dashboard",
            len(dashboard_control_keys),
        )
        control_group = (
            '<section class="dv-runtime-control-group">'
            f'<div class="dv-control-fields">{"".join(control_items)}</div></section>'
            if control_items
            else ""
        )
        control_block = ""
        if dashboard_control_keys or actionable:
            encoded_targets = html.escape(
                json.dumps(manual_targets, ensure_ascii=False),
                quote=True,
            )
            encoded_keys = html.escape(
                json.dumps(dashboard_control_keys, ensure_ascii=False),
                quote=True,
            )
            footer = (
                '<footer><span data-control-dirty-label>Results are current</span>'
                f'<button type="button" data-control-apply data-control-keys="{encoded_keys}" '
                f'data-analysis-always="{str(bool(actionable)).lower()}" '
                f'data-manual-targets="{encoded_targets}">RUN</button></footer>'
                if control_items or actionable
                else ""
            )
            control_block = (
                f'<details class="dv-runtime-control" name="dv-runtime-header-control" '
                f'data-runtime-popover data-overlay-group="runtime-header" data-control-origin="dashboard" '
                f'data-overlay-floating="true" {control_panel_attributes}>'
                '<summary><span class="dv-context-controls__mark">C</span>'
                '<strong>DASHBOARD CONTROLS</strong>'
                '<span class="dv-control-chevron" aria-hidden="true"><svg viewBox="0 0 16 16">'
                '<path d="m4 6 4 4 4-4"/></svg></span></summary>'
                '<div class="dv-runtime-popover dv-runtime-popover--controls">'
                f'<div class="dv-runtime-control-groups">{control_group}</div>{footer}'
                '</div></details>'
            )
        card_is_present = bool(dashboard.definition.query_parameters)
        card_hidden = "" if card_is_present else " hidden"
        query_control = ""
        if card_is_present:
            query_control = (
                '<div class="query-run-control dv-runtime-query-run-control">'
                '<button class="query-run-control__primary" type="button" disabled '
                'aria-disabled="true" title="导出报告已固化查询结果">'
                '<span class="query-run-control__copy"><strong>查询</strong></span></button>'
                '<button class="query-run-control__toggle" type="button" '
                'data-runtime-query-toggle aria-controls="dv-runtime-query-panel" '
                'aria-expanded="false" aria-keyshortcuts="Q" title="展开查询参数 (Q)" '
                'aria-label="展开查询参数">'
                '<span class="query-run-control__chevron" aria-hidden="true"></span>'
                '</button></div>'
            )
        return (
            '<header class="dv-runtime-header dv-shell-header" aria-label="Report controls">'
            '<div class="dv-runtime-brand dv-shell-brand" aria-label="Dataviz">'
            '<span class="dv-runtime-brand__mark" aria-hidden="true">D/V</span>'
            '<strong>DATAVIZ</strong></div>'
            '<nav class="dv-runtime-actions dv-shell-header-actions" '
            'aria-label="Dataset and analysis controls">'
            f'{control_block}{query_control}</nav></header>'
            f'<section class="dv-runtime-query-tray dv-query-card-host" '
            f'{query_panel_attributes} data-open="false"{card_hidden}>'
            '<div class="dv-query-card">'
            '<header class="dv-query-card__header"><h2>查询参数</h2></header>'
            '<div id="dv-runtime-query-panel" class="dv-runtime-popover '
            'dv-runtime-popover--query dv-runtime-query-panel dv-query-card__body" '
            'data-control-panel-body hidden>'
            f'<div class="dv-runtime-query-values">{query_items}</div></div></div></section>'
            '<div class="dv-runtime-shortcut-toast" data-runtime-shortcut-toast role="status" '
            'aria-live="polite" aria-atomic="true" hidden></div>'
            '<dialog class="dv-runtime-shortcuts" data-runtime-shortcut-help '
            'aria-labelledby="dv-runtime-shortcuts-title"><form method="dialog">'
            '<header><h2 id="dv-runtime-shortcuts-title">快捷键</h2>'
            '<button type="submit" aria-label="关闭">×</button></header><dl>'
            '<div><dt><kbd>Q</kbd></dt><dd>查询参数</dd></div>'
            '<div><dt><kbd>Esc</kbd></dt><dd>关闭临时面板</dd></div>'
            '<div><dt><kbd>?</kbd></dt><dd>快捷键帮助</dd></div>'
            '</dl><footer><button type="submit">关闭</button></footer></form></dialog>'
        )

    def _control_html(
        self,
        dashboard: LoadedDashboard,
        key: str,
        definition,
        value: Any,
        *,
        view_id: str | None = None,
        trigger: str,
        frozen: bool,
    ) -> str:
        presentation = self._control_component_presentation(
            dashboard, key, definition
        )
        field = self._portable_field(
            key,
            definition,
            value,
            presentation,
            view_id=(
                view_id
                or (
                    key.split(":", 1)[1].split("/", 1)[0]
                    if key.startswith("view:")
                    else None
                )
            ),
            trigger=trigger,
            disabled=frozen,
        )
        return (
            f'<label class="dv-control-field" data-control-key="{html.escape(key)}" '
            f'data-control-update-trigger="{html.escape(trigger)}" data-control-frozen="{str(frozen).lower()}" '
            f'data-control-path="{str(bool(definition.path_fields)).lower()}" '
            f'data-control-span="{int(presentation.get("span", 1))}">'
            f'<span>{html.escape(definition.label or definition.id)}</span>{field}'
            f'{"<small>Fixed snapshot</small>" if frozen else ""}</label>'
        )

    def _control_component_presentation(
        self,
        dashboard: LoadedDashboard,
        key: str,
        definition,
    ) -> dict[str, Any]:
        configured = (
            dashboard.presentation.control_components.get(key)
            if dashboard.presentation
            else None
        )
        return resolve_control_component(definition, configured)

    def _portable_field(
        self,
        key: str,
        definition,
        value: Any,
        presentation: dict[str, Any] | None = None,
        view_id: str | None = None,
        *,
        trigger: str = "auto",
        disabled: bool = False,
    ) -> str:
        """Render the canonical native value plus one packaged Data Entry host."""

        presentation = presentation or resolve_control_component(definition)
        component = presentation["component"]
        escaped_key = html.escape(key, quote=True)
        label = html.escape(definition.label or definition.id, quote=True)
        path_fields = list(getattr(definition, "path_fields", []) or [])
        role_attributes = (
            f'data-control-state-input="{escaped_key}" '
            f'data-control-update-trigger="{html.escape(trigger, quote=True)}"'
        )
        common_native = (
            f'aria-label="{label}" data-control-input '
            f'data-control-type="{html.escape(definition.type, quote=True)}" '
            f'data-value-type="{html.escape(definition.value_type, quote=True)}" '
            f'{role_attributes}'
            + (" disabled" if disabled else "")
            + (
                " required"
                if definition.required and definition.value_type != "boolean"
                else ""
            )
        )
        constraints = ""
        if definition.min is not None:
            constraints += f' min="{html.escape(str(definition.min), quote=True)}"'
        if definition.max is not None:
            constraints += f' max="{html.escape(str(definition.max), quote=True)}"'
        if definition.step is not None:
            constraints += f' step="{html.escape(str(definition.step), quote=True)}"'
        elif definition.value_type == "integer":
            constraints += ' step="1"'
        if definition.min_date:
            constraints += f' min="{html.escape(definition.min_date, quote=True)}"'
        if definition.max_date:
            constraints += f' max="{html.escape(definition.max_date, quote=True)}"'
        if definition.max_length:
            constraints += f' maxlength="{int(definition.max_length)}"'

        if definition.type in {"single_select", "multiple_select"}:
            choices = static_control_choices(definition)
            typed_choices = bool(path_fields) or any(
                not isinstance(choice.value, str) for choice in choices
            )
            encode = (
                lambda item: json.dumps(
                    item, ensure_ascii=False, separators=(",", ":")
                )
                if typed_choices
                else str(item)
            )
            if definition.type == "multiple_select":
                selected_values = value if isinstance(value, list) else []
            elif path_fields:
                selected_values = [value] if isinstance(value, (list, tuple)) else []
            else:
                selected_values = [value]
            selected = {encode(item) for item in selected_values if item is not None}
            options = ""
            if definition.type == "single_select":
                empty_selected = (
                    not value
                    if isinstance(value, (list, tuple))
                    else value in {None, ""}
                )
                options += (
                    '<option value="" data-empty-option="true" hidden'
                    f'{" selected" if empty_selected else ""}></option>'
                )
            for choice in choices:
                serialized = encode(choice.value)
                metadata = ""
                if choice.group:
                    metadata += f' data-group="{html.escape(choice.group, quote=True)}"'
                if choice.description:
                    metadata += (
                        f' data-description="{html.escape(choice.description, quote=True)}"'
                    )
                if choice.keywords:
                    metadata += (
                        f' data-keywords="{html.escape(" ".join(choice.keywords), quote=True)}"'
                    )
                options += (
                    f'<option value="{html.escape(serialized, quote=True)}"{metadata}'
                    f'{" selected" if serialized in selected else ""}>'
                    f'{html.escape(choice.label)}</option>'
                )
            multiple = " multiple" if definition.type == "multiple_select" else ""
            native = (
                f'<select {common_native} data-value-encoding="'
                f'{"json" if typed_choices else "string"}"{multiple}>{options}</select>'
            )
        else:
            if definition.value_type == "boolean":
                native = (
                    f'<input type="checkbox" {common_native}'
                    f'{" checked" if bool(value) else ""}>'
                )
            else:
                input_type = (
                    "range"
                    if component == "slider" and definition.type == "single_input"
                    else "number"
                    if definition.value_type in {"number", "integer"}
                    else "date"
                    if definition.type == "single_input" and definition.value_type == "date"
                    else "text"
                )
                display = (
                    ",".join("" if item is None else str(item) for item in value)
                    if isinstance(value, (list, tuple))
                    else ""
                    if value is None
                    else str(value)
                )
                value_attribute = html.escape(display, quote=True)
                placeholder = html.escape(definition.placeholder, quote=True)
                if component == "input" and presentation.get("multiline"):
                    native = (
                        f'<textarea {common_native}{constraints} placeholder="{placeholder}">'
                        f'{html.escape(display)}</textarea>'
                    )
                else:
                    native = (
                        f'<input type="{input_type}" {common_native}{constraints} '
                        f'value="{value_attribute}" placeholder="{placeholder}">'
                    )

        clearable = (
            definition.clearable
            if definition.clearable is not None
            else (
                not definition.required
                and definition.type in {
                    "single_input", "multiple_input", "single_select",
                    "multiple_select", "range_input",
                }
            )
        )
        allow_empty = list(getattr(definition, "allow_empty", (False, False)))
        suggestions = [
            item.model_dump(mode="json") for item in definition.suggestions
        ]
        levels = [
            {
                "field": field,
                "label": (
                    presentation.get("level_labels", [])[index]
                    if index < len(presentation.get("level_labels", []))
                    else field
                ),
            }
            for index, field in enumerate(path_fields)
        ]
        hidden_native = component in {
            "select",
            "radio-group",
            "checkbox-group",
            "cascader",
            "tree-select",
            "range-picker",
            "multiple-input",
            "switch",
        } or (component == "slider" and definition.type == "range_input")
        attrs = (
            f'data-control-component="{html.escape(component, quote=True)}" '
            f'data-requested-component="{html.escape(presentation.get("requested_component", "auto"), quote=True)}" '
            f'data-auto-reason="{html.escape(presentation.get("auto_reason", ""), quote=True)}" '
            f'data-required="{str(bool(definition.required)).lower()}" '
            f'data-control-type="{html.escape(definition.type, quote=True)}" '
            f'data-value-type="{html.escape(definition.value_type, quote=True)}" '
            f'data-clearable="{str(bool(clearable)).lower()}" '
            f'data-show-unavailable="{str(bool(presentation.get("show_unavailable", False))).lower()}" '
            f'data-search-mode="{html.escape(presentation.get("search", "auto"), quote=True)}" '
            f'data-virtual-mode="{html.escape(presentation.get("virtual", "auto"), quote=True)}" '
            f'data-search-threshold="{int(presentation.get("search_threshold", 9))}" '
            f'data-virtual-threshold="{int(presentation.get("virtual_threshold", 200))}" '
            f'data-max-tag-count="{int(presentation.get("max_tag_count", 2))}" '
            f'data-max-selected="{definition.max_selected or ""}" '
            f'data-max-items="{definition.max_items or ""}" '
            f'data-hide-selected="{str(bool(presentation.get("hide_selected", False))).lower()}" '
            f'data-search-placeholder="{html.escape(presentation.get("search_placeholder", "Search options…"), quote=True)}" '
            f'data-empty-text="{html.escape(presentation.get("empty_text", "No matching options"), quote=True)}" '
            f'data-placeholder="{html.escape(definition.placeholder or "Choose…", quote=True)}" '
            f'data-select-all-label="{html.escape(presentation.get("select_all_label", "Select all"), quote=True)}" '
            f'data-invert-label="{html.escape(presentation.get("invert_label", "Invert"), quote=True)}" '
            f'data-clear-label="{html.escape(presentation.get("clear_label", "Clear"), quote=True)}" '
            f'data-path-separator="{html.escape(presentation.get("path_separator", " / "), quote=True)}" '
            f'data-selection-strategy="{html.escape(presentation.get("selection_strategy", "leaf"), quote=True)}" '
            f'data-show-checked-strategy="{html.escape(presentation.get("show_checked_strategy", "child"), quote=True)}" '
            f'data-start-label="{html.escape(presentation.get("start_label", "Start"), quote=True)}" '
            f'data-end-label="{html.escape(presentation.get("end_label", "End"), quote=True)}" '
            f'data-min-date="{html.escape(definition.min_date or "", quote=True)}" '
            f'data-max-date="{html.escape(definition.max_date or "", quote=True)}" '
            f'data-allow-empty-start="{str(bool(allow_empty[0])).lower()}" '
            f'data-allow-empty-end="{str(bool(allow_empty[1])).lower()}" '
            f'data-presets="{html.escape(json.dumps(presentation.get("presets", []), ensure_ascii=False), quote=True)}" '
            f'data-item-height="{int(presentation.get("item_height", 38))}" '
            f'data-viewport-height="{int(presentation.get("viewport_height", 304))}" '
            f'data-overscan="{int(presentation.get("overscan", 5))}" '
            f'data-default-expand-depth="{int(presentation.get("default_expand_depth", 0))}" '
            f'data-option-type="{html.escape(presentation.get("option_type", "default"), quote=True)}" '
            f'data-button-style="{html.escape(presentation.get("button_style", "outline"), quote=True)}" '
            f'data-checked-label="{html.escape(presentation.get("checked_label", ""), quote=True)}" '
            f'data-unchecked-label="{html.escape(presentation.get("unchecked_label", ""), quote=True)}" '
            f'data-min-rows="{int(presentation.get("min_rows", 2))}" '
            f'data-max-rows="{int(presentation.get("max_rows", 6))}" '
            f'data-show-count="{str(bool(presentation.get("show_count", False))).lower()}" '
            f'data-prefix="{html.escape(presentation.get("prefix", ""), quote=True)}" '
            f'data-suffix="{html.escape(presentation.get("suffix", ""), quote=True)}" '
            f'data-number-controls="{str(bool(presentation.get("number_controls", True))).lower()}" '
            f'data-show-input="{str(bool(presentation.get("show_input", False))).lower()}" '
            f'data-tooltip="{html.escape(presentation.get("tooltip", "auto"), quote=True)}" '
            f'data-marks="{html.escape(json.dumps(presentation.get("marks", []), ensure_ascii=False), quote=True)}" '
            f'data-suggestions="{html.escape(json.dumps(suggestions, ensure_ascii=False), quote=True)}" '
            f'data-cascader-levels="{html.escape(json.dumps(levels, ensure_ascii=False), quote=True)}" '
            f'data-cascader-view="{html.escape(view_id or "", quote=True)}"'
        )
        css_class = html.escape(presentation.get("css_class", ""), quote=True)
        native = native.replace(
            "data-control-input",
            f'data-control-native="{"hidden" if hidden_native else "visible"}" data-control-input',
            1,
        )
        return (
            f'<div class="dv-control {css_class}" {attrs}>{native}'
            '<div data-control-mount></div>'
            '<small class="dv-control__error" data-control-error role="alert" hidden></small>'
            '</div>'
        )

    def write_report(
        self,
        dashboard: LoadedDashboard,
        result: RunResult,
        output: Path,
        *,
        control_state: dict[str, dict[str, Any]] | None = None,
        applied_revisions: dict[str, dict[str, dict[str, int]]] | None = None,
        applied_control_state: (
            dict[str, dict[str, dict[str, dict[str, Any]]]] | None
        ) = None,
        control_writer_provenance: dict[str, dict[str, Any]] | None = None,
        applied_writer_provenance: (
            dict[str, dict[str, dict[str, dict[str, Any]]]] | None
        ) = None,
        derived_outputs: dict[str, Any] | None = None,
        snapshot_interactions: set[str] | None = None,
    ) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        dependency_contract = dashboard.dependency_contract
        manifest = output.with_suffix(output.suffix + ".manifest.json")
        previous_manifest = manifest.read_bytes() if manifest.is_file() else None
        manifest_published = False
        resolved_control_state = resolve_control_states(
            dashboard.definition,
            control_state,
            phase="canvas-hydration",
        )
        runtime_assets = self._runtime_asset_usage(
            dashboard,
            {**result.outputs, **(derived_outputs or {})},
            dependency_contract=dependency_contract,
            live=None,
            asset_mode="inline",
            snapshot_interactions=snapshot_interactions or set(),
        )
        try:
            rendered = self.render(
                dashboard,
                result,
                asset_mode="inline",
                control_state=resolved_control_state,
                applied_revisions=applied_revisions,
                applied_control_state=applied_control_state,
                control_writer_provenance=control_writer_provenance,
                applied_writer_provenance=applied_writer_provenance,
                derived_outputs=derived_outputs,
                snapshot_interactions=snapshot_interactions,
                dependency_contract=dependency_contract,
            )
            manifest_content = json.dumps(
                {
                    "schema": "dataviz/report-manifest/v2",
                    "runtime": RUNTIME_PROTOCOL_SCHEMA,
                    "dashboard": dashboard.definition.id,
                    "dependency_contract": dependency_contract.as_dict(),
                    "layout_contract": dashboard.layout_contract.as_dict(),
                    "query_run": _portable_run_result(result, self.workspace.root),
                    "state": {
                        "query_parameters": result.query_parameters,
                        "control_state": resolved_control_state,
                        "consumer_revisions": normalize_consumer_revisions(
                            dashboard,
                            resolved_control_state,
                            applied_revisions,
                            applied_control_state,
                            applied_writer_provenance,
                        ),
                    },
                    "derived_outputs": {
                        reference: descriptor.model_dump(mode="json", by_alias=True)
                        for reference, descriptor in (derived_outputs or {}).items()
                    },
                    "snapshot_interactions": sorted(snapshot_interactions or set()),
                    "assets": {},
                    "network_dependencies": runtime_assets["network_dependencies"],
                    "portable_without_network": not runtime_assets[
                        "network_dependencies"
                    ],
                    # Arbitrary Canvas/Presentation code can make its own
                    # requests and is intentionally outside static analysis.
                    "portability_scope": "declared-runtime-and-view-assets",
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
            atomic_write_text(manifest, manifest_content)
            manifest_published = True
            # Publish HTML last: once it is visible, its manifest and bundled
            # runtime assets are already complete.
            atomic_write_text(output, rendered)
        except BaseException:
            if manifest_published:
                if previous_manifest is None:
                    manifest.unlink(missing_ok=True)
                else:
                    atomic_write_bytes(manifest, previous_manifest)
            raise
        return output

    def _default_body(
        self,
        dashboard: LoadedDashboard,
        definition: DashboardDefinition,
        views: dict[str, str],
        parameters: dict[str, Any],
        control_state: dict[str, dict[str, Any]],
        binding_fields: set[str],
    ) -> str:
        assumptions = "".join(
            f'<li data-dv-content-field="assumptions[{index}]">{html.escape(value)}</li>'
            if f"assumptions[{index}]" in binding_fields
            else f"<li>{html.escape(value)}</li>"
            for index, value in enumerate(definition.assumptions)
        )
        presentation_views = dashboard.presentation.views if dashboard.presentation else {}
        layout_contract = dashboard.layout_contract
        layout_sections = {
            section.section_id: section for section in layout_contract.sections
        }
        all_view_ids = list(dashboard.views)
        declarative_views = {item.id: item for item in definition.views}
        run_state = SimpleNamespace(control_state=control_state)

        def view_item(view_id: str, section_id: str) -> str:
            visual = presentation_views.get(view_id)
            placement = layout_contract.placement(section_id, view_id)
            style = f"--dv-span:{placement.span};" if placement else ""
            css_class = ""
            if visual:
                if visual.min_height is not None:
                    style += f"min-height:{max(1, visual.min_height)}px;"
                css_class = " ".join(
                    value
                    for value in [
                        f"dv-view--{visual.container}" if visual.container else "",
                        visual.css_class,
                    ]
                    if value
                )
            return (
                f'<div class="dv-section-view {html.escape(css_class)}" style="{style}">'
                f'{views.get(view_id, self._client_view_html(dashboard, view_id, run_state, declarative=declarative_views.get(view_id), binding_fields=binding_fields))}'
                "</div>"
            )

        sections = []
        assigned: set[str] = set()
        for section in definition.sections:
            view_ids = list(section.views)
            assigned.update(view_ids)
            section_selection = self._context_controls(dashboard, run_state, "section", section.id)
            title_field = f"sections.{section.id}.title"
            description_field = f"sections.{section.id}.description"
            title_binding = (
                f' data-dv-content-field="{html.escape(title_field, quote=True)}"'
                if title_field in binding_fields
                else ""
            )
            description_binding = description_field in binding_fields
            description = (
                f'<p data-dv-content-field="{html.escape(description_field, quote=True)}">'
                f'{html.escape(section.description)}</p>'
                if section.description or description_binding
                else ""
            )
            compiled_section = layout_sections[section.id]
            section_tokens = [
                f"--dv-section-columns:{compiled_section.columns}",
            ]
            if compiled_section.repeat_columns is not None:
                section_tokens.append(
                    f"--dv-repeat-columns:{compiled_section.repeat_columns}"
                )
            section_style = f' style="{";".join(section_tokens)}"'
            if section.repeat:
                section_body = (
                    f'<div class="dv-repeat" data-repeat-section="{html.escape(section.id)}" '
                    f'data-repeat-template="{html.escape(section.template)}">'
                    '<div class="dv-repeat-empty"><strong>Preparing grouped views</strong>'
                    '<span>The browser will build each view from the shared dataset.</span></div></div>'
                )
            else:
                section_body = "".join(
                    view_item(view_id, section.id) for view_id in view_ids
                )
            sections.append(
                f'<section class="dv-section dv-section--{html.escape(section.template)} {html.escape(section.css_class)}" data-section-id="{html.escape(section.id)}"{section_style}>'
                '<header class="dv-section__header"><div>'
                f'<p class="dv-section__eyebrow">{html.escape(section.id)}</p><h2{title_binding}>{html.escape(section.title)}</h2>{description}'
                f'</div>{section_selection}</header>'
                f'<div class="dv-state-summary dv-state-summary--section" data-state-summary-scope="section" '
                f'data-state-summary-owner="{html.escape(section.id, quote=True)}" hidden></div>'
                f'<div class="dv-section__body">'
                f'{section_body}</div></section>'
            )
        remaining = [view_id for view_id in all_view_ids if view_id not in assigned]
        if remaining:
            overview = layout_sections["overview"]
            sections.append(
                '<section class="dv-section dv-section--stack" data-section-id="overview" '
                f'style="--dv-section-columns:{overview.columns}">'
                f'<div class="dv-section__body">'
                f'{"".join(view_item(view_id, "overview") for view_id in remaining)}'
                '</div></section>'
            )
        dashboard_title_binding = (
            ' data-dv-content-field="title"' if "title" in binding_fields else ""
        )
        dashboard_subtitle_binding = (
            ' data-dv-content-field="subtitle"' if "subtitle" in binding_fields else ""
        )
        dashboard_description_binding = (
            ' data-dv-content-field="description"'
            if "description" in binding_fields
            else ""
        )
        return f"""
<div class="dv-default-shell" style="--dv-columns:{layout_contract.columns};--dv-gap:{layout_contract.gap}px">
<header class="dv-report-header dv-report-header--compact">
  <div>
    <p class="dv-eyebrow">{html.escape(definition.id.upper())}</p>
    <h1{dashboard_title_binding}>{html.escape(definition.title)}</h1>
    {f'<p class="dv-subtitle"{dashboard_subtitle_binding}>{html.escape(definition.subtitle)}</p>' if definition.subtitle or 'subtitle' in binding_fields else ''}
    {f'<p class="dv-deck"{dashboard_description_binding}>{html.escape(definition.description)}</p>' if definition.description or 'description' in binding_fields else ''}
  </div>
</header>
<div class="dv-state-summary dv-state-summary--dashboard" data-state-summary-scope="dashboard" data-state-summary-owner="{html.escape(definition.id, quote=True)}" hidden></div>
{f'<details class="dv-assumptions"><summary>口径与假设</summary><ul>{assumptions}</ul></details>' if assumptions else ''}
<div class="dv-sections">{''.join(sections)}</div>
</div>
"""

    def _plotly_script(self, asset_mode: str) -> str:
        if asset_mode == "server":
            return '<script src="/runtime/plotly.js"></script>'
        return f"<script>{get_plotlyjs()}</script>"

    def _tanstack_table_script(self, asset_mode: str) -> str:
        if asset_mode == "server":
            return '<script src="/static/tanstack-table-runtime.js"></script>'
        source = (
            PACKAGE_ROOT / "server" / "static" / "tanstack-table-runtime.js"
        ).read_text(encoding="utf-8")
        return f"<script>{source}</script>"

    def _perspective_script(self) -> str:
        version = html.escape(self.workspace.definition.runtime.perspective_version, quote=True)
        base = "https://cdn.jsdelivr.net/npm/@perspective-dev"
        return f"""
<link rel="stylesheet" href="{base}/viewer@{version}/dist/css/themes.css">
<script>
window.datavizPerspectiveReady = (async () => {{
  const perspective = (await import("{base}/client@{version}/dist/cdn/perspective.js")).default;
  await import("{base}/viewer@{version}/dist/cdn/perspective-viewer.js");
  await import("{base}/viewer-datagrid@{version}/dist/cdn/perspective-viewer-datagrid.js");
  await import("{base}/viewer-charts@{version}/dist/cdn/perspective-viewer-charts.js");
  await customElements.whenDefined("perspective-viewer");
  return {{perspective, version: {json.dumps(self.workspace.definition.runtime.perspective_version)}}};
}})();
</script>"""

    def _arrow_script(self) -> str:
        source = self.workspace.definition.runtime.arrow_js
        if source.startswith("http://") or source.startswith("https://"):
            tag = f'<script src="{html.escape(source, quote=True)}"></script>'
        else:
            path = self._workspace_runtime_asset(
                source,
                field="runtime.arrow_js",
            )
            tag = f"<script>{path.read_text(encoding='utf-8')}</script>"
        return (
            f"{tag}\n<script>window.datavizArrowReady = Promise.resolve("
            "window.arrow || window.Arrow).then(value => { if (!value?.tableFromIPC) "
            "throw new Error('Apache Arrow JavaScript could not be loaded'); return value; });</script>"
        )

    def _runtime_script(self) -> str:
        return (PACKAGE_ROOT / "server" / "static" / "canvas-runtime.js").read_text(
            encoding="utf-8"
        )
