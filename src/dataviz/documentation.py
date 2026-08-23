from __future__ import annotations

from typing import Any


DOC_ALIASES = {
    "start": "quickstart",
    "architecture": "pipeline",
    "output": "outputs",
    "transform": "server-transforms",
    "browser-transform": "browser-transforms",
    "renderer": "renderers",
    "chart": "charts",
    "view": "charts",
    "source": "sources",
    "content": "dashboard",
    "interpolation": "dashboard",
    "title": "dashboard",
    "selection": "selections",
    "layout": "presentation",
    "style": "presentation",
    "repeat": "repeated-views",
    "multiples": "repeated-views",
    "gallery": "components",
    "component": "components",
    "compact": "ai-authoring",
    "context": "ai-authoring",
    "benchmark": "ai-authoring",
    "feedback": "ai-authoring",
    "authoring-log": "ai-authoring",
    "schema": "strict-schema",
    "schemas": "schema-reference",
    "validate": "validation",
    "preflight": "validation",
    "version": "versioning-release",
    "migration": "versioning-release",
    "migrate": "versioning-release",
    "release": "versioning-release",
    "frontend-adapter": "frontend-adapters",
    "security": "runtime-limits",
    "performance": "runtime-limits",
    "cleanup": "maintenance",
    "clean": "maintenance",
    "error": "troubleshooting",
    "debug": "troubleshooting",
}


