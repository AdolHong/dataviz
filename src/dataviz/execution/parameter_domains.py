"""Compile the declarative topology of Dashboard Parameter Domain consumers."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, TYPE_CHECKING

from dataviz.errors import ValidationFailure
from dataviz.protocols import PARAMETER_DOMAIN_CONTRACT_SCHEMA
from dataviz.workspace.models import ParameterDomainOptionDefinition

if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard


@dataclass(frozen=True, slots=True)
class ParameterDomainContract:
    """Only topology and ownership; rows remain in the Server materialization."""

    dependencies: dict[str, tuple[str, ...]]
    descendants: dict[str, tuple[str, ...]]
    order: tuple[str, ...]
    domain_consumers: dict[str, tuple[str, ...]]

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "dependencies": {key: list(value) for key, value in self.dependencies.items()},
            "descendants": {key: list(value) for key, value in self.descendants.items()},
            "order": list(self.order),
            "domain_consumers": {
                key: list(value) for key, value in self.domain_consumers.items()
            },
        }

    @property
    def contract_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self._canonical_payload(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_DOMAIN_CONTRACT_SCHEMA,
            "contract_hash": self.contract_hash,
            **deepcopy(self._canonical_payload()),
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


def _transitive_descendants(
    graph: Mapping[str, set[str]],
) -> dict[str, tuple[str, ...]]:
    direct = {key: set() for key in graph}
    for child, parents in graph.items():
        for parent in parents:
            direct[parent].add(child)
    result: dict[str, tuple[str, ...]] = {}
    for parameter_id in graph:
        pending = list(direct[parameter_id])
        found: set[str] = set()
        while pending:
            child = pending.pop()
            if child in found:
                continue
            found.add(child)
            pending.extend(direct[child])
        result[parameter_id] = tuple(sorted(found))
    return result


def compile_parameter_domain_contract(
    dashboard: LoadedDashboard,
) -> ParameterDomainContract:
    definitions = {item.id: item for item in dashboard.definition.query_parameters}
    graph = {key: set() for key in definitions}
    domain_consumers = {key: set() for key in dashboard.parameter_domains}
    for parameter_id, definition in definitions.items():
        options = definition.options
        if not isinstance(options, ParameterDomainOptionDefinition):
            continue
        if options.source not in dashboard.parameter_domains:
            raise ValidationFailure(
                f"Query Parameter {parameter_id} references unknown Parameter Domain: {options.source}",
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
        graph[parameter_id].update(parents)
        domain_consumers[options.source].add(parameter_id)
    return ParameterDomainContract(
        dependencies={key: tuple(sorted(value)) for key, value in graph.items()},
        descendants=_transitive_descendants(graph),
        order=_topological_order(graph),
        domain_consumers={
            key: tuple(sorted(value)) for key, value in domain_consumers.items()
        },
    )
