from __future__ import annotations

import base64
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import markdown as markdown_lib
from jinja2 import Environment, StrictUndefined
from markupsafe import Markup

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.errors import ExecutionFailure
from dataviz.execution.results import RunResult
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
        widget_html = {
            widget_id: self._widget_html(widget_id, artifacts, store, chart_mode, image_format)
            for widget_id, artifacts in result.outputs.items()
        }

        def widget(widget_id: str) -> str:
            return widget_html.get(
                widget_id,
                f'<section class="dv-widget dv-widget--missing"><p>Widget “{html.escape(widget_id)}” has no output.</p></section>',
            )

        canvas = dashboard.definition.canvas
        if canvas.template:
            template_text = (dashboard.root / canvas.template).read_text(encoding="utf-8")
            environment = Environment(autoescape=True, undefined=StrictUndefined)
            template = environment.from_string(template_text)
            body = template.render(
                workspace=self.workspace.definition,
                dashboard=dashboard.definition,
                parameters=result.parameters,
                filters=result.filters,
                run=result,
                widget=lambda value: Markup(widget(value)),
                widgets=widget_html,
            )
        else:
            body = self._default_body(dashboard, widget_html, result.parameters, result.filters)

        base_style = ""
        if canvas.use_default_style:
            base_style = (PACKAGE_ROOT / "server" / "static" / "canvas.css").read_text(encoding="utf-8")
        custom_style = (
            (dashboard.root / canvas.style).read_text(encoding="utf-8") if canvas.style else ""
        )
        custom_script = (
            (dashboard.root / canvas.script).read_text(encoding="utf-8") if canvas.script else ""
        )
        plotly_script = self._plotly_script(asset_mode) if "plotly-json" in self._formats(result) and chart_mode == "interactive" else ""
        echarts_script = self._echarts_script(asset_mode) if "echarts-json" in self._formats(result) else ""
        runtime = self._runtime_script(result)
        document_title = title or dashboard.definition.title
        meta = {
            "run_id": result.run_id,
            "status": result.status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parameters": result.parameters,
            "filters": result.filters,
        }
        return f"""<!doctype html>
<html lang="{html.escape(self.workspace.definition.context.language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(document_title)}</title>
  <style>{base_style}\n{custom_style}</style>
  {plotly_script}
  {echarts_script}
</head>
<body>
  <main class="dv-canvas" data-dashboard="{html.escape(dashboard.definition.id)}">
    {body}
  </main>
  <script>window.dataviz = {json.dumps(meta, ensure_ascii=False, default=str)};</script>
  <script>{runtime}</script>
  <script>{custom_script}</script>
</body>
</html>"""

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
        filters: dict[str, Any],
    ) -> str:
        definition = dashboard.definition
        assumptions = "".join(f"<li>{html.escape(value)}</li>" for value in definition.assumptions)
        items = []
        by_id = {item.widget: item for item in definition.layout.items}
        for widget_id in definition.widgets:
            loaded_id = Path(widget_id).parent.name
            widget_definition = next(
                (value[1] for value in dashboard.widgets.values() if value[1].id == loaded_id), None
            )
            actual_id = widget_definition.id if widget_definition else loaded_id
            layout = by_id.get(actual_id)
            if not layout:
                continue
            style = (
                f"grid-column:{layout.x + 1} / span {layout.width};"
                f"grid-row:{layout.y + 1} / span {layout.height};"
            )
            items.append(
                f'<div class="dv-grid-item {html.escape(layout.css_class)}" style="{style}">{widgets.get(actual_id, "")}</div>'
            )
        if not items:
            items = [f'<div class="dv-grid-item">{value}</div>' for value in widgets.values()]
        grid_style = (
            f"--dv-columns:{definition.layout.columns};"
            f"--dv-row-height:{definition.layout.row_height}px;"
            f"--dv-gap:{definition.layout.gap}px;"
        )
        return f"""
<header class="dv-report-header">
  <div>
    <p class="dv-eyebrow">ANALYSIS CANVAS · {html.escape(definition.id.upper())}</p>
    <h1>{html.escape(definition.title)}</h1>
    <p class="dv-deck">{html.escape(definition.description)}</p>
  </div>
  <aside class="dv-report-note"><strong>Run inputs</strong><pre>{html.escape(json.dumps({"parameters": parameters, "filters": filters}, ensure_ascii=False, indent=2, default=str))}</pre></aside>
</header>
{f'<details class="dv-assumptions"><summary>口径与假设</summary><ul>{assumptions}</ul></details>' if assumptions else ''}
<section class="dv-grid" style="{grid_style}">{''.join(items)}</section>
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
            columns = [item["name"] for item in artifact.schema_ or []]
            header = "".join(f"<th>{html.escape(value)}</th>" for value in columns)
            rows = "".join(
                "<tr>" + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns) + "</tr>"
                for row in (artifact.preview or [])[:100]
            )
            count = artifact.metadata.get("row_count", len(artifact.preview or []))
            return f'<div class="dv-table-meta">{count:,} rows · showing first {min(count, 100)}</div><div class="dv-table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table></div>'
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
window.dispatchEvent(new CustomEvent('dataviz:ready', {detail: window.dataviz}));
"""
