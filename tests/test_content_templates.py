from __future__ import annotations

from pathlib import Path
import shutil

import pytest
import yaml

from dataviz.content_templates import (
    build_content_bindings,
    format_parameter_value,
    format_control_value,
    inspect_content_template,
    interpolate_dashboard_content,
)
from dataviz.execution import Executor
from dataviz.rendering import CanvasRenderer
from dataviz.workspace import load_workspace, validate_workspace
from dataviz.workspace.models import (
    DashboardDefinition,
    QueryParameterDefinition,
    ControlDefinition,
)


ROOT = Path(__file__).resolve().parents[1]
MINIMAL = ROOT / "examples" / "minimal-workspace"


@pytest.fixture(scope="module", autouse=True)
def _isolate_repository_workspaces(isolated_workspace):
    global MINIMAL
    MINIMAL = isolated_workspace(MINIMAL)


def test_parameter_content_templates_format_human_facing_values():
    period = QueryParameterDefinition(id="period", type="range_input", value_type="date")
    stores = QueryParameterDefinition.model_validate(
        {
            "id": "stores",
            "type": "multiple_select", "value_type": "integer",
            "options": {
                "mode": "static",
                "choices": [
                    {"label": "上海仓", "value": 5740},
                    {"label": "杭州仓", "value": 5750},
                ],
            },
        }
    )

    assert format_parameter_value(["2026-08-09", "2026-08-22"], period) == (
        "2026-08-09 至 2026-08-22"
    )
    assert format_parameter_value("2026-08-09,2026-08-22", period) == (
        "2026-08-09 至 2026-08-22"
    )
    assert format_parameter_value([5740, 5750], stores) == "上海仓、杭州仓"
    inspection = inspect_content_template("仓 {{ parameters.store_id }}")
    assert inspection.query_parameters == {"store_id"}
    assert inspect_content_template("{{ selections.region }}").errors


def test_selection_content_uses_choice_labels_and_compiles_browser_binding():
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v11",
            "id": "hourly-sales",
            "title": "小时销售",
            "controls": [
                {
                    "id": "region",

                    "type": "single_select", "value_type": "text",
                    "initial": {"mode": "value", "value": "south"},
                    "options": {
                        "mode": "static",
                        "choices": [{"label": "华南", "value": "south"}],
                    },
                }
            ],
            "sections": [
                {
                    "id": "night_analysis",
                    "title": "{{ controls.section.night_analysis.dow }}各小时销售分析",
                    "description": "{{ controls.dashboard.region }}区域",
                    "controls": [
                        {
                            "id": "dow",

                            "type": "single_select", "value_type": "integer",
                            "initial": {"mode": "value", "value": 5},
                            "options": {
                                "mode": "static",
                                "choices": [
                                    {"label": "周四", "value": 4},
                                    {"label": "周五", "value": 5},
                                ],
                            },
                        }
                    ],
                    "views": ["detail"],
                }
            ],
            "views": [
                {
                    "id": "detail",
                    "title": "{{ controls.section.night_analysis.dow }}明细",
                    "description": "统计{{ controls.section.night_analysis.dow }}的数据",
                    "template": "table",
                    "input": "source:hourly/main",
                }
            ],
        }
    )
    control_state = {
        "section:night_analysis/dow": {
            "value": 4,
            "revision": 1,
            "intent": "explicit",
        }
    }
    resolved = interpolate_dashboard_content(definition, {}, control_state)
    bindings = build_content_bindings(definition, {})

    assert resolved.sections[0].title == "周四各小时销售分析"
    assert resolved.sections[0].description == "华南区域"
    assert resolved.views[0].title == "周四明细"
    assert resolved.views[0].description == "统计周四的数据"
    binding = bindings["sections.night_analysis.title"]
    assert binding["template"] == (
        "{{ controls.section.night_analysis.dow }}各小时销售分析"
    )
    assert binding["references"][0]["key"] == "section:night_analysis/dow"
    assert binding["target"] == {
        "scope": "section",
        "owner_id": "night_analysis",
        "property": "title",
    }
    selection = ControlDefinition.model_validate(
        {
            "id": "dow",

                "type": "multiple_select", "value_type": "integer",
            "options": {
                "mode": "static",
                "choices": [
                    {"label": "周四", "value": 4},
                    {"label": "周五", "value": 5},
                ],
            },
        }
    )
    assert format_control_value([4, 5], selection) == "全部"


