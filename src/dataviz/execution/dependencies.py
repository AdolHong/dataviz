from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any, Iterable, Literal, TYPE_CHECKING

from dataviz.content_templates import (
    content_control_contract,
    content_template_fields,
    inspect_content_template,
)
from dataviz.errors import ValidationFailure
from dataviz.execution.references import parse_output_reference
from dataviz.execution.control_filter import OPERATORS_BY_VALUE_TYPE
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
from dataviz.protocols import DEPENDENCY_CONTRACT_SCHEMA
from dataviz.workspace.models import (
    InferredOptionDomainDefinition,
    ViewControlBindingDefinition,
    ViewControlWriteDefinition,
)

if TYPE_CHECKING:
    from dataviz.workspace.loader import LoadedDashboard


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
        raise ValidationFailure(f"{label} references unknown dependencies: {', '.join(unknown)}")
    order: list[str] = []
    while pending:
        ready = sorted(node for node, dependencies in pending.items() if not dependencies)
        if not ready:
            raise ValidationFailure(f"{label} contains a cycle: {', '.join(sorted(pending))}")
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

    return tuple(item.definition.path_fields or [item.definition.field or item.id])


def _declared_outputs(kind: str, identifier: str, definition: Any) -> tuple[str, ...]:
    return tuple(f"{kind}:{identifier}/{name}" for name in definition.outputs)


def _require_declared_references(
    references: Iterable[str],
    declared: set[str],
    *,
    label: str,
) -> None:
    canonical = {parse_output_reference(reference).canonical for reference in references}
    unknown = sorted(canonical - declared)
    if unknown:
        raise ValidationFailure(f"{label} references unknown Named Outputs: {', '.join(unknown)}")


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
            raise ValidationFailure(f"Unknown Interactive Transform dependency: {identifier}")
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
            "direct_interactive_transforms": list(self.direct_interactive_transforms),
            "content_fields": list(self.content_fields),
            "affected_query_nodes": list(self.affected_query_nodes),
            "affected_interactive_transforms": list(self.affected_interactive_transforms),
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
class ViewControlWriteDependency:
    control: str
    fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"control": self.control, "fields": list(self.fields)}


@dataclass(frozen=True, slots=True)
class ViewControlBindingDependency:
    view_id: str
    control: str
    fields: tuple[str, ...]
    renderer: str
    source_layer: str | None = None
    role: Literal["primary", "context"] = "primary"
    writes: tuple[ViewControlWriteDependency, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "source_view": self.view_id,
            "control": self.control,
            "fields": list(self.fields),
            "renderer": self.renderer,
            "actions": ["select", "select_many", "clear", "reset"],
        }
        if self.source_layer is not None:
            payload["source_layer"] = self.source_layer
        if self.role != "primary":
            payload["role"] = self.role
        if self.writes:
            payload["writes"] = [write.as_dict() for write in self.writes]
        return payload


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
    writer_edges: tuple[ViewControlBindingDependency, ...]
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
            "writer_edges": [edge.as_dict() for edge in self.writer_edges],
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


def _validate_typed_filter_binding(
    *,
    binding: dict[str, Any],
    definition: Any,
    consumer: str,
    alias: str,
) -> None:
    if binding.get("mode") != "filter":
        return
    raw_fields = binding.get("field")
    fields = raw_fields if isinstance(raw_fields, list) else [raw_fields]
    operator = str(binding.get("operator") or "auto")
    if len(fields) > 1:
        if operator not in {"auto", "in", "equals"}:
            raise ValidationFailure(
                f"Path filter {consumer}.{alias} does not support {operator}",
                details={
                    "code": "control_filter_operator_incompatible",
                    "consumer": consumer,
                    "alias": alias,
                    "operator": operator,
                    "value_type": definition.value_type,
                },
            )
        return
    if operator == "auto":
        if definition.type in {"multiple_input", "multiple_select"}:
            operator = "in"
        elif definition.type == "range_input":
            operator = "between"
        else:
            operator = "equals"
    if operator not in OPERATORS_BY_VALUE_TYPE[definition.value_type]:
        raise ValidationFailure(
            f"Control filter {consumer}.{alias} uses {operator} with {definition.value_type}",
            details={
                "code": "control_filter_operator_incompatible",
                "consumer": consumer,
                "alias": alias,
                "operator": operator,
                "value_type": definition.value_type,
            },
        )


