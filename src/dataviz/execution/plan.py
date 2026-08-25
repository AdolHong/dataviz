from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataviz.errors import ValidationFailure
from dataviz.execution.references import OutputReference, parse_output_reference
from dataviz.workspace.loader import LoadedDashboard


@dataclass(slots=True)
class PlanNode:
    id: str
    local_id: str
    kind: str
    definition_path: Path
    definition: Any
    dependencies: set[str]
    inputs: dict[str, OutputReference]
    parameter_inputs: dict[str, Any]


@dataclass(slots=True)
class ExecutionPlan:
    nodes: dict[str, PlanNode]
    targets: set[str]


def _target_node_id(value: str) -> str:
    raw = value.strip()
    if "/" not in raw:
        # A Query target addresses a node execution, not one individual output.
        # Reuse the canonical reference validator while accepting the documented
        # source:<id> / dataset:<id> shorthand.
        return parse_output_reference(f"{raw}/main").node_id
    return parse_output_reference(raw).node_id


def compile_plan(
    dashboard: LoadedDashboard,
    *,
    targets: list[str] | None = None,
) -> ExecutionPlan:
    dependency_contract = dashboard.dependency_contract
    nodes: dict[str, PlanNode] = {}
    for source_id, (path, definition) in dashboard.sources.items():
        node_id = f"source:{source_id}"
        nodes[node_id] = PlanNode(
            id=node_id,
            local_id=source_id,
            kind="source",
            definition_path=path,
            definition=definition,
            dependencies=set(),
            inputs={},
            parameter_inputs=dict(dependency_contract.parameter_inputs[node_id]),
        )

    for transform_id, (path, definition) in dashboard.dataset_transforms.items():
        node_id = f"dataset:{transform_id}"
        inputs = {
            name: parse_output_reference(reference)
            for name, reference in dependency_contract.data_inputs[node_id].items()
        }
        nodes[node_id] = PlanNode(
            id=node_id,
            local_id=transform_id,
            kind="dataset_transform",
            definition_path=path,
            definition=definition,
            dependencies=set(dependency_contract.query_dependencies[node_id]),
            inputs=inputs,
            parameter_inputs=dict(dependency_contract.parameter_inputs[node_id]),
        )

    requested_targets = targets
    if requested_targets is None:
        requested_targets = sorted(dependency_contract.base_output_roots)
    selected_targets = {_target_node_id(value) for value in requested_targets or []}
    if not selected_targets:
        selected_targets.update(nodes)

    unknown = selected_targets - set(nodes)
    if unknown:
        raise ValidationFailure(f"Unknown execution targets: {', '.join(sorted(unknown))}")

    selected = dependency_contract.query_closure(selected_targets)

    selected_nodes = {node_id: node for node_id, node in nodes.items() if node_id in selected}
    return ExecutionPlan(nodes=selected_nodes, targets=selected_targets)
