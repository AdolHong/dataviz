"""Resolve pre-query Parameter Domains without entering the analytical Query DAG."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, TYPE_CHECKING

import pandas as pd

from dataviz.auth import AdapterResolver
from dataviz.errors import ExecutionFailure, QueryTimeoutFailure, ValidationFailure
from dataviz.execution.parameters import (
    project_query_inputs,
    query_input_contract,
    query_input_parameter,
    resolve_query_parameter_intents,
    resolve_query_parameter_values,
)
from dataviz.protocols import (
    PARAMETER_DOMAIN_CONTRACT_SCHEMA,
    PARAMETER_DOMAIN_RESOLUTION_SCHEMA,
)
from dataviz.sources.sql import execute_sql_query
from dataviz.value_contract import (
    ValueContractViolation,
    is_empty_control_value,
    json_compatible_value,
    json_value_signature,
    normalize_control_value,
    select_initial_contract,
    select_initial_value,
)
from dataviz.workspace.models import ParameterDomainOptionDefinition

if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


PARAMETER_DOMAIN_CLIENT_PROJECTION_MAX_ROWS = 50_000
PARAMETER_DOMAIN_CLIENT_PROJECTION_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ParameterDomainContract:
    dependencies: dict[str, tuple[str, ...]]
    projection_dependencies: dict[str, tuple[str, ...]]
    projection_descendants: dict[str, tuple[str, ...]]
    query_domains: dict[str, tuple[str, ...]]
    order: tuple[str, ...]
    domain_consumers: dict[str, tuple[str, ...]]
    domain_inputs: dict[str, tuple[str, ...]]
    domain_input_bindings: dict[str, dict[str, dict[str, Any]]]

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "dependencies": {key: list(value) for key, value in self.dependencies.items()},
            "projection_dependencies": {
                key: list(value) for key, value in self.projection_dependencies.items()
            },
            "projection_descendants": {
                key: list(value) for key, value in self.projection_descendants.items()
            },
            "query_domains": {key: list(value) for key, value in self.query_domains.items()},
            "order": list(self.order),
            "domain_consumers": {key: list(value) for key, value in self.domain_consumers.items()},
            "domain_inputs": {key: list(value) for key, value in self.domain_inputs.items()},
            "domain_input_bindings": deepcopy(self.domain_input_bindings),
        }

    @property
    def contract_hash(self) -> str:
        encoded = json.dumps(
            self._canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_DOMAIN_CONTRACT_SCHEMA,
            "contract_hash": self.contract_hash,
            **self._canonical_payload(),
        }


def _topological_order(graph: dict[str, set[str]]) -> tuple[str, ...]:
    pending = {key: set(value) for key, value in graph.items()}
    order: list[str] = []
    while pending:
        ready = sorted(key for key, value in pending.items() if not value)
        if not ready:
            raise ValidationFailure(
                "Query Parameter Domain dependencies contain a cycle: "
                + ", ".join(sorted(pending)),
                details={
                    "code": "parameter_domain_dependency_cycle",
                    "parameters": sorted(pending),
                },
            )
        order.extend(ready)
        for key in ready:
            pending.pop(key)
        for value in pending.values():
            value.difference_update(ready)
    return tuple(order)


def _transitive_projection_descendants(
    graph: Mapping[str, set[str]],
) -> dict[str, tuple[str, ...]]:
    direct_children = {key: set() for key in graph}
    for child, parents in graph.items():
        for parent in parents:
            direct_children[parent].add(child)
    descendants: dict[str, tuple[str, ...]] = {}
    for parameter_id in graph:
        pending = list(direct_children[parameter_id])
        found: set[str] = set()
        while pending:
            child = pending.pop()
            if child in found:
                continue
            found.add(child)
            pending.extend(direct_children[child])
        descendants[parameter_id] = tuple(sorted(found))
    return descendants


def compile_parameter_domain_contract(
    dashboard: LoadedDashboard,
) -> ParameterDomainContract:
    definitions = {item.id: item for item in dashboard.definition.query_parameters}
    graph = {key: set() for key in definitions}
    projection_graph = {key: set() for key in definitions}
    domain_consumers = {key: set() for key in dashboard.parameter_domains}
    domain_inputs: dict[str, set[str]] = {}
    domain_input_bindings: dict[str, dict[str, dict[str, Any]]] = {}
    query_domains = {key: set() for key in definitions}

    for domain_id, (_, domain) in dashboard.parameter_domains.items():
        bindings = {
            alias: query_input_contract(binding) for alias, binding in domain.query_inputs.items()
        }
        inputs = {query_input_parameter(binding) for binding in domain.query_inputs.values()}
        unknown = sorted(inputs - set(definitions))
        if unknown:
            raise ValidationFailure(
                f"Parameter Domain {domain_id} references unknown Query Parameters: "
                + ", ".join(unknown),
                details={
                    "code": "parameter_domain_input_unknown",
                    "domain": domain_id,
                    "parameters": unknown,
                },
            )
        domain_inputs[domain_id] = inputs
        domain_input_bindings[domain_id] = bindings
        for parameter_id in inputs:
            query_domains[parameter_id].add(domain_id)

    for parameter_id, definition in definitions.items():
        options = definition.options
        if not isinstance(options, ParameterDomainOptionDefinition):
            continue
        if options.source not in dashboard.parameter_domains:
            raise ValidationFailure(
                f"Query Parameter {parameter_id} references unknown Parameter Domain: "
                f"{options.source}",
                details={
                    "code": "parameter_domain_unknown",
                    "parameter": parameter_id,
                    "domain": options.source,
                },
            )
        parents = set(options.depends_on)
        unknown = sorted(parents - set(definitions))
        if unknown:
            raise ValidationFailure(
                f"Query Parameter {parameter_id} references unknown parent Parameters: "
                + ", ".join(unknown),
                details={
                    "code": "parameter_domain_parent_unknown",
                    "parameter": parameter_id,
                    "parents": unknown,
                },
            )
        if parameter_id in parents:
            raise ValidationFailure(
                f"Query Parameter {parameter_id} cannot depend on itself",
                details={
                    "code": "parameter_domain_dependency_self",
                    "parameter": parameter_id,
                },
            )
        ambiguous = sorted(parents & domain_inputs[options.source])
        if ambiguous:
            raise ValidationFailure(
                f"Parameter Domain {options.source} declares the same parent as "
                "both a local projection edge and a query input: " + ", ".join(ambiguous),
                details={
                    "code": "parameter_domain_dependency_mode_conflict",
                    "domain": options.source,
                    "parameter": parameter_id,
                    "parents": ambiguous,
                },
            )
        projection_graph[parameter_id].update(parents)
        graph[parameter_id].update(parents)
        graph[parameter_id].update(domain_inputs[options.source])
        domain_consumers[options.source].add(parameter_id)

    return ParameterDomainContract(
        dependencies={key: tuple(sorted(value)) for key, value in graph.items()},
        projection_dependencies={
            key: tuple(sorted(value)) for key, value in projection_graph.items()
        },
        projection_descendants=_transitive_projection_descendants(projection_graph),
        query_domains={key: tuple(sorted(value)) for key, value in query_domains.items()},
        order=_topological_order(graph),
        domain_consumers={key: tuple(sorted(value)) for key, value in domain_consumers.items()},
        domain_inputs={key: tuple(sorted(value)) for key, value in domain_inputs.items()},
        domain_input_bindings=domain_input_bindings,
    )


@dataclass(slots=True)
class _CacheEntry:
    frame: pd.DataFrame
    created_at: float
    content_hash: str


class ParameterDomainCache:
    """One process-local cache; callers scope instances by tab/session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, key: str, *, ttl_seconds: int | None) -> _CacheEntry | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if ttl_seconds is not None and time.monotonic() - entry.created_at >= ttl_seconds:
                self._entries.pop(key, None)
                return None
            return _CacheEntry(entry.frame.copy(deep=True), entry.created_at, entry.content_hash)

    def put(self, key: str, frame: pd.DataFrame, content_hash: str) -> None:
        with self._lock:
            self._entries[key] = _CacheEntry(frame.copy(deep=True), time.monotonic(), content_hash)