def test_interpolation_is_limited_to_declarative_content_fields():
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v11",
            "id": "hourly-sales",
            "title": "商品 {{ parameters.product_id }}",
            "subtitle": "{{ parameters.period }}",
            "description": "仓 {{ parameters.store_id }}",
            "assumptions": ["当前商品：{{ parameters.product_id }}"],
            "query_parameters": [
                {"id": "store_id", "type": "single_input", "value_type": "integer", "default": 5740},
                {"id": "product_id", "type": "single_input", "value_type": "text", "default": "980464683"},
                {"id": "period", "type": "range_input", "value_type": "date", "default": []},
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
        query_parameters={"min_query_revenue": 150000},
        refresh=True,
    )
    rendered = CanvasRenderer(workspace).render(dashboard, result, asset_mode="inline")

    assert '<p class="dv-subtitle">当前取数下限：150000</p>' in rendered
    assert "{{ parameters.min_query_revenue }}" not in rendered
    assert '"query_parameters": {"min_query_revenue": 150000}' in rendered


def test_default_view_shell_renders_static_and_dynamic_descriptions(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL, root, ignore=shutil.ignore_patterns(".dataviz", "dist"))
    dashboard_path = root / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    total = next(item for item in definition["views"] if item["id"] == "total-revenue")
    comparison = next(
        item for item in definition["views"] if item["id"] == "region-comparison"
    )
    total["description"] = "汇总当前样本的收入。"
    comparison["description"] = "当前区域：{{ controls.dashboard.region }}"
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales-overview")
    result = Executor(workspace).run("sales-overview", refresh=True)
    rendered = CanvasRenderer(workspace).render(dashboard, result, asset_mode="inline")

    assert '<div class="dv-view-heading">' in rendered
    assert (
        '<p class="dv-view-description">汇总当前样本的收入。</p>'
        in rendered
    )
    assert (
        '<p class="dv-view-description" '
        'data-dv-content-field="views.region-comparison.description">'
        '当前区域：全部</p>'
    ) in rendered


def test_custom_canvas_content_helper_keeps_selection_binding(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL, root, ignore=shutil.ignore_patterns(".dataviz", "dist"))
    dashboard_root = root / "dashboards" / "sales-overview"
    dashboard_path = dashboard_root / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    trend = next(item for item in definition["sections"] if item["id"] == "trend")
    trend["title"] = "{{ controls.section.trend.dow }}趋势"
    trend["controls"] = [
        {
            "id": "dow",

            "field": "region",
            "type": "single_select", "value_type": "text",
            "initial": {"mode": "value", "value": "华东"},
            "options": {
                "mode": "static",
                "choices": [{"label": "周五", "value": "华东"}],
            },
        }
    ]
    definition["canvas"] = {"template": "canvas/content.html"}
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    canvas_path = dashboard_root / "canvas" / "content.html"
    canvas_path.parent.mkdir(parents=True)
    canvas_path.write_text(
        '<h2>{{ content("sections.trend.title") }}</h2>{{ view("revenue-trend") }}',
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    dashboard = workspace.dashboard("sales-overview")
    result = Executor(workspace).run("sales-overview", refresh=True)
    rendered = CanvasRenderer(workspace).render(dashboard, result, asset_mode="inline")

    assert (
        '<h2><span data-dv-content-field="sections.trend.title">'
        "周五趋势</span></h2>"
    ) in rendered


def test_validate_rejects_unknown_and_executable_content_expressions(tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(MINIMAL, root, ignore=shutil.ignore_patterns(".dataviz", "dist"))
    dashboard_path = root / "dashboards" / "sales-overview" / "dashboard.yaml"
    definition = yaml.safe_load(dashboard_path.read_text(encoding="utf-8"))
    definition["title"] = "{{ parameters.deleted_id }}"
    definition["subtitle"] = "{{ parameters.min_query_revenue + 1 }}"
    definition["description"] = "{{ controls.section.trend.dow }}"
    definition["sections"][1]["controls"] = [
        {
            "id": "dow",

            "type": "single_select", "value_type": "integer",
            "options": {
                "mode": "static",
                "choices": [{"label": "周五", "value": 5}],
            },
        }
    ]
    definition["views"][0]["description"] = (
        "{{ controls.section.missing.dow }}"
    )
    dashboard_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    diagnostics = validate_workspace(load_workspace(root))

    assert any(item.code == "content_parameter_unknown" for item in diagnostics)
    assert any(item.code == "content_template_invalid" for item in diagnostics)
    assert any(item.code == "content_control_out_of_scope" for item in diagnostics)
    assert any(item.code == "content_control_unknown" for item in diagnostics)
