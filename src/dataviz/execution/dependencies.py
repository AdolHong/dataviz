from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, TYPE_CHECKING

from dataviz.content_templates import (
    content_control_contract,
    content_template_fields,
    inspect_content_template,
)
from dataviz.errors import ValidationFailure
from dataviz.execution.references import parse_output_reference
from dataviz.execution.parameters import (
    control_input_contract,
    control_input_control,
    query_input_contract,
    query_input_parameter,
)
from dataviz.workspace.controls import (
    EffectiveControl,
    canonical_control_key,
    compile_control_contract,
    resolve_dashboard_control_reference,
    scoped_control_registry,
)
from dataviz.input_state import initial_input_state
from dataviz.workspace.models import (
    InferredOptionDomainDefinition,
    ViewControlBindingDefinition,
)

if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard


DEPENDENCY_CONTRACT_SCHEMA = "dataviz/dependency-contract/v7"


def _topological_order(
    graph: dict[str, set[str]],
    *,
    label: str,
) -> tuple[str, ...]:
    pending = {node: set(dependencies) for node, dependencies in graph.items()}
    unknown = sorted(
        dependency
        for dependencies in pending.values()
        for dependency in dependencies
        if dependency not in pending
    )
    if unknown:
        raise ValidationFailure(
            f"{label} references unknown dependencies: {', '.join(unknown)}"
        )
    order: list[str] = []
    while pending:
        ready = sorted(
            node
            for node, dependencies in pending.items()
            if not dependencies
        )
        if not ready:
            raise ValidationFailure(
                f"{label} contains a cycle: {', '.join(sorted(pending))}"
            )
        order.extend(ready)
        for node in ready:
            pending.pop(node)
        for dependencies in pending.values():
            dependencies.difference_update(ready)
    return tuple(order)


def _dependency_cycle(graph: dict[str, set[str]]) -> tuple[str, ...] | None:
    """Return one deterministic dependency cycle, including its repeated start."""

    visited: set[str] = set()
    active: list[str] = []
    active_index: dict[str, int] = {}

    def visit(node: str) -> tuple[str, ...] | None:
        if node in active_index:
            start = active_index[node]
            return tuple([*active[start:], node])
        if node in visited:
            return None
        active_index[node] = len(active)
        active.append(node)
        for dependency in sorted(graph[node]):
            cycle = visit(dependency)
            if cycle is not None:
                return cycle
        active.pop()
        active_index.pop(node)
        visited.add(node)
        return None

    for node in sorted(graph):
        cycle = visit(node)
        if cycle is not None:
            return cycle
    return None


def _compile_control_dependency_graph(
    dashboard_id: str,
    registry: dict[str, EffectiveControl],
    section_for_view: dict[str, Any],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
    tuple[str, ...],
]:
    """Resolve scoped references and compile one option-domain DAG."""

    dependencies: dict[str, set[str]] = {key: set() for key in registry}

    for target in registry.values():
        references = getattr(target.definition, "depends_on", ())
        for reference in references:
            scope, control_id = reference.split(".", 1)
            if scope == "dashboard":
                owner_id = dashboard_id
            elif scope == "section":
                if target.origin == "dashboard":
                    owner_id = None
                elif target.origin == "section":
                    owner_id = target.owner_id
                else:
                    section = section_for_view.get(target.owner_id)
                    owner_id = section.id if section is not None else None
            else:  # view
                owner_id = target.owner_id if target.origin == "view" else None

            if owner_id is None:
                raise ValidationFailure(
                    f"Control {target.key} cannot depend on {reference} from its scope",
                    details={
                        "code": "control_dependency_scope_invalid",
                        "control": target.key,
                        "dependency": reference,
                        "origin": target.origin,
                    },
                )

            dependency_key = canonical_control_key(scope, owner_id, control_id)
            dependency = registry.get(dependency_key)
            if dependency is None:
                raise ValidationFailure(
                    f"Control {target.key} references unknown dependency: {reference}",
                    details={
                        "code": "control_dependency_unknown",
                        "control": target.key,
                        "dependency": reference,
                        "resolved_key": dependency_key,
                    },
                )
            dependencies[target.key].add(dependency_key)

    cycle = _dependency_cycle(dependencies)
    if cycle is not None:
        raise ValidationFailure(
            "Control dependency DAG contains a cycle: " + " -> ".join(cycle),
            details={
                "code": "control_dependency_cycle",
                "cycle": list(cycle),
            },
        )

    order = _topological_order(dependencies, label="Control dependency DAG")
    ancestors: dict[str, set[str]] = {key: set() for key in registry}
    for key in order:
        for dependency in dependencies[key]:
            ancestors[key].add(dependency)
            ancestors[key].update(ancestors[dependency])
    descendants: dict[str, set[str]] = {key: set() for key in registry}
    for key, upstream in ancestors.items():
        for dependency in upstream:
            descendants[dependency].add(key)
    return dependencies, ancestors, descendants, order


def _resolve_control_reference(
    reference: str,
    *,
    dashboard_id: str,
    view_id: str,
    section_for_view: dict[str, Any],
) -> str:
    """Resolve an author-facing scoped key from one View's location."""

    scope, control_id = reference.split(".", 1)
    if scope == "dashboard":
        owner_id = dashboard_id
    elif scope == "section":
        section = section_for_view.get(view_id)
        owner_id = section.id if section is not None else None
    else:
        owner_id = view_id
    if owner_id is None:
        raise ValidationFailure(
            f"View {view_id} cannot resolve Control binding {reference}",
            details={
                "code": "view_control_binding_scope_invalid",
                "view": view_id,
                "control": reference,
            },
        )
    return canonical_control_key(scope, owner_id, control_id)


def _control_value_fields(item: EffectiveControl) -> tuple[str, ...]:
    """Return the default datum fields written by one bound View."""

    return tuple(
        item.definition.path_fields
        or [item.definition.field or item.id]
    )


def _declared_outputs(kind: str, identifier: str, definition: Any) -> tuple[str, ...]:
    return tuple(
        f"{kind}:{identifier}/{name}"
        for name in definition.outputs
    )


def _require_declared_references(
    references: Iterable[str],
    declared: set[str],
    *,
    label: str,
) -> None:
    canonical = {
        parse_output_reference(reference).canonical for reference in references
    }
    unknown = sorted(canonical - declared)
    if unknown:
        raise ValidationFailure(
            f"{label} references unknown Named Outputs: {', '.join(unknown)}"
        )


