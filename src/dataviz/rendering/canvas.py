from __future__ import annotations

import base64
import gzip
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

from jinja2 import Environment, StrictUndefined
from markupsafe import Markup

from dataviz.artifacts import ArtifactStore
from dataviz.components import component_runtime_assets
from dataviz.errors import ExecutionFailure
from dataviz.execution.plan import reachable_output_references
from dataviz.execution.results import RunResult
from dataviz.templates import COMPONENT_REGISTRY_VERSION, RUNTIME_PROTOCOL_SCHEMA
from dataviz.workspace.selections import compile_selection_contract
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace
from dataviz.workspace.selector_templates import resolve_selector_presentation


PACKAGE_ROOT = Path(__file__).resolve().parent.parent


class CanvasRenderer:
    def __init__(self, workspace: LoadedWorkspace):
        self.workspace = workspace

    def render(
        self,
        dashboard: LoadedDashboard,
        result: RunResult,
        *,
        chart_mode: str = "interactive",
        image_format: str = "svg",
        asset_mode: str = "server",
        title: str | None = None,
        live: dict[str, str] | None = None,
        session_id: str | None = None,
    ) -> str:
        if chart_mode not in {"interactive", "static"}:
            raise ExecutionFailure("chart_mode must be interactive or static")
        if chart_mode == "static" and dashboard.definition.views:
            raise ExecutionFailure(
                "Static rendering is not implemented for declarative Views; use --chart-mode interactive"
            )
        store = ArtifactStore(self.workspace.root, result.run_id)
        declarative_views = {item.id: item for item in dashboard.definition.views}
        view_html = {
            view_id: self._client_view_html(dashboard, view_id, result)
            for view_id in dashboard.views
        }

        def view(view_id: str) -> str:
            return view_html.get(view_id, self._client_view_html(dashboard, view_id, result))

        canvas = dashboard.definition.canvas
        if canvas.template:
            template_text = (dashboard.root / canvas.template).read_text(encoding="utf-8")
            environment = Environment(autoescape=True, undefined=StrictUndefined)
            template = environment.from_string(template_text)
            content_definition = dashboard.definition.model_copy(
                update={"title": dashboard.title}
            )
            body = template.render(
                workspace=self.workspace.definition,
                dashboard=content_definition,
                parameters=result.parameters,
                selections=result.selections,
                run=result,
                view=lambda value: Markup(view(value)),
                section_selections=lambda value: Markup(
                    self._context_selection_controls(dashboard, result, "section", value)
                ),
                views=view_html,
            )
        else:
            body = self._default_body(dashboard, view_html, result.parameters, result.selections)

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
        style_paths = ([canvas.style] if canvas.style else []) + list(canvas.styles)
        script_paths = ([canvas.script] if canvas.script else []) + list(canvas.scripts)
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
        chart_views = [
            view
            for view in declarative_views.values()
            if view.template in {"line", "bar", "stacked-bar", "pie", "scatter", "heatmap", "radar"}
        ]
        needs_plotly = (
            "plotly-json" in self._formats(result)
            or "plotly" in canvas.client_libraries
            or any(view.engine == "plotly" for view in chart_views)
        )
        needs_echarts = (
            "echarts-json" in self._formats(result)
            or "echarts" in canvas.client_libraries
            or any(view.engine == "echarts" for view in chart_views)
        )
        needs_perspective = (
            "perspective" in canvas.client_libraries
            or any(view.template == "perspective" for view in declarative_views.values())
        )
        transport_runtime = self.workspace.definition.runtime
        needs_arrow = (
            chart_mode == "interactive"
            and transport_runtime.browser_table_transport != "json"
            and (
                live is not None
                or any(
                    artifact.kind == "table"
                    and (
                        transport_runtime.browser_table_transport == "arrow"
                        or int(artifact.metadata.get("row_count", 0))
                        >= transport_runtime.arrow_min_rows
                    )
                    for artifact in result.outputs.values()
                )
            )
        )
        plotly_script = self._plotly_script(asset_mode) if needs_plotly and chart_mode == "interactive" else ""
        echarts_script = self._echarts_script(asset_mode) if needs_echarts else ""
        arrow_script = self._arrow_script() if needs_arrow else ""
        perspective_script = self._perspective_script() if needs_perspective and chart_mode == "interactive" else ""
        runtime = self._runtime_script()
        worker_source = self._browser_transform_worker_source(dashboard)
        browser_transform_script = self._browser_transform_script(dashboard)
        declarative_script = self._declarative_script(dashboard)
        view_specs, repeat_specs = self._declarative_manifest(dashboard)
        document_title = title or dashboard.title
        portable = (
            asset_mode in {"inline", "server"}
            and chart_mode == "interactive"
            and (bool(result.outputs) or live is not None)
        )
        portable_bundle = (
            self._portable_bundle(
                dashboard,
                result,
                store,
                allow_missing=live is not None,
                asset_mode=asset_mode,
                session_id=session_id,
            )
            if portable
            else None
        )
        portable_controls = self._portable_controls(dashboard, result) if portable and asset_mode == "inline" else ""
        meta = {
            "protocol": {
                "schema": RUNTIME_PROTOCOL_SCHEMA,
                "component_registry_version": COMPONENT_REGISTRY_VERSION,
            },
            "run_id": result.run_id,
            "status": result.status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parameters": result.parameters,
            "selections": result.selections,
            "portable": portable_bundle,
            "live": live,
            "view_specs": view_specs,
            "repeat_specs": repeat_specs,
            "runtime_versions": {
                "perspective": self.workspace.definition.runtime.perspective_version,
            },
        }
        meta_json = json.dumps(meta, ensure_ascii=False, default=str).replace("</", "<\\/")
        return f"""<!doctype html>
<html lang="{html.escape(self.workspace.definition.context.language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(document_title)}</title>
  <style>{functional_style}\n{component_style}\n{base_style}\n{custom_style}</style>
  {plotly_script}
  {echarts_script}
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
  <script>{browser_transform_script}</script>
  <script>{declarative_script}</script>
  <script>{custom_script}</script>
  <script>if (window.dataviz.portable) {{ window.dataviz.applySelections().catch(error => console.error('[dataviz:init]', error)); window.datavizRuntime.hydrateOutputTransports(); }} if (window.dataviz.live) window.dataviz.connectLive?.();</script>
</body>
</html>"""

    def _client_view_html(
        self, dashboard: LoadedDashboard, view_id: str, result: RunResult
    ) -> str:
        declarative = dashboard.views.get(view_id)
        title = (declarative.title or declarative.id) if declarative else view_id
        status = declarative.template if declarative else "browser"
        controls = self._context_selection_controls(dashboard, result, "view", view_id)
        return (
            f'<article class="dv-view dv-view--client" data-view-id="{html.escape(view_id)}" '
            'data-view-status="waiting">'
            f'<header class="dv-view-header"><span>{html.escape(title)}</span>'
            f'<div class="dv-view-actions">{controls}<small data-view-status-label>{html.escape(status)}</small></div></header>'
            '<div class="dv-view-body"><div class="dv-view-placeholder">Waiting for dataset</div></div>'
            '</article>'
        )

    def _context_selection_controls(
        self,
        dashboard: LoadedDashboard,
        result: RunResult,
        origin: str,
        owner_id: str,
    ) -> str:
        contract = compile_selection_contract(dashboard.definition)
        controls = {}
        for selections in contract.values():
            for item in selections:
                if item.origin == origin and item.owner_id == owner_id:
                    controls.setdefault(item.key, item)
        if not controls:
            return ""
        selector_view_id = owner_id if origin == "view" else None
        if origin == "section":
            section = next((item for item in dashboard.definition.sections if item.id == owner_id), None)
            if section and section.views:
                selector_view_id = section.views[0]
        fields = []
        for key, item in controls.items():
            definition = item.definition
            value = result.selections.get(key, definition.default)
            fields.append(
                f'<label class="dv-context-selection" data-selection-key="{html.escape(key)}" '
                f'data-selection-type="{html.escape(definition.type)}" '
                f'data-selection-path="{str(bool(definition.path_fields)).lower()}">'
                f'<span>{html.escape(definition.label or definition.id)}</span>'
                f'{self._portable_field(key, definition, value, self._selector_presentation(dashboard, key, definition), selector_view_id)}</label>'
            )
        scope = "Section" if origin == "section" else "View"
        return (
            f'<details class="dv-context-selections" data-selection-origin="{html.escape(origin)}" '
            'data-overlay-floating="true" data-overlay-width="440">'
            f'<summary><span class="dv-context-selections__mark">{scope[0]}</span>'
            f'<strong>{scope} selection</strong><small>{len(fields)}</small><i>⌄</i></summary>'
            f'<div class="dv-context-selections__panel">{"".join(fields)}</div></details>'
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
        self, dashboard: LoadedDashboard
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        view_specs = [item.model_dump(mode="json") for item in dashboard.definition.views]
        repeat_specs: list[dict[str, Any]] = []
        for section in dashboard.definition.sections:
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

    def _declarative_script(self, dashboard: LoadedDashboard) -> str:
        if not dashboard.definition.views:
            return ""
        return (PACKAGE_ROOT / "server" / "static" / "declarative-runtime.js").read_text(
            encoding="utf-8"
        )
    def _browser_transform_script(self, dashboard: LoadedDashboard) -> str:
        registrations = []
        _, browser_ids = self._reachable_outputs(dashboard)
        for transform_id in browser_ids:
            transform_path, definition = dashboard.browser_transforms[transform_id]
            code_path = (transform_path.parent / definition.code).resolve()
            code = json.dumps(code_path.read_text(encoding="utf-8"), ensure_ascii=False).replace("</", "<\\/")
            spec = json.dumps(
                definition.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                default=str,
            ).replace("</", "<\\/")
            entrypoint = json.dumps(definition.entrypoint)
            registrations.append(
                f"window.datavizRuntime.registerTransform({spec}, "
                f"{{code:{code},entrypoint:{entrypoint}}});"
            )
        return "\n".join(registrations)

    def _browser_transform_worker_source(self, dashboard: LoadedDashboard) -> str:
        _, browser_ids = self._reachable_outputs(dashboard)
        if not browser_ids:
            return ""
        source = (
            PACKAGE_ROOT / "server" / "static" / "browser-transform-worker.js"
        ).read_text(encoding="utf-8")
        encoded = json.dumps(source, ensure_ascii=False).replace("</", "<\\/")
        return f"<script>window.datavizBrowserTransformWorkerSource={encoded};</script>"

    def _reachable_outputs(self, dashboard: LoadedDashboard) -> tuple[set[str], list[str]]:
        """Return the minimal server payload and Browser Transform dependency order."""
        return reachable_output_references(dashboard)

    def _portable_bundle(
        self,
        dashboard: LoadedDashboard,
        result: RunResult,
        store: ArtifactStore,
        *,
        allow_missing: bool = False,
        asset_mode: str = "inline",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        output_transports: dict[str, Any] = {}
        output_kinds: dict[str, str] = {}
        reachable, _ = self._reachable_outputs(dashboard)
        runtime = self.workspace.definition.runtime
        row_count = 0
        payload_bytes = 0
        pending_outputs: list[str] = []
        for reference in sorted(reachable):
            artifact = result.outputs.get(reference)
            if artifact is None:
                if allow_missing:
                    pending_outputs.append(reference)
                    continue
                raise ExecutionFailure(f"Report input is unavailable: {reference}")
            if artifact.kind == "table":
                table_rows = int(artifact.metadata.get("row_count", 0))
                row_count += table_rows
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
                    "hint": "Aggregate with a Server Transform or raise runtime.max_embedded_rows explicitly.",
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
        contract = compile_selection_contract(dashboard.definition)
        return {
            "outputs": outputs,
            "output_transports": output_transports,
            "output_kinds": output_kinds,
            "output_errors": {},
            "pending_outputs": pending_outputs,
            "view_inputs": {
                view.id: view.input_refs
                for view in dashboard.definition.views
            },
            "selection_contract": {
                view_id: [item.as_dict() for item in selections]
                for view_id, selections in contract.items()
            },
        }

    def _portable_controls(self, dashboard: LoadedDashboard, result: RunResult) -> str:
        contract = compile_selection_contract(dashboard.definition)
        controls: dict[str, dict[str, Any]] = {}
        for view_id, selections in contract.items():
            for item in selections:
                control = controls.setdefault(
                    item.key,
                    {"selection": item, "views": []},
                )
                control["views"].append(view_id)

        rendered: dict[str, list[str]] = {"dashboard": []}
        for key, control in controls.items():
            item = control["selection"]
            if item.origin != "dashboard":
                continue
            definition = item.definition
            value = result.selections.get(key, definition.default)
            scope = "All views"
            field = self._portable_field(
                key, definition, value, self._selector_presentation(dashboard, key, definition)
            )
            rendered[item.origin].append(
                f'<div class="dv-report-selection" data-selection-key="{html.escape(key)}" '
                f'data-selection-type="{html.escape(definition.type)}">'
                f'<div class="dv-report-selection__scope"><span>{html.escape(scope)}</span>'
                f'<small>{len(control["views"])} view{"s" if len(control["views"]) != 1 else ""}</small></div>'
                f'<strong>{html.escape(definition.label or definition.id)}</strong>{field}</div>'
            )
        if not any(rendered.values()):
            return ""
        query_items = "".join(
            f'<div class="dv-query-value"><span>{html.escape(item.label or item.id)}</span>'
            f'<strong>{html.escape(json.dumps(result.parameters.get(item.id), ensure_ascii=False, default=str))}</strong></div>'
            for item in dashboard.definition.query_parameters
        ) or '<div class="dv-query-value"><span>Query parameters</span><strong>None</strong></div>'
        groups = []
        group_titles = {"dashboard": ("02", "Dashboard selections", "All views")}
        for origin, values in rendered.items():
            number, title, description = group_titles[origin]
            groups.append(
                f'<details class="dv-runtime-control" data-runtime-popover data-selection-origin="{origin}" '
                'data-overlay-floating="true" data-overlay-width="560">'
                f'<summary><span>{number}</span><div><strong>Selections</strong><small>{len(values)} selector{"" if len(values) == 1 else "s"}</small></div><i>⌄</i></summary>'
                f'<div class="dv-runtime-popover"><header><span>{number}</span><div><strong>{title}</strong><small>Browser-only · redraws embedded views</small></div></header>'
                f'<div class="dv-report-selection-group__fields">{"".join(values) if values else "<em>None</em>"}</div></div></details>'
            )
        return (
            '<header class="dv-runtime-header" aria-label="Report controls">'
            '<div class="dv-runtime-brand"><span>PORTABLE ANALYSIS</span><strong>Dataset fixed. Views live.</strong></div>'
            '<nav class="dv-runtime-actions" aria-label="Dataset controls">'
            '<details class="dv-runtime-control" data-runtime-popover data-overlay-floating="true" data-overlay-width="440">'
            '<summary><span>01</span><div><strong>Parameters</strong><small>Fixed snapshot</small></div><i>⌄</i></summary>'
            f'<div class="dv-runtime-popover dv-runtime-popover--query"><header><span>01</span><div><strong>Query snapshot</strong><small>Values embedded in this HTML</small></div></header><div class="dv-runtime-query-values">{query_items}</div></div></details>'
            f'{"".join(groups)}</nav></header>'
        )

    def _selector_presentation(self, dashboard: LoadedDashboard, key: str, definition) -> dict[str, Any]:
        selector = dashboard.presentation.selectors.get(key) if dashboard.presentation else None
        return resolve_selector_presentation(definition, selector)

    def _portable_field(
        self,
        key: str,
        definition,
        value: Any,
        selector: dict[str, Any] | None = None,
        view_id: str | None = None,
    ) -> str:
        escaped_key = html.escape(key)
        if definition.type in {"single_select", "multi_select", "boolean"}:
            selector = selector or {}
            choice_count = len(definition.choices)
            default_template = (
                "segmented"
                if definition.type == "boolean"
                or (definition.type == "single_select" and 0 < choice_count <= 4)
                else "checkbox-group"
                if definition.type == "multi_select" and 0 < choice_count <= 8
                else "select"
            )
            template = selector.get("template", default_template)
            css_class = html.escape(selector.get("css_class", ""))
            choice_value = lambda item: str(item).lower() if isinstance(item, bool) else str(item)
            selected = {choice_value(item) for item in (value if isinstance(value, list) else [value])}
            multiple = " multiple" if definition.type == "multi_select" else ""
            choices = list(definition.choices)
            if definition.type == "boolean" and not choices:
                choices = [
                    SimpleNamespace(label="Yes", value=True, group=None, description="", keywords=[]),
                    SimpleNamespace(label="No", value=False, group=None, description="", keywords=[]),
                ]
            options = ""
            if definition.type != "multi_select":
                empty_selected = value is None or value == "" or value == []
                options += f'<option value="" data-empty-option="true" hidden{" selected" if empty_selected else ""}></option>'
            for choice in choices:
                serialized_value = choice_value(choice.value)
                metadata = ""
                if getattr(choice, "group", None):
                    metadata += f' data-group="{html.escape(choice.group, quote=True)}"'
                if getattr(choice, "description", ""):
                    metadata += f' data-description="{html.escape(choice.description, quote=True)}"'
                if getattr(choice, "keywords", []):
                    metadata += f' data-keywords="{html.escape(" ".join(choice.keywords), quote=True)}"'
                options += (
                    f'<option value="{html.escape(serialized_value, quote=True)}"{metadata}'
                    f'{" selected" if serialized_value in selected else ""}>{html.escape(choice.label)}</option>'
                )
            select = f'<select aria-label="{html.escape(definition.label or definition.id)}" data-selection-input="{escaped_key}"{multiple}>{options}</select>'
            attrs = (
                f'data-selector-template="{html.escape(template)}" '
                f'data-requested-template="{html.escape(selector.get("requested_template", selector.get("template", "auto")))}" '
                f'data-auto-reason="{html.escape(selector.get("auto_reason", ""))}" '
                'data-empty-means-all="true" '
                f'data-required="{str(bool(definition.required)).lower()}" '
                f'data-variant="{html.escape(selector.get("variant", "default"))}" '
                f'data-show-unavailable="{str(bool(selector.get("show_unavailable", False))).lower()}" '
                f'data-search-mode="{html.escape(selector.get("search", "auto"))}" '
                f'data-virtual-mode="{html.escape(selector.get("virtual", "auto"))}" '
                f'data-search-threshold="{int(selector.get("search_threshold", 9))}" '
                f'data-virtual-threshold="{int(selector.get("virtual_threshold", 200))}" '
                f'data-max-visible-tags="{int(selector.get("max_visible_tags", 2))}" '
                f'data-max-selected="{selector.get("max_selected") or ""}" '
                f'data-hide-selected="{str(bool(selector.get("hide_selected", False))).lower()}" '
                f'data-search-placeholder="{html.escape(selector.get("search_placeholder", "Search options…"))}" '
                f'data-empty-text="{html.escape(selector.get("empty_text", "No matching options"))}"'
                f' data-placeholder="{html.escape(selector.get("placeholder", "Choose…"))}"'
                f' data-all-label="{html.escape(selector.get("all_label", "All"))}"'
                f' data-select-all-label="{html.escape(selector.get("select_all_label", "Select all"))}"'
                f' data-invert-label="{html.escape(selector.get("invert_label", "Invert"))}"'
                f' data-clear-label="{html.escape(selector.get("clear_label", "Clear"))}"'
                f' data-item-height="{int(selector.get("item_height", 38))}"'
                f' data-viewport-height="{int(selector.get("viewport_height", 304))}"'
                f' data-overscan="{int(selector.get("overscan", 5))}"'
            )
            if template in {"cascader", "tree-select"}:
                levels = [
                    {"field": field, "label": (
                        selector.get("level_labels", [])[index]
                        if index < len(selector.get("level_labels", []))
                        else field
                    )}
                    for index, field in enumerate(definition.path_fields)
                ]
                attrs += (
                    f' data-cascader-levels="{html.escape(json.dumps(levels, ensure_ascii=False), quote=True)}"'
                    f' data-cascader-view="{html.escape(view_id or "")}"'
                    f' data-placeholder="{html.escape(selector.get("placeholder", "Choose…"))}"'
                    f' data-path-separator="{html.escape(selector.get("path_separator", " / "))}"'
                    f' data-default-expand-depth="{int(selector.get("default_expand_depth", 0))}"'
                    f' data-hierarchy-selection="{html.escape(selector.get("hierarchy_selection", "leaf"))}"'
                    f' data-checked-strategy="{html.escape(selector.get("checked_strategy", "child"))}"'
                )
            return f'<div class="dv-selector {css_class}" {attrs}>{select}<div data-selector-mount></div></div>'
        input_type = "number" if definition.type == "number" else "date" if definition.type == "date" else "text"
        display = ",".join(map(str, value)) if isinstance(value, list) else "" if value is None else str(value)
        if definition.type == "date_range":
            selector = selector or {"template": "date-range"}
            css_class = html.escape(selector.get("css_class", ""))
            attrs = (
                'data-selector-template="date-range" '
                f'data-start-label="{html.escape(selector.get("start_label", "Start"))}" '
                f'data-end-label="{html.escape(selector.get("end_label", "End"))}" '
                f'data-clear-label="{html.escape(selector.get("clear_label", "Clear"))}" '
                f'data-min="{html.escape(selector.get("min") or "")}" '
                f'data-max="{html.escape(selector.get("max") or "")}" '
                f'data-allow-open-range="{str(bool(selector.get("allow_open_range", False))).lower()}" '
                f'data-presets="{html.escape(json.dumps(selector.get("presets", []), ensure_ascii=False), quote=True)}"'
            )
            native = (
                f'<input type="text" value="{html.escape(display)}" aria-label="{html.escape(definition.label or definition.id)}" '
                f'data-selection-input="{escaped_key}" data-selector-native>'
            )
            return f'<div class="dv-selector {css_class}" {attrs}>{native}<div data-selector-mount></div></div>'
        placeholder = ""
        return f'<input type="{input_type}" value="{html.escape(display)}" data-selection-input="{escaped_key}"{placeholder}>'

    def write_report(
        self,
        dashboard: LoadedDashboard,
        result: RunResult,
        output: Path,
        *,
        chart_mode: str = "interactive",
        image_format: str = "svg",
    ) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            self.render(
                dashboard,
                result,
                chart_mode=chart_mode,
                image_format=image_format,
                asset_mode="inline",
            ),
            encoding="utf-8",
        )
        manifest = output.with_suffix(output.suffix + ".manifest.json")
        manifest.write_text(result.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
        return output

    def _default_body(
        self,
        dashboard: LoadedDashboard,
        views: dict[str, str],
        parameters: dict[str, Any],
        selections: dict[str, Any],
    ) -> str:
        definition = dashboard.definition
        assumptions = "".join(f"<li>{html.escape(value)}</li>" for value in definition.assumptions)
        presentation_views = dashboard.presentation.views if dashboard.presentation else {}
        all_view_ids = list(dashboard.views)
        run_state = SimpleNamespace(selections=selections)

        def view_item(view_id: str) -> str:
            layout = presentation_views.get(view_id)
            style = ""
            css_class = ""
            if layout:
                if layout.span is not None:
                    style = f"--dv-span:{max(1, min(definition.layout.columns, layout.span))};"
                if layout.min_height is not None:
                    style += f"min-height:{max(1, layout.min_height)}px;"
                css_class = " ".join(
                    value
                    for value in [
                        f"dv-view--{layout.container}" if layout.container else "",
                        layout.css_class,
                    ]
                    if value
                )
            return (
                f'<div class="dv-section-view {html.escape(css_class)}" style="{style}">'
                f'{views.get(view_id, self._client_view_html(dashboard, view_id, run_state))}'
                "</div>"
            )

        sections = []
        assigned: set[str] = set()
        for section in definition.sections:
            view_ids = list(section.views)
            assigned.update(view_ids)
            section_selection = self._context_selection_controls(dashboard, run_state, "section", section.id)
            description = f'<p>{html.escape(section.description)}</p>' if section.description else ""
            if section.repeat:
                section_style = f' style="--dv-repeat-columns:{max(1, section.columns or 1)}"'
            else:
                section_style = (
                    f' style="--dv-columns:{max(1, section.columns)}"' if section.columns else ""
                )
            if section.repeat:
                section_body = (
                    f'<div class="dv-repeat" data-repeat-section="{html.escape(section.id)}" '
                    f'data-repeat-template="{html.escape(section.template)}">'
                    '<div class="dv-repeat-empty"><strong>Preparing grouped views</strong>'
                    '<span>The browser will build each view from the shared dataset.</span></div></div>'
                )
            else:
                section_body = "".join(view_item(view_id) for view_id in view_ids)
            sections.append(
                f'<section class="dv-section dv-section--{html.escape(section.template)} {html.escape(section.css_class)}" data-section-id="{html.escape(section.id)}"{section_style}>'
                '<header class="dv-section__header"><div>'
                f'<p class="dv-section__eyebrow">{html.escape(section.id)}</p><h2>{html.escape(section.title)}</h2>{description}'
                f'</div>{section_selection}</header><div class="dv-section__body">'
                f'{section_body}</div></section>'
            )
        remaining = [view_id for view_id in all_view_ids if view_id not in assigned]
        if remaining:
            sections.append(
                '<section class="dv-section dv-section--stack" data-section-id="overview">'
                f'<div class="dv-section__body">{"".join(view_item(view_id) for view_id in remaining)}</div></section>'
            )
        return f"""
<div class="dv-default-shell" style="--dv-columns:{definition.layout.columns};--dv-gap:{definition.layout.gap}px">
<header class="dv-report-header dv-report-header--compact">
  <div>
    <p class="dv-eyebrow">{html.escape(definition.id.upper())}</p>
    <h1>{html.escape(dashboard.title)}</h1>
    {f'<p class="dv-subtitle">{html.escape(definition.subtitle)}</p>' if definition.subtitle else ''}
    {f'<p class="dv-deck">{html.escape(definition.description)}</p>' if definition.description else ''}
  </div>
</header>
{f'<details class="dv-assumptions"><summary>口径与假设</summary><ul>{assumptions}</ul></details>' if assumptions else ''}
<div class="dv-sections">{''.join(sections)}</div>
</div>
"""

    def _formats(self, result: RunResult) -> set[str]:
        return {artifact.format for artifact in result.outputs.values()}

    def _plotly_script(self, asset_mode: str) -> str:
        if asset_mode == "server":
            return '<script src="/runtime/plotly.js"></script>'
        from plotly.offline.offline import get_plotlyjs

        return f"<script>{get_plotlyjs()}</script>"

    def _echarts_script(self, asset_mode: str) -> str:
        source = self.workspace.definition.runtime.echarts_js
        if source.startswith("http://") or source.startswith("https://"):
            return f'<script src="{html.escape(source)}"></script>'
        path = (self.workspace.root / source).resolve()
        if not path.exists():
            raise ExecutionFailure("Configured ECharts JavaScript does not exist", file=path)
        return f"<script>{path.read_text(encoding='utf-8')}</script>"

    def _perspective_script(self) -> str:
        version = html.escape(self.workspace.definition.runtime.perspective_version, quote=True)
        base = f"https://cdn.jsdelivr.net/npm/@perspective-dev"
        return f"""
<link rel="stylesheet" href="{base}/viewer@{version}/dist/css/themes.css">
<script>
window.datavizPerspectiveReady = (async () => {{
  const perspective = (await import("{base}/client@{version}/dist/cdn/perspective.js")).default;
  await import("{base}/viewer@{version}/dist/cdn/perspective-viewer.js");
  await import("{base}/viewer-datagrid@{version}/dist/cdn/perspective-viewer-datagrid.js");
  await import("{base}/viewer-charts@{version}/dist/cdn/perspective-viewer-charts.js");
  await customElements.whenDefined("perspective-viewer");
  return {{perspective, worker: await perspective.worker(), version: {json.dumps(self.workspace.definition.runtime.perspective_version)}}};
}})();
</script>"""

    def _arrow_script(self) -> str:
        source = self.workspace.definition.runtime.arrow_js
        if source.startswith("http://") or source.startswith("https://"):
            tag = f'<script src="{html.escape(source, quote=True)}"></script>'
        else:
            path = (self.workspace.root / source).resolve()
            if not path.exists():
                raise ExecutionFailure("Configured Apache Arrow JavaScript does not exist", file=path)
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
