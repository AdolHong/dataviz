from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import yaml

from dataviz.errors import ValidationFailure
from dataviz.identifiers import is_stable_id, stable_id_help
from dataviz.execution.plan import compile_plan
from dataviz.templates import (
    COMPONENT_REGISTRY_VERSION,
    SECTION_TEMPLATES,
    VIEW_TEMPLATES,
    component_catalog,
    template_catalog,
)
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace
from dataviz.workspace.control_components import resolve_control_component


RUNTIME_CONTRACT = [
    "Adapter",
    "Source",
    "Dataset Transform",
    "Base Named Output",
    "Interactive Transform",
    "Derived Named Output",
    "View Renderer",
    "Presentation",
]


@dataclass(frozen=True, slots=True)
class ContextFocus:
    kind: str
    identifier: str

    @property
    def canonical(self) -> str:
        return f"{self.kind}:{self.identifier}"


def parse_context_focus(value: str | None) -> ContextFocus | None:
    if value is None:
        return None
    raw = value.strip()
    kind, separator, identifier = raw.partition(":")
    if not separator or not identifier:
        raise ValidationFailure(
            "Context focus must use <kind>:<id>",
            details={
                "examples": [
                    "view:revenue-trend",
                    "section:overview",
                    "source:sales",
                    "dataset:sales-model",
                    "interactive:visible-sales",
                    "component:control.cascader",
                ]
            },
        )
    if kind not in {
        "view",
        "section",
        "source",
        "dataset",
        "interactive",
        "component",
    }:
        raise ValidationFailure(f"Unsupported context focus kind: {kind}")
    return ContextFocus(kind, identifier)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _code_content(definition_path: Path, relative: str | None) -> str | None:
    if not relative:
        return None
    path = (definition_path.parent / relative).resolve()
    if not path.exists() or path.is_dir():
        return None
    if path.stat().st_size > 500_000:
        return f"<omitted: {path.stat().st_size} bytes>"
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "<binary file>"


