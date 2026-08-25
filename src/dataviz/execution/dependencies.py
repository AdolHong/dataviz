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
from dataviz.workspace.controls import (
    EffectiveControl,
    compile_control_contract,
    scoped_control_registry,
)
from dataviz.workspace.models import InferredOptionDomainDefinition

if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard


DEPENDENCY_CONTRACT_SCHEMA = "dataviz/dependency-contract/v1"


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
class SelectionViewDependency:
    view_id: str
    fields: tuple[str, ...]
    operator: str
    input_references: tuple[str, ...]
    applicability: Literal["declared", "runtime", "not_applicable"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fields": list(self.fields),
            "operator": self.operator,
            "input_references": list(self.input_references),
            "applicability": self.applicability,
        }


@dataclass(frozen=True, slots=True)
class ControlDependency:
    key: str
    kind: str
    origin: str
    owner_id: str
    scope_views: tuple[str, ...]
    direct_views: tuple[str, ...]
    declared_direct_views: tuple[str, ...]
    runtime_checked_views: tuple[str, ...]
    non_data_views: tuple[str, ...]
    direct_view_bindings: dict[str, SelectionViewDependency]
    transform_consumers: tuple[str, ...]
    transform_inputs: dict[str, tuple[str, ...]]
    derived_views: tuple[str, ...]
    content_fields: tuple[str, ...]
    content_views: tuple[str, ...]
    affected_views: tuple[str, ...]
    option_domain_references: tuple[str, ...]
    cascade_upstream: tuple[str, ...]
    cascade_downstream: tuple[str, ...]
    definition: dict[str, Any]
    binding: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
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
            "transform_consumers": list(self.transform_consumers),
            "transform_inputs": {
                transform_id: list(aliases)
                for transform_id, aliases in self.transform_inputs.items()
            },
            "derived_views": list(self.derived_views),
            "content_fields": list(self.content_fields),
            "content_views": list(self.content_views),
            "affected_views": list(self.affected_views),
            "option_domain_references": list(self.option_domain_references),
            "cascade_upstream": list(self.cascade_upstream),
            "cascade_downstream": list(self.cascade_downstream),
            "definition": self.definition,
            "binding": self.binding,
        }


