from __future__ import annotations

from typing import Any

from dataviz.components import component_index
from dataviz.protocols import RUNTIME_PROTOCOL_SCHEMA
from dataviz.view_contracts import VIEW_TEMPLATE_CONTRACTS


VIEW_TEMPLATES: dict[str, dict[str, Any]] = {
    name: {
        "purpose": contract["purpose"],
        "fields": list(contract["required"]),
        "optional": list(contract["optional"]),
        **({"one_of": contract["one_of"]} if contract.get("one_of") else {}),
        **({"aggregate": contract["aggregate"]} if contract.get("aggregate") else {}),
    }
    for name, contract in VIEW_TEMPLATE_CONTRACTS.items()
}

SECTION_TEMPLATES: dict[str, dict[str, str]] = {
    "single": {"purpose": "One full-width view"},
    "stack": {"purpose": "Full-width narrative sequence"},
    "grid": {"purpose": "Equal-weight responsive views"},
    "split": {"purpose": "Primary view with a narrower companion"},
    "hero-metrics": {"purpose": "Hero chart followed by KPI cards"},
    "chart-and-table": {"purpose": "Chart beside an analysis table"},
    "comparison": {"purpose": "Two equal views"},
    "band": {"purpose": "Compact KPI strip"},
    "small-multiples": {"purpose": "Repeat one View blueprint for every data group"},
    "selection-gallery": {"purpose": "Search or cascade-select groups and repeat only the chosen View instances"},
}

LAYOUT_TEMPLATES: dict[str, dict[str, str]] = {
    "overview": {"purpose": "General executive overview"},
    "monitoring": {"purpose": "Dense operational monitoring"},
    "report": {"purpose": "Long-form analytical narrative"},
    "exploration": {"purpose": "Filter- and table-led exploration"},
    "freeform": {"purpose": "Explicit item widths with minimal preset behavior"},
}

THEME_PRESETS: dict[str, dict[str, str]] = {
    "plain": {"purpose": "Minimal neutral analysis style"},
    "editorial": {"purpose": "Warm report and narrative style"},
    "terminal": {"purpose": "Dark technical monitoring style"},
    "business": {"purpose": "Clean neutral analytical default"},
}

THEME_TOKENS = [
    "--dv-paper",
    "--dv-panel",
    "--dv-overlay-surface",
    "--dv-soft",
    "--dv-soft-blue",
    "--dv-ink",
    "--dv-muted",
    "--dv-line",
    "--dv-accent",
    "--dv-accent-strong",
    "--dv-green",
    "--dv-amber",
    "--dv-red",
    "--dv-blue",
    "--dv-chart-grid",
    *[f"--dv-chart-{index}" for index in range(1, 9)],
    "--dv-radius",
    "--dv-radius-sm",
    "--dv-shadow",
    "--dv-shadow-float",
    "--dv-font-sans",
    "--dv-font-mono",
    "--dv-header-bg",
]


COMPONENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "control-panel.adaptive": {
        "category": "presentation",
        "purpose": "Keep Query Parameters and scoped Controls readable inside the viewport",
        "use_when": "A Dashboard has enough controls to need a responsive grid or a bounded scrolling tray",
        "presentation": {
            "path": "controls.<query|dashboard>; sections.<id>.controls; views.<id>.controls",
            "options": ["template", "width", "columns", "column_width", "density"],
            "templates": ["auto", "stack", "grid"],
            "widths": ["auto", "compact", "regular", "wide"],
        },
        "behavior": {
            "auto": "Query uses a width-derived responsive grid; scoped Controls stack unless grid is explicit",
            "query_columns": "columns is a maximum and column_width is the bounded target track width; sparse forms keep trailing whitespace",
            "viewport": "The tray never exceeds the viewport and scrolls its fields internally",
            "ownership": "Presentation changes composition only; shared Runtime owns values, validation, cascade and execution",
            "export": "Scoped Controls stay interactive in Server and exported HTML; Query is a fixed snapshot after export",
        },
        "semantic_dom": ["[data-dv-control-panel]", ".parameter-form", ".selection-form"],
        "tokens": ["--dv-ink", "--dv-line", "--dv-panel"],
        "example": {
            "presentation.yaml": {
                "controls": {
                    "query": {"template": "grid", "width": "wide", "columns": 3, "density": "compact"},
                    "dashboard": {"template": "grid", "width": "regular", "columns": 2},
                }
            }
        },
    },
    "view.table": {
        "category": "view",
        "purpose": "Default TanStack-powered data expression table",
        "logic": {
            "template": "table",
            "fields": ["input"],
            "optional": ["columns", "sort", "limit", "options"],
        },
        "presentation": {
            "options": ["min_height", "container", "css_class", "options"]
        },
        "behavior": {
            "runtime": "Locally bundled @tanstack/table-core 9.2.4; no React or Runtime CDN",
            "defaults": "Dataviz owns semantic DOM, accessible headers, styling, numeric alignment, sorting and Control Binding",
            "optional_features": ["labels", "formats", "align", "widths", "wrap", "emphasis.columns", "searchable", "page_size", "hidden_columns", "column_order", "pinned_columns"],
            "custom_service": "context.tables.tanstack provides managed lifecycle; context.tables.tanstack.core exposes the complete headless API",
            "wheel_boundary": "Scroll the table only while it can consume vertical movement; otherwise continue scrolling the page",
        },
        "semantic_dom": [".dv-view--table", ".dv-table-toolbar", ".dv-table-meta", ".dv-table-wrap", ".dv-table", ".dv-table-pagination"],
        "tokens": ["--dv-ink", "--dv-line", "--dv-panel", "--dv-paper"],
    },
    "view.plotly-category": {
        "category": "view",
        "purpose": "Render categorical bar or line charts with explicit legend semantics",
        "use_when": "A bar or line View contains one or more series",
        "logic": {
            "templates": ["bar", "stacked-bar", "line"],
            "fields": ["input", "x", "y"],
            "optional": ["series", "aggregate"],
        },
        "presentation": {
            "options": ["layout", "trace", "config"],
        },
        "behavior": {
            "legend": "Plotly owns native series visibility and double-click isolation",
            "analysis": "Zoom, pan, box/lasso selection and autoscale remain available through Plotly",
        },
        "semantic_dom": [".dv-view", ".dv-chart", ".dv-plotly"],
        "tokens": ["--dv-ink", "--dv-line", "--dv-panel", "--dv-paper"],
        "example": {
            "dashboard.yaml": {
                "id": "district-bars",
                "template": "bar",
                "input": "source:cities/main",
                "x": "district",
                "y": "value",
                "series": "city",
            },
            "presentation.yaml": {
                "views": {
                    "district-bars": {
                        "options": {"layout": {"legend": {"orientation": "h"}}}
                    }
                }
            },
        },
    },
    "view.perspective": {
        "category": "view",
        "purpose": "End-user grouping, aggregation, pivoting and multidimensional exploration",
        "logic": {
            "template": "perspective",
            "fields": ["input"],
            "optional": ["columns", "sort", "limit", "config"],
        },
        "presentation": {
            "options": ["min_height", "container", "css_class", "config"]
        },
        "behavior": {"wheel_boundary": "Shadow-DOM scrolling yields to the page for short data and at the top or bottom boundary"},
        "semantic_dom": [".dv-view--perspective", ".dv-perspective", ".dv-perspective-loading"],
        "tokens": ["--dv-ink", "--dv-line", "--dv-panel", "--dv-paper"],
    },
    "section.small-multiples": {
        "category": "section",
        "purpose": "Inspect every entity through one repeated View blueprint",
        "use_when": "The same chart should be shown for every store, product, region or model",
        "logic": {
            "template": "small-multiples",
            "fields": ["views", "repeat.by"],
            "repeat": [
                "view", "input", "by", "title", "limit", "order_by", "order", "render",
                "searchable", "search_placeholder", "page_size", "recycle_offscreen",
            ],
        },
        "behavior": {
            "dataset": "One shared browser dataset, indexed into groups without copying Source nodes",
            "render": "Lazy by default; offscreen charts are disposed and recreated on demand",
            "scale": "Search plus page_size bounds DOM/card count for large group sets",
            "identity": "view:<blueprint>@<section>/<group-key>",
        },
        "semantic_dom": [".dv-section--small-multiples", ".dv-repeat", ".dv-repeat-card"],
        "tokens": ["--dv-repeat-columns", "--dv-repeat-min-height", "--dv-gap", "--dv-panel", "--dv-line"],
    },
    "section.selection-gallery": {
        "category": "section",
        "purpose": "Render repeated View instances only for groups selected by the user",
        "use_when": "Users need searchable or hierarchical multi-selection before comparing entities",
        "logic": {
            "template": "selection-gallery",
            "fields": ["controls", "views", "repeat.by", "repeat.control"],
            "recommended_components": ["control.select", "control.cascader", "control.tree-select"],
        },
        "behavior": {
            "empty_selection": "Show the configured empty state instead of rendering every group",
            "export": "Keep every source row available and use the exported selection as initial state",
            "redraw": "Create or remove only this Section's repeated instances",
        },
        "semantic_dom": [".dv-section--selection-gallery", ".dv-repeat", ".dv-repeat-empty", ".dv-repeat-card"],
        "tokens": ["--dv-repeat-columns", "--dv-repeat-min-height", "--dv-gap", "--dv-panel", "--dv-line"],
    },
    "output.named": {
        "category": "data",
        "purpose": "Expose stable typed results from a Source, Dataset Transform, or Interactive Transform",
        "use_when": "Several Views reuse different tables, scalars, text, or objects from one computation",
        "logic": {
            "reference": "source|dataset|interactive:<node-id>/<output-name>",
            "kinds": ["table", "scalar", "object", "text", "html", "chart", "image", "file"],
            "optional": ["schema", "format", "mime_type", "description", "required"],
        },
        "behavior": {
            "explicit": "Every node declares outputs; even main is referenced explicitly as <kind>:<id>/main",
            "validation": "Declared names, kinds, required outputs, and table schemas are enforced",
        },
        "example": {
            "outputs": {
                "trend": {"kind": "table", "schema": [{"name": "date"}, {"name": "revenue", "dtype": "float64"}]},
                "total": {"kind": "scalar"},
            }
        },
    },
    "dataset-transform.server-python": {
        "category": "transform",
        "purpose": "Run query-stage Python against explicit Base Named Outputs",
        "logic": {
            "kind": "dataset_transform",
            "runtime": "server-python",
            "fields": ["id", "code", "inputs", "outputs"],
            "optional": ["entrypoint", "query_inputs", "input_schemas", "code_dependencies", "python_dependencies", "timeout_seconds", "cache"],
        },
        "behavior": {
            "isolation": "Fresh spawned process per execution",
            "timeout": "Hard termination when timeout_seconds is exceeded",
            "failure": "Node-local traceback plus execution-log Artifact",
            "cache": "Code, dependencies, packages, parameters, Adapter, and upstream hashes",
        },
    },
    "interactive-transform.browser-js": {
        "category": "transform",
        "purpose": "Derive interactive Named Outputs in a JavaScript Worker without DOM access or a new query",
        "logic": {
            "kind": "interactive_transform",
            "runtime": "browser-js",
            "fields": ["id", "runtime", "code", "inputs", "export", "outputs"],
            "optional": ["entrypoint", "query_inputs", "control_inputs", "trigger", "debounce_ms", "timeout_seconds", "cache"],
        },
        "behavior": {
            "contract": "Pure serializable sync/async function returning a Named Output object",
            "context": "Read only declared aliases from context.inputs, context.query_inputs, and context.control_inputs; context.selections does not exist",
            "invalidation": "Only declared Selection dependencies and downstream Views update",
            "execution": "Dedicated Web Worker with cancellation and a hard timeout",
            "registration": "window.datavizRuntime.registerInteractiveTransform(spec, {code, entrypoint})",
        },
    },
    "interactive-transform.server-python": {
        "category": "transform",
        "purpose": "Run heavy interaction-stage Python against one immutable Query Run",
        "logic": {
            "kind": "interactive_transform",
            "runtime": "server-python",
            "fields": ["id", "runtime", "code", "inputs", "export", "outputs"],
            "optional": ["entrypoint", "query_inputs", "control_inputs", "python_dependencies", "code_dependencies", "trigger", "debounce_ms", "timeout_seconds", "cache"],
        },
        "behavior": {
            "adapter": "Unavailable by contract; Interactive Transform cannot query new data",
            "isolation": "Fresh process per generation with timeout and cancellation",
            "scope": "Session, Dashboard, Query Run, Transform, and generation",
            "export": "Static reports use snapshot or an explicit unavailable state",
        },
    },
    "renderer.custom": {
        "category": "renderer",
        "purpose": "Add one View renderer without replacing the Canvas Runtime",
        "logic": {
            "registration": "window.datavizRuntime.registerRenderer(id, lifecycle)",
            "lifecycle": ["validate", "mount", "update", "dispose"],
        },
        "behavior": {
            "isolation": "A renderer failure marks only its View failed",
            "state": "Runtime retains renderer state per View id",
            "inputs": "Declare input as the primary Named Output and optional inputs as additional aliases; read them from descriptor.inputs.main / descriptor.inputs.<alias>. descriptor.rows is only the primary-input convenience projection",
            "platform_matrix": [
                "mount", "update", "empty", "restore",
                "interaction", "resize", "dispose", "export",
            ],
            "chart_service": "Prefer context.charts.plotly so theme, page-first wheel behavior, resize, update and disposal remain platform-owned",
            "table_service": "Use context.tables.tanstack for the managed default table or context.tables.tanstack.core for unrestricted TanStack Table Core",
        },
    },
}


