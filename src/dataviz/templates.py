from __future__ import annotations

from typing import Any

from dataviz.components import component_index


VIEW_TEMPLATES: dict[str, dict[str, Any]] = {
    "metric": {"purpose": "Single scalar or aggregated table KPI", "fields": ["input"], "optional": ["value", "aggregate", "label"]},
    "line": {"purpose": "Trend or ordered series", "fields": ["input", "x", "y"], "optional": ["series", "aggregate", "engine"]},
    "bar": {"purpose": "Category comparison", "fields": ["input", "x", "y"], "optional": ["series", "aggregate", "engine"]},
    "stacked-bar": {"purpose": "Part-to-whole category comparison", "fields": ["input", "x", "y", "series"], "optional": ["aggregate", "engine"]},
    "pie": {"purpose": "Compact part-to-whole view", "fields": ["input", "label", "value"], "optional": ["aggregate", "engine"]},
    "scatter": {"purpose": "Relationship between measures", "fields": ["input", "x", "y"], "optional": ["series", "color", "size", "engine"]},
    "heatmap": {"purpose": "Two-dimensional intensity matrix", "fields": ["input", "x", "y", "z"], "optional": ["aggregate", "engine"]},
    "radar": {"purpose": "Compare multiple measures across entities", "fields": ["input", "label", "columns"], "optional": ["limit", "engine", "options"]},
    "table": {"purpose": "Themeable presentation table", "fields": ["input"], "optional": ["columns", "limit", "options"]},
    "perspective": {"purpose": "Interactive table, sorting, filtering and pivoting", "fields": ["input"], "optional": ["columns", "config"]},
    "markdown": {"purpose": "Narrative text or text Named Output", "fields": [], "optional": ["input", "text"]},
    "image": {"purpose": "Image or generated visual", "fields": ["url"], "optional": ["title"]},
    "custom": {"purpose": "Trusted extension rendered by a registered lifecycle", "fields": ["input", "renderer"], "optional": ["inputs", "options", "config"]},
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
    "plain": {"purpose": "Neutral analytical default"},
    "editorial": {"purpose": "Warm report and narrative style"},
    "terminal": {"purpose": "Dark technical monitoring style"},
    "business": {"purpose": "Crisp enterprise analysis style"},
}


COMPONENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "selector.select": {
        "category": "selector",
        "purpose": "Search and select from one flat option list at any supported scale",
        "use_when": "More than four single-select or eight multi-select choices, or whenever a compact control is preferred",
        "logic": {"types": ["single_select", "multi_select"], "fields": ["choices"]},
        "presentation": {
            "template": "select",
            "options": ["search", "virtual", "search_threshold", "virtual_threshold", "max_visible_tags", "max_selected", "hide_selected", "placeholder", "select_all_label", "invert_label", "clear_label", "css_class"],
        },
        "behavior": {"search": "capability", "virtual": "capability", "canonical_state": "native select"},
        "semantic_dom": [".dv-selector", ".dv-select", ".dv-select-panel", ".dv-choice-option"],
        "tokens": ["--dv-accent", "--dv-green", "--dv-ink", "--dv-line", "--dv-panel"],
    },
    "selector.segmented": {
        "category": "selector",
        "purpose": "Keep a very small single-select visible for immediate comparison",
        "use_when": "At most four peer choices, including boolean All/Yes/No selection",
        "logic": {"types": ["single_select", "boolean"], "fields": ["choices"]},
        "presentation": {"template": "segmented", "options": ["variant", "all_label", "show_unavailable", "css_class"]},
        "semantic_dom": [".dv-selector", ".dv-segmented", ".dv-segmented__option"],
        "tokens": ["--dv-accent", "--dv-green", "--dv-ink", "--dv-line", "--dv-panel"],
    },
    "selector.checkbox-group": {
        "category": "selector",
        "purpose": "Keep a small multi-select visible with explicit select-all and subset states",
        "use_when": "At most eight short peer choices",
        "logic": {"type": "multi_select", "fields": ["choices"]},
        "presentation": {"template": "checkbox-group", "options": ["variant", "select_all_label", "invert_label", "max_selected", "show_unavailable", "css_class"]},
        "semantic_dom": [".dv-selector", ".dv-checkbox-group", ".dv-checkbox-option"],
        "tokens": ["--dv-accent", "--dv-green", "--dv-ink", "--dv-line", "--dv-panel"],
    },
    "selector.cascader": {
        "category": "selector",
        "purpose": "Select full paths from associated hierarchical data such as province/city/district",
        "use_when": "Leaf labels need parent context or the value is a multi-stage classification",
        "logic": {
            "type": "multi_select",
            "fields": ["path_fields"],
            "value_shape": [["level-1", "level-2", "leaf"]],
            "empty_selection": "all paths",
        },
        "presentation": {
            "template": "cascader",
            "options": ["level_labels", "placeholder", "search_placeholder", "path_separator", "empty_text", "hierarchy_selection", "checked_strategy", "max_visible_tags", "css_class"],
        },
        "behavior": {
            "overlay": "viewport-aware",
            "placement": "bottom-or-top",
            "safe_area": "12px",
            "reposition_on": ["scroll", "resize", "path-change"],
            "navigation_state": "independent from selected paths",
            "multi_branch_selection": True,
        },
        "semantic_dom": [
            ".dv-selector", ".dv-cascader", ".dv-cascader-panel", ".dv-cascader-columns",
            ".dv-cascader-column", ".dv-cascader-option", ".dv-cascader-results",
        ],
        "tokens": ["--dv-accent", "--dv-green", "--dv-ink", "--dv-line", "--dv-panel"],
        "example": {
            "dashboard.yaml": {
                "id": "district",
                "type": "multi_select",
                "path_fields": ["province", "city", "district"],
                "default": [],
            },
            "presentation.yaml": {
                "selectors": {
                    "view:detail/district": {
                        "template": "cascader",
                        "level_labels": ["省份", "城市", "区县"],
                        "search_placeholder": "搜索省 / 市 / 区县…",
                        "css_class": "location-cascader",
                    }
                }
            },
        },
    },
    "selector.date-range": {
        "category": "selector",
        "purpose": "Choose an inclusive start and end date with two reviewable native date controls",
        "use_when": "A query parameter or browser Selection uses type: date_range",
        "logic": {"type": "date_range", "value_shape": ["start", "end"]},
        "presentation": {
            "template": "date-range",
            "options": ["start_label", "end_label", "min", "max", "allow_open_range", "presets", "clear_label", "css_class"],
        },
        "semantic_dom": [".dv-date-range", ".dv-date-range__field"],
        "tokens": ["--dv-accent", "--dv-ink", "--dv-line", "--dv-panel"],
    },
    "selector.tree-select": {
        "category": "selector",
        "purpose": "Search, expand and select hierarchy leaves in one narrow tree overlay",
        "use_when": "Parent context matters and a multi-column Cascader would be too wide",
        "logic": {
            "type": "multi_select",
            "fields": ["path_fields"],
            "value_shape": [["level-1", "level-2", "leaf"]],
        },
        "presentation": {
            "template": "tree-select",
            "options": ["level_labels", "placeholder", "search_placeholder", "path_separator", "default_expand_depth", "hierarchy_selection", "checked_strategy", "max_visible_tags", "css_class"],
        },
        "semantic_dom": [".dv-tree-select", ".dv-tree-panel", ".dv-tree-list", ".dv-tree-option"],
        "tokens": ["--dv-accent", "--dv-green", "--dv-ink", "--dv-line", "--dv-panel"],
    },
    "view.table": {
        "category": "view",
        "purpose": "Themeable, readable detail table",
        "logic": {"template": "table", "fields": ["input"], "optional": ["columns", "limit"]},
        "presentation": {"options": ["container", "span", "min_height", "css_class"]},
        "behavior": {"wheel_boundary": "Scroll the table only while it can consume vertical movement; otherwise continue scrolling the page"},
        "semantic_dom": [".dv-view--table", ".dv-table-meta", ".dv-table-wrap", ".dv-table"],
        "tokens": ["--dv-ink", "--dv-line", "--dv-panel", "--dv-paper"],
    },
    "view.echarts-category": {
        "category": "view",
        "purpose": "Render categorical bar or line charts with explicit legend semantics",
        "use_when": "A bar or line View uses engine: echarts and one or more series",
        "logic": {
            "templates": ["bar", "stacked-bar", "line"],
            "fields": ["input", "x", "y"],
            "optional": ["series", "aggregate"],
        },
        "presentation": {
            "engine": "echarts",
            "options": ["legend_interaction", "legend", "color"],
        },
        "behavior": {
            "legend_interaction": {
                "filter": "Hide the series and remove categories that no visible series uses (default)",
                "visibility": "Use native ECharts series visibility and keep the category axis",
                "none": "Render a non-interactive legend",
            }
        },
        "semantic_dom": [".dv-view", ".dv-chart", ".dv-echarts"],
        "tokens": ["--dv-ink", "--dv-line", "--dv-panel", "--dv-paper"],
        "example": {
            "dashboard.yaml": {
                "id": "district-bars",
                "template": "bar",
                "engine": "echarts",
                "input": "cities",
                "x": "district",
                "y": "value",
                "series": "city",
            },
            "presentation.yaml": {
                "views": {
                    "district-bars": {
                        "options": {"legend_interaction": "filter"}
                    }
                }
            },
        },
    },
    "view.perspective": {
        "category": "view",
        "purpose": "Interactive sorting, filtering, pivoting and chart exploration",
        "logic": {"template": "perspective", "fields": ["input"], "optional": ["columns", "config"]},
        "presentation": {"options": ["container", "span", "min_height", "css_class"]},
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
            "fields": ["selections", "views", "repeat.by", "repeat.selection"],
            "selector_templates": ["select", "cascader", "tree-select"],
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
        "purpose": "Expose stable typed results from a Source or Server Transform",
        "use_when": "Several Views reuse different tables, scalars, text, or objects from one computation",
        "logic": {
            "reference": "transform:<node-id>/<output-name>",
            "kinds": ["table", "scalar", "object", "text", "html", "chart", "image", "file"],
            "optional": ["schema", "format", "mime_type", "description", "required"],
        },
        "behavior": {
            "implicit": "A node without outputs has exactly source:<id>/main or transform:<id>/main",
            "validation": "Declared names, kinds, required outputs, and table schemas are enforced",
        },
        "example": {
            "outputs": {
                "trend": {"kind": "table", "schema": [{"name": "date"}, {"name": "revenue", "dtype": "float64"}]},
                "total": {"kind": "scalar"},
            }
        },
    },
    "transform.server-python": {
        "category": "transform",
        "purpose": "Run reviewable complex Python against explicit upstream Named Outputs",
        "logic": {
            "kind": "server_transform",
            "runtime": "python",
            "fields": ["id", "code", "inputs", "outputs"],
            "optional": ["entrypoint", "params", "input_schemas", "code_dependencies", "python_dependencies", "timeout_seconds", "cache"],
        },
        "behavior": {
            "isolation": "Fresh spawned process per execution",
            "timeout": "Hard termination when timeout_seconds is exceeded",
            "failure": "Node-local traceback plus execution-log Artifact",
            "cache": "Code, dependencies, packages, parameters, Adapter, and upstream hashes",
        },
    },
    "transform.browser-js": {
        "category": "transform",
        "purpose": "Derive browser-only Named Outputs without DOM access or a new query",
        "logic": {
            "kind": "browser_transform",
            "fields": ["id", "code", "inputs", "outputs"],
            "optional": ["entrypoint", "params", "selections", "timeout_seconds"],
        },
        "behavior": {
            "contract": "Pure serializable sync/async function returning a Named Output object",
            "invalidation": "Only declared Selection dependencies and downstream Views update",
            "execution": "Dedicated Web Worker with cancellation and a hard timeout",
            "registration": "window.datavizRuntime.registerTransform(spec, {code, entrypoint})",
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
        },
    },
}


