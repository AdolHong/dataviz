from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


# One source of truth for the declarative View DSL. Runtime implementation
# metadata belongs to Component Packages; this table owns only author-facing
# logic fields and the requirements enforced by Pydantic.
VIEW_TEMPLATE_CONTRACTS: dict[str, dict[str, Any]] = {
    "metric": {
        "purpose": "Single scalar or aggregated table KPI",
        "required": ["input"],
        "optional": [
            "value", "aggregate", "label", "unit", "secondary", "sort", "limit",
            "options",
        ],
        "aggregate": ["sum", "mean", "min", "max", "count"],
        "field_references": ["value", "sort"],
    },
    "line": {
        "purpose": "Trend or ordered series",
        "required": ["input", "x", "y"],
        "optional": ["series", "aggregate", "sort", "limit", "options", "config"],
        "field_references": ["x", "y", "series", "sort"],
    },
    "bar": {
        "purpose": "Category comparison",
        "required": ["input", "x", "y"],
        "optional": ["series", "aggregate", "sort", "limit", "options", "config"],
        "field_references": ["x", "y", "series", "sort"],
    },
    "stacked-bar": {
        "purpose": "Part-to-whole category comparison",
        "required": ["input", "x", "y", "series"],
        "optional": ["aggregate", "sort", "limit", "options", "config"],
        "field_references": ["x", "y", "series", "sort"],
    },
    "pie": {
        "purpose": "Compact part-to-whole view",
        "required": ["input", "label", "value"],
        "optional": ["aggregate", "sort", "limit", "options", "config"],
        "field_references": ["label", "value", "sort"],
    },
    "scatter": {
        "purpose": "Relationship between measures",
        "required": ["input", "x", "y"],
        "optional": [
            "series", "color", "size", "aggregate", "sort", "limit",
            "options", "config",
        ],
        "field_references": ["x", "y", "series", "color", "size", "sort"],
    },
    "heatmap": {
        "purpose": "Two-dimensional intensity matrix",
        "required": ["input", "x", "y", "z"],
        "optional": ["aggregate", "sort", "limit", "options", "config"],
        "field_references": ["x", "y", "z", "sort"],
    },
    "radar": {
        "purpose": "Compare multiple measures across entities",
        "required": ["input", "label", "columns"],
        "optional": ["sort", "limit", "options", "config"],
        "field_references": ["label", "columns", "sort"],
    },
    "map": {
        "purpose": "Analyze point locations or values joined to GeoJSON regions",
        "required": [],
        "optional": [
            "longitude", "latitude", "geojson", "data_key", "feature_key",
            "label", "color", "size", "sort", "limit", "options", "config",
            "input", "mark", "layers",
        ],
        "one_of": [["input", "layers"]],
        "field_references": [
            "longitude", "latitude", "data_key", "label", "color", "size", "sort",
        ],
    },
    "table": {
        "purpose": "TanStack-powered default data expression table",
        "required": ["input"],
        "optional": ["columns", "sort", "limit", "options"],
        "field_references": ["columns", "sort"],
    },
    "perspective": {
        "purpose": "End-user grouping, aggregation, pivoting and multidimensional exploration",
        "required": ["input"],
        "optional": ["columns", "sort", "limit", "config"],
        "field_references": ["columns", "sort"],
    },
    "markdown": {
        "purpose": "Narrative text or text Named Output",
        "required": [],
        "optional": ["input", "text"],
        "one_of": [["input", "text"]],
    },
    "image": {
        "purpose": "Image or generated visual",
        "required": ["url"],
        "optional": [],
    },
    "custom": {
        "purpose": "Trusted extension rendered by a registered lifecycle",
        "required": ["input", "renderer"],
        "optional": ["inputs", "sort", "limit", "options", "config"],
        "field_references": ["sort"],
    },
}


VIEW_COMMON_FIELDS = {
    "id",
    "title",
    "description",
    "span",
    "template",
    "controls",
    "control_inputs",
    "control_binding",
}


PLOTLY_VIEW_TEMPLATES = {
    "line", "bar", "stacked-bar", "pie", "scatter", "heatmap", "radar", "map",
}
_PLOTLY_PARAMETER_TOKEN = re.compile(
    r"^{{\s*parameters\.([A-Za-z_][A-Za-z0-9_.-]*)\s*}}$"
)


@dataclass(frozen=True, slots=True)
class PlotlyLayoutParameterBinding:
    path: str
    parameter: str | None
    error: str | None = None


def plotly_layout_parameter_bindings(
    view: Any,
) -> tuple[PlotlyLayoutParameterBinding, ...]:
    """Inspect exact typed Query Parameter bindings inside Plotly layout values."""
    if view.template not in PLOTLY_VIEW_TEMPLATES:
        return ()
    layout = view.options.get("layout") if isinstance(view.options, dict) else None
    if not isinstance(layout, dict):
        return ()
    bindings: list[PlotlyLayoutParameterBinding] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}")
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
            return
        if not isinstance(value, str) or ("{{" not in value and "}}" not in value):
            return
        match = _PLOTLY_PARAMETER_TOKEN.fullmatch(value)
        if match:
            bindings.append(PlotlyLayoutParameterBinding(path, match.group(1)))
            return
        bindings.append(
            PlotlyLayoutParameterBinding(
                path,
                None,
                "Plotly layout interpolation must be one complete "
                "{{ parameters.<id> }} value; expressions, Control references, "
                "and surrounding text are not supported",
            )
        )

    visit(layout, f"views.{view.id}.options.layout")
    return tuple(bindings)


