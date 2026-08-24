from __future__ import annotations

from collections.abc import Iterable

from dataviz.errors import ValidationFailure
from dataviz.execution.references import parse_output_reference
from dataviz.workspace.controls import compile_control_contract, scoped_control_registry


def _base_dependencies(
    dashboard,
    references: Iterable[str],
    *,
    trail: tuple[str, ...] = (),
) -> set[str]:
    """Resolve presentation references to immutable Query-stage Named Outputs.

    Dynamic Selection options must exist before an Interactive Transform can run.
    Walking through Interactive inputs establishes that acyclic bootstrap boundary
    without coupling the option list to a filtered Derived Output.
    """

    result: set[str] = set()
    for value in references:
        reference = parse_output_reference(value)
        if not reference.node_id.startswith("interactive:"):
            result.add(reference.canonical)
            continue
        transform_id = reference.node_id.split(":", 1)[1]
        if transform_id in trail:
            cycle = " -> ".join((*trail, transform_id))
            raise ValidationFailure(
                f"Interactive Transform dependency graph contains a cycle: {cycle}"
            )
        transform = dashboard.interactive_transforms.get(transform_id)
        if transform is None:
            # Reference validation reports the unknown node with file/field context.
            continue
        result.update(
            _base_dependencies(
                dashboard,
                transform[1].inputs.values(),
                trail=(*trail, transform_id),
            )
        )
    return result


def selection_option_domain_references(dashboard) -> dict[str, list[str]]:
    """Compile one deterministic Base Output domain for every Selection Control.

    ``options_from`` is an explicit override. Otherwise each Control inherits the
    union of immutable Base Outputs behind the Views where it is visible. Runtime
    field checks discard unrelated tables, so multi-input Views remain supported.
    """

    registry = scoped_control_registry(dashboard.definition, kind="selection")
    domains: dict[str, set[str]] = {key: set() for key in registry}
    explicit = {
        key
        for key, item in registry.items()
        if item.definition.options_from
    }
    for key in explicit:
        domains[key].add(
            parse_output_reference(registry[key].definition.options_from).canonical
        )

    views = {view.id: view for view in dashboard.definition.views}
    for view_id, controls in compile_control_contract(dashboard.definition).items():
        view = views.get(view_id)
        if view is None:
            continue
        inferred = _base_dependencies(dashboard, view.input_refs.values())
        for item in controls:
            if item.kind == "selection" and item.key not in explicit:
                domains[item.key].update(inferred)
    return {key: sorted(references) for key, references in domains.items()}


def explicit_selection_option_references(dashboard) -> set[str]:
    """Return explicit option-domain roots that must join the Query reachability set."""

    return {
        parse_output_reference(item.definition.options_from).canonical
        for item in scoped_control_registry(
            dashboard.definition,
            kind="selection",
        ).values()
        if item.definition.options_from
    }