def _output_dependency_closure(
    references: Iterable[str],
    interactive_inputs: dict[str, dict[str, str]],
) -> tuple[set[str], set[str]]:
    interactive: set[str] = set()
    base: set[str] = set()
    pending = [parse_output_reference(reference).canonical for reference in references]
    while pending:
        parsed = parse_output_reference(pending.pop())
        if not parsed.node_id.startswith("interactive:"):
            base.add(parsed.canonical)
            continue
        identifier = parsed.node_id.split(":", 1)[1]
        if identifier in interactive:
            continue
        if identifier not in interactive_inputs:
            raise ValidationFailure(
                f"Unknown Interactive Transform dependency: {identifier}"
            )
        interactive.add(identifier)
        pending.extend(interactive_inputs[identifier].values())
    return interactive, base


def _downstream_closure(
    seeds: Iterable[str],
    consumers: dict[str, set[str]],
) -> set[str]:
    """Return seeds and every transitive consumer in one compiled graph."""

    selected: set[str] = set()
    pending = list(seeds)
    while pending:
        current = pending.pop()
        if current in selected:
            continue
        selected.add(current)
        pending.extend(consumers.get(current, ()))
    return selected


def _upstream_closure(
    seeds: Iterable[str],
    dependencies: dict[str, set[str]],
) -> set[str]:
    """Return seeds and every transitive dependency in one compiled graph."""

    selected: set[str] = set()
    pending = list(seeds)
    while pending:
        current = pending.pop()
        if current in selected:
            continue
        selected.add(current)
        pending.extend(dependencies.get(current, ()))
    return selected


@dataclass(frozen=True, slots=True)
class QueryParameterDependency:
    key: str
    direct_query_nodes: tuple[str, ...]
    direct_interactive_transforms: tuple[str, ...]
    content_fields: tuple[str, ...]
    affected_query_nodes: tuple[str, ...]
    affected_interactive_transforms: tuple[str, ...]
    affected_option_controls: tuple[str, ...]
    affected_views: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "direct_query_nodes": list(self.direct_query_nodes),
            "direct_interactive_transforms": list(
                self.direct_interactive_transforms
            ),
            "content_fields": list(self.content_fields),
            "affected_query_nodes": list(self.affected_query_nodes),
            "affected_interactive_transforms": list(
                self.affected_interactive_transforms
            ),
            "affected_option_controls": list(self.affected_option_controls),
            "affected_views": list(self.affected_views),
        }


@dataclass(frozen=True, slots=True)
class ControlFilterDependency:
    view_id: str
    alias: str
    fields: tuple[str, ...]
    operator: str
    empty: str
    input_aliases: tuple[str, ...]
    input_references: tuple[str, ...]
    applicability: Literal["declared", "runtime", "not_applicable"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "fields": list(self.fields),
            "operator": self.operator,
            "empty": self.empty,
            "input_aliases": list(self.input_aliases),
            "input_references": list(self.input_references),
            "applicability": self.applicability,
        }


@dataclass(frozen=True, slots=True)
class ViewControlBindingDependency:
    view_id: str
    control: str
    fields: tuple[str, ...]
    renderer: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "control": self.control,
            "fields": list(self.fields),
            "renderer": self.renderer,
            "actions": ["select", "select_many", "clear", "reset"],
        }


@dataclass(frozen=True, slots=True)
class ControlDependency:
    key: str
    origin: str
    owner_id: str
    scope_views: tuple[str, ...]
    direct_views: tuple[str, ...]
    declared_direct_views: tuple[str, ...]
    runtime_checked_views: tuple[str, ...]
    non_data_views: tuple[str, ...]
    direct_view_bindings: dict[str, ControlFilterDependency]
    writer_view: str | None
    writer_fields: tuple[str, ...]
    transform_consumers: tuple[str, ...]
    transform_inputs: dict[str, tuple[str, ...]]
    derived_views: tuple[str, ...]
    content_fields: tuple[str, ...]
    content_views: tuple[str, ...]
    repeat_views: tuple[str, ...]
    affected_views: tuple[str, ...]
    option_domain_references: tuple[str, ...]
    depends_on: tuple[str, ...]
    dependency_ancestors: tuple[str, ...]
    dependency_descendants: tuple[str, ...]
    definition: dict[str, Any]
    initial_state: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "origin": self.origin,
            "owner_id": self.owner_id,
            "scope_views": list(self.scope_views),
            "direct_views": list(self.direct_views),
            "declared_direct_views": list(self.declared_direct_views),
            "runtime_checked_views": list(self.runtime_checked_views),
            "non_data_views": list(self.non_data_views),
            "direct_view_bindings": {
                view_id: dependency.as_dict()
                for view_id, dependency in self.direct_view_bindings.items()
            },
            "writer_view": self.writer_view,
            "writer_fields": list(self.writer_fields),
            "transform_consumers": list(self.transform_consumers),
            "transform_inputs": {
                transform_id: list(aliases)
                for transform_id, aliases in self.transform_inputs.items()
            },
            "derived_views": list(self.derived_views),
            "content_fields": list(self.content_fields),
            "content_views": list(self.content_views),
            "repeat_views": list(self.repeat_views),
            "affected_views": list(self.affected_views),
            "option_domain_references": list(self.option_domain_references),
            "depends_on": list(self.depends_on),
            "dependency_ancestors": list(self.dependency_ancestors),
            "dependency_descendants": list(self.dependency_descendants),
            "definition": self.definition,
            "initial_state": self.initial_state,
        }