COMPONENT_REGISTRY_VERSION = "6.2.0"


def _generated_component_templates() -> dict[str, dict[str, Any]]:
    """Create discoverable contracts for every strict DSL template.

    Specialized contracts in ``COMPONENT_TEMPLATES`` override these defaults.
    This keeps the CLI Registry complete when a new schema template is added.
    """
    generated: dict[str, dict[str, Any]] = {}
    for name, definition in VIEW_TEMPLATES.items():
        optional = definition.get("optional", [])
        presentation_options = ["min_height", "container", "css_class"]
        presentation_options.extend(
            field
            for field in ("options", "config")
            if field in optional
        )
        required_inputs = "input" in definition.get("fields", [])
        optional_inputs = "input" in optional or "inputs" in optional
        generated[f"view.{name}"] = {
            "category": "view",
            "purpose": definition["purpose"],
            "logic": {
                "template": name,
                "fields": definition.get("fields", []),
                "optional": optional,
                **({"one_of": definition["one_of"]} if definition.get("one_of") else {}),
                **({"aggregate": definition["aggregate"]} if definition.get("aggregate") else {}),
            },
            "presentation": {
                "options": presentation_options,
            },
            "behavior": {
                "input": (
                    "Consumes a canonical Named Output"
                    if required_inputs
                    else "May consume a canonical Named Output"
                    if optional_inputs
                    else "Self-contained; consumes no Named Output"
                ),
                "lifecycle": {
                    "author_hooks": ["validate", "mount", "update", "dispose"],
                    "platform_matrix": [
                        "mount", "update", "empty", "restore",
                        "interaction", "resize", "dispose", "export",
                    ],
                },
                "failure_scope": "view",
            },
            "semantic_dom": [".dv-view", f".dv-view--{name}", ".dv-view-body"],
            "tokens": ["--dv-accent", "--dv-ink", "--dv-line", "--dv-panel"],
        }
    for name, definition in SECTION_TEMPLATES.items():
        generated[f"section.{name}"] = {
            "category": "section",
            "purpose": definition["purpose"],
            "logic": {
                "template": name,
                "fields": ["id", "views"],
                "optional": ["title", "description", "controls", "columns", "repeat"],
            },
            "presentation": {"options": ["template", "columns", "css_class"]},
            "behavior": {
                "default_flow": "document order",
                "selection_scope": "Only Views owned by this Section",
            },
            "semantic_dom": [".dv-section", f".dv-section--{name}"],
            "tokens": ["--dv-gap", "--dv-line", "--dv-panel"],
        }
    for name, definition in LAYOUT_TEMPLATES.items():
        generated[f"layout.{name}"] = {
            "category": "layout",
            "purpose": definition["purpose"],
            "logic": {"template": name, "fields": [], "optional": ["columns", "gap"]},
            "behavior": {
                "coordinates": False,
                "custom_canvas": "May place stable View hosts with arbitrary HTML/CSS",
            },
            "semantic_dom": [".dv-canvas", f".dv-layout--{name}"],
            "tokens": ["--dv-gap", "--dv-paper", "--dv-panel"],
        }
    for name, definition in THEME_PRESETS.items():
        generated[f"theme.{name}"] = {
            "category": "theme",
            "purpose": definition["purpose"],
            "presentation": {
                "preset": name,
                "optional": ["accent", "background", "panel", "ink", "density"],
            },
            "semantic_dom": [f".dv-theme--{name}"],
            "tokens": THEME_TOKENS,
        }
    generated.update(COMPONENT_TEMPLATES)
    return generated


