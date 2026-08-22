from __future__ import annotations

import base64
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import markdown as markdown_lib
from jinja2 import Environment, StrictUndefined
from markupsafe import Markup

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.errors import ExecutionFailure
from dataviz.execution.results import RunResult
from dataviz.workspace.selections import compile_selection_contract, view_definition
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


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
    ) -> str:
        store = ArtifactStore(self.workspace.root, result.run_id)
        declarative_views = {item.id: item for item in dashboard.definition.views}
        client_sources = self._client_sources(dashboard)
        widget_html = {
            widget_id: self._client_view_html(dashboard, widget_id, result)
            for widget_id in dashboard.widgets
        }
        widget_html.update({
            widget_id: self._widget_html(widget_id, artifacts, store, chart_mode, image_format)
            for widget_id, artifacts in result.outputs.items()
        })

        def widget(widget_id: str) -> str:
            return widget_html.get(widget_id, self._client_view_html(dashboard, widget_id, result))

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
                widget=lambda value: Markup(widget(value)),
                section_selections=lambda value: Markup(
                    self._context_selection_controls(dashboard, result, "section", value)
                ),
                # Deprecated template aliases.
                filters=result.selections,
                section_filters=lambda value: Markup(
                    self._context_selection_controls(dashboard, result, "section", value)
                ),
                widgets=widget_html,
            )
        else:
            body = self._default_body(dashboard, widget_html, result.parameters, result.selections)

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
            if view.template in {"line", "bar", "stacked-bar", "pie", "scatter", "heatmap"}
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
            or any(
                widget.output.type == "perspective"
                for _, widget in dashboard.widgets.values()
            )
            or any(
                artifact.kind == "table"
                for artifacts in result.outputs.values()
                for artifact in artifacts
            )
        )
        plotly_script = self._plotly_script(asset_mode) if needs_plotly and chart_mode == "interactive" else ""
        echarts_script = self._echarts_script(asset_mode) if needs_echarts else ""
        perspective_script = self._perspective_script() if needs_perspective and chart_mode == "interactive" else ""
        runtime = self._runtime_script(result)
        declarative_script = self._declarative_script(dashboard)
        document_title = title or dashboard.title
        portable = (
            asset_mode in {"inline", "server"}
            and chart_mode == "interactive"
            and bool(client_sources)
        )
        portable_bundle = self._portable_bundle(dashboard, result, store) if portable else None
        portable_controls = self._portable_controls(dashboard, result) if portable and asset_mode == "inline" else ""
        meta = {
            "run_id": result.run_id,
            "status": result.status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parameters": result.parameters,
            "selections": result.selections,
            "portable": portable_bundle,
        }
        meta_json = json.dumps(meta, ensure_ascii=False, default=str).replace("</", "<\\/")
        return f"""<!doctype html>
<html lang="{html.escape(self.workspace.definition.context.language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(document_title)}</title>
  <style>{base_style}\n{custom_style}</style>
  {plotly_script}
  {echarts_script}
  {perspective_script}
</head>
<body>
  {portable_controls}
  <main class="dv-canvas dv-layout--{html.escape(dashboard.definition.layout.template)} dv-theme--{html.escape(dashboard.definition.theme.preset)} dv-density--{html.escape(dashboard.definition.theme.density)}" data-dashboard="{html.escape(dashboard.definition.id)}" style="{self._theme_style(dashboard)}">
    {body}
  </main>
  <script>window.dataviz = {meta_json};</script>
  <script>{runtime}</script>
  <script>{declarative_script}</script>
  <script>{custom_script}</script>
  <script>if (window.dataviz.portable) window.dataviz.applySelections();</script>
</body>
</html>"""

    def _client_view_html(
        self, dashboard: LoadedDashboard, widget_id: str, result: RunResult
    ) -> str:
        loaded = dashboard.widgets.get(widget_id)
        title = loaded[1].title if loaded else widget_id
        declarative = next((item for item in dashboard.definition.views if item.id == widget_id), None)
        status = declarative.template if declarative else "browser"
        controls = self._context_selection_controls(dashboard, result, "view", widget_id)
        return (
            f'<article class="dv-widget dv-widget--client" data-widget-id="{html.escape(widget_id)}" '
            'data-view-status="waiting">'
            f'<header class="dv-widget-header"><span>{html.escape(title)}</span>'
            f'<div class="dv-widget-actions">{controls}<small data-view-status-label>{html.escape(status)}</small></div></header>'
            '<div class="dv-widget-body"><div class="dv-view-placeholder">Waiting for dataset</div></div>'
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
                selector_view_id = view_definition(section.views[0]).widget
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
            f'<details class="dv-context-selections" data-selection-origin="{html.escape(origin)}">'
            f'<summary><span class="dv-context-selections__mark">{scope[0]}</span>'
            f'<strong>{scope} selection</strong><small>{len(fields)}</small><i>⌄</i></summary>'
            f'<div class="dv-context-selections__panel">{"".join(fields)}</div></details>'
        )

    def _client_sources(self, dashboard: LoadedDashboard) -> list[str]:
        configured = list(dashboard.definition.canvas.client_sources)
        inferred = [
            source_id
            for view in dashboard.definition.views
            for source_id in view.source_ids
        ]
        repeated = [
            section.repeat.source
            for section in dashboard.definition.sections
            if section.repeat and section.repeat.source
        ]
        return list(dict.fromkeys(configured + inferred + repeated))

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

    def _declarative_script(self, dashboard: LoadedDashboard) -> str:
        if not dashboard.definition.views:
            return ""
        specs = json.dumps(
            [item.model_dump(mode="json") for item in dashboard.definition.views],
            ensure_ascii=False,
            default=str,
        ).replace("</", "<\\/")
        repeat_specs = []
        for section in dashboard.definition.sections:
            if not section.repeat:
                continue
            view_ids = [view_definition(value).widget for value in section.views]
            repeat_specs.append({
                "section": section.id,
                "template": section.template,
                **section.repeat.model_dump(mode="json"),
                "view": section.repeat.view or (view_ids[0] if view_ids else None),
            })
        repeat_json = json.dumps(repeat_specs, ensure_ascii=False, default=str).replace("</", "<\\/")
        return f"""
const datavizViewSpecs = {specs};
const datavizRepeatSpecs = {repeat_json};
const datavizRepeatedViewIds = new Set(datavizRepeatSpecs.map(spec => spec.view));
const dvEscape = value => String(value ?? '').replace(/[&<>\"']/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[char]));
const dvSelectRows = (view, state) => {{
  const contract = state.portable?.selection_contract?.[view.id] || [];
  return state.data.source(view.source || view.sources?.[0]).rows().filter(row => contract.every(item => {{
    const value = state.selections[item.key];
    if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return true;
    const pathFields = item.definition?.path_fields || [];
    if (pathFields.length) {{
      const paths = Array.isArray(value?.[0]) ? value : [value];
      const matched = paths.some(path => pathFields.every((field, index) => String(row[field] ?? '') === String(path[index] ?? '')));
      return item.definition?.mode === 'exclude' ? !matched : matched;
    }}
    const field = item.binding?.field || item.id;
    const actual = row[field];
    const operator = item.binding?.operator === 'auto'
      ? (item.definition?.type === 'multi_select' ? 'in' : item.definition?.type === 'date_range' ? 'between' : 'equals')
      : item.binding?.operator;
    let matched;
    if (operator === 'in') matched = (Array.isArray(value) ? value : [value]).map(String).includes(String(actual));
    else if (operator === 'between') matched = !Array.isArray(value) || value.length < 2 || (String(actual) >= String(value[0]) && String(actual) <= String(value[1]));
    else if (operator === 'contains') matched = String(actual ?? '').includes(String(value ?? ''));
    else if (operator === 'gte') matched = Number(actual) >= Number(value);
    else if (operator === 'lte') matched = Number(actual) <= Number(value);
    else if (operator === 'gt') matched = Number(actual) > Number(value);
    else if (operator === 'lt') matched = Number(actual) < Number(value);
    else matched = String(actual ?? '') === String(value ?? '');
    return item.definition?.mode === 'exclude' ? !matched : matched;
  }}));
}};
const dvAggregate = (rows, groupFields, valueField, operation = 'sum') => {{
  const groups = new Map();
  rows.forEach(row => {{
    const key = JSON.stringify(groupFields.map(field => row[field]));
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }});
  return [...groups].map(([key, values]) => {{
    const output = Object.fromEntries(groupFields.map((field, index) => [field, JSON.parse(key)[index]]));
    const numbers = values.map(row => Number(row[valueField] ?? 0));
    if (operation === 'count') output[valueField] = values.length;
    else if (operation === 'mean') output[valueField] = numbers.reduce((a,b) => a+b, 0) / Math.max(numbers.length, 1);
    else if (operation === 'min') output[valueField] = Math.min(...numbers);
    else if (operation === 'max') output[valueField] = Math.max(...numbers);
    else output[valueField] = numbers.reduce((a,b) => a+b, 0);
    return output;
  }});
}};
const dvPreparedRows = (view, state) => {{
  let rows = dvSelectRows(view, state);
  const valueField = view.template === 'heatmap' ? view.z : (view.y || view.value || view.z);
  const groups = (view.template === 'heatmap' ? [view.x, view.y] : [view.x || view.label, view.series]).filter(Boolean);
  const operation = view.template === 'metric'
    ? 'none'
    : (view.aggregate || (['scatter','table','perspective'].includes(view.template) ? 'none' : 'sum'));
  if (operation !== 'none' && valueField && groups.length) rows = dvAggregate(rows, groups, valueField, operation);
  if (view.sort) {{
    const descending = view.sort.startsWith('-');
    const field = descending ? view.sort.slice(1) : view.sort;
    rows.sort((a,b) => (a[field] > b[field] ? 1 : a[field] < b[field] ? -1 : 0) * (descending ? -1 : 1));
  }}
  return view.limit ? rows.slice(0, view.limit) : rows;
}};
const dvPlotlyDescriptor = (view, rows) => {{
  const groups = view.series ? [...new Set(rows.map(row => row[view.series]))] : [null];
  const traces = groups.map(group => {{
    const selected = group == null ? rows : rows.filter(row => row[view.series] === group);
    const common = {{name: group == null ? view.title : String(group), x: selected.map(row => row[view.x]), y: selected.map(row => row[view.y])}};
    if (view.template === 'line') return {{...common, type:'scatter', mode:'lines+markers'}};
    if (view.template === 'scatter') return {{...common, type:'scatter', mode:'markers', marker:{{size:view.size ? selected.map(row => row[view.size]) : 9, color:view.color ? selected.map(row => row[view.color]) : undefined}}}};
    return {{...common, type:'bar'}};
  }});
  if (view.template === 'pie') traces.splice(0, traces.length, {{type:'pie', labels:rows.map(row => row[view.label || view.x]), values:rows.map(row => row[view.value || view.y]), hole:view.options?.hole || 0}});
  if (view.template === 'heatmap') {{
    const xs = [...new Set(rows.map(row => row[view.x]))], ys = [...new Set(rows.map(row => row[view.y]))];
    traces.splice(0, traces.length, {{type:'heatmap', x:xs, y:ys, z:ys.map(y => xs.map(x => rows.find(row => row[view.x] === x && row[view.y] === y)?.[view.z] ?? null)), colorscale:view.options?.colorscale || 'Viridis'}});
  }}
  return {{type:'plotly', data:traces, layout:{{margin:{{l:48,r:20,t:20,b:46}}, paper_bgcolor:'transparent', plot_bgcolor:'transparent', barmode:view.template === 'stacked-bar' ? 'stack' : (view.options?.barmode || 'group'), legend:{{orientation:'h', y:1.12}}, ...view.options?.layout}}, config:view.config}};
}};
const dvEchartsDescriptor = (view, rows) => {{
  if (view.template === 'pie') return {{type:'echarts', options:{{tooltip:{{trigger:'item'}}, series:[{{type:'pie', radius:['18%','72%'], data:rows.map(row => ({{name:row[view.label || view.x], value:row[view.value || view.y]}}))}}], ...view.options}}}};
  if (view.template === 'heatmap') {{
    const xs = [...new Set(rows.map(row => row[view.x]))], ys = [...new Set(rows.map(row => row[view.y]))];
    const data = rows.map(row => [xs.indexOf(row[view.x]), ys.indexOf(row[view.y]), row[view.z]]);
    const {{colors, visualMap:visualMapOptions, ...heatmapOptions}} = view.options || {{}};
    const visualMap = {{min:Math.min(...data.map(item=>Number(item[2]))),max:Math.max(...data.map(item=>Number(item[2]))),calculable:true,orient:'horizontal',...(colors ? {{inRange:{{color:colors}}}} : {{}}),...(visualMapOptions || {{}})}};
    return {{type:'echarts', options:{{tooltip:{{}}, xAxis:{{type:'category',data:xs}}, yAxis:{{type:'category',data:ys}}, visualMap, series:[{{type:'heatmap',data}}], ...heatmapOptions}}}};
  }}
  if (view.template === 'scatter') return {{type:'echarts', options:{{tooltip:{{trigger:'item'}}, xAxis:{{type:'value'}}, yAxis:{{type:'value'}}, series:[{{type:'scatter',data:rows.map(row => [row[view.x],row[view.y],view.size ? row[view.size] : undefined]),symbolSize:item => item[2] || 10}}], ...view.options}}}};
  const categories = [...new Set(rows.map(row => row[view.x]))];
  const groups = view.series ? [...new Set(rows.map(row => row[view.series]))] : [null];
  const {{legend_interaction:legendInteraction = 'filter', legend:legendOptions = {{}}, ...chartOptions}} = view.options || {{}};
  return {{
    type:'echarts',
    legendInteraction,
    options:{{
      tooltip:{{trigger:'axis'}},
      legend:{{...legendOptions, selectedMode:legendInteraction === 'none' ? false : (legendOptions.selectedMode ?? true)}},
      xAxis:{{type:'category', data:categories}},
      yAxis:{{type:'value'}},
      series:groups.map(group => ({{
        name:group == null ? view.title : String(group),
        type:view.template === 'line' ? 'line' : 'bar',
        stack:view.template === 'stacked-bar' ? 'total' : undefined,
        data:categories.map(category => rows.find(row => row[view.x] === category && (group == null || row[view.series] === group))?.[view.y] ?? null)
      }})),
      ...chartOptions
    }}
  }};
}};
const dvBuildView = (view, state, preparedRows = null) => {{
  const rows = preparedRows == null ? dvPreparedRows(view, state) : (() => {{
    let values = preparedRows;
    const valueField = view.template === 'heatmap' ? view.z : (view.y || view.value || view.z);
    const groups = (view.template === 'heatmap' ? [view.x, view.y] : [view.x || view.label, view.series]).filter(Boolean);
    const operation = view.template === 'metric'
      ? 'none'
      : (view.aggregate || (['scatter','table','perspective'].includes(view.template) ? 'none' : 'sum'));
    if (operation !== 'none' && valueField && groups.length) values = dvAggregate(values, groups, valueField, operation);
    if (view.sort) {{
      const descending = view.sort.startsWith('-');
      const field = descending ? view.sort.slice(1) : view.sort;
      values = [...values].sort((a,b) => (a[field] > b[field] ? 1 : a[field] < b[field] ? -1 : 0) * (descending ? -1 : 1));
    }}
    return view.limit ? values.slice(0, view.limit) : values;
  }})();
  if (view.template === 'table') return {{type:'table', rows, columns:view.columns?.length ? view.columns : Object.keys(rows[0] || {{}}), limit:view.limit, options:view.options, config:view.config}};
  if (view.template === 'perspective') return {{type:'perspective', rows, columns:view.columns?.length ? view.columns : Object.keys(rows[0] || {{}}), config:view.config, limit:view.limit}};
  if (view.template === 'metric') {{
    const field = view.value || view.y;
    const values = rows.map(row => Number(row[field] ?? 0));
    const operation = view.aggregate || 'sum';
    const value = operation === 'count' ? rows.length : operation === 'mean' ? values.reduce((a,b)=>a+b,0)/Math.max(values.length,1) : operation === 'min' ? Math.min(...values) : operation === 'max' ? Math.max(...values) : values.reduce((a,b)=>a+b,0);
    const formatted = Number.isFinite(value) ? new Intl.NumberFormat(undefined, view.options?.format || {{maximumFractionDigits:2}}).format(value) : '—';
    return {{type:'html', html:`<div class="dv-metric"><strong>${{dvEscape(formatted)}}</strong><span>${{dvEscape(view.label || field || '')}}</span></div>`}};
  }}
  if (view.template === 'markdown') return {{type:'html', html:`<div class="dv-prose">${{dvEscape(view.text || '').replace(/\\n\\n/g,'</p><p>').replace(/\\n/g,'<br>')}}</div>`}};
  if (view.template === 'image') return {{type:'html', html:`<img class="dv-image" src="${{dvEscape(view.url || '')}}" alt="${{dvEscape(view.title || '')}}">`}};
  return view.engine === 'echarts' ? dvEchartsDescriptor(view, rows) : dvPlotlyDescriptor(view, rows);
}};
const dvRepeatTitle = (template, row, fields) => String(template || '{{value}}').replace(/[{{]([^}}]+)[}}]/g, (_, name) => {{
  if (name === 'value') return fields.map(field => row[field] ?? '').join(' / ');
  return row[name] ?? '';
}});
const dvRepeatInstances = (spec, view, state) => {{
  if (!view) return [];
  const repeatedView = spec.source ? {{...view, source:spec.source, sources:[]}} : view;
  const contract = state.portable?.selection_contract?.[view.id] || [];
  if (spec.template === 'selection-gallery') {{
    const selection = contract.find(item => item.origin === 'section' && item.owner_id === spec.section && (!spec.selection || item.id === spec.selection));
    const value = selection ? state.selections[selection.key] : null;
    if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return [];
  }}
  const grouped = new Map();
  dvSelectRows(repeatedView, state).forEach(row => {{
    const values = spec.by.map(field => row[field]);
    const key = JSON.stringify(values);
    if (!grouped.has(key)) grouped.set(key, {{key, values, row, rows:[]}});
    grouped.get(key).rows.push(row);
  }});
  let groups = [...grouped.values()];
  const direction = spec.order === 'desc' ? -1 : 1;
  groups.sort((left, right) => {{
    if (spec.order_by) {{
      const a = left.rows.reduce((sum, row) => sum + Number(row[spec.order_by] ?? 0), 0);
      const b = right.rows.reduce((sum, row) => sum + Number(row[spec.order_by] ?? 0), 0);
      if (a !== b) return (a - b) * direction;
    }}
    return left.values.map(String).join('\u0000').localeCompare(right.values.map(String).join('\u0000')) * direction;
  }});
  if (spec.limit) groups = groups.slice(0, spec.limit);
  return groups.map(group => ({{
    key: group.key,
    id: `${{view.id}}@${{group.values.map(value => encodeURIComponent(String(value ?? ''))).join('/')}}`,
    title: dvRepeatTitle(spec.title, group.row, spec.by),
    signature: JSON.stringify(group.rows),
    render: () => dvBuildView(repeatedView, state, group.rows),
  }}));
}};
window.datavizClient = {{
  render(state, context = {{}}) {{
    const affected = context.affectedViewIds ? new Set(context.affectedViewIds) : null;
    datavizViewSpecs
      .filter(view => !datavizRepeatedViewIds.has(view.id) && (!affected || affected.has(view.id)))
      .forEach(view => state.renderView(view.id, () => dvBuildView(view, state)));
    datavizRepeatSpecs
      .filter(spec => !affected || affected.has(spec.view))
      .forEach(spec => {{
        const view = datavizViewSpecs.find(item => item.id === spec.view);
        state.renderRepeatedSection(spec, dvRepeatInstances(spec, view, state));
      }});
  }}
}};
"""

    def _portable_bundle(
        self, dashboard: LoadedDashboard, result: RunResult, store: ArtifactStore
    ) -> dict[str, Any]:
        sources: dict[str, list[dict[str, Any]]] = {}
        for source_id in self._client_sources(dashboard):
            node = result.nodes.get(f"source:{source_id}")
            if not node or node.status != "succeeded":
                continue
            artifact = next((item for item in node.artifacts if item.kind == "table"), None)
            if artifact:
                frame = store.read_table(artifact)
                sources[source_id] = json.loads(frame.to_json(orient="records", date_format="iso"))
        contract = compile_selection_contract(dashboard.definition)
        view_sources = {view.id: list(view.source_ids) for view in dashboard.definition.views}
        for section in dashboard.definition.sections:
            if not section.repeat or not section.repeat.source:
                continue
            view_ids = [view_definition(value).widget for value in section.views]
            repeat_view = section.repeat.view or (view_ids[0] if view_ids else None)
            if repeat_view:
                view_sources[repeat_view] = list(dict.fromkeys(view_sources.get(repeat_view, []) + [section.repeat.source]))
        return {
            "sources": sources,
            "view_sources": view_sources,
            "selection_contract": {
                view_id: [item.as_dict() for item in selections]
                for view_id, selections in contract.items()
            },
        }

    def _portable_controls(self, dashboard: LoadedDashboard, result: RunResult) -> str:
        contract = compile_selection_contract(dashboard.definition)
        controls: dict[str, dict[str, Any]] = {}
        section_titles = {item.id: item.title for item in dashboard.definition.sections}
        widget_titles = {key: value[1].title for key, value in dashboard.widgets.items()}
        for widget_id, selections in contract.items():
            for item in selections:
                control = controls.setdefault(
                    item.key,
                    {"selection": item, "views": []},
                )
                control["views"].append(widget_id)

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
                f'<details class="dv-runtime-control" data-runtime-popover data-selection-origin="{origin}">'
                f'<summary><span>{number}</span><div><strong>Selections</strong><small>{len(values)} selector{"" if len(values) == 1 else "s"}</small></div><i>⌄</i></summary>'
                f'<div class="dv-runtime-popover"><header><span>{number}</span><div><strong>{title}</strong><small>Browser-only · redraws embedded views</small></div></header>'
                f'<div class="dv-report-selection-group__fields">{"".join(values) if values else "<em>None</em>"}</div></div></details>'
            )
        return (
            '<header class="dv-runtime-header" aria-label="Report controls">'
            '<div class="dv-runtime-brand"><span>PORTABLE ANALYSIS</span><strong>Dataset fixed. Views live.</strong></div>'
            '<nav class="dv-runtime-actions" aria-label="Dataset controls">'
            '<details class="dv-runtime-control" data-runtime-popover>'
            '<summary><span>01</span><div><strong>Parameters</strong><small>Fixed snapshot</small></div><i>⌄</i></summary>'
            f'<div class="dv-runtime-popover dv-runtime-popover--query"><header><span>01</span><div><strong>Query snapshot</strong><small>Values embedded in this HTML</small></div></header><div class="dv-runtime-query-values">{query_items}</div></div></details>'
            f'{"".join(groups)}</nav></header>'
        )

    def _selector_presentation(self, dashboard: LoadedDashboard, key: str, definition) -> dict[str, Any]:
        selector = dashboard.presentation.selectors.get(key) if dashboard.presentation else None
        result = selector.model_dump(mode="json") if selector else {
            "template": "auto",
            "show_unavailable": False,
            "search_placeholder": "Search options…",
            "empty_text": "No matching options",
            "css_class": "",
        }
        if result["template"] == "auto":
            if definition.path_fields:
                result["template"] = "cascader"
                return result
            count = len(definition.choices)
            if definition.type == "multi_select":
                result["template"] = "chips" if 0 < count <= 8 else "searchable"
            elif definition.type == "single_select":
                result["template"] = "dropdown" if count <= 20 else "searchable"
        return result

    def _portable_field(
        self,
        key: str,
        definition,
        value: Any,
        selector: dict[str, Any] | None = None,
        view_id: str | None = None,
    ) -> str:
        escaped_key = html.escape(key)
        if definition.type in {"single_select", "multi_select"}:
            selector = selector or {}
            template = selector.get("template", "chips" if definition.type == "multi_select" else "dropdown")
            css_class = html.escape(selector.get("css_class", ""))
            selected = {str(item) for item in (value if isinstance(value, list) else [value])}
            multiple = " multiple" if definition.type == "multi_select" else ""
            options = "".join(
                f'<option value="{html.escape(str(choice.value))}"'
                f'{" selected" if str(choice.value) in selected else ""}>{html.escape(choice.label)}</option>'
                for choice in definition.choices
            )
            select = f'<select aria-label="{html.escape(definition.label or definition.id)}" data-selection-input="{escaped_key}"{multiple}>{options}</select>'
            attrs = (
                f'data-selector-template="{html.escape(template)}" '
                f'data-show-unavailable="{str(bool(selector.get("show_unavailable", False))).lower()}" '
                f'data-search-placeholder="{html.escape(selector.get("search_placeholder", "Search options…"))}" '
                f'data-empty-text="{html.escape(selector.get("empty_text", "No matching options"))}"'
            )
            if template == "cascader":
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
                )
            return f'<div class="dv-selector {css_class}" {attrs}>{select}<div data-selector-mount></div></div>'
        input_type = "number" if definition.type == "number" else "date" if definition.type == "date" else "checkbox" if definition.type == "boolean" else "text"
        if definition.type == "boolean":
            return f'<input type="checkbox" data-selection-input="{escaped_key}"{" checked" if value else ""}>'
        display = ",".join(map(str, value)) if isinstance(value, list) else "" if value is None else str(value)
        placeholder = ' placeholder="start,end"' if definition.type == "date_range" else ""
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
        widgets: dict[str, str],
        parameters: dict[str, Any],
        selections: dict[str, Any],
    ) -> str:
        definition = dashboard.definition
        assumptions = "".join(f"<li>{html.escape(value)}</li>" for value in definition.assumptions)
        by_id = {item.widget: item for item in definition.layout.items}
        all_view_ids = list(dashboard.widgets)
        run_state = SimpleNamespace(selections=selections)

        def view_item(view_id: str) -> str:
            layout = by_id.get(view_id)
            style = ""
            css_class = ""
            if layout:
                style = f"--dv-span:{max(1, min(definition.layout.columns, layout.width))};"
                if layout.min_height is not None:
                    style += f"min-height:{max(1, layout.min_height)}px;"
                css_class = layout.css_class
            return (
                f'<div class="dv-section-view {html.escape(css_class)}" style="{style}">'
                f'{widgets.get(view_id, self._client_view_html(dashboard, view_id, run_state))}'
                "</div>"
            )

        sections = []
        assigned: set[str] = set()
        for section in definition.sections:
            view_ids = [view_definition(value).widget for value in section.views]
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
                '<section class="dv-section dv-section--grid" data-section-id="overview">'
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

    def _widget_html(
        self,
        widget_id: str,
        artifacts: list[ArtifactDescriptor],
        store: ArtifactStore,
        chart_mode: str,
        image_format: str,
    ) -> str:
        if not artifacts:
            return '<section class="dv-widget dv-widget--empty">No output</section>'
        title = artifacts[0].metadata.get("title", widget_id)
        contents = [self._artifact_html(item, store, chart_mode, image_format) for item in artifacts]
        return (
            f'<article class="dv-widget" data-widget-id="{html.escape(widget_id)}">'
            f'<header class="dv-widget-header"><span>{html.escape(str(title))}</span>'
            f'<small>{html.escape(artifacts[0].kind)}</small></header>'
            f'<div class="dv-widget-body">{"".join(contents)}</div></article>'
        )

    def _artifact_html(
        self, artifact: ArtifactDescriptor, store: ArtifactStore, chart_mode: str, image_format: str
    ) -> str:
        path = store.resolve(artifact)
        if artifact.kind == "chart" and artifact.format == "plotly-json":
            spec = json.loads(path.read_text("utf-8")) if path else artifact.inline
            if chart_mode == "static":
                try:
                    import plotly.io as pio

                    image = pio.to_image(spec, format=image_format)
                except Exception as exc:
                    raise ExecutionFailure(f"Plotly static export failed: {exc}") from exc
                mime = "image/svg+xml" if image_format == "svg" else f"image/{image_format}"
                encoded = base64.b64encode(image).decode("ascii")
                return f'<img class="dv-image" src="data:{mime};base64,{encoded}" alt="chart">'
            encoded = base64.b64encode(json.dumps(spec, ensure_ascii=False).encode()).decode()
            return f'<div class="dv-chart dv-plotly" data-spec="{encoded}"></div>'
        if artifact.kind == "chart" and artifact.format == "echarts-json":
            spec = json.loads(path.read_text("utf-8")) if path else artifact.inline
            encoded = base64.b64encode(json.dumps(spec, ensure_ascii=False).encode()).decode()
            return f'<div class="dv-chart dv-echarts" data-spec="{encoded}"></div>'
        if artifact.kind == "table":
            frame = store.read_table(artifact)
            rows = json.loads(frame.to_json(orient="records", date_format="iso"))
            columns = [str(value) for value in frame.columns]
            payload = base64.b64encode(
                json.dumps({"rows": rows, "columns": columns}, ensure_ascii=False).encode("utf-8")
            ).decode("ascii")
            return (
                '<div class="dv-perspective-bootstrap" '
                f'data-perspective-payload="{payload}">Preparing interactive table…</div>'
            )
        if artifact.kind == "image" and path:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f'<img class="dv-image" src="data:{artifact.mime_type};base64,{encoded}" alt="visualization">'
        if artifact.kind == "text" and path:
            content = path.read_text("utf-8")
            rendered = markdown_lib.markdown(content) if artifact.format == "markdown" else f"<pre>{html.escape(content)}</pre>"
            return f'<div class="dv-prose">{rendered}</div>'
        if artifact.kind == "scalar" and path:
            value = json.loads(path.read_text("utf-8"))
            return f'<div class="dv-scalar">{html.escape(str(value))}</div>'
        if artifact.kind == "html" and path:
            return path.read_text("utf-8")
        return f'<p class="dv-muted">Unsupported artifact: {html.escape(artifact.format)}</p>'

    def _formats(self, result: RunResult) -> set[str]:
        return {artifact.format for values in result.outputs.values() for artifact in values}

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
  return {{perspective, worker: await perspective.worker()}};
}})();
</script>"""

    def _runtime_script(self, result: RunResult) -> str:
        return """
