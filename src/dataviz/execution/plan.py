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


@dataclass(slots=True)
class ExecutionPlan:
    nodes: dict[str, PlanNode]
    targets: set[str]


def _target_node_id(value: str) -> str:
    return parse_output_reference(value).node_id


def reachable_output_references(
    dashboard: LoadedDashboard,
) -> tuple[set[str], list[str]]:
    """Return server Outputs and Browser Transforms reachable from presentation roots.

    Views, repeated Sections and explicitly declared Canvas inputs are the only
    presentation roots. This keeps an unused Source or Transform from delaying a
    Dashboard run while still allowing a custom Canvas to opt in explicitly.
    """
    pending = [
        reference
        for view in dashboard.definition.views
        for reference in view.input_refs.values()
    ]
    pending.extend(dashboard.definition.canvas.inputs)
    pending.extend(
        section.repeat.input
        for section in dashboard.definition.sections
        if section.repeat and section.repeat.input
    )
    server_references: set[str] = set()
    browser_ids: set[str] = set()

    while pending:
        reference = parse_output_reference(pending.pop())
        if reference.node_id.startswith("browser:"):
            transform_id = reference.node_id.split(":", 1)[1]
            if transform_id in browser_ids:
                continue
            browser_ids.add(transform_id)
            transform = dashboard.browser_transforms[transform_id][1]
            pending.extend(transform.inputs.values())
        else:
            server_references.add(reference.canonical)

    ordered: list[str] = []
    remaining = set(browser_ids)
    while remaining:
        ready = sorted(
            transform_id
            for transform_id in remaining
            if all(
                not parse_output_reference(reference).node_id.startswith("browser:")
                or parse_output_reference(reference).node_id.split(":", 1)[1] in ordered
                for reference in dashboard.browser_transforms[transform_id][1].inputs.values()
            )
        )
        if not ready:
            raise ValidationFailure("Browser Transform dependency graph contains a cycle")
        ordered.extend(ready)
        remaining.difference_update(ready)
    return server_references, ordered


def compile_plan(
    dashboard: LoadedDashboard,
    *,
    targets: list[str] | None = None,
) -> ExecutionPlan:
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
        )

    for transform_id, (path, definition) in dashboard.transforms.items():
        node_id = f"transform:{transform_id}"
        inputs = {
            name: parse_output_reference(reference)
            for name, reference in definition.inputs.items()
        }
        nodes[node_id] = PlanNode(
            id=node_id,
            local_id=transform_id,
            kind="transform",
            definition_path=path,
            definition=definition,
            dependencies={reference.node_id for reference in inputs.values()},
            inputs=inputs,
        )

    requested_targets = targets
    if requested_targets is None:
        reachable, _ = reachable_output_references(dashboard)
        requested_targets = sorted(reachable)
    selected_targets = {_target_node_id(value) for value in requested_targets or []}
    if not selected_targets:
        selected_targets.update(nodes)

    unknown = selected_targets - set(nodes)
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

    for target in selected_targets:
        include(target)

    selected_nodes = {node_id: node for node_id, node in nodes.items() if node_id in selected}
    _assert_acyclic(selected_nodes)
    return ExecutionPlan(nodes=selected_nodes, targets=selected_targets)


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
