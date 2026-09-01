from __future__ import annotations

from typing import Any

from dataviz.protocols import (
    CURRENT_PROTOCOL_SCHEMAS,
    DASHBOARD_SCHEMA,
    DATASET_TRANSFORM_SCHEMA,
    DEPENDENCY_CONTRACT_SCHEMA,
    INTERACTIVE_TRANSFORM_SCHEMA,
    LAYOUT_CONTRACT_SCHEMA,
    RUNTIME_PROTOCOL_SCHEMA,
    STATE_SNAPSHOT_SCHEMA,
    TARGET_REFERENCE_SCHEMA,
    WORKSPACE_CHANGE_SCHEMA,
)
from dataviz.view_contracts import VIEW_TEMPLATE_CONTRACTS


DOC_CATALOG_SCHEMA = "dataviz/docs-catalog/v2"


AUTHORING_ROUTE_ALIASES = {
    "dashboard": "minimal",
    "simple": "minimal",
    "controls": "interactive",
    "control": "interactive",
    "interaction": "interactive",
    "renderer": "custom-renderer",
    "custom": "custom-renderer",
}

AUTHORING_DOCUMENTS: dict[str, dict[str, Any]] = {
    "minimal-dashboard": {
        "requires": ["adapter", "source", "view", "layout"],
        "purpose": "Build a declarative Dashboard without browser-side state or custom code.",
        "path": "Adapter → Source → View → Layout",
        "steps": [
            "Create a minimal Workspace scaffold.",
            "Bind each Source to a Workspace Adapter or a local file.",
            "Point each View at one complete Source output reference.",
            "Arrange Views with Sections and the default Layout contract.",
            "Run validate, report, then visual-check.",
        ],
    },
    "interactive-dashboard": {
        "requires": [
            "adapter", "source", "view", "layout", "named-output",
            "control", "interactive-transform", "dependency-closure",
        ],
        "purpose": "Add typed post-query Control state with explicit filter or value consumers.",
        "path": "Base Named Output + Control → Interactive Transform → Derived Named Output → View",
        "steps": [
            "Declare each consumer as mode: filter or mode: value; do not infer behavior from the Control component.",
            "Declare only the inputs consumed by the Interactive Transform.",
            "Inspect the compiled dependency closure before debugging Runtime behavior.",
            "Run validate, report, then visual-check.",
        ],
    },
    "custom-renderer": {
        "requires": [
            "adapter", "source", "view", "layout", "named-output",
            "renderer-contract", "renderer-lifecycle",
        ],
        "purpose": "Use trusted JavaScript only when built-in declarative Views cannot express the visual.",
        "path": "Named Output → Renderer Contract → validate/mount/update/dispose",
        "steps": [
            "Start from a working declarative Source and Named Output.",
            "Register one Renderer with validate, mount, update and dispose hooks.",
            "Let the platform own empty, restore, interaction, resize and export behavior.",
            "Run validate, report, then visual-check.",
        ],
    },
    "cascading-selection": {
        "requires": ["view", "control", "option-domain", "dependency-closure"],
        "purpose": "Filter a child choice Control's candidates from one or more direct parent Controls.",
        "path": "Base option domain → parent Control → child depends_on → explicit consumers",
        "steps": [
            "Put every candidate and parent field in one immutable Base table output.",
            "Declare only the child's direct parent in depends_on.",
            "Use initial for Select startup behavior; do not use default.",
            "Inspect the compiled control order before opening a browser.",
        ],
        "minimal_example": """controls:
  - id: province
    field: province
    type: multiple_select
    value_type: text
    initial: {mode: all}
    options: {mode: infer, source: source:stores/main}
sections:
  - id: geography
    title: Geography
    controls:
      - id: city
        field: city
        type: multiple_select
        value_type: text
        initial: {mode: all}
        depends_on: [dashboard.province]
        options: {mode: infer, source: source:stores/main}
    views: [stores]""",
        "allowed_fields": {
            "control": [
                "id", "field", "path_fields", "type", "value_type",
                "label", "initial", "required", "clearable", "depends_on", "options",
            ],
            "options": ["mode", "source"],
            "depends_on_prefixes": ["dashboard.", "section.", "view."],
        },
        "common_errors": [
            "Putting initial under options; initial belongs to the Select control.",
            "Listing transitive ancestors instead of only direct parents.",
            "Using an Interactive Output as an option domain; candidates must come from Base table outputs.",
            "Omitting a parent field from the child option-domain rows.",
        ],
        "validation_commands": [
            "dataviz validate <workspace> --dashboard <dashboard> --strict",
            "dataviz inspect dependencies <workspace> <dashboard> --format json",
            "dataviz visual-check <workspace> <dashboard> --target both",
        ],
    },
    "view-filter": {
        "requires": ["view", "control", "option-domain"],
        "purpose": "Filter one View directly with a View-scoped Control and no Interactive Transform.",
        "path": "Base Named Output + Control filter binding → filtered View",
        "steps": [
            "Place the Control under the target View's controls list.",
            "Declare an explicit control_inputs filter binding for that View input.",
            "Use a static closed enum or infer candidates from the immutable Base output.",
            "Keep the View input unchanged; the Runtime applies the include filter.",
        ],
        "minimal_example": """views:
  - id: orders
    title: Orders
    template: table
    input: source:orders/main
    controls:
      - id: region
        field: region
        type: multiple_select
        value_type: text
        initial: {mode: all}
        options: {mode: infer, source: source:orders/main}
    control_inputs:
      region: {mode: filter, control: view.region, field: region, inputs: [main], empty: match_none}""",
        "allowed_fields": {
            "control": [
                "id", "field", "path_fields", "type", "value_type",
                "label", "initial", "required", "clearable", "options",
            ],
            "binding_operators": ["auto", "equals", "in", "between", "contains", "gte", "lte", "gt", "lt"],
        },
        "common_errors": [
            "Adding an Interactive Transform for a direct include filter.",
            "Filtering on a field absent from the View's table input.",
            "Using default on a Select instead of initial.",
            "Omitting empty policy; passthrough and match_none are intentionally different.",
        ],
        "validation_commands": [
            "dataviz validate <workspace> --dashboard <dashboard> --strict",
            "dataviz inspect layout <workspace> <dashboard> --format json",
            "dataviz visual-check <workspace> <dashboard> --target both",
        ],
    },
    "browser-compute": {
        "requires": [
            "view", "control", "named-output", "interactive-transform", "dependency-closure",
        ],
        "purpose": "Recompute a Derived Named Output in a browser Worker after a value-bound Control changes.",
        "path": "Base Named Output + Control value binding → browser-js Transform → Derived Named Output → View",
        "steps": [
            "Use browser-js unless the calculation genuinely requires Python.",
            "Declare inputs and control_inputs with node-local aliases.",
            "Return the exact Named Output declared by outputs.",
            "Point the View at interactive:<transform>/<output>.",
        ],
        "minimal_example": """# dashboard.yaml
controls:
  - id: factor
    type: single_input
    value_type: number
    default: 2
interactive_transforms:
  - transforms/scale.yaml
views:
  - {id: scaled, title: Scaled values, template: table, input: interactive:scale/main}

# transforms/scale.yaml
schema: dataviz/interactive-transform/v4
id: scale
runtime: browser-js
code: scale.js
inputs: {rows: source:data/main}
control_inputs:
  factor: {mode: value, control: dashboard.factor}
outputs:
  main: {kind: table}
export: {mode: interactive}""",
        "allowed_fields": {
            "control": [
                "id", "type", "value_type", "label", "default",
                "required", "min", "max", "step",
            ],
            "interactive_transform": [
                "schema", "id", "runtime", "code", "inputs", "query_inputs",
                "control_inputs", "outputs", "trigger", "timeout_seconds", "export",
            ],
        },
        "common_errors": [
            "Reading global state directly instead of declaring a control_inputs alias.",
            "Pointing a View at the Transform id without an output name.",
            "Returning a shape that disagrees with the declared output kind.",
            "Choosing server-python for code that must remain interactive in portable HTML.",
        ],
        "validation_commands": [
            "dataviz validate <workspace> --dashboard <dashboard> --strict",
            "dataviz inspect dependencies <workspace> <dashboard> --format json",
            "dataviz report <workspace> <dashboard> --output report.html",
            "dataviz visual-check <workspace> <dashboard> --target both",
        ],
    },
}

AUTHORING_ROUTES: dict[str, dict[str, Any]] = {
    "minimal": {
        "summary": "Default path for a simple declarative Dashboard.",
        "inherits": [],
        "documents": ["minimal-dashboard"],
        "scaffolds": [
            "minimal", "source.file", "source.sql", "source.python",
            "view.metric", "view.line", "view.bar", "view.table",
        ],
        "commands": [
            "dataviz scaffold minimal --id <dashboard> --output <workspace>",
            "dataviz validate <workspace> --dashboard <dashboard> --format json",
            "dataviz report <workspace> <dashboard> --output report.html",
            "dataviz visual-check <workspace> <dashboard> --target both",
        ],
        "excludes": ["control", "interactive-transform", "renderer-contract"],
    },
    "interactive": {
        "summary": "Use only when browser-side state or post-query computation is required.",
        "inherits": ["minimal"],
        "documents": ["interactive-dashboard"],
        "scaffolds": [
            "interactive", "interactive-transform.browser-js",
            "interactive-transform.server-python",
        ],
        "commands": [
            "dataviz scaffold interactive --id <dashboard> --output <workspace>",
            "dataviz inspect dependencies <workspace> <dashboard> --format json",
        ],
        "excludes": ["renderer-contract"],
    },
    "custom-renderer": {
        "summary": "Use only when no built-in View can express the required visual.",
        "inherits": ["minimal"],
        "documents": ["custom-renderer"],
        "scaffolds": ["custom-renderer", "renderer.custom", "view.custom"],
        "commands": [
            "dataviz scaffold custom-renderer --id <dashboard> --output <workspace>",
            "dataviz components show renderer.custom --format json",
            "dataviz components gallery --output component-gallery.html",
        ],
        "excludes": ["control", "interactive-transform"],
    },
    "cascading-selection": {
        "summary": "Build a parent-child choice-Control candidate cascade.",
        "inherits": ["minimal"],
        "documents": ["cascading-selection"],
        "scaffolds": ["control.select", "control.cascader", "control.tree-select"],
        "commands": [
            "dataviz inspect dependencies <workspace> <dashboard> --format json",
        ],
        "excludes": ["interactive-transform", "renderer-contract"],
    },
    "view-filter": {
        "summary": "Apply one Control to an explicit View input through mode: filter.",
        "inherits": ["minimal"],
        "documents": ["view-filter"],
        "scaffolds": ["control.select", "control.checkbox-group"],
        "commands": [
            "dataviz inspect layout <workspace> <dashboard> --format json",
        ],
        "excludes": ["interactive-transform", "renderer-contract"],
    },
    "browser-compute": {
        "summary": "Compute a Derived Named Output in a browser Worker.",
        "inherits": ["minimal"],
        "documents": ["browser-compute"],
        "scaffolds": ["interactive", "interactive-transform.browser-js"],
        "commands": [
            "dataviz inspect dependencies <workspace> <dashboard> --format json",
            "dataviz report <workspace> <dashboard> --output report.html",
        ],
        "excludes": ["renderer-contract"],
    },
}


def _authoring_route_closure(route: str) -> list[str]:
    ordered: list[str] = []

    def visit(identifier: str) -> None:
        if identifier in ordered:
            return
        for parent in AUTHORING_ROUTES[identifier]["inherits"]:
            visit(parent)
        ordered.append(identifier)

    visit(route)
    return ordered


