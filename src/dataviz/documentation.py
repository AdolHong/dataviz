from __future__ import annotations

from difflib import get_close_matches
from typing import Any

from dataviz.action_examples import annotation_recipe

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
DOC_SEARCH_SCHEMA = "dataviz/docs-search/v1"


AUTHORING_ROUTE_ALIASES = {
    "dashboard": "minimal",
    "simple": "minimal",
    "controls": "interactive",
    "control": "interactive",
    "interaction": "interactive",
    "renderer": "custom-renderer",
    "custom": "custom-renderer",
    "map": "map-view",
    "entity": "entity-select",
    "lookup": "entity-select",
    "remote-select": "entity-select",
    "large-select": "entity-select",
}

AUTHORING_DOCUMENTS: dict[str, dict[str, Any]] = {
    "server-action-authoring": {
        "requires": ["server-action", "adapter"],
        "purpose": "Implement explicit server Python commands without adding writes to the read DAG.",
        "path": "Explicit invocation → Python + external bindings → receipt → selected Source/View refresh",
        "steps": [
            "Read dataviz docs server-actions for the Python context, resource, receipt and refresh contracts.",
            "Generate server-action.python; implement business validation, transactions and JSON return values.",
            "Declare aliases and allowed invalidations, then add the Action YAML to Dashboard server_actions.",
            "Validate without writes; test against isolated external databases/files before authorizing real mutations.",
            "Use the existing Server applied Run and one request ID. Query status or retry refresh without repeating Python.",
        ],
    },
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
            "In Server author mode, click the Interactive node for the producer trace; click a View renderer signal for the View-centric cause, changed Outputs, query_executed evidence, input rows/bytes and render timing. Copy diagnosis exports that existing evidence as one bounded JSON object.",
            "Run validate, report, then visual-check.",
        ],
        "incremental_boundary": {
            "execution": "One Control change executes the affected Transform as one function and one generation.",
            "rendering": "Runtime compares each Named Output by stable value signature and redraws only Views reached from Outputs that actually changed.",
            "authoring": "Split genuinely independent expensive computations into separate Transforms; outputs.<name>.depends_on_controls is not a supported field.",
            "evidence": "Author-mode traces describe the latest successful session generation and are not immutable Result/Evidence records.",
        },
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
            "Keep unrelated relations as separate View input/inputs aliases; read descriptor.inputs.main and descriptor.inputs.<alias> instead of joining them with a synthetic row_kind.",
            "In Server author mode, inspect the View signal to see changed input aliases; waiting and failure evidence names the exact alias and canonical Output reference. Use Copy diagnosis when handing the complete current-View evidence to another author or AI.",
            "Register one Renderer with validate, mount, update and dispose hooks.",
            "Let the platform own empty, restore, interaction, resize and export behavior.",
            "Run dataviz renderer test before browser validation; it exercises mount/update/dispose and rejects an empty mount or DOM left behind after dispose.",
            "Run validate, report, then visual-check.",
        ],
        "named_inputs_example": {
            "yaml": """- id: geography-and-stores
  template: custom
  renderer: geography-and-stores
  input: interactive:geo-scope/stores
  inputs:
    geography: dataset:map-geography/main
""",
            "javascript": "const stores = descriptor.inputs.main;\nconst geography = descriptor.inputs.geography;",
            "rule": "input is the primary alias main; inputs adds named relations. For a table, descriptor.inputs.main and descriptor.rows share the processed rows. Additional aliases receive only filters explicitly bound to them; original Outputs are unchanged.",
        },
    },
    "map-view": {
        "requires": ["adapter", "source", "view", "layout", "workspace-asset"],
        "purpose": "Render one point/region mark or ordered point + GeoJSON layers without custom JavaScript.",
        "path": "Named Output(s) + optional Workspace GeoJSON Asset → one native Plotly Map View",
        "steps": [
            "Use a map only when geographic position or shape is part of the analytical question.",
            "Use mark=point with longitude/latitude, or mark=region with an allowlisted GeoJSON Asset and explicit join keys.",
            "Use layers only when region and point marks must share one viewport; each Layer declares its own id, input and optional Control binding.",
            "Keep business aggregation in the Source or Transform; one region key must produce one row.",
            "Run validate, report, then visual-check in both Server and portable HTML.",
        ],
        "minimal_example": """views:
  - id: stores
    template: map
    mark: point
    input: source:stores/main
    longitude: longitude
    latitude: latitude
    label: store_name
""",
    },
    "entity-select": {
        "requires": ["adapter", "parameter-domain", "query-parameter", "source"],
        "purpose": "Search and select a large entity catalog without loading all candidates into the Browser.",
        "path": "Materialized Parameter Domain → server Lookup → compact multiple_select → query_filters",
        "steps": [
            "Scaffold the current strict composition instead of inventing an entity_select type.",
            "Project stable value, label and search keyword columns from one materialized SQL catalog.",
            "Use default none, clearable true and query_filters empty=passthrough when an empty choice means no filter.",
            "Keep include operands bounded; use a table/upload join instead of a huge SQL IN list.",
        ],
    },
    "cascading-selection": {
        "requires": ["view", "control", "option-domain", "dependency-closure"],
        "purpose": "Filter a post-query child choice Control's candidates from one or more direct parent Controls over an already loaded Base Output.",
        "path": "Base option domain → parent Control → child depends_on → explicit consumers",
        "steps": [
            "Put every candidate and parent field in one immutable Base table output.",
            "Declare only the child's direct parent in depends_on.",
            "Use initial for post-query Control Select startup behavior; Query Parameters use default instead.",
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
            "Using default on a post-query Control Select instead of initial; Query Parameters do use default.",
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
        "worker_example": """function transform(context) {
  const rows = context.rows('rows');
  const factor = Number(context.control_inputs.factor ?? 1);
  return {main: rows.map(row => ({...row, value: Number(row.value) * factor}))};
}""",
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
            "Reading removed context.selections instead of context.control_inputs.<alias>; validate reports browser_context_selections_removed without executing the Worker.",
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
    "server-actions": {
        "summary": "Explicit trusted server Python computation or writeback; UI-independent and separate from automatic reads.",
        "inherits": [], "documents": ["server-action-authoring"],
        "scaffolds": ["server-action.python"],
        "commands": [
            "dataviz docs server-actions --format json",
            "dataviz schemas server-action --full --format json",
            "dataviz scaffold server-action.python --id <action> --format json",
            "dataviz actions invoke --help",
        ],
        "excludes": ["automatic-write-retry", "annotation-specific-dsl"],
    },
    "minimal": {
        "summary": "Default path for a simple declarative Dashboard.",
        "inherits": [],
        "documents": ["minimal-dashboard"],
        "scaffolds": [
            "standalone", "minimal", "source.file", "source.sql", "source.python",
            "view.metric", "view.line", "view.bar", "view.map", "view.table",
        ],
        "commands": [
            "dataviz scaffold standalone --id sales --output ./sales",
            "dataviz validate ./sales/dashboard.yaml --strict --format json",
            "dataviz run ./sales/dashboard.yaml --format json",
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
        "summary": "Use only when no built-in View can express the required visual; one Custom View may consume multiple Named Outputs through input/inputs aliases.",
        "inherits": ["minimal"],
        "documents": ["custom-renderer"],
        "scaffolds": ["custom-renderer", "renderer.custom", "view.custom"],
        "commands": [
            "dataviz scaffold custom-renderer --id <dashboard> --output <workspace>",
            "dataviz renderer test <renderer.js> --renderer-id <renderer-id>",
            "dataviz docs renderers --format json",
            "dataviz components show renderer.custom --format json",
            "dataviz components gallery --output component-gallery.html",
        ],
        "excludes": ["control", "interactive-transform"],
    },
    "map-view": {
        "summary": "Build a native Plotly point, GeoJSON region, or ordered multi-Layer Map View.",
        "inherits": ["minimal"],
        "documents": ["map-view"],
        "scaffolds": ["view.map"],
        "commands": [
            "dataviz docs maps --format json",
            "dataviz validate <workspace> --dashboard <dashboard> --format json",
            "dataviz visual-check <workspace> <dashboard> --target both",
        ],
        "excludes": ["renderer-contract", "remote-map-service", "gis-runtime"],
    },
    "entity-select": {
        "summary": "Compose a searchable large entity Query Parameter from existing strict contracts.",
        "inherits": ["minimal"],
        "documents": ["entity-select"],
        "scaffolds": ["query-parameter.entity-select"],
        "commands": [
            "dataviz scaffold query-parameter.entity-select --id <parameter> --format json",
            "dataviz parameters prewarm <workspace> <dashboard>",
            "dataviz parameters lookup <workspace> <dashboard> <parameter> --search <text>",
        ],
        "excludes": ["entity-runtime", "browser-candidate-relation"],
    },
    "cascading-selection": {
        "summary": "Build a post-query parent-child choice-Control candidate cascade; query-time Parameter Domain cascades belong to docs query-parameters.",
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

        requested_component = component.strip()
        catalog = component_catalog()
        selected_component = _resolve_component_identifier(requested_component, catalog)
        selected_definition = catalog[selected_component]
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
        "schema": "dataviz/authoring-route-catalog/v2",
        "default": "minimal",
        "routes": {
            identifier: {
                "summary": definition["summary"],
                "inherits": definition["inherits"],
                "scaffolds": definition["scaffolds"],
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
    "map",
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
    "map": "maps",
    "geojson": "maps",
    "entity-select": "entity-selection",
    "entity-picker": "entity-selection",
    "view": "charts",
    "source": "sources",
    "parameter": "query-parameters",
    "parameters": "query-parameters",
    "query-parameter": "query-parameters",
    "parameter-domain": "query-parameters",
    "query-parameter-domain": "query-parameters",
    "lookup": "query-parameters",
    "remote-select": "query-parameters",
    "asset": "workspace-assets",
    "workspace-asset": "workspace-assets",
    "shared-file": "workspace-assets",
    "bundle": "workspace-assets",
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
    "interaction-stability": {
        "summary": "品类切片、商品选择变 null、级联候选为空、右图漏刷、刷新后 409：联动稳定性诊断。",
        "checks": [
            "动态必选 Control 初始化时，依赖它的 Interactive Transform 等待候选域与默认值就绪，不提交空值制造 control_state_required 422；等待的是数据与 Control，而不是其他 Section 的图表渲染。无关 Transform 可继续执行。",
            "候选加载完成但为空时显示 No available options；加载失败或字段映射错误保留明确错误。服务端按目标 Transform 的依赖闭包检查必选值，实际依赖的非法空值仍拒绝，不放宽必选约束。",
            "先看 canonical Control state，不用手动高亮推断选择成功。点击被接受后，原生高亮与消费 View 应使用同一份选择。",
            "depends_on 声明父 Control；级联字段优先使用该 View 已有 filter 绑定，否则使用父 Control 的 field/path_fields（未指定时为 id）。不需要为了候选级联而给所有 View 补父过滤。字段应显式映射，平台不猜业务关系。",
            "声明过的候选 schema 缺少父字段时 validate 报 control_dependency_field_unknown；没有静态 schema 时查看运行时 option_domain，不能把 field_mismatch 当成合法空选。",
            "Interactive 输出同步登记 value/kind/schema；值未变但错误恢复或元信息变化，也必须更新相关消费者。可选输出消失时一起清理；不使用多余 mode:value 绑定绕过漏刷。",
            "同 Run 的 Canvas 重载从服务端 generation 水位接续，仍拒绝旧 generation。不自动重试过期写入，不重跑 Query 来修正本地选择。",
        ],
        "diagnostics": {
            "view_report": "作者模式点击 View 的证据信号，再选 Copy diagnosis。汇总当前状态、等待/失败输入、输入行数/字节、Control revision 与 Renderer binding revision；unknown 表示证据不足，不默认标记 ready。默认复制省略业务值、标题、原始错误和 Transform trace payload。仍包含配置 ID 与引用，分享前需审阅。界面中的原始分段证据及其 Copy 按钮不属于脱敏报告。",
            "view_triage": {
                "query_completion": "查询事件连接永久关闭时重查原 Run；临时断流保留 EventSource 自动重连。每次完成状态 GET 最多等待 30 秒，超时只中止这次读取，不取消服务端 Query。完成状态读取失败，或重查时仍在排队/执行，显示 Unconfirmed / Retry status 并保留 Run ID；点击只重查原 Run，不重复提交查询。不要将未确认回执误判为计算失败；网络恢复后可直接重查，无需刷新整个页面。",
                "symptoms": "图表没刷新、图表空白、没有数据、旧图不变、加载失败、缓存命中怎么判断：先查 View 证据信号，不必查框架源码。",
                "input": "Copy diagnosis 的 inputs.<alias> 提供 reference、kind、input_type、transport、status、rows、bytes。pending/error 的未知行数为 null，不是 0；input_profiles 优先于上一次 renderer.inputs，防止旧行数误导。静态依赖用 dataviz inspect dependencies <workspace> <dashboard> --format json。",
                "control": "REFRESH CAUSE 中 control_state 是本次渲染消费的值、intent、revision；最新值可在 Canvas/导出页控制台通过公开 window.dataviz.control.state(canonicalKey) 查询。不要把上一次消费值当成实时状态。默认 Copy diagnosis 不复制业务值；原始证据含值，外发前需审阅。",
                "waiting": "stage=waiting_input 且 inputs.status=pending：上游尚未发布，继续查 reference 对应节点；rows=0 且 status=empty 是合法空表，两者不同。",
                "failed": "stage=input_failed 或 render_failed：按 error_code 定位下载、计算或渲染失败；原始错误看分段证据。output_fetch_failed 是实时下载失败，不代表 SQL 返回 0 行。",
                "not_refreshed": "scheduling.status=not_affected 表示最近一次调度没有命中该 View，不伪造一次渲染；检查声明依赖和 changed_controls。transforms.<id>.cache=hit 表示重用计算；status=cancelled/waiting/error 是不同终态，不应当成 ready。",
                "limits": "报告是本页面的局部运行证据，不代表其他标签页或新打开的独立 CLI 分析会话。没有抓到证据时保留 unknown/null，不靠猜测补值。",
            },
            "selection": "window.dataviz.control.state(canonicalKey)",
            "domain": "window.datavizRuntime.controlDomainEvidence.get(canonicalKey)",
            "domain_states": "pending=输入未到；field_mismatch=字段映射失败；error=上游失败；empty=合法候选为空；ready/static=可用。sources 带 reference、rows、missing_fields。关系无法解析时保留原选择，不伪装成空候选。",
            "updates": "viewRefreshEvidence / viewRenderEvidence：核对 affected views、query_executed、control_revisions、binding_revisions；刷新失败与保存失败分开处理。",
        },
        "commands": ["dataviz docs controls --format json", "dataviz docs renderer-selection --format json", "dataviz docs action-save --format json"],
    },
    "renderer-selection": {
        "summary": "Custom Renderer 行高亮不更新、选错行、刷新后才正确：controlBinding.state 快照、选择订阅和 update 生命周期。",
        "rules": [
            "controlBinding.state 是本次 descriptor 的 canonical state 快照，不是实时 getter。update(context, descriptor, state) 会收到新的 context。",
            "长期事件处理器通过 state.context.controlBinding.emit 使用最新 context；update 开头替换 state.context。不要一直读取 mount 时闭包里的 context。",
            "control_binding 的发起视图需要随 canonical 选择刷新反馈，不过滤自己的候选行；额外只读订阅用 control_inputs: {selected: {mode: value, control: dashboard.item}}。数据行不变也应收到 update。",
            "mode:value 是依赖声明，不会自动往 context 增加 control_inputs 字段。绑定发起视图读 context.controlBinding.state；其他订阅者可通过公开 window.dataviz.control.state(canonicalKey) 读取当前状态。",
            "高亮依据已提交状态而非刚点击的原始值；处理 clear/reset、类型差异、多选 intent、拒绝和 superseded。优先用稳定业务 ID，不用展示 label 或行号作为身份。",
            "只更新现有行的高亮和 aria-selected，不必重建整表；Control 更新不应触发 Query，无关视图不重绘。",
        ],
        "diagnostics": {
            "current": "window.dataviz.control.state(canonicalKey).revision",
            "scheduled": "datavizRuntime.viewRefreshEvidence.get(viewId).control_revisions：显式消费状态的调度快照；query_executed 说明是否查库。",
            "rendered": "datavizRuntime.viewRenderEvidence.get(viewId)：phase/generation/binding_revisions 记录最近完成的渲染与 binding revision。未被调度时保留上次证据，不伪造一次 update。",
            "interpretation": "当前 revision 新于 rendered 时检查是否订阅/是否等待或 superseded；revision 一致但 DOM 高亮错误时检查 Renderer 的旧闭包或行 ID 比较。不要只凭现象认定是 Plotly 或浏览器 repaint。",
        },
        "javascript_example": """mount(context, descriptor) {
  const state = {context, rows:[]};
  // Create row DOM once. A handler uses state.context, not captured context:
  // button.onclick = () => state.context.controlBinding.emit('select', row);
  this.update(context, descriptor, state);
  return state;
},
update(context, descriptor, state) {
  state.context = context;
  const selected = context.controlBinding.state.value; // single-select example
  for (const {node, id} of state.rows) {
    node.setAttribute('aria-selected', String(Object.is(id, selected)));
  }
  return state;
}""",
        "commands": ["dataviz docs controls --format json", "dataviz docs --task custom-renderer --format json"],
    },
    "action-save": {
        "summary": "保存慢、人工标注、checkbox 保存 SQLite、保存后局部刷新：完整示例、onProgress 保存确认与耗时诊断。",
        "recipe": annotation_recipe(),
        "progress_contract": {
            "onProgress(receipt)": "先收到本地 queued（含 request_id、初始 position、submitted:false）和 submitting 状态，再接收服务端完整回执，可重复。queued 不代表已保存。status=succeeded 才确认成功；refresh.status=ready 只表示服务端完成。快速刷新也会在浏览器更新前发送成功 progress。",
            "query_readiness": "渐进式 Canvas 可能先显示数据、宿主后确认 Run 已提交；invoke 在既有本地队列等待当前 Run 的宿主确认，不提前发送写入。离开页面会取消未提交项；queued 不代表服务端已受理或已保存。",
            "连续保存": "invoke/refresh 共用每个 Canvas 的内存串行队列，最多等待 50 条；payload 入队时复制，请求 ID 独立，status 查回执不排队。执行超时从发送开始。不会合并写入、自动重试或改写版本号。Action 刷新的新 Run 可以接续；切换查询或关闭 Canvas 时未发送请求取消。action_not_submitted 表示未提交，不是保存结果未知。前一条结果不确定时先查回执，剩余排队请求取消。",
            "invoke_resolves": "invoke 继续等待浏览器同步；检查 refresh.status，failed/superseded 不等于页面已同步。",
            "host_http_deadline": "宿主从调用开始为 HTTP 预检、提交、轮询和输出下载共用 290 秒等待上限，早于 Canvas 300 秒 RPC 超时；不延长每次轮询预算。超时释放宿主占用，只取消客户端 HTTP，不取消或回滚服务端 Python。invoke 的提交前超时为 action_not_submitted；提交后为 action_response_unknown；已有 succeeded 回执仍保留保存成功和独立 client_refresh 失败。任意自定义 Renderer 的挂起不属于 HTTP 超时保证。",
            "error.receipt": "status=succeeded 时显示已保存／同步失败，使用同一 request ID 调 actions.refresh；failed/unknown 不保证回滚，不能自动换 ID 再保存。",
            "superseded": "新 Query 已接管；写入仍可成功，但不要用旧响应覆盖新页面。",
        },
        "timings": {
            "receipt.timings": "毫秒：preparation_ms=资源/代码快照和回执声明；worker_startup_ms=派发到 worker 入口（含 spawn/import）；code_load_ms=恢复快照及导入；python_execute_ms=全部 execute 业务代码；dispatch_to_outcome_ms 包含启动/执行/结果处理/IPC，不与子阶段相加。缺失阶段不当作 0。",
            "receipt.refresh.timings": "scheduling_ms=解析/计划及启动；nodes 提供 duration_ms/status/result_origin，含 Source 和 Transform。result 表示复用，其历史耗时不算本次执行；并行节点耗时不能简单相加。",
            "receipt.client_timings": "浏览器响应附加，不持久化：write_confirmed_ms=首次观察成功；refresh_roundtrip_ms=刷新数据传输及更新；data_prepare_ms=解码准备；runtime_update_ms=输出传播及渲染 Promise；total_ms=调用总时间。不是精确网络或屏幕 paint 时间。",
            "limits": "ActionService 容量满直接拒绝，不排队；未单独测量 HTTP/Run 队列或数据库事务。不能把 Python 约 1 秒解释为 SQLite 写入约 1 秒。",
        },
        "readiness": [
            "GET /api/workspace 的 server.package_version 是运行中服务版本；dataviz version 只证明 CLI 环境。升级后重启旧服务并刷新页面。",
            "确认页面 Run 成功、context.actions.available=true，且 /api/workspace 的 Dashboard server_actions 包含动作 ID。",
            "inspect context --focus action:<id> 检查资源别名、代码和刷新目标；validate 不证明实际数据库可连接或可写。",
            "相对 SQLite/文件路径基准见 docs standalone 和 server-actions；不要向前端输出凭据或任意服务器路径。",
            "保存慢保留 request ID，actions status 查看回执与 refresh.run_id 对应节点耗时；不要重新 invoke 测速。",
        ],
        "commands": ["dataviz docs server-actions --format json", "dataviz docs standalone --format json"],
    },
    "server-actions": {
        "summary": "Server Action：显式调用服务端 Python，完成 writeback、标注、数据库或文件 CRUD 与业务计算；保存后局部刷新，独立于只读 Source/Transform。",
        "commands": [
            "dataviz docs action-save --format json",
            "dataviz schemas server-action --full --format json",
            "dataviz scaffold server-action.python --id save-record --format json",
            "dataviz inspect context <workspace> <dashboard> --focus action:<action> --format json",
            "dataviz validate <workspace> --dashboard <dashboard-id> --strict",
            "dataviz actions invoke <dashboard> <action> --server http://127.0.0.1:8080 --session-id <session> --run-id <run> --request-id <request> --payload-file payload.json",
            "dataviz actions status <dashboard> <action> --server http://127.0.0.1:8080 --session-id <session> --request-id <request>",
            "dataviz actions refresh <dashboard> <action> --server http://127.0.0.1:8080 --session-id <session> --request-id <request>",
        ],
        "example": {"server_actions": [{
            "id": "save_annotation", "code": "actions/annotations.py",
            "entrypoint": "execute",
            "resources": {"annotations": "annotations_database"},
            "invalidates": ["source:annotations", "view:details"],
        }]},
        "python_context": {
            "request_id": "本次显式调用的请求 ID；重查回执和刷新重试使用同一个 ID。",
            "payload": "JSON 对象；Python 必须校验业务主键、允许操作、值域和并发版本。",
            "resources.config(alias)": "返回外部 Adapter 绑定的配置，仅可信服务端 Python 使用；不得返回凭据。",
            "resources.path(alias, relative_path)": "解析声明的文件资源根目录内路径；不要从 payload 接受任意服务器路径或 Adapter 名。",
            "invalidate(reference)": "成功后请求刷新已声明的 source:<id> 或 view:<id>；允许集合不会自动全部执行。",
            "return": "execute(context) 返回 JSON 对象；SQL 参数绑定、事务、CRUD 和业务计算由 Python 负责。",
        },
        "renderer_api": {
            "context.actions.available": "仅连接可用 Server 且有已应用 Run 时调用；portable HTML 不提供写入。",
            "context.actions.invoke(action, payload, options)": "options 可含 requestId 和 onProgress；返回包含写入结果及独立刷新状态的回执。",
            "context.actions.status(action, requestId)": "查询回执，不重跑 Python。",
            "context.actions.refresh(action, requestId)": "仅重试刷新，不重复已保存的业务写入。",
        },
        "http_api": [
            "POST /api/dashboards/{dashboard}/actions/{action}: session_id, run_id, request_id, payload。run_id 必须是当前已完成的 applied Run。",
            "GET /api/dashboards/{dashboard}/actions/{action}/{request_id}?session_id=...：查询回执与刷新进度。",
            "POST /api/dashboards/{dashboard}/actions/{action}/{request_id}/refresh: session_id。",
        ],
        "rules": [
            "CLI 是同一 Server API 的显式客户端，不另起本地执行引擎。run-id 是 Server 当前已完成的 Run，不是磁盘 Result ID；没有可用 Run 时不会为了调用 Action 自动查询数据库。",
            "CLI 输出 JSON 回执；running 表示继续查询 status，而非已完成。--timeout 仅控制等待，不取消服务端写入。CLI 不自动重试、不跟随重定向，也不使用环境代理。",
            "Scaffold 是默认拒绝执行的 Python 起点；需实现业务逻辑并绑定资源。校验成功不代表已实现写入。",
            "这是通用显式命令，不是 checkbox 专用协议；新增、修改、删除、计算都由 Dashboard-local Python 实现。",
            "Action 开发和静态校验不授权执行真实写入；必须先确认用户授权的目标与操作范围。",
            "resources 将代码别名映射到外部 Adapter/auth；数据库和可变文件不放入 standalone 内容快照，也不嵌入 Dashboard 凭据。",
            "同一请求 ID 与相同调用返回已有回执；不同 payload 或 applied Run 复用 ID 会冲突。不同请求 ID 不保证业务去重。",
            "超时、断线或 Python 失败不代表事务已回滚。结果 unknown 时核对回执与业务数据，不得自动换 ID 重试写入。",
            "source 失效只重算该 Source 及下游，复用未受影响分支，生成新 Run；view 失效仅重绘当前输入，不隐式查库。",
            "刷新使用已提交查询状态，不使用未提交草稿；旧 Run 的 Action 不覆盖新查询。",
            "保存成功但刷新失败必须分别展示；error.receipt 可证明保存结果，刷新重试不重跑 Python。",
            "可信 Python 不是安全沙箱；资源声明不是用户认证。当前 Server 仍是可信本地服务，不应无认证暴露写入端点。",
            "浏览器修改请求要求同源和 JSON；没有 Origin 的非浏览器客户端允许调用，这不是认证机制。",
        ],
    },
    "pages": {
        "summary": "多个分析页面、第二条分析路径、不同参数、跨页保存与数据过期：Dashboard 内统一代码，Page 独立 Query 参数、运行结果和 Control；简单看板无需 pages。",
        "status": "已接入按页执行、报告、整项目 Bundle、浏览器导航、按页热更新和共享数据过期提示；关键 Chromium 流程已验证，当前工作树正在进行整体验收。",
        "hot_reload_evidence": "服务端按各 Page 依赖闭包识别代码、参数与展示变化；Workspace Change 的 page_changes 提供按页影响，changes 保留 Dashboard 汇总。Shell 按页标记 Query 定义过期，包括未打开页；不自动查询、不重建未受影响页的 Canvas。导航刷新保留当前 Page 与参数类型。",
        "data_freshness_evidence": "Run 与会话恢复 API 的 data_outdated_sources 返回已声明 Source 失效的 observed/current 版本；这是运行时证据，不修改历史 Result，也不等于 Query 定义变化。只追踪同 Dashboard 下的 Source ID，不根据共用数据库路径猜测依赖。事件连接会提示 Data changed，关闭文件热更新时也有效；未受影响页不变，其他页不会自动查询。用户在过期页 Run 后更新该页；保存成功不代表所有页已同步。",
        "rules": [
            "没有 pages 时继续在顶层声明 query_parameters、controls、sections、views；不需要默认 Page 包装层。",
            "需要第二条分析路径时，将参数与展示移入 pages，每页声明 id/title/query_parameters/controls/sections/views/layout。",
            "sources/dataset_transforms/interactive_transforms/parameter_domains/server_actions 的实现仍由 Dashboard 统一管理。Page.server_actions 是本页可调用的 Action ID 列表。",
            "每页依赖从 View 与候选入口推导，不维护另一份 Source 执行白名单。同名参数没有共享状态。",
            "run --page 选择分析入口；Result 封存 Page 身份，report Result 不重新查询，也不允许改投其他页。",
            "--page 始终可省略：没有 pages 时直接运行顶层看板；只有一页时选中该页；多页时默认第一条声明的 Page，不运行所有页。返回的 page_id 记录实际选择；自动化需要固定入口时显式传 --page。",
            "一个 YAML 仍可完成单页或多页看板；共享代码只在本 Dashboard 内，不引入软链接或跨 Dashboard Source 依赖。",
        ],
        "commands": [
            "dataviz run <workspace-or-yaml> <dashboard> --page history --format json",
            "dataviz run <workspace> <dashboard>::view:details --page history --format json",
            "dataviz report <workspace> <result-id> --output history.html",
        ],
        "related": ["standalone", "dataset-transforms", "controls"],
    },
    "standalone": {
        "summary": "单文件 standalone YAML 看板：内嵌 SQL/Python/JS、小型 Renderer，显式外部 auth；无需维护 Workspace 目录。",
        "commands": [
            "dataviz scaffold standalone --id sales --output ./sales",
            "dataviz validate sales.yaml --auth connections.yaml --strict",
            "dataviz run sales.yaml --auth connections.yaml --format json",
            "dataviz serve sales.yaml --auth connections.yaml",
            "dataviz report sales.yaml <result-id> --auth connections.yaml --output report.html",
        ],
        "example": {
            "schema": DASHBOARD_SCHEMA, "id": "sales", "title": "Sales",
            "sources": [{"id": "sales", "type": "sql", "adapter": "local",
                         "code": {"inline": "select 42 as revenue"},
                         "outputs": {"main": {"kind": "table"}}}],
            "views": [{"id": "total", "template": "metric", "input": "source:sales/main", "value": "revenue"}],
        },
        "adapter_example": {"adapters": {"local": {"type": "sqlalchemy", "url": "sqlite:///:memory:"}}},
        "rules": [
            "scaffold standalone（或省略 recipe）生成一个 dashboard.yaml，内含两行 Python 样例数据，无需 auth、数据库、Page 或浏览器测试扩展；执行返回的 next 命令即可校验和运行。SQL 示例才需要外部 Adapter 配置。",
            "validate/run/serve/report 接受 YAML 文件或含 dashboard.yaml 的目录；已有 Workspace 用法不变。",
            "--auth 显式选择 Adapter YAML、auth 目录或已有 Workspace（也可指定 workspace.yaml）；不自动搜索上级目录，不在看板内放凭据。",
            "auth 目录读取 adapters.yaml 与 adapters.local.yaml；外部 Workspace 只提供 Adapter 环境，不导入其 Source、Asset 或其他 Dashboard。",
            "Adapter 中相对 SQLite/文件路径以配置目录为基准；标准 auth 目录中的配置以 auth 的父目录为基准。指定同一环境的 Workspace、auth 目录或配置文件时路径一致；仅指定文件不会额外加载 local overlay。",
            "独立输入中 code 可为路径或严格的 {inline: text}；canvas.scripts/styles 可混用路径与 inline。SQL、Python 与 browser-js 仍由原有 Runtime 执行；只运行可信代码。",
            "这是独立输入的编译便利语法：先转为普通 Workspace，再执行现有 Schema 校验；Workspace 文件模式和 schemas 输出仍使用 code 文件路径。",
            "引用文件必须位于 YAML 所在目录内；仅携带已声明文件。相邻 presentation.yaml 和其声明资源会一并加载；未声明的动态文件读取不保证可用。",
            "快照与 Result 位于 YAML 同目录的 .dataviz/standalone/<hash>；不要手改生成目录。run 的 next_actions 提供 Result 检查命令。",
            "源文件或声明依赖变化产生新快照；导出旧 Result 时使用其 next_actions 中的原快照路径，不重新编译改过的 YAML。",
            "report 提供 result-id 时不重新查询；省略 target 时会运行该 Dashboard 再导出。",
            "serve 为单看板快照，不显示 Sidebar；编辑原 YAML 或依赖后重启。生成快照不支持页面编辑写回。",
            "凭据文件不复制到快照或报告；私有元数据仅保存外部路径。运行时继续读取外部配置并复用既有脱敏边界。",
            "共享 Workspace Asset、Catalog 管理或常规热更新使用完整 Workspace；可迁入生成的标准 Dashboard 文件，不迁移私有元数据。",
        ],
    },
    "quickstart": {
        "summary": "从空环境到可验证 Dashboard、不可变 Result 和 HTML 报告的最短当前路径。",
        "workspace_start": {
            "single_file": "dataviz scaffold standalone --id sales --output ./sales — 一个可运行 YAML，无需先 init Workspace 或配置数据库。",
            "starter_workspace": "dataviz init <workspace>",
            "focused_scaffold": "dataviz scaffold minimal --id <dashboard-id> --output <workspace>",
            "rule": "init 直接生成可运行的 hello Dashboard；需要特定结构或能力时，再选择对应 Scaffold recipe。",
        },
        "commands": [
            "dataviz scaffold standalone --id sales --output ./sales",
            "dataviz validate ./sales/dashboard.yaml --strict",
            "dataviz run ./sales/dashboard.yaml --format json",
            "dataviz serve ./sales/dashboard.yaml",
        ],
        "next_steps": {
            "query_parameters": "dataviz docs query-parameters --format json",
            "local_interaction": "dataviz docs --task interactive --format json",
            "second_analysis_page": "dataviz docs pages --format json",
            "inspect_or_export_result": "dataviz docs results --format json",
            "debug_or_verify": "dataviz docs workflow --format json",
        },
        "rules": [
            "先生成单个 dashboard.yaml 并运行内嵌的两行样例；不要求 pages、sections、空 controls、外部连接或手工创建 Workspace。接入数据库时再读 standalone 并显式提供 --auth。",
            "serve 用于打开交互页面，不代表已应用前一步 CLI Run；在页面点击 Run 执行查询。查看已有 Result 而不重查时，按 results 文档导出报告。",
            "不要从自定义 HTML/CSS/JS 开始；先用默认 Renderer 证明数据契约。",
            "Adapter 由 Workspace 或 standalone --auth 显式提供；Dashboard 只写逻辑别名，不保存账号密码。",
            "简单看板不要提前加载 Control、Interactive Transform 或 Custom Renderer 契约。",
            "所有 Output 引用必须写完整，例如 source:sales/main、dataset:model/trend、interactive:simulation/result。",
            "每次修改后运行 validate；未知字段、旧 schema 和不完整引用直接失败。",
            "serve 默认热更新 Workspace；Query Contract 改动只标记 Outdated，不会自动执行查询。",
            "自定义 Presentation/CSS 前读取 design-language；先覆盖 Theme token，再使用局部 css_class。",
            "普通 SQL 和文件默认留在 Dashboard 内；只有稳定且确实跨 Dashboard 共用的 GeoJSON、字典或其他静态文件才提升为 Workspace Asset。适度复制优于可变的共享依赖，且不得使用 ../../ 越界路径。",
        ],
        "success": [
            "validate 返回 passed=true。",
            "run 返回不可变 result_id；Result 终态为 ready，或按明确要求接受 partial。",
            "result inspect/show 只读取已封存 Artifact，不重新执行数据源。",
            "HTML report 生成，同时写出 report manifest。",
        ],
        "related": ["progressive-authoring", "workflow", "workspace-assets", "results", "design-language", "validation", "troubleshooting"],
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
            "已知道看板时直接 run <workspace> <dashboard>，或 run sales.yaml --auth connections.yaml；不必先学习 Catalog 或 Target Reference。",
            "run --help 将常用选项、Multi-page and interaction、Advanced analysis 分组；简单运行无需填写高级参数。--dry-run 仅检查显式 --overlay，不是通用查询预览。",
            "--query-param/--control 使用 name=value 或 name=JSON；同一名称只传一次，重复或空名称直接报错，不静默覆盖。参数名不能有首尾空白，值仍可为空字符串或包含等号。",
            "不知道物理引用时先 catalog search；需要全局概览时使用 catalog list。",
            "执行前用 catalog describe 查看参数闭包、默认值、lineage、语义和可复制的 run 命令。",
            "run 只执行一次并原子封存 Result；预览行数不限制已保存的完整 Artifact。",
            "后续分页、检查、导出和 Evidence 都消费 result_id，不重新查询。",
            "Result next_actions 使用 shell 引号保护路径中的空格、单引号、美元符号等；直接复制，不要删除引号或自己改成 JSON 引号。",
            "只有需要临时替换 SQL、代码或 File 输入时才增加 --overlay。",
            "单页无需 --page；显式多页省略时只运行第一条声明的 Page，返回 page_id。需要其他分析入口时才加 --page <id>；Result 的查看和导出沿用已封存 Page，不重复指定。",
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
            "describe 默认文本显示粒度、可信状态、caveats 和调用参数；依赖只计数。--detail debug 展开引用，--detail full 展示节点定义与资产路径/hash，只有 --include-code 才内联代码。",
            "list/search 空结果返回 analysis_catalog_no_matches 提示与只读下一步命令，而不是空白终端；它不表示 Workspace 没有数据，也不会自动纳入 internal、draft 或 deprecated 口径。",
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
            "describe 的错误项附带 Catalog 概览与引用语法文档命令；恢复命令只读，不自动修正引用或执行查询。",
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
            "--from-result 只允许 Dataset Transform 复用其已声明、reference/kind/Schema/hash 兼容的输入 Artifact；不匹配时失败，绝不回退重查 Source。",
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
            "dataviz docs --search '<keywords>' --format json",
            "dataviz docs --task minimal --format json",
            "dataviz docs --task interactive --format json",
            "dataviz docs --task custom-renderer --format json",
            "dataviz docs --component control.select --format json",
            "dataviz scaffold --list --format json",
        ],
        "rules": [
            "未知字段或能力先用 --search 读取专题与 --task 文档中带 topic/path 的正文片段，再执行结果的 command（可能是专题或任务入口）；不要先搜索安装包源码。多关键词有完整命中时优先返回完整匹配，否则保留部分匹配；它是关键词搜索，不是语义问答。",
            "--component 接受 control.select 等 canonical id，也接受可唯一解析的 select 短名；歧义或拼写错误返回可直接复制的候选命令。",
            "minimal 只披露 Adapter → Source → View → Layout。",
            "只有任务需要查询后交互状态或计算时才进入 interactive。",
            "只有内置 View 无法表达视觉时才进入 custom-renderer。",
            "默认 standalone profile 只生成一个可运行 YAML，先 validate → run，不要求浏览器扩展；minimal/interactive/custom-renderer 显式 profile 生成完整 Workspace，可继续 report → visual-check。fragment 需要先合并到所属 Dashboard。",
            "任务路由控制作者上下文，不改变 Runtime 的严格 Schema 或执行语义。",
        ],
        "related": ["quickstart", "workflow", "components", "ai-authoring"],
    },
    "workspace-assets": {
        "summary": "Workspace Asset 让多个 Dashboard 安全复用本地静态文件，并让 Bundle 与离线 HTML 自动携带真实依赖闭包。",
        "choose": {
            "dashboard_local": "默认把只属于一个 Dashboard 的 SQL、CSS、JS 和数据文件放在该 Dashboard 内；少量重复优于跨 Dashboard 的可变逻辑依赖。",
            "workspace_asset": "多个 Dashboard 共用的 GeoJSON、字典、图像或静态数据文件在 workspace.yaml 注册一次。",
            "file_source": "文件作为 Query 数据输入时使用 File Source；确需共享的稳定文件路径写 asset:<id>，并显式声明 format。",
            "parameter_domain": "Query Parameter 候选口径与 SQL 始终放在所属 Dashboard；相似看板复制后独立演进，不建立 Workspace SQL 引用。",
        },
        "workspace_example": """# workspace.yaml
schema: dataviz/workspace/v2
kind: workspace
id: retail
title: Retail
assets:
  china-city:
    path: assets/maps/100000_full_city.json
    media_type: application/geo+json
  store-dictionary:
    path: assets/data/store_dictionary.csv
    media_type: text/csv""",
        "dashboard_example": """# dashboard.yaml
schema: dataviz/dashboard/v20
kind: dashboard
id: city-map
assets: [china-city]  # Browser allowlist and portable-report dependency

sources:
  - id: shared-dictionary
    type: file
    path: asset:store-dictionary  # File Source dependency; no Browser exposure
    format: csv
    outputs: {main: {kind: table}}""",
        "renderer_example": """window.datavizRuntime.registerRenderer('city-map', {
  async mount(context) {
    const geojson = await context.assets.json('china-city');
    // Render with the same code in Server and portable HTML.
  },
  update() {},
  dispose() {},
});""",
        "runtime_service": {
            "api": ["list", "describe", "bytes", "text", "json", "blob", "url"],
            "server": "Server 通过 Dashboard-scoped safe route 和 ETag 提供文件。",
            "portable_html": "文本以 UTF-8、二进制以 base64 内嵌；业务代码不判断 transport。",
            "context": "inspect context 只返回依赖 Asset 的 path/MIME/bytes/hash，不嵌入文件内容。",
        },
        "security_and_portability": [
            "在 workspace.yaml 注册文件不会自动暴露给浏览器；只有 Dashboard.assets 中的显式 allowlist 可由 context.assets 读取。",
            "File Source 的 asset:<id> 引用与 Browser allowlist 相互独立；Source-only 文件不会获得 Browser URL。",
            "普通 SQL 和文件默认归 Dashboard 所有；只有稳定且确实跨 Dashboard 共用的文件才注册为 Workspace Asset，少量复制可以换取更清晰的所有权与迁移边界。",
            "路径必须位于 Workspace 内；不支持绝对路径、远程 URL、软链接逃逸或从 Downloads 读取。",
            "dataviz bundle 复制完整 Dashboard 目录及其实际引用的 Workspace Assets；不复制未引用文件、凭据或 .dataviz/ 下的 cache。Parameter Domain 定义与 SQL 已属于 Dashboard 目录。",
            "Bundle 是单向、自包含快照，不是 import、merge、sync 或 package manager；导出后与源 Workspace 的共享关系已经切断。",
            "Bundle 目标必须不存在或为空；非空目录稳定失败，绝不复用、合并或覆盖其中的 Dashboard、SQL、Asset 和其他用户文件。",
            "Bundle 在目标同级临时目录完整复制并校验 hash 后一次发布；复制期间来源变化会失败且不留下 partial destination。",
        ],
        "commands": [
            "dataviz validate <workspace> --dashboard <dashboard-id> --format json",
            "dataviz inspect context <workspace> <dashboard-id> --format json",
            "dataviz bundle <workspace> <dashboard-id> <destination>",
            "dataviz report <workspace> <dashboard-id-or-result-id> --output report.html",
        ],
        "related": ["quickstart", "custom-renderer", "validation", "html-export"],
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
            "folder": "Sidebar 的文件夹与 Dashboard 名称对应 ## 编码的物理目录位置；Dashboard 可拖到其他文件夹，右键可重命名或使用 Move Dashboard，复制和打包时所见即所得。重命名和移动不改变稳定 id。",
            "id": "CLI、DAG、API 与 Presentation 使用的稳定程序身份。",
            "title": "页面内容，可与文件夹名不同；为空时回退到文件夹末级名称。",
        },
        "minimal_example": """schema: dataviz/dashboard/v20
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
        "summary": "Query Parameter 创建不可变 Query Run；每个参数只保存一份 canonical state，Dashboard-owned SQL 候选由 Server 物化并通过 Lookup 搜索或分页。",
        "reload_restoration": "同标签页刷新应恢复当前 Page 的参数草稿，已提交参数另存于 Run 的 query_parameter_state。查询中和查询完成后均不应把可见日期、单选摘要重置为默认值；底层 input/select 与可见组件必须一起同步。刷新不会自动发起新查询。诊断时同时对照 URL、表单底层值、可见摘要和 Run 参数，不要仅凭面板默认文字认定服务器查询用了默认值。另开标签页不保证继承原会话。",
        "navigation_loading": "切换 Dashboard/Page 不等待候选 Lookup 完成。新导航立即取消旧页面详情和浏览器 Lookup 请求，旧初始化链及迟到响应不能更新新页；目标页详情未就绪时禁止 Run，但导航仍可继续点击。Page 详情读取已安装 Workspace 快照、只构造目标页，不执行全 Workspace 校验；目录发现与全项目检查仍由文件热更新或显式 Workspace 刷新负责。取消浏览器请求不等于取消已经开始的服务端 Domain 物化或数据库查询。",
        "remote_select": "Remote Select 的输入、搜索和翻页只触发 Parameter Lookup；选择提交后才改变 canonical Query Parameter state。打开的下拉框必须立即投影最新 request generation 的候选，迟到响应不得覆盖新搜索。",
        "dynamic_domains": {
            "purpose": "一个 SQL Domain 物化一张完整候选关系；多个 Query Parameter 可从不同字段去重投影，父级变化只在该 generation 上过滤，不重跑 SQL。",
            "example": """parameter_domains: [parameter_domains/locations/domain.yaml]
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
                "Parameter Domain 定义与 SQL 必须位于所属 Dashboard；修改一个看板的候选口径不会改变其他看板。Browser 永远不接收原始关系、SQL、Adapter、物化路径或候选全集。",
                "Browser Lookup 每页返回 500 个纯文本/元数据候选并通过 opaque cursor 继续；CLI 为控制终端和 AI token 密度默认 50、可显式提高到 500。",
                "同一 Dashboard 的 immutable generation 可由多个用户和 tab 复用；不同 Dashboard 即使 SQL 文本相同也拥有独立定义与 generation。",
                "options.depends_on 只对当前 generation 做本地 predicate；single_select 标量按单值 include，multiple_select 按 all/include/exclude/none；搜索、级联和 cursor 分页都不重新执行远端 SQL。",
                "multiple_select 使用 all/include/exclude/none 紧凑集合；all/none 不带 operands，include/exclude 只保存有限例外，绝不展开 10 万候选。",
                "Query Card 的 reload 请求刷新当前 Dashboard 的候选物化；已有 generation 时继续读旧数据，不清空选择、不恢复 default、不执行正式 Query。",
                "每次成功 Query 都封存完整 committed canonical state；Revert 按依赖拓扑恢复该 state，不恢复 default，也不执行正式 Query。",
                "页面刷新与首次 Dashboard hydration 先恢复 URL/tab/committed compact state，再由 Lookup 按依赖拓扑补标签；有限 include/exclude operands 不会被当作新的父级编辑而静默删除。",
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
            ],
            "portability": "Parameter Domain 定义与 SQL 随 Dashboard 目录自然搬运；稳定共享文件使用 Workspace Asset，并由 Bundle 复制依赖闭包。",
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
            "SQL 优先使用 Source query_filters 与 {{ dataviz_filter:<name> }}；all 始终生成 TRUE，include/exclude 生成 IN/NOT IN，空 multiple_input 或 multiple_select none 必须用 empty: passthrough|match_none 明确选择 TRUE/FALSE，永不产生 IN ()。",
            "query_filters 只接受 multiple_input 或 multiple_select；single/range 参数继续使用 query_inputs，不让 SQL Filter 猜测标量语义。",
            "直接消费 candidate multiple 的 value 时必须同时消费 selection，避免把 exclude operands 错当成 include。",
        ],
        "author_diagnostics": {
            "cli": "dataviz inspect query <workspace> <dashboard> --source <source> --query-param '<id>=<json>'",
            "ui": "Query Card 的 { } 按钮只读显示 canonical state、operand/available/unavailable 数、depends_on、Lookup status/request generation、request/commit/visible-refresh 耗时与最近一次确定性协调结果；它不改变 Query。",
            "lookup_timing": "request_ms 覆盖 Browser request 到响应；commit_ms 是响应写入当前 Picker；visible_refresh_ms 是同步后跨两个 animation frame 的可见刷新检查，不是像素级 paint 测量。",
            "boundary": "inspect query 只解释参数化 statement、脱敏 bindings 和 query_filter predicate，不执行 Source，也不隐式创建候选物化。实际行数、耗时、缓存与错误仍以 Result/Execution evidence 为准。",
        },
        "sql_filter_example": """# dashboard.yaml
query_parameters:
  - id: item_nbrs
    type: multiple_select
    value_type: text
    default: {mode: none}
    clearable: true
    options:
      mode: domain
      source: item_catalog
      value_field: item_nbr
      label_field: item_label

# source.yaml
query_filters:
  items: {parameter: item_nbrs, field: item_nbr, empty: passthrough}

# source.sql
# where {{ dataviz_filter:items }}
""",
        "selection_binding": """query_inputs:
  city_values: cities
  city_selection: {parameter: cities, projection: selection}
""",
        "related": ["entity-selection", "sources", "dataset-transforms", "interactive-transforms", "data-entry-components"],
    },
    "entity-selection": {
        "summary": "大型实体候选使用现有 Parameter Domain、服务端 Lookup、紧凑多选状态和 query_filters；不新增 Entity Runtime。",
        "scaffold": "dataviz scaffold query-parameter.entity-select --id item-nbr --format json",
        "default_contract": {
            "parameter": "multiple_select + options.mode=domain + default.mode=none + clearable=true",
            "lookup": "候选全集只在 Server 物化；Browser 按搜索词和 opaque cursor 读取页面。",
            "query": "query_filters.empty=passthrough：空选择不筛选；有限 include 只筛选所选实体。",
            "portable": "Result 与 HTML 只保存 canonical selection，不嵌入候选全集、cursor 或物化文件。",
        },
        "recipe_files": [
            "Parameter Domain definition and SQL",
            "Dashboard Query Parameter snippet",
            "SQL Source definition with query_filters and statement placeholder",
        ],
        "rules": [
            "value_field 使用稳定机器 ID；label/description/group/keywords 只帮助人搜索和识别，不改变参数值。",
            "实体候选 SQL 与所属 Dashboard 一起维护；跨 Dashboard 允许少量复制，避免共享取数口径的隐式影响。稳定字典或 GeoJSON 才使用 Workspace Asset。",
            "不要把十万候选展开成 all operands；all/none 是无 operands 的紧凑状态，include/exclude 只存有限例外。",
            "max_explicit_values 限制显式选择；需要几千 ID 时改用上传清单或临时表 Join，不生成巨大 IN。",
            "Parameter Domain 是候选建议而非合法性白名单；已提交但最新目录缺失的值显示 unavailable，不静默删除。",
        ],
        "operations": [
            "dataviz parameters prewarm <workspace> <dashboard>",
            "dataviz parameters status <workspace> [dashboard]",
            "dataviz parameters lookup <workspace> <dashboard> <parameter> --search <text> --limit 50",
            "dataviz parameters refresh <workspace> <dashboard>",
        ],
        "related": ["query-parameters", "sources", "workspace-assets", "validation"],
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
            "file": "{schema: dataviz/source/v6, kind: source, id: sales, type: file, path: data/sales.csv, outputs: {main: {kind: table}}}",
            "sql": "{schema: dataviz/source/v6, kind: source, id: sales, type: sql, adapter: warehouse, code: sales.sql, query_inputs: {start_date: start_date}, outputs: {main: {kind: table}}}",
            "python": "{schema: dataviz/source/v6, kind: source, id: api, type: python, code: api.py, outputs: {main: {kind: table}}}",
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
        "browser_payload": "浏览器只传输 View（含命名输入、Map Layer、repeat）、Canvas、候选域和活动 browser-js 真正需要的 Base Outputs。仅供 server-python 消费的全量输入留在 Run Artifact，初始页面与实时 Output 事件仅传就绪信息；服务端仍读取并校验完整输入。相同 Output 同时被浏览器消费时仍须传输并受 max_embedded_rows/bytes 限制，不要通过提高上限掩盖错误的消费边界。此优化不改变 HTML 对 server-python 的执行限制。",
        "summary": "Interactive Transform 在不可变 Query Run 上按编译后的 Control consumer bindings 重算 Derived Output。",
        "schema": INTERACTIVE_TRANSFORM_SCHEMA,
        "common_fields": ["runtime", "inputs", "query_inputs", "control_inputs", "trigger", "export", "outputs"],
        "runtimes": {
            "browser-js": "JavaScript Web Worker；Server 与 HTML 共用；支持 Promise、progress、timeout、cancel。",
            "server-python": "独立服务端进程；可用任意已安装 Python 依赖；不能访问 Adapter；HTML 只允许 snapshot/unavailable。",
        },
        "runtime_context": {
            "inputs": "context.inputs.<alias> 或 context.input(<alias>) 读取 inputs 中声明的 Base/Derived Named Output；table 输入也可用 context.table(<alias>)。",
            "rows": "browser-js 推荐 context.rows(alias)：JSON/Arrow/auto 都返回普通行对象数组副本，可用 Array.filter/sort/slice。会物化该表，较大数据优先 context.table(alias) 的列式/Frame API；不要把 Array.isArray(context.inputs.alias) 为 false 当成无数据。",
            "table": "browser-js context.table(alias) 始终返回 DatavizFrame；filter 返回 Frame，sort(field, direction) 按字段排序，rows() 转为数组。原始 context.inputs/input 为兼容保留 JSON 数组或 Arrow Frame；不能对它们混用数组与 Frame 的 sort 接口。rows/table 的未声明别名或非表输入抛 interactive_input_not_table（含 input_alias/input_type），合法空表仍返回空结果。",
            "query_inputs": "context.query_inputs.<alias> 只读取 query_inputs 中显式声明的 Query Parameter projection。",
            "control_inputs": "context.control_inputs.<alias> 只读取 control_inputs 中 mode:value 的局部 alias；mode:filter 已在代码执行前过滤对应输入。不存在 context.selections。",
            "progress": "context.progress(value, message) 报告当前 generation 的有限进度；旧 generation 被 supersede 后不能覆盖新结果。",
            "boundary": "Browser Worker 没有 DOM、Adapter、Source、全局 Control Store 或隐式 Query API；YAML 未声明的值不进入 context。",
        },
        "browser_value_contract": {
            "tables": "JSON/Arrow 的公开 rows/columnar 单元格采用共同表示；Custom Renderer 主表和所有命名辅助表均为 rows[]，scalar/object 不转成表。原始 inputs 的容器仍为兼容保留。",
            "dates": "date 为 YYYY-MM-DD；timestamp 为 UTC ISO 字符串，毫秒精度。无时区 timestamp 按 UTC 时间线解释，不套用本机时区。原始服务端 Artifact 精度不变。",
            "numbers": "超出 JavaScript 安全整数范围的整数、Decimal 均使用精确十进制字符串；浮点非有限值在表传输中为 null。binary 为字节数组，list/struct 递归转换。精确金额计算应留在服务端，不应直接 Number(decimal)。",
            "outputs": "browser-js Named Output 可返回 DatavizFrame，发布前转成 rows。其他输出必须为 JSON 值；Date/Map/Set/typed array/BigInt/undefined/NaN/Infinity/循环引用在缓存或快照边界报 interactive_output_not_json_serializable，包含 path。日期请显式 toISOString()，不要依赖缓存隐式转换。合法共享引用不属于循环。",
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
            "browser-js session cache 使用语义输入签名并有内部 LRU 上限；Control revision 本身不制造 miss，命中/未命中/淘汰进入当前会话 trace，不成为作者 DSL 或业务 Result。",
            "Transform 仍按函数整体执行；Runtime 按每个 Named Output 的稳定 value signature 收窄 View 更新，不支持 outputs.<name>.depends_on_controls。",
            "server-python 可调用 context.progress 与 context.log；日志保存为结构化 Artifact。",
        ],
        "author_diagnostics": {
            "where": "Server Query Card author mode → click one Interactive node",
            "shows": [
                "triggering Controls and input Outputs",
                "missing and actually changed Named Outputs",
                "affected Views",
                "query_executed=false",
                "session cache hit/miss/stored state",
            ],
            "boundary": "This is session-local scheduling evidence; immutable audit remains in Result consumer applied state.",
        },
        "related": ["html-export", "controls", "outputs", "dependencies"],
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
            "select": "平面单选或多选；下拉在视口内提供更宽阅读面，分页/非虚拟候选自动换行显示全文，本地大列表使用固定行高虚拟化并以 Tooltip 提供全文。search/virtual 支持 auto/always/never；单选不提供批量操作。多选无搜索时提供 Select all / Clear，搜索时改为 Select results / Clear results，仅作用于匹配项并保留其他选择；Clear 遵守 clearable，菜单不提供 Revert。",
            "checkbox-group": "2–5 个并列选项的直接多选；不显示全选、反选或清空工具栏。",
            "cascader": "用 path_fields 逐级浏览并选择完整路径。与 select 共用 select_all_label / clear_label：单选仅提供允许的 Clear；多选无搜索时提供 Select all / Clear，搜索时为 Select results / Clear results，仅更新匹配路径并保留其他选择。清空搜索后恢复全域操作；Clear 遵守 clearable，菜单不提供 Revert。",
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
            "Select 与 Cascader 统一使用 select_all_label / clear_label；多选无搜索时提供 Select all、允许时的 Clear，搜索时改为 Select results / Clear results，保留搜索外选择。清空搜索后才能执行全域操作；受 max_selected 限制时禁用，不截断成部分全选。菜单没有 Revert；旧 invert_label 配置仍可读取，但菜单不再切换为 Invert。",
            "远程 Select 搜索结果尚未与搜索词同步或仍有未加载的分页时，Select results / Clear results 均禁用；须加载完整匹配结果，不能把当前页当成全部搜索结果。",
            "Multi Select 的关闭态摘要按有效选择规模表达，而不机械暴露 compact state：all/all_available 显示‘全部’；不超过 max_tag_count（默认 2）时显示具体值；不超过 20 项时显示‘已选 N 项’；更大集合仅在 exclude 一侧更短时显示‘全部，排除 N 项’，否则显示已选数量。菜单批量操作不等于 Query Card 全局 Revert；后者仍恢复上次 committed Query snapshot，不是恢复配置默认值。",
            "Control canonical state 是 {value, revision, intent?}；候选型多选可带 all_available/explicit intent，自由集合只保存 list value。",
            "mode: filter 必须同时解释 value 与 intent：multiple_select 的 all_available 按已解析的候选值过滤，不等于无条件放行整个 Output；compact value=[] 的静态候选仍受 choices 白名单约束，非静态 compact 全选保持通过。empty: passthrough|match_none 解释 explicit 空集。原生 View、Interactive Transform 与 Portable/Web Component Runtime 遵守同一规则。",
            "Multi Select 和 Date Range 用 required 控制是否允许空值；clearable 可显式关闭清空操作，required: true 与 clearable: true 会被 validate 拒绝。",
            "候选依赖用 depends_on 声明直接 Control 父节点；Compiler 计算传递闭包和拓扑顺序。",
            "父字段可从 Control.field/path_fields 解析，不要求每个消费 View 重复声明父 filter。候选异常与空域诊断见 dataviz docs interaction-stability。",
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
            "summary": "一个 Control 可由多个 Bound View 写入；一次 View gesture 也可从同一 datum 原子更新主 Control 与声明过的上下文 Controls，所有写入仍只经过唯一 ControlRuntime。",
            "example": """views:
  - id: store-map
    input: source:stores/main
    template: map
    mark: point
    longitude: lng
    latitude: lat
    control_binding:
      control: dashboard.selected_store
      field: store_id
      writes:
        - {control: dashboard.selected_city, field: city}
""",
            "supported": ["Plotly point/selection event", "Table row", "typed Custom Renderer outlet"],
            "rules": [
                "Control owns values and candidate domain; it never declares highlight, row, cell, Renderer or callback.",
                "主 control/field 决定该 View 的 selected projection；writes 只携带同一手势的上下文，不改变主高亮语义。",
                "The bound View receives candidate rows after ancestor Controls but before the primary target Control filters itself.",
                "A View event can only dispatch select, select_many, clear or reset through context.controlBinding.emit; clear is explicit empty while reset restores the declared initial policy.",
                "For controlBinding.state snapshots, current-context handlers and row highlighting read: dataviz docs renderer-selection --format json.",
                "Runtime 先验证全部 target 再一次提交；任一字段、类型、scope、generation 或 single-value cardinality 无效都会拒绝整次 action，不产生 partial state。",
                "select_many 对每个目标稳定去重；single-value Control 获得多个不同值时拒绝，不能猜 first/last。clear/reset 原子作用于主目标和全部 writes。",
                "Unknown targets, duplicate targets from one View, narrower reverse-scope candidate dependencies, ambiguous aggregate mappings, unsupported Renderers and missing fields fail validation; multiple valid Views may write the same Control.",
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
                "control.select": "Ant Select；单/多选、分组、搜索、max tag、视口约束宽弹层，以及兼顾长标签全文与本地大列表性能的虚拟列表。",
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
            "contract_test": "dataviz renderer test 记录 mount/update/dispose 次数，并拒绝空 mount、dispose 后遗留 DOM 或 hook 失败。",
            "author_evidence": "Server 作者模式按 View 展示最近一次 mount/update 耗时、输入 rows/bytes 与可观察的 lifecycle warning；Copy diagnosis 只聚合这些现有会话事实，不进入 Result/Evidence。",
            "boundary": "生命周期检查只验证 hook、Renderer state 与可观察 DOM，不宣称能够侦测任意第三方事件监听器泄漏。",
            "async_boundary": "终态、View 移除或 Runtime 销毁会作废旧挂载；迟到成功或异常不得覆盖当前状态。旧 context.body 与替换内容隔离；进行中的 update 结束后清理最终 state。mount 返回 state 后其 pending 失败也会调用 dispose。",
            "author_cleanup": "将拥有的节点和资源放在 state 中，dispose 只清理自己拥有的内容，不重新查询全局 DOM 删除新 View。若 mount 在返回 state 前失败，作者应自行释放已分配资源；平台无法收回未返回的任意第三方资源。",
        },
        "isolation": "一个 Renderer 失败只影响自己的 View；输入没有变化时不 update。",
        "named_inputs": {
            "yaml": """- id: geography-and-stores
  template: custom
  renderer: geography-and-stores
  input: interactive:geo-scope/stores
  inputs:
    geography: dataset:map-geography/main
""",
            "javascript": "const stores = descriptor.inputs.main;\nconst geography = descriptor.inputs.geography;",
            "rule": "input 是主 Named Output，inputs 中每个 alias 是额外 Named Output；不要为了让 Renderer 接收多张表而拼接 row_kind 混合表。表格主输入的 descriptor.inputs.main 与 descriptor.rows 使用同一份处理后数据；额外输入只应用 control_inputs 中明确绑定给该 alias 的过滤，不修改原始 Output。",
        },
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
        "metric": {
            "example": """- id: net-uplift
  title: 品类净增量
  template: metric
  input: interactive:uplift/summary
  value: net_uplift_qty
  aggregate: sum
  unit: 件
  secondary:
    value: uplift_ratio
    aggregate: max
    label: 增量率
    format: percent""",
            "semantics": "unit 与主值同一基线；label 是可选说明文字。secondary 只接受一个已计算字段，独立聚合；percent 输入使用 0.2447 这类比例值并显示为 24.47%。",
            "limits": "Metric 不计算公式，不提供趋势箭头或 Sparkline；先在 SQL/Transform 中生成辅助指标。空值显示为 —。Band Section 自动使用紧凑 Metric 几何，不需要尺寸 DSL。",
        },
        "field_matrix": _CHART_FIELD_MATRIX,
        "rule": "先验证数据口径、字段、聚合和 Named Output，再用 Plotly trace/layout/config 调整视觉细节。",
        "plotly_runtime": {
            "version": "4.1.0",
            "grammar": "内置 line/bar/stacked-bar/pie/scatter/heatmap/radar/map 都生成 Plotly traces 与 layout。",
            "native": "复杂视觉由 Custom Renderer 复用 context.charts.plotly，或直接调用完整 Plotly.js API。",
            "interaction": "图例、点击、框选、套索与缩放使用 Plotly 事件和 config；矩形/套索手势提交后自动隐藏临时轮廓并保留 Control 选择，再次点击当前激活的工具可退出选择模式；页面滚动仍由 Dashboard 优先处理。",
            "offline": "Plotly.js 4.1.0 作为固定浏览器资产随 Dataviz 提供；Server 与 portable HTML 使用同一份 JS，不依赖 Python plotly 包。",
        },
        "layout_parameter_binding": {
            "purpose": "让参考线、参考区间、轴范围等 Plotly layout 值读取最近一次 RUN 已提交的 Query Parameter，同时保留 date/number/list 的真实类型。",
            "syntax": "{{ parameters.<id> }}",
            "example": """options:
  layout:
    shapes:
      - type: line
        x0: "{{ parameters.holiday_date }}"
        x1: "{{ parameters.holiday_date }}"
        y0: 0
        y1: 1
        yref: paper
        line: {dash: dash}
""",
            "boundary": "只有 options.layout 中由完整 token 构成的值会进行 typed binding；不支持字符串拼接、表达式、Control 引用，也不处理 options.trace 或 config。validate 会以具体嵌套路径拒绝残留或未知模板。",
            "lifecycle": "绑定读取最近一次 RUN 的 committed Query Parameter；草稿参数不会移动当前 Result 的参考线。结果字段驱动的复杂标注继续在 SQL/Transform 中生成，不新增计算 DSL。",
        },
        "ownership": {
            "data": "Server/Transform 生成 canonical Named Output；Browser Adapter 只把已计算字段投影为 Plotly traces，不重新解释业务口径。",
            "layout": "Dashboard options.layout 保存稳定作者意图；其中完整 {{ parameters.<id> }} 值在 Browser Runtime 中按 committed Query state 进行 typed binding，再合并 Theme、容器尺寸和响应式边距。",
            "config": "Browser Runtime 提供 page-first 滚轮、Modebar、框选交互、Resize 与离线安全默认，并关闭 Plotly 云端分享入口；View config 只覆盖明确的局部需求。",
            "render": "浏览器直接调用内置 Plotly.js 4.1.0 的 newPlot/react/resize/purge，不经过 Python Figure。",
        },
        "official_gallery": "https://plotly.com/javascript/",
        "official_source": "https://github.com/plotly/plotly.js/",
        "gallery_guidance": "先确定需要回答的分析问题，再从 Plotly 官方示例选择 trace 类型，并接入 Named Output、Controls 与 Renderer 生命周期。",
        "source_adaptation": "官方源码可能自行准备 DOM、数据和事件；接入时必须改用 Named Output、声明资产并遵守 Dataviz 生命周期。",
        "recipe_policy": "Dataviz Recipe 只提供少量经过验证的起点，不复制官方示例库、不形成能力白名单，也不替代 Plotly 文档。",
        "service_example": "const state = await context.charts.plotly.mount(node, {data, layout, config});",
        "wheel_and_zoom": {
            "plotly_default": "内置 Plotly 模板关闭 scrollZoom。没有可写 Control binding 的图不显示工具栏；绑定后只显示矩形选择、套索选择和恢复默认值。选择手势结束后临时轮廓自动消失，工具保持激活以便连续选择；再次点击激活工具可退出选择模式、回到普通查看且不清空选区。下载图片不默认出现。",
            "explicit_zoom": "缩放、平移和坐标轴恢复不进入默认工具栏；有明确分析需求时通过 config 覆盖，但不得默认截获 Dashboard 的连续滚动。",
            "custom_renderer": "Custom Renderer 使用 context.charts.plotly；只有明确需求时才启用 scrollZoom。",
        },
    },
    "maps": {
        "summary": "原生 Map View 用唯一 Plotly Renderer 表达经纬度点位、本地 GeoJSON 区域指标，或同一 viewport 内的有序 layers；位置必须真正参与分析问题。",
        "point_example": """- id: stores
  template: map
  mark: point
  input: source:stores/main
  longitude: longitude
  latitude: latitude
  label: store_name
  color: sales
  size: revenue
""",
        "region_example": """# workspace.yaml
assets:
  china-city: {path: assets/maps/china-city.geojson, media_type: application/geo+json}

# dashboard.yaml
assets: [china-city]
views:
  - id: city-sales
    template: map
    mark: region
    input: source:city-sales/main
    geojson: china-city
    data_key: city_code
    feature_key: properties.adcode
    color: revenue
    label: city_name
""",
        "overview_detail_example": """# 全国图保留全部门店；一次点击同时写 City + Store
- id: all-stores
  template: map
  mark: point
  input: source:stores/main
  longitude: longitude
  latitude: latitude
  control_binding:
    control: dashboard.store
    field: store_nbr
    writes:
      - {control: dashboard.city, field: city}

# 城市图只消费 City，并允许继续选择 Store
- id: city-stores
  template: map
  mark: point
  input: source:stores/main
  longitude: longitude
  latitude: latitude
  control_inputs:
    city: {mode: filter, control: dashboard.city, field: city, inputs: [main], empty: match_none}
  control_binding: {control: dashboard.store, field: store_nbr}
""",
        "layers_example": """- id: city-and-stores
  template: map
  layers:
    - id: boundary
      input: source:city-metrics/main
      mark: region
      geojson: china-city
      data_key: city_code
      feature_key: properties.adcode
      color: revenue
    - id: stores
      input: source:stores/main
      mark: point
      longitude: longitude
      latitude: latitude
      label: store_name
      control_binding: {control: dashboard.store, field: store_nbr}
""",
        "contracts": {
            "point": "longitude/latitude 必填；label/color/size 可选。经纬度必须是有限数值。",
            "region": "geojson/data_key/feature_key/color 必填；数据 key 与 GeoJSON feature key 都必须唯一且能连接。",
            "asset": "GeoJSON 必须先在 workspace.yaml 注册，再由 Dashboard.assets 显式 allowlist；Bundle 与 portable HTML 自动携带。",
            "interaction": "control_binding 继续写同一 ControlRuntime；writes 可让一次点击原子更新 Store 与 City。全国图不要消费详情 City/Store，城市图消费 City 并继续写 Store；点击、矩形和套索不创建地图专属状态。内置 Map 会在点位集合变化时重新 fitbounds，只改高亮则保留当前视野。",
            "layers": "单 mark 与 layers 互斥。每个 Layer 有独立 input/mark/字段与可选 control_binding，但共享一个 Plotly 生命周期、viewport 和 ControlRuntime；writer provenance 同时记录 source_view/source_layer。",
            "escape_hatch": "复杂样式继续使用 options.trace、options.layout 和 config；只有超出 point/region 时才使用 Custom Renderer。",
        },
        "geographic_clipping_recipe": {
            "when": "全国 GeoJSON 太大，或结果只涉及少量省市时，在 server-python Dataset Transform 中按实际行政区范围裁剪，再把结果作为 Named Output 交给 Map。",
            "steps": [
                "先规范化 province_code/city_code，并显式处理直辖市。",
                "同时接受 Polygon 与 MultiPolygon；无效 Geometry 应修复或稳定失败，不能静默丢弃。",
                "只保留当前结果范围需要的 features，并保留 join key 与必要 label。",
                "Map viewport 从裁剪后区域和可见点位的并集计算；Store 高亮变化不应重新 fit。",
            ],
            "boundary": "这是 Transform Recipe，不是 GIS DSL。聚合、空间裁剪和业务范围属于 Python/JavaScript；View 只负责渲染与交互。",
        },
        "non_goals": [
            "远程底图 URL 或 token",
            "轨迹、热力聚合、地理编码与 GIS 运算",
            "Python plotly 或第二套地图引擎",
            "仅因为存在地区字段就自动选地图",
        ],
        "commands": [
            "dataviz scaffold view.map --id stores --format json",
            "dataviz validate <workspace> --dashboard <dashboard> --format json",
            "dataviz visual-check <workspace> <dashboard> --target both",
        ],
        "related": ["charts", "workspace-assets", "controls", "validation", "html-export"],
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
            "presentation": ["labels", "formats", "align", "widths", "wrap", "emphasis.columns", "striped", "compact", "layout", "show_count"],
            "behavior": ["sortable", "initial_sort", "sort_desc_first", "searchable", "initial_search", "page_size", "hidden_columns", "column_order", "pinned_columns"],
            "rule": "默认只显示表头和数据；Table 的 show_count、搜索框和分页都必须由作者显式启用。Input 的 show_count 仅与 max_length 一起显示 current / maximum，不展示没有上限语境的裸长度。emphasis.columns 只静态强调少量关键列，不表达条件样式或业务计算。",
        },
        "declarative_example": """- id: revenue-detail
  template: table
  input: source:revenue/main
  options:
    labels: {store_nbr: Store, revenue: Revenue}
    formats: {revenue: ',.2f'}
    align: {revenue: right}
    widths: {store_nbr: 160}
    wrap: false
    emphasis:
      columns: [revenue]
""",
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
            "default": "Server 的 Query Parameters / Dashboard Controls 使用 Q/C 右侧面板；Section/View 默认使用 sidebar，仅需弹窗时显式设置 placement: popover。Sidebar 按 Dashboard → 当前 Section → 当前 View 展示祖先链，不展示兄弟 View；无控件的组省略。C 直接收起已打开的任意 Controls 上下文。",
            "path": "control_panels.<query|dashboard|section|view>；sections.<id>.controls / views.<id>.controls 覆盖本对象，不向子 View 继承",
            "options": {
                "template": ["auto", "stack", "grid"],
                "width": ["auto", "compact", "regular", "wide"],
                "columns": "1–6，表示 popover 网格的最大列数；右侧 sidebar 始终单列，避免将输入压窄",
                "column_width": "160–600 px，默认 280；Dashboard Panel 按有效列数和舒适列宽收口，稀疏表单与单个控件不拉满整行",
                "density": ["compact", "comfortable"],
                "placement": "仅 Section/View 支持 popover 或 sidebar。优先级：本对象 controls.placement → control_panels 对应类型 placement → sidebar；query/dashboard 不接受该字段。",
            },
            "control_span": "control_components.<canonical-key>.span 可显式设为 1 或 2；默认 1，RangePicker 等组件不会自动跨列，窄容器会安全退化为单列。",
            "boundary": "展示位置不提交 Control 或 Query；值、校验、级联与执行仍由共享 Runtime 管理。Sidebar 使用祖先上下文，Popover 仅展示本对象；同时可见时共享 canonical 状态并双向同步。不同入口更新上下文（Query 切换为 Controls），同一 sidebar 入口再次点击收起；popover 入口只开关弹窗，不收起侧栏。右侧隐藏时，仅 sidebar 入口展开右侧。导出 HTML 中 Query 为只读快照，Controls 保持交互与 placement。",
            "example": {
                "control_panels": {
                    "query": {"columns": 6, "column_width": 280, "density": "compact"},
                    "dashboard": {"template": "stack"},
                    "section": {"placement": "sidebar"},
                    "view": {"placement": "sidebar"},
                },
                "views": {"detail": {"controls": {"placement": "popover"}}},
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
            "Workspace Asset 注册、Dashboard Browser allowlist、File Source asset:<id> 引用与 Workspace 内路径约束",
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
                "workspace",
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
                "dashboard_bundle",
                "report_manifest",
                "layout_contract",
                "state_snapshot",
            )
        },
        "browser_assets": {
            "plotly_js": "4.1.0（直接内置，不安装 Python plotly）",
            "tanstack_table_core": "9.2.4（直接内置）",
            "workspace_asset_service": "Runtime v13 的 context.assets；Server URL 与 portable inline 共用同一作者 API。",
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
            "默认正式发布运行完整 Chromium Runtime tests；稳定发布、跨浏览器敏感修改或明确要求时再重复 Firefox/WebKit。",
            "默认正式发布在干净 venv 中对 wheel、sdist、pip ZIP 运行 version/schemas/components check/init/validate/report smoke。",
            "明确约定的快速发布可以缩小浏览器或 smoke 范围，但必须在 Changelog/发布记录中写明省略项，不能把临时例外改写成默认质量门禁。",
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
            "Execution Artifact、NodeCache、Dashboard Parameter Materialization 与不可变 Result 只写入 Workspace/.dataviz；默认缓存由 tab session 隔离，Server Interactive 复用同一 Query Run。",
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
            "author_view": "Server 作者模式的 View renderer signal 投影最近一次刷新原因、是否执行 Query、Named Output 输入 rows/bytes、Renderer mount/update 耗时与 Custom Renderer lifecycle warning；Copy diagnosis 一次复制同一投影。",
        },
        "author_evidence_boundary": "rows/bytes 是浏览器实际消费值的 Arrow 字节数或 canonical JSON 字节数；timing 属于当前会话最新成功 generation，不是持久化性能承诺，也不写入 immutable Result/Evidence。",
        "memory_scope": "进程树 RSS 包含 Playwright driver、browser、workers、native Arrow 与 GPU helper；JS heap 不包含 Worker/native 内存。Firefox/WebKit 不公开 performance.memory 时返回 null，不伪造估值。",
        "fixed_fixture": "benchmarks/scale-workspace 的 row_count=10000/100000/1000000；结果与方法见 docs/runtime-performance.md。",
        "decision": "1M 聚合链路可完成后仍不自动推出通用分页；原始明细 View、候选型 Control 和高基数组合需各自基准触发。",
        "boundary": "Runtime 性能基准只衡量页面运行规模与资源生命周期。",
    },
    "maintenance": {
        "summary": "安全预览并清理 Workspace 的不可变 Result、Execution Artifact、Dashboard 候选物化旧 generation 和持久缓存。",
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
            {"symptom": "Source 失败", "action": "先对已有 Result 使用 result inspect，查看 SQL、Adapter、参数、timeout、node.error 和 traceback。没有结果时保留 CLI 错误 JSON 或 Server Run ID；只有确需复现且允许重新取数时，才对规范 Source Target 单独 run。"},
            {"symptom": "Dataset Transform 失败", "action": "先用 result inspect 检查已有 Result 的 input schema、node.error.traceback 和 node.log。需要复现时读 docs results 的 --from-result 约束，复用兼容输入，不默认重新查 Source。"},
            {"symptom": "查询一直 Loading 或 Unconfirmed，事件断流", "action": "保留当前 Run ID、Dashboard/Page 和服务版本。永久断流会重查原 Run；Retry status 只读取原查询状态，排队/执行中不会当作完成。完成后采用原 Run 快照恢复图表，不重复提交查询。正常临时断流由 EventSource 重连；这不表示任意网络故障都会自动恢复。详见 docs interaction-stability。"},
            {"symptom": "保存未确认、断线或超时 action_response_unknown", "action": "保留 request_id、动作 ID、Dashboard 和原会话；用 actions status 查询同一请求。不要自动换 ID 重试 invoke，不要把 failed/unknown 当作业务事务已经回滚。若回执无法获取或长期 unknown，核对业务数据与服务端记录后再决定，不能默认没保存。详见 docs server-actions。"},
            {"symptom": "保存成功但刷新失败", "action": "先以回执 status=succeeded 确认已保存，再用相同 request_id 调 actions refresh，只重试刷新，不重复执行写入。refresh.status=ready 不等于浏览器已经完成展示；如 client_refresh 失败，应另查 View 诊断。详见 docs action-save。"},
            {"symptom": "排队保存被取消 action_not_submitted", "action": "此项未提交，不等于保存结果未知或已保存。检查是否离开 Canvas、切换 Query 或前一项结果待确认；先处理前一请求的回执，再由用户决定是否重新提交取消项。不要批量盲重试。详见 docs action-save。"},
            {"symptom": "Interactive Transform 失败", "action": "检查 Runtime、trigger、canonical state、generation 与 export.mode；browser-js Derived Output 使用 --runtime browser。"},
            {"symptom": "需要查看更多结果", "action": "不要重新 run；使用 result show 的 --offset/--limit 分页，或 result export 原样复制一个 Artifact。"},
            {"symptom": "Result 引用的 File Source 已变化", "action": "Result 保留实际读取的 path/hash 收据；重新执行产生新 Result，不修改旧 manifest。"},
            {"symptom": "多个 Dashboard 共享 GeoJSON/静态文件", "action": "使用 workspace.yaml assets 注册、Dashboard.assets 显式暴露，并用 dataviz bundle 搬运依赖闭包；不要使用 ../../ 或绝对路径。"},
            {"symptom": "多个 Dashboard 想共用候选或业务 SQL", "action": "不要建立 Workspace SQL 引用；把 Parameter Domain/Source SQL 复制到各 Dashboard 并独立演进。只有稳定本地文件使用 Workspace Asset。"},
            {"symptom": "Parameter Lookup 返回 200 但下拉候选未刷新", "action": "打开 Query Card 作者模式，核对 lookup status、request generation 与 request/commit/visible-refresh 耗时；确认 native options 与可见 rows 属于同一最新请求。迟到成功或失败都不得覆盖较新的搜索或父级状态。"},
            {"symptom": "Bundle 报 dashboard_bundle_destination_not_empty", "action": "选择不存在或为空的新目标目录；Bundle 只创建快照，绝不导入、合并、同步或覆盖已有 Workspace。"},
            {"symptom": "Bundle 报 dashboard_bundle_source_changed", "action": "来源文件在复制期间发生变化；等待写入结束后重新执行 Bundle，失败过程不会发布 partial destination。"},
            {"symptom": "查询成功但 View 为空", "action": "检查 Named Output 字段、类型、显式 Control filter 后行数和 View input。"},
            {"symptom": "多输入 View 等待或失败", "action": "点击 View renderer signal；refresh evidence 会指出 waiting_input/failed_input alias、canonical reference 与 changed_input_aliases，不要先把多张表拼成 row_kind。"},
            {"symptom": "Server 正常但 HTML 失败", "action": "检查 export.mode；server-python 不能离线重算，browser-js 的代码和依赖必须随报告嵌入。"},
            {"symptom": "源码环境 ModuleNotFoundError", "action": "在 dataviz-tool 下运行 uv sync --python 3.12 --extra dev --no-editable --reinstall-package ai-dataviz；后续 CLI 使用 uv run --no-editable dataviz。"},
        ],
        "evidence": [
            "CLI version 与运行中 GET /api/workspace 的 server.package_version；两者可能来自不同安装。",
            "故障发生时的 Dashboard/Page、Run ID 或 Action request_id、操作顺序及时间；不要在取证时先重新提交。",
            "dataviz validate 的完整 JSON。",
            "result inspect 的状态、Node error、traceback、log 和 provenance。",
            "Sources 面板中的参数化 SQL 与解析 SQL。",
            "HTML 同目录的 manifest。",
            "分享前脱敏：SQL、日志、traceback、manifest 与浏览器 trace 可能含业务值和路径。优先使用作者模式 Copy diagnosis，并审阅内容；不要上传凭据或原始生产数据。",
        ],
    },
}


