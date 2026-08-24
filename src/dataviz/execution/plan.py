from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataviz.errors import ValidationFailure
from dataviz.execution.references import OutputReference, parse_output_reference
from dataviz.workspace.loader import LoadedDashboard
from dataviz.workspace.selection_domains import explicit_selection_option_references


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
    raw = value.strip()
    if "/" not in raw:
        # A Query target addresses a node execution, not one individual output.
        # Reuse the canonical reference validator while accepting the documented
        # source:<id> / dataset:<id> shorthand.
        return parse_output_reference(f"{raw}/main").node_id
    return parse_output_reference(raw).node_id


def reachable_output_references(
    dashboard: LoadedDashboard,
) -> tuple[set[str], list[str]]:
    """Return Base Outputs and Interactive Transforms reachable from presentation roots.

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
    pending.extend(explicit_selection_option_references(dashboard))
    base_references: set[str] = set()
    interactive_ids: set[str] = set()

    while pending:
        reference = parse_output_reference(pending.pop())
        if reference.node_id.startswith("interactive:"):
            transform_id = reference.node_id.split(":", 1)[1]
            if transform_id in interactive_ids:
                continue
            interactive_ids.add(transform_id)
            transform = dashboard.interactive_transforms[transform_id][1]
            pending.extend(transform.inputs.values())
        else:
            base_references.add(reference.canonical)

    ordered: list[str] = []
    remaining = set(interactive_ids)
    while remaining:
        ready = sorted(
            transform_id
            for transform_id in remaining
            if all(
                not parse_output_reference(reference).node_id.startswith("interactive:")
                or parse_output_reference(reference).node_id.split(":", 1)[1] in ordered
                for reference in dashboard.interactive_transforms[transform_id][1].inputs.values()
            )
        )
        if not ready:
            raise ValidationFailure("Interactive Transform dependency graph contains a cycle")
        ordered.extend(ready)
        remaining.difference_update(ready)
    return base_references, ordered


def server_interactive_base_references(dashboard: LoadedDashboard) -> set[str]:
    """Return Base Outputs that must remain server-readable for reachable interactions.

    Query Run Artifacts are already persisted below ``.dataviz/runs``. This
    classification makes the retention reason explicit: a browser-only branch
    needs a transport, while a reachable server-python branch needs the same
    immutable Base Output for every later interaction generation.
    """
    _, reachable_interactive = reachable_output_references(dashboard)
    reachable = set(reachable_interactive)
    required: set[str] = set()
    visited: set[str] = set()

    def include_inputs(identifier: str) -> None:
        if identifier in visited:
            return
        visited.add(identifier)
        definition = dashboard.interactive_transforms[identifier][1]
        for value in definition.inputs.values():
            reference = parse_output_reference(value)
            if reference.node_id.startswith("interactive:"):
                dependency = reference.node_id.split(":", 1)[1]
                if dependency in reachable:
                    include_inputs(dependency)
            else:
                required.add(reference.canonical)

    for identifier in reachable_interactive:
        definition = dashboard.interactive_transforms[identifier][1]
        if definition.runtime == "server-python":
            include_inputs(identifier)
    return required


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

    for transform_id, (path, definition) in dashboard.dataset_transforms.items():
        node_id = f"dataset:{transform_id}"
        inputs = {
            name: parse_output_reference(reference)
            for name, reference in definition.inputs.items()
        }
        nodes[node_id] = PlanNode(
            id=node_id,
            local_id=transform_id,
            kind="dataset_transform",
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