def _validate_filter_schema_type(
    *,
    binding: dict[str, Any],
    definition: Any,
    consumer: str,
    alias: str,
    inputs: dict[str, str],
    output_definitions: dict[str, Any],
) -> None:
    if binding.get("mode") != "filter" or isinstance(binding.get("field"), list):
        return
    field = str(binding["field"])
    compatible_tokens = {
        "text": ("str", "string", "object", "utf8"),
        "integer": ("int", "uint"),
        "number": ("int", "uint", "float", "double", "decimal"),
        "boolean": ("bool",),
        "date": ("date", "datetime", "timestamp"),
    }[definition.value_type]
    for input_alias in binding.get("inputs", ()):
        reference = inputs.get(input_alias)
        output = output_definitions.get(reference or "")
        column = next(
            (item for item in getattr(output, "schema_", ()) if item.name == field and item.dtype),
            None,
        )
        if column is None:
            continue
        dtype = str(column.dtype).casefold()
        if not any(token in dtype for token in compatible_tokens):
            raise ValidationFailure(
                f"Control filter {consumer}.{alias} expects {definition.value_type}, "
                f"but {reference}.{field} declares {column.dtype}",
                details={
                    "code": "control_filter_schema_type_incompatible",
                    "consumer": consumer,
                    "alias": alias,
                    "input": input_alias,
                    "reference": reference,
                    "field": field,
                    "value_type": definition.value_type,
                    "dtype": column.dtype,
                },
            )


def _validate_writer_schema_type(
    *,
    fields: tuple[str, ...],
    definition: Any,
    view_id: str,
    references: tuple[str, ...],
    output_definitions: dict[str, Any],
) -> None:
    compatible_tokens = {
        "text": ("str", "string", "object", "utf8"),
        "integer": ("int", "uint"),
        "number": ("int", "uint", "float", "double", "decimal"),
        "boolean": ("bool",),
        "date": ("date", "datetime", "timestamp"),
    }[definition.value_type]
    for reference in references:
        output = output_definitions.get(reference)
        for field in fields:
            column = next(
                (
                    item
                    for item in getattr(output, "schema_", ())
                    if item.name == field and item.dtype
                ),
                None,
            )
            if column is None:
                continue
            dtype = str(column.dtype).casefold()
            if any(token in dtype for token in compatible_tokens):
                continue
            raise ValidationFailure(
                f"View {view_id} writer expects {definition.value_type}, "
                f"but {reference}.{field} declares {column.dtype}",
                details={
                    "code": "view_control_binding_schema_type_incompatible",
                    "view": view_id,
                    "reference": reference,
                    "field": field,
                    "value_type": definition.value_type,
                    "dtype": column.dtype,
                },
            )


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
    interactive_triggers: dict[str, str]
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
    view_layer_control_bindings: dict[
        str, dict[str, ViewControlBindingDependency]
    ]
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
        return tuple(identifier for identifier in self.interactive_order if identifier in selected)

    def interactive_ancestors(self, target: str) -> set[str]:
        return set(self.interactive_closure(target)) - {target}

    def output_closure(self, references: Iterable[str]) -> tuple[set[str], set[str]]:
        """Resolve presentation references into Interactive nodes and Base Outputs."""

        return _output_dependency_closure(references, self.interactive_inputs)

    def server_interactive_base_references(self) -> set[str]:
        required: set[str] = set()
        for identifier in self.reachable_interactive_order:
            if self.interactive_runtimes[identifier] == "server-python":
                _, base = self.output_closure(self.interactive_inputs[identifier].values())
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

    def control_contract_projection(self) -> dict[str, Any]:
        """Return the compiler-owned checkpoint compatibility boundary.

        Presentation-only text is deliberately excluded: changing a label must
        not invalidate a tab-local Control checkpoint.  Reducer inputs,
        writer/consumer bindings, option domains and trigger policy are all
        included because changing any of them changes how a restored value is
        interpreted or consumed.
        """

        presentation_fields = {
            "description",
            "help",
            "help_text",
            "label",
            "placeholder",
            "presentation",
        }
        controls: dict[str, Any] = {}
        for key in self.control_order:
            dependency = self.controls[key]
            controls[key] = {
                "origin": dependency.origin,
                "owner_id": dependency.owner_id,
                "definition": {
                    field: value
                    for field, value in dependency.definition.items()
                    if field not in presentation_fields
                },
                "initial_state": dependency.initial_state,
                "depends_on": list(dependency.depends_on),
                "option_domain_references": list(dependency.option_domain_references),
                "writer_edges": [edge.as_dict() for edge in dependency.writer_edges],
                "direct_view_bindings": {
                    view_id: binding.as_dict()
                    for view_id, binding in sorted(dependency.direct_view_bindings.items())
                },
                "transform_inputs": {
                    transform_id: list(aliases)
                    for transform_id, aliases in sorted(dependency.transform_inputs.items())
                },
            }
        return {
            "control_order": list(self.control_order),
            "controls": controls,
            "views": {
                view_id: {
                    "control_inputs": dict(self.view_control_inputs.get(view_id, {})),
                    "control_binding": (
                        self.view_control_bindings[view_id].as_dict()
                        if view_id in self.view_control_bindings
                        else None
                    ),
                    "layer_control_bindings": {
                        layer_id: binding.as_dict()
                        for layer_id, binding in sorted(
                            self.view_layer_control_bindings.get(view_id, {}).items()
                        )
                    },
                }
                for view_id in sorted(self.view_inputs)
                if (
                    self.view_control_inputs.get(view_id)
                    or view_id in self.view_control_bindings
                    or view_id in self.view_layer_control_bindings
                )
            },
            "transforms": {
                identifier: {
                    "trigger": self.interactive_triggers[identifier],
                    "control_inputs": dict(self.interactive_control_inputs.get(identifier, {})),
                }
                for identifier in self.reachable_interactive_order
                if self.interactive_control_inputs.get(identifier)
            },
        }

    @property
    def control_contract_hash(self) -> str:
        payload = json.dumps(
            self.control_contract_projection(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def runtime_manifest(self) -> dict[str, Any]:
        reachable = set(self.reachable_interactive_order)
        output_views = {
            reference: list(views)
            for reference, views in self.output_view_consumers.items()
            if views
        }
        return {
            "schema": DEPENDENCY_CONTRACT_SCHEMA,
            "control_contract_hash": self.control_contract_hash,
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
                    "layer_control_bindings": {
                        layer_id: binding.as_dict()
                        for layer_id, binding in sorted(
                            self.view_layer_control_bindings.get(view_id, {}).items()
                        )
                    },
                }
                for view_id, inputs in self.view_inputs.items()
            },
            "outputs": {reference: {"views": views} for reference, views in output_views.items()},
            "controls": {key: dependency.as_dict() for key, dependency in self.controls.items()},
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
                "outputs": {key: list(value) for key, value in self.query_outputs.items()},
                "order": list(self.query_order),
                "parameter_inputs": self.parameter_inputs,
                "parameter_consumers": {
                    key: list(value) for key, value in self.query_parameter_consumers.items()
                },
                "parameters": {
                    key: value.as_dict() for key, value in self.query_parameters.items()
                },
                "downstream_views": {
                    key: list(value) for key, value in self.query_node_downstream_views.items()
                },
                "option_controls": {
                    key: list(value) for key, value in self.query_node_option_controls.items()
                },
                "presentation_roots": list(self.presentation_roots),
                "base_output_roots": list(self.base_output_roots),
            },
            "interactive": {
                "dependencies": {
                    key: list(value) for key, value in self.interactive_dependencies.items()
                },
                "inputs": self.interactive_inputs,
                "outputs": {key: list(value) for key, value in self.interactive_outputs.items()},
                "runtimes": dict(self.interactive_runtimes),
                "triggers": dict(self.interactive_triggers),
                "parameter_inputs": self.interactive_parameter_inputs,
                "control_inputs": self.interactive_control_inputs,
                "order": list(self.interactive_order),
                "reachable_order": list(self.reachable_interactive_order),
                "direct_views": {
                    key: list(value) for key, value in self.transform_direct_views.items()
                },
                "downstream_views": {
                    key: list(value) for key, value in self.transform_downstream_views.items()
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
                    "layer_control_bindings": {
                        layer_id: binding.as_dict()
                        for layer_id, binding in sorted(
                            self.view_layer_control_bindings.get(key, {}).items()
                        )
                    },
                }
                for key, value in self.view_inputs.items()
            },
            "outputs": {
                key: {"views": list(value)} for key, value in self.output_view_consumers.items()
            },
            "control_option_domains": {
                key: list(value) for key, value in self.control_option_domains.items()
            },
            "controls": {key: value.as_dict() for key, value in self.controls.items()},
            "control_order": list(self.control_order),
            "control_contract_hash": self.control_contract_hash,
        }