def resolve_doc_topic(topic: str) -> str:
    normalized = topic.strip().lower()
    return DOC_TOPIC_REDIRECTS.get(normalized, normalized)


def _resolve_component_identifier(
    requested: str,
    catalog: dict[str, dict[str, Any]],
) -> str:
    normalized = requested.casefold()
    exact = [identifier for identifier in catalog if identifier.casefold() == normalized]
    if exact:
        return exact[0]

    suffix_matches = [
        identifier
        for identifier in catalog
        if "." not in requested and identifier.rsplit(".", 1)[-1].casefold() == normalized
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    if suffix_matches:
        commands = "; ".join(
            f"dataviz docs --component {identifier} --format json"
            for identifier in suffix_matches
        )
        raise ValueError(
            f"Ambiguous Component short name {requested!r}. Use one of: "
            f"{', '.join(suffix_matches)}. Commands: {commands}"
        )

    aliases: dict[str, list[str]] = {}
    for identifier in catalog:
        aliases.setdefault(identifier.casefold(), []).append(identifier)
        aliases.setdefault(identifier.rsplit(".", 1)[-1].casefold(), []).append(identifier)
    close_aliases = get_close_matches(normalized, aliases, n=5, cutoff=0.45)
    suggestions = list(dict.fromkeys(
        identifier
        for alias in close_aliases
        for identifier in aliases[alias]
    ))[:5]
    if suggestions:
        commands = "; ".join(
            f"dataviz docs --component {identifier} --format json"
            for identifier in suggestions
        )
        raise ValueError(
            f"Unknown Component: {requested}. Did you mean: "
            f"{', '.join(suggestions)}? Commands: {commands}"
        )
    raise ValueError(
        f"Unknown Component: {requested}. List available ids with: "
        "dataviz components list --format json"
    )


def _documentation_fragments(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _documentation_fragments(child, (*path, str(key)))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _documentation_fragments(child, (*path, f"[{index}]"))
        return
    if isinstance(value, str) and value.strip():
        yield path, " ".join(value.split())


def _documentation_snippet(text: str, terms: tuple[str, ...], limit: int = 240) -> str:
    folded = text.casefold()
    positions = [folded.find(term) for term in terms if folded.find(term) >= 0]
    if len(text) <= limit:
        return text
    center = min(positions) if positions else 0
    start = max(0, center - limit // 3)
    end = min(len(text), start + limit)
    start = max(0, end - limit)
    return f"{'…' if start else ''}{text[start:end]}{'…' if end < len(text) else ''}"


def _documentation_path(path: tuple[str, ...]) -> str:
    result = ""
    for segment in path:
        if segment.startswith("["):
            result += segment
        else:
            result += f"{'.' if result else ''}{segment}"
    return result


def search_documentation(search: str, *, limit: int = 20) -> dict[str, Any]:
    """Return ranked, bounded leaf snippets instead of complete matching topics."""
    if limit < 1:
        raise ValueError("Documentation search limit must be positive")
    query = " ".join(search.split())
    if not query:
        raise ValueError("Documentation search requires a non-empty query")
    terms = tuple(dict.fromkeys(part.casefold() for part in query.split()))
    redirected_topic = resolve_doc_topic(query.casefold().replace(" ", "-"))
    matches: list[dict[str, Any]] = []
    documents = [
        (topic, definition, f"dataviz docs {topic} --format json")
        for topic, definition in DOC_TOPICS.items()
    ]
    # Index each task-owned document once, without duplicating inherited closures.
    for identifier, definition in AUTHORING_DOCUMENTS.items():
        owner = next((
            task for task, route in AUTHORING_ROUTES.items()
            if identifier in route["documents"]
        ), None)
        if owner is not None:
            documents.append((
                f"task:{identifier}", definition,
                f"dataviz docs --task {owner} --format json",
            ))
    for topic, definition, command in documents:
        summary = str(definition.get("summary", definition.get("purpose", "")))
        for path, text in _documentation_fragments(definition):
            path_text = _documentation_path(path)
            searchable = f"{topic} {path_text} {text}".casefold()
            matched_terms = sum(term in searchable for term in terms)
            if not matched_terms and not (topic == redirected_topic and path_text == "summary"):
                continue
            score = matched_terms * 20
            topic_folded = topic.casefold()
            path_folded = path_text.casefold()
            text_folded = text.casefold()
            if matched_terms == len(terms):
                score += 45
            if topic == redirected_topic:
                score += 35
            if query.casefold() in text_folded:
                score += 70
            if query.casefold() == topic_folded:
                score += 120
            elif query.casefold() in topic_folded:
                score += 80
            if path_text == "summary":
                score += 45
            if all(term in path_folded for term in terms):
                score += 30
            if all(term in text_folded for term in terms):
                score += 20
            matches.append(
                {
                    "topic": topic,
                    "path": path_text,
                    "snippet": _documentation_snippet(text, terms),
                    "summary": summary,
                    "command": command,
                    "score": score,
                    "complete": matched_terms == len(terms) or (
                        topic == redirected_topic and path_text == "summary"
                    ),
                }
            )
    # Prefer complete matches; partial matching remains a fallback for sparse docs.
    if any(item["complete"] for item in matches):
        matches = [item for item in matches if item["complete"]]
    matches.sort(key=lambda item: (-item["score"], item["topic"], item["path"]))
    total = len(matches)
    selected: list[dict[str, Any]] = []
    per_topic: dict[str, int] = {}
    for item in matches:
        if per_topic.get(item["topic"], 0) >= 5:
            continue
        selected.append(item)
        per_topic[item["topic"]] = per_topic.get(item["topic"], 0) + 1
        if len(selected) == limit:
            break
    results = [
        {key: value for key, value in item.items() if key not in {"score", "complete"}}
        for item in selected
    ]
    suggestions = []
    if not results:
        vocabulary = list(DOC_TOPICS) + list(DOC_TOPIC_REDIRECTS)
        suggestions = get_close_matches(query.casefold(), vocabulary, n=5, cutoff=0.4)
    return {
        "schema": DOC_SEARCH_SCHEMA,
        "query": query,
        "results": results,
        "returned": len(results),
        "total": total,
        "truncated": total > len(results),
        "suggestions": suggestions,
    }


def docs_catalog(search: str | None = None) -> dict[str, dict[str, Any]]:
    if not search:
        return DOC_TOPICS
    needle = search.casefold()
    return {
        name: definition
        for name, definition in DOC_TOPICS.items()
        if needle in name.casefold() or needle in str(definition).casefold()
    }