@dataclass(frozen=True, slots=True)
class DashboardDependencyContract:
    dashboard_id: str
    parameter_domain_contract: dict[str, Any]
    query_dependencies: dict[str, tuple[str, ...]]
    data_inputs: dict[str, dict[str, str]]
    query_outputs: dict[str, tuple[str, ...]]
    query_order: tuple[str, ...]
    parameter_inputs: dict[str, dict[str, dict[str, Any]]]
    query_parameter_consumers: dict[str, tuple[str, ...]]
    query_parameters: dict[str, QueryParameterDependency]
    query_node_downstream_views: dict[str, tuple[str, ...]]
    query_node_option_controls: dict[str, tuple[str, ...]]
    presentation_roots: tuple[str, ...]
    base_output_roots: tuple[str, ...]
    interactive_dependencies: dict[str, tuple[str, ...]]
    interactive_inputs: dict[str, dict[str, str]]
    interactive_outputs: dict[str, tuple[str, ...]]
    interactive_runtimes: dict[str, str]
    interactive_parameter_inputs: dict[str, dict[str, dict[str, Any]]]
    interactive_control_inputs: dict[str, dict[str, dict[str, Any]]]
    interactive_order: tuple[str, ...]
    reachable_interactive_order: tuple[str, ...]
    transform_direct_views: dict[str, tuple[str, ...]]
    transform_downstream_views: dict[str, tuple[str, ...]]
    view_inputs: dict[str, dict[str, str]]
    view_controls: dict[str, tuple[str, ...]]
    view_control_contract: dict[str, tuple[EffectiveControl, ...]]
    view_control_inputs: dict[str, dict[str, dict[str, Any]]]
    view_control_bindings: dict[str, ViewControlBindingDependency]
    output_view_consumers: dict[str, tuple[str, ...]]
    control_option_domains: dict[str, tuple[str, ...]]
    control_order: tuple[str, ...]
    controls: dict[str, ControlDependency]

    def view_filter_contract(self, view_id: str) -> tuple[dict[str, Any], ...]:
        bindings = self.view_control_inputs.get(view_id, {})
        registry = {item.key: item for item in self.view_control_contract.get(view_id, ())}
        result: list[dict[str, Any]] = []
        for alias, binding in bindings.items():
            if binding.get("mode") != "filter":
                continue
            item = registry[binding["control"]]
            result.append({**item.as_dict(), "alias": alias, "consumer_binding": binding})
        return tuple(result)

    def query_closure(self, targets: Iterable[str]) -> set[str]:
        selected: set[str] = set()

        def include(node_id: str) -> None:
            if node_id in selected:
                return
            if node_id not in self.query_dependencies:
                raise ValidationFailure(f"Unknown Query dependency: {node_id}")
            selected.add(node_id)
            for dependency in self.query_dependencies[node_id]:
                include(dependency)

        for target in targets:
            include(target)
        return selected

    def interactive_closure(self, target: str) -> tuple[str, ...]:
        if target not in self.interactive_dependencies:
            raise ValidationFailure(f"Unknown Interactive Transform: {target}")
        selected: set[str] = set()

        def include(identifier: str) -> None:
            if identifier in selected:
                return
            for dependency in self.interactive_dependencies[identifier]:
                include(dependency)
            selected.add(identifier)

        include(target)
        return tuple(
            identifier for identifier in self.interactive_order if identifier in selected
        )

    def interactive_ancestors(self, target: str) -> set[str]:
        return set(self.interactive_closure(target)) - {target}

    def output_closure(
        self, references: Iterable[str]
    ) -> tuple[set[str], set[str]]:
        """Resolve presentation references into Interactive nodes and Base Outputs."""

        return _output_dependency_closure(references, self.interactive_inputs)

    def server_interactive_base_references(self) -> set[str]:
        required: set[str] = set()
        for identifier in self.reachable_interactive_order:
            if self.interactive_runtimes[identifier] == "server-python":
                _, base = self.output_closure(
                    self.interactive_inputs[identifier].values()
                )
                required.update(base)
        return required

    def view_pipeline_nodes(self, view_id: str) -> tuple[str, ...]:
        """Return one compiler-owned, topologically ordered View pipeline.

        Authors declare data and View inputs once.  Diagnostics must project that
        same graph instead of asking a Canvas or Renderer to reconstruct it.
        """

        query_nodes = (
            node_id
            for node_id in self.query_order
            if view_id in self.query_node_downstream_views.get(node_id, ())
        )
        interactive_nodes = (
            f"interactive:{identifier}"
            for identifier in self.reachable_interactive_order
            if view_id in self.transform_downstream_views.get(identifier, ())
        )
        return tuple((*query_nodes, *interactive_nodes))

    def runtime_manifest(self) -> dict[str, Any]:
        reachable = set(self.reachable_interactive_order)
        output_views = {
            reference: list(views)
            for reference, views in self.output_view_consumers.items()
            if views
        }
        return {
            "schema": DEPENDENCY_CONTRACT_SCHEMA,
            "initialization": [
                "base_outputs",
                "control_option_domains",
                "canonical_controls",
                "base_views",
                "interactive_transforms",
            ],
            "interactive": {
                "order": list(self.reachable_interactive_order),
                "inputs": {
                    identifier: dict(self.interactive_inputs[identifier])
                    for identifier in self.reachable_interactive_order
                },
                "outputs": {
                    identifier: list(self.interactive_outputs[identifier])
                    for identifier in self.reachable_interactive_order
                },
                "parameter_inputs": {
                    identifier: dict(self.interactive_parameter_inputs[identifier])
                    for identifier in self.reachable_interactive_order
                },
                "control_inputs": {
                    identifier: dict(self.interactive_control_inputs[identifier])
                    for identifier in self.reachable_interactive_order
                },
                "dependencies": {
                    identifier: [
                        dependency
                        for dependency in self.interactive_dependencies[identifier]
                        if dependency in reachable
                    ]
                    for identifier in self.reachable_interactive_order
                },
                "downstream_views": {
                    identifier: list(self.transform_downstream_views[identifier])
                    for identifier in self.reachable_interactive_order
                },
                "direct_views": {
                    identifier: list(self.transform_direct_views[identifier])
                    for identifier in self.reachable_interactive_order
                },
            },
            "views": {
                view_id: {
                    "inputs": dict(inputs),
                    "pipeline_nodes": list(self.view_pipeline_nodes(view_id)),
                    "controls": list(self.view_controls.get(view_id, ())),
                    "control_inputs": dict(self.view_control_inputs.get(view_id, {})),
                    "filter_contract": list(self.view_filter_contract(view_id)),
                    "control_binding": (
                        self.view_control_bindings[view_id].as_dict()
                        if view_id in self.view_control_bindings
                        else None
                    ),
                }
                for view_id, inputs in self.view_inputs.items()
            },
            "outputs": {
                reference: {"views": views}
                for reference, views in output_views.items()
            },
            "controls": {
                key: dependency.as_dict()
                for key, dependency in self.controls.items()
            },
            "control_order": list(self.control_order),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": DEPENDENCY_CONTRACT_SCHEMA,
            "dashboard": self.dashboard_id,
            "query": {
                "parameter_domains": self.parameter_domain_contract,
                "dependencies": {
                    key: list(value) for key, value in self.query_dependencies.items()
                },
                "data_inputs": self.data_inputs,
                "outputs": {
                    key: list(value) for key, value in self.query_outputs.items()
                },
                "order": list(self.query_order),
                "parameter_inputs": self.parameter_inputs,
                "parameter_consumers": {
                    key: list(value)
                    for key, value in self.query_parameter_consumers.items()
                },
                "parameters": {
                    key: value.as_dict()
                    for key, value in self.query_parameters.items()
                },
                "downstream_views": {
                    key: list(value)
                    for key, value in self.query_node_downstream_views.items()
                },
                "option_controls": {
                    key: list(value)
                    for key, value in self.query_node_option_controls.items()
                },
                "presentation_roots": list(self.presentation_roots),
                "base_output_roots": list(self.base_output_roots),
            },
            "interactive": {
                "dependencies": {
                    key: list(value)
                    for key, value in self.interactive_dependencies.items()
                },
                "inputs": self.interactive_inputs,
                "outputs": {
                    key: list(value)
                    for key, value in self.interactive_outputs.items()
                },
                "runtimes": dict(self.interactive_runtimes),
                "parameter_inputs": self.interactive_parameter_inputs,
                "control_inputs": self.interactive_control_inputs,
                "order": list(self.interactive_order),
                "reachable_order": list(self.reachable_interactive_order),
                "direct_views": {
                    key: list(value)
                    for key, value in self.transform_direct_views.items()
                },
                "downstream_views": {
                    key: list(value)
                    for key, value in self.transform_downstream_views.items()
                },
            },
            "views": {
                key: {
                    "inputs": value,
                    "pipeline_nodes": list(self.view_pipeline_nodes(key)),
                      "controls": list(self.view_controls.get(key, ())),
                      "control_inputs": dict(self.view_control_inputs.get(key, {})),
                    "control_binding": (
                        self.view_control_bindings[key].as_dict()
                        if key in self.view_control_bindings
                        else None
                    ),
                }
                for key, value in self.view_inputs.items()
            },
            "outputs": {
                key: {"views": list(value)}
                for key, value in self.output_view_consumers.items()
            },
            "control_option_domains": {
                  key: list(value)
                  for key, value in self.control_option_domains.items()
              },
            "controls": {
                key: value.as_dict() for key, value in self.controls.items()
            },
            "control_order": list(self.control_order),
        }