def _compile_query_graph(
    dashboard: LoadedDashboard,
) -> tuple[
    dict[str, set[str]],
    dict[str, dict[str, str]],
    dict[str, tuple[str, ...]],
    tuple[str, ...],
    set[str],
]:
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
            parse_output_reference(reference).node_id for reference in data_inputs[node_id].values()
        }
        query_outputs[node_id] = _declared_outputs("dataset", identifier, definition)
    query_order = _topological_order(query_dependencies, label="Query DAG")
    query_output_references = {
        reference for references in query_outputs.values() for reference in references
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
    return (
        query_dependencies,
        data_inputs,
        query_outputs,
        query_order,
        query_output_references,
    )


def _compile_interactive_graph(
    dashboard: LoadedDashboard,
    query_output_references: set[str],
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, set[str]],
    tuple[str, ...],
    dict[str, tuple[str, ...]],
    set[str],
]:
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
            for parsed in (parse_output_reference(reference) for reference in inputs.values())
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
        reference for references in interactive_outputs.values() for reference in references
    }
    _require_declared_references(
        (reference for inputs in interactive_inputs.values() for reference in inputs.values()),
        query_output_references | interactive_output_references,
        label="Interactive DAG",
    )
    return (
        interactive_inputs,
        interactive_dependencies,
        interactive_order,
        interactive_outputs,
        interactive_output_references,
    )