def resolve_plotly_layout_parameters(
    value: Any,
    parameter_values: dict[str, Any],
    *,
    path: str = "options.layout",
) -> Any:
    """Replace exact layout tokens with committed typed Query Parameter values."""
    if isinstance(value, dict):
        return {
            key: resolve_plotly_layout_parameters(
                child,
                parameter_values,
                path=f"{path}.{key}",
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            resolve_plotly_layout_parameters(
                child,
                parameter_values,
                path=f"{path}[{index}]",
            )
            for index, child in enumerate(value)
        ]
    if not isinstance(value, str) or ("{{" not in value and "}}" not in value):
        return value
    match = _PLOTLY_PARAMETER_TOKEN.fullmatch(value)
    if not match:
        raise ValueError(
            f"{path} contains an unresolved Plotly layout template; "
            "use one complete {{ parameters.<id> }} value"
        )
    parameter = match.group(1)
    if parameter not in parameter_values:
        raise ValueError(f"{path} references unknown Query Parameter {parameter}")
    return parameter_values[parameter]


def _is_missing(value: Any) -> bool:
    if value is None or value == "":
        return True
    return isinstance(value, (list, dict)) and not value


def validate_view_contract(view: Any) -> Any:
    """Reject fields that the selected Renderer path would silently ignore."""
    contract = VIEW_TEMPLATE_CONTRACTS[view.template]
    allowed = VIEW_COMMON_FIELDS | set(contract["required"]) | set(contract["optional"])
    unknown = sorted(set(view.model_fields_set) - allowed)
    if unknown:
        raise ValueError(
            f"View template {view.template} does not use fields: {', '.join(unknown)}"
        )
    missing = [
        field
        for field in contract["required"]
        if _is_missing(getattr(view, field, None))
    ]
    if missing:
        raise ValueError(
            f"View template {view.template} requires: {', '.join(missing)}"
        )
    for group in contract.get("one_of", []):
        if not any(not _is_missing(getattr(view, field, None)) for field in group):
            raise ValueError(
                f"View template {view.template} requires one of: {', '.join(group)}"
            )
    allowed_aggregates = contract.get("aggregate")
    if view.aggregate is not None and allowed_aggregates is not None:
        if view.aggregate not in allowed_aggregates:
            raise ValueError(
                f"View template {view.template} does not support "
                f"aggregate={view.aggregate}"
            )
    if view.template == "map":
        if view.layers and any(
            not _is_missing(getattr(view, field, None))
            for field in (
                "input", "inputs", "mark", "longitude", "latitude", "geojson",
                "data_key", "feature_key", "label", "color", "size", "control_binding",
            )
        ):
            raise ValueError(
                "View template map layers cannot be combined with single-mark fields "
                "or View-level control_binding"
            )
        if view.layers:
            identifiers = [layer.id for layer in view.layers]
            if len(set(identifiers)) != len(identifiers):
                raise ValueError("View template map requires unique layer ids")
            for layer in view.layers:
                required_by_mark = {
                    "point": ("longitude", "latitude"),
                    "region": ("geojson", "data_key", "feature_key", "color"),
                }
                missing = [
                    field
                    for field in required_by_mark[layer.mark]
                    if _is_missing(getattr(layer, field, None))
                ]
                if missing:
                    raise ValueError(
                        f"View template map layer={layer.id} mark={layer.mark} requires: "
                        + ", ".join(missing)
                    )
            return view
        required_by_mark = {
            "point": ("longitude", "latitude"),
            "region": ("geojson", "data_key", "feature_key", "color"),
        }
        missing = [
            field
            for field in required_by_mark[view.mark]
            if _is_missing(getattr(view, field, None))
        ]
        if missing:
            raise ValueError(
                f"View template map mark={view.mark} requires: {', '.join(missing)}"
            )
    return view


def referenced_view_fields(view: Any, input_alias: str | None = None) -> set[str]:
    """Return statically declared table columns consumed by one View template."""
    if view.template == "map" and view.layers:
        layers = [
            layer for layer in view.layers
            if input_alias is None or layer.id == input_alias
        ]
        return {
            value
            for layer in layers
            for value in (
                layer.longitude,
                layer.latitude,
                layer.data_key,
                layer.label,
                layer.color,
                layer.size,
            )
            if isinstance(value, str) and value
        }
    fields: set[str] = set()
    for property_name in VIEW_TEMPLATE_CONTRACTS[view.template].get(
        "field_references", []
    ):
        value = getattr(view, property_name, None)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, str) or not item:
                continue
            fields.add(item[1:] if property_name == "sort" and item.startswith("-") else item)
    if view.template == "metric" and view.secondary is not None:
        fields.add(view.secondary.value)
    return fields