def _dependency_content(definition_path: Path, dependencies: list[str]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for relative in dependencies:
        path = (definition_path.parent / relative).resolve()
        if path.is_dir():
            for child in sorted(value for value in path.rglob("*") if value.is_file()):
                child_relative = str(child.relative_to(definition_path.parent))
                result[child_relative] = _code_content(definition_path, child_relative)
        else:
            result[relative] = _code_content(definition_path, relative)
    return result


def _data_file_metadata(definition_path: Path, relative: str | None) -> dict[str, Any] | None:
    if not relative:
        return None
    path = (definition_path.parent / relative).resolve()
    if not path.is_file():
        return {"path": relative, "exists": False}
    return {"path": relative, "exists": True, "bytes": path.stat().st_size}


def _source_payload(workspace: LoadedWorkspace, path: Path, definition: Any) -> dict[str, Any]:
    return {
        "definition": definition.model_dump(mode="json", by_alias=True),
        "file": _relative(path, workspace.root),
        # File datasets are intentionally not copied into AI context. Their path and
        # byte size are enough to locate them; query/Python code remains reviewable.
        "code": _code_content(path, getattr(definition, "code", None)),
        "data_file": _data_file_metadata(path, getattr(definition, "path", None)),
        "code_dependencies": _dependency_content(
            path, getattr(definition, "code_dependencies", [])
        ),
    }


def _dataset_transform_payload(
    workspace: LoadedWorkspace, path: Path, definition: Any
) -> dict[str, Any]:
    return {
        "definition": definition.model_dump(mode="json", by_alias=True),
        "file": _relative(path, workspace.root),
        "code": _code_content(path, definition.code),
        "code_dependencies": _dependency_content(path, definition.code_dependencies),
    }


def _interactive_transform_payload(
    workspace: LoadedWorkspace, path: Path, definition: Any
) -> dict[str, Any]:
    return {
        "definition": definition.model_dump(mode="json", by_alias=True),
        "file": _relative(path, workspace.root),
        "code": _code_content(path, definition.code),
    }


def _presentation_assets(
    workspace: LoadedWorkspace, dashboard: LoadedDashboard
) -> dict[str, dict[str, Any]]:
    paths: set[str] = set()
    if dashboard.presentation:
        paths.update(dashboard.presentation.assets.css)
        paths.update(dashboard.presentation.assets.js)
    canvas = dashboard.definition.canvas
    paths.update(value for value in [canvas.template] if value)
    paths.update(canvas.styles)
    paths.update(canvas.scripts)
    result: dict[str, dict[str, Any]] = {}
    for relative in sorted(paths):
        path = (dashboard.root / relative).resolve()
        result[relative] = {
            "file": _relative(path, workspace.root),
            "content": _code_content(dashboard.definition_path, relative),
        }
    return result


def _focused_ids(
    dashboard: LoadedDashboard, focus: ContextFocus, dependency_contract
) -> tuple[set[str], set[str], set[str], set[str], set[str]]:
    view_ids: set[str] = set()
    section_ids: set[str] = set()
    references: list[str] = []

    if focus.kind == "view":
        if focus.identifier not in dashboard.views:
            raise ValidationFailure(f"Unknown View: {focus.identifier}")
        view_ids.add(focus.identifier)
    elif focus.kind == "section":
        section = next(
            (value for value in dashboard.definition.sections if value.id == focus.identifier), None
        )
        if section is None:
            raise ValidationFailure(f"Unknown Section: {focus.identifier}")
        section_ids.add(section.id)
        view_ids.update(section.views)
        if section.repeat and section.repeat.view:
            view_ids.add(section.repeat.view)
    elif focus.kind in {"source", "dataset", "interactive"}:
        collection = {
            "source": dashboard.sources,
            "dataset": dashboard.dataset_transforms,
            "interactive": dashboard.interactive_transforms,
        }[focus.kind]
        if focus.identifier not in collection:
            raise ValidationFailure(f"Unknown {focus.kind.title()}: {focus.identifier}")
        outputs = (
            dependency_contract.interactive_outputs[focus.identifier]
            if focus.kind == "interactive"
            else dependency_contract.query_outputs[
                f"{focus.kind}:{focus.identifier}"
            ]
        )
        references.extend(outputs)

    for section in dashboard.definition.sections:
        if any(view_id in section.views for view_id in view_ids):
            section_ids.add(section.id)
    for view_id in view_ids:
        references.extend(dependency_contract.view_inputs[view_id].values())

    interactive_ids, base_references = dependency_contract.output_closure(references)
    source_ids: set[str] = set()
    transform_ids: set[str] = set()
    if base_references:
        plan = compile_plan(dashboard, targets=sorted(base_references))
        for node_id in plan.nodes:
            kind, identifier = node_id.split(":", 1)
            (source_ids if kind == "source" else transform_ids).add(identifier)
    return view_ids, section_ids, source_ids, transform_ids, interactive_ids


def _focused_presentation(
    dashboard: LoadedDashboard,
    view_ids: set[str],
    section_ids: set[str],
    control_keys: set[str],
) -> dict[str, Any] | None:
    if dashboard.presentation is None:
        return None
    value = dashboard.presentation.model_dump(mode="json", by_alias=True)
    value["views"] = {
        key: definition
        for key, definition in value["views"].items()
        if key in view_ids
    }
    value["sections"] = {
        key: definition
        for key, definition in value["sections"].items()
        if key in section_ids
    }
    value["control_components"] = {
        key: definition
        for key, definition in value["control_components"].items()
        if key in control_keys
    }
    return value


def _focused_templates(
    dashboard: LoadedDashboard,
    view_ids: set[str],
    section_ids: set[str],
    control_keys: set[str],
    *,
    include_dataset_transform: bool,
    interactive_runtimes: set[str],
) -> dict[str, Any]:
    catalog = template_catalog()
    view_templates = {dashboard.views[value].template for value in view_ids}
    section_templates = {
        section.template
        for section in dashboard.definition.sections
        if section.id in section_ids
    }
    definitions = {
        f"query:{item.id}": item for item in dashboard.definition.query_parameters
    }
    for effective in dashboard.dependency_contract.view_control_contract.values():
        for item in effective:
            definitions.setdefault(item.key, item.definition)
    control_components = {
        resolve_control_component(
            definition,
            dashboard.presentation.control_components.get(key)
            if dashboard.presentation
            else None,
        )["component"]
        for key, definition in definitions.items()
        if key in control_keys
    }
    component_ids = {f"view.{value}" for value in view_templates}
    component_ids.update(f"section.{value}" for value in section_templates)
    component_ids.update(f"control.{value}" for value in control_components)
    component_ids.add(f"layout.{dashboard.definition.layout.template}")
    component_ids.add(f"theme.{dashboard.definition.theme.preset}")
    if any(dashboard.views[value].template == "custom" for value in view_ids):
        component_ids.add("renderer.custom")
    if include_dataset_transform:
        component_ids.update({"dataset-transform.server-python", "output.named"})
    for runtime in interactive_runtimes:
        component_ids.update({f"interactive-transform.{runtime}", "output.named"})
    components = component_catalog()
    return {
        "component_registry_version": COMPONENT_REGISTRY_VERSION,
        "views": {
            key: value for key, value in catalog["views"].items() if key in view_templates
        },
        "sections": {
            key: value
            for key, value in catalog["sections"].items()
            if key in section_templates
        },
        "layout": {
            dashboard.definition.layout.template: catalog["layouts"][
                dashboard.definition.layout.template
            ]
        },
        "theme": {
            dashboard.definition.theme.preset: catalog["themes"][
                dashboard.definition.theme.preset
            ]
        },
        "components": {
            key: components[key] for key in sorted(component_ids) if key in components
        },
        "extension_path": catalog["extension_path"],
    }


def _dependency_context_payload(
    contract,
    *,
    focused: bool,
    source_ids: set[str],
    dataset_ids: set[str],
    interactive_ids: set[str],
    view_ids: set[str],
    control_keys: set[str],
) -> dict[str, Any]:
    """Project the authoritative graph without making focused AI context global."""

    payload = contract.as_dict()
    if not focused:
        return payload
    query_nodes = {
        *(f"source:{identifier}" for identifier in source_ids),
        *(f"dataset:{identifier}" for identifier in dataset_ids),
    }
    producers = query_nodes | {
        f"interactive:{identifier}" for identifier in interactive_ids
    }

    def selected_reference(reference: str) -> bool:
        return reference.rsplit("/", 1)[0] in producers

    query = payload["query"]
    query["dependencies"] = {
        key: [value for value in values if value in query_nodes]
        for key, values in query["dependencies"].items()
        if key in query_nodes
    }
    query["data_inputs"] = {
        key: value
        for key, value in query["data_inputs"].items()
        if key in query_nodes
    }
    query["outputs"] = {
        key: values
        for key, values in query["outputs"].items()
        if key in query_nodes
    }
    query["order"] = [value for value in query["order"] if value in query_nodes]
    query["parameter_inputs"] = {
        key: value
        for key, value in query["parameter_inputs"].items()
        if key in query_nodes
    }
    query["parameter_consumers"] = {
        key: [
            value
            for value in values
            if value in producers or value.startswith("content:")
        ]
        for key, values in query["parameter_consumers"].items()
        if any(
            value in producers or value.startswith("content:")
            for value in values
        )
    }
    query["presentation_roots"] = [
        value for value in query["presentation_roots"] if selected_reference(value)
    ]
    query["base_output_roots"] = [
        value for value in query["base_output_roots"] if selected_reference(value)
    ]

    interactive = payload["interactive"]
    for field in (
        "dependencies",
        "inputs",
        "outputs",
        "runtimes",
        "parameter_inputs",
        "control_inputs",
        "direct_views",
        "downstream_views",
    ):
        interactive[field] = {
            key: value
            for key, value in interactive[field].items()
            if key in interactive_ids
        }
    interactive["order"] = [
        value for value in interactive["order"] if value in interactive_ids
    ]
    interactive["reachable_order"] = [
        value for value in interactive["reachable_order"] if value in interactive_ids
    ]
    payload["views"] = {
        key: value for key, value in payload["views"].items() if key in view_ids
    }
    payload["outputs"] = {
        key: value
        for key, value in payload["outputs"].items()
        if selected_reference(key)
        or any(view_id in view_ids for view_id in value["views"])
    }
    payload["control_option_domains"] = {
        key: value
        for key, value in payload["control_option_domains"].items()
        if key in control_keys
    }
    payload["controls"] = {
        key: value
        for key, value in payload["controls"].items()
        if key in control_keys
    }
    payload["control_order"] = [
        key for key in payload["control_order"] if key in control_keys
    ]
    return payload


def build_context_payload(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
    *,
    focus: str | None = None,
) -> dict[str, Any]:
    """Build a complete or dependency-sliced, secret-free authoring context."""
    parsed_focus = parse_context_focus(focus)
    if parsed_focus and parsed_focus.kind == "component":
        definition = component_catalog().get(parsed_focus.identifier)
        if definition is None:
            raise ValidationFailure(f"Unknown Component: {parsed_focus.identifier}")
        return {
            "schema": "dataviz/context/v1",
            "mode": "focused",
            "focus": parsed_focus.canonical,
            "runtime_contract": RUNTIME_CONTRACT,
            "component": definition,
            "next": [
                "dataviz scaffold " + parsed_focus.identifier,
                "dataviz components gallery",
            ],
        }

    dependency_contract = dashboard.dependency_contract
    contract = dependency_contract.view_control_contract
    if parsed_focus is None:
        view_ids = set(dashboard.views)
        section_ids = {value.id for value in dashboard.definition.sections}
        source_ids = set(dashboard.sources)
        transform_ids = set(dashboard.dataset_transforms)
        interactive_ids = set(dashboard.interactive_transforms)
    else:
        view_ids, section_ids, source_ids, transform_ids, interactive_ids = _focused_ids(
            dashboard,
            parsed_focus,
            dependency_contract,
        )

    effective_contract = {
        view_id: [value.as_dict() for value in contract.get(view_id, [])]
        for view_id in sorted(view_ids)
    }
    control_keys = {
        value["key"] for controls in effective_contract.values() for value in controls
    }
    relevant_params = {
        binding["parameter"]
        for identifier in source_ids
        for binding in dependency_contract.parameter_inputs[
            f"source:{identifier}"
        ].values()
    }
    relevant_params.update(
        binding["parameter"]
        for identifier in transform_ids
        for binding in dependency_contract.parameter_inputs[
            f"dataset:{identifier}"
        ].values()
    )
    relevant_params.update(
        binding["parameter"]
        for identifier in interactive_ids
        for binding in dependency_contract.interactive_parameter_inputs[identifier].values()
    )
    control_keys.update(
        key
        for identifier in interactive_ids
        for key in {
            binding["control"]
            for binding in dependency_contract.interactive_control_inputs[
                identifier
            ].values()
        }
    )
    control_keys.update(f"query:{parameter}" for parameter in relevant_params)

    if parsed_focus is None:
        logic_definition: dict[str, Any] = dashboard.logic_definition.model_dump(
            mode="json", by_alias=True
        )
        effective_definition: dict[str, Any] = dashboard.definition.model_dump(
            mode="json", by_alias=True
        )
        presentation = (
            dashboard.presentation.model_dump(mode="json", by_alias=True)
            if dashboard.presentation
            else None
        )
        templates = template_catalog()
    else:
        logic_views = {value.id: value for value in dashboard.logic_definition.views}
        logic_sections = {value.id: value for value in dashboard.logic_definition.sections}
        logic_definition = {
            "schema": dashboard.logic_definition.schema_,
            "kind": dashboard.logic_definition.kind,
            "id": dashboard.logic_definition.id,
            "title": dashboard.logic_definition.title,
            "subtitle": dashboard.logic_definition.subtitle,
            "description": dashboard.logic_definition.description,
            "context": dashboard.logic_definition.context,
            "assumptions": dashboard.logic_definition.assumptions,
            "adapters": {
                key: value
                for key, value in dashboard.logic_definition.adapters.items()
                if any(
                    dashboard.sources[source_id][1].adapter == key
                    for source_id in source_ids
                )
            },
            "query_parameters": [
                value.model_dump(mode="json")
                for value in dashboard.logic_definition.query_parameters
                if value.id in relevant_params
            ],
            "controls": [
                value.model_dump(mode="json")
                for value in dashboard.logic_definition.controls
                if f"dashboard:{dashboard.definition.id}/{value.id}" in control_keys
            ],
            "sections": [
                logic_sections[value].model_dump(mode="json")
                for value in sorted(section_ids)
                if value in logic_sections
            ],
            "views": [
                logic_views[value].model_dump(mode="json")
                for value in sorted(view_ids)
                if value in logic_views
            ],
        }
        effective_definition = {
            **logic_definition,
            "layout": dashboard.definition.layout.model_dump(mode="json"),
            "theme": dashboard.definition.theme.model_dump(mode="json"),
            "views": [
                dashboard.views[value].model_dump(mode="json") for value in sorted(view_ids)
            ],
        }
        presentation = _focused_presentation(
            dashboard, view_ids, section_ids, control_keys
        )
        templates = _focused_templates(
            dashboard,
            view_ids,
            section_ids,
            control_keys,
            include_dataset_transform=bool(transform_ids),
            interactive_runtimes={
                dashboard.interactive_transforms[value][1].runtime
                for value in interactive_ids
            },
        )

    return {
        "schema": "dataviz/context/v1",
        "mode": "full" if parsed_focus is None else "focused",
        "focus": parsed_focus.canonical if parsed_focus else None,
        "workspace": workspace.definition.model_dump(mode="json", by_alias=True),
        "workspace_readme": workspace.readme if parsed_focus is None else None,
        "canvas_name": dashboard.canvas_name,
        "content_title": dashboard.title,
        "dashboard_logic": logic_definition,
        "dashboard": effective_definition,
        "presentation": presentation,
        "presentation_file": (
            _relative(dashboard.presentation_path, workspace.root)
            if dashboard.presentation_path
            else None
        ),
        "presentation_diagnostics": [
            diagnostic.as_dict() for diagnostic in (dashboard.presentation_diagnostics or [])
        ],
        "presentation_assets": _presentation_assets(workspace, dashboard),
        "dashboard_readme": dashboard.readme,
        "templates": templates,
        "runtime_contract": RUNTIME_CONTRACT,
        "effective_controls": effective_contract,
        "dependency_contract": _dependency_context_payload(
            dependency_contract,
            focused=parsed_focus is not None,
            source_ids=source_ids,
            dataset_ids=transform_ids,
            interactive_ids=interactive_ids,
            view_ids=view_ids,
            control_keys=control_keys,
        ),
        "layout_contract": dashboard.layout_contract.as_dict(),
        "sources": {
            key: _source_payload(workspace, *dashboard.sources[key])
            for key in sorted(source_ids)
        },
        "dataset_transforms": {
            key: _dataset_transform_payload(
                workspace, *dashboard.dataset_transforms[key]
            )
            for key in sorted(transform_ids)
        },
        "interactive_transforms": {
            key: _interactive_transform_payload(
                workspace, *dashboard.interactive_transforms[key]
            )
            for key in sorted(interactive_ids)
        },
        "views": {
            key: dashboard.views[key].model_dump(mode="json") for key in sorted(view_ids)
        },
    }


def _yaml(value: Any) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).rstrip() + "\n"