def _compile_interactive_bindings(
    dashboard: LoadedDashboard,
) -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, dict[str, dict[str, Any]]],
    dict[str, dict[str, dict[str, Any]]],
]:
    interactive_runtimes = {
        identifier: definition.runtime
        for identifier, (_, definition) in dashboard.interactive_transforms.items()
    }
    interactive_triggers = {
        identifier: definition.trigger
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
    return (
        interactive_runtimes,
        interactive_triggers,
        interactive_parameter_inputs,
        interactive_control_inputs,
    )


def _compile_output_definitions(dashboard: LoadedDashboard) -> dict[str, Any]:
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
    return output_definitions


def _compile_view_inputs(dashboard: LoadedDashboard) -> dict[str, dict[str, str]]:
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
            view_inputs[view_id] = {"main": parse_output_reference(section.repeat.input).canonical}
    return view_inputs


def _compile_view_control_inputs(
    dashboard: LoadedDashboard,
    *,
    section_for_view: dict[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
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


def _compile_effective_control_views(
    dashboard: LoadedDashboard,
) -> tuple[
    dict[str, tuple[EffectiveControl, ...]],
    dict[str, tuple[str, ...]],
]:
    effective_controls = compile_control_contract(dashboard.definition)
    return (
        {view_id: tuple(items) for view_id, items in effective_controls.items()},
        {
            view_id: tuple(item.key for item in items)
            for view_id, items in effective_controls.items()
        },
    )


def _validate_view_control_inputs(
    *,
    registry: dict[str, EffectiveControl],
    view_control_inputs: dict[str, dict[str, dict[str, Any]]],
    view_controls: dict[str, tuple[str, ...]],
    view_inputs: dict[str, dict[str, str]],
    output_definitions: dict[str, Any],
) -> None:
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
            _validate_typed_filter_binding(
                binding=binding,
                definition=registry[control_key].definition,
                consumer=f"view:{view_id}",
                alias=alias,
            )
            _validate_filter_schema_type(
                binding=binding,
                definition=registry[control_key].definition,
                consumer=f"view:{view_id}",
                alias=alias,
                inputs=view_inputs.get(view_id, {}),
                output_definitions=output_definitions,
            )


def _compile_writer_edges(
    dashboard: LoadedDashboard,
    *,
    registry: dict[str, EffectiveControl],
    section_for_view: dict[str, Any],
    view_control_inputs: dict[str, dict[str, dict[str, Any]]],
    view_controls: dict[str, tuple[str, ...]],
    view_inputs: dict[str, dict[str, str]],
    output_definitions: dict[str, Any],
    writer_views: Iterable[Any] | None = None,
) -> tuple[
    dict[str, ViewControlBindingDependency],
    dict[str, list[ViewControlBindingDependency]],
]:
    view_control_bindings: dict[str, ViewControlBindingDependency] = {}
    writers_by_control: dict[str, list[ViewControlBindingDependency]] = {
        key: [] for key in registry
    }
    scope_rank = {"dashboard": 0, "section": 1, "view": 2}
    chart_templates = {
        "line",
        "bar",
        "stacked-bar",
        "pie",
        "scatter",
        "heatmap",
        "radar",
        "map",
    }
    views_by_id = {
        view.id: view
        for view in (
            writer_views if writer_views is not None else dashboard.definition.views
        )
    }
    for view_id, view in views_by_id.items():
        raw_binding = view.control_binding
        if raw_binding is None:
            continue
        binding = (
            ViewControlBindingDefinition(control=raw_binding)
            if isinstance(raw_binding, str)
            else raw_binding
        )
        value_fields = (
            [view.z]
            if view.template == "heatmap"
            else (list(view.y) if isinstance(view.y, list) else [view.y or view.value or view.z])
        )
        value_fields = [field for field in value_fields if field]
        group_fields = [
            field
            for field in (
                [view.x, view.y]
                if view.template == "heatmap"
                else [view.x or view.label, view.series]
            )
            if isinstance(field, str) and field
        ]
        operation = (
            "none"
            if view.template == "metric"
            else (
                view.aggregate
                or ("none" if view.template in {"scatter", "map", "table", "perspective"} else "sum")
            )
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
        targets: list[tuple[ViewControlWriteDefinition, Literal["primary", "context"]]] = [
            (
                ViewControlWriteDefinition(control=binding.control, field=binding.field),
                "primary",
            ),
            *((write, "context") for write in binding.writes),
        ]
        compiled_targets: list[
            tuple[str, tuple[str, ...], Literal["primary", "context"]]
        ] = []
        seen_controls: set[str] = set()
        for target_binding, role in targets:
            control_key = _resolve_control_reference(
                target_binding.control,
                dashboard_id=dashboard.definition.id,
                view_id=view_id,
                section_for_view=section_for_view,
            )
            target = registry.get(control_key)
            if target is None:
                raise ValidationFailure(
                    f"View {view_id} binds unknown Control: {target_binding.control}",
                    details={
                        "code": "view_control_binding_unknown",
                        "view": view_id,
                        "control": target_binding.control,
                        "resolved_key": control_key,
                        "role": role,
                    },
                )
            if control_key in seen_controls:
                raise ValidationFailure(
                    f"View {view_id} writes Control {control_key} more than once",
                    details={
                        "code": "view_control_binding_duplicate_target",
                        "view": view_id,
                        "control": control_key,
                    },
                )
            seen_controls.add(control_key)
            if control_key not in view_controls.get(view_id, ()):
                raise ValidationFailure(
                    f"Control {control_key} is outside View {view_id} scope",
                    details={
                        "code": "view_control_binding_out_of_scope",
                        "view": view_id,
                        "control": control_key,
                        "role": role,
                    },
                )
            narrower = sorted(
                item["control"]
                for item in view_control_inputs.get(view_id, {}).values()
                if item.get("mode") == "filter"
                and item["control"] != control_key
                and scope_rank[registry[item["control"]].origin] > scope_rank[target.origin]
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
                        "role": role,
                    },
                )
            fields = tuple(
                [target_binding.field]
                if target_binding.field
                else _control_value_fields(target)
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
                        "role": role,
                    },
                )
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
                        "role": role,
                    },
                )
            _validate_writer_schema_type(
                fields=fields,
                definition=target.definition,
                view_id=view_id,
                references=references,
                output_definitions=output_definitions,
            )
            compiled_targets.append((control_key, fields, role))

        primary_control, primary_fields, _ = compiled_targets[0]
        writes = tuple(
            ViewControlWriteDependency(control=control, fields=fields)
            for control, fields, role in compiled_targets
            if role == "context"
        )
        compiled_binding = ViewControlBindingDependency(
            view_id=view_id,
            control=primary_control,
            fields=primary_fields,
            renderer=renderer,
            writes=writes,
        )
        view_control_bindings[view_id] = compiled_binding
        writers_by_control[primary_control].append(compiled_binding)
        for write in writes:
            writers_by_control[write.control].append(
                ViewControlBindingDependency(
                    view_id=view_id,
                    control=write.control,
                    fields=write.fields,
                    renderer=renderer,
                    role="context",
                )
            )
    return view_control_bindings, writers_by_control