def resolve_authoring_route(
    task: str | None = None,
    *,
    component: str | None = None,
) -> dict[str, Any]:
    """Return the smallest documented concept closure for one authoring task."""
    if bool(task) == bool(component):
        raise ValueError("Choose exactly one of task or component")
    selected_component = None
    selected_definition = None
    if component:
        from dataviz.templates import component_catalog

        selected_component = component.strip()
        selected_definition = component_catalog().get(selected_component)
        if selected_definition is None:
            raise ValueError(f"Unknown Component: {selected_component}")
        if selected_component in {
            "view.custom", "renderer.custom", "service.charts", "service.tables",
            "view.renderer-lifecycle"
        }:
            route = "custom-renderer"
        elif (
            selected_component.startswith(("control.", "interactive-transform."))
            or selected_component == "runtime.control"
        ):
            route = "interactive"
        else:
            route = "minimal"
    else:
        normalized = str(task).strip().lower()
        route = AUTHORING_ROUTE_ALIASES.get(normalized, normalized)
        if route not in AUTHORING_ROUTES:
            raise ValueError(
                f"Unknown authoring task: {task}. Available: {', '.join(AUTHORING_ROUTES)}"
            )

    closure = _authoring_route_closure(route)
    document_ids = list(dict.fromkeys(
        document
        for identifier in closure
        for document in AUTHORING_ROUTES[identifier]["documents"]
    ))
    documents = {
        identifier: AUTHORING_DOCUMENTS[identifier]
        for identifier in document_ids
    }
    concepts = list(dict.fromkeys(
        concept
        for document in documents.values()
        for concept in document["requires"]
    ))
    if selected_component == "output.named":
        concepts.append("named-output")
    elif selected_component and selected_component.startswith("dataset-transform."):
        concepts.append("dataset-transform")
    scaffolds = list(dict.fromkeys(
        recipe
        for identifier in closure
        for recipe in AUTHORING_ROUTES[identifier]["scaffolds"]
    ))
    if selected_component and selected_component.startswith(
        ("view.", "section.", "control.", "dataset-transform.", "interactive-transform.")
    ):
        if selected_component not in scaffolds:
            scaffolds.append(selected_component)
    if selected_component == "renderer.custom" and selected_component not in scaffolds:
        scaffolds.append(selected_component)
    commands = list(dict.fromkeys(
        command
        for identifier in closure
        for command in AUTHORING_ROUTES[identifier]["commands"]
    ))
    for identifier, document in documents.items():
        missing = sorted(set(document["requires"]) - set(concepts))
        if missing:
            raise RuntimeError(f"Authoring document {identifier} has missing concepts: {missing}")
    return {
        "schema": "dataviz/authoring-route/v1",
        "task": route,
        "component": selected_component,
        "component_definition": selected_definition,
        "summary": AUTHORING_ROUTES[route]["summary"],
        "closure": closure,
        "concepts": concepts,
        "documents": documents,
        "scaffolds": scaffolds,
        "commands": commands,
        "excluded_concepts": AUTHORING_ROUTES[route]["excludes"],
    }


def authoring_route_catalog() -> dict[str, Any]:
    return {
        "schema": "dataviz/authoring-route-catalog/v1",
        "default": "minimal",
        "routes": {
            identifier: {
                "summary": definition["summary"],
                "inherits": definition["inherits"],
                "scaffold": identifier,
            }
            for identifier, definition in AUTHORING_ROUTES.items()
        },
        "commands": {
            "task": "dataviz docs --task <route> --format json",
            "component": "dataviz docs --component <component-id> --format json",
        },
    }


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
            "aggregate",
            "field_references",
        )
        if key in contract
    }
    for name in _CHART_TEMPLATES
    for contract in [VIEW_TEMPLATE_CONTRACTS[name]]
}


DOC_TOPIC_REDIRECTS = {
    "start": "quickstart",
    "build": "quickstart",
    "analysis": "analysis-quickstart",
    "analyze": "analysis-quickstart",
    "explore": "analysis-quickstart",
    "catalog": "catalog-discovery",
    "search": "catalog-discovery",
    "target": "target-references",
    "reference": "target-references",
    "result": "results",
    "evidence": "evidence-promotion",
    "promote": "evidence-promotion",
    "overlay": "analysis-overlays",
    "architecture": "pipeline",
    "dag": "dependencies",
    "graph": "dependencies",
    "dependency": "dependencies",
    "output": "outputs",
    "dataset-transform": "dataset-transforms",
    "interactive-transform": "interactive-transforms",
    "control": "controls",
    "data-entry": "data-entry-components",
    "input-component": "data-entry-components",
    "renderer": "renderers",
    "chart": "charts",
    "view": "charts",
    "source": "sources",
    "parameter": "query-parameters",
    "parameters": "query-parameters",
    "query-parameter": "query-parameters",
    "content": "dashboard",
    "interpolation": "dashboard",
    "title": "dashboard",
    "layout": "layout-contract",
    "style": "presentation",
    "visual": "design-language",
    "visual-language": "design-language",
    "theme-guide": "design-language",
    "diy-style": "design-language",
    "repeat": "repeated-views",
    "multiples": "repeated-views",
    "gallery": "components",
    "component": "components",
    "compact": "ai-authoring",
    "context": "ai-authoring",
    "progressive": "progressive-authoring",
    "authoring-route": "progressive-authoring",
    "benchmark": "runtime-performance",
    "export": "html-export",
    "html": "html-export",
    "offline": "html-export",
    "schema": "strict-schema",
    "schemas": "schema-reference",
    "validate": "validation",
    "preflight": "validation",
    "version": "versioning-release",
    "release": "versioning-release",
    "frontend-adapter": "frontend-adapters",
    "security": "runtime-limits",
    "performance": "runtime-performance",
    "cleanup": "maintenance",
    "clean": "maintenance",
    "reload": "hot-reload",
    "watch": "hot-reload",
    "serve": "hot-reload",
    "error": "troubleshooting",
    "debug": "troubleshooting",
}


DOC_PATHS: dict[str, dict[str, Any]] = {
    "build-and-verify": {
        "title": "构建与验证看板",
        "summary": "创建、校验、运行和交付 Dashboard。",
        "start": "quickstart",
        "workflow": [
            "quickstart", "progressive-authoring", "workflow", "validation",
            "design-language", "troubleshooting",
        ],
        "command": "dataviz docs quickstart",
    },
    "explore-and-execute": {
        "title": "探索与执行数据",
        "summary": "发现数据口径、执行 Target、复用 Result，并把审阅结论沉淀为 Evidence。",
        "start": "analysis-quickstart",
        "workflow": [
            "analysis-quickstart", "catalog-discovery", "target-references",
            "results", "analysis-overlays", "evidence-promotion", "troubleshooting",
        ],
        "command": "dataviz docs analysis-quickstart",
    },
    "operate-and-extend": {
        "title": "运行维护与扩展",
        "summary": "维护 Runtime、Component、Renderer、性能与发布边界。",
        "start": "runtime-limits",
        "workflow": [
            "runtime-limits", "maintenance", "components", "renderers",
            "frontend-adapters", "runtime-performance", "versioning-release",
        ],
        "command": "dataviz docs runtime-limits",
    },
}