DOC_TOPICS: dict[str, dict[str, Any]] = {
    "quickstart": {
        "summary": "AI 从空环境到第一个可验证 HTML 报告的最短路径。",
        "goal": "先证明数据契约和默认 Renderer 正确，再调整 Presentation 或扩展代码。",
        "workflow": [
            "dataviz authoring start <workspace> --dashboard <dashboard-id> --task \"<task>\"",
            "dataviz docs pipeline --format json",
            "dataviz schemas dashboard --format json",
            "dataviz list <workspace>",
            "dataviz context <workspace> <dashboard-id> --focus view:<view-id> --format json",
            "dataviz validate <workspace> --dashboard <dashboard-id> --format json",
            "dataviz query <workspace> <dashboard-id> --source <source-id> --format json",
            "dataviz report <workspace> <dashboard-id> --output <workspace>/dist/report.html",
            "dataviz serve <workspace> --port 8080",
            "dataviz authoring finish <workspace> <session-id> --outcome success --first-attempt success --correction-rounds 0",
        ],
        "rules": [
            "不要从自定义 HTML/CSS/JS 开始；先使用默认 Renderer。",
            "Dashboard 只引用 Adapter 名称；账号密码只留在 Workspace 本地配置或环境变量。",
            "Query Parameter 会重新执行服务端 DAG；Selection 只处理浏览器已经拿到的数据。",
            "先用 query 检查 Source，再用 output 检查 Named Output，最后渲染 View。",
            "Schema 是严格契约；未知字段和旧字段直接报错，不存在兼容模式。",
            "优先读取 focused Context 和单个 Component 契约；不要先吞入完整 Runtime 源码。",
            "把真实首次成功、修正轮次、耗时、客户端提供的 Token 和不清晰处写入 dataviz-authoring.jsonl；不能测量的值保持 unknown。",
        ],
        "success": [
            "validate 返回 status=valid。",
            "query/output 返回预期 kind、schema、row_count 和 preview/value。",
            "report 返回 status=success，并生成 HTML 与 manifest。",
        ],
        "related": ["pipeline", "workflow", "dashboard", "strict-schema", "troubleshooting"],
    },
    "pipeline": {
        "summary": "Dataviz 的稳定分层：取数、计算、浏览器交互、渲染和视觉编排彼此解耦。",
        "contract": [
            "Adapter → Workspace 中的连接与文件访问授权。",
            "Source → 从 File、SQL 或 Python 入口读取外部数据。",
            "Server Transform（可选）→ 用 Python 消费上游 Named Output，执行复杂计算。",
            "OutputBundle → 每个 Source/Transform 产出一个或多个有名称、有类型的 Output。",
            "Browser Transform（可选）→ 用纯 JS 处理已下载数据，不触发查询。",
            "View Renderer → Plotly、ECharts、Table、Perspective 或自定义生命周期。",
            "Presentation → 只负责布局、容器、Theme、组件样式和资源。",
        ],
        "boundaries": {
            "query_parameters": "只进入 Source/Server Transform 执行与缓存键；修改后需要 Run query。",
            "selections": "只在当前浏览器 tab 的当前 Dashboard 中生效；不进入服务端缓存键。",
            "dashboard_yaml": "分析逻辑、稳定 ID、数据引用、Selection 和最小阅读顺序。",
            "presentation_yaml": "可选的视觉覆盖；删除后默认页面仍然可运行。",
            "view_readiness": "只依赖该 View 的可达 Output；无关慢分支不阻塞，完成 Output 立即增量发布。",
            "frontend_framework": "只消费 Output、Selection、Runtime Event、View Descriptor 与 Renderer 生命周期协议。",
        },
        "simple_path": "Source 的 main Output 可用 input: sales 直接绑定 View，不需要显式 Transform。",
        "complex_path": "使用 transform:model/trend 或 browser:derive/summary 绑定稳定 Named Output。",
        "related": ["outputs", "server-transforms", "browser-transforms", "renderers", "presentation"],
    },
    "workflow": {
        "summary": "以最小失败边界开发看板的固定顺序。",
        "steps": [
            {"stage": "1. Discover", "command": "dataviz list <workspace>", "stop_when": "确认 Dashboard id、文件夹名和节点 id。"},
            {"stage": "2. Read", "command": "dataviz context <workspace> <dashboard-id> --focus view:<id> --format json", "stop_when": "只掌握当前任务的依赖闭包、Selection 和组件契约。"},
            {"stage": "3. Validate", "command": "dataviz validate <workspace> --dashboard <dashboard-id> --format json", "stop_when": "passed=true；没有 error，团队要求时也没有 warning。"},
            {"stage": "4. Source", "command": "dataviz query <workspace> <dashboard-id> --source <source-id> --format json", "stop_when": "原始字段、类型和行数正确。"},
            {"stage": "5. Compute", "command": "dataviz output <workspace> <dashboard-id> transform:<id>/<name>", "stop_when": "View 所需 Named Output 正确。"},
            {"stage": "6. Render", "command": "dataviz report <workspace> <dashboard-id> --output <workspace>/dist/check.html", "stop_when": "默认 Renderer 成功。"},
            {"stage": "7. Present", "command": "编辑 presentation.yaml 后重新 validate/report", "stop_when": "外观改变但数据口径不变。"},
            {"stage": "8. Interact", "command": "dataviz serve <workspace>", "stop_when": "Parameter 重新查询，Selection 只局部重绘。"},
        ],
        "do_not": [
            "不要同时修改 SQL、Transform、字段绑定和 CSS。",
            "不要在 Named Output 尚未正确时调图表 options。",
            "不要让 Presentation JS 承担本应可测试的业务计算。",
            "不要为了改一个 View 先读取整个 Gallery 或 1000 行浏览器 Runtime。",
        ],
        "related": ["quickstart", "troubleshooting"],
    },
    "dashboard": {
        "summary": "Dashboard 文件夹、稳定 ID 和最小 dashboard.yaml 契约。",
        "identity": {
            "folder_name": "导航和分享看到的画布名称；## 前缀片段表达目录位置。",
            "id": "稳定程序身份；CLI、API、DAG、Presentation 引用和运行状态使用。",
            "title_subtitle_description": "页面内容；可引用本次已提交的 Query Parameter，title 为空时回退到文件夹末级名称。",
        },
        "minimal_example": """schema: dataviz/dashboard/v1
kind: dashboard
id: sales-overview
title: 销售概览
subtitle: "仓 {{ parameters.warehouse_id }} · 商品 {{ parameters.product_id }}"
adapters: {warehouse: team-duckdb}
query_parameters:
  - {id: warehouse_id, label: 仓, default: 5740}
  - {id: product_id, label: 商品, default: "980464683"}
sources:
  - id: sales
    kind: source
    type: sql
    adapter: warehouse
    code: sources/sales.sql
    params: [warehouse_id, product_id]
views:
  - {id: trend, title: 收入趋势, input: sales, template: line, x: date, y: revenue}
sections:
  - {id: overview, title: 概览, template: single, views: [trend]}
""",
        "parameter_interpolation": {
            "syntax": "{{ parameters.<id> }}",
            "fields": [
                "dashboard title/subtitle/description/assumptions",
                "section title/description",
                "view title/description and markdown text",
            ],
            "lifecycle": "只读取最近一次 Run query 已提交的参数；编辑表单不会改旧数据集标题，重新查询后 Server 与导出 HTML 同步更新。",
            "formatting": "date_range 显示为“开始 至 结束”；选择参数优先显示 choice label；多值使用顿号连接。",
            "validation": "只允许直接参数引用；未知 ID、Selection、运算和任意 Jinja 表达式由 dataviz validate 拒绝。",
        },
        "rules": [
            "Parameter、Source、Transform、Selection、Section 和 View id 在各自作用域内稳定且唯一。",
            "极简看板不需要 presentation.yaml、CSS、JS 或 Canvas 文件。",
            "dashboard.yaml 中只保留逻辑和最小布局；视觉优化按 ID 放入 presentation.yaml。",
            "分析对象应优先进入 title/subtitle/section/view 内容层级，不要只藏在 Parameters 弹层。",
        ],
        "related": ["sources", "charts", "selections", "presentation", "strict-schema"],
    },
    "adapters": {
        "summary": "把凭证留在 Workspace，让可分享 Dashboard 只绑定 Adapter 名称。",
        "rules": [
            "Dashboard adapters 把逻辑别名映射到 Workspace Adapter，例如 warehouse: team-starrocks。",
            "真实账号密码放在 auth/adapters.local.yaml 或环境变量中，不提交 Git。",
            "同事复制 Dashboard 后，只需修改 Adapter 映射，不改 SQL 和业务代码。",
            "DuckDB 使用 duckdb Adapter；MySQL 和 StarRocks 可通过 SQLAlchemy/MySQL wire protocol。",
            "files Adapter 的 root 是访问边界，Source 不能通过 .. 越界。",
            "自定义 Python Source 可通过 context.adapter 读取已解析的 config、secrets 和常用连接字段。",
            "Adapter secrets 只进入可信 Python Source 子进程；Runtime 不主动把它们写入 Artifact、日志或导出 HTML，入口代码也不能主动泄露。",
        ],
        "example": """# auth/adapters.local.yaml
adapters:
  local-warehouse:
    type: duckdb
    database: data/warehouse.duckdb
  team-starrocks:
    type: sqlalchemy
    env: STARROCKS_URL
""",
        "related": ["sources", "runtime-limits", "troubleshooting"],
    },
    "sources": {
        "summary": "Source 只负责读取外部数据；跨 Dataset 计算应进入 Server Transform。",
        "types": {
            "file": "读取 CSV、Parquet、JSON/JSONL 或可选 Excel；可使用 Workspace files Adapter。",
            "sql": "通过 DuckDB、MySQL、StarRocks 等 Workspace Adapter 执行参数化 SQL。",
            "python": "调用可信 Python 入口读取特殊外部系统；可绑定 Adapter，但不消费其他节点输入。",
        },
        "examples": {
            "bundled_csv": "{id: orders, kind: source, type: file, path: data/orders.csv, format: csv}",
            "duckdb_sql": "{id: sales, kind: source, type: sql, adapter: warehouse, code: sources/sales.sql, params: [start_date], timeout_seconds: 120, timeout_retries: 1}",
            "python": "{id: api, kind: source, type: python, adapter: crm, code: sources/api.py, entrypoint: load, params: [account], timeout_seconds: 30}",
        },
        "sql_timeout_policy": {
            "defaults": {"timeout_seconds": 120, "timeout_retries": 1},
            "meaning": "timeout_retries 是首次尝试之外的立即重试次数；0 关闭重试，最大 5。",
            "scope": "只重试 query_timeout；连接、权限、语法和其他执行错误不重试。",
            "upper_bound": "单个 SQL Source 的最坏耗时约为 timeout_seconds × (timeout_retries + 1)。",
        },
        "python_contract": "Python entrypoint 接收 ExecutionContext；读取 context.params 和可选 context.adapter，并返回单值或与 outputs 完全一致的命名字典。Server Transform 的 context.adapter 始终为空。",
        "verification": [
            "dataviz validate <workspace> --dashboard <dashboard-id> --format json",
            "dataviz query <workspace> <dashboard-id> --source <source-id> --format json",
            "Server 中打开 Sources 并点击节点，检查本次 Run 的状态、缓存来源、耗时和错误。",
            "SQL Source 额外核对 Resolved SQL、参数化 Driver statement、bound parameters、Adapter、超时策略和 query hash。",
            "Resolved SQL 只用于人类 review；数据库仍接收参数化 statement 与 bound values。",
        ],
        "related": ["adapters", "outputs", "server-transforms", "troubleshooting"],
    },
    "outputs": {
        "summary": "OutputBundle 是 Source、Server Transform 和 Browser Transform 共用的命名结果契约。",
        "references": ["source:sales/main", "transform:sales-model/trend", "browser:latest/summary"],
        "kinds": ["table", "scalar", "object", "text", "html", "chart", "image", "file"],
        "declaration": """outputs:
  trend:
    kind: table
    schema:
      - {name: date, required: true, nullable: false}
      - {name: revenue, dtype: float64}
  total: {kind: scalar}
  narrative: {kind: text}
""",
        "rules": [
            "未声明 outputs 的节点只产生 main。",
            "声明 outputs 后，返回名称必须完全匹配；缺少或多出名称都失败。",
            "table 可声明列、精确 pandas dtype、required 和 nullable 边界契约。",
            "input: sales 是 source:sales/main 的正式简写；复杂引用使用完整 canonical reference。",
        ],
        "commands": [
            "dataviz output <workspace> <dashboard-id> source:sales/main --format json",
            "dataviz output <workspace> <dashboard-id> transform:model/trend --format csv",
        ],
        "related": ["server-transforms", "browser-transforms", "renderers"],
    },
    "server-transforms": {
        "summary": "用隔离 Python 进程完成可复用、可审查的复杂服务端计算。",
        "definition": """schema: dataviz/server-transform/v1
kind: server_transform
id: sales-model
runtime: python
code: sales_model.py
entrypoint: transform
inputs:
  orders: source:orders/main
  targets: source:targets/main
params: [forecast_factor]
outputs:
  trend: {kind: table}
  completion: {kind: table}
code_dependencies: [helpers/]
python_dependencies: [scikit-learn>=1.5]
timeout_seconds: 60
cache: {mode: session, scope: tab}
""",
        "python": """def transform(context):
    orders = context.table("orders").copy()
    targets = context.table("targets")
    factor = context.params["forecast_factor"]
    orders["forecast"] = orders["revenue"] * factor
    return {"trend": orders, "completion": build_completion(orders, targets)}
""",
        "runtime": [
            "每次执行使用 fresh spawn 子进程；timeout_seconds 到期会硬终止。",
            "失败保存完整 traceback 和 execution-log Artifact，节点外只返回短摘要。",
            "缓存指纹包含入口代码、code_dependencies、Python 包版本、参数、Adapter 和上游 Artifact。",
            "产品定位是可信单机执行；不把多租户 CPU/内存配额混入当前 DSL。",
        ],
        "related": ["outputs", "runtime-limits", "troubleshooting"],
    },
    "browser-transforms": {
        "summary": "用独立 Web Worker 中的无 DOM JavaScript 处理浏览器已有数据，并精确声明 Selection 失效依赖。",
        "definition": """schema: dataviz/browser-transform/v1
kind: browser_transform
id: latest
code: latest.js
entrypoint: transform
inputs:
  sales: transform:sales-model/trend
selections: [dashboard:sales/region]
outputs:
  rows: {kind: table}
timeout_seconds: 30
""",
        "javascript": """async function transform(context) {
  const rows = context.inputs.sales || [];
  const selected = context.selections["dashboard:sales/region"] || [];
  return {rows: selected.length ? rows.filter(row => selected.includes(row.region)) : rows};
}
""",
        "context": ["inputs", "input(name)", "parameters", "selections", "frame(rows)"],
        "rules": [
            "函数可以同步返回或返回 Promise，但结果必须可结构化克隆；函数、DOM、循环引用等输出会得到 browser_transform_not_serializable。",
            "禁止访问 DOM；页面行为属于 Renderer 或 Presentation extension。",
            "selections 只列真实依赖的 canonical selection key，Runtime 才能局部失效。",
            "失败只阻断依赖该 Output 的分支，不重绘无关 View。",
            "每次执行使用 fresh Worker；新 Selection/Output 会取消旧任务，timeout_seconds 默认 30 秒、最大 300 秒。",
            "错误稳定携带 code/name/message/stack/transform_id/worker，取消和超时可以被 AI 直接区分。",
        ],
        "related": ["outputs", "selections", "renderers", "runtime-limits"],
    },
    "renderers": {
        "summary": "Renderer 只把 Named Output 转成 View，并遵守统一生命周期。",
        "built_in": ["Plotly", "ECharts", "Table", "Perspective", "Markdown/Text", "Image"],
        "lifecycle": ["validate(descriptor)", "mount(context, descriptor)", "update(context, descriptor, state)", "dispose(context, state)"],
        "custom": """window.datavizRuntime.registerRenderer("team.sparkline", {
  validate(descriptor) { if (!Array.isArray(descriptor.rows)) throw new Error("table required"); },
  mount(context, descriptor) {
    const node = document.createElement("div");
    context.body.append(node);
    this.update(context, descriptor, {node});
    return {node};
  },
  update(_context, descriptor, state) {
    state.node.textContent = JSON.stringify(descriptor.rows);
    return state;
  },
  dispose(_context, state) { state.node.remove(); }
});
""",
        "view": "{id: spark, template: custom, renderer: team.sparkline, input: sales}",
        "rules": [
            "自定义 Renderer 通过显式 ID 注册，不覆盖 Canvas 全局渲染函数。",
            "同步或异步 lifecycle 失败会生成 renderer_lifecycle_error，只标记当前 View，并保留 renderer/phase/view_id/stack。",
            "优先使用内置 Renderer；只有无法表达的视觉类型才增加扩展。",
        ],
        "commands": [
            "dataviz components renderer.custom",
            "dataviz scaffold renderer.custom --id team.spark --output ./team-spark",
            "dataviz renderer-test ./team-spark/assets/team.spark.js --renderer-id team.spark --contract ./team-spark/assets/team.spark.contract.json",
            "dataviz templates",
        ],
        "related": ["charts", "tables", "presentation"],
    },
    "charts": {
        "summary": "Plotly/ECharts 声明式 View 配方、必填字段和最短排错路径。",
        "field_matrix": {
            "metric": {"required": ["input"], "optional": ["value", "aggregate", "label"]},
            "line": {"required": ["input", "x", "y"], "optional": ["series", "aggregate", "engine"]},
            "bar": {"required": ["input", "x", "y"], "optional": ["series", "aggregate", "engine"]},
            "stacked-bar": {"required": ["input", "x", "y", "series"], "optional": ["aggregate", "engine"]},
            "pie": {"required": ["input", "label", "value"], "optional": ["aggregate", "engine"]},
            "scatter": {"required": ["input", "x", "y"], "optional": ["series", "color", "size", "engine"]},
            "heatmap": {"required": ["input", "x", "y", "z"], "optional": ["aggregate", "engine"]},
        },
        "minimal_examples": {
            "plotly_line": "{id: revenue-trend, input: sales, template: line, engine: plotly, x: date, y: revenue, series: region}",
            "echarts_bar": "{id: region-bars, input: sales, template: bar, engine: echarts, x: region, y: revenue, aggregate: sum}",
            "heatmap": "{id: matrix, input: sales, template: heatmap, engine: echarts, x: month, y: region, z: revenue, aggregate: sum}",
        },
        "preflight": [
            "output preview 中必须存在编码字段，大小写完全一致。",
            "数值编码应为数值类型；日期和类别列不能意外全为空。",
            "先只保留必填字段完成渲染，再逐项加入 series/color/size/options。",
            "engine 只允许 plotly 或 echarts；普通图表不需要 Python 画图代码。",
        ],
        "related": ["outputs", "tables", "workflow", "troubleshooting"],
    },
    "tables": {
        "summary": "普通 Table 与 Perspective 是两个独立模板。",
        "templates": {
            "table": "展示型明细表；columns、limit、格式和 CSS 容易定制。",
            "perspective": "分析型 Web Component；支持排序、筛选、分组、透视和图形探索。",
        },
        "examples": {
            "table": "{id: detail, title: 明细, input: sales, template: table, columns: [date, region, revenue], limit: 200}",
            "perspective": "{id: pivot, title: 透视分析, input: sales, template: perspective, columns: [region, revenue], config: {plugin: Datagrid, group_by: [region]}}",
        },
        "rules": [
            "需要品牌化样式或固定列展示时使用 table。",
            "需要用户现场分析和透视时使用 perspective。",
            "两个模板都只在内部可以消费滚轮时拦截滚动，到边界或内容不足时交还页面。",
            "Perspective 更新复用 Viewer/Table 并执行 replace + flush；dispose 会断开 observer，并依次 delete Viewer 与 Table。",
        ],
        "related": ["charts", "presentation"],
    },
    "repeated-views": {
        "summary": "用一个 View 蓝图巡检全部分组，或只渲染用户选中的分组。",
        "templates": {
            "small-multiples": "按 repeat.by 展示全部分组；适合 100 家门店全量巡检。",
            "selection-gallery": "搜索/级联多选后只创建选中分组；空选择显示提示。",
        },
        "minimal_example": """views:
  - {id: store-trend, input: sales, template: line, x: week, y: revenue}
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
      searchable: true
      page_size: 40
      recycle_offscreen: true
""",
        "rules": [
            "Repeat Section 复用一个浏览器 Dataset，不复制 Source 查询。",
            "searchable 搜索所有分组，page_size 只限制当前卡片 DOM，不截断 Dataset。",
            "lazy 使用 IntersectionObserver，在接近视口时创建图表实例；recycle_offscreen 离屏后 dispose，滚回再创建。",
            "selection-gallery 可配 searchable 或 cascader Selector。",
            "导出 HTML 保留完整 Dataset；导出 Selection 只是初始状态。",
        ],
        "commands": [
            "dataviz components section.small-multiples",
            "dataviz components section.selection-gallery",
            "dataviz benchmark <workspace> <dashboard> --browser-runtime --format json",
        ],
        "related": ["charts", "selections", "presentation"],
    },
    "selections": {
        "summary": "Query Parameter 与 Dashboard/Section/View Selection 的职责和级联。",
        "scopes": {
            "query_parameters": "服务端取数参数；修改后必须重新 Run query。",
            "dashboard_selections": "浏览器端影响所有绑定 View。",
            "section_selections": "只影响所属 Section 的绑定 View。",
            "view_selections": "只影响单个 View，不重绘兄弟 View。",
        },
        "rules": [
            "Selection 只有 include 语义；空选择表示不施加 include 约束，显式选择全部值会保留完整 canonical state，不再自动折叠为空。",
            "Dashboard → Section → View 逐级收缩可用选项，并清除已失效选择。",
            "一个 Selection 内的层级值用 path_fields，并在 Presentation 选择 cascader。",
            "type/field/path_fields/choices 属于 dashboard.yaml 数据契约；搜索、虚拟滚动和视觉 variant 属于 presentation.yaml。",
            "Selection 状态按浏览器 tab 与 Dashboard 隔离，不在用户和 tab 之间共享。",
            "CLI query/run 只接受 Query Parameter；report --selection 仅设置导出页初始值。",
        ],
        "selector_choice": {
            "auto": "single_select <= 4 使用 segmented；multi_select <= 8 使用 checkbox-group；更大的平面集合使用 select；path_fields 使用 cascader；date_range 使用 date-range。",
            "select": "统一的平面单选/多选。search 与 virtual 使用 auto/always/never；无需更换模板即可从 10 个选项扩展到 1,000 个选项。",
            "segmented": "不超过 4 个的单选或 Selection 布尔三态；variant: radio 可改为换行 Radio 语言。",
            "checkbox-group": "不超过 8 个的多选；全选会真实勾选全部值并把操作切换为反选，可从全集取消少数项；variant: tags 提供 Checkable Tag 外观。",
            "cascader": "省/市/区县等路径；hierarchy_selection: cascade 可用父节点批量选择后代叶子。",
            "tree-select": "大型或窄面板层级；支持搜索、跨分支选择、父节点半选和后代批量选择。checked_strategy 只改变摘要，不改变叶路径值。",
            "date-range": "两个可 review 的原生日期输入；支持 min/max、开放端点和命名 presets。",
        },
        "presentation_fields": {
            "common": "template、variant、placeholder、all_label、select_all_label、invert_label、clear_label、show_unavailable、css_class。",
            "select": "search/virtual: auto|always|never；search_threshold、virtual_threshold、max_visible_tags、max_selected、hide_selected、item_height、viewport_height、overscan。多选的全选/反选保留显式值。",
            "choice_metadata": "dashboard.yaml 的每个 Choice 可声明 group、description、keywords；Select 搜索会同时匹配标签、值和这些元数据。",
            "hierarchy": "level_labels、path_separator、hierarchy_selection: leaf|cascade、checked_strategy: child|parent|all、default_expand_depth。child 显示叶路径，parent 折叠完整分支，all 同时显示推导出的父路径与叶路径；canonical state 始终是叶路径。",
            "date_range": "start_label、end_label、min、max、allow_open_range、presets[{label,start,end}]。当前内置组件是日粒度；month/quarter/year 专用输入尚未实现。",
        },
        "interaction_contract": [
            "原生 select/input 是唯一 canonical state；视觉 Adapter 不持有第二份业务值。",
            "空 multi_select 与显式全选是不同状态：前者是不施加约束，后者保存所有当前值；两者在当前数据上结果相同，但后者允许立即取消少数项，也不会吞掉用户操作。",
            "Selection 单选的隐藏空值表示 All，避免浏览器在无默认值时自动选中第一项。",
            "所有浮层复用 runtime.overlay：同组互斥、点击外部关闭、Esc、焦点返回和视口重定位。",
            "显式 template 覆盖 auto；解析后的 template 与 auto_reason 会进入 Runtime DOM，便于调试。",
        ],
        "select_example": """# presentation.yaml\nselectors:\n  dashboard:sales/region:\n    template: select\n    search: auto\n    virtual: auto\n    search_threshold: 9\n    virtual_threshold: 200\n    max_visible_tags: 2\n    max_selected: 20\n""",
        "small_option_examples": """# presentation.yaml\nselectors:\n  dashboard:sales/status:\n    template: segmented\n    variant: radio\n  section:stores/channel:\n    template: checkbox-group\n    variant: tags\n""",
        "hierarchy_example": """# dashboard.yaml\n- id: location\n  type: multi_select\n  field: district\n  path_fields: [province, city, district]\n\n# presentation.yaml\nselectors:\n  view:detail/location:\n    template: cascader\n    level_labels: [Province, City, District]\n    hierarchy_selection: cascade\n    checked_strategy: child\n""",
        "date_range_example": """selectors:\n  view:detail/window:\n    template: date-range\n    min: '2026-01-01'\n    max: '2026-12-31'\n    presets:\n      - {label: Q1, start: '2026-01-01', end: '2026-03-31'}\n""",
        "version_policy": "Registry v3 只接受当前公开 Component ID；未知模板直接校验失败，不提供别名或旧 Registry 迁移路径。",
        "commands": [
            "dataviz docs selections",
            "dataviz components selector.select",
            "dataviz components selector.cascader",
            "dataviz components selector.tree-select",
            "dataviz components selector.date-range",
            "dataviz scaffold selector.select --id region",
            "dataviz scaffold selector.checkbox-group --id channel",
            "dataviz scaffold selector.segmented --id status",
            "dataviz scaffold selector.cascader --id location",
            "dataviz scaffold selector.tree-select --id location-tree",
            "dataviz scaffold selector.date-range --id window",
        ],
        "related": ["browser-transforms", "presentation", "workflow"],
    },
    "presentation": {
        "summary": "用可选 presentation.yaml 调整页面，不改变分析逻辑。",
        "boundary": [
            "dashboard.yaml：Adapter、Source、Transform、参数、Selection、View 数据绑定和最小顺序。",
            "presentation.yaml：Theme、布局、Section/View 容器、Selector 模板、CSS/JS 资源。",
            "Presentation 只能通过稳定 ID 引用逻辑对象；失效引用给 warning 并忽略。",
        ],
        "extension_order": [
            "默认 Renderer",
            "Section/View/Layout 模板",
            "Theme 和模板参数",
            "CSS token 与局部 css_class",
            "单 View 自定义 Renderer",
            "完整自定义 Canvas",
        ],
        "layout_rules": [
            "默认 Section 是自上而下的文档流，不需要坐标或 Mosaic 配置。",
            "grid、split、chart-and-table 等是可选语义模板；View 只用 span/min_height 做提示。",
            "完整 Canvas 可以自由编排稳定 View Host，不受默认 Layout 限制。",
            "canvas-functional.css 始终加载以保证交互；canvas.css 是可替换的默认视觉层。",
        ],
        "commands": ["dataviz components", "dataviz templates", "dataviz context <workspace> <dashboard-id> --focus view:<id> --format json"],
        "related": ["dashboard", "selections", "renderers"],
    },
    "components": {
        "summary": "用物理 Component Package、Registry v3、Story Gallery 和 Scaffold 发现并复用 Section/View/Selector/Renderer。",
        "contract": [
            "manifest.yaml：版本、owner、依赖、组件和公开契约。",
            "controller.js：headless state、Overlay 或 lifecycle。",
            "adapter.js：当前 Vanilla Runtime 或未来 React/Vue 如何消费 dataviz/runtime/v1。",
            "style.css：必需 functional CSS、可覆盖 token 和稳定 semantic DOM。",
            "story.yaml：Gallery specimen 的唯一清单来源。",
            "test.yaml：行为、键盘、可访问性、视觉几何或性能契约。",
        ],
        "commands": [
            "dataviz components --format json",
            "dataviz components --check --format json",
            "dataviz components selector.select --format json",
            "dataviz components selector.cascader --format json",
            "dataviz scaffold view.line --id revenue",
            "dataviz scaffold selector.select --id region",
            "dataviz scaffold selector.checkbox-group --id channel",
            "dataviz scaffold selector.segmented --id status",
            "dataviz scaffold selector.cascader --id location",
            "dataviz scaffold selector.tree-select --id location-tree",
            "dataviz gallery",
            "dataviz gallery --output component-gallery.html",
        ],
        "rules": [
            "Registry 的每个 Component 必须有物理 owner；同生命周期模板可以共享一个实现 Package。",
            "components --check 拒绝缺失六类资产、重复 owner、未知依赖、错误 Story/Test 引用和 Registry 漏项。",
            "普通需求先选内置模板；自定义 Renderer 是单 View 逃生口；完整 Canvas 是最后一层。",
            "Gallery available 直接由 story.yaml 推导；Gallery 索引、锚点和导航运行时自动生成。",
            "随包分发的 Gallery 会复制到临时 Workspace 运行，不向 site-packages 写 Artifact。",
            "runtime.overlay 统一同组互斥、外部点击、Esc/焦点返回和视口重定位；组件不得另写全局关闭状态。",
            "Selector Adapter 必须保留原生 form control 作为 canonical state，Server 和 HTML 才能共用语义。",
            "CLI 组件文档直接读取 Component Registry v3 和物理 Package，不维护第二份手写字段表。",
        ],
        "related": ["charts", "selections", "presentation", "ai-authoring"],
    },
    "ai-authoring": {
        "summary": "减少 AI 输入、输出和试错的可执行工作流；不预设未经真实任务验证的 Token 目标。",
        "focused_context": {
            "view": "只包含该 View、所属 Section、有效 Selection、可达 Browser/Server DAG、代码和相关组件契约。",
            "section": "包含该 Section 的 View/Repeat 蓝图及共同依赖。",
            "source_transform_browser": "包含目标节点及其上游服务端依赖闭包。",
            "component": "不携带 Workspace，只返回一个 Component 契约与 recipe 入口。",
        },
        "commands": [
            "dataviz authoring start <workspace> --dashboard <id> --task \"<task>\" --model <model>",
            "dataviz authoring note <workspace> <session-id> --category documentation --reference <topic> --message \"<problem>\"",
            "dataviz authoring finish <workspace> <session-id> --outcome success --first-attempt failure --correction-rounds 2 --input-tokens <measured> --output-tokens <measured>",
            "dataviz authoring show <workspace> --format json",
            "dataviz schemas dashboard --format json",
            "dataviz context <workspace> <dashboard> --focus view:<id> --format json",
            "dataviz context <workspace> <dashboard> --focus component:view.line --format json",
            "dataviz scaffold dashboard --id sales --output <workspace>/dashboards/sales",
            "dataviz benchmark <workspace> <dashboard> --format json",
            "dataviz benchmark <workspace> <dashboard> --focus section:<id> --format json",
            "dataviz benchmark <workspace> <dashboard> --browser-runtime --format json",
        ],
        "benchmark": [
            "当前命令确定性记录 authoring files 的文件数、行数、字符和 UTF-8 bytes。",
            "同时比较完整 Context 与每个 View focused Context 的 bytes 和缩减比例。",
            "--browser-runtime 会执行一次查询和 HTML 导出，并在真实 Chromium 中记录 Arrow、Worker、Repeat 分组/DOM/挂载峰值、页面时序和控制台错误。",
            "不把 bytes 粗暴换算为 Token；模型、Tokenizer、首次成功率和修正轮次需要后续真实 eval。",
            "最终评测必须同时覆盖默认看板、三级 Selection、复杂 Transform、多 Output、自定义 Renderer/Canvas。",
        ],
        "feedback_log": [
            "Workspace 根目录的 dataviz-authoring.jsonl 是 append-only、可提交 Git、可直接分享的真实任务记录。",
            "started / friction / finished 事件使用 dataviz/authoring-event/v1；损坏单行会产生诊断，不吞掉其他会话。",
            "首次成功指第一次实现经过 validate、目标 Output 与渲染验证，无需修改；correction_rounds 是之后的实现修正轮次。",
            "elapsed_seconds 由 CLI 按 start/finish 自动记录；Token 只接受 authoring client 的实际值，不由 bytes 推算。",
            "不要在 task、notes 或 friction 中写凭证、原始敏感数据或个人信息。",
        ],
        "related": ["workflow", "components", "troubleshooting"],
    },
    "schema-reference": {
        "summary": "从当前安装版本的 Pydantic 模型生成 AI 可读字段契约，避免文档与校验器漂移。",
        "commands": [
            "dataviz schemas",
            "dataviz schemas dashboard --format json",
            "dataviz schemas source --full --format json",
            "dataviz components view.line --format json",
        ],
        "boundary": [
            "schemas 负责字段、类型、默认值、约束和完整 JSON Schema。",
            "components 负责行为、生命周期、semantic DOM、样式 token、Story 和契约测试。",
            "context --focus 只组合当前任务可达的 Schema/Component/代码切片。",
        ],
        "rule": "修改 DSL 必须先修改 Pydantic 模型；CLI 输出自动变化，不复制维护字段清单。",
        "related": ["strict-schema", "components", "ai-authoring"],
    },
    "validation": {
        "summary": "每次修改 Dashboard 后先运行的静态 preflight；不连接数据库、不启动 Server，也不执行 Source。",
        "recommended_command": "dataviz validate <workspace> --dashboard <dashboard-id> --format json",
        "options": {
            "--dashboard / -d": "只检查一个 Dashboard 及其 Workspace 级依赖；其他损坏 Dashboard 不污染本次结果。",
            "--format json": "输出稳定 dataviz/validation/v1 机器契约；默认 text 面向人阅读。",
            "--strict": "warning 也返回 exit code 1，适合 CI 或分享前门禁。",
        },
        "checks": [
            "Workspace/Dashboard 严格 Schema 和 retired/unknown 字段。",
            "Adapter 绑定、Source 类型兼容和本地配置可解析性；不会输出凭证。",
            "SQL 文件存在且 UTF-8 可读；命名占位符与 Source params 双向一致。",
            "Source、Transform、Named Output、Browser Transform、View 和 Section 引用。",
            "Query Parameter 内容插值、Selection canonical key 和绑定。",
            "Presentation、Renderer、Canvas 与本地资源路径。",
            "Python code_dependencies 和 python_dependencies。",
        ],
        "json_contract": {
            "status": "valid | valid_with_warnings | invalid",
            "passed": "是否满足当前 strict 策略",
            "queries_executed": "固定为 0，证明这是纯静态检查",
            "checks": "固定检查域及 passed/warning/failed 结果",
            "diagnostics": "level/code/category/dashboard/file/field/message/details/hint",
            "next_actions": "按当前结果生成的最短后续动作",
            "exit_code": "0 可继续；1 必须修复",
        },
        "ai_loop": [
            "编辑一个逻辑层或 Presentation 层文件。",
            "运行 focused JSON preflight。",
            "按 diagnostics 中的 code、file、field、details 和 hint 修复第一类错误。",
            "重复 validate，直到 passed=true。",
            "然后才 query 单个 Source/Output，最后 report 或 serve。",
        ],
        "sql_parameter_example": {
            "source": "params: [start_date, region]",
            "sql": "where dt >= :start_date and region = :region",
            "errors": "SQL 中出现但 params 未声明 → sql_parameter_undeclared；params 声明但 SQL 未引用 → sql_parameter_unused warning。",
        },
        "related": ["workflow", "strict-schema", "sources", "troubleshooting"],
    },
    "strict-schema": {
        "summary": "这是全新 DSL：强制迁移、严格校验，不读取旧字段，也不提供 deprecated 层。",
        "rules": [
            "统一使用 View，不接受 Widget 目录、widget 字段或 widget helper。",
            "统一使用 Selection，不接受 filters、dashboard_filters、filter_bindings 或 exclude mode。",
            "统一使用 Workspace Adapter，不读取 connections 文件。",
            "workspace.yaml 只用 folders；不接受 navigation 或 trash 持久化树。",
            "Dashboard 目录必须直接位于 dashboards/ 下，多层逻辑路径编码为 父##子##画布。",
            "View 使用 input/inputs，不接受 source 字段。",
            "Layout 不接受 x/y/height/row_height/items 坐标字段；默认按 Section/View 顺序排布。",
            "Source 不使用 depends_on；跨 Dataset 计算必须声明 Server Transform inputs。",
            "未知字段由 Pydantic extra=forbid 直接报错。",
            "独立 workspace/dashboard/presentation/source/transform 文件必须显式携带 schema；版本 URI 是 Literal，不接受未来或旧版本字符串。",
        ],
        "migration_policy": "先运行 dataviz migrate <workspace> 查看计划，再显式 --apply；未知旧版本没有注册路径时阻断。迁移是离线文件改写，Runtime 永远只执行当前协议。",
        "related": ["dashboard", "pipeline", "troubleshooting"],
    },
    "frontend-adapters": {
        "summary": "用第二个 Web Component 参考实现验证 dataviz/runtime/v1 不依赖默认 Vanilla Canvas 内部函数。",
        "commands": [
            "dataviz frontend-adapters --format json",
            "dataviz frontend-adapters web-component --format json",
            "dataviz frontend-adapters web-component --output runtime-v1-adapter.js",
        ],
        "contract": [
            "Vanilla 是生产 Adapter；Web Component 是无框架、零依赖的契约探针，不替代完整默认 Renderer。",
            "DatavizRuntimeV1Client 只读取 protocol、portable outputs/view_inputs/selection_contract、view_specs 和 selections。",
            "参考 <dataviz-output> 支持 output/view 与 json/count/table，用公共 selection contract 做 include 筛选。",
            "它不引用 window.datavizRuntime、Python CanvasRenderer 私有结构或默认 View Renderer。",
            "Server 可从 /runtime/web-component-adapter.js 提供资源，CLI 也能复制为独立 JS。",
        ],
        "events": ["dataviz:ready", "dataviz:selectionchange", "dataviz:outputschange"],
        "related": ["pipeline", "renderers", "versioning-release"],
    },
    "versioning-release": {
        "summary": "严格 DSL、离线迁移、可读 changelog 与三种 pip 发行物的发布流程。",
        "commands": [
            "dataviz version",
            "dataviz migrate <workspace>",
            "dataviz migrate <workspace> --apply",
            "uv build",
            "python scripts/build_release_zip.py",
        ],
        "version_change": [
            "新增 schema URI 和严格 Pydantic 模型；不要让旧、新协议同时进入 Runtime。",
            "为旧 URI 注册确定性的离线 migration，并提供 before/after fixture、幂等和 blocker 测试。",
            "先发布 migrate 工具与 CHANGELOG，再要求 Workspace 文件迁移，最后删除旧实现代码。",
            "更新 Component Registry/Runtime protocol 时分别版本化，不用 package version 暗示全部协议同步变化。",
        ],
        "release_contract": [
            "Python 3.11、3.12、3.13、3.14 分别跑 unit/contract tests。",
            "Chromium、Firefox、WebKit 分别跑真实浏览器 Runtime tests。",
            "wheel、sdist、pip-installable ZIP 在干净 venv 中安装，并运行 version/schemas/components/init/validate/report smoke。",
            "ZIP 内容可复现，发布时同时生成 SHA-256；发行包禁止包含 .venv、build、缓存和运行 Artifact。",
        ],
        "related": ["strict-schema", "schema-reference", "frontend-adapters"],
    },
    "runtime-limits": {
        "summary": "当前已实现的运行治理和必须显式知道的边界。",
        "implemented": [
            "Python Source/Server Transform 使用独立 spawn 进程和可选硬超时。",
            "SQL Source 使用独立查询进程；硬超时会终止进程并释放连接，MySQL/StarRocks 同时设置 Session 查询超时。",
            "SQL Source 默认单次 120 秒并在 timeout 后立即额外重试一次；timeout_seconds 与 timeout_retries 可按 Source 覆盖。",
            "每次 SQL 重试创建新进程和新连接，并通过 node_retrying 事件公开尝试进度；非超时错误不会重试。",
            "SQL 错误稳定分类为 query_timeout、query_connection_error 和 query_execution_error。",
            "Python 失败保留完整 traceback 与日志 Artifact。",
            "Workspace max_concurrent_runs 限制并发 Run 数。",
            "max_embedded_rows 与 max_embedded_bytes 在导出/页面前阻止失控 payload。",
            "缓存覆盖上游 Artifact、入口代码、声明代码依赖、包版本、参数和 Adapter 指纹。",
            "浏览器只嵌入可达 Named Output；不同 Dashboard、tab、浏览器状态相互隔离。",
            "默认 Run 从 View/Repeat/Canvas 输入反推最小服务端目标闭包。",
            "运行中 NodeResult 与 output_ready 持续提交；每个 View 可在自己的依赖完成后先展示。",
            "RunRecord、Run Artifact 和缓存按 Workspace 数量/时间策略自动淘汰，正在运行的 Run 始终受保护。",
            "Browser Transform 在 fresh Web Worker 中运行，支持 Promise、supersede cancellation、timeout_seconds 和结构化错误。",
            "大 Table 自动切换 Arrow IPC；Server 使用 HTTP gzip，HTML 使用 gzip + base64 分片，浏览器异步解码后发布 Output。",
            "Perspective 明确执行 create/update/flush/dispose，并检查 v5 主版本与必要 API。",
            "Repeat 使用全量分组搜索、page_size DOM 上限、IntersectionObserver 懒挂载和离屏 Renderer 回收。",
        ],
        "current_limits": [
            "Arrow 当前优化传输和初始解析；Selection/图表/Browser Transform 消费数据时仍会按需物化 JavaScript 行对象。",
            "Server 与导出仍传输完整可达 Output；尚未实现列式浏览器执行、服务端分页或可见 Record Batch 请求。",
            "当前是可信单机工具，不提供多租户 CPU/内存配额。",
            "Workspace Python、JS 和自定义 Canvas 都是可信本地代码，不能运行不可信包。",
        ],
        "related": ["server-transforms", "browser-transforms", "maintenance", "troubleshooting"],
    },
    "maintenance": {
        "summary": "限制长期 Server 的 RunRecord、Artifact 与缓存增长，并用安全的 dry-run 清理本地状态。",
        "runtime_fields": {
            "max_retained_runs": 100,
            "run_retention_seconds": 604800,
            "max_retained_cache_entries": 500,
            "cache_retention_seconds": 2592000,
        },
        "commands": [
            "dataviz clean <workspace>",
            "dataviz clean <workspace> --keep-runs 20 --run-max-age-hours 48",
            "dataviz clean <workspace> --all --apply",
        ],
        "rules": [
            "默认是 dry-run，只返回候选路径、原因和字节数；必须显式 --apply 才删除。",
            "清理目标只允许位于 Workspace/.dataviz/runs 或 cache 内。",
            "Server 自动清理时，queued/running 和仍由 API 保留的 Run 不会被删除。",
            "--runs/--no-runs 与 --cache/--no-cache 可分别控制两类数据。",
        ],
        "related": ["runtime-limits", "troubleshooting"],
    },
    "troubleshooting": {
        "summary": "按执行层定位错误，避免同时修改多层。",
        "triage": [
            {"symptom": "Workspace 无法加载", "action": "运行 validate；修复 YAML、未知字段、路径和重复 ID。"},
            {"symptom": "Source 失败", "action": "单独 query；检查 Adapter、参数、SQL/Python traceback。"},
            {"symptom": "StarRocks 偶发超时", "action": "查看 node_retrying 与最终 error.details；按 Source 调整 timeout_seconds/timeout_retries，不要重试语法或权限错误。"},
            {"symptom": "Transform 失败", "action": "用 output 只执行目标闭包；检查 input schema、node.error.traceback 和 node.log。"},
            {"symptom": "查询成功但图为空", "action": "检查 Named Output 字段、类型、空值以及 Selection 后行数。"},
            {"symptom": "一个 View 报错", "action": "缩减到模板必填字段，并确认其 input reference。"},
            {"symptom": "默认页面正常，自定义页面失败", "action": "问题位于 Presentation/Renderer/CSS/JS；逐层恢复。"},
            {"symptom": "Server 正常，HTML 导出失败", "action": "检查 payload 限额、manifest、JS 资产和浏览器控制台。"},
            {"symptom": "源码环境出现 ModuleNotFoundError: dataviz", "action": "使用 uv sync --extra dev --no-editable；框架源码变化后增加 --reinstall-package workspace-dataviz，并始终用 uv run --no-editable dataviz。"},
        ],
        "evidence": [
            "dataviz validate 的完整 JSON。",
            "dataviz query/output 的 status、schema、preview/value、node.error 和 node.log。",
            "dataviz context --focus view:<id> --format json 中的依赖切片与组件契约。",
            "导出 HTML 同目录的 .manifest.json。",
        ],
        "reset": [
            "保留一个 Source、一个 Named Output 和一个最小 View。",
            "暂时移除 presentation.yaml 和自定义 assets。",
            "默认 Renderer 成功后，每次只恢复一个配置。",
        ],
        "related": ["workflow", "strict-schema", "runtime-limits"],
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
