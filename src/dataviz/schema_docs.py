from __future__ import annotations

from collections import OrderedDict
from typing import Any

from pydantic import BaseModel

from dataviz import __version__
from dataviz.errors import ValidationFailure
from dataviz.workspace.models import (
    AdapterDefinition,
    CacheDefinition,
    ComputeParameterDefinition,
    DashboardDefinition,
    DatasetTransformDefinition,
    DeclarativeViewDefinition,
    LayoutDefinition,
    OutputDefinition,
    InteractiveExportDefinition,
    InteractiveTransformDefinition,
    PresentationDefinition,
    PresentationSelectorDefinition,
    QueryParameterDefinition,
    RepeatDefinition,
    RuntimeDefinition,
    SectionDefinition,
    SelectionDefinition,
    SourceDefinition,
    ThemeDefinition,
    WorkspaceDefinition,
)


SCHEMA_CATALOG_VERSION = "dataviz/schema-catalog/v2"
SCHEMA_MODELS: OrderedDict[str, type[BaseModel]] = OrderedDict(
    [
        ("workspace", WorkspaceDefinition),
        ("runtime", RuntimeDefinition),
        ("dashboard", DashboardDefinition),
        ("presentation", PresentationDefinition),
        ("source", SourceDefinition),
        ("dataset-transform", DatasetTransformDefinition),
        ("interactive-transform", InteractiveTransformDefinition),
        ("interactive-export", InteractiveExportDefinition),
        ("adapter", AdapterDefinition),
        ("query-parameter", QueryParameterDefinition),
        ("compute-parameter", ComputeParameterDefinition),
        ("selection", SelectionDefinition),
        ("section", SectionDefinition),
        ("repeat", RepeatDefinition),
        ("view", DeclarativeViewDefinition),
        ("output", OutputDefinition),
        ("cache", CacheDefinition),
        ("layout", LayoutDefinition),
        ("theme", ThemeDefinition),
        ("selector-presentation", PresentationSelectorDefinition),
    ]
)


CURRENT_SCHEMAS = {
    "workspace": "dataviz/workspace/v1",
    "dashboard": "dataviz/dashboard/v2",
    "presentation": "dataviz/presentation/v1",
    "source": "dataviz/source/v1",
    "dataset_transform": "dataviz/dataset-transform/v1",
    "interactive_transform": "dataviz/interactive-transform/v1",
    "runtime": "dataviz/runtime/v2",
}


def _type_name(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return repr(schema["const"])
    if "enum" in schema:
        return " | ".join(repr(value) for value in schema["enum"])
    if "anyOf" in schema:
        values = list(dict.fromkeys(_type_name(value) for value in schema["anyOf"]))
        return " | ".join(values)
    kind = schema.get("type", "any")
    if kind == "array":
        return f"list[{_type_name(schema.get('items', {}))}]"
    if kind == "object":
        additional = schema.get("additionalProperties")
        return f"dict[str, {_type_name(additional)}]" if isinstance(additional, dict) else "object"
    return str(kind)


def _field_contract(
    name: str, definition: dict[str, Any], required: set[str]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "required": name in required,
        "type": _type_name(definition),
    }
    for key in [
        "description",
        "default",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "pattern",
    ]:
        if key in definition:
            result[key] = definition[key]
    return result


def schema_model_contract(name: str, *, full: bool = False) -> dict[str, Any]:
    normalized = name.strip().lower().replace("_", "-")
    model = SCHEMA_MODELS.get(normalized)
    if model is None:
        raise ValidationFailure(
            f"Unknown schema model: {name}", details={"available": list(SCHEMA_MODELS)}
        )
    generated = model.model_json_schema(by_alias=True, mode="validation")
    required = set(generated.get("required", []))
    schema_property = generated.get("properties", {}).get("schema", {})
    result = {
        "name": normalized,
        "model": model.__name__,
        "contract_schema": schema_property.get("const", schema_property.get("default")),
        "fields": [
            _field_contract(field, definition, required)
            for field, definition in generated.get("properties", {}).items()
        ],
    }
    if full:
        result["json_schema"] = generated
    return result


def schema_catalog(*, full: bool = False) -> dict[str, Any]:
    return {
        "schema": SCHEMA_CATALOG_VERSION,
        "dataviz_version": __version__,
        "models": {
            name: schema_model_contract(name, full=full) for name in SCHEMA_MODELS
        },
        "generation": (
            "Generated from the installed Pydantic models; use Component Registry "
            "for behavior, semantic DOM and style contracts."
        ),
    }