@dataclass(frozen=True, slots=True)
class ParameterDomainResolution:
    values: dict[str, Any]
    choices: dict[str, list[dict[str, Any]]]
    intents: dict[str, str]
    domains: dict[str, dict[str, Any]]
    contract: ParameterDomainContract
    client_projection: dict[str, Any]
    frames: dict[str, pd.DataFrame]

    def as_dict(self) -> dict[str, Any]:
        generation_payload = {
            key: {
                "content_hash": value.get("content_hash", ""),
                "input_signature": value.get("input_signature", ""),
            }
            for key, value in self.domains.items()
        }
        generation = hashlib.sha256(
            json.dumps(generation_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return {
            "schema": PARAMETER_DOMAIN_RESOLUTION_SCHEMA,
            "status": "ready",
            "generation": f"domain_{generation}",
            "query_parameters": deepcopy(self.values),
            "choices": deepcopy(self.choices),
            "intents": dict(self.intents),
            "domains": deepcopy(self.domains),
            "contract": self.contract.as_dict(),
            "client_projection": deepcopy(self.client_projection),
        }


def _frame_hash(frame: pd.DataFrame) -> str:
    payload = frame.to_json(orient="split", date_format="iso", force_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _domain_cache_key(
    *,
    dashboard: LoadedDashboard,
    domain_id: str,
    code_path: Path,
    adapter: Mapping[str, Any],
    query_inputs: Mapping[str, Any],
) -> str:
    payload = {
        "dashboard": dashboard.definition.id,
        "domain": domain_id,
        "definition": dashboard.parameter_domains[domain_id][1].model_dump(
            mode="json", by_alias=True
        ),
        "code": hashlib.sha256(code_path.read_bytes()).hexdigest(),
        "adapter": dict(adapter),
        "query_inputs": dict(query_inputs),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _execute_domain(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
    domain_id: str,
    parameters: Mapping[str, Any],
    parameter_intents: Mapping[str, str],
    *,
    cache: ParameterDomainCache | None,
    refresh: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    definition_path, definition = dashboard.parameter_domains[domain_id]
    code_path = (definition_path.parent / definition.code).resolve()
    query = code_path.read_text(encoding="utf-8")
    query_inputs = project_query_inputs(definition.query_inputs, parameters, parameter_intents)
    input_signature = hashlib.sha256(json_value_signature(query_inputs).encode("utf-8")).hexdigest()
    adapters = AdapterResolver(workspace.root)
    adapter = adapters.runtime_config(definition.adapter, dashboard.definition.adapters)
    cache_key = _domain_cache_key(
        dashboard=dashboard,
        domain_id=domain_id,
        code_path=code_path,
        adapter=adapter,
        query_inputs=query_inputs,
    )
    ttl = definition.cache.ttl_seconds if definition.cache.mode == "ttl" else None
    cached = (
        None
        if refresh or cache is None or definition.cache.mode == "none"
        else cache.get(cache_key, ttl_seconds=ttl)
    )
    if cached is not None:
        return cached.frame, {
            "rows": len(cached.frame),
            "columns": list(cached.frame.columns),
            "content_hash": cached.content_hash,
            "input_signature": input_signature,
            "cached": True,
        }

    frame: pd.DataFrame | None = None
    max_attempts = definition.timeout_retries + 1
    for attempt in range(1, max_attempts + 1):
        domain_run_id = f"parameter_domain_{uuid.uuid4().hex[:16]}"
        domain_run_root = workspace.root / ".dataviz" / "runs" / domain_run_id
        try:
            frame = execute_sql_query(
                adapter=adapter,
                query=query,
                parameters=query_inputs,
                timeout_seconds=definition.timeout_seconds,
                workspace_root=workspace.root,
                run_id=domain_run_id,
                node_id=f"parameter-domain:{domain_id}",
                definition_path=code_path,
            )
            break
        except QueryTimeoutFailure:
            if attempt >= max_attempts:
                raise
        finally:
            if domain_run_root.exists() and not any(domain_run_root.iterdir()):
                domain_run_root.rmdir()
    assert frame is not None
    if len(frame) > definition.max_rows:
        raise ExecutionFailure(
            f"Parameter Domain {domain_id} returned {len(frame)} rows; "
            f"max_rows is {definition.max_rows}",
            file=code_path,
            details={
                "code": "parameter_domain_row_limit",
                "domain": domain_id,
                "rows": len(frame),
                "max_rows": definition.max_rows,
            },
        )
    content_hash = _frame_hash(frame)
    if cache is not None and definition.cache.mode != "none":
        cache.put(cache_key, frame, content_hash)
    return frame, {
        "rows": len(frame),
        "columns": list(frame.columns),
        "content_hash": content_hash,
        "input_signature": input_signature,
        "cached": False,
    }


def _candidate_value(definition: Any, value: Any) -> Any:
    try:
        if definition.type == "multiple_select":
            return normalize_control_value(definition, [value])[0]
        return normalize_control_value(definition, value)
    except (ValueContractViolation, ValueError) as error:
        raise ExecutionFailure(
            f"Parameter Domain value for {definition.id} violates value_type: {error}",
            details={
                "code": "parameter_domain_value_invalid",
                "parameter": definition.id,
                "reason": str(error),
            },
        ) from error


def _is_null(value: Any) -> bool:
    """Return a scalar null test without triggering pandas' array truth rules."""

    if isinstance(value, (list, tuple, set, dict)):
        return False
    result = pd.isna(value)
    return bool(result) if not hasattr(result, "__len__") else False


def _json_scalar(value: Any) -> Any:
    """Normalize pandas/numpy scalars before applying the public value contract."""

    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    elif hasattr(value, "item") and callable(value.item):
        value = value.item()
    return json_compatible_value(value)


def _projection_fields(options: ParameterDomainOptionDefinition) -> set[str]:
    return {
        options.value_field,
        *(
            field
            for field in (
                options.label_field,
                options.description_field,
                options.group_field,
                options.keywords_field,
                options.sort_field,
                options.disabled_field,
            )
            if field
        ),
        *(binding.field for binding in options.depends_on.values()),
    }


def _validated_projection_frame(
    definition: Any,
    frame: pd.DataFrame,
) -> pd.DataFrame:
    options = definition.options
    assert isinstance(options, ParameterDomainOptionDefinition)
    missing = sorted(_projection_fields(options) - set(frame.columns))
    if missing:
        raise ExecutionFailure(
            f"Parameter Domain {options.source} is missing fields: " + ", ".join(missing),
            details={
                "code": "parameter_domain_field_missing",
                "domain": options.source,
                "parameter": definition.id,
                "fields": missing,
            },
        )
    if options.sort_field:
        return frame.sort_values(options.sort_field, kind="stable")
    return frame


def _choice_from_row(definition: Any, row: Any) -> dict[str, Any] | None:
    options = definition.options
    assert isinstance(options, ParameterDomainOptionDefinition)
    raw = row[options.value_field]
    if _is_null(raw):
        return None
    value = _candidate_value(definition, _json_scalar(raw))
    label_raw = row[options.label_field] if options.label_field else value
    choice: dict[str, Any] = {
        "value": value,
        "label": str(label_raw if not _is_null(label_raw) else value),
    }
    for output_key, field in (
        ("description", options.description_field),
        ("group", options.group_field),
    ):
        if field and not _is_null(row[field]):
            choice[output_key] = str(row[field])
    if options.keywords_field and not _is_null(row[options.keywords_field]):
        raw_keywords = row[options.keywords_field]
        choice["keywords"] = (
            [str(item) for item in raw_keywords]
            if isinstance(raw_keywords, (list, tuple, set))
            else [item.strip() for item in str(raw_keywords).split(",") if item.strip()]
        )
    if options.disabled_field:
        choice["disabled"] = bool(row[options.disabled_field])
    return choice


def _project_choices(
    definition: Any,
    frame: pd.DataFrame,
    parameters: Mapping[str, Any],
) -> list[dict[str, Any]]:
    options = definition.options
    assert isinstance(options, ParameterDomainOptionDefinition)
    filtered = _validated_projection_frame(definition, frame)
    for parent, binding in options.depends_on.items():
        value = parameters.get(parent)
        values = value if isinstance(value, list) else [value]
        values = [item for item in values if not is_empty_control_value(item)]
        if not values:
            filtered = filtered.iloc[0:0]
            break
        signatures = {json_value_signature(item) for item in values}
        filtered = filtered[
            filtered[binding.field].map(
                lambda item, allowed=signatures: (
                    False if _is_null(item) else json_value_signature(_json_scalar(item)) in allowed
                )
            )
        ]
    projected: dict[str, dict[str, Any]] = {}
    for _, row in filtered.iterrows():
        choice = _choice_from_row(definition, row)
        if choice is None:
            continue
        value = choice["value"]
        signature = json_value_signature(value)
        previous = projected.get(signature)
        if previous is not None and previous != choice:
            raise ExecutionFailure(
                f"Parameter Domain {options.source} maps one value to conflicting metadata",
                details={
                    "code": "parameter_domain_metadata_conflict",
                    "domain": options.source,
                    "parameter": definition.id,
                    "value": value,
                },
            )
        projected[signature] = choice
    return list(projected.values())


def _build_client_projection(
    dashboard: LoadedDashboard,
    contract: ParameterDomainContract,
    frames: Mapping[str, pd.DataFrame],
) -> dict[str, Any]:
    """Project only browser-required relation fields from immutable Domain frames."""

    definitions = {item.id: item for item in dashboard.definition.query_parameters}
    parameters: dict[str, dict[str, Any]] = {}
    relation_rows = 0
    involved_domains: set[str] = set()
    involved_consumers: list[str] = []

    for parameter_id in contract.order:
        parents = contract.projection_dependencies.get(parameter_id, ())
        if not parents:
            continue
        definition = definitions[parameter_id]
        options = definition.options
        assert isinstance(options, ParameterDomainOptionDefinition)
        frame = _validated_projection_frame(definition, frames[options.source])
        rows: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            choice = _choice_from_row(definition, row)
            if choice is None:
                continue
            parent_signatures = {
                parent: (
                    None
                    if _is_null(row[options.depends_on[parent].field])
                    else json_value_signature(_json_scalar(row[options.depends_on[parent].field]))
                )
                for parent in parents
            }
            rows.append(
                {
                    "signature": json_value_signature(choice["value"]),
                    "choice": choice,
                    "parents": parent_signatures,
                }
            )
        parameters[parameter_id] = {
            "domain": options.source,
            "parents": list(parents),
            "rows": rows,
        }
        relation_rows += len(rows)
        involved_domains.add(options.source)
        involved_consumers.append(parameter_id)

    payload = {
        "contract_schema": PARAMETER_DOMAIN_CONTRACT_SCHEMA,
        "contract_hash": contract.contract_hash,
        "parameters": parameters,
    }
    serialized_bytes = len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    capacity = {
        "rows": relation_rows,
        "max_rows": PARAMETER_DOMAIN_CLIENT_PROJECTION_MAX_ROWS,
        "serialized_bytes": serialized_bytes,
        "max_serialized_bytes": PARAMETER_DOMAIN_CLIENT_PROJECTION_MAX_BYTES,
    }
    if (
        relation_rows > PARAMETER_DOMAIN_CLIENT_PROJECTION_MAX_ROWS
        or serialized_bytes > PARAMETER_DOMAIN_CLIENT_PROJECTION_MAX_BYTES
    ):
        raise ExecutionFailure(
            "Parameter Domain client projection exceeds its complete snapshot capacity",
            details={
                "code": "parameter_domain_client_projection_limit",
                **capacity,
                "domains": sorted(involved_domains),
                "consumers": involved_consumers,
                "suggestions": [
                    "Move the high-cardinality parent to the Domain query_inputs",
                    "Split the Parameter Domain into smaller input-specific snapshots",
                    "Use multiple_input for known high-cardinality identifiers",
                ],
            },
        )
    return {**payload, "capacity": capacity}


def _resolve_dynamic_value(
    definition: Any,
    choices: list[dict[str, Any]],
    *,
    supplied: bool,
    raw_value: Any,
    initialized: bool,
    intent: str | None,
    strict: bool,
    preserve_unavailable: bool,
) -> tuple[Any, str]:
    available = [choice["value"] for choice in choices if not choice.get("disabled")]
    signatures = {json_value_signature(value): value for value in available}

    def initial() -> tuple[Any, str]:
        value = select_initial_value(definition, available)
        resolved_intent = (
            "all_available"
            if definition.type == "multiple_select"
            and select_initial_contract(definition)["mode"] == "all"
            else "explicit"
        )
        return normalize_control_value(definition, value, enforce_required=True), resolved_intent

    if not supplied or not initialized:
        return initial()
    try:
        normalized = normalize_control_value(definition, raw_value, enforce_required=False)
    except ValueContractViolation as error:
        raise ExecutionFailure(
            f"Invalid Query Parameter {definition.id}: {error}",
            details={
                "code": "query_parameter_value_invalid",
                "id": definition.id,
                "reason": str(error),
            },
        ) from error
    if preserve_unavailable:
        # A committed Query snapshot is an execution fact, not a suggestion from
        # the latest UI Domain. Preserve its canonical value and intent exactly;
        # missing candidates are projected as unavailable choices below so the
        # browser can explain the mismatch instead of silently changing history.
        return normalize_control_value(definition, normalized, enforce_required=True), (
            "all_available"
            if definition.type == "multiple_select" and intent == "all_available"
            else "explicit"
        )
    if definition.type == "multiple_select" and intent == "all_available":
        return normalize_control_value(
            definition, available, enforce_required=True
        ), "all_available"
    if is_empty_control_value(normalized):
        if definition.required:
            if strict:
                raise ExecutionFailure(
                    f"Invalid Query Parameter {definition.id}: a value is required",
                    details={
                        "code": "query_parameter_value_required",
                        "id": definition.id,
                    },
                )
            return initial()
        return normalized, "explicit"
    items = normalized if isinstance(normalized, list) else [normalized]
    retained = [
        signatures[json_value_signature(item)]
        for item in items
        if json_value_signature(item) in signatures
    ]
    if strict and len(retained) != len(items):
        invalid = [item for item in items if json_value_signature(item) not in signatures]
        raise ExecutionFailure(
            f"Invalid Query Parameter {definition.id}: values are outside the current domain",
            details={
                "code": "query_parameter_unknown_choice",
                "id": definition.id,
                "values": invalid,
            },
        )
    if definition.type == "multiple_select":
        if items and not retained:
            return initial()
        return normalize_control_value(definition, retained, enforce_required=True), "explicit"
    if items and retained:
        return normalize_control_value(definition, retained[0], enforce_required=True), "explicit"
    return initial()


def _with_unavailable_choices(
    definition: Any,
    choices: list[dict[str, Any]],
    value: Any,
) -> list[dict[str, Any]]:
    """Expose committed values missing from the latest Domain as read-only choices."""

    selected = value if isinstance(value, list) else [value]
    known = {json_value_signature(choice["value"]) for choice in choices}
    projected = list(choices)
    for item in selected:
        if is_empty_control_value(item) or json_value_signature(item) in known:
            continue
        label = (
            json.dumps(item, ensure_ascii=False, sort_keys=True)
            if isinstance(item, (dict, list))
            else str(item)
        )
        projected.append(
            {
                "value": item,
                "label": label,
                "description": "Unavailable in the current Parameter Domain",
                "disabled": True,
                "unavailable": True,
            }
        )
    return projected


def resolve_parameter_domains(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
    values: Mapping[str, Any] | None,
    *,
    timezone_name: str,
    current_time: datetime | None = None,
    initialized_parameters: set[str] | None = None,
    intents: Mapping[str, str] | None = None,
    strict: bool = True,
    preserve_unavailable: bool = False,
    cache: ParameterDomainCache | None = None,
    refresh: bool = False,
) -> ParameterDomainResolution:
    contract = compile_parameter_domain_contract(dashboard)
    provided = dict(values or {})
    definitions = {item.id: item for item in dashboard.definition.query_parameters}
    unknown = sorted(set(provided) - set(definitions))
    if unknown:
        raise ExecutionFailure(
            "Unknown Query Parameters",
            details={"code": "query_parameter_unknown", "ids": unknown},
        )
    initialized = initialized_parameters if initialized_parameters is not None else set(provided)
    requested_intents = dict(intents or {})
    resolved: dict[str, Any] = {}
    choices: dict[str, list[dict[str, Any]]] = {}
    resolved_intents: dict[str, str] = {}
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    domain_metadata: dict[str, dict[str, Any]] = {}

    for parameter_id in contract.order:
        definition = definitions[parameter_id]
        options = definition.options
        if not isinstance(options, ParameterDomainOptionDefinition):
            value = resolve_query_parameter_values(
                [definition],
                {parameter_id: provided[parameter_id]} if parameter_id in provided else {},
                timezone_name=timezone_name,
                current_time=current_time,
            )[parameter_id]
            resolved[parameter_id] = value
            resolved_intents[parameter_id] = resolve_query_parameter_intents(
                [definition],
                {parameter_id: provided[parameter_id]} if parameter_id in provided else {},
                {parameter_id: requested_intents[parameter_id]}
                if parameter_id in requested_intents
                else {},
            )[parameter_id]
            continue
        domain_inputs = project_query_inputs(
            dashboard.parameter_domains[options.source][1].query_inputs,
            resolved,
            resolved_intents,
        )
        input_signature = json.dumps(domain_inputs, sort_keys=True, ensure_ascii=False, default=str)
        frame_key = (options.source, input_signature)
        if frame_key not in frames:
            frame, metadata = _execute_domain(
                workspace,
                dashboard,
                options.source,
                resolved,
                resolved_intents,
                cache=cache,
                refresh=refresh,
            )
            frames[frame_key] = frame
            domain_metadata[options.source] = metadata
        parameter_choices = _project_choices(definition, frames[frame_key], resolved)
        choices[parameter_id] = parameter_choices
        value, resolved_intent = _resolve_dynamic_value(
            definition,
            parameter_choices,
            supplied=parameter_id in provided,
            raw_value=provided.get(parameter_id),
            initialized=parameter_id in initialized,
            intent=requested_intents.get(parameter_id),
            strict=strict,
            preserve_unavailable=preserve_unavailable,
        )
        if preserve_unavailable:
            parameter_choices = _with_unavailable_choices(definition, parameter_choices, value)
            choices[parameter_id] = parameter_choices
        resolved[parameter_id] = value
        resolved_intents[parameter_id] = resolved_intent

    resolved_frames = {
        domain_id: next(
            frame.copy(deep=True)
            for (candidate_id, _), frame in frames.items()
            if candidate_id == domain_id
        )
        for domain_id in domain_metadata
    }
    return ParameterDomainResolution(
        values=resolved,
        choices=choices,
        intents=resolved_intents,
        domains=domain_metadata,
        contract=contract,
        client_projection=_build_client_projection(dashboard, contract, resolved_frames),
        frames=resolved_frames,
    )