def component_catalog(category: str | None = None) -> dict[str, dict[str, Any]]:
    packages = component_index()
    definitions = _generated_component_templates()
    for name, packaged in packages.items():
        declaration = {
            key: value
            for key, value in packaged.items()
            if key not in {"package", "stories", "tests"}
        }
        # A physical Component Package is the semantic source of truth. Generated
        # contracts exist only for DSL templates that do not own a package yet.
        definitions[name] = {**definitions.get(name, {}), **declaration}
    result: dict[str, dict[str, Any]] = {}
    for name, definition in definitions.items():
        if category is not None and definition.get("category") != category:
            continue
        packaged = packages.get(name)
        stories = packaged.get("stories", []) if packaged else []
        story = stories[0] if stories else None
        package_metadata = packaged.get("package") if packaged else None
        result[name] = {
            "schema": "dataviz/component/v1",
            "id": name,
            "version": package_metadata["version"] if package_metadata else COMPONENT_REGISTRY_VERSION,
            "status": packaged.get("status", "unpackaged") if packaged else "unpackaged",
            **definition,
            "package": package_metadata,
            "implementation": (
                {
                    **package_metadata["implementation"],
                    "assets": package_metadata["runtime"],
                }
                if package_metadata
                else {}
            ),
            "tests": packaged.get("tests", []) if packaged else [],
            "gallery": {
                "available": bool(story),
                "workspace": "builtin" if story else None,
                "dashboard": story.get("gallery", {}).get("dashboard") if story else None,
                "anchor": story.get("gallery", {}).get("anchor") if story else None,
                "story": story.get("id") if story else None,
            },
        }
    return result


def template_catalog() -> dict[str, Any]:
    return {
        "views": VIEW_TEMPLATES,
        "sections": SECTION_TEMPLATES,
        "layouts": LAYOUT_TEMPLATES,
        "themes": THEME_PRESETS,
        "component_registry_version": COMPONENT_REGISTRY_VERSION,
        "runtime_protocol": RUNTIME_PROTOCOL_SCHEMA,
        "components": component_catalog(),
        "presentation": {
            "schema": "dataviz/presentation/v2",
            "optional": True,
            "id_scopes": ["sections", "views", "control_components"],
            "visual_fields": ["theme", "layout", "sections", "views", "control_components", "control_panels", "assets", "canvas"],
            "protected_logic": ["adapters", "query_parameters", "controls", "sources", "dataset_transforms", "interactive_transforms", "sections", "views"],
        },
        "selection_operators": ["auto", "equals", "in", "between", "contains", "gte", "lte", "gt", "lt"],
        "extension_path": [
            "declarative",
            "template-options",
            "theme-tokens",
            "custom-view-renderer",
            "custom-canvas",
        ],
    }