def _scaffold_output(title: str, purpose: str, grain: str) -> dict[str, Any]:
    return {
        "kind": "table",
        "semantics": {
            "visibility": "public",
            "title": title,
            "purpose": purpose,
            "grain": grain,
            "caveats": [],
        },
    }


SCAFFOLD_PROFILES = ("minimal", "interactive", "custom-renderer")


def scaffold_recipes() -> tuple[str, ...]:
    """Return every recipe accepted by the current generator."""
    controls = sorted(
        identifier
        for identifier in component_catalog()
        if identifier.startswith("control.")
    )
    return (
        *SCAFFOLD_PROFILES,
        "dashboard",
        "source.file",
        "source.sql",
        "source.python",
        "dataset-transform.server-python",
        "interactive-transform.browser-js",
        "interactive-transform.server-python",
        "renderer.custom",
        *(f"view.{value}" for value in VIEW_TEMPLATES),
        *(f"section.{value}" for value in SECTION_TEMPLATES),
        *controls,
    )


def _scaffold_route(recipe: str) -> str:
    if recipe in SCAFFOLD_PROFILES:
        return recipe
    if recipe.startswith("control.") or recipe.startswith("interactive-transform."):
        return "interactive"
    if recipe in {"renderer.custom", "view.custom"}:
        return "custom-renderer"
    if recipe == "section.selection-gallery":
        return "interactive"
    return "minimal"