def _compile_map_layer_writer_edges(
    dashboard: LoadedDashboard,
    *,
    registry: dict[str, EffectiveControl],
    section_for_view: dict[str, Any],
    view_control_inputs: dict[str, dict[str, dict[str, Any]]],
    view_controls: dict[str, tuple[str, ...]],
    view_inputs: dict[str, dict[str, str]],
    output_definitions: dict[str, Any],
) -> tuple[
    dict[str, dict[str, ViewControlBindingDependency]],
    dict[str, list[ViewControlBindingDependency]],
]:
    """Compile layer writers through the same canonical View writer rules."""

    bindings: dict[str, dict[str, ViewControlBindingDependency]] = {}
    writers: dict[str, list[ViewControlBindingDependency]] = {
        key: [] for key in registry
    }
    for view in dashboard.definition.views:
        if view.template != "map" or not view.layers:
            continue
        for layer in view.layers:
            if layer.control_binding is None:
                continue
            synthetic = view.model_copy(
                update={
                    "input": layer.input,
                    "inputs": {},
                    "layers": [],
                    "mark": layer.mark,
                    "longitude": layer.longitude,
                    "latitude": layer.latitude,
                    "geojson": layer.geojson,
                    "data_key": layer.data_key,
                    "feature_key": layer.feature_key,
                    "label": layer.label,
                    "color": layer.color,
                    "size": layer.size,
                    "control_binding": layer.control_binding,
                }
            )
            local_bindings, local_writers = _compile_writer_edges(
                dashboard,
                registry=registry,
                section_for_view=section_for_view,
                view_control_inputs=view_control_inputs,
                view_controls=view_controls,
                view_inputs={view.id: {"main": view_inputs[view.id][layer.id]}},
                output_definitions=output_definitions,
                writer_views=[synthetic],
            )
            compiled = replace(
                local_bindings[view.id], source_layer=layer.id
            )
            bindings.setdefault(view.id, {})[layer.id] = compiled
            for control, edges in local_writers.items():
                writers[control].extend(
                    replace(edge, source_layer=layer.id) for edge in edges
                )
    return bindings, writers


