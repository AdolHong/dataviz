from __future__ import annotations

from typing import Any

from dataviz.auth import AdapterResolver
from dataviz.errors import ValidationFailure
from dataviz.execution.context import ExecutionContext
from dataviz.execution.parameter_materializations import ParameterMaterializationStore
from dataviz.execution.parameters import (
    project_query_inputs,
    query_input_parameter,
    resolve_query_parameter_states,
)
from dataviz.protocols import QUERY_INSPECTION_SCHEMA
from dataviz.redaction import redact_value
from dataviz.sources import SOURCE_RUNNERS
from dataviz.sources.base import SourceRequest
from dataviz.workspace.loading.loaded_types import LoadedWorkspace


def _source_id(raw: str) -> str:
    value = raw.strip()
    if value.startswith("source:"):
        value = value.split(":", 1)[1]
    if "/" in value or not value:
        raise ValidationFailure(
            "--source must identify one Source, not one Output",
            details={"code": "query_inspection_source_invalid", "source": raw},
        )
    return value


def _parameter_projection(
    definition: Any,
    state: dict[str, Any],
    *,
    domain_dependency: dict[str, Any],
    domain_evidence: dict[str, Any] | None,
    operand_limit: int,
) -> dict[str, Any]:
    raw = state.get("value")
    operands = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
    selection = state.get("selection")
    active = (
        selection in {"include", "exclude"}
        or (selection is None and raw not in (None, "", [], ()))
        or (selection == "none" and getattr(definition, "required", False))
    )
    return {
        "id": definition.id,
        "type": definition.type,
        "value_type": definition.value_type,
        "state": state,
        "selection": selection,
        "active": active,
        "operand_count": len(operands),
        "operands": operands[:operand_limit],
        "operands_truncated": len(operands) > operand_limit,
        "domain_dependency": domain_dependency,
        "domain_evidence": domain_evidence,
    }


def inspect_query(
    loaded: LoadedWorkspace,
    dashboard_id: str,
    source: str,
    *,
    query_parameter_state: dict[str, Any] | None = None,
    operand_limit: int = 20,
) -> dict[str, Any]:
    """Explain one SQL Source without executing it or creating candidate data."""

    dashboard = loaded.dashboard(dashboard_id)
    source_id = _source_id(source)
    if source_id not in dashboard.sources:
        raise ValidationFailure(
            f"Unknown Source: {source_id}",
            details={
                "code": "query_inspection_source_unknown",
                "source": source_id,
                "available": sorted(dashboard.sources),
            },
        )
    definition_path, definition = dashboard.sources[source_id]
    if definition.type != "sql":
        raise ValidationFailure(
            f"Source {source_id} is {definition.type}; inspect query requires SQL",
            details={
                "code": "query_inspection_source_not_sql",
                "source": source_id,
                "source_type": definition.type,
            },
        )
    parameters = resolve_query_parameter_states(
        dashboard.definition.query_parameters,
        query_parameter_state,
        timezone_name=loaded.definition.context.timezone,
    )
    query_inputs = project_query_inputs(definition.query_inputs, parameters)
    adapters = AdapterResolver(loaded.root)
    context = ExecutionContext(
        workspace_root=loaded.root,
        dashboard_root=dashboard.root,
        run_id="inspect_query",
        query_parameter_state=parameters,
        query_inputs=query_inputs,
        control_inputs={},
        control_state={},
        inputs={},
        store=None,  # SQL diagnostics never materialize or read an Artifact.
    )
    request = SourceRequest(
        definition_path=definition_path,
        definition=definition,
        context=context,
        adapters=adapters,
        adapter_bindings=dashboard.definition.adapters,
        node_id=f"source:{source_id}",
        workspace_root=loaded.root,
        workspace_assets=loaded.definition.assets,
    )
    query = SOURCE_RUNNERS["sql"].diagnostics(request).get("query", {})
    secrets = adapters.redaction_values(
        definition.adapter,
        dashboard.definition.adapters,
    )
    query = redact_value(query, secrets)

    relevant = {
        query_input_parameter(binding) for binding in definition.query_inputs.values()
    }
    relevant.update(item.parameter for item in definition.query_filters.values())
    definitions = {item.id: item for item in dashboard.definition.query_parameters}
    domain_contract = dashboard.parameter_domain_contract
    materializations = (
        ParameterMaterializationStore(loaded)
        if (loaded.root / ".dataviz" / "parameter-materializations").exists()
        else None
    )
    parameter_payload = []
    for parameter_id in sorted(relevant):
        definition_item = definitions[parameter_id]
        parents = domain_contract.dependencies.get(parameter_id, ())
        domain_evidence = None
        if getattr(definition_item.options, "mode", None) == "domain" and materializations:
            domain_evidence = materializations.inspect_state(
                dashboard,
                parameter_id,
                state=parameters[parameter_id],
                parent_states={parent: parameters[parent] for parent in parents},
            )
        elif getattr(definition_item.options, "mode", None) == "domain":
            domain_evidence = {
                "status": "missing",
                "freshness": "missing",
                "candidate_count": None,
                "effective_selected_count": None,
                "unavailable_count": None,
            }
        parameter_payload.append(
            _parameter_projection(
                definition_item,
                parameters[parameter_id],
                domain_dependency={
                    "parents": list(parents),
                    "descendants": list(domain_contract.descendants.get(parameter_id, ())),
                    "source": getattr(definition_item.options, "source", None),
                },
                domain_evidence=domain_evidence,
                operand_limit=operand_limit,
            )
        )
    return {
        "schema": QUERY_INSPECTION_SCHEMA,
        "status": "ready" if not query.get("inspection_warning") else "partial",
        "executed": False,
        "workspace": loaded.definition.id,
        "dashboard": dashboard_id,
        "source": source_id,
        "query_parameter_state": parameters,
        "parameters": parameter_payload,
        "query": query,
    }


__all__ = ["inspect_query"]
