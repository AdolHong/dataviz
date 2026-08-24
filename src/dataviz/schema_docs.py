from __future__ import annotations

from collections import OrderedDict
from typing import Any

from pydantic import BaseModel, TypeAdapter

from dataviz import __version__
from dataviz.adapter_contracts import ADAPTER_CONTRACTS
from dataviz.errors import ValidationFailure
from dataviz.view_contracts import VIEW_TEMPLATE_CONTRACTS
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
    SOURCE_DEFINITION_ADAPTER,
    ThemeDefinition,
    WorkspaceDefinition,
)


SCHEMA_CATALOG_VERSION = "dataviz/schema-catalog/v2"
SchemaProvider = type[BaseModel] | TypeAdapter


SCHEMA_MODELS: OrderedDict[str, SchemaProvider] = OrderedDict(
    [
        ("workspace", WorkspaceDefinition),
        ("runtime", RuntimeDefinition),
        ("dashboard", DashboardDefinition),
        ("presentation", PresentationDefinition),
        ("source", SOURCE_DEFINITION_ADAPTER),
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


def _provider_schema(provider: SchemaProvider) -> dict[str, Any]:
    if isinstance(provider, TypeAdapter):
        return provider.json_schema(by_alias=True, mode="validation")
    return provider.model_json_schema(by_alias=True, mode="validation")


def _provider_name(provider: SchemaProvider, fallback: str) -> str:
    return "SourceDefinition" if isinstance(provider, TypeAdapter) else provider.__name__


def _variant_schemas(generated: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = generated.get("$defs", {})
    result: list[dict[str, Any]] = []
    for item in generated.get("oneOf", []):
        reference = item.get("$ref") if isinstance(item, dict) else None
        if not reference or not reference.startswith("#/$defs/"):
            continue
        definition = definitions.get(reference.rsplit("/", 1)[-1])
        if isinstance(definition, dict):
            result.append(definition)
    return result


def _variant_contracts(generated: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for definition in _variant_schemas(generated):
        properties = definition.get("properties", {})
        required = set(definition.get("required", []))
        discriminator = properties.get("type", {}).get("const")
        result.append(
            {
                "type": discriminator,
                "model": definition.get("title", discriminator or "variant"),
                "fields": [
                    _field_contract(field, value, required)
                    for field, value in properties.items()
                ],
            }
        )
    return result


def _merged_fields(generated: dict[str, Any]) -> list[dict[str, Any]]:
    properties = generated.get("properties", {})
    if properties:
        required = set(generated.get("required", []))
        return [
            _field_contract(field, definition, required)
            for field, definition in properties.items()
        ]
    variants = _variant_contracts(generated)
    if not variants:
        return []
    names = list(
        dict.fromkeys(
            field["name"]
            for variant in variants
            for field in variant["fields"]
        )
    )
    merged: list[dict[str, Any]] = []
    for name in names:
        occurrences = [
            (variant["type"], field)
            for variant in variants
            for field in variant["fields"]
            if field["name"] == name
        ]
        value = dict(occurrences[0][1])
        required_in = [
            variant for variant, field in occurrences if field["required"]
        ]
        value["required"] = len(occurrences) == len(variants) and all(
            field["required"] for _, field in occurrences
        )
        value["required_in"] = required_in
        value["type"] = " | ".join(
            dict.fromkeys(
                part.strip()
                for _, field in occurrences
                for part in field["type"].split(" | ")
            )
        )
        value["variants"] = [variant for variant, _ in occurrences]
        merged.append(value)
    return merged


def schema_model_contract(name: str, *, full: bool = False) -> dict[str, Any]:
    normalized = name.strip().lower().replace("_", "-")
    model = SCHEMA_MODELS.get(normalized)
    if model is None:
        raise ValidationFailure(
            f"Unknown schema model: {name}", details={"available": list(SCHEMA_MODELS)}
        )
    generated = _provider_schema(model)
    variants = _variant_contracts(generated)
    schema_properties = [
        definition.get("properties", {}).get("schema", {})
        for definition in ([generated] if not variants else _variant_schemas(generated))
    ]
    contract_values = list(
        dict.fromkeys(
            value
            for definition in schema_properties
            if (value := definition.get("const", definition.get("default")))
        )
    )
    result = {
        "name": normalized,
        "model": _provider_name(model, normalized),
        "contract_schema": contract_values[0] if len(contract_values) == 1 else None,
        "fields": _merged_fields(generated),
    }
    if normalized == "view":
        result["template_contracts"] = VIEW_TEMPLATE_CONTRACTS
        if full:
            generated["x-dataviz-template-contracts"] = VIEW_TEMPLATE_CONTRACTS
    if normalized == "adapter":
        result["adapter_contracts"] = ADAPTER_CONTRACTS
        if full:
            generated["x-dataviz-adapter-contracts"] = ADAPTER_CONTRACTS
    if variants:
        result["discriminator"] = generated.get("discriminator", {}).get(
            "propertyName"
        )
        result["variants"] = variants
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