def _compile_presentation_roots(
    dashboard: LoadedDashboard,
    *,
    registry: dict[str, EffectiveControl],
    view_inputs: dict[str, dict[str, str]],
    interactive_inputs: dict[str, dict[str, str]],
    output_definitions: dict[str, Any],
    declared_outputs: set[str],
) -> tuple[dict[str, set[str]], list[str], set[str], set[str]]:
    option_domains: dict[str, set[str]] = {key: set() for key in registry}
    explicit_option_roots: list[str] = []
    for key, item in registry.items():
        options = item.definition.options
        if isinstance(options, InferredOptionDomainDefinition) and options.source:
            reference = parse_output_reference(options.source).canonical
            option_domains[key].add(reference)
            explicit_option_roots.append(reference)

    presentation_roots = [
        reference for inputs in view_inputs.values() for reference in inputs.values()
    ]
    presentation_roots.extend(
        parse_output_reference(reference).canonical
        for reference in dashboard.definition.canvas.inputs
    )
    presentation_roots.extend(explicit_option_roots)
    _require_declared_references(
        presentation_roots,
        declared_outputs,
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
    return (
        option_domains,
        presentation_roots,
        reachable_interactive,
        base_output_roots,
    )


def _complete_option_domains(
    *,
    option_domains: dict[str, set[str]],
    view_control_contract: dict[str, tuple[EffectiveControl, ...]],
    view_inputs: dict[str, dict[str, str]],
    interactive_inputs: dict[str, dict[str, str]],
    control_dependencies: dict[str, set[str]],
    control_ancestors: dict[str, set[str]],
    output_definitions: dict[str, Any],
) -> dict[str, set[str]]:
    completed = {key: set(references) for key, references in option_domains.items()}
    for view_id, items in view_control_contract.items():
        _, inferred = _output_dependency_closure(
            view_inputs.get(view_id, {}).values(),
            interactive_inputs,
        )
        for item in items:
            options = item.definition.options
            dynamic_domain = (
                isinstance(options, InferredOptionDomainDefinition) and not options.source
            )
            dependent_static_domain = (
                options is not None
                and not isinstance(options, InferredOptionDomainDefinition)
                and bool(control_dependencies[item.key])
            )
            if dynamic_domain or dependent_static_domain:
                completed[item.key].update(inferred)

    effective_by_view_and_key = {
        (view_id, item.key): item
        for view_id, items in view_control_contract.items()
        for item in items
    }
    for key, dependencies in control_dependencies.items():
        if not dependencies:
            continue
        references = completed[key]
        if not references:
            raise ValidationFailure(
                f"Dependent Control {key} has no Base Output option domain",
                details={
                    "code": "control_dependency_option_domain_missing",
                    "control": key,
                    "depends_on": sorted(dependencies),
                },
            )

        declared_domains = [
            {column.name for column in output_definitions[reference].schema_}
            for reference in references
            if output_definitions[reference].schema_
        ]
        has_runtime_schema = any(
            not output_definitions[reference].schema_ for reference in references
        )
        if has_runtime_schema:
            continue
        required_field_sets: list[set[str]] = []
        for view_id, items in view_control_contract.items():
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
                    "required_field_sets": [sorted(fields) for fields in required_field_sets],
                    "declared_domains": [sorted(fields) for fields in declared_domains],
                },
            )
    return completed


def _compile_reverse_indexes(
    *,
    interactive_dependencies: dict[str, set[str]],
    interactive_order: tuple[str, ...],
    declared_outputs: set[str],
    view_inputs: dict[str, dict[str, str]],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, tuple[str, ...]],
]:
    direct_transform_views: dict[str, set[str]] = {
        identifier: set() for identifier in interactive_dependencies
    }
    output_view_consumers: dict[str, set[str]] = {
        reference: set() for reference in declared_outputs
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
    return (
        direct_transform_views,
        output_view_consumers,
        transform_consumers,
        transform_downstream_views,
    )


def _compile_control_impacts(
    dashboard: LoadedDashboard,
    *,
    registry: dict[str, EffectiveControl],
    view_control_contract: dict[str, tuple[EffectiveControl, ...]],
    view_control_inputs: dict[str, dict[str, dict[str, Any]]],
    view_inputs: dict[str, dict[str, str]],
    interactive_inputs: dict[str, dict[str, str]],
    interactive_control_inputs: dict[str, dict[str, dict[str, Any]]],
    output_definitions: dict[str, Any],
    writers_by_control: dict[str, list[ViewControlBindingDependency]],
    option_domains: dict[str, set[str]],
    control_dependencies: dict[str, set[str]],
    control_ancestors: dict[str, set[str]],
    control_descendants: dict[str, set[str]],
    transform_downstream_views: dict[str, tuple[str, ...]],
) -> dict[str, ControlDependency]:
    scope_views_by_control: dict[str, set[str]] = {key: set() for key in registry}
    for view_id, items in view_control_contract.items():
        for item in items:
            scope_views_by_control[item.key].add(view_id)
    transform_consumers_by_control: dict[str, set[str]] = {key: set() for key in registry}
    transform_inputs_by_control: dict[str, dict[str, set[str]]] = {key: {} for key in registry}
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
            _validate_typed_filter_binding(
                binding=binding,
                definition=registry[key].definition,
                consumer=f"interactive:{identifier}",
                alias=alias,
            )
            _validate_filter_schema_type(
                binding=binding,
                definition=registry[key].definition,
                consumer=f"interactive:{identifier}",
                alias=alias,
                inputs=interactive_inputs[identifier],
                output_definitions=output_definitions,
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
                        any(column.name == field and column.required for column in output.schema_)
                        for field in fields
                    )
                    for output in table_outputs
                )
                applicability: Literal["declared", "runtime", "not_applicable"]
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
            writer_edges=tuple(writers_by_control[key]),
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
                    | {edge.view_id for edge in writers_by_control[key]}
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
    return controls