def scaffold_catalog() -> dict[str, Any]:
    """Describe profile and fragment recipes without requiring prose parsing."""
    return {
        "schema": "dataviz/scaffold-catalog/v2",
        "default": "minimal",
        "profiles": list(SCAFFOLD_PROFILES),
        "recipes": [
            {
                "id": recipe,
                "route": _scaffold_route(recipe),
                "scope": "workspace" if recipe in SCAFFOLD_PROFILES else "fragment",
            }
            for recipe in scaffold_recipes()
        ],
    }


def _profile_files(profile: str, item_id: str) -> dict[str, str]:
    dashboard_root = f"dashboards/{item_id}"
    workspace = {
        "schema": "dataviz/workspace/v1",
        "kind": "workspace",
        "id": f"{item_id}-workspace",
        "title": item_id.replace("-", " ").title(),
        # Profiles use tiny fixture data and must remain independently visual-checkable
        # without downloading the Apache Arrow browser bundle.
        "runtime": {"browser_table_transport": "json"},
    }
    dashboard: dict[str, Any] = {
        "schema": "dataviz/dashboard/v13",
        "kind": "dashboard",
        "id": item_id,
        "title": item_id.replace("-", " ").title(),
        "sources": [
            {
                "id": "data",
                "type": "file",
                "path": "data/data.csv",
                "format": "csv",
                "outputs": {
                    "main": _scaffold_output(
                        "Sample rows",
                        "Provide the reusable input rows for this Dashboard.",
                        "One row per category.",
                    )
                },
            }
        ],
    }
    files = {
        "workspace.yaml": _yaml(workspace),
        f"{dashboard_root}/data/data.csv": "category,value\nAlpha,12\nBeta,19\n",
    }

    if profile == "minimal":
        dashboard.update(
            {
                "views": [
                    {
                        "id": "overview",
                        "title": "Overview",
                        "template": "table",
                        "input": "source:data/main",
                    }
                ],
                "sections": [
                    {"id": "main", "title": "Main", "views": ["overview"]}
                ],
            }
        )
    elif profile == "interactive":
        dashboard.update(
            {
                "controls": [
                    {
                        "id": "factor",
                        "label": "Factor",
                        "type": "single_input",
                        "value_type": "number",
                        "default": 2,
                    }
                ],
                "interactive_transforms": ["transforms/scaled.yaml"],
                "views": [
                    {
                        "id": "scaled",
                        "title": "Scaled values",
                        "template": "table",
                        "input": "interactive:scaled/main",
                        "columns": ["category", "value"],
                    }
                ],
                "sections": [
                    {"id": "main", "title": "Main", "views": ["scaled"]}
                ],
            }
        )
        files[f"{dashboard_root}/transforms/scaled.yaml"] = _yaml(
            {
                "schema": "dataviz/interactive-transform/v4",
                "kind": "interactive_transform",
                "id": "scaled",
                "runtime": "browser-js",
                "code": "scaled.js",
                "inputs": {"rows": "source:data/main"},
                "control_inputs": {"factor": f"dashboard:{item_id}/factor"},
                "trigger": "auto",
                "export": {"mode": "interactive"},
                "outputs": {
                    "main": _scaffold_output(
                        "Scaled rows",
                        "Compare category values after applying the selected factor.",
                        "One row per category.",
                    )
                },
            }
        )
        files[f"{dashboard_root}/transforms/scaled.js"] = (
            "function transform(context) {\n"
            "  const factor = Number(context.control_inputs.factor ?? 1);\n"
            "  return {main: context.inputs.rows.map(row => ({\n"
            "    ...row, value: Number(row.value) * factor,\n"
            "  }))};\n"
            "}\n"
        )
    elif profile == "custom-renderer":
        renderer_id = f"{item_id}.renderer"
        dashboard.update(
            {
                "views": [
                    {
                        "id": "custom-view",
                        "title": "Custom renderer",
                        "template": "custom",
                        "renderer": renderer_id,
                        "input": "source:data/main",
                    }
                ],
                "sections": [
                    {"id": "main", "title": "Main", "views": ["custom-view"]}
                ],
            }
        )
        files[f"{dashboard_root}/presentation.yaml"] = _yaml(
            {
                "schema": "dataviz/presentation/v2",
                "kind": "presentation",
                "dashboard": item_id,
                "assets": {
                    "css": ["assets/renderer.css"],
                    "js": ["assets/renderer.js"],
                },
            }
        )
        files[f"{dashboard_root}/assets/renderer.js"] = (
            f"window.datavizRuntime.registerRenderer({json.dumps(renderer_id)}, {{\n"
            "  validate(_descriptor) {},\n"
            "  mount(context, descriptor) {\n"
            "    const node = document.createElement('pre');\n"
            "    node.className = 'profile-custom-renderer';\n"
            "    context.body.append(node);\n"
            "    this.update(context, descriptor, {node});\n"
            "    return {node};\n"
            "  },\n"
            "  update(_context, descriptor, state) {\n"
            "    state.node.textContent = JSON.stringify(descriptor.rows || [], null, 2);\n"
            "    return state;\n"
            "  },\n"
            "  dispose(_context, state) { state.node.remove(); },\n"
            "});\n"
        )
        files[f"{dashboard_root}/assets/renderer.css"] = (
            ".profile-custom-renderer { margin: 0; min-height: 12rem; white-space: pre-wrap; }\n"
        )
    else:  # pragma: no cover - caller limits this helper to known profiles.
        raise ValidationFailure(f"Unknown scaffold profile: {profile}")

    files[f"{dashboard_root}/dashboard.yaml"] = _yaml(dashboard)
    return files