@dataclass(frozen=True, slots=True)
class DashboardDependencyContract:
    dashboard_id: str
    query_dependencies: dict[str, tuple[str, ...]]
    query_inputs: dict[str, dict[str, str]]
    query_outputs: dict[str, tuple[str, ...]]
    query_order: tuple[str, ...]
    query_parameter_inputs: dict[str, tuple[str, ...]]
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
    interactive_query_parameters: dict[str, tuple[str, ...]]
    interactive_selection_inputs: dict[str, dict[str, str]]
    interactive_compute_inputs: dict[str, dict[str, str]]
    interactive_order: tuple[str, ...]
    reachable_interactive_order: tuple[str, ...]
    transform_direct_views: dict[str, tuple[str, ...]]
    transform_downstream_views: dict[str, tuple[str, ...]]
    view_inputs: dict[str, dict[str, str]]
    view_controls: dict[str, tuple[str, ...]]
    view_control_contract: dict[str, tuple[EffectiveControl, ...]]
    output_view_consumers: dict[str, tuple[str, ...]]
    selection_option_domains: dict[str, tuple[str, ...]]
    control_order: tuple[str, ...]
    controls: dict[str, ControlDependency]

    def view_selection_contract(self, view_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            item.as_dict()
            for item in self.view_control_contract.get(view_id, ())
            if item.kind == "selection"
        )

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
                "selection_option_domains",
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
                "query_parameters": {
                    identifier: list(self.interactive_query_parameters[identifier])
                    for identifier in self.reachable_interactive_order
                },
                "selection_inputs": {
                    identifier: dict(self.interactive_selection_inputs[identifier])
                    for identifier in self.reachable_interactive_order
                },
                "compute_inputs": {
                    identifier: dict(self.interactive_compute_inputs[identifier])
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
                    "controls": list(self.view_controls.get(view_id, ())),
                    "selection_contract": list(
                        self.view_selection_contract(view_id)
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
                "dependencies": {
                    key: list(value) for key, value in self.query_dependencies.items()
                },
                "inputs": self.query_inputs,
                "outputs": {
                    key: list(value) for key, value in self.query_outputs.items()
                },
                "order": list(self.query_order),
                "parameter_inputs": {
                    key: list(value)
                    for key, value in self.query_parameter_inputs.items()
                },
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
                "query_parameters": {
                    key: list(value)
                    for key, value in self.interactive_query_parameters.items()
                },
                "selection_inputs": self.interactive_selection_inputs,
                "compute_inputs": self.interactive_compute_inputs,
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
                    "controls": list(self.view_controls.get(key, ())),
                }
                for key, value in self.view_inputs.items()
            },
            "outputs": {
                key: {"views": list(value)}
                for key, value in self.output_view_consumers.items()
            },
            "selection_option_domains": {
                key: list(value)
                for key, value in self.selection_option_domains.items()
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
    query_inputs: dict[str, dict[str, str]] = {}
    query_outputs: dict[str, tuple[str, ...]] = {}
    for identifier, (_, definition) in dashboard.sources.items():
        node_id = f"source:{identifier}"
        query_dependencies[node_id] = set()
        query_inputs[node_id] = {}
        query_outputs[node_id] = _declared_outputs("source", identifier, definition)
    for identifier, (_, definition) in dashboard.dataset_transforms.items():
        node_id = f"dataset:{identifier}"
        query_inputs[node_id] = {
            alias: parse_output_reference(reference).canonical
            for alias, reference in definition.inputs.items()
        }
        query_dependencies[node_id] = {
            parse_output_reference(reference).node_id
            for reference in query_inputs[node_id].values()
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
    interactive_query_parameters = {
        identifier: tuple(definition.query_params)
        for identifier, (_, definition) in dashboard.interactive_transforms.items()
    }
    interactive_selection_inputs = {
        identifier: dict(definition.selection_inputs)
        for identifier, (_, definition) in dashboard.interactive_transforms.items()
    }
    interactive_compute_inputs = {
        identifier: dict(definition.compute_inputs)
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
                    f"Selection {key} option domain must use an immutable Base Output",
                    details={
                        "code": "selection_option_domain_invalid",
                        "control": key,
                        "reference": reference,
                    },
                )
            if output_definitions[reference].kind != "table":
                raise ValidationFailure(
                    f"Selection {key} option domain must reference a table Output",
                    details={
                        "code": "selection_option_domain_kind",
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
    for view_id, items in effective_controls.items():
        _, inferred = _output_dependency_closure(
            view_inputs.get(view_id, {}).values(),
            interactive_inputs,
        )
        for item in items:
            options = item.definition.options
            if item.kind != "selection":
                continue
            dynamic_domain = (
                isinstance(options, InferredOptionDomainDefinition)
                and not options.source
            )
            cascading_static_domain = (
                options is not None
                and not isinstance(options, InferredOptionDomainDefinition)
                and item.definition.cascade
            )
            if dynamic_domain or cascading_static_domain:
                option_domains[item.key].update(inferred)

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
    for identifier, (_, definition) in dashboard.interactive_transforms.items():
        for kind, inputs in (
            ("selection", definition.selection_inputs),
            ("compute", definition.compute_inputs),
        ):
            for alias, key in inputs.items():
                item = registry.get(key)
                if item is None:
                    raise ValidationFailure(
                        f"Interactive Transform {identifier} references unknown "
                        f"Control: {key}"
                    )
                if item.kind != kind:
                    raise ValidationFailure(
                        f"Interactive Transform {identifier} uses {key} as {kind}, "
                        f"but it is {item.kind}"
                    )
                transform_consumers_by_control[key].add(identifier)
                transform_inputs_by_control[key].setdefault(identifier, set()).add(
                    alias
                )
    content_fields_by_control: dict[str, set[str]] = {key: set() for key in registry}
    content_views_by_control: dict[str, set[str]] = {key: set() for key in registry}
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

    selection_rank = {"dashboard": 0, "section": 1, "view": 2}
    cascade_upstream: dict[str, set[str]] = {key: set() for key in registry}
    for items in effective_controls.values():
        selections = [item for item in items if item.kind == "selection"]
        for target in selections:
            if not target.definition.cascade or target.definition.type not in {
                "single_select",
                "multi_select",
            }:
                continue
            target_rank = selection_rank[target.origin]
            cascade_upstream[target.key].update(
                candidate.key
                for candidate in selections
                if selection_rank[candidate.origin] < target_rank
            )
    cascade_downstream: dict[str, set[str]] = {key: set() for key in registry}
    for key, upstream in cascade_upstream.items():
        for parent in upstream:
            cascade_downstream[parent].add(key)

    controls: dict[str, ControlDependency] = {}
    for key, item in registry.items():
        scope_views = scope_views_by_control[key]
        direct_view_bindings: dict[str, SelectionViewDependency] = {}
        if item.kind == "selection":
            for view_id in sorted(scope_views):
                effective = next(
                    control
                    for control in view_control_contract[view_id]
                    if control.key == key
                )
                fields = tuple(
                    effective.definition.path_fields
                    or [
                        effective.binding.field
                        if effective.binding and effective.binding.field
                        else effective.id
                    ]
                )
                references = tuple(sorted(view_inputs.get(view_id, {}).values()))
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
                direct_view_bindings[view_id] = SelectionViewDependency(
                    view_id=view_id,
                    fields=fields,
                    operator=(
                        effective.binding.operator
                        if effective.binding is not None
                        else "auto"
                    ),
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
            kind=item.kind,
            origin=item.origin,
            owner_id=item.owner_id,
            scope_views=tuple(sorted(scope_views)),
            direct_views=tuple(sorted(direct_views)),
            declared_direct_views=tuple(sorted(declared_direct_views)),
            runtime_checked_views=tuple(sorted(runtime_checked_views)),
            non_data_views=tuple(sorted(non_data_views)),
            direct_view_bindings=direct_view_bindings,
            transform_consumers=tuple(sorted(transform_consumers_by_control[key])),
            transform_inputs={
                transform_id: tuple(sorted(aliases))
                for transform_id, aliases in transform_inputs_by_control[key].items()
            },
            derived_views=tuple(sorted(derived_views)),
            content_fields=tuple(sorted(content_fields_by_control[key])),
            content_views=tuple(sorted(content_views)),
            affected_views=tuple(
                sorted(direct_views | derived_views | content_views)
            ),
            option_domain_references=tuple(sorted(option_domains[key])),
            cascade_upstream=tuple(sorted(cascade_upstream[key])),
            cascade_downstream=tuple(sorted(cascade_downstream[key])),
            definition=item.definition.model_dump(mode="json", by_alias=True),
            binding=(
                item.binding.model_dump(mode="json")
                if item.binding is not None
                else None
            ),
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
                if interactive_runtimes[ancestor]
                in {"browser-js", "browser-python"}
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
        for kind, inputs in (
            ("selection", interactive_selection_inputs[identifier]),
            ("compute", interactive_compute_inputs[identifier]),
        ):
            for alias, control_key in inputs.items():
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
                            "input_kind": kind,
                            "alias": alias,
                            "control": control_key,
                            "views": outside_scope,
                        },
                    )

    query_parameter_inputs = {
        **{
            f"source:{identifier}": tuple(getattr(definition, "query_params", []))
            for identifier, (_, definition) in dashboard.sources.items()
        },
        **{
            f"dataset:{identifier}": tuple(definition.query_params)
            for identifier, (_, definition) in dashboard.dataset_transforms.items()
        },
    }
    query_parameter_consumers: dict[str, set[str]] = {
        item.id: set() for item in dashboard.definition.query_parameters
    }
    for identifier, (_, definition) in dashboard.sources.items():
        for key in getattr(definition, "query_params", []):
            query_parameter_consumers.setdefault(key, set()).add(f"source:{identifier}")
    for identifier, (_, definition) in dashboard.dataset_transforms.items():
        for key in definition.query_params:
            query_parameter_consumers.setdefault(key, set()).add(f"dataset:{identifier}")
    for identifier, (_, definition) in dashboard.interactive_transforms.items():
        for key in definition.query_params:
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
        query_dependencies={
            key: tuple(sorted(value)) for key, value in query_dependencies.items()
        },
        query_inputs=query_inputs,
        query_outputs=query_outputs,
        query_order=query_order,
        query_parameter_inputs=query_parameter_inputs,
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
        interactive_query_parameters=interactive_query_parameters,
        interactive_selection_inputs=interactive_selection_inputs,
        interactive_compute_inputs=interactive_compute_inputs,
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
        output_view_consumers={
            key: tuple(sorted(value))
            for key, value in output_view_consumers.items()
        },
        selection_option_domains={
            key: tuple(sorted(value)) for key, value in option_domains.items()
        },
        control_order=_topological_order(
            {
                key: set(cascade_upstream[key])
                for key in registry
            },
            label="Control DAG",
        ),
        controls=controls,
    )