def _validate_execution_edges(
    *,
    interactive_order: tuple[str, ...],
    interactive_runtimes: dict[str, str],
    interactive_dependencies: dict[str, set[str]],
    transform_downstream_views: dict[str, tuple[str, ...]],
    interactive_control_inputs: dict[str, dict[str, dict[str, Any]]],
    controls: dict[str, ControlDependency],
) -> None:
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
            outside_scope = sorted(downstream_views - set(controls[control_key].scope_views))
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


def _compile_query_parameter_impacts(
    dashboard: LoadedDashboard,
    *,
    query_dependencies: dict[str, set[str]],
    query_outputs: dict[str, tuple[str, ...]],
    query_order: tuple[str, ...],
    interactive_inputs: dict[str, dict[str, str]],
    transform_consumers: dict[str, set[str]],
    transform_downstream_views: dict[str, tuple[str, ...]],
    output_view_consumers: dict[str, set[str]],
    option_domains: dict[str, set[str]],
    controls: dict[str, ControlDependency],
) -> tuple[
    dict[str, dict[str, dict[str, Any]]],
    dict[str, set[str]],
    dict[str, QueryParameterDependency],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
]:
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
        for query_filter in getattr(definition, "query_filters", {}).values():
            query_parameter_consumers.setdefault(
                query_filter.parameter, set()
            ).add(f"source:{identifier}")
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

    declared_query_parameters = {item.id for item in dashboard.definition.query_parameters}
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

    query_consumers: dict[str, set[str]] = {node_id: set() for node_id in query_dependencies}
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
    for key, consumers in query_parameter_consumers.items():
        direct_query = {value for value in consumers if value.startswith(("source:", "dataset:"))}
        direct_interactive = {
            value.split(":", 1)[1] for value in consumers if value.startswith("interactive:")
        }
        content_fields = {
            value.split(":", 1)[1] for value in consumers if value.startswith("content:")
        }
        affected_query = {
            affected for node_id in direct_query for affected in query_node_affected_nodes[node_id]
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
            view_id for node_id in direct_query for view_id in query_node_downstream_views[node_id]
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
            control for node_id in direct_query for control in query_node_option_controls[node_id]
        }
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
    return (
        parameter_inputs,
        query_parameter_consumers,
        query_parameters,
        query_node_downstream_views,
        query_node_option_controls,
    )