def scaffold_recipe(name: str, identifier: str) -> dict[str, Any]:
    """Return a copyable, deterministic recipe without mutating a Workspace."""
    recipe = name.strip()
    item_id = identifier.strip()
    if not is_stable_id(item_id):
        raise ValidationFailure(stable_id_help("Scaffold id"))

    if recipe in SCAFFOLD_PROFILES:
        files = _profile_files(recipe, item_id)
    elif recipe == "dashboard":
        files = {
            "dashboard.yaml": _yaml(
                {
                    "schema": "dataviz/dashboard/v13",
                    "kind": "dashboard",
                    "id": item_id,
                    "title": item_id.replace("-", " ").title(),
                    "description": "A minimal declarative Dashboard.",
                    "sources": [
                        {
                            "id": "data",
                            "kind": "source",
                            "type": "file",
                            "path": "data/data.csv",
                            "format": "csv",
                            "outputs": {
                                "main": _scaffold_output(
                                    "Dashboard rows",
                                    "Provide the reusable rows rendered by this Dashboard.",
                                    "One row per category.",
                                )
                            },
                        }
                    ],
                    "views": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "template": "table",
                            "input": "source:data/main",
                        }
                    ],
                    "sections": [
                        {"id": "main", "title": "Main", "views": ["overview"]}
                    ],
                }
            ),
            "data/data.csv": "category,value\nA,12\nB,19\n",
        }
    elif recipe in {"source.file", "source.sql", "source.python"}:
        source_type = recipe.split(".", 1)[1]
        definition: dict[str, Any] = {
            "schema": "dataviz/source/v3",
            "kind": "source",
            "id": item_id,
            "type": source_type,
            "outputs": {
                "main": _scaffold_output(
                    item_id.replace("-", " ").title(),
                    "Describe the business question answered by this Source.",
                    "Describe what one row represents.",
                )
            },
        }
        files = {}
        if source_type == "file":
            definition.update({"path": f"data/{item_id}.csv", "format": "csv"})
            files[f"data/{item_id}.csv"] = "category,value\nA,1\n"
        elif source_type == "sql":
            definition.update({"adapter": "warehouse", "code": f"{item_id}.sql"})
            files[f"{item_id}.sql"] = "select category, value from your_table\n"
        else:
            definition.update({"code": f"{item_id}.py", "entrypoint": "load"})
            files[f"{item_id}.py"] = (
                "def load(context):\n"
                "    # context.query_inputs and context.adapter are explicit inputs.\n"
                "    return [{\"category\": \"A\", \"value\": 1}]\n"
            )
        files = {f"{item_id}.yaml": _yaml(definition), **files}
    elif recipe == "dataset-transform.server-python":
        files = {
            f"{item_id}.yaml": _yaml(
                {
                    "schema": "dataviz/dataset-transform/v3",
                    "kind": "dataset_transform",
                    "id": item_id,
                    "runtime": "server-python",
                    "code": f"{item_id}.py",
                    "inputs": {"data": "source:data/main"},
                    "outputs": {
                        "main": _scaffold_output(
                            item_id.replace("-", " ").title(),
                            "Describe the reusable business result of this Dataset Transform.",
                            "Describe what one row represents.",
                        )
                    },
                }
            ),
            f"{item_id}.py": (
                "def transform(context):\n"
                "    rows = context.table(\"data\").copy()\n"
                "    return {\"main\": rows}\n"
            ),
        }
    elif recipe in {
        "interactive-transform.browser-js",
        "interactive-transform.server-python",
    }:
        runtime = recipe.rsplit(".", 1)[1]
        suffix = "js" if runtime == "browser-js" else "py"
        files = {
            f"{item_id}.yaml": _yaml(
                {
                    "schema": "dataviz/interactive-transform/v4",
                    "kind": "interactive_transform",
                    "id": item_id,
                    "runtime": runtime,
                    "code": f"{item_id}.{suffix}",
                    "inputs": {"data": "source:data/main"},
                    "control_inputs": {},
                    "trigger": "apply" if runtime == "server-python" else "auto",
                    "export": (
                        {"mode": "interactive"}
                        if runtime == "browser-js"
                        else {"mode": "snapshot"}
                    ),
                    "outputs": {
                        "main": _scaffold_output(
                            item_id.replace("-", " ").title(),
                            "Describe the interactive analysis result produced by this Transform.",
                            "Describe what one row represents.",
                        )
                    },
                }
            ),
            f"{item_id}.{suffix}": (
                "function transform(context) {\n"
                "  return {main: context.inputs.data.map(row => ({...row}))};\n"
                "}\n"
                if suffix == "js"
                else "def transform(context):\n    return {\"main\": context.table(\"data\")}\n"
            ),
        }
    elif recipe.startswith("view."):
        template = recipe.split(".", 1)[1]
        if template not in VIEW_TEMPLATES:
            raise ValidationFailure(f"Unknown View scaffold: {recipe}")
        definition: dict[str, Any] = {
            "id": item_id,
            "title": item_id.replace("-", " ").title(),
            "template": template,
        }
        placeholders = {
            "input": "source:data/main",
            "x": "x_field",
            "y": "y_field",
            "z": "value_field",
            "value": "value_field",
            "label": "label_field",
            "series": "series_field",
            "url": "assets/image.svg",
            "renderer": "team.renderer",
            "text": "Write the analytical narrative here.",
        }
        for field in VIEW_TEMPLATES[template].get("fields", []):
            if field == "columns":
                definition[field] = ["value_field"]
            else:
                definition[field] = placeholders.get(field, f"{field}_value")
        if template == "markdown":
            definition["text"] = placeholders["text"]
        files = {"dashboard.view.snippet.yaml": _yaml([definition])}
        if template == "image":
            files["assets/image.svg"] = (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 420">'
                '<rect width="800" height="420" fill="#1a237e"/>'
                '<circle cx="640" cy="110" r="74" fill="#26a69a"/>'
                '<path d="M0 360L250 150L440 300L800 70V420H0Z" fill="#3949ab"/>'
                '<text x="42" y="76" fill="#ffffff" font-family="sans-serif" '
                'font-size="38">IMAGE VIEW</text></svg>\n'
            )
    elif recipe.startswith("section."):
        template = recipe.split(".", 1)[1]
        if template not in SECTION_TEMPLATES:
            raise ValidationFailure(f"Unknown Section scaffold: {recipe}")
        definition = {
            "id": item_id,
            "title": item_id.replace("-", " ").title(),
            "template": template,
            "views": ["view-id"],
        }
        if template in {"small-multiples", "selection-gallery"}:
            definition["repeat"] = {
                "view": "view-id",
                "by": ["entity_id"],
                "title": "{entity_id}",
            }
        if template == "selection-gallery":
            definition["controls"] = [
                {
                    "id": "groups",
                    "field": "entity_id",
                    "type": "multiple_select", "value_type": "text",
                    "label": "Groups",
                    "initial": {"mode": "empty"},
                    "options": {"mode": "infer"},
                }
            ]
            definition["repeat"]["control"] = "groups"
        files = {"dashboard.section.snippet.yaml": _yaml([definition])}
    elif recipe.startswith("control."):
        component = recipe.split(".", 1)[1]
        if f"control.{component}" not in component_catalog():
            raise ValidationFailure(f"Unknown Control scaffold: {recipe}")
        label = item_id.replace("-", " ").title()
        control: dict[str, Any] = {
            "id": item_id,
            "type": "single_input", "value_type": "text",
            "label": label,
            "default": "",
        }
        if component == "input":
            control.update({"placeholder": "Enter text", "max_length": 120})
        elif component == "multiple-input":
            control.update(
                {
                    "type": "multiple_input",
                    "value_type": "text",
                    "default": ["alpha", "beta"],
                    "max_items": 8,
                }
            )
        elif component == "auto-complete":
            control.update(
                {
                    "placeholder": "Enter or choose a suggestion",
                    "suggestions": [
                        {"label": "Alpha", "value": "alpha"},
                        {"label": "Beta", "value": "beta"},
                    ],
                }
            )
        elif component in {"input-number", "slider"}:
            control.update({"type": "single_input", "value_type": "integer", "default": 50, "min": 0, "max": 100, "step": 5})
        elif component in {"checkbox", "switch"}:
            control.update({"type": "single_input", "value_type": "boolean", "default": False})
        elif component == "date-picker":
            control.update(
                {
                    "type": "single_input", "value_type": "date",
                    "default": "2026-01-15",
                    "min_date": "2026-01-01",
                    "max_date": "2026-12-31",
                }
            )
        elif component == "range-picker":
            control.update(
                {
                    "type": "range_input", "value_type": "date",
                    "default": ["2026-01-01", "2026-01-31"],
                    "min_date": "2026-01-01",
                    "max_date": "2026-12-31",
                }
            )
        elif component == "radio-group":
            control.pop("default")
            control.update(
                {
                    "type": "single_select", "value_type": "text",
                    "initial": {"mode": "value", "value": "alpha"},
                    "required": True,
                    "options": {
                        "mode": "static",
                        "choices": [
                            {"label": "Alpha", "value": "alpha"},
                            {"label": "Beta", "value": "beta"},
                        ],
                    },
                }
            )
        elif component in {"select", "checkbox-group"}:
            control.pop("default")
            control.update(
                {
                    "type": "multiple_select", "value_type": "text",
                    "initial": {"mode": "values", "values": ["alpha"]},
                    "options": {
                        "mode": "static",
                        "choices": [
                            {"label": "Alpha", "value": "alpha"},
                            {"label": "Beta", "value": "beta"},
                        ],
                    },
                }
            )
        elif component in {"cascader", "tree-select"}:
            control.pop("default")
            control.update(
                {
                    "type": "multiple_select", "value_type": "text",
                    "field": "district",
                    "path_fields": ["province", "city", "district"],
                    "options": {"mode": "infer"},
                }
            )
        files = {
            "dashboard.control.snippet.yaml": _yaml([control]),
            "presentation.control-component.snippet.yaml": _yaml(
                {
                    "control_components": {
                        f"view:view-id/{item_id}": {"component": component}
                    }
                }
            ),
        }
    elif recipe == "renderer.custom":
        renderer_class = "renderer-" + "".join(
            value if value.isalnum() or value in {"-", "_"} else "-"
            for value in item_id
        )
        renderer_literal = json.dumps(item_id, ensure_ascii=False)
        class_literal = json.dumps(renderer_class, ensure_ascii=False)
        files = {
            "dashboard.view.snippet.yaml": _yaml(
                [
                    {
                        "id": item_id,
                        "title": item_id.replace("-", " ").title(),
                        "template": "custom",
                        "renderer": item_id,
                        "input": "source:data/main",
                    }
                ]
            ),
            f"assets/{item_id}.js": (
                "// For charts prefer context.charts.plotly. The platform owns theme,\n"
                "// responsive resize, page-first wheel behavior, update and disposal.\n"
                "// For tables use context.tables.tanstack; .core exposes the full headless API.\n"
                f"window.datavizRuntime.registerRenderer({renderer_literal}, {{\n"
                "  validate(descriptor) {},\n"
                "  mount(context, descriptor) {\n"
                "    const node = document.createElement('div');\n"
                f"    node.className = {class_literal};\n"
                "    context.body.append(node);\n"
                "    this.update(context, descriptor, {node});\n"
                "    return {node};\n"
                "  },\n"
                "  update(_context, descriptor, state) {\n"
                "    state.node.textContent = JSON.stringify(descriptor.rows || descriptor.value);\n"
                "    return state;\n"
                "  },\n"
                "  dispose(_context, state) { state.node.remove(); },\n"
                "});\n"
            ),
            f"assets/{item_id}.css": (
                f".{renderer_class} {{\n"
                "  min-height: 12rem;\n"
                "  color: var(--dv-ink);\n"
                "  background: var(--dv-panel);\n"
                "}\n"
            ),
            f"assets/{item_id}.contract.json": json.dumps(
                {
                    "schema": "dataviz/renderer-contract/v1",
                    "renderer": item_id,
                    "cases": [
                        {"type": item_id, "rows": [{"category": "A", "value": 1}]},
                        {"type": item_id, "rows": []},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            "presentation.asset.snippet.yaml": _yaml(
                {
                    "assets": {
                        "css": [f"assets/{item_id}.css"],
                        "js": [f"assets/{item_id}.js"],
                    }
                }
            ),
        }
    else:
        raise ValidationFailure(
            f"Unknown scaffold recipe: {recipe}",
            details={"available": list(scaffold_recipes())},
        )

    route = _scaffold_route(recipe)
    scope = "workspace" if recipe in SCAFFOLD_PROFILES else "fragment"
    return {
        "schema": "dataviz/scaffold/v1",
        "recipe": recipe,
        "id": item_id,
        "route": route,
        "scope": scope,
        "files": files,
        "verify": [
            f"dataviz validate <workspace> --dashboard {item_id} --format json",
            f"dataviz report <workspace> {item_id} --output report.html",
            f"dataviz visual-check <workspace> {item_id} --target both",
        ],
        "notes": [
            "Snippets are strict current-schema examples; no legacy aliases are emitted.",
            "Run dataviz validate after placing or merging the files.",
        ],
    }
