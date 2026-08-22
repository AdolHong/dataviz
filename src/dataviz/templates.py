from __future__ import annotations

from typing import Any


VIEW_TEMPLATES: dict[str, dict[str, Any]] = {
    "metric": {"purpose": "Single aggregated KPI", "fields": ["source", "value"], "optional": ["aggregate", "label"]},
    "line": {"purpose": "Trend or ordered series", "fields": ["source", "x", "y"], "optional": ["series", "aggregate", "engine"]},
    "bar": {"purpose": "Category comparison", "fields": ["source", "x", "y"], "optional": ["series", "aggregate", "engine"]},
    "stacked-bar": {"purpose": "Part-to-whole category comparison", "fields": ["source", "x", "y", "series"], "optional": ["aggregate", "engine"]},
    "pie": {"purpose": "Compact part-to-whole view", "fields": ["source", "label", "value"], "optional": ["aggregate", "engine"]},
    "scatter": {"purpose": "Relationship between measures", "fields": ["source", "x", "y"], "optional": ["series", "color", "size", "engine"]},
    "heatmap": {"purpose": "Two-dimensional intensity matrix", "fields": ["source", "x", "y", "z"], "optional": ["aggregate", "engine"]},
    "table": {"purpose": "Themeable presentation table", "fields": ["source"], "optional": ["columns", "limit", "options"]},
    "perspective": {"purpose": "Interactive table, sorting, filtering and pivoting", "fields": ["source"], "optional": ["columns", "config"]},
    "markdown": {"purpose": "Narrative text", "fields": ["text"], "optional": []},
    "image": {"purpose": "Image or generated visual", "fields": ["url"], "optional": ["title"]},
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
    "selector.chips": {
        "category": "selector",
        "purpose": "Expose a small multi-select set for immediate comparison",
        "use_when": "At most eight short, peer options",
        "logic": {"type": "multi_select", "fields": ["field", "choices"]},
        "presentation": {"template": "chips", "options": ["show_unavailable", "class"]},
        "semantic_dom": [".dv-selector", ".dv-choice-control", ".dv-choice-chip"],
        "tokens": ["--dv-accent", "--dv-green", "--dv-ink", "--dv-line", "--dv-panel"],
    },
    "selector.dropdown": {
        "category": "selector",
        "purpose": "Keep a short selection compact until the user opens it",
        "use_when": "A compact single-select or short multi-select",
        "logic": {"types": ["single_select", "multi_select"], "fields": ["choices"]},
        "presentation": {"template": "dropdown", "options": ["placeholder", "class"]},
        "semantic_dom": [".dv-selector", ".dv-choice-picker", ".dv-choice-panel", ".dv-choice-option"],
        "tokens": ["--dv-accent", "--dv-green", "--dv-ink", "--dv-line", "--dv-panel"],
    },
    "selector.searchable": {
        "category": "selector",
        "purpose": "Search and select from a long flat option list",
        "use_when": "More than eight multi-select or twenty single-select choices",
        "logic": {"types": ["single_select", "multi_select"], "fields": ["choices"]},
        "presentation": {"template": "searchable", "options": ["search_placeholder", "empty_text", "class"]},
        "semantic_dom": [".dv-selector", ".dv-choice-search", ".dv-choice-options", ".dv-choice-option"],
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
            "options": ["level_labels", "placeholder", "search_placeholder", "path_separator", "empty_text", "class"],
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
                        "class": "location-cascader",
                    }
                }
            },
        },
    },
    "view.table": {
        "category": "view",
        "purpose": "Themeable, readable detail table",
        "logic": {"template": "table", "fields": ["source"], "optional": ["columns", "limit"]},
        "presentation": {"options": ["container", "width", "height", "class"]},
        "behavior": {"wheel_boundary": "Scroll the table only while it can consume vertical movement; otherwise continue scrolling the page"},
        "semantic_dom": [".dv-widget--table", ".dv-table-meta", ".dv-table-wrap", ".dv-table"],
        "tokens": ["--dv-ink", "--dv-line", "--dv-panel", "--dv-paper"],
    },
    "view.echarts-category": {
        "category": "view",
        "purpose": "Render categorical bar or line charts with explicit legend semantics",
        "use_when": "A bar or line View uses engine: echarts and one or more series",
        "logic": {
            "templates": ["bar", "stacked-bar", "line"],
            "fields": ["source", "x", "y"],
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
        "semantic_dom": [".dv-widget", ".dv-chart", ".dv-echarts"],
        "tokens": ["--dv-ink", "--dv-line", "--dv-panel", "--dv-paper"],
        "example": {
            "dashboard.yaml": {
                "id": "district-bars",
                "template": "bar",
                "engine": "echarts",
                "source": "cities",
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
        "logic": {"template": "perspective", "fields": ["source"], "optional": ["columns", "config"]},
        "presentation": {"options": ["container", "width", "height", "class"]},
        "behavior": {"wheel_boundary": "Shadow-DOM scrolling yields to the page for short data and at the top or bottom boundary"},
        "semantic_dom": [".dv-widget--perspective", ".dv-perspective", ".dv-perspective-loading"],
        "tokens": ["--dv-ink", "--dv-line", "--dv-panel", "--dv-paper"],
    },
    "section.small-multiples": {
        "category": "section",
        "purpose": "Inspect every entity through one repeated View blueprint",
        "use_when": "The same chart should be shown for every store, product, region or model",
        "logic": {
            "template": "small-multiples",
            "fields": ["views", "repeat.by"],
            "repeat": ["view", "source", "by", "title", "limit", "order_by", "order", "render"],
        },
        "behavior": {
            "dataset": "One shared browser dataset, indexed into groups without copying Source nodes",
            "render": "Lazy by default with IntersectionObserver",
            "identity": "view:<blueprint>@<group-key>",
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
            "selector_templates": ["searchable", "cascader"],
        },
        "behavior": {
            "empty_selection": "Show the configured empty state instead of rendering every group",
            "export": "Keep every source row available and use the exported selection as initial state",
            "redraw": "Create or remove only this Section's repeated instances",
        },
        "semantic_dom": [".dv-section--selection-gallery", ".dv-repeat", ".dv-repeat-empty", ".dv-repeat-card"],
        "tokens": ["--dv-repeat-columns", "--dv-repeat-min-height", "--dv-gap", "--dv-panel", "--dv-line"],
    },
}


def component_catalog(category: str | None = None) -> dict[str, dict[str, Any]]:
    return {
        name: definition
        for name, definition in COMPONENT_TEMPLATES.items()
        if category is None or definition.get("category") == category
    }


def template_catalog() -> dict[str, Any]:
    return {
        "views": VIEW_TEMPLATES,
        "sections": SECTION_TEMPLATES,
        "layouts": LAYOUT_TEMPLATES,
        "themes": THEME_PRESETS,
        "components": COMPONENT_TEMPLATES,
        "presentation": {
            "schema": "dataviz/presentation/v1",
            "optional": True,
            "id_scopes": ["sections", "views"],
            "visual_fields": ["theme", "layout", "sections", "views", "assets", "canvas"],
            "protected_logic": ["adapters", "query_parameters", "sources", "selections", "aggregates"],
        },
        "selection_operators": ["auto", "equals", "in", "between", "contains", "gte", "lte", "gt", "lt"],
        "selection_modes": ["include", "exclude"],
        "extension_path": [
            "declarative",
            "template-options",
            "theme-tokens",
            "custom-view-renderer",
            "custom-canvas",
        ],
    }