def compile_dashboard_dependencies(
    dashboard: LoadedDashboard,
) -> DashboardDependencyContract:
    (
        query_dependencies,
        data_inputs,
        query_outputs,
        query_order,
        query_output_references,
    ) = _compile_query_graph(dashboard)
    (
        interactive_inputs,
        interactive_dependencies,
        interactive_order,
        interactive_outputs,
        interactive_output_references,
    ) = _compile_interactive_graph(dashboard, query_output_references)
    (
        interactive_runtimes,
        interactive_triggers,
        interactive_parameter_inputs,
        interactive_control_inputs,
    ) = _compile_interactive_bindings(dashboard)
    output_definitions = _compile_output_definitions(dashboard)
    view_inputs = _compile_view_inputs(dashboard)

    registry = scoped_control_registry(dashboard.definition)
    section_for_view = {
        view_id: section for section in dashboard.definition.sections for view_id in section.views
    }
    view_control_inputs = _compile_view_control_inputs(
        dashboard,
        section_for_view=section_for_view,
    )
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
    view_control_contract, view_controls = _compile_effective_control_views(dashboard)
    _validate_view_control_inputs(
        registry=registry,
        view_control_inputs=view_control_inputs,
        view_controls=view_controls,
        view_inputs=view_inputs,
        output_definitions=output_definitions,
    )
    (
        option_domains,
        presentation_roots,
        reachable_interactive,
        base_output_roots,
    ) = _compile_presentation_roots(
        dashboard,
        registry=registry,
        view_inputs=view_inputs,
        interactive_inputs=interactive_inputs,
        output_definitions=output_definitions,
        declared_outputs=query_output_references | interactive_output_references,
    )
    view_control_bindings, writers_by_control = _compile_writer_edges(
        dashboard,
        registry=registry,
        section_for_view=section_for_view,
        view_control_inputs=view_control_inputs,
        view_controls=view_controls,
        view_inputs=view_inputs,
        output_definitions=output_definitions,
    )
    view_layer_control_bindings, layer_writers_by_control = (
        _compile_map_layer_writer_edges(
            dashboard,
            registry=registry,
            section_for_view=section_for_view,
            view_control_inputs=view_control_inputs,
            view_controls=view_controls,
            view_inputs=view_inputs,
            output_definitions=output_definitions,
        )
    )
    for control, edges in layer_writers_by_control.items():
        writers_by_control[control].extend(edges)
    option_domains = _complete_option_domains(
        option_domains=option_domains,
        view_control_contract=view_control_contract,
        view_inputs=view_inputs,
        interactive_inputs=interactive_inputs,
        control_dependencies=control_dependencies,
        control_ancestors=control_ancestors,
        output_definitions=output_definitions,
    )

    (
        direct_transform_views,
        output_view_consumers,
        transform_consumers,
        transform_downstream_views,
    ) = _compile_reverse_indexes(
        interactive_dependencies=interactive_dependencies,
        interactive_order=interactive_order,
        declared_outputs=query_output_references | interactive_output_references,
        view_inputs=view_inputs,
    )

    controls = _compile_control_impacts(
        dashboard,
        registry=registry,
        view_control_contract=view_control_contract,
        view_control_inputs=view_control_inputs,
        view_inputs=view_inputs,
        interactive_inputs=interactive_inputs,
        interactive_control_inputs=interactive_control_inputs,
        output_definitions=output_definitions,
        writers_by_control=writers_by_control,
        option_domains=option_domains,
        control_dependencies=control_dependencies,
        control_ancestors=control_ancestors,
        control_descendants=control_descendants,
        transform_downstream_views=transform_downstream_views,
    )

    _validate_execution_edges(
        interactive_order=interactive_order,
        interactive_runtimes=interactive_runtimes,
        interactive_dependencies=interactive_dependencies,
        transform_downstream_views=transform_downstream_views,
        interactive_control_inputs=interactive_control_inputs,
        controls=controls,
    )

    (
        parameter_inputs,
        query_parameter_consumers,
        query_parameters,
        query_node_downstream_views,
        query_node_option_controls,
    ) = _compile_query_parameter_impacts(
        dashboard,
        query_dependencies=query_dependencies,
        query_outputs=query_outputs,
        query_order=query_order,
        interactive_inputs=interactive_inputs,
        transform_consumers=transform_consumers,
        transform_downstream_views=transform_downstream_views,
        output_view_consumers=output_view_consumers,
        option_domains=option_domains,
        controls=controls,
    )

    return DashboardDependencyContract(
        dashboard_id=dashboard.definition.id,
        parameter_domain_contract=dashboard.parameter_domain_contract.as_dict(),
        query_dependencies={key: tuple(sorted(value)) for key, value in query_dependencies.items()},
        data_inputs=data_inputs,
        query_outputs=query_outputs,
        query_order=query_order,
        parameter_inputs=parameter_inputs,
        query_parameter_consumers={
            key: tuple(sorted(value)) for key, value in query_parameter_consumers.items()
        },
        query_parameters=query_parameters,
        query_node_downstream_views=query_node_downstream_views,
        query_node_option_controls=query_node_option_controls,
        presentation_roots=tuple(sorted(set(presentation_roots))),
        base_output_roots=tuple(sorted(base_output_roots)),
        interactive_dependencies={
            key: tuple(sorted(value)) for key, value in interactive_dependencies.items()
        },
        interactive_inputs=interactive_inputs,
        interactive_outputs=interactive_outputs,
        interactive_runtimes=interactive_runtimes,
        interactive_triggers=interactive_triggers,
        interactive_parameter_inputs=interactive_parameter_inputs,
        interactive_control_inputs=interactive_control_inputs,
        interactive_order=interactive_order,
        reachable_interactive_order=tuple(
            identifier for identifier in interactive_order if identifier in reachable_interactive
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
        view_layer_control_bindings=view_layer_control_bindings,
        output_view_consumers={
            key: tuple(sorted(value)) for key, value in output_view_consumers.items()
        },
        control_option_domains={key: tuple(sorted(value)) for key, value in option_domains.items()},
        control_order=control_order,
        controls=controls,
    )
