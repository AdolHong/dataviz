from __future__ import annotations

from pathlib import Path
import shutil

import yaml

from dataviz.content_templates import (
    format_parameter_value,
    inspect_parameter_template,
    interpolate_dashboard_content,
)
from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.models import DashboardDefinition, ParameterDefinition


ROOT = Path(__file__).resolve().parents[1]
MINIMAL = ROOT / "examples" / "minimal-workspace"


def test_parameter_content_templates_format_human_facing_values():
    period = ParameterDefinition(id="period", type="date_range")
    stores = ParameterDefinition.model_validate(
        {
            "id": "stores",
            "type": "multi_select",
            "choices": [
                {"label": "上海仓", "value": 5740},
                {"label": "杭州仓", "value": 5750},
            ],
        }
    )

    assert format_parameter_value(["2026-08-09", "2026-08-22"], period) == (
        "2026-08-09 至 2026-08-22"
    )
    assert format_parameter_value("2026-08-09,2026-08-22", period) == (
        "2026-08-09 至 2026-08-22"
    )
    assert format_parameter_value([5740, 5750], stores) == "上海仓、杭州仓"
    assert inspect_parameter_template("仓 {{ parameters.store_id }}")[0] == {"store_id"}
    assert inspect_parameter_template("{{ selections.region }}")[1]


def test_interpolation_is_limited_to_declarative_content_fields():
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v1",
            "id": "hourly-sales",
            "title": "商品 {{ parameters.product_id }}",
            "subtitle": "{{ parameters.period }}",
            "description": "仓 {{ parameters.store_id }}",
            "assumptions": ["当前商品：{{ parameters.product_id }}"],
            "query_parameters": [
                {"id": "store_id", "default": 5740},
                {"id": "product_id", "default": "980464683"},
                {"id": "period", "type": "date_range", "default": []},
            ],
            "sections": [
                {
                    "id": "overview",
                    "title": "{{ parameters.store_id }} · 概览",
                    "description": "期间 {{ parameters.period }}",
                }
            ],
            "views": [
                {
                    "id": "note",
                    "title": "商品 {{ parameters.product_id }}",
                    "description": "仓 {{ parameters.store_id }}",
                    "template": "markdown",
                    "text": "分析对象：{{ parameters.product_id }}",
                }
            ],
        }
    )
    resolved = interpolate_dashboard_content(
        definition,
        {
            "store_id": 5740,
            "product_id": "980464683",
            "period": ["2026-08-09", "2026-08-22"],
        },
    )

    assert resolved.title == "商品 980464683"
    assert resolved.subtitle == "2026-08-09 至 2026-08-22"
    assert resolved.description == "仓 5740"
    assert resolved.assumptions == ["当前商品：980464683"]
    assert resolved.sections[0].title == "5740 · 概览"
    assert resolved.views[0].text == "分析对象：980464683"


def test_default_renderer_uses_committed_parameters_in_server_and_export_content():
    workspace = load_workspace(MINIMAL)
    dashboard = workspace.dashboard("sales-overview")
    result = Executor(workspace).run(
        "sales-overview",
        params={"min_query_revenue": 150000},
        refresh=True,
    )
    rendered = CanvasRenderer(workspace).render(dashboard, result, asset_mode="inline")

    assert '<p class="dv-subtitle">当前取数下限：150000</p>' in rendered
    assert "{{ parameters.min_query_revenue }}" not in rendered
    assert '"parameters": {"min_query_revenue": 150000}' in rendered


def test_validate_rejects_unknown_and_executable_content_expressions(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL, root, ignore=shutil.ignore_patterns(".dataviz", "dist"))
    dashboard_path = root / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["title"] = "{{ parameters.deleted_id }}"
    definition["subtitle"] = "{{ parameters.min_query_revenue + 1 }}"
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    diagnostics = validate_workspace(load_workspace(root))

    assert any(item.code == "content_parameter_unknown" for item in diagnostics)
    assert any(item.code == "content_template_invalid" for item in diagnostics)
