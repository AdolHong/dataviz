from __future__ import annotations

from typing import Any

from dataviz.view_contracts import VIEW_TEMPLATE_CONTRACTS


_CHART_TEMPLATES = (
    "line",
    "bar",
    "stacked-bar",
    "pie",
    "scatter",
    "heatmap",
    "radar",
)
_CHART_FIELD_MATRIX = {
    name: {
        key: contract[key]
        for key in (
            "required",
            "optional",
            "engine",
            "aggregate",
            "field_references",
        )
        if key in contract
    }
    for name in _CHART_TEMPLATES
    for contract in [VIEW_TEMPLATE_CONTRACTS[name]]
}


DOC_ALIASES = {
    "start": "quickstart",
    "architecture": "pipeline",
    "output": "outputs",
    "dataset-transform": "dataset-transforms",
    "interactive-transform": "interactive-transforms",
    "compute": "compute-parameters",
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
    "export": "html-export",
    "html": "html-export",
    "offline": "html-export",
    "pyodide": "html-export",
    "schema": "strict-schema",
    "schemas": "schema-reference",
    "validate": "validation",
    "preflight": "validation",
    "version": "versioning-release",
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
        "summary": "从空环境到可验证 Dashboard 和 HTML 报告的最短 v2 路径。",
        "commands": [
            "dataviz version",
            "dataviz docs pipeline --format json",
            "dataviz schemas dashboard --format json",
            "dataviz list <workspace>",
            "dataviz context <workspace> <dashboard-id> --focus view:<view-id> --format json",
            "dataviz validate <workspace> --dashboard <dashboard-id> --format json",
            "dataviz query <workspace> <dashboard-id> --source <id> --output-name main --query-param key=value",
            "dataviz output <workspace> <dashboard-id> source:<id>/<output>",
            "dataviz report <workspace> <dashboard-id> --output report.html",
            "dataviz serve <workspace> --port 8080",
        ],
        "rules": [
            "不要从自定义 HTML/CSS/JS 开始；先用默认 Renderer 证明数据契约。",
            "Adapter 只在 Workspace 定义；Dashboard 只写逻辑别名，不保存账号密码。",
            "Query Parameter 创建新的 Query Run；Selection 不查询；Compute Parameter 只触发声明它的 Interactive Transform。",
            "所有 Output 引用必须写完整，例如 source:sales/main、dataset:model/trend、interactive:simulation/result。",
            "每次修改后运行 validate；未知字段、旧 schema 和不完整引用直接失败。",
        ],
        "success": [
            "validate 返回 passed=true。",
            "Query Run 的目标节点为 ready 或 empty。",
            "HTML report 生成，同时写出 report manifest。",
        ],
        "related": ["pipeline", "workflow", "validation", "troubleshooting"],
    },
    "pipeline": {
        "summary": "稳定主链分成不可变取数阶段与可重复交互计算阶段。",
        "contract": [
            "Adapter → Source → Dataset Transform（可选）→ Base Named Output",
            "Base Named Output + Query Parameter 快照 + Selection + Compute Parameter",
            "→ Interactive Transform（可选）→ Derived Named Output",
            "→ View Renderer → Presentation",
        ],
        "state_namespaces": {
            "query_parameters": "提交后创建新 Query Run，只进入声明依赖它们的 Source/Dataset Transform。",
            "selections": "include-only 浏览器状态；直接筛选 View，并可作为 Interactive Transform 输入。",
            "compute_parameters": "不取数；提交后只重算声明依赖它们的 Interactive Transform。",
        },
        "execution": {
            "query_dag": "Source 与 Dataset Transform；完成的独立分支立即发布 Base Output。",
            "interactive_dag": "三种 Runtime 共用 Named Output、依赖、状态、缓存和局部失效协议。",
            "view_isolation": "View 只因自己的 Selection、内容绑定或输入 Output 变化而更新。",
            "identity": "Interaction 以 tab、Dashboard、Query Run、Transform、generation 隔离。",
            "server_interactive_cache": (
                "Query 计划显式标记 server_interactive_inputs；Server Compute 只读取该 tab Query Run 的 Artifact，"
                "不会重新执行 Source。运行数据位于 Workspace/.dataviz，不进入 Dashboard。"
            ),
        },
        "related": ["outputs", "dataset-transforms", "interactive-transforms"],
    },
    "workflow": {
        "summary": "按最小失败边界开发，避免把数据、计算和样式问题混在一起。",
        "steps": [
            {"stage": "Discover", "command": "dataviz list <workspace>"},
            {"stage": "Read", "command": "dataviz context <workspace> <dashboard> --focus view:<id> --format json"},
            {"stage": "Validate", "command": "dataviz validate <workspace> --dashboard <dashboard> --format json"},
            {"stage": "Query", "command": "dataviz query <workspace> <dashboard> --source <id>"},
            {"stage": "Inspect", "command": "dataviz output <workspace> <dashboard> <canonical-output>"},
            {"stage": "Compute", "command": "dataviz compute <workspace> <dashboard> <transform-id> --run-id <run>"},
            {"stage": "Render", "command": "dataviz report <workspace> <dashboard> --output report.html"},
            {"stage": "Interact", "command": "dataviz serve <workspace>"},
        ],
        "do_not": [
            "不要同时修改 SQL、Transform、View 字段和 CSS。",
            "不要在 Named Output 尚未正确时调图表 options。",
            "不要让 Presentation 脚本承载可测试的业务计算。",
        ],
    },
    "dashboard": {
        "summary": "dashboard.yaml 是分析逻辑；presentation.yaml 是可删除的视觉覆盖。",
        "schema": "dataviz/dashboard/v2",
        "identity": {
            "folder": "导航显示名及 ## 目录位置；复制、重命名和打包时所见即所得。",
            "id": "CLI、DAG、API 与 Presentation 使用的稳定程序身份。",
            "title": "页面内容，可与文件夹名不同；为空时回退到文件夹末级名称。",
        },
        "minimal_example": """schema: dataviz/dashboard/v2
kind: dashboard
id: sales-overview
title: 销售概览
subtitle: "仓 {{ parameters.warehouse_id }}"
query_parameters:
  - {id: warehouse_id, type: integer, label: 仓, default: 5740}
sources:
  - id: sales
    kind: source
    type: file
    path: data/sales.csv
    outputs: {main: {kind: table}}
views:
  - {id: trend, title: 收入趋势, input: source:sales/main, template: line, x: date, y: revenue}
sections:
  - {id: overview, title: 概览, views: [trend]}
""",
        "content_interpolation": {
            "parameter_syntax": "{{ parameters.<id> }}",
            "compute_syntax": "{{ compute.<id> }}",
            "selection_syntax": {
                "dashboard": "{{ selections.dashboard.<selection-id> }}",
                "section": "{{ selections.section.<section-id>.<selection-id> }}",
                "view": "{{ selections.view.<view-id>.<selection-id> }}",
            },
            "fields": [
                "dashboard title/subtitle/description/assumptions",
                "section title/description",
                "view title/description/markdown text",
            ],
            "lifecycle": {
                "query_parameter": "展示最近一次 Run query 已提交的值；草稿值不会伪装成当前结果。",
                "compute_parameter": "展示产生当前 Derived Output 的已提交值。",
                "selection": "浏览器 Selection 变化后即时更新可见文案与受影响 View。",
            },
        },
        "related": ["presentation", "selections", "compute-parameters"],
    },
    "adapters": {
        "summary": "连接配置属于 Workspace；可分享的 Dashboard 只引用逻辑 Adapter 名。",
        "supported": ["duckdb", "mysql", "starrocks", "sqlalchemy", "file root", "Python Source adapter config"],
        "rules": [
            "非敏感定义放在 auth/adapters.yaml；密码使用环境变量字段或未提交的 auth/adapters.local.yaml。",
            "更换团队环境只修改 Dashboard adapter 别名映射。",
            "内置类型只接受 file、duckdb、mysql、starrocks、sqlalchemy，不保留旧类型别名。",
            "validate 会检查被 Source 引用的 Adapter、文件路径和必需环境变量。",
            "Interactive Transform 永远没有 Adapter，不能借交互状态重新查数。",
            "Dataviz 会脱敏错误和日志；可信 Python Source 仍不得主动把 Adapter 凭据作为 Output 返回。",
        ],
    },
    "sources": {
        "summary": "Source 是唯一外部取数入口，类型为 file、sql 或 python。",
        "required": ["schema", "kind", "id", "type", "outputs"],
        "examples": {
            "file": "{schema: dataviz/source/v1, kind: source, id: sales, type: file, path: data/sales.csv, outputs: {main: {kind: table}}}",
            "sql": "{schema: dataviz/source/v1, kind: source, id: sales, type: sql, adapter: warehouse, code: sales.sql, query_params: [start_date], outputs: {main: {kind: table}}}",
            "python": "{schema: dataviz/source/v1, kind: source, id: api, type: python, code: api.py, outputs: {main: {kind: table}}}",
        },
        "timeouts": "SQL/Python 默认 120 秒；SQL timeout_retries 默认 1，超时后立即使用新连接重试。",
        "debug": "Server 的 Sources 面板公开参数化 SQL、解析后 SQL、绑定参数、Adapter 类型、超时和重试证据。",
    },
    "outputs": {
        "summary": "所有数据节点都必须声明类型明确且名称稳定的 Output。",
        "canonical_references": [
            "source:<id>/<name>",
            "dataset:<id>/<name>",
            "interactive:<id>/<name>",
        ],
        "kinds": ["table", "scalar", "object", "text", "html", "chart", "image", "file"],
        "rules": [
            "main 也必须显式声明和引用，不接受裸 id。",
            "返回值必须与声明名称完全一致；缺失或多余 Output 都失败。",
            "table 可声明列、dtype、nullable 与 required 作为节点边界契约。",
        ],
    },
    "dataset-transforms": {
        "summary": "Dataset Transform 在 Query DAG 中加工取数结果，并固化为 Base Output。",
        "schema": "dataviz/dataset-transform/v1",
        "runtime": "server-python",
        "example": """schema: dataviz/dataset-transform/v1
kind: dataset_transform
id: features
runtime: server-python
code: features.py
inputs: {sales: source:sales/main}
query_params: [start_date]
outputs:
  rows: {kind: table}
  total: {kind: scalar}
timeout_seconds: 120
""",
        "context": [
            "context.inputs / context.input(name) / context.table(name)",
            "context.query_params",
            "context.compute_params={} / context.selections={}",
            "context.adapter=None",
            "context.progress(value, message)",
            "context.log(message, level='info', **fields)",
        ],
        "behavior": [
            "独立 spawn 子进程、硬超时、完整 traceback 与日志 Artifact。",
            "缓存覆盖代码、递归声明依赖、包版本、Query Parameter、上游 hash 与 Source Adapter 指纹。",
            "Selection 和 Compute Parameter 不会执行 Query DAG。",
        ],
    },
    "interactive-transforms": {
        "summary": "Interactive Transform 在不可变 Query Run 上按 Selection/Compute Parameter 重算 Derived Output。",
        "schema": "dataviz/interactive-transform/v1",
        "common_fields": ["runtime", "inputs", "query_params", "compute_params", "selections", "trigger", "export", "outputs"],
        "runtimes": {
            "browser-js": "JavaScript Web Worker；Server 与 HTML 共用；支持 Promise、progress、timeout、cancel。",
            "browser-python": "Pyodide module Worker；支持纯 Python/Pyodide wheel；图表仍由 JS Renderer 绘制。",
            "server-python": "独立服务端进程；可用任意已安装 Python 依赖；不能访问 Adapter；HTML 只允许 snapshot/unavailable。",
        },
        "runtime_choice": {
            "default_order": ["browser-js", "browser-python", "server-python"],
            "rule": (
                "当三者都能清楚、可靠地表达同一逻辑且数据规模适合浏览器时，"
                "优先 browser-js，其次 browser-python，最后 server-python。"
            ),
            "reason": (
                "这个顺序优化启动开销、分发体积和 HTML 可移植性，不表示 JavaScript "
                "在所有算法上都比原生 Python 更快。原生依赖、大模型、运筹求解或大数据量仍应选择 server-python。"
            ),
        },
        "triggers": {
            "apply": "默认；用户提交相关草稿后执行。",
            "auto": "输入变化后 debounce，并取消同一 Transform 的旧 generation。",
            "manual": "仅明确指定 Transform 时执行，同时补齐其依赖闭包。",
        },
        "export_modes": {
            "interactive": "HTML 中继续计算；仅 browser-js/browser-python。",
            "snapshot": "导出时固化 Derived Output 及产生它的状态，相关控件只读。",
            "unavailable": "HTML 明确显示缺失能力与原因。",
        },
        "rules": [
            "只返回 Named Output，不接触 DOM，不调用 Renderer。",
            "输入只能是已声明 Base/Derived Output；没有 Adapter，也没有 Source API。",
            "server-python 输入来自同一 tab、Dashboard 和 Query Run 的不可变 Artifact；交互阶段禁止重查 Source。",
            "generation 采用最后写入获胜，旧任务不能覆盖新结果。",
            "server-python 可调用 context.progress 与 context.log；日志保存为结构化 Artifact。",
        ],
        "related": ["html-export", "compute-parameters", "outputs"],
    },
    "html-export": {
        "summary": (
            "HTML 固化 Query Run；只有 Browser Runtime 能在脱离 Dataviz Server 后继续计算。"
        ),
        "runtime_matrix": {
            "browser-js": "interactive/snapshot/unavailable；interactive 不需要 Python 或 Pyodide。",
            "browser-python": "interactive/snapshot/unavailable；interactive 需要 Pyodide CDN 或 bundle。",
            "server-python": (
                "只能 snapshot 或 unavailable。导出页没有 Python Server，不能继续执行模型、"
                "运筹或其他 server-python 逻辑。"
            ),
        },
        "pyodide_assets": {
            "cdn": (
                "下载较小的 HTML，打开时从 runtime.pyodide_index_url 加载 Pyodide；"
                "公司内网或离线环境可能失败。"
            ),
            "bundle": (
                "从 runtime.pyodide_bundle_path 复制已校验的本地 Pyodide 分发。CLI 输出 HTML + "
                "<name>.assets/pyodide + manifest；Server 下载 ZIP。它是自包含文件包，不是单一 HTML。"
            ),
            "bundle_contract": (
                "目录根部必须包含 pyodide.mjs、pyodide.asm.mjs、pyodide.asm.wasm、"
                "python_stdlib.zip、package.json 和 pyodide-lock.json。validate 会检查固定版本，"
                "按 Emscripten marker 继续检查 micropip、声明依赖的传递 wheel 闭包与必需 SHA-256。"
            ),
            "serve": (
                "bundle 报告应解压后通过 HTTP 静态服务打开；module Worker/WASM 不保证在 file:// 下工作。"
            ),
            "conditional": (
                "没有可执行 browser-python 分支时，报告不嵌入 Python Worker、不写 Pyodide URL，"
                "也不复制 Pyodide 资产。snapshot/unavailable 分支同样不携带无用 Runtime。"
            ),
            "other_assets": (
                "Pyodide bundle 不等于整页离线：Plotly 内嵌；ECharts/Arrow 只有配置本地文件时离线；"
                "Perspective 当前仍依赖 CDN。manifest 只判断声明的 Runtime/View 资产，不分析自定义脚本请求。"
            ),
        },
        "commands": [
            "dataviz report <workspace> <dashboard> --output report.html",
            "python -m http.server 8081 -d <report-directory>",
        ],
        "related": ["interactive-transforms", "pipeline", "troubleshooting"],
    },
    "compute-parameters": {
        "summary": "Compute Parameter 控制取数后的复杂分析，不创建新 Query Run。",
        "types": ["string", "number", "integer", "boolean", "date", "date_range", "single_select", "multi_select"],
        "lifecycle": [
            "draft：控件正在编辑但尚未产生当前结果。",
            "committed：Interactive Transform 本次执行使用的值。",
            "result state：内容绑定和 provenance 只描述真正产生当前 Output 的 committed 值。",
        ],
        "cli": "dataviz compute <workspace> <dashboard> <transform-id> --run-id <run> --compute-param seed=42",
    },
    "selections": {
        "summary": "Selection 是 include-only 的浏览器样本选择，可直接筛选 View，也可驱动 Interactive Transform。",
        "scopes": {
            "dashboard": "影响全部声明可见的 View。",
            "section": "影响该 Section 的 View。",
            "view": "只影响单个 View。",
        },
        "selector_choice": {
            "auto": "按类型、选项规模和 path_fields 确定组件。",
            "select": "大量平面选项；search/virtual 支持 auto/always/never。",
            "segmented": "少量单选。",
            "checkbox-group": "少量多选，支持全选、反选和逐项取消。",
            "cascader": "path_fields 定义的多级路径。",
            "tree-select": "树状多选与父子策略。",
            "date-range": "日期区间及 preset。",
        },
        "canonical_keys": [
            "dashboard:<dashboard-id>/<selection-id>",
            "section:<section-id>/<selection-id>",
            "view:<view-id>/<selection-id>",
        ],
        "behavior": [
            "级联上游域改变时，会移除不可用的下游已选值。",
            "直接 View Selection 不重绘无关 View。",
            "导出 HTML 保留完整 Dataset；Selection 是初始状态，不是导出裁剪。",
        ],
    },
    "renderers": {
        "summary": "Renderer 只消费 Named Output 和 View descriptor，不执行业务取数。",
        "view_templates": list(VIEW_TEMPLATE_CONTRACTS),
        "chart_engines": ["plotly", "echarts"],
        "lifecycle": ["validate", "mount", "update", "dispose"],
        "isolation": "一个 Renderer 失败只影响自己的 View；输入没有变化时不 update。",
    },
    "charts": {
        "summary": "默认图表模板覆盖常见 Plotly/ECharts 场景，业务逻辑留在 Transform。",
        "field_matrix": _CHART_FIELD_MATRIX,
        "rule": "先验证字段、聚合和 Named Output，再用 Presentation options 调视觉细节。",
    },
    "tables": {
        "summary": "普通 Table 用于可定制展示；Perspective 用于排序、筛选和透视分析。",
        "templates": {
            "table": "自定义列、格式、对齐、紧凑度和条纹样式。",
            "perspective": "Perspective v5 Web Component；拥有独立分析 UI 和配置。",
        },
        "scroll": "表格和 Perspective 仅在内部仍可滚动时消费滚轮；边界把滚轮交还页面。",
    },
    "repeated-views": {
        "summary": "一个 View 蓝图可按实体平铺或由 Selection 选择后重复。",
        "templates": {
            "small-multiples": "按 repeat.by 生成所有实体，支持分页、懒挂载与离屏回收。",
            "selection-gallery": "先搜索/级联选择实体，再只创建选中的 View 实例。",
        },
        "rule": "所有实例共享一个 Named Output，不为每个实体重复查询 Source。",
    },
    "presentation": {
        "summary": "可选 Presentation 按稳定 ID 覆盖布局、容器、Theme、Selector 和资源，不改变逻辑。",
        "file": "dashboard 文件夹中的 presentation.yaml；删除后退化为自上而下的默认布局。",
        "extension_path": ["默认模板", "模板参数", "Theme token", "局部 CSS class/options", "自定义 Renderer", "自定义 Canvas"],
        "non_goals": ["坐标/Mosaic 编辑器", "让 CSS 决定数据依赖", "在 Presentation 中保存密钥"],
    },
    "components": {
        "summary": "Component Registry 是 AI 选择 View、Section、Selector、Runtime 和扩展点的机器可读目录。",
        "commands": [
            "dataviz components --check --format json",
            "dataviz components <component-id> --format json",
            "dataviz scaffold --list --format json",
            "dataviz scaffold <recipe> --id <id> --format json",
            "dataviz gallery --output gallery.html",
        ],
        "scaffold_rule": "Component IDs and Scaffold recipes are related catalogs, not interchangeable names; discover recipes with scaffold --list.",
        "contract": [
            "logic fields",
            "behavior",
            "semantic DOM",
            "CSS tokens",
            "story",
            "test declarations",
        ],
        "check_scope": (
            "components --check validates Package metadata/assets and test declarations; "
            "pytest plus browser E2E execute behavior."
        ),
    },
    "ai-authoring": {
        "summary": "AI 应读取任务相关的最小契约，而不是整个 Runtime 源码。",
        "commands": [
            "dataviz context <workspace> <dashboard> --focus view:<id> --format json",
            "dataviz context <workspace> <dashboard> --focus dataset:<id> --format json",
            "dataviz context <workspace> <dashboard> --focus interactive:<id> --format json",
            "dataviz context <workspace> <dashboard> --focus component:<id> --format json",
            "dataviz benchmark <workspace> <dashboard>",
            "dataviz benchmark <workspace> <dashboard> --browser-runtime --format json",
            "dataviz authoring tasks --format json",
            "dataviz authoring protocol --format json",
            "dataviz authoring prepare <task> <directory> --approach dataviz|standalone-html --trial-id <trial>",
            "dataviz authoring start <measurement-workspace> --trial-dir <directory> --model <model> --tool <client>",
            "dataviz authoring assess <directory> <check-id> --status passed --assessor automation --evidence <evidence>",
            "dataviz authoring verify <directory> --format json",
            "dataviz authoring finish <measurement-workspace> <session> --trial-dir <directory> --outcome success --first-attempt success --correction-rounds 0",
            "dataviz authoring compare <measurement-workspace> --format json",
        ],
        "evaluation": {
            "design": "同一固定任务、模型、客户端/工具和权限做 Dataviz 与 standalone HTML 成对试验。",
            "quality_gate": "固定任务/approach prompt/输入 SHA-256；每条验收项必须记录 assessor 与证据。只有两边 prompt/输入完整并通过全部验收的 identity-matched pair 才进入效率聚合。",
            "measurements": [
                "client 实际报告的 input/output tokens",
                "首次成功率",
                "行为修正轮次",
                "完成时间",
                "分类 friction",
            ],
            "rule": "缺失 Token 保持 unmeasured；不按字符数或文件大小估算。",
        },
        "runtime_benchmark": {
            "purpose": "在 Chromium 中等待页面稳定后测量 Query、报告构建、页面就绪、Arrow 传输、Renderer 生命周期和 View 终态。",
            "schema": "dataviz/browser-runtime-benchmark/v2",
            "boundary": "它验证页面规模与生命周期，不估算 AI Token，也不替代成对 authoring trial。",
        },
        "goal": "先追求可用性和低试错；Token 节省比例只能由真实任务测量，不能预设。",
    },
    "schema-reference": {
        "summary": "schemas 命令直接由安装版本的严格 Pydantic 模型生成，不维护手写副本。",
        "commands": [
            "dataviz schemas --format json",
            "dataviz schemas dashboard --full --format json",
            "dataviz schemas interactive-transform --full --format json",
        ],
    },
    "validation": {
        "summary": "validate 是每次修改后的零查询静态门禁，优先把错误暴露给 AI。",
        "recommended_command": "dataviz validate <workspace> --dashboard <dashboard-id> --format json",
        "coverage": [
            "schema、未知字段、重复 ID 和本地路径边界",
            "显式 Output 引用、缺失 Output、两个 DAG 的环和跨 Runtime 非法依赖",
            "Query/Compute/Selection namespace 与 trigger 冲突",
            "Interactive export.mode、Pyodide 依赖和 bundle 资产",
            "SQL named parameter、Python 依赖和输入/输出 Schema",
            "View/Section/Presentation/Selector 引用",
        ],
        "json_contract": {
            "queries_executed": "固定为 0；静态验证不触发任何数据源。",
            "passed": "无 error；--strict 时 warning 也令 exit code 非零。",
            "diagnostic": "包含稳定 code、field/JSON path、file、details 和 hint。",
        },
        "sql_parameter_example": {
            "errors": ["sql_parameter_undeclared", "sql_parameter_unused"],
            "fix": "同时更新 SQL placeholder、Source query_params 和 Dashboard query_parameters。",
        },
    },
    "strict-schema": {
        "summary": "只接受当前 DSL；不提供 deprecated 层、字段别名、自动迁移或双协议 Runtime。",
        "current": {
            "dashboard": "dataviz/dashboard/v2",
            "runtime": "dataviz/runtime/v2",
            "dataset_transform": "dataviz/dataset-transform/v1",
            "interactive_transform": "dataviz/interactive-transform/v1",
        },
        "rules": [
            "未知字段 extra=forbid。",
            "旧 Dashboard、旧 Transform 名称和隐式 Output 引用直接报错。",
            "仓库示例与调用方必须一次性改写后再运行。",
        ],
    },
    "frontend-adapters": {
        "summary": "前端实现只消费 dataviz/runtime/v2 Manifest/Event/Output，不读取 Python 内部对象。",
        "commands": [
            "dataviz frontend-adapters --format json",
            "dataviz frontend-adapters web-component --output runtime-adapter.js",
        ],
        "public": ["canonical Named Output", "Selection/Compute state", "node lifecycle", "Renderer lifecycle"],
    },
    "versioning-release": {
        "summary": "版本发布验证当前契约，不把旧 DSL 重新带回发行包。",
        "commands": ["dataviz version", "uv build", "python scripts/build_release_zip.py"],
        "release_contract": [
            "Python 3.11–3.14 运行 unit/contract tests。",
            "Chromium/Firefox/WebKit 运行真实 Runtime tests。",
            "wheel、sdist、pip ZIP 在干净 venv 中运行 version/schemas/components/init/validate/report smoke。",
            "发行包排除 .venv、build、缓存和运行 Artifact。",
        ],
    },
    "runtime-limits": {
        "summary": "当前是可信单机 Runtime，但仍提供可预测的 timeout、cancel、缓存和清理。",
        "implemented": [
            "SQL/Python Source 与 Dataset Transform 独立进程；SQL 默认 120 秒并立即重试一次。",
            "server-python Interactive Transform 使用独立进程和 generation 取消。",
            "browser-js/browser-python 使用 Web Worker、timeout、supersede cancellation 和结构化错误。",
            "大 Table 自动使用 Arrow IPC；浏览器按需物化行。",
            "内置数值聚合使用线性 reducer，避免大数组展开触发 JavaScript 参数上限。",
            "节点独立发布，失败分支不阻塞无关分支。",
            "runtime.max_concurrent_runs 与 max_concurrent_interactions 分别限制单机并发 Query/Server 交互任务。",
            "Run Artifact 与 NodeCache 只写入 Workspace/.dataviz；默认缓存由 tab session 隔离，Server Interactive 复用同一 Query Run。",
            "Run、cache、Worker、PyProxy、Renderer 与订阅均有 dispose/淘汰路径。",
        ],
        "current_limits": [
            "可信本地 Python/JavaScript 不是不可信代码沙箱。",
            "没有多租户 CPU/内存配额。",
            "Server 与 HTML 仍传输完整可达 Output，未实现服务端分页。",
            "150K 行已有真实浏览器回归；固定 10K/100K/1M 内存预算仍待建立。",
            "修改 Workspace Runtime 并发上限后需要重启 Server，已有信号量不会热替换。",
            "只支持一个 Dataviz Server 进程写一个 Workspace/报告目标；协调锁不是跨进程锁。",
            "Server 没有账号体系或 HTTP 鉴权，默认只监听回环地址；非回环 --host 必须显式使用 --allow-remote，并由可信网络或外部代理负责访问控制。session_id 不是访问凭证。",
        ],
        "related": ["interactive-transforms", "maintenance"],
    },
    "maintenance": {
        "summary": "安全清理 Workspace 的 Run Artifact 和缓存。",
        "commands": [
            "dataviz clean <workspace>",
            "dataviz clean <workspace> --keep-runs 20 --run-max-age-hours 48",
            "dataviz clean <workspace> --all --apply",
        ],
        "rules": [
            "默认 dry-run；必须显式 --apply 才删除。",
            "只允许删除 Workspace/.dataviz/runs 与 cache 中的目标。",
            "活动 Query，以及仍被活动 Interaction 消费的 Query Run 和缓存始终受保护。",
        ],
    },
    "troubleshooting": {
        "summary": "沿 Pipeline 分层定位，保留可复查证据。",
        "triage": [
            {"symptom": "Workspace 无法加载", "action": "先运行 validate，修复 schema、路径和重复 ID。"},
            {"symptom": "Source 失败", "action": "单独 query；查看解析 SQL、Adapter、参数、timeout 和 traceback。"},
            {"symptom": "Dataset Transform 失败", "action": "output 目标闭包；检查 input schema、node.error.traceback 和 node.log。"},
            {"symptom": "Interactive Transform 失败", "action": "检查 Runtime、trigger、canonical state、generation 与 export.mode。"},
            {"symptom": "查询成功但 View 为空", "action": "检查 Named Output 字段、类型、Selection 后行数和 View input。"},
            {"symptom": "Server 正常但 HTML 失败", "action": "检查 export.mode；server-python 不能离线重算。browser-python 再检查 CDN/bundle、manifest，并通过 HTTP 打开。"},
            {"symptom": "源码环境 ModuleNotFoundError", "action": "在 dataviz-tool 下运行 uv sync --python 3.12 --extra dev --no-editable --reinstall-package workspace-dataviz；后续 CLI 使用 uv run --no-editable dataviz。"},
        ],
        "evidence": [
            "dataviz validate 的完整 JSON。",
            "query/output/compute 的状态、Node error、traceback、log 和 provenance。",
            "Sources 面板中的参数化 SQL 与解析 SQL。",
            "HTML 同目录的 manifest。",
        ],
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