DOC_TOPICS: dict[str, dict[str, Any]] = {
    "quickstart": {
        "summary": "从空环境到可验证 Dashboard、不可变 Result 和 HTML 报告的最短当前路径。",
        "workspace_start": {
            "starter_workspace": "dataviz init <workspace>",
            "focused_scaffold": "dataviz scaffold minimal --id <dashboard-id> --output <workspace>",
            "rule": "init 直接生成可运行的 hello Dashboard；需要特定结构或能力时，再选择对应 Scaffold recipe。",
        },
        "commands": [
            "dataviz version",
            "dataviz docs --task minimal --format json",
            "dataviz scaffold minimal --id <dashboard-id> --output <workspace>",
            "dataviz tree <workspace>",
            "dataviz inspect context <workspace> <dashboard-id> --focus view:<view-id> --format json",
            "dataviz inspect dependencies <workspace> <dashboard-id> --format json",
            "dataviz validate <workspace> --dashboard <dashboard-id> --format json",
            "dataviz run <workspace> <dashboard-id> --query-param key=value",
            "dataviz result inspect <workspace> <result-id>",
            "dataviz result show <workspace> <result-id> '<dashboard-id>::source:<id>/<output>'",
            "dataviz report <workspace> <result-id> --output report.html",
            "dataviz visual-check <workspace> <dashboard-id> --target both",
            "dataviz serve <workspace> --port 8080",
        ],
        "rules": [
            "不要从自定义 HTML/CSS/JS 开始；先用默认 Renderer 证明数据契约。",
            "Adapter 只在 Workspace 定义；Dashboard 只写逻辑别名，不保存账号密码。",
            "简单看板不要提前加载 Control、Interactive Transform 或 Custom Renderer 契约。",
            "所有 Output 引用必须写完整，例如 source:sales/main、dataset:model/trend、interactive:simulation/result。",
            "每次修改后运行 validate；未知字段、旧 schema 和不完整引用直接失败。",
            "serve 默认热更新 Workspace；Query Contract 改动只标记 Outdated，不会自动执行查询。",
            "自定义 Presentation/CSS 前读取 design-language；先覆盖 Theme token，再使用局部 css_class。",
        ],
        "success": [
            "validate 返回 passed=true。",
            "run 返回不可变 result_id；Result 终态为 ready，或按明确要求接受 partial。",
            "result inspect/show 只读取已封存 Artifact，不重新执行数据源。",
            "HTML report 生成，同时写出 report manifest。",
        ],
        "related": ["progressive-authoring", "workflow", "results", "design-language", "validation", "troubleshooting"],
    },
    "analysis-quickstart": {
        "summary": "让 AI 从业务语义发现可复用口径，先理解调用契约，再执行一次并复用不可变 Result。",
        "commands": [
            "dataviz catalog search <workspace> '收入|销售|日期' --top 5",
            "dataviz catalog describe <workspace> '<dashboard-id>::source:<source-id>/<output>' --format json",
            "dataviz run <workspace> '<dashboard-id>::source:<source-id>/<output>' --query-param key=value",
            "dataviz result inspect <workspace> <result-id>",
            "dataviz result show <workspace> <result-id> '<dashboard-id>::source:<source-id>/<output>' --offset 0 --limit 100",
            "dataviz result export <workspace> <result-id> '<dashboard-id>::source:<source-id>/<output>' --to <destination>",
        ],
        "workflow": [
            "不知道物理引用时先 catalog search；需要全局概览时使用 catalog list。",
            "执行前用 catalog describe 查看参数闭包、默认值、lineage、语义和可复制的 run 命令。",
            "run 只执行一次并原子封存 Result；预览行数不限制已保存的完整 Artifact。",
            "后续分页、检查、导出和 Evidence 都消费 result_id，不重新查询。",
            "只有需要临时替换 SQL、代码或 File 输入时才增加 --overlay。",
        ],
        "do_not": [
            "不要猜测已移除的短 alias；复制 Catalog 返回的 canonical Target Reference。",
            "不要为了查看更多行再次 run；使用 result show 分页。",
            "不要把 Catalog 命中等同于可信口径；检查 assurance、purpose、grain 和 caveats。",
        ],
        "related": ["catalog-discovery", "target-references", "results", "analysis-overlays", "evidence-promotion"],
    },
    "catalog-discovery": {
        "summary": "Catalog 是可删除重建的语义索引，只负责发现和描述，不执行数据。",
        "commands": [
            "dataviz catalog list <workspace>",
            "dataviz catalog search <workspace> '收入|工资|年入|月入' --top 10",
            "dataviz catalog describe <workspace> '<target-reference>' '<second-target-reference>' --format json",
            "dataviz catalog describe <workspace> '<target-reference>' --detail full --include-code --format json",
        ],
        "default_output": [
            "title、purpose、grain 和 assurance 是主体；kind、Dashboard 和物理引用是次级索引。",
            "紧凑附带 Query Parameter 契约、Output 摘要、相关 View、最小执行闭包和搜索命中原因。",
            "Source/View 命中默认投影到可复用 Output，避免与可复用 Output 平铺竞争。",
        ],
        "author_contract": {
            "required_for_discovery": ["title", "purpose", "grain"],
            "review_when_relevant": ["caveats", "visibility", "assurance", "measures", "relationships"],
            "rule": "Output 作者应说明这份数据回答什么问题、每行代表什么以及使用限制；不要只重复 Source/View 名称。",
        },
        "consistency": [
            "Catalog generation 由 Dashboard 定义 hash 驱动，可安全重建；它不是第二份业务事实来源。",
            "list/search/describe 不执行 Source、候选查询或 Transform，也不创建 Result。",
            "批量 describe 固定在同一 generation，保持输入顺序并逐项返回错误。",
        ],
        "related": ["target-references", "analysis-quickstart", "results", "outputs"],
    },
    "target-references": {
        "summary": "Target Reference v1 是 Catalog、run、Result 和 Evidence 共用的可读物理坐标。",
        "schema": TARGET_REFERENCE_SCHEMA,
        "grammar": [
            "<dashboard-id>",
            "<dashboard-id>::source:<source-id>",
            "<dashboard-id>::source:<source-id>/<output-name>",
            "<dashboard-id>::dataset:<transform-id>/<output-name>",
            "<dashboard-id>::interactive:<transform-id>/<output-name>",
            "<dashboard-id>::view:<view-id>",
        ],
        "rules": [
            "Dashboard id 是完整看板执行的 CLI 简写；其余字符串按 v1 grammar 严格解析。",
            "不接受 src_/base_/drv_/view_ 等生成式短 alias，也不按对象名或 Result ID 猜测。",
            "Source Target 可封存其全部声明 Output；--output 只选择一个。View Target 封存其直接数据输入与呈现映射。",
            "Derived Output 自动执行 Base 闭包和对应 Interactive Runtime。",
        ],
        "related": ["catalog-discovery", "results", "dependencies"],
    },
    "results": {
        "summary": "Result 是一次 Execution 的不可变公开事实；show、inspect、export、report 和 Evidence 都不得重跑。",
        "commands": [
            "dataviz result list <workspace> --status ready",
            "dataviz result inspect <workspace> <result-id> --detail full",
            "dataviz result show <workspace> <result-id> '<output-reference>' --offset 0 --limit 100",
            "dataviz result export <workspace> <result-id> '<output-reference>' --to <destination>",
            "dataviz report <workspace> <result-id> --output report.html",
        ],
        "terminal_statuses": {
            "ready": "目标闭包完成且所需 Output 可用。",
            "partial": "显式允许局部失败，并封存成功 Output 与失败证据。",
            "failed": "没有满足目标，但仍封存错误、日志、lineage 和已完成 Artifact。",
            "cancelled": "执行被取消并封存可审查终态。",
        },
        "storage": "默认位于 <workspace>/.dataviz/results/<result-id>/；manifest、hash、Artifact 和 provenance 发布后不可变。",
        "artifact_rules": [
            "--preview-rows 只影响 stdout，不截断完整 Artifact。",
            "show 分页读取；export 只复制一个选定的原生 Artifact，不转换格式、不修改 Result。",
            "直接 File Source 默认只封存实际读取的 path/hash 收据，不复制大型原文件；再次读取会核验变化。",
            "只有携带完整 Presentation 快照且 renderability 允许的 Dashboard/View Result 才能生成完整报告。",
        ],
        "related": ["analysis-quickstart", "evidence-promotion", "maintenance", "html-export"],
    },
    "analysis-overlays": {
        "summary": "Overlay 在内存中临时替换分析闭包的 SQL、代码或同格式 File 输入，不修改原 Dashboard。",
        "commands": [
            "dataviz run <workspace> '<target-reference>' --overlay experiment.yaml",
            "cat experiment.yaml | dataviz run <workspace> '<target-reference>' --overlay -",
        ],
        "rules": [
            "Overlay 只允许替换目标依赖闭包内的既有资产，不新增旁路 DAG。",
            "相对路径按 Overlay 文件位置解析；stdin Overlay 的相对路径按 Workspace 解析。",
            "Overlay 不写回 Dashboard、不进入 Catalog；Result provenance 记录原资产、替代资产和 Overlay hash。",
            "缓存 namespace 包含 Overlay hash，不能污染正式 Dashboard 的同名缓存。",
        ],
        "related": ["target-references", "results", "evidence-promotion"],
    },
    "evidence-promotion": {
        "summary": "Evidence 把 Result 中的结论变成可审阅证据；Promote 只生成可校验、可 Git 审查的补丁。",
        "commands": [
            "dataviz evidence create <workspace> <result-id> --question '<question>' --conclusion '<conclusion>' --snapshot-rows 10",
            "dataviz evidence promote <workspace> <evidence-id-or-json> proposal.yaml --dry-run --output promotion.patch",
        ],
        "evidence_contract": [
            "记录问题、结论/断言、Result 与 Output hash、lineage、生成者、审阅者和审阅状态。",
            "默认不复制完整大结果；可附带小型 snapshot 方便核验。",
            "Evidence 不是第二个知识数据库，原始数据变化时必须明确不可重现性。",
        ],
        "promotion_boundary": [
            "可提议新的 Transform/Named Output、semantics/caveat/deprecation 修订或契约测试/小型证据 snapshot。",
            "Promote 在隔离副本中 validate 并生成统一 diff，不直接修改 Workspace。",
            "新 Output 仍从 draft 开始；Promote 不自动 apply、reviewed 或 certified。",
        ],
        "related": ["results", "catalog-discovery", "analysis-overlays"],
    },
    "progressive-authoring": {
        "summary": "按任务返回最小作者概念闭包，简单看板不需要阅读完整 Runtime 架构。",
        "default": "minimal",
        "routes": authoring_route_catalog(),
        "commands": [
            "dataviz docs --task minimal --format json",
            "dataviz docs --task interactive --format json",
            "dataviz docs --task custom-renderer --format json",
            "dataviz docs --component control.select --format json",
            "dataviz scaffold --list --format json",
        ],
        "rules": [
            "minimal 只披露 Adapter → Source → View → Layout。",
            "只有任务需要查询后交互状态或计算时才进入 interactive。",
            "只有内置 View 无法表达视觉时才进入 custom-renderer。",
            "每条 Scaffold profile 都是完整 Workspace，并声明 validate → report → visual-check 验证链。",
            "任务路由控制作者上下文，不改变 Runtime 的严格 Schema 或执行语义。",
        ],
        "related": ["quickstart", "workflow", "components", "ai-authoring"],
    },
    "pipeline": {
        "summary": "稳定主链分成不可变取数阶段与可重复交互计算阶段。",
        "contract": [
            "Adapter → Source → Dataset Transform（可选）→ Base Named Output",
            "Base Named Output + Query Parameter 快照 + scoped Controls",
            "→ Interactive Transform（可选）→ Derived Named Output",
            "→ View Renderer → Presentation",
        ],
        "state_contract": {
            "query_parameters": "提交后创建新 Query Run，只进入声明依赖它们的 Source/Dataset Transform。",
            "controls": "Dashboard、Section、View 范围内的统一 typed state owner；Control 本身不声明消费语义。",
            "consumer_binding": "View/Interactive Transform 用 mode: filter 或 mode: value 显式解释同一 Control state。",
            "writer": "Control Component 与可选的 View selection gesture 只负责写 canonical state；影响范围由编译后的 binding graph 决定。",
        },
        "execution": {
            "compiled_contract": (
                f"每个 Dashboard load snapshot 以并发安全方式只编译并缓存一份 {DEPENDENCY_CONTRACT_SCHEMA}；"
                "Query planner、Interactive executor、Canvas、Server API 与浏览器 Runtime 都消费同一个对象。"
            ),
            "query_dag": "Source 与 Dataset Transform；完成的独立分支立即发布 Base Output。",
            "interactive_dag": "两种 Runtime 共用 Named Output、依赖、状态、缓存和局部失效协议。",
            "view_isolation": "View 只因自己的 Control binding、内容绑定或输入 Output 变化而更新。",
            "diagnostic_projection": (
                "Header 只显示 Query DAG 的 Source/Dataset 节点；每个 View 使用编译后的 pipeline_nodes "
                "在类型标签左侧显示自己的上游与 Renderer。View 灯只在活动、过期或失败时出现，Ready/Not run 隐藏；"
                "导出 HTML 因 Base Output 已固化，只显示端侧 Interactive/Renderer 的瞬时状态。"
            ),
            "identity": "Interaction 以 tab、Dashboard、Query Run、Transform、generation 隔离。",
            "server_interactive_cache": (
                "Query 计划显式标记 server_interactive_inputs；Server Interactive Transform 只读取该 tab Query Run 的 Artifact，"
                "不会重新执行 Source。运行数据位于 Workspace/.dataviz，不进入 Dashboard。"
            ),
        },
        "related": ["outputs", "dataset-transforms", "interactive-transforms"],
    },
    "dependencies": {
        "summary": "检查一个 Dashboard 编译后的 Query、Control、Interactive、Output 与 View 依赖契约。",
        "commands": [
            "dataviz inspect dependencies <workspace> <dashboard-id>",
            "dataviz inspect dependencies <workspace> <dashboard-id> --format json",
        ],
        "schema": DEPENDENCY_CONTRACT_SCHEMA,
        "graphs": {
            "query": (
                "Query Parameter → Source/Dataset Transform → immutable Base Named Output；"
                "同时列出最终失效的 Query/Interactive/option Control/View 闭包。"
            ),
            "control": (
                "Control 分开报告 scope_views、depends_on、传递祖先/后代、option domains、direct_view_bindings、"
                "runtime field checks、Transform aliases/consumers、derived_views、content_fields 与最终 affected_views。"
            ),
            "interactive": (
                "Base/Derived inputs → browser-js 或 server-python → Derived Named Output。"
            ),
            "render": "Named Output → direct View consumers；上游 Transform 另有完整 downstream Views。",
        },
        "initialization": [
            "Hydrate immutable Base Outputs。",
            "从 Base Outputs 推导候选型 Control 的 option domains。",
            "按编译后的 Control DAG 拓扑顺序协调候选域并提交 canonical Controls。",
            "先渲染 Base Views，再按编译顺序执行 Interactive DAG。",
        ],
        "rules": [
            "Control 不因自身类型自动筛选 View；View 或 Transform 必须用 mode: filter 显式声明输入、字段和空值策略。",
            "候选型 Control 只用 depends_on 声明直接父节点；Compiler 生成 control_order 和 dependency_ancestors。",
            "dashboard.<id>、section.<id>、view.<id> 相对当前 owner 解析，不能跨兄弟 Section/View。",
            "Browser 使用编译后的 Control DAG，不按 DOM 层级重建依赖。",
            "Browser 注册 payload 只检查契约漂移；Transform 调度、View waiting 和 Renderer 输入仍读取编译契约。",
            "mode: value 只向显式 consumer alias 投影 value、present 或 intent，不隐式筛选任何 View。",
            "Control 经 Transform 影响的 View 由 Derived Output 依赖反向索引决定。",
            "Query Parameter 变更创建新 Query Run；Control 变更不得触发 Source Query。",
            "Query/Interactive 节点只能读取自己显式声明的参数 alias。",
            "契约编译直接拒绝环、未知 Output、browser → server-python 非法边和越界 Control consumer。",
            "Loader recovery diagnostics 只服务无效配置定位，不构成第二张运行时 DAG。",
            "动态候选型 Control 在 canvas-hydration 阶段允许暂未解析，进入执行边界前必须成为合法值。",
        ],
        "related": ["pipeline", "controls", "interactive-transforms", "validation"],
    },
    "workflow": {
        "summary": "构建看板与探索数据是两条渐进路径；二者共享同一 Compiler、Runtime 和不可变 Result。",
        "build_and_verify": [
            {"stage": "Discover", "command": "dataviz tree <workspace>"},
            {"stage": "Read", "command": "dataviz inspect context <workspace> <dashboard> --focus view:<id> --format json"},
            {"stage": "Validate", "command": "dataviz validate <workspace> --dashboard <dashboard> --format json"},
            {"stage": "Layout", "command": "dataviz inspect layout <workspace> <dashboard> --format json"},
            {"stage": "Run", "command": "dataviz run <workspace> <dashboard>"},
            {"stage": "Inspect", "command": "dataviz result inspect <workspace> <result-id>"},
            {"stage": "Render", "command": "dataviz report <workspace> <result-id> --output report.html"},
            {"stage": "Visual", "command": "dataviz visual-check <workspace> <dashboard> --target both"},
            {"stage": "Interact", "command": "dataviz serve <workspace>"},
        ],
        "explore_and_execute": [
            {"stage": "Search", "command": "dataviz catalog search <workspace> '<regex>'"},
            {"stage": "Describe", "command": "dataviz catalog describe <workspace> '<target-reference>'"},
            {"stage": "Run", "command": "dataviz run <workspace> '<target-reference>' --query-param key=value"},
            {"stage": "Read", "command": "dataviz result show <workspace> <result-id> '<output-reference>'"},
            {"stage": "Explain", "command": "dataviz result inspect <workspace> <result-id> --detail full"},
            {"stage": "Preserve", "command": "dataviz evidence create <workspace> <result-id> --question '<question>' --conclusion '<conclusion>'"},
        ],
        "do_not": [
            "不要同时修改 SQL、Transform、View 字段和 CSS。",
            "不要在 Named Output 尚未正确时调图表 options。",
            "不要让 Presentation 脚本承载可测试的业务计算。",
        ],
    },
    "hot-reload": {
        "summary": "serve 监听 Workspace，并按影响边界更新页面而不擅自重新查询。",
        "commands": [
            "dataviz serve <workspace> --port 8080",
            "dataviz serve <workspace> --port 8080 --no-watch",
        ],
        "event_schema": WORKSPACE_CHANGE_SCHEMA,
        "impact_matrix": {
            "navigation": "Dashboard 目录新增、移除、改名；只更新导航。",
            "canvas": "内容、View、Presentation、CSS/JS；重载 Canvas 并保留 Run/Controls/滚动。",
            "analysis": "Interactive Transform 或 Control Contract；复用 Base Output 重算。",
            "query": "Query Parameter、Adapter、Source、数据文件或 Dataset Transform；标记 Outdated，等待用户执行 RUN。",
            "server": "Workspace Runtime/进程级设置；明确提示重启 Server。",
            "invalid": "新的 Workspace load snapshot 无效；保留上一份完整 Canvas 并显示诊断。",
        },
        "rules": [
            "活动 Query 使用启动时的不可变 Workspace 快照。",
            "查询运行途中发生 Query 变化时，旧 Run 成功也不会提交为当前结果。",
            "页面刷新和 tab 恢复会在 Server 再次核验 Query Contract。",
            "Header Reload 是显式兜底；--no-watch 只关闭主动文件通知。",
            "修改 Dataviz 自身 Python Server 源码仍需要重装并重启。",
        ],
        "related": ["workflow", "pipeline", "troubleshooting"],
    },
    "dashboard": {
        "summary": "dashboard.yaml 是分析逻辑；presentation.yaml 是可删除的视觉覆盖。",
        "schema": DASHBOARD_SCHEMA,
        "state_summary": {
            "schema": STATE_SNAPSHOT_SCHEMA,
            "behavior": "Runtime 始终维护已提交 Query、Control current/applied state 与各 consumer 的 applied revision；State Snapshot 按编译契约规范化 effective/applied/stale，Result 与 Evidence 继承该审计证据，但默认不把它机械复述到画布。",
            "presentation": "仅在确有分析价值时设置 presentation.state_summary.enabled: true；items 可按 canonical Control key 调整 label/order/hidden/formatter，且不允许改写状态值。",
        },
        "identity": {
            "folder": "导航显示名及 ## 目录位置；复制、重命名和打包时所见即所得。",
            "id": "CLI、DAG、API 与 Presentation 使用的稳定程序身份。",
            "title": "页面内容，可与文件夹名不同；为空时回退到文件夹末级名称。",
        },
        "minimal_example": """schema: dataviz/dashboard/v14
kind: dashboard
id: sales-overview
title: 销售概览
subtitle: "仓 {{ parameters.warehouse_id }}"
query_parameters:
  - {id: warehouse_id, type: single_input, value_type: integer, label: 仓, default: 5740}
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
            "control_syntax": {
                "dashboard": "{{ controls.dashboard.<control-id> }}",
                "section": "{{ controls.section.<section-id>.<control-id> }}",
                "view": "{{ controls.view.<view-id>.<control-id> }}",
            },
            "fields": [
                "dashboard title/subtitle/description/assumptions",
                "section title/description",
                "view title/description/markdown text",
            ],
            "lifecycle": {
                "query_parameter": "展示最近一次 RUN 已提交的值；草稿值不会伪装成当前结果。",
                "control": "展示 canonical Control state；value/filter consumer 根据 trigger 决定即时更新或提交后重算。",
            },
        },
        "related": ["layout-contract", "presentation", "controls", "interactive-transforms"],
    },
    "layout-contract": {
        "summary": "Dashboard owns page structure; the compiler emits the only deterministic Layout Contract consumed by every renderer.",
        "schema": LAYOUT_CONTRACT_SCHEMA,
        "example": """layout: {template: overview, columns: 12, gap: 18}
views:
  - {id: trend, template: line, input: source:sales/main, x: day, y: revenue, span: 8}
  - {id: detail, template: table, input: source:sales/main, span: 4}
sections:
  - {id: overview, template: chart-and-table, views: [trend, detail]}
""",
        "ownership": {
            "dashboard": "Section/View order, Section template and columns, View span, global columns and gap.",
            "presentation": "Theme, container appearance, min_height, component appearance, visual renderer options and local assets only.",
            "custom_canvas": "Contract mode=custom exposes stable Section/View mount IDs but does not pretend arbitrary CSS has a static grid.",
        },
        "rules": [
            "Explicit view.span wins over a template default; a template may not silently discard it.",
            "single requires one View; split/comparison/chart-and-table require two; repeat templates require one blueprint View.",
            "validate compiles the Layout Contract without querying and rejects unknown Views, duplicate placement, invalid cardinality and span overflow.",
            "Server, exported HTML, AI context and the default Renderer consume the same compiled object.",
        ],
        "related": ["dashboard", "presentation", "validation"],
    },
    "query-parameters": {
        "summary": "Query Parameter 创建不可变 Query Run；每个参数只保存一份 canonical state，SQL 候选统一由 Server 共享物化并通过 Lookup 搜索或分页。",
        "dynamic_domains": {
            "purpose": "一个 SQL Domain 物化一张完整候选关系；多个 Query Parameter 可从不同字段去重投影，父级变化只在该 generation 上过滤，不重跑 SQL。",
            "example": """parameter_domains: [workspace:/parameter_domains/locations/domain.yaml]
query_parameters:
  - id: province
    type: multiple_select
    value_type: text
    default: {mode: include, values: [GD]}
    options: {mode: domain, source: locations, value_field: province_code, label_field: province_name}
  - id: city
    type: multiple_select
    value_type: text
    default: {mode: all}
    options:
      mode: domain
      source: locations
      value_field: city_code
      label_field: city_name
      depends_on: {province: {field: province_code}}
""",
            "rules": [
                "Parameter Domain 只提供候选发现与标签，不产生 Named Output、Result 或 Catalog 条目，也不是 Source 参数白名单。",
                "所有 SQL Domain 都先形成 Workspace 共享 immutable generation；Browser 永远不接收原始关系、SQL、Adapter、物化路径或候选全集。",
                "同一个 Workspace Domain、定义/代码 hash、Adapter identity 与 visibility scope 可以跨 Dashboard、tab 和用户复用；权限范围不同不得共用。",
                "options.depends_on 只对当前 generation 做本地 predicate；搜索、级联和 cursor 分页都不重新执行远端 SQL。",
                "multiple_select 使用 all/include/exclude/none 紧凑集合；all/none 不带 operands，include/exclude 只保存有限例外，绝不展开 10 万候选。",
                "Query Card 的 reload 请求刷新共享物化；已有 generation 时继续读旧数据，不清空选择、不恢复 default、不执行正式 Query。",
                "每次成功 Query 都封存完整 committed canonical state；Revert 按依赖拓扑恢复该 state，不恢复 default，也不执行正式 Query。",
                "最新 generation 中缺失的 committed operand 仍显示为 unavailable，不会静默删除。",
                "Domain 失败只禁用当前 Dashboard 的查询；切换 Dashboard 会取消旧请求，损坏的草稿不能锁住 Shell 导航。",
                "dataviz run 不隐式物化或查询候选；已知参数值的 AI 可直接提交 canonical state。",
                "portable HTML 与分享链接只携带已提交 canonical state，不嵌入 Parameter Domain、候选页、cursor 或物化数据。",
            ],
            "inspect": "dataviz schemas parameter-domain --full --format json",
            "operations": [
                "dataviz parameters prewarm <workspace> <dashboard>",
                "dataviz parameters status <workspace> [dashboard]",
                "dataviz parameters lookup <workspace> <dashboard> <parameter> --search <text> --limit 10",
                "dataviz parameters refresh <workspace> <dashboard>",
                "dataviz bundle <workspace> <dashboard> <destination>",
            ],
        },
        "date_range": {
            "definition": """- id: job_date_range
  type: range_input
  value_type: date
  required: true
  default:
    - {mode: relative, anchor: today, offset: -3d}
    - {mode: relative, anchor: today, offset: -1d}
""",
            "binding": """query_inputs:
  start_date: {parameter: job_date_range, part: start}
  end_date: {parameter: job_date_range, part: end}
""",
        },
        "relative_defaults": [
            "range_input/date 由两个独立 Date Atom 组成，每个端点可用固定 ISO 日期或 {mode: relative, anchor: today, offset: -1d}。",
            "当前严格契约只接受 anchor=today 与整数日偏移 ±Nd/0d。",
            "today 按 workspace.context.timezone 计算，不使用 Server 操作系统时区。",
            "Run 创建时固化为 ISO 日期；缓存、SQL、HTML Export 均使用固化值，不在导出文件中重新求值。",
        ],
        "query_inputs": [
            "key 是节点本地别名，也是 SQL named placeholder 或 context.query_inputs 的 key。",
            "字符串值是 {parameter: <id>, projection: value} 的简写。",
            "part=start/end 仅允许投影 range_input/date；validate 在查询前拒绝错误类型。",
            "candidate multiple 可投影 selection=all/include/exclude/none、有限 value operands、active 约束状态，或把完整 state 交给 Python。",
            "SQL 优先使用 Source query_filters 与 {{ dataviz_filter:<name> }}，由 Adapter 参数化生成 TRUE/FALSE/IN/NOT IN，永不产生 IN ()。",
            "直接消费 candidate multiple 的 value 时必须同时消费 selection，避免把 exclude operands 错当成 include。",
        ],
        "selection_binding": """query_inputs:
  city_values: cities
  city_selection: {parameter: cities, projection: selection}
""",
        "related": ["sources", "dataset-transforms", "interactive-transforms", "data-entry-components"],
    },
    "adapters": {
        "summary": "连接配置属于 Workspace；可分享的 Dashboard 只引用逻辑 Adapter 名。",
        "supported": ["duckdb", "mysql", "starrocks", "sqlalchemy", "file root", "Python Source adapter config"],
        "rules": [
            "非敏感定义放在 auth/adapters.yaml；密码使用环境变量字段或未提交的 auth/adapters.local.yaml。",
            "更换团队环境只修改 Dashboard adapter 别名映射。",
            "内置类型只接受 file、duckdb、mysql、starrocks、sqlalchemy，不保留旧类型别名。",
            "validate 会检查被 Source 或 Parameter Domain 引用的 Adapter、文件路径和必需环境变量。",
            "Interactive Transform 永远没有 Adapter，不能借交互状态重新查数。",
            "Dataviz 会脱敏错误和日志；可信 Python Source 仍不得主动把 Adapter 凭据作为 Output 返回。",
        ],
    },
    "sources": {
        "summary": "Source 是唯一进入分析 DAG 的外部取数入口，类型为 file、sql 或 python；Parameter Domain 只能查询网页候选元数据，不产生分析 Output。",
        "required": ["schema", "kind", "id", "type", "outputs"],
        "examples": {
            "file": "{schema: dataviz/source/v4, kind: source, id: sales, type: file, path: data/sales.csv, outputs: {main: {kind: table}}}",
            "sql": "{schema: dataviz/source/v4, kind: source, id: sales, type: sql, adapter: warehouse, code: sales.sql, query_inputs: {start_date: start_date}, outputs: {main: {kind: table}}}",
            "python": "{schema: dataviz/source/v4, kind: source, id: api, type: python, code: api.py, outputs: {main: {kind: table}}}",
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
        "schema": DATASET_TRANSFORM_SCHEMA,
        "runtime": "server-python",
        "example": """schema: dataviz/dataset-transform/v3
kind: dataset_transform
id: features
runtime: server-python
code: features.py
inputs: {sales: source:sales/main}
query_inputs: {start_date: start_date}
outputs:
  rows: {kind: table}
  total: {kind: scalar}
timeout_seconds: 120
""",
        "context": [
            "context.inputs / context.input(name) / context.table(name)",
            "context.query_inputs",
            "context.adapter=None",
            "context.progress(value, message)",
            "context.log(message, level='info', **fields)",
        ],
        "behavior": [
            "独立 spawn 子进程、硬超时、完整 traceback 与日志 Artifact。",
            "缓存覆盖代码、递归声明依赖、包版本、Query Parameter、上游 hash 与 Source Adapter 指纹。",
            "任何 scoped Control 都不会执行 Query DAG。",
        ],
    },
    "interactive-transforms": {
        "summary": "Interactive Transform 在不可变 Query Run 上按编译后的 Control consumer bindings 重算 Derived Output。",
        "schema": INTERACTIVE_TRANSFORM_SCHEMA,
        "common_fields": ["runtime", "inputs", "query_inputs", "control_inputs", "trigger", "export", "outputs"],
        "runtimes": {
            "browser-js": "JavaScript Web Worker；Server 与 HTML 共用；支持 Promise、progress、timeout、cancel。",
            "server-python": "独立服务端进程；可用任意已安装 Python 依赖；不能访问 Adapter；HTML 只允许 snapshot/unavailable。",
        },
        "runtime_choice": {
            "default_order": ["browser-js", "server-python"],
            "rule": (
                "浏览器内 snapshot 数据加工和便携交互使用 browser-js；"
                "完整 Python 生态、复杂模型或重型计算使用 server-python。"
            ),
            "reason": (
                "浏览器 Runtime 受浏览器内存、CPU 和资产边界约束；作者语言偏好不构成新增 Runtime 的理由。"
            ),
        },
        "triggers": {
            "auto": "browser-js 默认；输入变化后 debounce，并取消同一 Transform 的旧 generation。",
            "apply": "server-python 默认；用户提交相关草稿后执行。",
            "manual": "仅明确指定 Transform 时执行，同时补齐其依赖闭包。",
        },
        "export_modes": {
            "interactive": "HTML 中继续计算；仅 browser-js。",
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
        "related": ["html-export", "controls", "outputs"],
    },
    "html-export": {
        "summary": (
            "HTML 从已封存 Result 的数据与 Presentation 快照生成；只有 Browser Runtime 能在脱离 Dataviz Server 后继续计算。"
        ),
        "runtime_matrix": {
            "browser-js": "interactive/snapshot/unavailable；interactive 在 JavaScript Worker 中执行。",
            "server-python": (
                "只能 snapshot 或 unavailable。导出页没有 Python Server，不能继续执行模型、"
                "运筹或其他 server-python 逻辑。"
            ),
        },
        "commands": [
            "dataviz report <workspace> <result-id> --output report.html",
            "dataviz report <workspace> <dashboard> --output report.html  # convenience: run once, seal Result, then render",
            "python -m http.server 8081 -d <report-directory>",
        ],
        "related": ["interactive-transforms", "pipeline", "troubleshooting"],
    },
    "controls": {
        "summary": "Control 是 Query 后统一的 typed state owner；筛选或计算含义由 consumer binding 显式声明。",
        "scopes": {
            "dashboard": "在 dashboard.controls 声明，影响全部可见 View。",
            "section": "在 section.controls 声明，影响该 Section 的 View。",
            "view": "在 view.controls 声明，只影响单个 View。",
        },
        "consumer_modes": {
            "filter": "对指定 View/Transform 输入应用字段筛选；empty 必须选择 passthrough 或 match_none。",
            "value": "把 Control 值、present 状态或 intent 投影为 Interactive Transform 的局部 alias。",
        },
        "filter_operators_by_value_type": {
            "text": ["equals", "in", "contains"],
            "integer": ["equals", "in", "between", "gte", "lte", "gt", "lt"],
            "number": ["equals", "in", "between", "gte", "lte", "gt", "lt"],
            "date": ["equals", "in", "between", "gte", "lte", "gt", "lt"],
            "boolean": ["equals", "in"],
            "rules": (
                "比较类型只来自 Control.value_type；number/integer 使用数值比较，date 使用规范 ISO 日期，"
                "text 不做词法排序，boolean 不做有序比较。between 的 null 端点表示开放边界，0 不是空值；"
                "字段或 bound 不可转换时返回稳定错误，不按行猜类型。"
            ),
        },
        "dashboard_example": """controls:
  - id: region
    type: multiple_select
    value_type: text
    field: region
    initial: {mode: all}
    options:
      mode: static
      choices:
        - {label: 华东, value: east}
        - {label: 华南, value: south}
  - id: simulations
    type: single_input
    value_type: integer
    default: 100000
    min: 1000
    max: 1000000
""",
        "interactive_input_example": """control_inputs:
  simulations: {mode: value, control: dashboard.simulations}
  region:
    mode: filter
    control: dashboard.region
    field: region
    inputs: [rows]
    empty: match_none
""",
        "component_choice": {
            "auto": "按 value type、choices 数量、suggestions 和 path_fields 确定 Data Entry component。",
            "input": "自由文本；multiline 只改变展示，不改变 string value。",
            "input-number": "有界 number/integer；min/max/step 属于逻辑契约。",
            "auto-complete": "自由文本 + suggestions；建议不是封闭枚举。",
            "checkbox": "随所在 Query/Control 工作流提交的 boolean。",
            "switch": "立即发出 input/change 的 boolean；执行策略仍由外层工作流决定。",
            "radio-group": "少量可见单选；不合成 All/Clear。",
            "select": "平面单选或多选；search/virtual 支持 auto/always/never。单选不提供批量操作。",
            "checkbox-group": "2–5 个并列选项的直接多选；不显示全选、反选或清空工具栏。",
            "cascader": "用 path_fields 逐级浏览并选择完整路径。",
            "tree-select": "在窄弹层中搜索、展开和选择层级路径。",
            "date-picker": "选择一个 ISO 日期，遵守 min_date/max_date。",
            "range-picker": "一个触发器与一个弹层共同编辑 [start, end]。",
            "slider": "在 min/max/step 约束内调整 number/integer。",
        },
        "canonical_keys": [
            "dashboard:<dashboard-id>/<control-id>",
            "section:<section-id>/<control-id>",
            "view:<view-id>/<control-id>",
        ],
        "behavior": [
            "Single Select 不出现 All、Select all 或 Invert；optional + clearable 的单选允许 Clear，required single 始终恰好一个值且拒绝 clearable。",
            "Control canonical state 是 {value, revision, intent?}；候选型多选可带 all_available/explicit intent，自由集合只保存 list value。",
            "Multi Select 和 Date Range 用 required 控制是否允许空值；clearable 可显式关闭清空操作，required: true 与 clearable: true 会被 validate 拒绝。",
            "候选依赖用 depends_on 声明直接 Control 父节点；Compiler 计算传递闭包和拓扑顺序。",
            "Dashboard Control 只可依赖 dashboard.*；Section 可再依赖本 section.*；View 可再依赖自身 view.*。",
            "上游域改变时，下游 all_available 跟随全部新候选；explicit 优先保留有效交集，原非空选择完全失效才恢复 initial，用户主动空集保留。",
            "Select 必须显式声明 options.mode；static 表示封闭业务枚举，infer 表示从数据推导候选域。",
            "options.mode=static 的 choices 是权威白名单；Source 中未声明的成员会被有意排除。",
            "Control Select 使用 initial：多选为 all/empty/values，单选为 first/empty/value；Query Parameter 统一使用 default，候选多选声明 all/include/exclude/none。",
            "infer 未写 source 时，Runtime 从消费 View 背后的 Base Output 建立选项域；不会从依赖该 Control 的 Derived Output 反推。",
            "多输入或需要明确数据域时使用 options.source: source:<id>/<name> 或 dataset:<id>/<name>；Interactive Output 会被 validate 拒绝。",
            "View Control 不重绘无关 View。",
            "导出 HTML 保留完整 Dataset；Control state 是导出时锁定的交互快照，不是 Query 裁剪。",
            "View 与 Interactive Transform 都用 control_inputs 声明局部 alias 和 mode，不从 Control type 猜测行为。",
            "Runtime 在 Transform 代码执行前应用 mode: filter，并把 mode: value 投影到 context.control_inputs。",
        ],
        "view_control_binding": {
            "summary": "一个 Control 可由多个经过 Compiler 校验的 Bound View 写入；Control Component 与所有合法 View selection gesture 都只向同一 ControlRuntime 发送 typed action。",
            "example": """views:
  - id: store-map
    input: source:stores/main
    template: scatter
    x: lng
    y: lat
    control_binding:
      control: section.selected_store
      field: store_id
""",
            "supported": ["Plotly point/selection event", "Table row", "typed Custom Renderer outlet"],
            "rules": [
                "Control owns values and candidate domain; it never declares highlight, row, cell, Renderer or callback.",
                "The bound View receives candidate rows after ancestor Controls but before the target Control filters itself.",
                "A View event can only dispatch select, select_many, clear or reset through context.controlBinding.emit; clear is explicit empty while reset restores the declared initial policy.",
                "Unknown targets, duplicate writer edges from one View, narrower reverse-scope candidate dependencies, ambiguous aggregate mappings, unsupported Renderers and missing fields fail validation; multiple valid Views may write the same Control.",
            ],
        },
        "dynamic_option_example": """controls:
  - id: dow
    type: single_select
    value_type: text
    field: dow
    initial: {mode: first}
    options:
      mode: infer
      source: source:forecast-series/main
  - id: job_date
    type: multiple_select
    value_type: text
    field: job_date
    initial: {mode: all}
    depends_on: [view.dow]
    options:
      mode: infer
      source: source:forecast-series/main
""",
        "interactive_cli": "dataviz run <workspace> '<dashboard>::interactive:<transform-id>/<output>' --control dashboard:<dashboard>/<id>=42",
        "related": ["data-entry-components", "interactive-transforms", "presentation"],
    },
    "data-entry-components": {
        "summary": "Query Parameter 与 Control 共用同一套独立 Data Entry Component；生命周期、consumer binding 和 UI 组件是三个正交维度。",
        "architecture": {
            "value": "dashboard.yaml 定义 type、default、required、options/suggestions、min/max/step、path_fields 等可验证逻辑。",
            "scope": "Query，或 dashboard/section/view 范围内的 Control。",
            "component": "presentation.yaml 的 control_components.<canonical-key>.component 只选择交互表现；span: 1|2 是独立的排版选择。",
            "runtime": "runtime.control 管理 canonical native value、事件、键盘与浮层生命周期；每个 control.* 包只实现一个组件。",
        },
        "ant_design_alignment": {
            "policy": "对齐 Ant Design 的组件边界、值形状、状态与交互语义；当前 Runtime 不引入 React/Ant 依赖，以保持 Server、单文件 HTML 和离线导出的同构能力。",
            "implemented": {
                "control.input": "Ant Input / Input.TextArea；string、max_length、prefix/suffix、count。",
                "control.input-number": "Ant InputNumber；number/integer、min/max/step、step controls。",
                "control.auto-complete": "Ant AutoComplete；自由 string + suggestions，不等同 Select。",
                "control.checkbox": "Ant Checkbox；一个 staged boolean。",
                "control.switch": "Ant Switch；一个 immediate boolean。",
                "control.radio-group": "Ant Radio.Group；一个真实 scalar choice，无 All/Clear。",
                "control.select": "Ant Select；单/多选、分组、搜索、max tag、虚拟列表。",
                "control.checkbox-group": "Ant Checkbox.Group；2–5 个小规模显式多选，无批量工具栏。",
                "control.cascader": "Ant Cascader；完整层级 path，单选或多选。",
                "control.tree-select": "Ant TreeSelect；可搜索、展开的层级 path。",
                "control.date-picker": "Ant DatePicker；单个 ISO date。",
                "control.range-picker": "Ant DatePicker.RangePicker；一个弹层编辑两个日期。",
                "control.multiple-input": "开放的有序值列表；支持 text/integer/number/date。",
                "control.slider": "Ant Slider；单值或双端 numeric range、marks、tooltip 和可选同步输入框。",
            },
            "composition": {
                "Form": "不是 value component；由 control_panels 和 Query/Control 生命周期组合 label、description、validation、layout 与 submit/apply。",
            },
            "deferred": {
                "TimePicker": "当前 DSL 没有 time/time_range value type；先不制造 string 伪语义。",
                "Transfer": "适合数百项的显式候选/已选双栏；待真实分析场景与窄屏契约验证。",
            },
            "not_default_analytics_controls": {
                "ColorPicker": "更适合 Theme/Presentation 编辑器，而不是分析参数。",
                "Mentions": "没有通用分析参数语义。",
                "Rate": "可由 Radio/Slider 表达，除非出现稳定评分录入场景。",
                "Upload": "属于 Source/Adapter 数据接入和安全边界，不属于浏览器筛选控件。",
            },
        },
        "auto_resolution": [
            "path_fields → cascader",
            "range_input/date → range-picker；single_input/date → date-picker",
            "range_input/number|integer → slider；single_input/number|integer → input-number",
            "single_input/boolean → checkbox；multiple_input → multiple-input",
            "single_input/text + suggestions → auto-complete；其余 single_input/text → input",
            "不超过 4 个 static choices 的 single_select → radio-group",
            "2–5 个 static choices 的 multiple_select → checkbox-group",
            "其余 flat select → select",
        ],
        "dynamic_option_domains": [
            "options.mode=static 的 choices 是权威白名单，只用于真正封闭或需要主动限制的候选集合。",
            "数据成员来自 Source 且可能变化时使用 options.mode=infer，由 options.source 或消费 View 的 Base Output 推导完整选项域。",
            "多选未声明 initial 时默认 all_available，需要空集或指定值时分别使用 initial.mode=empty/values。",
            "单选未声明 initial 时默认 first；可选单选需要空值时使用 initial.mode=empty。候选域更新时优先保留仍有效的当前值，完全失效后才恢复 initial。",
        ],
        "example": """# dashboard.yaml: value and behavior contract
controls:
  - id: model
    type: single_select
    value_type: text
    required: true
    initial: {mode: value, value: baseline}
    options:
      mode: static
      choices:
        - {label: Baseline, value: baseline}
        - {label: Candidate, value: candidate}

# presentation.yaml: UI component only
control_components:
  query:job_date_range:
    component: range-picker
    span: 2  # optional; every component defaults to one track

  dashboard:forecast/model:
    component: radio-group
    option_type: button
    button_style: solid
""",
        "commands": [
            "dataviz docs data-entry-components --format json",
            "dataviz components list --category data-entry --format json",
            "dataviz components show control.cascader --format json",
            "dataviz scaffold control.range-picker --id analysis-window --format json",
            "dataviz components gallery --output component-gallery.html",
        ],
        "related": ["controls", "components", "presentation", "design-language"],
    },
    "renderers": {
        "summary": "Renderer 只消费 Named Output 和 View descriptor，不执行业务取数。",
        "commands": [
            "dataviz renderer test <renderer.js> --renderer-id <renderer-id>",
            "dataviz components show renderer.custom --format json",
            "dataviz components gallery --output component-gallery.html",
        ],
        "view_templates": list(VIEW_TEMPLATE_CONTRACTS),
        "lifecycle": {
            "author_hooks": ["validate", "mount", "update", "dispose"],
            "platform_matrix": [
                "mount", "update", "empty", "restore",
                "interaction", "resize", "dispose", "export",
            ],
            "rule": "Renderer 作者只实现四个 hook；平台宿主负责 Empty/Restore，Adapter/Chart Service 负责 Interaction/Resize，Server 与 portable HTML 必须通过同一矩阵。",
        },
        "isolation": "一个 Renderer 失败只影响自己的 View；输入没有变化时不 update。",
        "chart_service": {
            "api": "Custom Renderer 使用 context.charts.plotly 的 mount/update/resize/dispose，输入是 Plotly data/layout/config。",
            "ownership": "平台统一 Theme、responsive、page-first wheel、ResizeObserver、首屏 bootstrap、更新、Empty/Restore 与释放。",
            "grammar": "声明式模板生成 Plotly traces 与 layout；作者可通过 View options.trace、options.layout 和 config 调整表达。",
            "native_api": "可信 Custom Renderer 可直接访问页面内嵌的完整 Plotly.js API；Dataviz 不用封闭白名单限制 trace、layout、事件和命令式交互。",
            "escape_hatch": "直接调用底层 Plotly.js API 是显式逃生口，作者自行承担 Theme、Resize、Update、事件解绑与 purge。",
        },
        "table_service": {
            "api": "Custom Renderer 可使用 context.tables.tanstack.mount/update/resize/dispose 复用默认 Table，也可通过 context.tables.tanstack.core 访问完整 TanStack Table Core。",
            "ownership": "托管入口统一 Dataviz Theme、语义 DOM、可访问性、Control Binding、滚轮边界与 Export；直接 Core 调用由作者负责 markup、订阅、重绘、事件解绑和资源释放。",
        },
    },
    "charts": {
        "summary": "Plotly 是 Dataviz 唯一的作者图表接口；声明式模板与 Custom Renderer 逐层开放完整分析能力。",
        "field_matrix": _CHART_FIELD_MATRIX,
        "rule": "先验证数据口径、字段、聚合和 Named Output，再用 Plotly trace/layout/config 调整视觉细节。",
        "plotly_runtime": {
            "version": "4.0.0",
            "grammar": "内置 line/bar/stacked-bar/pie/scatter/heatmap/radar 都生成 Plotly traces 与 layout。",
            "native": "复杂视觉由 Custom Renderer 复用 context.charts.plotly，或直接调用完整 Plotly.js API。",
            "interaction": "图例、点击、框选、套索与缩放使用 Plotly 事件和 config；再次点击当前激活的矩形/套索工具会退出选择模式并保留已有选区；页面滚动仍由 Dashboard 优先处理。",
            "offline": "Plotly.js 4.0.0 作为固定浏览器资产随 Dataviz 提供；Server 与 portable HTML 使用同一份 JS，不依赖 Python plotly 包。",
        },
        "ownership": {
            "data": "Server/Transform 生成 canonical Named Output；Browser Adapter 只把已计算字段投影为 Plotly traces，不重新解释业务口径。",
            "layout": "Dashboard options.layout 保存稳定作者意图；Browser Runtime 再合并 Theme、容器尺寸和响应式边距。",
            "config": "Browser Runtime 提供 page-first 滚轮、Modebar、框选交互、Resize 与离线安全默认，并关闭 Plotly 云端分享入口；View config 只覆盖明确的局部需求。",
            "render": "浏览器直接调用内置 Plotly.js 4.0.0 的 newPlot/react/resize/purge，不经过 Python Figure。",
        },
        "official_gallery": "https://plotly.com/javascript/",
        "official_source": "https://github.com/plotly/plotly.js/",
        "gallery_guidance": "先确定需要回答的分析问题，再从 Plotly 官方示例选择 trace 类型，并接入 Named Output、Controls 与 Renderer 生命周期。",
        "source_adaptation": "官方源码可能自行准备 DOM、数据和事件；接入时必须改用 Named Output、声明资产并遵守 Dataviz 生命周期。",
        "recipe_policy": "Dataviz Recipe 只提供少量经过验证的起点，不复制官方示例库、不形成能力白名单，也不替代 Plotly 文档。",
        "service_example": "const state = await context.charts.plotly.mount(node, {data, layout, config});",
        "wheel_and_zoom": {
            "plotly_default": "内置 Plotly 模板关闭 scrollZoom。没有可写 Control binding 的图不显示工具栏；绑定后只显示矩形选择、套索选择和恢复默认值。再次点击激活的选择工具退出到普通查看模式，不清空选区；下载图片不默认出现。",
            "explicit_zoom": "缩放、平移和坐标轴恢复不进入默认工具栏；有明确分析需求时通过 config 覆盖，但不得默认截获 Dashboard 的连续滚动。",
            "custom_renderer": "Custom Renderer 使用 context.charts.plotly；只有明确需求时才启用 scrollZoom。",
        },
    },
    "tables": {
        "summary": "Table 是默认数据表达组件；Perspective 只用于赋予终端用户临时分组、聚合、透视和多维探索能力。",
        "templates": {
            "table": "本地固定 TanStack Table Core + Dataviz 默认语义 DOM/CSS；无需 React 或运行时 CDN。",
            "perspective": "Perspective v5 Web Component；拥有独立的自助分析 UI 和配置。",
        },
        "runtime": {
            "package": "@tanstack/table-core",
            "version": "9.2.4",
            "default_features": ["sorting", "global search", "pagination", "column visibility", "column order", "column pinning", "column sizing"],
            "offline": "Server 与 portable HTML 共用 Dataviz 本地打包的固定版本资产。",
        },
        "options": {
            "presentation": ["labels", "formats", "align", "widths", "striped", "compact", "wrap", "layout", "show_count"],
            "behavior": ["sortable", "initial_sort", "sort_desc_first", "searchable", "initial_search", "page_size", "hidden_columns", "column_order", "pinned_columns"],
            "rule": "默认只显示表头和数据；show_count、搜索框和分页都必须由作者显式启用。",
        },
        "custom_service": {
            "managed": "context.tables.tanstack.mount(node, {data, columns, options}) 返回可 update/resize/dispose 的托管 state。",
            "raw": "context.tables.tanstack.core 暴露 constructTable、tableFeatures、ColumnDef 所需函数和完整 feature/plugin 原语；作者可完全自定义 markup 与 CSS。",
        },
        "decision_rule": "明细、排行、对账、格式化、排序、搜索、分页和行选择使用 Table；只有看板使用者需要现场改变分析维度或聚合方式时使用 Perspective。",
        "scroll": "表格和 Perspective 仅在内部仍可滚动时消费滚轮；边界把滚轮交还页面。",
    },
    "repeated-views": {
        "summary": "一个 View 蓝图可按实体平铺，或按一个候选型 Control 的值重复。",
        "templates": {
            "small-multiples": "按 repeat.by 生成所有实体，支持分页、懒挂载与离屏回收。",
            "selection-gallery": "先搜索/级联选择实体，再只创建选中的 View 实例。",
        },
        "rule": "所有实例共享一个 Named Output，不为每个实体重复查询 Source。",
    },
    "presentation": {
        "summary": "可选 Presentation 按稳定 ID 覆盖 Theme、容器外观、Data Entry Component 和资源；结构布局只属于 Dashboard。",
        "file": "dashboard 文件夹中的 presentation.yaml；删除后仍使用 Dashboard Layout Contract，只退化为默认视觉样式。",
        "forbidden_structure": ["layout", "section.template", "section.columns", "view.span"],
        "themes": {
            "default": "business：白色画布、白色卡片、靛蓝分析强调、轻边框与极低阴影；绿色只保留给 Ready/成功语义，Dashboard 内图表与控件自动继承同一组 token。",
            "presets": {
                "business": "简洁中性分析工作台（默认）",
                "plain": "最小中性分析样式",
                "editorial": "暖色叙事报告",
                "terminal": "深色技术监控",
            },
            "boundary": "Theme 只改变 Dashboard Presentation；稳定 Shell 不随 Theme 染色。Renderer 显式 options/config 仍优先于默认主题。",
        },
        "shell": {
            "summary": "Server 与导出 HTML 默认使用连续白色 Shell；Server Header 横跨屏幕，Dataviz 品牌按钮控制其下方 Sidebar，Query 信号灯紧随品牌。Header、Sidebar 与 Workbench 只用极浅分割线区分，稳定 Shell 不跟随 Dashboard Theme 染色。",
            "tokens": [
                "--dv-shell-bg",
                "--dv-shell-surface",
                "--dv-shell-line",
                "--dv-shell-ink",
                "--dv-shell-muted",
                "--dv-shell-accent",
                "--dv-shell-soft",
                "--dv-shell-shadow",
            ],
            "boundary": "Dashboard Theme 只拥有 Canvas、Section、View 与 Renderer；Dashboard CSS 不应重写 Shell token。",
        },
        "control_panels": {
            "default": "Query Parameters 是正常文档流中的 Query Card；Header 最右侧的 RUN split control 负责执行与开合，Card 内不重复运行按钮。Dashboard/Section/View Controls 使用临时托盘，默认只展示业务字段与组件；consumer mode 与影响范围保留在 Runtime 契约中。",
            "path": "control_panels.<query|dashboard>；Section/View 可在各自 presentation 条目中设置 controls",
            "options": {
                "template": ["auto", "stack", "grid"],
                "width": ["auto", "compact", "regular", "wide"],
                "columns": "1–6，表示最大列数；Query 的实际列数由 Panel 自身宽度动态计算",
                "column_width": "160–600 px；Query 每轨目标宽度，默认 280；稀疏表单不拉满整行",
                "density": ["compact", "comfortable"],
            },
            "control_span": "control_components.<canonical-key>.span 可显式设为 1 或 2；默认 1，RangePicker 等组件不会自动跨列，窄容器会安全退化为单列。",
            "boundary": "这些字段只调整排版；值、校验、级联、tab 状态和执行仍由共享 Runtime 管理。导出 HTML 中 Query 为只读快照，Controls 保持交互。",
            "example": {
                "control_panels": {
                    "query": {"columns": 6, "column_width": 280, "density": "compact"},
                    "dashboard": {"template": "stack"},
                }
            },
        },
        "extension_path": ["默认模板", "模板参数", "Theme token", "局部 CSS class/options", "自定义 Renderer", "自定义 Canvas"],
        "non_goals": ["坐标/Mosaic 编辑器", "让 CSS 决定数据依赖", "在 Presentation 中保存密钥"],
        "related": ["design-language", "components", "charts", "tables"],
    },
    "design-language": {
        "summary": "AI 自定义 Dashboard 样式时应遵循的统一视觉语言、Token 契约与验收清单。",
        "default_direction": {
            "name": "Quiet white shell + clean analytical canvas",
            "intent": "冷静、清晰、可信；先让人理解分析对象和结论，再展示交互与实现细节。",
            "signature": [
                "白色 Header、Sidebar、Workbench 与默认 Canvas 形成连续表面，只用极浅分割线确认边界",
                "Dashboard 画布可独立使用 business、plain、editorial 或 terminal Theme，但默认 business 不与 Shell 争夺注意力",
                "靛蓝表达当前项、主操作和默认分析序列；绿色只表达 Ready、成功或正向语义",
                "留白是主要层级手段；轻边框和近乎不可见的阴影只做辅助",
            ],
            "default_preset": "business",
            "alternatives": {
                "plain": "中性、克制的日常分析",
                "editorial": "带叙事节奏的长报告",
                "terminal": "深色技术监控与诊断",
            },
        },
        "principles": [
            "Insight first：首屏先说明当前分析对象、关键结果和可采取的下一步。",
            "One section, one question：一个 Section 回答一个问题；View title 描述内容，description 说明读法。",
            "Semantic before decorative：颜色、容器和层级表达语义，不用装饰制造虚假重点。",
            "Progressive disclosure：Query Parameters 首次默认展开并参与页面文档流；Controls 位于最右侧 RUN split control 左侧并按需展开；Pipeline 以品牌旁逐节点状态灯呈现，悬停看任务名、点击看证据。",
            "Stable interaction：自定义 CSS 不改变 Control 级联、焦点、弹层几何、滚动或 Renderer 生命周期。",
            "Two bounded token layers：稳定 Shell token 管理导航和操作；Dashboard Theme token 管理 Canvas 与 Renderer。",
        ],
        "information_hierarchy": {
            "dashboard": "title 说明分析主题；subtitle/description 交代对象、范围和目的。不要重复 Run ID、Source ID 或实现口径。",
            "section": "短标题 + 一句决策问题；局部 Controls 放在 Section header，避免漂浮在图表内容上。",
            "view": "标题应能脱离页面独立理解；可选 description 说明指标口径或交互结果，不重复 Section 文案。",
            "detail": "诊断、SQL 和日志由节点状态灯的点击证据承载，不使用常驻 Pipeline 按钮抢占分析画布。",
        },
        "core_tokens": {
            "shell": {
                "--dv-shell-bg": "Header、导出工具栏与 Query 托盘的白色背景",
                "--dv-shell-surface": "Shell 按钮和弹层表面",
                "--dv-shell-line": "Shell 低对比边框",
                "--dv-shell-ink": "Shell 主要文字",
                "--dv-shell-muted": "Shell 辅助文字",
                "--dv-shell-accent": "活动导航、主操作与 Control 轻强调",
                "--dv-shell-soft": "Shell 弱强调背景",
                "--dv-shell-shadow": "Shell 工具栏低阴影",
            },
            "surfaces": {
                "--dv-paper": "页面背景",
                "--dv-panel": "卡片、表格与图表面板",
                "--dv-overlay-surface": "必须不透明的弹层表面",
                "--dv-soft": "弱强调背景",
                "--dv-soft-blue": "信息或上下文背景",
            },
            "content": {
                "--dv-ink": "主要文字",
                "--dv-muted": "辅助文字与元数据",
                "--dv-line": "边框、分隔线和图表网格基线",
            },
            "semantic": {
                "--dv-accent": "主要操作、活动状态和第一图表序列",
                "--dv-accent-strong": "高层标题和强强调",
                "--dv-green": "Ready、成功与正向业务语义",
                "--dv-amber": "Stale、Warning 与 Cancelled",
                "--dv-red": "Error 与破坏性操作",
                "--dv-blue": "信息状态",
            },
            "charts": "--dv-chart-1 … --dv-chart-8；无业务色彩约定时保持稳定顺序，不为每个 View 发明新 palette。",
            "shape_and_depth": [
                "--dv-radius",
                "--dv-radius-sm",
                "--dv-shadow",
                "--dv-shadow-float",
            ],
            "typography": ["--dv-font-sans", "--dv-font-mono"],
        },
        "composition": {
            "rhythm": "以 4px 为最小单位，常用间距 8/12/18/24/32；同层级保持一致。",
            "grid": "优先 12 列语义布局：12、8+4、6+6、4+4+4；窄屏回落为单列。",
            "density": "默认 comfortable；运营监控可 compact，叙事报告可 spacious。不要靠缩小字体容纳更多信息。",
            "height": "图表通常使用可读的 min-height；Table/Perspective 随容器增长。避免固定页面高度和无数据也锁住滚轮的内部滚动。",
            "emphasis": "每个 Section 至多一个主要 View；其余面板降低视觉重量。",
        },
        "component_rules": {
            "charts": [
                "数据编码优先于装饰；显式 View options 可以覆盖主题，但应保留字体、网格和语义色。",
                "同一业务维度跨 View 保持同色；比较序列优先使用位置、长度和直接标签。",
                "避免 3D、厚重阴影、彩虹 palette 和同时竞争注意力的多种图表风格。",
            ],
            "tables": [
                "普通 TanStack Table 负责明细阅读、排序、搜索、分页、列显示和行选择；Perspective 只用于终端用户需要临时重组、聚合或透视数据的场景。",
                "表头、斑马纹与 hover 保持低对比；数字右对齐，文本左对齐，关键列可用局部 class 强调。",
                "Perspective 拥有自己的交互 UI；只调整外层容器和语义 Token，不覆盖其内部结构。",
            ],
            "data_entry": [
                "最多四个短单选可用 radio-group；更多选项用 searchable select；层级数据用 cascader/tree-select。",
                "弹层必须使用 --dv-overlay-surface，保持不透明、视口内定位并支持键盘关闭。",
                "不要用 CSS 隐藏 unavailable/selected 状态来改变真实选择语义。",
            ],
            "states": "Ready/Loading/Stale/Empty/Error/Cancelled/Unavailable 使用共享状态颜色与文案；颜色不是唯一线索。",
        },
        "customization_order": [
            "先选择 layout/theme/Section/View/Data Entry Component",
            "再覆盖 theme.accent/background/panel/ink/density",
            "再通过稳定 ID 添加 css_class，并在 Dashboard 自有 CSS 中覆盖 Token",
            "只有模板无法表达行为时才写自定义 Renderer",
            "只有整个页面结构都特殊时才使用完整 Canvas",
        ],
        "presentation_example": """schema: dataviz/presentation/v2
kind: presentation
dashboard: sales-overview

theme:
  preset: business
  accent: \"#3451b2\"
  density: comfortable

sections:
  performance:
    css_class: insight-section

views:
  revenue-trend:
    min_height: 380
    container: chart
    css_class: insight-primary
  sales-detail:
    container: table

assets:
  css: [assets/presentation.css]
""",
        "css_example": """/* Dashboard-owned CSS: change semantic tokens before component internals. */
.dv-canvas {
  --dv-accent: #3451b2;
  --dv-accent-strong: #1f2f78;
  --dv-chart-1: #3451b2;
  --dv-chart-2: #23867b;
}

.dv-view.insight-primary {
  border-top: 3px solid var(--dv-accent);
}
""",
        "avoid": [
            "在每个 View 中复制一套颜色、字体、卡片和弹层 CSS",
            "透明弹层、任意高 z-index、固定页面宽高和嵌套滚动锁",
            "把绿色、黄色、红色当装饰色，削弱状态语义",
            "用巨型标题重复 Dashboard/Section/View 的同一句话",
            "在画布主区域展示 SQL、Source ID、Run ID 或框架实现说明",
            "为追求独特而重写稳定 Data Entry、Perspective 或 Runtime DOM",
        ],
        "ai_workflow": [
            "读取 dataviz inspect context 与相关 Component contract，确认现有模板能否满足需求。",
            "选择一个明确方向；默认沿用 business，不同时混合 business/editorial/terminal 的视觉语法。",
            "先写 Presentation YAML，再写最少量 Dashboard 自有 CSS；不修改数据逻辑。",
            "运行 dataviz validate，并在 Gallery/真实数据/窄视口下检查 Ready、Empty、Error 和弹层状态。",
            "确认 Server 与导出 HTML 的 Shell 一致，Plotly/Table/Perspective 均继承 Dashboard Theme Token。",
        ],
        "acceptance_checklist": [
            "首屏通过状态灯知道 Pipeline 健康度，需要时点击具体节点查看证据。",
            "页面只有一个主要强调色，状态色保持原有语义。",
            "标题层级不重复，Section 和 View 在脱离上下文时仍可理解。",
            "控件弹层不透明、不越过视口，点击外部与 Escape 可关闭。",
            "窄屏无水平页面溢出；Table/Perspective 不无条件截获页面滚轮。",
            "自定义 CSS 删除后仍能回退为完整可用的声明式 Dashboard。",
        ],
        "commands": [
            "dataviz components list --category theme --format json",
            "dataviz components show theme.business --format json",
            "dataviz components gallery --output component-gallery.html",
            "dataviz validate <workspace> --dashboard <dashboard-id> --format json",
        ],
        "related": ["presentation", "components", "charts", "tables", "controls"],
    },
    "components": {
        "summary": "Component Registry 是 AI 选择 Data Entry、View、Section、Runtime 和扩展点的机器可读目录。",
        "commands": [
            "dataviz components check --format json",
            "dataviz components show <component-id> --format json",
            "dataviz scaffold --list --format json",
            "dataviz scaffold <recipe> --id <id> --format json",
            "dataviz components gallery --output gallery.html",
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
            "components check validates Package metadata/assets and test declarations; "
            "pytest plus browser E2E execute behavior."
        ),
    },
    "ai-authoring": {
        "summary": "AI 应读取任务相关的最小契约，而不是整个 Runtime 源码。",
        "commands": [
            "dataviz docs design-language --format json",
            "dataviz inspect context <workspace> <dashboard> --focus view:<id> --format json",
            "dataviz inspect context <workspace> <dashboard> --focus dataset:<id> --format json",
            "dataviz inspect context <workspace> <dashboard> --focus interactive:<id> --format json",
            "dataviz inspect context <workspace> <dashboard> --focus component:<id> --format json",
            "dataviz benchmark runtime <workspace> <dashboard> --browser chromium --repeat 3 --query-param row_count=1000000 --format json",
        ],
        "runtime_benchmark": {
            "purpose": "在 Chromium/Firefox/WebKit 中等待页面稳定，重复装载并 dispose；测量 Query、报告构建、页面就绪、Arrow、Renderer、View 终态和可用内存口径。",
            "schema": "dataviz/browser-runtime-benchmark/v3",
            "boundary": "它验证页面规模与生命周期，不估算 AI Token。",
        },
        "goal": "先追求可用性和低试错；Token 节省比例只能由真实任务测量，不能预设。",
    },
    "schema-reference": {
        "summary": "schemas 命令直接由安装版本的严格 Pydantic 模型生成，不维护手写副本。",
        "commands": [
            "dataviz schemas --format json",
            "dataviz schemas dashboard --full --format json",
            "dataviz schemas parameter-domain --full --format json",
            "dataviz schemas interactive-transform --full --format json",
            "dataviz schemas target-reference --full --format json",
            "dataviz schemas analysis-result --full --format json",
            "dataviz schemas analysis-evidence --full --format json",
        ],
    },
    "validation": {
        "summary": "validate 是每次修改后的零查询静态门禁，优先把错误暴露给 AI。",
        "recommended_command": "dataviz validate <workspace> --dashboard <dashboard-id> --format json",
        "coverage": [
            "schema、未知字段、重复 ID 和本地路径边界",
            "显式 Output 引用、缺失 Output、两个 DAG 的环和跨 Runtime 非法依赖",
            "Query/Control namespace、Control type、consumer binding、作用域可见性与 trigger 冲突",
            "Interactive export.mode 与浏览器 Runtime 资产",
            "SQL named parameter、Python 依赖和输入/输出 Schema",
            "Parameter Domain Adapter、SQL named parameter、字段投影、父参数依赖与环",
            "View/Section/Presentation/Data Entry Control 引用",
            "最终 Layout/Dependency/Renderer 配置中的确定性冲突、no-op 与无 consumer Control",
        ],
        "json_contract": {
            "queries_executed": "固定为 0；静态验证不触发任何数据源。",
            "passed": "无 error；--strict 时 warning 也令 exit code 非零。",
            "advice": "主观或依赖未知数据规模的启发式建议，不阻塞 --strict。",
            "diagnostic": "包含稳定 code、field/JSON path、file、details 和 hint。",
        },
        "layout": "inspect layout 输出 dataviz/layout-inspection/v1 的最终 rows、span、来源与 custom 边界。",
        "visual": "visual-check 在真实浏览器中输出 dataviz/visual-check/v1、截图和客观几何诊断；不评价配色或业务图表选择。",
        "visual_install": "未安装浏览器依赖时运行 pip install \"ai-dataviz[visual-check]\"，再执行 playwright install chromium；CLI 缺依赖错误会给出可复制命令。",
        "sql_parameter_example": {
            "errors": ["sql_parameter_undeclared", "sql_parameter_unused"],
            "fix": "同时更新 SQL placeholder、Source query_inputs 本地别名和 Dashboard query_parameters 绑定。",
        },
    },
    "strict-schema": {
        "summary": "只接受当前 DSL；不提供 deprecated 层、字段别名、自动迁移或双协议 Runtime。",
        "current": {
            key: CURRENT_PROTOCOL_SCHEMAS[key]
            for key in (
                "dashboard",
                "parameter_domain",
                "presentation",
                "source",
                "runtime",
                "dependency_contract",
                "dataset_transform",
                "interactive_transform",
                "target_reference",
                "analysis_result",
                "analysis_evidence",
                "layout_contract",
                "state_snapshot",
            )
        },
        "browser_assets": {
            "plotly_js": "4.0.0（直接内置，不安装 Python plotly）",
            "tanstack_table_core": "9.2.4（直接内置）",
        },
        "rules": [
            "未知字段 extra=forbid。",
            "旧 Dashboard、旧 Transform 名称和隐式 Output 引用直接报错。",
            "仓库示例与调用方必须一次性改写后再运行。",
        ],
    },
    "frontend-adapters": {
        "summary": f"前端实现只消费 {RUNTIME_PROTOCOL_SCHEMA} Manifest/Event/Output，不读取 Python 内部对象。",
        "commands": [
            "dataviz frontend-adapters --format json",
            "dataviz frontend-adapters web-component --output runtime-adapter.js",
        ],
        "public": ["canonical Named Output", "Control state revisions and bindings", "node lifecycle", "Renderer lifecycle"],
    },
    "versioning-release": {
        "summary": "版本发布验证当前契约，不把旧 DSL 重新带回发行包。",
        "commands": ["dataviz version", "uv build", "python scripts/build_release_zip.py"],
        "release_contract": [
            "Python 3.11–3.14 运行 unit/contract tests。",
            "快速迭代默认运行完整 Chromium Runtime tests；稳定发布、跨浏览器敏感修改或明确要求时再重复 Firefox/WebKit。",
            "wheel、sdist、pip ZIP 在干净 venv 中运行 version/schemas/components check/init/validate/report smoke。",
            "干净环境确认 Python plotly 未安装，并核对 version 与报告中的 Plotly.js 固定版本。",
            "发行包排除 .venv、build、缓存和运行 Artifact。",
        ],
    },
    "runtime-limits": {
        "summary": "当前是可信单机 Runtime，但仍提供可预测的 timeout、cancel、缓存和清理。",
        "implemented": [
            "SQL/Python Source 与 Dataset Transform 独立进程；SQL 默认 120 秒并立即重试一次。",
            "server-python Interactive Transform 使用独立进程和 generation 取消。",
            "browser-js 使用 Web Worker、timeout、supersede cancellation 和结构化错误。",
            "大 Table 自动使用 Arrow IPC；浏览器按需物化行。",
            "内置数值聚合使用线性 reducer，避免大数组展开触发 JavaScript 参数上限。",
            "节点独立发布，失败分支不阻塞无关分支。",
            "runtime.max_concurrent_runs 与 max_concurrent_interactions 分别限制单机并发 Query/Server 交互任务。",
            "Execution Artifact、NodeCache、共享 Parameter Materialization 与不可变 Result 只写入 Workspace/.dataviz；默认缓存由 tab session 隔离，Server Interactive 复用同一 Query Run。",
            "Run、cache、Worker、Renderer 与订阅均有 dispose/淘汰路径。",
        ],
        "current_limits": [
            "可信本地 Python/JavaScript 不是不可信代码沙箱。",
            "没有多租户 CPU/内存配额。",
            "Server 与 HTML 仍传输完整可达 Output，未实现服务端分页。",
            "固定 10K/100K/1M 聚合链路已有 Chromium 基线；它不代表 1M 行原始 Table/Perspective 的交互预算。",
            "修改 Workspace Runtime 并发上限后需要重启 Server，已有信号量不会热替换。",
            "只支持一个 Dataviz Server 进程写一个 Workspace/报告目标；协调锁不是跨进程锁。",
            "Server 没有账号体系或 HTTP 鉴权，默认只监听回环地址；非回环 --host 必须显式使用 --allow-remote，并由可信网络或外部代理负责访问控制。session_id 不是访问凭证。",
        ],
        "related": ["interactive-transforms", "maintenance"],
    },
    "runtime-performance": {
        "summary": "用真实 Query → Arrow → Interactive → Renderer 页面建立可复现规模证据，而不是按行数猜测。",
        "commands": [
            "dataviz benchmark runtime <workspace> <dashboard> --browser chromium --repeat 3 --query-param key=value --format json",
            "uv run --no-editable python scripts/run_runtime_scale_benchmarks.py --browser chromium --repeat 3 --output benchmarks/results/runtime-scale.json",
        ],
        "schema": "dataviz/browser-runtime-benchmark/v3",
        "measurements": {
            "query": "耗时与 CLI 进程峰值 RSS；包含 DuckDB/Arrow 等 native 分配。",
            "browser": "页面就绪时间、进程树 RSS 峰值/释放后回落、Chromium 主 renderer JS heap。",
            "runtime": "Arrow 行/字节/耗时、Interactive 与 Renderer 生命周期、View 终态和 console error。",
        },
        "memory_scope": "进程树 RSS 包含 Playwright driver、browser、workers、native Arrow 与 GPU helper；JS heap 不包含 Worker/native 内存。Firefox/WebKit 不公开 performance.memory 时返回 null，不伪造估值。",
        "fixed_fixture": "benchmarks/scale-workspace 的 row_count=10000/100000/1000000；结果与方法见 docs/runtime-performance.md。",
        "decision": "1M 聚合链路可完成后仍不自动推出通用分页；原始明细 View、候选型 Control 和高基数组合需各自基准触发。",
        "boundary": "Runtime 性能基准只衡量页面运行规模与资源生命周期。",
    },
    "maintenance": {
        "summary": "安全预览并清理 Workspace 的不可变 Result、Execution Artifact、共享候选物化旧 generation 和持久缓存。",
        "commands": [
            "dataviz prune <workspace>",
            "dataviz prune <workspace> --keep-runs 20 --run-max-age-hours 48",
            "dataviz prune <workspace> --keep-results 20 --result-max-age-days 30",
            "dataviz prune <workspace> --all --apply",
        ],
        "rules": [
            "默认 dry-run；必须显式 --apply 才删除。",
            "只允许删除 Workspace/.dataviz/results、runs、cache 与 parameter-materializations 中被策略选中的目标；当前、活动读取或仍被租约保护的 generation 不会删除。",
            "活动 Query、读取租约，以及仍被活动 Interaction 消费的 Query Run 和缓存始终受保护。",
            "复制到 Workspace 外的 export 和原始 File Source 永不由 prune 删除。",
        ],
    },
    "troubleshooting": {
        "summary": "沿 Pipeline 分层定位，保留可复查证据。",
        "triage": [
            {"symptom": "Workspace 无法加载", "action": "先运行 validate，修复 schema、路径和重复 ID。"},
            {"symptom": "找不到可执行口径", "action": "先 catalog search，再 catalog describe；不要猜测已移除的短 alias。必要时使用 --refresh-catalog 安全重建索引。"},
            {"symptom": "Target Reference 无法解析", "action": "复制 catalog 返回的 canonical reference，并对照 docs target-references；不要传 Result ID 或模糊对象名。"},
            {"symptom": "Source 失败", "action": "用规范 Source Target 单独 run；再通过 result inspect 查看解析 SQL、Adapter、参数、timeout 和 traceback。"},
            {"symptom": "Dataset Transform 失败", "action": "run 对应 Output Target；检查 result inspect 中的 input schema、node.error.traceback 和 node.log。"},
            {"symptom": "Interactive Transform 失败", "action": "检查 Runtime、trigger、canonical state、generation 与 export.mode；browser-js Derived Output 使用 --runtime browser。"},
            {"symptom": "需要查看更多结果", "action": "不要重新 run；使用 result show 的 --offset/--limit 分页，或 result export 原样复制一个 Artifact。"},
            {"symptom": "Result 引用的 File Source 已变化", "action": "Result 保留实际读取的 path/hash 收据；重新执行产生新 Result，不修改旧 manifest。"},
            {"symptom": "查询成功但 View 为空", "action": "检查 Named Output 字段、类型、显式 Control filter 后行数和 View input。"},
            {"symptom": "Server 正常但 HTML 失败", "action": "检查 export.mode；server-python 不能离线重算，browser-js 的代码和依赖必须随报告嵌入。"},
            {"symptom": "源码环境 ModuleNotFoundError", "action": "在 dataviz-tool 下运行 uv sync --python 3.12 --extra dev --no-editable --reinstall-package ai-dataviz；后续 CLI 使用 uv run --no-editable dataviz。"},
        ],
        "evidence": [
            "dataviz validate 的完整 JSON。",
            "result inspect 的状态、Node error、traceback、log 和 provenance。",
            "Sources 面板中的参数化 SQL 与解析 SQL。",
            "HTML 同目录的 manifest。",
        ],
    },
}


def resolve_doc_topic(topic: str) -> str:
    normalized = topic.strip().lower()
    return DOC_TOPIC_REDIRECTS.get(normalized, normalized)


def docs_catalog(search: str | None = None) -> dict[str, dict[str, Any]]:
    if not search:
        return DOC_TOPICS
    needle = search.casefold()
    return {
        name: definition
        for name, definition in DOC_TOPICS.items()
        if needle in name.casefold() or needle in str(definition).casefold()
    }
