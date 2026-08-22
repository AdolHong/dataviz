from __future__ import annotations

from typing import Any


DOC_ALIASES = {
    "start": "quickstart",
    "chart": "charts",
    "view": "charts",
    "source": "sources",
    "selection": "selections",
    "filter": "selections",
    "layout": "presentation",
    "style": "presentation",
    "repeat": "repeated-views",
    "multiples": "repeated-views",
    "gallery": "repeated-views",
    "error": "troubleshooting",
    "debug": "troubleshooting",
}


DOC_TOPICS: dict[str, dict[str, Any]] = {
    "quickstart": {
        "summary": "AI 从空环境到第一个可验证 HTML 报告的最短路径。",
        "goal": "先证明数据和声明式 View 正确，再启动 Server 或写自定义样式。",
        "workflow": [
            "dataviz docs workflow",
            "dataviz list <workspace>",
            "dataviz context <workspace> <dashboard-id> --format json",
            "dataviz validate <workspace>",
            "dataviz query <workspace> <dashboard-id> --source <source-id> --format json",
            "dataviz report <workspace> <dashboard-id> --output <workspace>/dist/report.html",
            "dataviz serve <workspace> --port 8080",
        ],
        "rules": [
            "不要从自定义 HTML/CSS/JS 开始；先用默认 Renderer。",
            "不要把账号密码写进 Dashboard；只引用 Workspace Adapter 名称。",
            "Query Parameter 会重新取数；Selection 只筛选浏览器中已有数据。",
            "每次只解决一层：Adapter → Source → View → Selection → Presentation。",
        ],
        "success": [
            "validate 返回 status=valid。",
            "query 返回预期 schema、row_count 和 preview。",
            "report 返回 status=success，且 HTML 与 manifest 同时生成。",
        ],
        "related": ["workflow", "dashboard", "sources", "charts", "troubleshooting"],
    },
    "workflow": {
        "summary": "降低反复试错的固定开发顺序与每一步停止条件。",
        "goal": "把错误限制在最小边界，不在数据错误时调图表样式。",
        "steps": [
            {"stage": "1. Discover", "command": "dataviz list <workspace>", "stop_when": "确认 dashboard id、Canvas Name、Source id。"},
            {"stage": "2. Read", "command": "dataviz context <workspace> <dashboard-id> --format json", "stop_when": "确认 Adapter、参数、字段绑定和有效 Presentation。"},
            {"stage": "3. Validate", "command": "dataviz validate <workspace>", "stop_when": "没有 error 级诊断。"},
            {"stage": "4. Query", "command": "dataviz query <workspace> <dashboard-id> --source <source-id> --format json", "stop_when": "preview 中真实存在 View 要使用的字段和数值。"},
            {"stage": "5. Render", "command": "dataviz report <workspace> <dashboard-id> --output <workspace>/dist/check.html", "stop_when": "默认 Renderer 成功导出。"},
            {"stage": "6. Present", "command": "编辑 presentation.yaml 后重新 validate/report", "stop_when": "布局和样式改变但查询结果不变。"},
            {"stage": "7. Interact", "command": "dataviz serve <workspace>", "stop_when": "Parameter 重新查询，Selection 局部重绘，行为符合预期。"},
        ],
        "do_not": [
            "不要同时修改 SQL、字段名、图表类型和 CSS。",
            "不要在 query 尚未成功时启动浏览器调试图表。",
            "不要为普通图表创建自定义 Canvas；先读取 dataviz docs charts。",
        ],
        "related": ["quickstart", "troubleshooting"],
    },
    "dashboard": {
        "summary": "Dashboard 文件夹、稳定 ID 与最小 dashboard.yaml 契约。",
        "identity": {
            "canvas_name": "文件夹末级名称；侧栏、复制、移动和分享使用。",
            "id": "稳定程序身份；CLI、API、DAG 和运行状态使用。",
            "title_subtitle_description": "页面内容；title 可省略并回退到 Canvas Name。",
        },
        "minimal_example": """schema: dataviz/dashboard/v1
kind: dashboard
id: sales-overview
title: 销售概览
subtitle: 华东经营专题
description: 收入趋势与明细分析
adapters: {warehouse: team-duckdb}
sources:
  - {id: sales, type: sql, adapter: warehouse, query: sources/sales.sql}
views:
  - {id: trend, title: 收入趋势, source: sales, template: line, x: date, y: revenue}
sections:
  - {id: overview, title: 概览, template: single, views: [trend]}
""",
        "rules": [
            "所有 Parameter、Source、Selection、Section、View 都使用稳定且唯一的 id。",
            "极简看板不需要 presentation.yaml、CSS、JS 或 Canvas 文件。",
            "逻辑层只声明数据语义和最小阅读顺序。",
        ],
        "related": ["sources", "charts", "selections", "presentation"],
    },
    "sources": {
        "summary": "File、DuckDB、MySQL、StarRocks 与 Python Source 的配置和验证顺序。",
        "source_types": {
            "file": "Dashboard 自带文件，或通过 files Adapter 读取 Workspace 授权目录。",
            "sql": "通过 Adapter 执行 SQL；DuckDB、MySQL、StarRocks 均使用此类型。",
            "python": "仅用于取数或服务端计算；浏览器 View 渲染仍由 JS Runtime 完成。",
        },
        "examples": {
            "bundled_csv": "{id: orders, type: file, path: data/orders.csv, format: csv}",
            "duckdb_sql": "{id: sales, type: sql, adapter: warehouse, query: sources/sales.sql, params: [start_date]}",
            "python": "{id: forecast, type: python, path: sources/forecast.py, entrypoint: load, params: [horizon]}",
        },
        "verification": [
            "先运行 dataviz validate <workspace>。",
            "再运行 dataviz query <workspace> <dashboard-id> --source <source-id> --format json。",
            "检查 schema、row_count、preview 和 node.error；不要只看 status。",
            "SQL 参数必须在 Source params 中声明，并在 SQL 中使用 Runtime 支持的参数形式。",
        ],
        "related": ["adapters", "workflow", "troubleshooting"],
    },
    "adapters": {
        "summary": "把凭证留在 Workspace，把可分享 Dashboard 绑定到 Adapter 名称。",
        "rules": [
            "Dashboard 只写逻辑别名到实际 Adapter 的映射，例如 warehouse: team-starrocks。",
            "账号密码放入 auth/adapters.local.yaml 或环境变量，不提交 Git。",
            "同事复制 Dashboard 后，只需把 Adapter 名称改为其本地定义。",
            "MySQL 与 StarRocks 共用 MySQL wire protocol；DuckDB 使用本地数据库或内存连接。",
            "files Adapter 的 root 是访问边界，Source 不得用 .. 越界。",
        ],
        "checklist": [
            "Adapter 名称在 Workspace 中存在。",
            "驱动依赖已安装。",
            "环境变量在启动 dataviz 的同一 Shell 中可见。",
            "先用最小 SELECT 1 或小文件验证连接，再运行复杂查询。",
        ],
        "related": ["sources", "troubleshooting"],
    },
    "charts": {
        "summary": "Plotly/ECharts 声明式 View 配方、必填字段和最短排错路径。",
        "field_matrix": {
            "metric": {"required": ["source", "value"], "typical": "aggregate: sum|mean|min|max|count"},
            "line": {"required": ["source", "x", "y"], "optional": ["series", "aggregate", "engine"]},
            "bar": {"required": ["source", "x", "y"], "optional": ["series", "aggregate", "engine"]},
            "stacked-bar": {"required": ["source", "x", "y", "series"], "optional": ["aggregate", "engine"]},
            "pie": {"required": ["source", "label", "value"], "optional": ["aggregate", "engine"]},
            "scatter": {"required": ["source", "x", "y"], "optional": ["series", "color", "size", "engine"]},
            "heatmap": {"required": ["source", "x", "y", "z"], "optional": ["aggregate", "engine"]},
        },
        "minimal_examples": {
            "plotly_line": "{id: revenue-trend, source: sales, template: line, engine: plotly, x: date, y: revenue, series: region}",
            "echarts_bar": "{id: region-bars, source: sales, template: bar, engine: echarts, x: region, y: revenue, aggregate: sum}",
            "heatmap": "{id: matrix, source: sales, template: heatmap, engine: echarts, x: month, y: region, z: revenue, aggregate: sum}",
        },
        "preflight": [
            "query preview 中必须存在 source/x/y/z/value/label/series 对应字段，大小写完全一致。",
            "y、z、value、size 通常应为数值；日期和类别字段不要意外全为空。",
            "先去掉 series/color/size/options，只保留必填字段完成首屏渲染，再逐项加入。",
            "engine 只允许 plotly 或 echarts；普通图表不需要 Python 画图代码。",
            "validate 成功不代表数据类型正确；必须检查 query preview。",
        ],
        "failure_order": [
            "Unknown source/field → 修正 id 或列名。",
            "空图 → 检查 Query Parameter 和上游 Selection 后是否仍有行。",
            "数轴异常 → 检查数值列是否被读成字符串。",
            "只有导出失败 → 用默认 interactive 模式，确认 JS 资产和浏览器控制台。",
            "自定义样式失败 → 暂时移除 presentation/assets，证明默认 Renderer 正常。",
        ],
        "commands": [
            "dataviz components view.echarts-category",
            "dataviz templates",
            "dataviz query <workspace> <dashboard-id> --source <source-id> --format json",
            "dataviz report <workspace> <dashboard-id> --output <workspace>/dist/chart-check.html",
        ],
        "related": ["tables", "workflow", "troubleshooting"],
    },
    "tables": {
        "summary": "普通 Table 与 Perspective 的选择边界和最小配置。",
        "templates": {
            "table": "展示型明细表，样式容易定制；支持 columns、limit 和 options。",
            "perspective": "分析型表格，支持排序、筛选、分组、透视与图形探索。",
        },
        "examples": {
            "table": "{id: detail, title: 明细, source: sales, template: table, columns: [date, region, revenue], limit: 200}",
            "perspective": "{id: pivot, title: 透视分析, source: sales, template: perspective, columns: [region, revenue], config: {plugin: Datagrid, group_by: [region]}}",
        },
        "rules": [
            "需要品牌化样式或固定列展示时使用 table。",
            "需要用户现场分析和透视时使用 perspective。",
            "Perspective 样式由 Web Component 主导，不要依赖普通 Table CSS。",
        ],
        "related": ["charts", "presentation"],
    },
    "repeated-views": {
        "summary": "用一个 View 蓝图巡检全部分组，或只渲染用户搜索、级联选择的分组。",
        "templates": {
            "small-multiples": "按 repeat.by 展示全部分组；适合 100 家门店等全量巡检。",
            "selection-gallery": "空选择不渲染；搜索或级联多选后只创建选中分组的 View 实例。",
        },
        "minimal_example": """views:
  - {id: store-trend, source: sales, template: line, x: week, y: revenue}
sections:
  - id: stores
    title: Store performance
    template: small-multiples
    views: [store-trend]
    repeat:
      view: store-trend
      by: [store_id]
      title: "{store_name}"
      render: lazy
""",
        "selection_gallery": {
            "logic": "在 Section selections 中声明 multi_select；repeat.selection 引用其 id。",
            "flat": "Presentation 使用 selector.searchable；choices 为空时 Runtime 从 Dataset 建立选项。",
            "hierarchical": "Selection 声明 path_fields，Presentation 使用 selector.cascader。",
        },
        "rules": [
            "Repeat Section 当前只接受一个声明式 View 蓝图，不能复制 Source 查询。",
            "默认 lazy 使用 IntersectionObserver，只在接近视口时创建 Plotly/ECharts 实例。",
            "动态实例 id 从稳定 View id 和分组值派生，Presentation 仍只配置基础 View id。",
            "导出 HTML 保留全部 Dataset；导出时的 Selection 只是初始状态。",
            "Selection 只影响该 Section 时使用 Section Selection；需要影响全页时提升为 Dashboard Selection。",
        ],
        "commands": [
            "dataviz components section.small-multiples",
            "dataviz components section.selection-gallery",
            "dataviz serve examples/repeat-workspace",
            "dataviz report examples/repeat-workspace store-performance --output stores.html",
        ],
        "related": ["charts", "selections", "presentation"],
    },
    "selections": {
        "summary": "Query Parameter 与 Dashboard/Section/View Selection 的职责和级联。",
        "scopes": {
            "query_parameters": "服务端取数参数；修改后必须重新 Query。",
            "dashboard_selections": "浏览器端筛选全部 View，不重新查询。",
            "section_selections": "只影响 Section 内 View。",
            "view_selections": "只影响单个 View，不应重绘兄弟 View。",
        },
        "rules": [
            "Selection 默认是 include 语义；空选择表示当前可用全集。",
            "Dashboard → Section → View 默认级联，下游可用选项随上游数据收缩。",
            "层级值使用 path_fields 声明完整路径，并在 Presentation 选择 cascader。",
            "不要把 Selection 传给 dataviz query；CLI query 只接受 Query Parameter。",
        ],
        "related": ["presentation", "workflow"],
    },
    "presentation": {
        "summary": "用 presentation.yaml 调整布局和组件，而不改变分析逻辑。",
        "boundary": [
            "dashboard.yaml：Adapter、Source、参数、Selection 语义、View 数据绑定、最小顺序。",
            "presentation.yaml：Theme、布局、Section/View 容器、Selector 模板、CSS/JS 资源。",
            "Presentation 只能通过稳定 ID 引用逻辑对象。",
        ],
        "safe_order": [
            "默认 Renderer",
            "Section/View/Layout 模板",
            "Theme 和模板参数",
            "CSS token 与局部 class",
            "单 View 自定义 renderer",
            "完整自定义 Canvas（最后手段）",
        ],
        "commands": [
            "dataviz components",
            "dataviz components selector.cascader",
            "dataviz context <workspace> <dashboard-id> --format json",
        ],
        "related": ["dashboard", "selections", "charts"],
    },
    "troubleshooting": {
        "summary": "发生错误时的固定定位树，避免同时修改多层。",
        "triage": [
            {"symptom": "Workspace 无法加载", "action": "运行 validate；先修 YAML、路径和重复 ID。"},
            {"symptom": "Source 查询失败", "action": "单独运行 query；检查 Adapter、参数、SQL/Python traceback。"},
            {"symptom": "查询成功但图为空", "action": "检查 preview 字段、类型、空值以及 Selection 后行数。"},
            {"symptom": "一个 View 报错", "action": "缩减到模板必填字段，移除 options/series/color/size 后重试。"},
            {"symptom": "默认页面正常，自定义页面失败", "action": "问题位于 Presentation/CSS/JS；逐层恢复。"},
            {"symptom": "Server 正常，HTML 导出失败", "action": "检查 report manifest、JS 资产及是否依赖服务端重新查询。"},
        ],
        "evidence_to_collect": [
            "dataviz validate 的完整 JSON。",
            "dataviz query 的 status、schema、row_count、preview、node.error。",
            "失败 View 的完整 YAML 和 Source id。",
            "dataviz context --format json 中的 effective definition。",
            "导出 HTML 同目录的 .manifest.json。",
        ],
        "reset_to_known_good": [
            "保留一个 Source 和一个最小 View。",
            "暂时移除 presentation.yaml 或自定义 assets。",
            "使用 plain theme 和 overview layout。",
            "query 成功后 report；report 成功后再 serve。",
            "每次只恢复一个字段并重新验证。",
        ],
        "related": ["workflow", "sources", "charts"],
    },
}


def resolve_doc_topic(topic: str) -> str:
    normalized = topic.strip().lower()
    return DOC_ALIASES.get(normalized, normalized)


def docs_catalog(search: str | None = None) -> dict[str, dict[str, Any]]:
    if not search:
        return DOC_TOPICS
    needle = search.casefold()
    return {
        name: definition
        for name, definition in DOC_TOPICS.items()
        if needle in name.casefold() or needle in str(definition).casefold()
    }
