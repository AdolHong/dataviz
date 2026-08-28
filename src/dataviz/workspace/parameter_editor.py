from __future__ import annotations

import hashlib
import io
import threading
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from dataviz.errors import WorkspaceError
from dataviz.filesystem import atomic_write_text
from dataviz.value_contract import select_initial_contract
from dataviz.workspace.loader import LoadedDashboard
from dataviz.workspace.models import DashboardDefinition, StaticOptionDomainDefinition


EDITOR_SCHEMA = "dataviz/parameter-editor/v1"


def _revision(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _yaml() -> YAML:
    parser = YAML(typ="rt")
    parser.preserve_quotes = True
    parser.width = 4096
    parser.indent(mapping=2, sequence=4, offset=2)
    return parser


def _choice_payload(choice) -> dict[str, Any]:
    return choice.model_dump(mode="json", exclude_defaults=True, exclude_none=True)


def _minimal_choice(value: dict[str, Any]) -> dict[str, Any]:
    choice = {"label": value.get("label"), "value": value.get("value")}
    if value.get("group") is not None:
        choice["group"] = value["group"]
    if value.get("description"):
        choice["description"] = value["description"]
    if value.get("keywords"):
        choice["keywords"] = value["keywords"]
    return choice


def _control_payload(control) -> dict[str, Any]:
    static = isinstance(control.options, StaticOptionDomainDefinition)
    inferred = getattr(control.options, "mode", None) == "infer"
    select = control.type in {"single_select", "multiple_select"}
    return {
        "id": control.id,
        "label": control.label or control.id,
        "type": control.type,
        "value_type": control.value_type,
        "path_fields": list(getattr(control, "path_fields", []) or []),
        "min": control.min,
        "max": control.max,
        "step": control.step,
        "min_date": control.min_date,
        "max_date": control.max_date,
        "max_length": control.max_length,
        "max_items": control.max_items,
        "kind": getattr(control, "kind", "query"),
        "required": control.required,
        "clearable": control.clearable,
        "default": control.default,
        "default_editable": not select,
        "initial": select_initial_contract(control) if select else None,
        "initial_editable": select,
        "option_source": "static" if static else "infer" if inferred else None,
        "choices_editable": static,
        "choices": [_choice_payload(choice) for choice in control.options.choices]
        if static
        else [],
    }


def _group_payload(
    owner: str,
    title: str,
    controls: list[Any],
) -> dict[str, Any]:
    return {
        "owner": owner,
        "title": title,
        "order": [control.id for control in controls],
        "items": [_control_payload(control) for control in controls],
    }


def parameter_editor_contract(dashboard: LoadedDashboard) -> dict[str, Any]:
    definition = dashboard.definition
    # Keep every authoring scope addressable, including an empty one.  The
    # browser can then open a truthful read-only/empty editor from any visible
    # scope trigger instead of treating "nothing editable" as a missing route.
    groups: list[dict[str, Any]] = [
        _group_payload("query", "查询参数", definition.query_parameters),
        _group_payload("dashboard", "看板控件", definition.controls),
    ]
    for section in definition.sections:
        groups.append(
            _group_payload(
                f"section:{section.id}",
                f"区块 · {section.title or section.id}",
                section.controls,
            )
        )
    for view in definition.views:
        groups.append(
            _group_payload(
                f"view:{view.id}",
                f"视图 · {view.title or view.id}",
                view.controls,
            )
        )
    source = dashboard.definition_path.read_text(encoding="utf-8")
    return {
        "schema": EDITOR_SCHEMA,
        "dashboard_id": definition.id,
        "dashboard_title": dashboard.title,
        "revision": _revision(source),
        "groups": groups,
    }


@dataclass(slots=True)
class ParameterEditor:
    """Round-trip edit the human-owned subset of one Dashboard contract.

    The editor deliberately cannot change ids, types, dependencies, bindings,
    layout or presentation. It owns only defaults, static choices and sibling
    order. That boundary keeps this UI useful without turning it into a second
    Dashboard authoring system.
    """

    lock: threading.RLock

    def __init__(self) -> None:
        self.lock = threading.RLock()

    def update_group(
        self,
        dashboard: LoadedDashboard,
        *,
        expected_revision: str,
        owner: str,
        order: list[str],
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        path = dashboard.definition_path
        with self.lock:
            source = path.read_text(encoding="utf-8")
            current_revision = _revision(source)
            if current_revision != expected_revision:
                raise WorkspaceError(
                    "dashboard.yaml changed while the parameter editor was open",
                    file=path,
                    details={
                        "code": "parameter_editor_revision_conflict",
                        "expected_revision": expected_revision,
                        "current_revision": current_revision,
                    },
                )

            yaml = _yaml()
            document = yaml.load(source)
            if not isinstance(document, CommentedMap):
                raise WorkspaceError("Dashboard YAML must be an object", file=path)

            sequence, definitions = self._resolve_group(document, dashboard, owner)
            current_ids = [definition.id for definition in definitions]
            if len(order) != len(set(order)) or set(order) != set(current_ids):
                raise WorkspaceError(
                    "Parameter order must contain every current item exactly once",
                    file=path,
                    details={
                        "code": "parameter_editor_invalid_order",
                        "owner": owner,
                        "expected": current_ids,
                        "received": order,
                    },
                )

            updates = {str(item.get("id")): item for item in items}
            if set(updates) != set(current_ids):
                raise WorkspaceError(
                    "Parameter update must contain every current item exactly once",
                    file=path,
                    details={
                        "code": "parameter_editor_invalid_items",
                        "owner": owner,
                        "expected": current_ids,
                        "received": sorted(updates),
                    },
                )

            nodes_by_id: dict[str, CommentedMap] = {}
            definitions_by_id = {definition.id: definition for definition in definitions}
            for node in sequence:
                if not isinstance(node, CommentedMap) or not isinstance(node.get("id"), str):
                    raise WorkspaceError(
                        "Editable parameter lists must contain id-addressable objects",
                        file=path,
                        details={"owner": owner},
                    )
                nodes_by_id[node["id"]] = node

            for identifier, update in updates.items():
                node = nodes_by_id[identifier]
                definition = definitions_by_id[identifier]
                static = isinstance(definition.options, StaticOptionDomainDefinition)
                select = definition.type in {"single_select", "multiple_select"}

                if select:
                    initial = update.get("initial")
                    if not isinstance(initial, dict):
                        raise WorkspaceError(
                            "Select controls require an initial policy",
                            file=path,
                            details={
                                "code": "parameter_editor_initial_missing",
                                "owner": owner,
                                "control": identifier,
                            },
                        )
                    node["initial"] = CommentedMap(initial)
                    node.pop("default", None)
                else:
                    node["default"] = update.get("default")

                choices = update.get("choices")
                if static:
                    if not isinstance(choices, list) or not choices:
                        raise WorkspaceError(
                            "Static option controls require at least one choice",
                            file=path,
                            details={
                                "code": "parameter_editor_empty_choices",
                                "owner": owner,
                                "control": identifier,
                            },
                        )
                    options = node.get("options")
                    if not isinstance(options, CommentedMap) or options.get("mode") != "static":
                        raise WorkspaceError(
                            "Static option contract changed while editing",
                            file=path,
                            details={"owner": owner, "control": identifier},
                        )
                    options["choices"] = CommentedSeq(
                        _minimal_choice(choice) for choice in choices
                    )
                elif choices not in (None, []):
                    raise WorkspaceError(
                        "Only static option choices are editable",
                        file=path,
                        details={
                            "code": "parameter_editor_choices_read_only",
                            "owner": owner,
                            "control": identifier,
                        },
                    )

            sequence[:] = [nodes_by_id[identifier] for identifier in order]

            try:
                DashboardDefinition.model_validate(document)
            except ValidationError as error:
                raise WorkspaceError(
                    "Edited parameter values violate the Dashboard contract",
                    file=path,
                    details={
                        "code": "parameter_editor_validation_failed",
                        "errors": error.errors(
                            include_url=False,
                            include_context=False,
                            include_input=False,
                        ),
                    },
                ) from error

            stream = io.StringIO()
            yaml.dump(document, stream)
            content = stream.getvalue()
            atomic_write_text(path, content)
            return {
                "schema": EDITOR_SCHEMA,
                "dashboard_id": dashboard.definition.id,
                "owner": owner,
                "revision": _revision(content),
            }

    @staticmethod
    def _resolve_group(
        document: CommentedMap,
        dashboard: LoadedDashboard,
        owner: str,
    ) -> tuple[CommentedSeq, list[Any]]:
        if owner == "query":
            sequence = document.get("query_parameters")
            definitions = dashboard.definition.query_parameters
        elif owner == "dashboard":
            sequence = document.get("controls")
            definitions = dashboard.definition.controls
        elif owner.startswith("section:"):
            identifier = owner.split(":", 1)[1]
            section = next(
                (item for item in dashboard.definition.sections if item.id == identifier),
                None,
            )
            container = ParameterEditor._find_owner(document.get("sections"), identifier)
            sequence = container.get("controls") if container is not None else None
            definitions = section.controls if section is not None else []
        elif owner.startswith("view:"):
            identifier = owner.split(":", 1)[1]
            view = dashboard.views.get(identifier)
            container = ParameterEditor._find_owner(document.get("views"), identifier)
            sequence = container.get("controls") if container is not None else None
            definitions = view.controls if view is not None else []
        else:
            sequence = None
            definitions = []

        if not isinstance(sequence, CommentedSeq) or not definitions:
            raise WorkspaceError(
                f"Unknown or empty parameter editor group: {owner}",
                file=dashboard.definition_path,
                details={"code": "parameter_editor_unknown_group", "owner": owner},
            )
        return sequence, list(definitions)

    @staticmethod
    def _find_owner(sequence: Any, identifier: str) -> CommentedMap | None:
        if not isinstance(sequence, CommentedSeq):
            return None
        for item in sequence:
            if isinstance(item, CommentedMap) and item.get("id") == identifier:
                return item
        return None