const decodeSpec = (node) => JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(node.dataset.spec), c => c.charCodeAt(0))));
document.querySelectorAll('.dv-plotly').forEach(node => {
  const spec = decodeSpec(node);
  if (typeof Plotly === 'undefined') {
    node.innerHTML = '<div class="dv-runtime-error">Plotly.js could not be loaded.</div>';
    return;
  }
  Plotly.newPlot(node, spec.data || [], spec.layout || {}, {responsive: true, displaylogo: false});
});
document.querySelectorAll('.dv-echarts').forEach(node => {
  if (typeof echarts === 'undefined') {
    node.innerHTML = '<div class="dv-runtime-error">ECharts could not be loaded. Check the runtime.echarts_js setting or network access.</div>';
    return;
  }
  const chart = echarts.init(node);
  chart.setOption(decodeSpec(node));
  new ResizeObserver(() => chart.resize()).observe(node);
});
class DatavizFrame {
  constructor(rows = []) { this._rows = Array.isArray(rows) ? rows : []; }
  rows() { return this._rows.map(row => ({...row})); }
  column(name) { return this._rows.map(row => row[name]); }
  filter(predicate) { return new DatavizFrame(this._rows.filter(predicate)); }
  where(field, operator, value) {
    const values = Array.isArray(value) ? value : [value];
    return this.filter(row => {
      const actual = row[field];
      if (operator === 'in') return !values.length || values.includes(actual);
      if (operator === 'not_in') return !values.includes(actual);
      if (operator === '>=') return Number(actual) >= Number(value);
      if (operator === '<=') return Number(actual) <= Number(value);
      if (operator === '>') return Number(actual) > Number(value);
      if (operator === '<') return Number(actual) < Number(value);
      if (operator === 'contains') return String(actual ?? '').includes(String(value ?? ''));
      return actual === value;
    });
  }
  derive(columns) {
    return new DatavizFrame(this._rows.map(row => {
      const next = {...row};
      Object.entries(columns).forEach(([name, derive]) => { next[name] = derive(next); });
      return next;
    }));
  }
  sort(field, direction = 'asc') {
    const sign = direction === 'desc' ? -1 : 1;
    return new DatavizFrame([...this._rows].sort((left, right) => {
      const a = left[field], b = right[field];
      return (typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b))) * sign;
    }));
  }
  limit(count) { return new DatavizFrame(this._rows.slice(0, count)); }
  groupBy(...fields) { return new DatavizGroupedFrame(this._rows, fields.flat()); }
}
class DatavizGroupedFrame {
  constructor(rows, fields) { this._rows = rows; this._fields = fields; }
  aggregate(spec) {
    const groups = new Map();
    this._rows.forEach(row => {
      const key = JSON.stringify(this._fields.map(field => row[field]));
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    });
    const rows = [...groups.entries()].map(([key, values]) => {
      const keys = JSON.parse(key);
      const result = Object.fromEntries(this._fields.map((field, index) => [field, keys[index]]));
      Object.entries(spec).forEach(([output, rule]) => {
        const definition = typeof rule === 'string' ? {field: output, op: rule} : rule;
        const numbers = values.map(row => Number(row[definition.field] ?? 0));
        if (definition.op === 'count') result[output] = values.length;
        else if (definition.op === 'mean') result[output] = numbers.reduce((a, b) => a + b, 0) / Math.max(numbers.length, 1);
        else if (definition.op === 'min') result[output] = Math.min(...numbers);
        else if (definition.op === 'max') result[output] = Math.max(...numbers);
        else result[output] = numbers.reduce((a, b) => a + b, 0);
      });
      return result;
    });
    return new DatavizFrame(rows);
  }
}
const viewNode = id => document.querySelector(`.dv-widget[data-widget-id="${CSS.escape(id)}"]`);
const perspectiveViews = new Map();
let perspectiveTableSerial = 0;
const releaseWheelAtBoundary = host => {
  if (!host || host.__datavizWheelBoundary) return;
  host.__datavizWheelBoundary = true;
  host.addEventListener('wheel', event => {
    if (event.ctrlKey || !event.deltaY || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
    const path = event.composedPath();
    const hostIndex = path.indexOf(host);
    const candidates = path.slice(0, hostIndex + 1).filter(node => {
      if (!(node instanceof Element)) return false;
      const style = getComputedStyle(node);
      return /(auto|scroll|overlay)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1;
    });
    const direction = Math.sign(event.deltaY);
    const canConsume = candidates.some(node => direction > 0
      ? node.scrollTop + node.clientHeight < node.scrollHeight - 1
      : node.scrollTop > 1);
    if (canConsume) return;
    const page = document.scrollingElement || document.documentElement;
    const pageCanConsume = page && page.scrollHeight > page.clientHeight + 1 && (direction > 0
      ? page.scrollTop + page.clientHeight < page.scrollHeight - 1
      : page.scrollTop > 1);
    if (!pageCanConsume) return;
    const multiplier = event.deltaMode === WheelEvent.DOM_DELTA_LINE
      ? 16
      : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? window.innerHeight : 1;
    event.preventDefault();
    event.stopImmediatePropagation();
    page.scrollTop += event.deltaY * multiplier;
  }, {capture:true, passive:false});
};
const formatTableValue = (value, rule) => {
  if (value == null) return '';
  if (!rule) return String(value);
  if (rule === 'number') return new Intl.NumberFormat().format(Number(value));
  if (rule === 'percent') return new Intl.NumberFormat(undefined, {style:'percent', maximumFractionDigits:2}).format(Number(value));
  if (rule === 'date') return new Intl.DateTimeFormat(undefined, {dateStyle:'medium'}).format(new Date(value));
  if (rule === 'datetime') return new Intl.DateTimeFormat(undefined, {dateStyle:'medium', timeStyle:'short'}).format(new Date(value));
  if (rule === 'currency') return new Intl.NumberFormat(undefined, {style:'currency', currency:'CNY'}).format(Number(value));
  if (typeof rule === 'object') {
    if (rule.type === 'date' || rule.type === 'datetime') return new Intl.DateTimeFormat(rule.locale, rule.options || {}).format(new Date(value));
    return new Intl.NumberFormat(rule.locale, rule.options || rule).format(Number(value));
  }
  return String(value);
};
const renderPlainTable = (body, rows, columns, limit = 100, descriptor = {}) => {
  const options = descriptor.options || {};
  const visibleRows = rows.slice(0, limit || rows.length);
  const fragment = document.createDocumentFragment();
  if (options.show_count !== false) {
    const meta = document.createElement('div');
    meta.className = 'dv-table-meta';
    meta.innerHTML = `<strong>${rows.length}</strong><span>rows${visibleRows.length < rows.length ? ` · showing ${visibleRows.length}` : ''}</span>`;
    fragment.append(meta);
  }
  if (!rows.length) {
    const empty = document.createElement('div');
    empty.className = 'dv-table-empty';
    empty.textContent = options.empty_text || 'No rows match the current selections.';
    fragment.append(empty);
    body.replaceChildren(fragment);
    return;
  }
  const wrap = document.createElement('div');
  wrap.className = 'dv-table-wrap';
  const table = document.createElement('table');
  table.className = `dv-table${options.striped === false ? '' : ' dv-table--striped'}${options.compact ? ' dv-table--compact' : ''}`;
  if (options.layout === 'fixed') table.style.tableLayout = 'fixed';
  const head = table.createTHead().insertRow();
  columns.forEach(column => {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.dataset.column = column;
    cell.textContent = options.labels?.[column] || column;
    if (options.align?.[column]) cell.dataset.align = options.align[column];
    head.append(cell);
  });
  const tbody = table.createTBody();
  visibleRows.forEach((row, rowIndex) => {
    const tr = tbody.insertRow();
    tr.dataset.rowIndex = rowIndex;
    columns.forEach(column => {
      const cell = tr.insertCell();
      cell.dataset.column = column;
      if (options.align?.[column]) cell.dataset.align = options.align[column];
      cell.textContent = formatTableValue(row[column], options.formats?.[column]);
    });
  });
  wrap.append(table);
  releaseWheelAtBoundary(wrap);
  fragment.append(wrap);
  body.replaceChildren(fragment);
};
const renderPerspectiveInto = (key, root, body, descriptor) => {
  const rows = descriptor.rows || [];
  const columns = descriptor.columns || Object.keys(rows[0] || {});
  const existing = perspectiveViews.get(key);
  if (existing) {
    existing.latestRows = rows;
    if (existing.table) {
      existing.pending = existing.pending.then(async () => {
        await existing.table.replace(existing.latestRows);
        if (typeof existing.viewer.flush === 'function') await existing.viewer.flush();
        else if (typeof existing.viewer.resize === 'function') await existing.viewer.resize();
        setViewStatus(root, 'ready', 'perspective');
      }).catch(error => {
        setViewStatus(root, 'failed', 'perspective failed');
        console.error(`[dataviz:${key}] Perspective update failed`, error);
      });
    }
    return existing.pending;
  }

  root?.classList.add('dv-widget--perspective');
  const loading = document.createElement('div');
  loading.className = 'dv-perspective-loading';
  loading.innerHTML = '<span></span><strong>Preparing analysis table</strong><small>sort · filter · pivot · chart</small>';
  body.replaceChildren(loading);
  const state = {table: null, viewer: null, latestRows: rows, pending: Promise.resolve()};
  perspectiveViews.set(key, state);
  state.pending = (async () => {
    if (!window.datavizPerspectiveReady) throw new Error('Perspective is not loaded; add perspective to canvas.client_libraries');
    if (!state.latestRows.length) {
      renderPlainTable(body, [], columns, descriptor.limit || 100, descriptor);
      return;
    }
    const {worker} = await window.datavizPerspectiveReady;
    const tableName = `dataviz_${String(key).replace(/[^A-Za-z0-9_]/g, '_')}_${++perspectiveTableSerial}`;
    const table = await worker.table(state.latestRows, {name: tableName});
    const viewer = document.createElement('perspective-viewer');
    viewer.className = 'dv-perspective';
    viewer.setAttribute('theme', descriptor.theme || 'Pro Light');
    releaseWheelAtBoundary(viewer);
    body.replaceChildren(viewer);
    await viewer.load(worker);
    state.table = table;
    state.viewer = viewer;
    const restore = viewer.restore({
      plugin: 'Datagrid',
      columns,
      settings: false,
      ...(descriptor.config || descriptor.perspective || {}),
      table: tableName,
    });
    restore.catch(error => console.warn(`[dataviz:${key}] Perspective restore completed with an error`, error));
    if (typeof viewer.flush === 'function') await viewer.flush();
    else await restore;
    if (state.latestRows !== rows) await table.replace(state.latestRows);
    new ResizeObserver(() => { if (typeof viewer.resize === 'function') viewer.resize(); }).observe(body);
    setViewStatus(root, 'ready', 'perspective');
  })().catch(error => {
    perspectiveViews.delete(key);
    root?.classList.remove('dv-widget--perspective');
    renderPlainTable(body, rows, columns, descriptor.limit || 100, descriptor);
    setViewStatus(root, 'ready', 'table fallback');
    console.warn(`[dataviz:${key}] Perspective unavailable; using basic table`, error);
  });
  return state.pending;
};
const clearViewRoot = (root, key) => {
  const body = root?.querySelector('.dv-widget-body');
  if (!root || !body) return {root, body};
  root.classList.remove('dv-widget--table');
  const perspectiveState = perspectiveViews.get(key);
  if (perspectiveState) {
    perspectiveViews.delete(key);
    perspectiveState.pending.finally(() => perspectiveState.table?.delete?.()).catch(() => {});
    root.classList.remove('dv-widget--perspective');
  }
  body.querySelectorAll('.dv-echarts').forEach(node => {
    const instance = typeof echarts !== 'undefined' && echarts.getInstanceByDom(node);
    if (instance) instance.dispose();
  });
  body.querySelectorAll('.dv-plotly').forEach(node => { if (typeof Plotly !== 'undefined') Plotly.purge(node); });
  body.replaceChildren();
  return {root, body};
};
const clearView = id => clearViewRoot(viewNode(id), id);
const setViewStatus = (root, status, label = status) => {
  if (!root) return;
  root.dataset.viewStatus = status;
  const node = root.querySelector('[data-view-status-label]');
  if (node) node.textContent = label;
};
const bindEchartsLegendInteraction = (chart, descriptor) => {
  if (descriptor.legendInteraction !== 'filter') return;
  const options = descriptor.options || {};
  const xAxes = Array.isArray(options.xAxis) ? options.xAxis : [options.xAxis];
  const categoryAxis = xAxes[0];
  const sourceCategories = [...(categoryAxis?.data || [])];
  const sourceSeries = (options.series || []).map(series => ({
    ...series,
    data: [...(series.data || [])],
  }));
  if (categoryAxis?.type !== 'category' || !sourceCategories.length || !sourceSeries.length) return;
  chart.on('legendselectchanged', event => {
    const categories = sourceCategories.filter((category, index) => sourceSeries.some(series =>
      event.selected?.[series.name] !== false && series.data[index] != null
    ));
    const series = sourceSeries.map(item => ({
      ...item,
      data: categories.map(category => item.data[sourceCategories.indexOf(category)]),
    }));
    const nextAxes = [{...categoryAxis, data:categories}, ...xAxes.slice(1)];
    chart.setOption(
      {xAxis:Array.isArray(options.xAxis) ? nextAxes : nextAxes[0], series},
      {replaceMerge:['xAxis', 'series']},
    );
  });
};
const renderViewInto = (root, key, producer) => {
  setViewStatus(root, 'rendering');
  try {
    const descriptor = producer();
    const type = descriptor?.type || 'text';
    if (type === 'perspective') {
      const body = root?.querySelector('.dv-widget-body');
      if (!body) throw new Error(`Unknown view: ${key}`);
      renderPerspectiveInto(key, root, body, descriptor);
      return descriptor;
    }
    const {body} = clearViewRoot(root, key);
    if (!body) throw new Error(`Unknown view: ${key}`);
    if (type === 'table') {
      root?.classList.add('dv-widget--table');
      renderPlainTable(body, descriptor.rows || [], descriptor.columns || Object.keys(descriptor.rows?.[0] || {}), descriptor.limit || 100, descriptor);
    } else if (type === 'plotly') {
      if (typeof Plotly === 'undefined') throw new Error('Plotly.js is not loaded; add plotly to canvas.client_libraries');
      const node = document.createElement('div'); node.className = 'dv-chart dv-plotly'; body.append(node);
      Plotly.react(node, descriptor.data || [], descriptor.layout || {}, {responsive:true, displaylogo:false, ...(descriptor.config || {})});
    } else if (type === 'echarts') {
      if (typeof echarts === 'undefined') throw new Error('ECharts.js is not loaded; add echarts to canvas.client_libraries');
      const node = document.createElement('div'); node.className = 'dv-chart dv-echarts'; body.append(node);
      const chart = echarts.init(node); chart.setOption(descriptor.options || {});
      bindEchartsLegendInteraction(chart, descriptor);
      new ResizeObserver(() => chart.resize()).observe(node);
    } else if (type === 'html') body.innerHTML = descriptor.html || '';
    else { const node = document.createElement('div'); node.className = 'dv-prose'; node.textContent = descriptor?.text ?? ''; body.append(node); }
    setViewStatus(root, 'ready', type);
    return descriptor;
  } catch (error) {
    const {body} = clearViewRoot(root, key);
    if (body) { const node = document.createElement('pre'); node.className = 'dv-view-error'; node.textContent = error.stack || error.message; body.append(node); }
    setViewStatus(root, 'failed', 'error');
    console.error(`[dataviz:${key}]`, error);
    return null;
  }
};
const renderView = (id, producer) => renderViewInto(viewNode(id), id, producer);
const repeatObserver = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (!entry.isIntersecting || !entry.target.__datavizRepeatRender) return;
    const render = entry.target.__datavizRepeatRender;
    entry.target.__datavizRepeatRender = null;
    repeatObserver.unobserve(entry.target);
    render();
  });
}, {rootMargin:'520px 0px'});
const disposeRepeatCard = card => {
  repeatObserver?.unobserve(card);
  clearViewRoot(card, card.dataset.widgetId);
  card.remove();
};
const renderRepeatedSection = (spec, instances) => {
  const host = document.querySelector(`.dv-repeat[data-repeat-section="${CSS.escape(spec.section)}"]`);
  if (!host) return;
  const current = new Map(Array.from(host.querySelectorAll(':scope > .dv-repeat-card')).map(card => [card.dataset.repeatKey, card]));
  const keep = new Set(instances.map(instance => instance.key));
  current.forEach((card, key) => { if (!keep.has(key)) disposeRepeatCard(card); });
  if (!instances.length) {
    const empty = document.createElement('div');
    empty.className = 'dv-repeat-empty';
    empty.innerHTML = `<strong>${spec.template === 'selection-gallery' ? 'Nothing selected' : 'No groups available'}</strong><span>${String(spec.empty_text || 'No data matches the current selections.').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}</span>`;
    host.replaceChildren(empty);
    host.dataset.repeatCount = '0';
    return;
  }
  host.querySelector(':scope > .dv-repeat-empty')?.remove();
  instances.forEach((instance, index) => {
    let card = current.get(instance.key);
    if (!card) {
      card = document.createElement('article');
      card.className = 'dv-widget dv-widget--client dv-repeat-card';
      card.dataset.widgetId = instance.id;
      card.dataset.repeatKey = instance.key;
      card.dataset.viewStatus = 'waiting';
      card.innerHTML = `<header class="dv-widget-header"><span></span><div class="dv-widget-actions"><small data-view-status-label>queued</small></div></header><div class="dv-widget-body"><div class="dv-view-placeholder">Waiting to enter the viewport</div></div>`;
    }
    card.style.setProperty('--dv-repeat-index', index);
    card.querySelector('.dv-widget-header > span').textContent = instance.title;
    const changed = card.dataset.repeatSignature !== instance.signature;
    if (changed) {
      card.dataset.repeatSignature = instance.signature;
      const run = () => renderViewInto(card, instance.id, instance.render);
      if (spec.render === 'eager' || !repeatObserver) run();
      else {
        clearViewRoot(card, instance.id);
        const placeholder = document.createElement('div');
        placeholder.className = 'dv-view-placeholder dv-repeat-placeholder';
        placeholder.innerHTML = '<span></span><small>Queued for lazy rendering</small>';
        card.querySelector('.dv-widget-body').append(placeholder);
        card.__datavizRepeatRender = run;
        repeatObserver.observe(card);
      }
    }
    host.append(card);
  });
  host.dataset.repeatCount = String(instances.length);
};
document.querySelectorAll('.dv-perspective-bootstrap').forEach((node, index) => {
  try {
    const payload = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(node.dataset.perspectivePayload), value => value.charCodeAt(0))));
    const body = node.closest('.dv-widget-body');
    const root = node.closest('.dv-widget');
    if (body) renderPerspectiveInto(`artifact:${index}`, root, body, {type: 'perspective', ...payload});
  } catch (error) {
    node.textContent = `Interactive table failed: ${error.message}`;
  }
});
window.dataviz.data = {
  source: id => new DatavizFrame(window.dataviz.portable?.sources?.[id] || []),
  frame: rows => new DatavizFrame(rows),
};
window.dataviz.renderView = renderView;
window.dataviz.renderRepeatedSection = renderRepeatedSection;
window.dataviz.getViewSelections = (viewId) => {
  const contract = window.dataviz.portable?.selection_contract?.[viewId] || [];
  return Object.fromEntries(contract.map(item => [item.id, window.dataviz.selections[item.key]]));
};
// Compatibility aliases for custom canvases created before the selection migration.
window.dataviz.filters = window.dataviz.selections;
window.dataviz.getViewFilters = window.dataviz.getViewSelections;
const datavizSelectionRank = {dashboard: 0, section: 1, view: 2};
const datavizSelectionMatches = (row, item, value) => {
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return true;
  const pathFields = item.definition?.path_fields || [];
  if (pathFields.length) {
    const paths = Array.isArray(value?.[0]) ? value : [value];
    const matched = paths.some(path => pathFields.every((field, index) => String(row[field] ?? '') === String(path[index] ?? '')));
    return item.definition?.mode === 'exclude' ? !matched : matched;
  }
  const field = item.binding?.field || item.id;
  const actual = row[field];
  const operator = item.binding?.operator === 'auto'
    ? (item.definition?.type === 'multi_select' ? 'in' : item.definition?.type === 'date_range' ? 'between' : 'equals')
    : item.binding?.operator;
  let matched;
  if (operator === 'in') matched = (Array.isArray(value) ? value : [value]).map(String).includes(String(actual));
  else if (operator === 'between') matched = !Array.isArray(value) || value.length < 2 || (String(actual) >= String(value[0]) && String(actual) <= String(value[1]));
  else if (operator === 'contains') matched = String(actual ?? '').includes(String(value ?? ''));
  else if (operator === 'gte') matched = Number(actual) >= Number(value);
  else if (operator === 'lte') matched = Number(actual) <= Number(value);
  else if (operator === 'gt') matched = Number(actual) > Number(value);
  else if (operator === 'lt') matched = Number(actual) < Number(value);
  else matched = String(actual ?? '') === String(value ?? '');
  return item.definition?.mode === 'exclude' ? !matched : matched;
};
const datavizCascadeOccurrences = () => {
  const occurrences = new Map();
  Object.entries(window.dataviz.portable?.selection_contract || {}).forEach(([viewId, contract]) => {
    contract.forEach(item => {
      if (!occurrences.has(item.key)) occurrences.set(item.key, []);
      occurrences.get(item.key).push({viewId, item});
    });
  });
  return occurrences;
};
const refreshCascadingSelections = () => {
  const occurrences = datavizCascadeOccurrences();
  const controls = Array.from(document.querySelectorAll('[data-selection-key]'));
  [0, 1, 2].forEach(rank => {
    controls.forEach(control => {
      const targets = occurrences.get(control.dataset.selectionKey) || [];
      const targetRank = datavizSelectionRank[targets[0]?.item?.origin];
      if (!targets.length || targetRank !== rank) return;
      const input = control.querySelector('select');
      if (!input) return;
      if (control.querySelector('[data-selector-template="cascader"]')) {
        syncPortableChoices(control);
        return;
      }
      if (targets[0]?.item?.definition?.cascade === false && targets[0]?.item?.definition?.choices?.length) return;
      const available = new Set();
      let observedSource = false;
      targets.forEach(({viewId, item}) => {
        const sourceIds = window.dataviz.portable?.view_sources?.[viewId] || [];
        const upstream = (window.dataviz.portable?.selection_contract?.[viewId] || []).filter(candidate =>
          (datavizSelectionRank[candidate.origin] ?? 99) < targetRank
        );
        sourceIds.forEach(sourceId => {
          if (Object.prototype.hasOwnProperty.call(window.dataviz.portable?.sources || {}, sourceId)) observedSource = true;
          (window.dataviz.portable?.sources?.[sourceId] || []).forEach(row => {
            const included = upstream.every(candidate =>
              datavizSelectionMatches(row, candidate, window.dataviz.selections[candidate.key])
            );
            if (!included) return;
            const field = item.binding?.field || item.id;
            if (row[field] != null) available.add(String(row[field]));
          });
        });
      });
      if (!observedSource) return;
      if (!(targets[0]?.item?.definition?.choices || []).length) {
        const currentValue = window.dataviz.selections[control.dataset.selectionKey];
        const selected = new Set([
          ...Array.from(input.selectedOptions).map(option => String(option.value)),
          ...(Array.isArray(currentValue) ? currentValue.map(String) : []),
        ]);
        input.replaceChildren(...[...available].sort((a, b) => a.localeCompare(b)).map(value => {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = value;
          option.selected = selected.has(value);
          return option;
        }));
      }
      Array.from(input.options).forEach(option => {
        const enabled = available.has(String(option.value));
        option.disabled = !enabled;
        if (!enabled) option.selected = false;
      });
      control.dataset.cascadeAvailable = String(available.size);
      syncPortableChoices(control);
    });
    // Commit each scope before deriving the next one. A Dashboard change can
    // invalidate Section values, which must be visible to View selectors in
    // this same interaction rather than one event later.
    readSelectionInputs();
  });
};
const readSelectionInputs = () => {
  document.querySelectorAll('[data-selection-key]').forEach(control => {
    const key = control.dataset.selectionKey;
    const type = control.dataset.selectionType;
    const input = control.querySelector('[data-selection-input]');
    if (!input) return;
    let value;
    if (type === 'boolean') value = input.checked;
    else if (type === 'multi_select') value = input.options.length
      ? Array.from(input.selectedOptions).map(option =>
          control.dataset.selectionPath === 'true' ? JSON.parse(option.value) : option.value
        )
      : (window.dataviz.selections[key] || []);
    else if (type === 'number') value = input.value === '' ? null : Number(input.value);
    else if (type === 'date_range') value = input.value.split(',', 2).map(item => item.trim());
    else value = input.value;
    window.dataviz.selections[key] = value;
  });
};
const datavizSelectionSignature = value => JSON.stringify(
  Array.isArray(value) ? [...value].map(String).sort() : value
);
const datavizChangedSelectionKeys = (previous, current) => {
  if (previous == null) return null;
  const keys = new Set([...Object.keys(previous), ...Object.keys(current)]);
  return [...keys].filter(key =>
    datavizSelectionSignature(previous[key]) !== datavizSelectionSignature(current[key])
  );
};
const datavizAffectedViewIds = changedKeys => {
  if (changedKeys == null) return null;
  const changed = new Set(changedKeys);
  return Object.entries(window.dataviz.portable?.selection_contract || {})
    .filter(([, contract]) => contract.some(item => changed.has(item.key)))
    .map(([viewId]) => viewId);
};
window.dataviz.applySelections = () => {
  const previous = window.dataviz.appliedSelections || null;
  readSelectionInputs();
  refreshCascadingSelections();
  readSelectionInputs();
  const changedSelectionKeys = datavizChangedSelectionKeys(previous, window.dataviz.selections);
  const affectedViewIds = datavizAffectedViewIds(changedSelectionKeys);
  window.dataviz.appliedSelections = JSON.parse(JSON.stringify(window.dataviz.selections));
  window.dataviz.renderContext = {
    initial: changedSelectionKeys == null,
    changedSelectionKeys: changedSelectionKeys || Object.keys(window.dataviz.selections),
    affectedViewIds,
  };
  if (changedSelectionKeys?.length === 0) return;
  if (window.datavizClient?.render) {
    window.datavizClient.render(window.dataviz, window.dataviz.renderContext);
    window.dispatchEvent(new CustomEvent('dataviz:selectionchange', {detail: window.dataviz.selections}));
    if (window.parent !== window) {
      window.parent.postMessage({type: 'dataviz:selections-changed', selections: window.dataviz.selections}, window.location.origin);
    }
  }
};
window.dataviz.applyFilters = window.dataviz.applySelections;
const setSelectionInputs = values => {
  document.querySelectorAll('[data-selection-key]').forEach(control => {
    const key = control.dataset.selectionKey;
    if (!(key in values)) return;
    const input = control.querySelector('[data-selection-input]');
    if (!input) return;
    const value = values[key];
    if (control.dataset.selectionType === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((value || []).map(item => JSON.stringify(item)));
      Array.from(input.options).forEach(option => {
        const comparable = control.dataset.selectionPath === 'true' ? option.value : JSON.stringify(option.value);
        option.selected = selected.has(comparable);
      });
      syncPortableChoices(control);
    }
    else if (Array.isArray(value)) input.value = value.join(',');
    else input.value = value ?? '';
  });
};
window.addEventListener('message', event => {
  if (event.origin !== window.location.origin) return;
  const legacy = event.data?.type === 'dataviz:set-filters' && event.data.filters;
  const values = event.data?.type === 'dataviz:set-selections' ? event.data.selections : legacy;
  if (!values) return;
  Object.assign(window.dataviz.selections, values);
  setSelectionInputs(values);
  window.dataviz.applySelections();
});
let datavizSelectionTimer;
const scheduleDatavizSelection = () => {
  clearTimeout(datavizSelectionTimer);
  datavizSelectionTimer = setTimeout(window.dataviz.applySelections, 70);
};
const datavizEscape = value => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
const syncPortableChoices = control => {
  const selector = control.querySelector('.dv-selector');
  const input = selector?.querySelector('select');
  if (!input) return;
  if (selector.dataset.selectorTemplate === 'cascader') {
    selector._syncCascader?.();
    return;
  }
  const selected = new Set(Array.from(input.selectedOptions).map(option => option.value));
  const choiceButtons = Array.from(control.querySelectorAll('[data-selection-choice]'));
  const showUnavailable = selector.dataset.showUnavailable === 'true';
  const query = (selector.querySelector('[data-selector-search]')?.value || '').trim().toLocaleLowerCase();
  let visible = 0;
  choiceButtons.forEach(button => {
    const option = Array.from(input.options).find(item => item.value === button.dataset.selectionChoice);
    const active = selected.has(button.dataset.selectionChoice) && !option?.disabled;
    const matches = !query || `${option?.textContent || ''} ${option?.value || ''}`.toLocaleLowerCase().includes(query);
    button.classList.toggle('is-selected', active);
    button.classList.toggle('is-unavailable', Boolean(option?.disabled));
    button.setAttribute('aria-pressed', String(active));
    button.disabled = Boolean(option?.disabled);
    button.hidden = !matches || (Boolean(option?.disabled) && !showUnavailable);
    button.title = option?.disabled ? 'Unavailable for the current upstream selection' : '';
    if (!button.hidden) visible += 1;
  });
  const all = control.querySelector('[data-selection-choice-all]');
  if (all) {
    const enabledButtons = choiceButtons.filter(button => !button.disabled && !button.hidden);
    const active = enabledButtons.length > 0 && enabledButtons.every(button => selected.has(button.dataset.selectionChoice));
    all.classList.toggle('is-selected', active);
    all.setAttribute('aria-pressed', String(active));
    all.disabled = enabledButtons.length === 0;
  }
  const available = Array.from(input.options).filter(option => !option.disabled);
  const selectedAvailable = available.filter(option => option.selected);
  const summary = selector.querySelector('[data-selector-summary]');
  if (summary) summary.textContent = input.multiple
    ? (available.length && selectedAvailable.length === available.length ? `All (${available.length})` : `${selectedAvailable.length} selected`)
    : (selectedAvailable[0]?.textContent || 'Choose…');
  const count = selector.querySelector('[data-selector-count]');
  if (count) count.textContent = `${available.length} available`;
  const empty = selector.querySelector('[data-selector-empty]');
  if (empty) empty.hidden = visible > 0;
};
const datavizPositionFloatingPanel = (panel, trigger, preferredWidth = 560) => {
  if (!panel || !trigger || panel.hidden) return;
  const gutter = 12;
  const gap = 5;
  const viewportWidth = document.documentElement.clientWidth;
  const viewportHeight = document.documentElement.clientHeight;
  const triggerRect = trigger.getBoundingClientRect();
  const width = Math.max(1, Math.min(preferredWidth, viewportWidth - gutter * 2));
  panel.style.width = `${width}px`;
  panel.style.right = 'auto';
  panel.style.left = '0px';
  panel.style.top = '0px';
  const measuredHeight = Math.min(panel.scrollHeight, viewportHeight - gutter * 2);
  const left = Math.max(gutter, Math.min(triggerRect.right - width, viewportWidth - width - gutter));
  const roomBelow = viewportHeight - triggerRect.bottom - gutter;
  const roomAbove = triggerRect.top - gutter;
  const openAbove = measuredHeight > roomBelow && roomAbove > roomBelow;
  const top = openAbove
    ? Math.max(gutter, triggerRect.top - measuredHeight - gap)
    : Math.min(triggerRect.bottom + gap, viewportHeight - measuredHeight - gutter);
  panel.style.left = `${left}px`;
  panel.style.top = `${Math.max(gutter, top)}px`;
  panel.dataset.floatingPlacement = openAbove ? 'top' : 'bottom';
};
const initializeCascader = (control, selector, input, mount) => {
  const levels = JSON.parse(selector.dataset.cascaderLevels || '[]');
  const viewId = selector.dataset.cascaderView;
  const separator = selector.dataset.pathSeparator || ' / ';
  const selectionKey = control.dataset.selectionKey;
  let activePath = [];
  mount.innerHTML = `<div class="dv-cascader" data-selector-picker><button type="button" class="dv-choice-trigger" data-selector-trigger aria-expanded="false"><span data-selector-summary></span><i>⌄</i></button><div class="dv-cascader-panel" data-selector-panel hidden><input type="search" class="dv-choice-search" data-cascader-search placeholder="${datavizEscape(selector.dataset.searchPlaceholder || 'Search paths…')}"><div class="dv-cascader-columns" data-cascader-columns></div><div class="dv-choice-empty" data-selector-empty hidden>${datavizEscape(selector.dataset.emptyText || 'No matching paths')}</div><footer><button type="button" data-cascader-clear>Clear selection</button><small data-selector-count></small></footer></div></div>`;
  const panel = mount.querySelector('[data-selector-panel]');
  const trigger = mount.querySelector('[data-selector-trigger]');
  const search = mount.querySelector('[data-cascader-search]');
  const columns = mount.querySelector('[data-cascader-columns]');
  const empty = mount.querySelector('[data-selector-empty]');
  const summary = mount.querySelector('[data-selector-summary]');
  const count = mount.querySelector('[data-selector-count]');
  const availablePaths = () => {
    const contract = window.dataviz.portable?.selection_contract?.[viewId] || [];
    const otherSelections = contract.filter(item => item.key !== selectionKey);
    const rows = (window.dataviz.portable?.view_sources?.[viewId] || []).flatMap(
      sourceId => window.dataviz.portable?.sources?.[sourceId] || []
    ).filter(row => otherSelections.every(item =>
      datavizSelectionMatches(row, item, window.dataviz.selections[item.key])
    ));
    const unique = new Map();
    rows.forEach(row => {
      const path = levels.map(level => row[level.field]);
      if (path.some(value => value == null)) return;
      unique.set(JSON.stringify(path), path);
    });
    return [...unique.values()];
  };
  const selectedValues = () => new Set(Array.from(input.selectedOptions).map(option => option.value));
  const choose = path => {
    const value = JSON.stringify(path);
    const option = Array.from(input.options).find(item => item.value === value);
    if (!option) return;
    option.selected = input.multiple ? !option.selected : true;
    render(false);
    input.dispatchEvent(new Event('change', {bubbles: true}));
    if (!input.multiple) panel.hidden = true;
  };
  const pathButton = (path, depth, leaf, selected) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `dv-cascader-option${selected ? ' is-selected' : ''}`;
    button.innerHTML = `<span>${datavizEscape(leaf ? path.join(separator) : path[depth])}</span><i>${leaf ? (selected ? '✓' : '') : '›'}</i>`;
    button.addEventListener('click', () => {
      if (leaf) choose(path);
      else {
        activePath = path.slice(0, depth + 1);
        render(false);
      }
    });
    return button;
  };
  function render(rebuild = true) {
    let paths = availablePaths();
    const previous = input.options.length
      ? selectedValues()
      : new Set((window.dataviz.selections[selectionKey] || []).map(path => JSON.stringify(path)));
    if (rebuild) {
      input.replaceChildren(...paths.map(path => {
        const option = document.createElement('option');
        option.value = JSON.stringify(path);
        option.textContent = path.join(separator);
        option.selected = previous.has(option.value);
        return option;
      }));
    }
    const selected = selectedValues();
    // Selection state and navigation state are intentionally independent.
    // Seed an unopened picker from a selected path, but never pull the user
    // back to that path while they browse another branch for multi-selection.
    if (!activePath.length && selected.size) activePath = JSON.parse([...selected][0]);
    const normalizedPath = [];
    for (let depth = 0; depth < levels.length; depth += 1) {
      const candidates = paths.filter(path => normalizedPath.every(
        (value, index) => String(path[index]) === String(value)
      ));
      const values = [...new Set(candidates.map(path => String(path[depth])))];
      const current = activePath[depth] == null ? null : String(activePath[depth]);
      if (current != null && values.includes(current)) normalizedPath.push(activePath[depth]);
      else if (values.length === 1) normalizedPath.push(candidates[0][depth]);
      else break;
    }
    activePath = normalizedPath;
    const query = search.value.trim().toLocaleLowerCase();
    columns.replaceChildren();
    let rendered = 0;
    if (query) {
      const results = document.createElement('div');
      results.className = 'dv-cascader-results';
      paths.filter(path => path.join(separator).toLocaleLowerCase().includes(query)).forEach(path => {
        results.append(pathButton(path, levels.length - 1, true, selected.has(JSON.stringify(path))));
        rendered += 1;
      });
      columns.append(results);
    } else {
      for (let depth = 0; depth < levels.length; depth += 1) {
        if (depth > 0 && activePath.length < depth) break;
        const prefix = activePath.slice(0, depth);
        const candidates = paths.filter(path => prefix.every((value, index) => String(path[index]) === String(value)));
        const values = [...new Map(candidates.map(path => [String(path[depth]), path])).values()];
        if (!values.length) break;
        const column = document.createElement('div');
        column.className = 'dv-cascader-column';
        column.dataset.level = levels[depth]?.label || levels[depth]?.field || String(depth + 1);
        values.forEach(path => {
          const leaf = depth === levels.length - 1;
          const button = pathButton(path, depth, leaf, leaf && selected.has(JSON.stringify(path)));
          if (!leaf && String(activePath[depth]) === String(path[depth])) button.classList.add('is-active');
          column.append(button);
          rendered += 1;
        });
        columns.append(column);
      }
    }
    empty.hidden = rendered > 0;
    summary.textContent = selected.size
      ? `${selected.size} selected`
      : (selector.dataset.placeholder || 'All paths');
    count.textContent = `${paths.length} available`;
    if (!panel.hidden) requestAnimationFrame(() => datavizPositionFloatingPanel(panel, trigger));
  }
  trigger.addEventListener('click', () => {
    document.querySelectorAll('[data-selector-panel]:not([hidden])').forEach(item => { if (item !== panel) item.hidden = true; });
    panel.hidden = !panel.hidden;
    trigger.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) {
      datavizPositionFloatingPanel(panel, trigger);
      search.focus();
    }
  });
  const reposition = () => datavizPositionFloatingPanel(panel, trigger);
  window.addEventListener('resize', reposition);
  window.addEventListener('scroll', reposition, true);
  search.addEventListener('input', () => render(false));
  mount.querySelector('[data-cascader-clear]').addEventListener('click', () => {
    Array.from(input.options).forEach(option => { option.selected = false; });
    render(false);
    input.dispatchEvent(new Event('change', {bubbles: true}));
  });
  selector._syncCascader = () => render(true);
  render(true);
};
document.querySelectorAll('[data-selection-key]').forEach(control => {
  const selector = control.querySelector('.dv-selector');
  const input = selector?.querySelector('select');
  if (!input) return;
  const mount = selector.querySelector('[data-selector-mount]');
  const template = selector.dataset.selectorTemplate;
  const choiceMarkup = () => Array.from(input.options).map(option =>
    `<button type="button" class="${template === 'chips' ? 'dv-choice-chip' : 'dv-choice-option'}" data-selection-choice="${datavizEscape(option.value)}"><span>${datavizEscape(option.textContent)}</span><i>✓</i></button>`
  ).join('');
  if (template === 'cascader') {
    initializeCascader(control, selector, input, mount);
  } else if (template === 'chips' && input.multiple) {
    mount.innerHTML = `<div class="dv-choice-control"><button type="button" class="dv-choice-chip dv-choice-chip--all" data-selection-choice-all>All</button>${choiceMarkup()}</div>`;
  } else {
    const searchable = template === 'searchable';
    mount.innerHTML = `<div class="dv-choice-picker" data-selector-picker><button type="button" class="dv-choice-trigger" data-selector-trigger aria-expanded="false"><span data-selector-summary></span><i>⌄</i></button><div class="dv-choice-panel" data-selector-panel hidden>${searchable ? `<input type="search" class="dv-choice-search" data-selector-search placeholder="${datavizEscape(selector.dataset.searchPlaceholder || 'Search options…')}">` : ''}<div class="dv-choice-options">${choiceMarkup()}</div><div class="dv-choice-empty" data-selector-empty hidden>${datavizEscape(selector.dataset.emptyText || 'No matching options')}</div>${input.multiple ? '<footer><button type="button" data-selection-choice-all>Select all available</button><small data-selector-count></small></footer>' : ''}</div></div>`;
  }
  if (template !== 'cascader') {
    control.querySelector('[data-selector-trigger]')?.addEventListener('click', event => {
    const panel = control.querySelector('[data-selector-panel]');
    const trigger = event.currentTarget;
    document.querySelectorAll('[data-selector-panel]:not([hidden])').forEach(item => { if (item !== panel) item.hidden = true; });
    panel.hidden = !panel.hidden;
    trigger.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) panel.querySelector('[data-selector-search]')?.focus();
    });
    control.querySelector('[data-selector-search]')?.addEventListener('input', () => syncPortableChoices(control));
    control.querySelector('[data-selection-choice-all]')?.addEventListener('click', () => {
    Array.from(input.options).forEach(option => { option.selected = !option.disabled; });
    syncPortableChoices(control);
    input.dispatchEvent(new Event('change', {bubbles: true}));
    });
    control.querySelectorAll('[data-selection-choice]').forEach(button => button.addEventListener('click', () => {
    const option = Array.from(input.options).find(item => item.value === button.dataset.selectionChoice);
    if (!option || option.disabled) return;
    if (input.multiple) option.selected = !option.selected;
    else {
      Array.from(input.options).forEach(item => { item.selected = item === option; });
      const panel = control.querySelector('[data-selector-panel]');
      if (panel) panel.hidden = true;
    }
    syncPortableChoices(control);
    input.dispatchEvent(new Event('change', {bubbles: true}));
    }));
  }
  syncPortableChoices(control);
});
document.querySelectorAll('[data-selection-input]').forEach(input => {
  input.addEventListener('input', scheduleDatavizSelection);
  input.addEventListener('change', scheduleDatavizSelection);
});
const closeRuntimePopovers = except => {
  document.querySelectorAll('[data-runtime-popover][open]').forEach(details => {
    if (details !== except) details.open = false;
  });
};
const closeContextSelectionPopovers = except => {
  document.querySelectorAll('.dv-context-selections[open]').forEach(details => {
    if (details !== except) details.open = false;
  });
};
document.querySelectorAll('[data-runtime-popover]').forEach(details => {
  details.addEventListener('toggle', () => {
    if (details.open) closeRuntimePopovers(details);
  });
});
document.querySelectorAll('.dv-context-selections').forEach(details => {
  details.addEventListener('toggle', () => {
    if (details.open) closeContextSelectionPopovers(details);
  });
});
document.addEventListener('click', event => {
  const eventPath = event.composedPath();
  const pathContains = selector => eventPath.some(node => node instanceof Element && node.matches(selector));
  if (!pathContains('[data-runtime-popover]')) closeRuntimePopovers();
  if (!pathContains('.dv-context-selections')) closeContextSelectionPopovers();
  if (!pathContains('[data-selector-picker]')) {
    document.querySelectorAll('[data-selector-panel]:not([hidden])').forEach(panel => { panel.hidden = true; });
    document.querySelectorAll('[data-selector-trigger]').forEach(trigger => trigger.setAttribute('aria-expanded', 'false'));
  }
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  const open = document.querySelector('[data-runtime-popover][open], .dv-context-selections[open]');
  closeRuntimePopovers();
  closeContextSelectionPopovers();
  document.querySelectorAll('[data-selector-panel]:not([hidden])').forEach(panel => { panel.hidden = true; });
  open?.querySelector('summary')?.focus();
});
window.dispatchEvent(new CustomEvent('dataviz:ready', {detail: window.dataviz}));
"""
