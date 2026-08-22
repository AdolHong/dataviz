from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataviz.errors import ValidationFailure
from dataviz.workspace.loader import LoadedDashboard


@dataclass(slots=True)
class PlanNode:
    id: str
    local_id: str
    kind: str
    definition_path: Path
    definition: Any
    dependencies: set[str]


@dataclass(slots=True)
class ExecutionPlan:
    nodes: dict[str, PlanNode]
    targets: set[str]


def _source_node_id(value: str) -> str:
    return value if value.startswith("source:") else f"source:{value}"


def compile_plan(
    dashboard: LoadedDashboard,
    *,
    source_targets: list[str] | None = None,
) -> ExecutionPlan:
    nodes: dict[str, PlanNode] = {}
    for source_id, (path, definition) in dashboard.sources.items():
        node_id = _source_node_id(source_id)
        nodes[node_id] = PlanNode(
            id=node_id,
            local_id=source_id,
            kind="source",
            definition_path=path,
            definition=definition,
            dependencies={_source_node_id(value) for value in definition.depends_on},
        )

    targets: set[str] = set()
    if source_targets:
        targets.update(_source_node_id(value) for value in source_targets)
    if not targets:
        targets.update(_source_node_id(value) for value in dashboard.sources)

    unknown = targets - set(nodes)
    if unknown:
        raise ValidationFailure(f"Unknown execution targets: {', '.join(sorted(unknown))}")

    selected: set[str] = set()

    def include(node_id: str) -> None:
        if node_id in selected:
            return
        if node_id not in nodes:
            raise ValidationFailure(f"Unknown node dependency: {node_id}")
        selected.add(node_id)
        for dependency in nodes[node_id].dependencies:
            include(dependency)

    for target in targets:
        include(target)

    selected_nodes = {node_id: node for node_id, node in nodes.items() if node_id in selected}
    _assert_acyclic(selected_nodes)
    return ExecutionPlan(nodes=selected_nodes, targets=targets)


def _assert_acyclic(nodes: dict[str, PlanNode]) -> None:
    incoming = {node_id: set(node.dependencies) for node_id, node in nodes.items()}
    ready = [node_id for node_id, dependencies in incoming.items() if not dependencies]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for node_id, dependencies in incoming.items():
            if current in dependencies:
                dependencies.remove(current)
                if not dependencies:
                    ready.append(node_id)
    if visited != len(nodes):
        cycle_nodes = sorted(node_id for node_id, dependencies in incoming.items() if dependencies)
        raise ValidationFailure(f"Execution plan contains a cycle: {', '.join(cycle_nodes)}")