COMPONENT_REGISTRY_VERSION = "3.0.0"
RUNTIME_PROTOCOL_SCHEMA = "dataviz/runtime/v1"


def _generated_component_templates() -> dict[str, dict[str, Any]]:
    """Create discoverable contracts for every strict DSL template.

    Specialized contracts in ``COMPONENT_TEMPLATES`` override these defaults.
    This keeps the CLI Registry complete when a new schema template is added.
    """
    generated: dict[str, dict[str, Any]] = {}
    for name, definition in VIEW_TEMPLATES.items():
        generated[f"view.{name}"] = {
            "category": "view",
            "purpose": definition["purpose"],
            "logic": {
                "template": name,
                "fields": definition.get("fields", []),
                "optional": definition.get("optional", []),
            },
            "presentation": {
                "options": [
                    "span",
                    "min_height",
                    "container",
                    "css_class",
                    "engine",
                    "options",
                    "config",
                ]
            },
            "behavior": {
                "input": "Consumes one or more canonical Named Outputs",
                "lifecycle": ["validate", "mount", "update", "dispose"],
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
                "optional": ["title", "description", "selections", "columns", "repeat"],
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
            "tokens": ["--dv-accent", "--dv-paper", "--dv-panel", "--dv-ink"],
        }
    generated.update(COMPONENT_TEMPLATES)
    return generated


def component_catalog(category: str | None = None) -> dict[str, dict[str, Any]]:
    packages = component_index()
    definitions = _generated_component_templates()
    for name, packaged in packages.items():
        definitions.setdefault(
            name,
            {
                "category": packaged["package"]["category"],
                "purpose": packaged["purpose"],
            },
        )
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
            "implementation": package_metadata["runtime"] if package_metadata else {},
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
            "schema": "dataviz/presentation/v1",
            "optional": True,
            "id_scopes": ["sections", "views"],
            "visual_fields": ["theme", "layout", "sections", "views", "assets", "canvas"],
            "protected_logic": ["adapters", "query_parameters", "sources", "server_transforms", "browser_transforms", "selections", "views"],
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