def compile_dashboard_dependencies(
    dashboard: LoadedDashboard,
) -> DashboardDependencyContract:
    query_dependencies: dict[str, set[str]] = {}
    data_inputs: dict[str, dict[str, str]] = {}
    query_outputs: dict[str, tuple[str, ...]] = {}
    for identifier, (_, definition) in dashboard.sources.items():
        node_id = f"source:{identifier}"
        query_dependencies[node_id] = set()
        data_inputs[node_id] = {}
        query_outputs[node_id] = _declared_outputs("source", identifier, definition)
    for identifier, (_, definition) in dashboard.dataset_transforms.items():
        node_id = f"dataset:{identifier}"
        data_inputs[node_id] = {
            alias: parse_output_reference(reference).canonical
            for alias, reference in definition.inputs.items()
        }
        query_dependencies[node_id] = {
            parse_output_reference(reference).node_id
            for reference in data_inputs[node_id].values()
        }
        query_outputs[node_id] = _declared_outputs("dataset", identifier, definition)
    query_order = _topological_order(query_dependencies, label="Query DAG")
    query_output_references = {
        reference
        for references in query_outputs.values()
        for reference in references
    }
    _require_declared_references(
        (
            reference
            for _, definition in dashboard.dataset_transforms.values()
            for reference in definition.inputs.values()
        ),
        query_output_references,
        label="Query DAG",
    )

    interactive_inputs = {
        identifier: {
            alias: parse_output_reference(reference).canonical
            for alias, reference in definition.inputs.items()
        }
        for identifier, (_, definition) in dashboard.interactive_transforms.items()
    }
    interactive_dependencies = {
        identifier: {
            parsed.node_id.split(":", 1)[1]
            for parsed in (
                parse_output_reference(reference)
                for reference in inputs.values()
            )
            if parsed.node_id.startswith("interactive:")
        }
        for identifier, inputs in interactive_inputs.items()
    }
    interactive_order = _topological_order(
        interactive_dependencies,
        label="Interactive DAG",
    )
    interactive_outputs = {
        identifier: _declared_outputs("interactive", identifier, definition)
        for identifier, (_, definition) in dashboard.interactive_transforms.items()
    }
    interactive_output_references = {
        reference
        for references in interactive_outputs.values()
        for reference in references
    }
    _require_declared_references(
        (
            reference
            for inputs in interactive_inputs.values()
            for reference in inputs.values()
        ),
        query_output_references | interactive_output_references,
        label="Interactive DAG",
    )
    interactive_runtimes = {
        identifier: definition.runtime
        for identifier, (_, definition) in dashboard.interactive_transforms.items()
    }
    interactive_parameter_inputs = {
        identifier: {
            alias: query_input_contract(binding)
            for alias, binding in definition.query_inputs.items()
        }
        for identifier, (_, definition) in dashboard.interactive_transforms.items()
    }
    interactive_control_inputs = {
        identifier: {
            alias: {
                **control_input_contract(binding),
                "control": resolve_dashboard_control_reference(
                    control_input_contract(binding)["control"],
                    dashboard.definition.id,
                ),
            }
            for alias, binding in definition.control_inputs.items()
        }
        for identifier, (_, definition) in dashboard.interactive_transforms.items()
    }
    output_definitions = {
        f"source:{identifier}/{name}": output
        for identifier, (_, definition) in dashboard.sources.items()
        for name, output in definition.outputs.items()
    }
    output_definitions.update(
        {
            f"dataset:{identifier}/{name}": output
            for identifier, (_, definition) in dashboard.dataset_transforms.items()
            for name, output in definition.outputs.items()
        }
    )
    output_definitions.update(
        {
            f"interactive:{identifier}/{name}": output
            for identifier, (_, definition) in dashboard.interactive_transforms.items()
            for name, output in definition.outputs.items()
        }
    )
    view_inputs = {
        view.id: {
            alias: parse_output_reference(reference).canonical
            for alias, reference in view.input_refs.items()
        }
        for view in dashboard.definition.views
    }
    # A repeated Section replaces the blueprint View's data input in the browser.
    # Compile that effective input once so Query reachability, option domains and
    # redraw routing all describe the same runtime graph.
    for section in dashboard.definition.sections:
        if not section.repeat:
            continue
        view_id = section.repeat.view or next(iter(section.views), None)
        if view_id and section.repeat.input:
            view_inputs[view_id] = {
                "main": parse_output_reference(section.repeat.input).canonical
            }

    registry = scoped_control_registry(dashboard.definition)
    section_for_view = {
        view_id: section
        for section in dashboard.definition.sections
        for view_id in section.views
    }
    view_control_inputs = {
        view.id: {
            alias: {
                **control_input_contract(binding),
                "control": _resolve_control_reference(
                    control_input_control(binding),
                    dashboard_id=dashboard.definition.id,
                    view_id=view.id,
                    section_for_view=section_for_view,
                ),
            }
            for alias, binding in view.control_inputs.items()
        }
        for view in dashboard.definition.views
    }
    (
        control_dependencies,
        control_ancestors,
        control_descendants,
        control_order,
    ) = _compile_control_dependency_graph(
        dashboard.definition.id,
        registry,
        section_for_view,
    )
    option_domains: dict[str, set[str]] = {key: set() for key in registry}
    explicit_option_roots: list[str] = []
    for key, item in registry.items():
        options = item.definition.options
        if isinstance(options, InferredOptionDomainDefinition) and options.source:
            reference = parse_output_reference(options.source).canonical
            option_domains[key].add(reference)
            explicit_option_roots.append(reference)

    presentation_roots = [
        reference
        for inputs in view_inputs.values()
        for reference in inputs.values()
    ]
    presentation_roots.extend(
        parse_output_reference(reference).canonical
        for reference in dashboard.definition.canvas.inputs
    )
    presentation_roots.extend(explicit_option_roots)
    _require_declared_references(
        presentation_roots,
        query_output_references | interactive_output_references,
        label="Presentation",
    )
    for key, references in option_domains.items():
        for reference in references:
            parsed = parse_output_reference(reference)
            if parsed.node_id.startswith("interactive:"):
                raise ValidationFailure(
                    f"Control {key} option domain must use an immutable Base Output",
                    details={
                        "code": "control_option_domain_invalid",
                        "control": key,
                        "reference": reference,
                    },
                )
            if output_definitions[reference].kind != "table":
                raise ValidationFailure(
                    f"Control {key} option domain must reference a table Output",
                    details={
                        "code": "control_option_domain_kind",
                        "control": key,
                        "reference": reference,
                        "kind": output_definitions[reference].kind,
                    },
                )

    reachable_interactive, base_output_roots = _output_dependency_closure(
        presentation_roots,
        interactive_inputs,
    )

    effective_controls = compile_control_contract(dashboard.definition)
    view_control_contract = {
        view_id: tuple(items) for view_id, items in effective_controls.items()
    }
    view_controls = {
        view_id: tuple(item.key for item in items)
        for view_id, items in effective_controls.items()
    }
    for view_id, bindings in view_control_inputs.items():
        for alias, binding in bindings.items():
            control_key = binding["control"]
            if control_key not in registry:
                raise ValidationFailure(
                    f"View {view_id} references unknown Control: {control_key}",
                    details={
                        "code": "view_control_input_unknown",
                        "view": view_id,
                        "alias": alias,
                        "control": control_key,
                    },
                )
            if control_key not in view_controls.get(view_id, ()):
                raise ValidationFailure(
                    f"Control {control_key} is outside View {view_id} scope",
                    details={
                        "code": "view_control_input_out_of_scope",
                        "view": view_id,
                        "alias": alias,
                        "control": control_key,
                    },
                )
    view_control_bindings: dict[str, ViewControlBindingDependency] = {}
    writer_by_control: dict[str, ViewControlBindingDependency] = {}
    scope_rank = {"dashboard": 0, "section": 1, "view": 2}
    chart_templates = {
        "line",
        "bar",
        "stacked-bar",
        "pie",
        "scatter",
        "heatmap",
        "radar",
    }
    views_by_id = {view.id: view for view in dashboard.definition.views}
    for view_id, view in views_by_id.items():
        raw_binding = view.control_binding
        if raw_binding is None:
            continue
        binding = (
            ViewControlBindingDefinition(control=raw_binding)
            if isinstance(raw_binding, str)
            else raw_binding
        )
        control_key = _resolve_control_reference(
            binding.control,
            dashboard_id=dashboard.definition.id,
            view_id=view_id,
            section_for_view=section_for_view,
        )
        target = registry.get(control_key)
        if target is None:
            raise ValidationFailure(
                f"View {view_id} binds unknown Control: {binding.control}",
                details={
                    "code": "view_control_binding_unknown",
                    "view": view_id,
                    "control": binding.control,
                    "resolved_key": control_key,
                },
            )
        if control_key not in view_controls.get(view_id, ()):
            raise ValidationFailure(
                f"Control {control_key} is outside View {view_id} scope",
                details={
                    "code": "view_control_binding_out_of_scope",
                    "view": view_id,
                    "control": control_key,
                },
            )
        previous_writer = writer_by_control.get(control_key)
        if previous_writer is not None:
            raise ValidationFailure(
                f"Control {control_key} has more than one writer View",
                details={
                    "code": "view_control_binding_writer_conflict",
                    "control": control_key,
                    "views": [previous_writer.view_id, view_id],
                },
            )
        narrower = sorted(
            binding["control"]
            for binding in view_control_inputs.get(view_id, {}).values()
            if binding.get("mode") == "filter"
            and binding["control"] != control_key
            and scope_rank[registry[binding["control"]].origin] > scope_rank[target.origin]
        )
        if narrower:
            raise ValidationFailure(
                f"View {view_id} cannot narrow bound Control {control_key} with "
                + ", ".join(narrower),
                details={
                    "code": "view_control_binding_reverse_scope",
                    "view": view_id,
                    "control": control_key,
                    "narrower_controls": narrower,
                },
            )
        fields = tuple(
            [binding.field]
            if binding.field
            else _control_value_fields(target)
        )
        value_fields = (
            [view.z]
            if view.template == "heatmap"
            else (
                list(view.y)
                if isinstance(view.y, list)
                else [view.y or view.value or view.z]
            )
        )
        value_fields = [field for field in value_fields if field]
        group_fields = [
            field
            for field in (
                [view.x, view.y] if view.template == "heatmap"
                else [view.x or view.label, view.series]
            )
            if isinstance(field, str) and field
        ]
        operation = (
            "none"
            if view.template == "metric"
            else (
                view.aggregate
                or (
                    "none"
                    if view.template in {"scatter", "table", "perspective"}
                    else "sum"
                )
            )
        )
        if operation != "none" and value_fields and not set(fields) <= set(group_fields):
            raise ValidationFailure(
                f"View {view_id} aggregates away its Control binding field",
                details={
                    "code": "view_control_binding_aggregate_ambiguous",
                    "view": view_id,
                    "control": control_key,
                    "fields": list(fields),
                    "group_fields": group_fields,
                    "aggregate": operation,
                },
            )
        if view.template == "custom":
            renderer = view.renderer or "custom"
        elif view.template == "table":
            renderer = "table"
        elif view.template in chart_templates:
            renderer = "plotly"
        else:
            raise ValidationFailure(
                f"View {view_id} template does not support Control binding: {view.template}",
                details={
                    "code": "view_control_binding_renderer_unsupported",
                    "view": view_id,
                    "template": view.template,
                },
            )
        references = tuple(sorted(view_inputs.get(view_id, {}).values()))
        declared_tables = [
            output_definitions[reference]
            for reference in references
            if output_definitions[reference].kind == "table"
            and output_definitions[reference].schema_
        ]
        if declared_tables and not any(
            all(any(column.name == field for column in output.schema_) for field in fields)
            for output in declared_tables
        ):
            raise ValidationFailure(
                f"View {view_id} binding fields are absent from its declared table schema",
                details={
                    "code": "view_control_binding_field_unknown",
                    "view": view_id,
                    "control": control_key,
                    "fields": list(fields),
                    "references": list(references),
                },
            )
        compiled_binding = ViewControlBindingDependency(
            view_id=view_id,
            control=control_key,
            fields=fields,
            renderer=renderer,
        )
        view_control_bindings[view_id] = compiled_binding
        writer_by_control[control_key] = compiled_binding
    for view_id, items in effective_controls.items():
        _, inferred = _output_dependency_closure(
            view_inputs.get(view_id, {}).values(),
            interactive_inputs,
        )
        for item in items:
            options = item.definition.options
            dynamic_domain = (
                isinstance(options, InferredOptionDomainDefinition)
                and not options.source
            )
            dependent_static_domain = (
                options is not None
                and not isinstance(options, InferredOptionDomainDefinition)
                and bool(control_dependencies[item.key])
            )
            if dynamic_domain or dependent_static_domain:
                option_domains[item.key].update(inferred)

    # Explicit Control dependencies are executable only when the child has an
    # immutable table relation from which its candidate values can be derived.
    # This is intentionally part of the Dependency Compiler: ``validate`` and
    # the browser must not maintain separate interpretations of the same edge.
    effective_by_view_and_key = {
        (view_id, item.key): item
        for view_id, items in effective_controls.items()
        for item in items
    }
    for key, dependencies in control_dependencies.items():
        if not dependencies:
            continue
        references = option_domains[key]
        if not references:
            raise ValidationFailure(
                  f"Dependent Control {key} has no Base Output option domain",
                details={
                    "code": "control_dependency_option_domain_missing",
                    "control": key,
                    "depends_on": sorted(dependencies),
                },
            )

        # If every candidate Output declares a schema, validate the complete
        # relation now: child fields plus every effective transitive ancestor.
        # A schema-less Output remains runtime-checked because validate does not
        # execute arbitrary queries merely to inspect their rows.
        declared_domains = [
            {column.name for column in output_definitions[reference].schema_}
            for reference in references
            if output_definitions[reference].schema_
        ]
        has_runtime_schema = any(
            not output_definitions[reference].schema_
            for reference in references
        )
        if has_runtime_schema:
            continue
        required_field_sets: list[set[str]] = []
        for view_id, items in effective_controls.items():
            target = next((item for item in items if item.key == key), None)
            if target is None:
                continue
            required = set(_control_value_fields(target))
            for dependency_key in control_ancestors[key]:
                ancestor = effective_by_view_and_key.get((view_id, dependency_key))
                if ancestor is not None:
                    required.update(_control_value_fields(ancestor))
            required_field_sets.append(required)
        if required_field_sets and not all(
            any(fields <= declared for declared in declared_domains)
            for fields in required_field_sets
        ):
            raise ValidationFailure(
                f"Dependent Control {key} option domain does not declare the "
                "fields required by its dependency relation",
                details={
                    "code": "control_dependency_field_unknown",
                    "control": key,
                    "depends_on": sorted(dependencies),
                    "dependency_ancestors": sorted(control_ancestors[key]),
                    "references": sorted(references),
                    "required_field_sets": [
                        sorted(fields) for fields in required_field_sets
                    ],
                    "declared_domains": [
                        sorted(fields) for fields in declared_domains
                    ],
                },
            )

    direct_transform_views: dict[str, set[str]] = {
        identifier: set() for identifier in interactive_dependencies
    }
    output_view_consumers: dict[str, set[str]] = {
        reference: set()
        for reference in query_output_references | interactive_output_references
    }
    for view_id, inputs in view_inputs.items():
        for reference in inputs.values():
            output_view_consumers.setdefault(reference, set()).add(view_id)
            parsed = parse_output_reference(reference)
            if parsed.node_id.startswith("interactive:"):
                direct_transform_views[parsed.node_id.split(":", 1)[1]].add(view_id)

    transform_consumers: dict[str, set[str]] = {
        identifier: set() for identifier in interactive_dependencies
    }
    for identifier, dependencies in interactive_dependencies.items():
        for dependency in dependencies:
            transform_consumers[dependency].add(identifier)

    transform_downstream_views: dict[str, tuple[str, ...]] = {}
    for identifier in interactive_order:
        views: set[str] = set()
        for current in _downstream_closure([identifier], transform_consumers):
            views.update(direct_transform_views[current])
        transform_downstream_views[identifier] = tuple(sorted(views))

    scope_views_by_control: dict[str, set[str]] = {key: set() for key in registry}
    for view_id, items in effective_controls.items():
        for item in items:
            scope_views_by_control[item.key].add(view_id)
    transform_consumers_by_control: dict[str, set[str]] = {
        key: set() for key in registry
    }
    transform_inputs_by_control: dict[str, dict[str, set[str]]] = {
        key: {} for key in registry
    }
    for identifier, bindings in interactive_control_inputs.items():
        available_inputs = set(interactive_inputs[identifier])
        for alias, binding in bindings.items():
            key = binding["control"]
            if key not in registry:
                raise ValidationFailure(
                    f"Interactive Transform {identifier} references unknown Control: {key}",
                    details={
                        "code": "interactive_control_unknown",
                        "transform": identifier,
                        "alias": alias,
                        "control": key,
                    },
                )
            unknown_inputs = sorted(set(binding.get("inputs", ())) - available_inputs)
            if unknown_inputs:
                raise ValidationFailure(
                    f"Interactive Transform {identifier} filter {alias} references "
                    "unknown inputs: " + ", ".join(unknown_inputs),
                    details={
                        "code": "interactive_control_filter_input_unknown",
                        "transform": identifier,
                        "alias": alias,
                        "inputs": unknown_inputs,
                    },
                )
            transform_consumers_by_control[key].add(identifier)
            transform_inputs_by_control[key].setdefault(identifier, set()).add(alias)
    content_fields_by_control: dict[str, set[str]] = {key: set() for key in registry}
    content_views_by_control: dict[str, set[str]] = {key: set() for key in registry}
    repeat_views_by_control: dict[str, set[str]] = {key: set() for key in registry}
    for section in dashboard.definition.sections:
        if not section.repeat or not section.repeat.control:
            continue
        key = f"section:{section.id}/{section.repeat.control}"
        if key not in repeat_views_by_control:
            continue
        view_id = section.repeat.view or (section.views[0] if section.views else None)
        if view_id:
            repeat_views_by_control[key].add(view_id)
    content_contract = content_control_contract(dashboard.definition)
    for field, template in content_template_fields(dashboard.definition):
        inspection = inspect_content_template(template)
        for expression in inspection.controls:
            item = content_contract.get(expression)
            if item is None or item.key not in content_fields_by_control:
                raise ValidationFailure(
                    f"Content references unknown Control: {expression}",
                    details={
                        "code": "content_control_unknown",
                        "field": field,
                        "control": expression,
                    },
                )
            content_fields_by_control[item.key].add(field)
            if field.startswith("views."):
                content_views_by_control[item.key].add(field.split(".", 2)[1])

    controls: dict[str, ControlDependency] = {}
    for key, item in registry.items():
        scope_views = scope_views_by_control[key]
        direct_view_bindings: dict[str, ControlFilterDependency] = {}
        for view_id in sorted(scope_views):
            matches = [
                (alias, binding)
                for alias, binding in view_control_inputs.get(view_id, {}).items()
                if binding.get("mode") == "filter" and binding["control"] == key
            ]
            if len(matches) > 1:
                raise ValidationFailure(
                    f"View {view_id} declares multiple filters for Control {key}",
                    details={
                        "code": "view_control_filter_duplicate",
                        "view": view_id,
                        "control": key,
                        "aliases": [alias for alias, _ in matches],
                    },
                )
            for alias, binding in matches:
                raw_fields = binding["field"]
                fields = tuple(raw_fields if isinstance(raw_fields, list) else [raw_fields])
                input_aliases = tuple(binding["inputs"])
                unknown_inputs = sorted(set(input_aliases) - set(view_inputs.get(view_id, {})))
                if unknown_inputs:
                    raise ValidationFailure(
                        f"View {view_id} filter {alias} references unknown inputs: "
                        + ", ".join(unknown_inputs),
                        details={
                            "code": "view_control_filter_input_unknown",
                            "view": view_id,
                            "alias": alias,
                            "inputs": unknown_inputs,
                        },
                    )
                references = tuple(
                    view_inputs[view_id][input_alias] for input_alias in input_aliases
                )
                table_outputs = [
                    output_definitions[reference]
                    for reference in references
                    if output_definitions[reference].kind == "table"
                ]
                declared = any(
                    all(
                        any(
                            column.name == field and column.required
                            for column in output.schema_
                        )
                        for field in fields
                    )
                    for output in table_outputs
                )
                applicability: Literal[
                    "declared", "runtime", "not_applicable"
                ]
                if declared:
                    applicability = "declared"
                elif table_outputs:
                    applicability = "runtime"
                else:
                    applicability = "not_applicable"
                direct_view_bindings[view_id] = ControlFilterDependency(
                    view_id=view_id,
                    alias=alias,
                    fields=fields,
                    operator=binding.get("operator", "auto"),
                    empty=binding["empty"],
                    input_aliases=input_aliases,
                    input_references=references,
                    applicability=applicability,
                )
        direct_views = {
            view_id
            for view_id, dependency in direct_view_bindings.items()
            if dependency.applicability != "not_applicable"
        }
        declared_direct_views = {
            view_id
            for view_id, dependency in direct_view_bindings.items()
            if dependency.applicability == "declared"
        }
        runtime_checked_views = {
            view_id
            for view_id, dependency in direct_view_bindings.items()
            if dependency.applicability == "runtime"
        }
        non_data_views = {
            view_id
            for view_id, dependency in direct_view_bindings.items()
            if dependency.applicability == "not_applicable"
        }
        derived_views = {
            view_id
            for identifier in transform_consumers_by_control[key]
            for view_id in transform_downstream_views[identifier]
        }
        content_views = content_views_by_control[key]
        controls[key] = ControlDependency(
            key=key,
            origin=item.origin,
            owner_id=item.owner_id,
            scope_views=tuple(sorted(scope_views)),
            direct_views=tuple(sorted(direct_views)),
            declared_direct_views=tuple(sorted(declared_direct_views)),
            runtime_checked_views=tuple(sorted(runtime_checked_views)),
            non_data_views=tuple(sorted(non_data_views)),
            direct_view_bindings=direct_view_bindings,
            writer_view=(
                writer_by_control[key].view_id
                if key in writer_by_control
                else None
            ),
            writer_fields=(
                writer_by_control[key].fields
                if key in writer_by_control
                else ()
            ),
            transform_consumers=tuple(sorted(transform_consumers_by_control[key])),
            transform_inputs={
                transform_id: tuple(sorted(aliases))
                for transform_id, aliases in transform_inputs_by_control[key].items()
            },
            derived_views=tuple(sorted(derived_views)),
            content_fields=tuple(sorted(content_fields_by_control[key])),
            content_views=tuple(sorted(content_views)),
            repeat_views=tuple(sorted(repeat_views_by_control[key])),
            affected_views=tuple(
                sorted(
                    direct_views
                    | derived_views
                    | content_views
                    | repeat_views_by_control[key]
                    | ({writer_by_control[key].view_id} if key in writer_by_control else set())
                )
            ),
            option_domain_references=tuple(sorted(option_domains[key])),
            depends_on=tuple(sorted(control_dependencies[key])),
            dependency_ancestors=tuple(sorted(control_ancestors[key])),
            dependency_descendants=tuple(sorted(control_descendants[key])),
            definition=item.definition.model_dump(mode="json", by_alias=True),
            initial_state=initial_input_state(
                item.definition,
                allow_unresolved_inferred=True,
            ).as_dict(),
        )

    # A compiled contract is executable by construction. Cross-runtime edges and
    # scoped Control consumers are rejected here, rather than being left as a
    # second graph interpretation owned only by ``dataviz validate``.
    for identifier in interactive_order:
        if interactive_runtimes[identifier] == "server-python":
            browser_ancestors = sorted(
                ancestor
                for ancestor in _upstream_closure(
                    interactive_dependencies[identifier],
                    interactive_dependencies,
                )
                if interactive_runtimes[ancestor] == "browser-js"
            )
            if browser_ancestors:
                raise ValidationFailure(
                    "server-python cannot depend on browser Runtime outputs: "
                    + ", ".join(browser_ancestors),
                    details={
                        "code": "server_interactive_depends_on_browser",
                        "transform": identifier,
                        "dependency_chain": browser_ancestors,
                    },
                )
        downstream_views = set(transform_downstream_views[identifier])
        for alias, binding in interactive_control_inputs[identifier].items():
            control_key = binding["control"]
            input_mode = binding["mode"]
            outside_scope = sorted(
                downstream_views - set(controls[control_key].scope_views)
            )
            if outside_scope:
                raise ValidationFailure(
                    f"Control {control_key} is outside downstream View scope: "
                    + ", ".join(outside_scope),
                    details={
                        "code": "interactive_control_out_of_scope",
                        "transform": identifier,
                        "input_mode": input_mode,
                        "alias": alias,
                        "control": control_key,
                        "views": outside_scope,
                    },
                )

    parameter_inputs = {
        **{
            f"source:{identifier}": {
                alias: query_input_contract(binding)
                for alias, binding in getattr(definition, "query_inputs", {}).items()
            }
            for identifier, (_, definition) in dashboard.sources.items()
        },
        **{
            f"dataset:{identifier}": {
                alias: query_input_contract(binding)
                for alias, binding in definition.query_inputs.items()
            }
            for identifier, (_, definition) in dashboard.dataset_transforms.items()
        },
    }
    query_parameter_consumers: dict[str, set[str]] = {
        item.id: set() for item in dashboard.definition.query_parameters
    }
    for identifier, (_, definition) in dashboard.sources.items():
        for binding in getattr(definition, "query_inputs", {}).values():
            key = query_input_parameter(binding)
            query_parameter_consumers.setdefault(key, set()).add(f"source:{identifier}")
    for identifier, (_, definition) in dashboard.dataset_transforms.items():
        for binding in definition.query_inputs.values():
            key = query_input_parameter(binding)
            query_parameter_consumers.setdefault(key, set()).add(f"dataset:{identifier}")
    for identifier, (_, definition) in dashboard.interactive_transforms.items():
        for binding in definition.query_inputs.values():
            key = query_input_parameter(binding)
            query_parameter_consumers.setdefault(key, set()).add(f"interactive:{identifier}")
    for field, template in content_template_fields(dashboard.definition):
        for key in inspect_content_template(template).query_parameters:
            query_parameter_consumers.setdefault(key, set()).add(f"content:{field}")

    declared_query_parameters = {
        item.id for item in dashboard.definition.query_parameters
    }
    unknown_query_parameters = {
        key: sorted(consumers)
        for key, consumers in query_parameter_consumers.items()
        if key not in declared_query_parameters
    }
    if unknown_query_parameters:
        raise ValidationFailure(
            "Dependency graph references undeclared Query Parameters: "
            + ", ".join(sorted(unknown_query_parameters)),
            details={
                "code": "query_parameter_unknown",
                "parameters": unknown_query_parameters,
            },
        )

    query_consumers: dict[str, set[str]] = {
        node_id: set() for node_id in query_dependencies
    }
    for node_id, dependencies in query_dependencies.items():
        for dependency in dependencies:
            query_consumers[dependency].add(node_id)

    query_node_downstream_views: dict[str, tuple[str, ...]] = {}
    query_node_option_controls: dict[str, tuple[str, ...]] = {}
    query_node_affected_nodes: dict[str, set[str]] = {}
    query_node_affected_interactive: dict[str, set[str]] = {}
    for node_id in query_order:
        affected_nodes = _downstream_closure([node_id], query_consumers)
        query_node_affected_nodes[node_id] = affected_nodes
        affected_outputs = {
            reference
            for affected_node in affected_nodes
            for reference in query_outputs[affected_node]
        }
        direct_interactive = {
            identifier
            for identifier, inputs in interactive_inputs.items()
            if affected_outputs.intersection(inputs.values())
        }
        affected_interactive = _downstream_closure(
            direct_interactive,
            transform_consumers,
        )
        query_node_affected_interactive[node_id] = affected_interactive
        views = {
            view_id
            for reference in affected_outputs
            for view_id in output_view_consumers.get(reference, ())
        }
        views.update(
            view_id
            for identifier in affected_interactive
            for view_id in transform_downstream_views[identifier]
        )
        query_node_downstream_views[node_id] = tuple(sorted(views))
        query_node_option_controls[node_id] = tuple(
            sorted(
                key
                for key, references in option_domains.items()
                if affected_outputs.intersection(references)
            )
        )

    query_parameters: dict[str, QueryParameterDependency] = {}
    for key in query_parameter_consumers:
        consumers = query_parameter_consumers[key]
        direct_query = {
            value
            for value in consumers
            if value.startswith(("source:", "dataset:"))
        }
        direct_interactive = {
            value.split(":", 1)[1]
            for value in consumers
            if value.startswith("interactive:")
        }
        content_fields = {
            value.split(":", 1)[1]
            for value in consumers
            if value.startswith("content:")
        }
        affected_query = {
            affected
            for node_id in direct_query
            for affected in query_node_affected_nodes[node_id]
        }
        affected_interactive = set(direct_interactive)
        affected_interactive.update(
            identifier
            for node_id in direct_query
            for identifier in query_node_affected_interactive[node_id]
        )
        affected_interactive = _downstream_closure(
            affected_interactive,
            transform_consumers,
        )
        affected_views = {
            view_id
            for node_id in direct_query
            for view_id in query_node_downstream_views[node_id]
        }
        affected_views.update(
            view_id
            for identifier in affected_interactive
            for view_id in transform_downstream_views[identifier]
        )
        affected_views.update(
            field.split(".", 2)[1]
            for field in content_fields
            if field.startswith("views.") and len(field.split(".", 2)) > 1
        )
        affected_option_controls = {
            control
            for node_id in direct_query
            for control in query_node_option_controls[node_id]
        }
        # A new Query snapshot may change an inferred option universe. Control
        # reconciliation can then change every View/Transform in that Control's
        # compiled impact closure, even when the option-domain Output is not a
        # View input itself.
        affected_views.update(
            view_id
            for control in affected_option_controls
            for view_id in controls[control].affected_views
        )
        query_parameters[key] = QueryParameterDependency(
            key=key,
            direct_query_nodes=tuple(sorted(direct_query)),
            direct_interactive_transforms=tuple(sorted(direct_interactive)),
            content_fields=tuple(sorted(content_fields)),
            affected_query_nodes=tuple(sorted(affected_query)),
            affected_interactive_transforms=tuple(sorted(affected_interactive)),
            affected_option_controls=tuple(sorted(affected_option_controls)),
            affected_views=tuple(sorted(affected_views)),
        )

    return DashboardDependencyContract(
        dashboard_id=dashboard.definition.id,
        parameter_domain_contract=dashboard.parameter_domain_contract.as_dict(),
        query_dependencies={
            key: tuple(sorted(value)) for key, value in query_dependencies.items()
        },
        data_inputs=data_inputs,
        query_outputs=query_outputs,
        query_order=query_order,
        parameter_inputs=parameter_inputs,
        query_parameter_consumers={
            key: tuple(sorted(value))
            for key, value in query_parameter_consumers.items()
        },
        query_parameters=query_parameters,
        query_node_downstream_views=query_node_downstream_views,
        query_node_option_controls=query_node_option_controls,
        presentation_roots=tuple(sorted(set(presentation_roots))),
        base_output_roots=tuple(sorted(base_output_roots)),
        interactive_dependencies={
            key: tuple(sorted(value))
            for key, value in interactive_dependencies.items()
        },
        interactive_inputs=interactive_inputs,
        interactive_outputs=interactive_outputs,
        interactive_runtimes=interactive_runtimes,
        interactive_parameter_inputs=interactive_parameter_inputs,
        interactive_control_inputs=interactive_control_inputs,
        interactive_order=interactive_order,
        reachable_interactive_order=tuple(
            identifier
            for identifier in interactive_order
            if identifier in reachable_interactive
        ),
        transform_direct_views={
            key: tuple(sorted(value)) for key, value in direct_transform_views.items()
        },
        transform_downstream_views=transform_downstream_views,
        view_inputs=view_inputs,
        view_controls=view_controls,
        view_control_contract=view_control_contract,
        view_control_inputs=view_control_inputs,
        view_control_bindings=view_control_bindings,
        output_view_consumers={
            key: tuple(sorted(value))
            for key, value in output_view_consumers.items()
        },
        control_option_domains={
            key: tuple(sorted(value)) for key, value in option_domains.items()
        },
        control_order=control_order,
        controls=controls,
    )
