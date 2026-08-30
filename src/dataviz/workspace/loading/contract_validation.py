"""Cross-file semantic contracts and stable Workspace diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse


from dataviz.content_templates import (
    allowed_content_controls,
    content_control_contract,
    content_template_fields,
    inspect_content_template,
)
from dataviz.errors import DatavizError, Diagnostic
from dataviz.execution.references import parse_output_reference
from dataviz.execution.parameters import query_input_parameter
from dataviz.sql_contract import sql_parameter_names
from dataviz.workspace.models import (
    DatasetTransformDefinition,
    InteractiveTransformDefinition,
    InferredOptionDomainDefinition,
    SourceDefinition,
)
from dataviz.workspace.controls import compile_control_contract, scoped_control_registry
from dataviz.view_contracts import referenced_view_fields

from dataviz.workspace.loading.asset_validation import (
    _browser_python_dependency_diagnostic,
    _code_path,
    _is_within,
    _python_dependency_error,
    _validate_pyodide_bundle,
)
from dataviz.workspace.loading.loaded_types import LoadedDashboard, LoadedWorkspace


def _duplicates(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def _cycle_nodes(graph: dict[str, set[str]]) -> list[str]:
    incoming = {node: set(dependencies) for node, dependencies in graph.items()}
    ready = [node for node, dependencies in incoming.items() if not dependencies]
    visited: set[str] = set()
    while ready:
        current = ready.pop()
        if current in visited:
            continue
        visited.add(current)
        for node, dependencies in incoming.items():
            if current in dependencies:
                dependencies.remove(current)
                if not dependencies:
                    ready.append(node)
    return sorted(set(graph) - visited)


def _reference_error(
    reference: str,
    *,
    sources: dict[str, tuple[Path, SourceDefinition]],
    dataset_transforms: dict[str, tuple[Path, DatasetTransformDefinition]],
    interactive_transforms: dict[str, tuple[Path, InteractiveTransformDefinition]],
    allow_interactive: bool,
) -> str | None:
    try:
        parsed = parse_output_reference(reference)
    except Exception as error:
        return str(error)
    kind, _, node_id = parsed.node_id.partition(":")
    collections = {
        "source": sources,
        "dataset": dataset_transforms,
        "interactive": interactive_transforms,
    }
    if kind == "interactive" and not allow_interactive:
        return "Query DAG nodes cannot depend on Interactive Outputs"
    collection = collections.get(kind)
    if collection is None or node_id not in collection:
        return f"Unknown output node: {parsed.node_id}"
    definition = collection[node_id][1]
    outputs = definition.outputs
    if parsed.output not in outputs:
        return f"Unknown output {parsed.output!r} on {parsed.node_id}"
    return None


def _safe_output_reference(reference: str):
    try:
        return parse_output_reference(reference)
    except Exception:
        return None


def _reference_kind(reference: str, dashboard: LoadedDashboard) -> str | None:
    parsed = parse_output_reference(reference)
    kind, _, node_id = parsed.node_id.partition(":")
    collection = {
        "source": dashboard.sources,
        "dataset": dashboard.dataset_transforms,
        "interactive": dashboard.interactive_transforms,
    }[kind]
    definition = collection[node_id][1]
    output = definition.outputs.get(parsed.output)
    return output.kind if output else None


def _reference_output_definition(reference: str, dashboard: LoadedDashboard):
    parsed = parse_output_reference(reference)
    kind, _, node_id = parsed.node_id.partition(":")
    collection = {
        "source": dashboard.sources,
        "dataset": dashboard.dataset_transforms,
        "interactive": dashboard.interactive_transforms,
    }[kind]
    definition = collection[node_id][1]
    return definition.outputs.get(parsed.output)


def _validate_query_inputs(
    bindings: dict[str, Any],
    *,
    parameter_definitions: dict[str, Any],
    definition_path: Path,
    diagnostics: list[Diagnostic],
) -> None:
    """Validate one node's local Query Parameter bindings consistently."""

    for alias, binding in bindings.items():
        parameter = query_input_parameter(binding)
        if parameter not in parameter_definitions:
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Unknown query parameter: {parameter}",
                    str(definition_path),
                    f"query_inputs.{alias}",
                    "query_input_parameter_unknown",
                )
            )
            continue
        if (
            not isinstance(binding, str)
            and binding.part is not None
            and (
                parameter_definitions[parameter].type != "range_input"
                or parameter_definitions[parameter].value_type != "date"
            )
        ):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Query input {alias} uses part={binding.part}, but {parameter} is not range_input/date",
                    str(definition_path),
                    f"query_inputs.{alias}.part",
                    "query_input_part_invalid",
                )
            )


def validate_workspace(workspace: LoadedWorkspace) -> list[Diagnostic]:
    """Validate the strict v2 contract and every cross-file/runtime reference."""
    diagnostics: list[Diagnostic] = list(workspace.load_diagnostics)
    if not workspace.dashboards:
        diagnostics.append(
            Diagnostic("warning", "Workspace has no dashboards", str(workspace.definition_path))
        )

    try:
        from dataviz.auth import AdapterResolver

        adapter_resolver = AdapterResolver(workspace.root)
    except Exception as error:
        adapter_resolver = None
        diagnostics.append(
            Diagnostic(
                "error",
                f"Adapter configuration is invalid: {error}",
                str(workspace.root),
                code="adapter_configuration_invalid",
            )
        )

    runtime = workspace.definition.runtime
    # Plotly is a package-owned bundled asset. Only configurable
    # Workspace runtime assets participate in local path validation.
    for field in ("arrow_js",):
        configured = getattr(runtime, field)
        parsed = urlparse(configured)
        if parsed.scheme in {"http", "https"}:
            continue
        asset_path = (workspace.root / configured).resolve()
        if not _is_within(asset_path, workspace.root):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Local Runtime asset must stay inside the Workspace: {configured}",
                    str(workspace.definition_path),
                    f"runtime.{field}",
                    "runtime_asset_outside_workspace",
                    {"asset": configured},
                )
            )
        elif not asset_path.is_file():
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Local Runtime asset does not exist: {configured}",
                    str(workspace.definition_path),
                    f"runtime.{field}",
                    "runtime_asset_missing",
                    {"asset": configured},
                )
            )
        else:
            try:
                asset_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Local Runtime asset is not readable UTF-8 JavaScript: {configured}",
                        str(workspace.definition_path),
                        f"runtime.{field}",
                        "runtime_asset_unreadable",
                        {"asset": configured, "error_type": type(error).__name__},
                    )
                )
    # A local bundle may be selected only by an exported browser-python branch
    # even when the live Server itself uses the CDN. Validate every configured
    # bundle path, not only the live Runtime policy.
    if runtime.pyodide_bundle_path:
        bundle_path = (workspace.root / runtime.pyodide_bundle_path).resolve()
        if not _is_within(bundle_path, workspace.root):
            diagnostics.append(
                Diagnostic(
                    "error",
                    "Pyodide bundle must stay inside the Workspace",
                    str(workspace.definition_path),
                    "runtime.pyodide_bundle_path",
                    "pyodide_bundle_outside_workspace",
                )
            )
        else:
            diagnostics.extend(_validate_pyodide_bundle(workspace, bundle_path))

    for dashboard in workspace.dashboards.values():
        diagnostics.extend(dashboard.presentation_diagnostics or [])
        definition_path = str(dashboard.definition_path)
        parameter_definitions = {item.id: item for item in dashboard.definition.query_parameters}
        parameter_ids = set(parameter_definitions)
        control_registry = scoped_control_registry(dashboard.definition)
        control_contract = compile_control_contract(dashboard.definition)
        compute_control_keys = {
            key for key, item in control_registry.items() if item.kind == "compute"
        }
        selection_control_keys = {
            key for key, item in control_registry.items() if item.kind == "selection"
        }
        control_content_contract = content_control_contract(dashboard.definition)
        dependency_contract = None
        view_ids = set(dashboard.views)

        try:
            _ = dashboard.layout_contract
        except DatavizError as error:
            payload = error.as_dict()
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Cannot compile Dashboard Layout Contract: {error.message}",
                    definition_path,
                    "layout",
                    payload["code"],
                    payload.get("details"),
                )
            )
        except Exception as error:
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Cannot compile Dashboard Layout Contract: {error}",
                    definition_path,
                    "layout",
                    "layout_contract_invalid",
                )
            )

        duplicate_contracts = [
            (
                "query_parameters",
                _duplicates([item.id for item in dashboard.definition.query_parameters]),
            ),
            (
                "controls",
                _duplicates([item.id for item in dashboard.definition.controls]),
            ),
            *(
                (
                    f"sections.{section.id}.controls",
                    _duplicates([item.id for item in section.controls]),
                )
                for section in dashboard.definition.sections
            ),
            *(
                (
                    f"views.{view.id}.controls",
                    _duplicates([item.id for item in view.controls]),
                )
                for view in dashboard.definition.views
            ),
        ]
        for field, duplicate_ids in duplicate_contracts:
            if duplicate_ids:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Duplicate ids in {field}: {', '.join(duplicate_ids)}",
                        definition_path,
                        field,
                        "state_id_duplicate",
                        {"ids": duplicate_ids},
                    )
                )

        option_domain_contract_valid = True
        for control_key, item in control_registry.items():
            options = item.definition.options
            if (
                item.kind != "selection"
                or not isinstance(options, InferredOptionDomainDefinition)
                or not options.source
            ):
                continue
            reference = options.source
            message = _reference_error(
                reference,
                sources=dashboard.sources,
                dataset_transforms=dashboard.dataset_transforms,
                interactive_transforms=dashboard.interactive_transforms,
                allow_interactive=False,
            )
            if message:
                option_domain_contract_valid = False
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Selection {control_key} options.source: {message}",
                        definition_path,
                        f"controls.{control_key}.options.source",
                        "selection_option_domain_invalid",
                        {"control": control_key, "reference": reference},
                    )
                )
                continue
            if _reference_kind(reference, dashboard) != "table":
                option_domain_contract_valid = False
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Selection {control_key} options.source must reference a table Output",
                        definition_path,
                        f"controls.{control_key}.options.source",
                        "selection_option_domain_kind",
                        {"control": control_key, "reference": reference},
                    )
                )
                continue
            output = _reference_output_definition(reference, dashboard)
            if output is not None and output.schema_:
                declared = {column.name for column in output.schema_}
                required_fields = {
                    field
                    for effective_controls in control_contract.values()
                    for effective in effective_controls
                    if effective.key == control_key
                    for field in (
                        effective.definition.path_fields
                        or [effective.binding.field or effective.id]
                    )
                } or set(item.definition.path_fields or [item.definition.field or item.id])
                unknown = sorted(required_fields - declared)
                if unknown:
                    option_domain_contract_valid = False
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Selection {control_key} option domain does not declare fields: "
                            + ", ".join(unknown),
                            definition_path,
                            f"controls.{control_key}.options.source",
                            "selection_option_domain_field_unknown",
                            {
                                "control": control_key,
                                "reference": reference,
                                "unknown": unknown,
                                "declared": sorted(declared),
                            },
                        )
                    )

        if option_domain_contract_valid:
            try:
                dependency_contract = dashboard.dependency_contract
                option_domains = {
                    key: list(references)
                    for key, references in dependency_contract.selection_option_domains.items()
                }
            except DatavizError as error:
                option_domains = {}
                payload = error.as_dict()
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Cannot compile Dashboard Dependency Contract: {error.message}",
                        definition_path,
                        "dependencies",
                        payload["code"],
                        payload.get("details"),
                    )
                )
            except Exception as error:
                option_domains = {}
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Cannot compile Dashboard Dependency Contract: {error}",
                        definition_path,
                        "dependencies",
                        "dependency_contract_invalid",
                    )
                )
            for control_key, item in control_registry.items():
                definition = item.definition
                dynamic_select = (
                    item.kind == "selection"
                    and definition.type in {"single_select", "multiple_select"}
                    and isinstance(definition.options, InferredOptionDomainDefinition)
                )
                references = option_domains.get(control_key, [])
                if dynamic_select and not references:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Dynamic Selection {control_key} has no Base Output option domain",
                            definition_path,
                            f"controls.{control_key}",
                            "selection_option_domain_missing",
                            {"control": control_key},
                        )
                    )
                    continue
                if not dynamic_select:
                    continue
                field_sets = [
                    set(
                        effective.definition.path_fields
                        or [effective.binding.field or effective.id]
                    )
                    for effective_controls in control_contract.values()
                    for effective in effective_controls
                    if effective.key == control_key
                ] or [set(definition.path_fields or [definition.field or definition.id])]
                declared_domains: list[set[str]] = []
                has_dynamic_schema = False
                for reference in references:
                    if _reference_kind(reference, dashboard) != "table":
                        continue
                    output = _reference_output_definition(reference, dashboard)
                    if output is None or not output.schema_:
                        has_dynamic_schema = True
                        continue
                    declared_domains.append({column.name for column in output.schema_})
                if not has_dynamic_schema and not all(
                    any(fields <= declared for declared in declared_domains)
                    for fields in field_sets
                ):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Dynamic Selection {control_key} cannot derive its fields from any Base Output",
                            definition_path,
                            f"controls.{control_key}",
                            "selection_option_domain_field_unknown",
                            {
                                "control": control_key,
                                "references": references,
                                "required_field_sets": [sorted(fields) for fields in field_sets],
                                "declared_domains": [sorted(fields) for fields in declared_domains],
                            },
                        )
                    )

        for field, value in content_template_fields(dashboard.definition):
            inspection = inspect_content_template(value)
            for message in inspection.errors:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        message,
                        definition_path,
                        field,
                        "content_template_invalid",
                    )
                )
            for parameter_id in sorted(inspection.query_parameters - parameter_ids):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Content references unknown Query Parameter: {parameter_id}",
                        definition_path,
                        field,
                        "content_parameter_unknown",
                    )
                )
            known_control_references = inspection.controls & set(control_content_contract)
            for expression in sorted(inspection.controls - set(control_content_contract)):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Content references unknown Control: {expression}",
                        definition_path,
                        field,
                        "content_control_unknown",
                    )
                )
            for expression in sorted(
                known_control_references - allowed_content_controls(dashboard.definition, field)
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Content references Control outside its visible scope: {expression}",
                        definition_path,
                        field,
                        "content_control_out_of_scope",
                    )
                )

        for source_path, source in dashboard.sources.values():
            if not _is_within(source_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Source definition must stay inside its Dashboard folder",
                        str(source_path),
                        "sources",
                        "source_definition_outside_dashboard",
                    )
                )
            source_adapter = getattr(source, "adapter", None)
            if source_adapter and adapter_resolver:
                try:
                    _, adapter = adapter_resolver.resolve(
                        source_adapter, dashboard.definition.adapters
                    )
                except Exception as error:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            str(error),
                            str(source_path),
                            "adapter",
                            "adapter_not_configured",
                        )
                    )
                else:
                    allowed = (
                        {"file"}
                        if source.type == "file"
                        else {"duckdb", "mysql", "starrocks", "sqlalchemy"}
                    )
                    if source.type in {"file", "sql"} and adapter.type not in allowed:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Adapter type {adapter.type!r} cannot be used by a {source.type} Source",
                                str(source_path),
                                "adapter",
                                "adapter_type_mismatch",
                            )
                        )
                    elif source.type in {"sql", "python"}:
                        try:
                            adapter_resolver.runtime_config(
                                source_adapter,
                                dashboard.definition.adapters,
                            )
                        except Exception as error:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    f"Adapter runtime configuration is incomplete: {error}",
                                    str(source_path),
                                    "adapter",
                                    "adapter_runtime_configuration_invalid",
                                )
                            )
                        else:
                            if source.type == "sql":
                                try:
                                    adapter_resolver.validate_sql_driver(
                                        source_adapter,
                                        dashboard.definition.adapters,
                                    )
                                except Exception as error:
                                    diagnostics.append(
                                        Diagnostic(
                                            "error",
                                            str(error),
                                            str(source_path),
                                            "adapter",
                                            "adapter_sql_driver_invalid",
                                        )
                                    )
                    elif source.type == "file":
                        try:
                            data_path = adapter_resolver.resolve_path(
                                source_adapter,
                                source.path,
                                dashboard.definition.adapters,
                            )
                        except Exception as error:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    str(error),
                                    str(source_path),
                                    "path",
                                    "source_asset_invalid",
                                )
                            )
                        else:
                            if not data_path.is_file():
                                diagnostics.append(
                                    Diagnostic(
                                        "error",
                                        "File Source data file does not exist",
                                        str(data_path),
                                        "path",
                                        "source_asset_missing",
                                    )
                                )
            _validate_query_inputs(
                getattr(source, "query_inputs", {}),
                parameter_definitions=parameter_definitions,
                definition_path=source_path,
                diagnostics=diagnostics,
            )
            if source.type == "file":
                file_format = source.format or Path(source.path).suffix.removeprefix(".").lower()
                reader_dependency = {
                    "xlsx": "openpyxl>=3.1",
                    "xls": "xlrd>=2.0",
                }.get(file_format)
                if reader_dependency and (message := _python_dependency_error(reader_dependency)):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Excel File Source reader dependency is unavailable: {message}",
                            str(source_path),
                            "format",
                            "file_reader_dependency_unavailable",
                            {
                                "format": file_format,
                                "dependency": reader_dependency,
                                "install": "pip install 'ai-dataviz[excel]'",
                            },
                        )
                    )
            for field in ("path", "code"):
                value = getattr(source, field, None)
                if not value:
                    continue
                if field == "path" and source_adapter:
                    continue
                path = _code_path(source_path, value)
                if not _is_within(path, dashboard.root):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Source {field} must stay inside its Dashboard folder",
                            str(path),
                            field,
                            "source_asset_outside_dashboard",
                        )
                    )
                    continue
                if not path.is_file():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Source {field} does not exist or is not a file",
                            str(path),
                            field,
                        )
                    )
            if source.type == "sql" and source.code:
                code_path = _code_path(source_path, source.code)
                if code_path.exists():
                    try:
                        sql = code_path.read_text(encoding="utf-8")
                    except (OSError, UnicodeError) as error:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"SQL source could not be read: {error}",
                                str(code_path),
                                "code",
                                "sql_file_unreadable",
                            )
                        )
                    else:
                        declared = set(source.query_inputs)
                        referenced = sql_parameter_names(sql)
                        undeclared = sorted(referenced - declared)
                        unused = sorted(declared - referenced)
                        if undeclared:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    "SQL uses named parameters not declared in Source query_inputs: "
                                    + ", ".join(undeclared),
                                    str(source_path),
                                    "query_inputs",
                                    "sql_parameter_undeclared",
                                    {"parameters": undeclared, "sql_file": str(code_path)},
                                )
                            )
                        if unused:
                            diagnostics.append(
                                Diagnostic(
                                    "warning",
                                    "Source query_inputs are not referenced by SQL: "
                                    + ", ".join(unused),
                                    str(source_path),
                                    "query_inputs",
                                    "sql_parameter_unused",
                                    {"parameters": unused, "sql_file": str(code_path)},
                                )
                            )
            for dependency in getattr(source, "code_dependencies", []):
                dependency_path = _code_path(source_path, dependency)
                if not _is_within(dependency_path, dashboard.root):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Python Source code dependency must stay inside its Dashboard folder",
                            str(dependency_path),
                            "code_dependencies",
                            "code_dependency_outside_dashboard",
                        )
                    )
                elif not dependency_path.exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Python Source code dependency does not exist",
                            str(dependency_path),
                            "code_dependencies",
                        )
                    )
            for dependency in getattr(source, "python_dependencies", []):
                if message := _python_dependency_error(dependency):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            message,
                            str(source_path),
                            "python_dependencies",
                        )
                    )

        for transform_path, transform in dashboard.dataset_transforms.values():
            code_path = _code_path(transform_path, transform.code)
            if not _is_within(transform_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Dataset Transform definition must stay inside its Dashboard folder",
                        str(transform_path),
                        "dataset_transforms",
                        "dataset_definition_outside_dashboard",
                    )
                )
            if not _is_within(code_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Dataset Transform code must stay inside its Dashboard folder",
                        str(code_path),
                        "code",
                        "dataset_code_outside_dashboard",
                    )
                )
            elif not code_path.exists():
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Dataset Transform code does not exist",
                        str(code_path),
                        "code",
                    )
                )
            for dependency in transform.code_dependencies:
                dependency_path = _code_path(transform_path, dependency)
                if not _is_within(dependency_path, dashboard.root):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Dataset Transform code dependency must stay inside its Dashboard folder",
                            str(dependency_path),
                            "code_dependencies",
                            "code_dependency_outside_dashboard",
                        )
                    )
                elif not dependency_path.exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Dataset Transform code dependency does not exist",
                            str(dependency_path),
                            "code_dependencies",
                        )
                    )
            for dependency in transform.python_dependencies:
                if message := _python_dependency_error(dependency):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            message,
                            str(transform_path),
                            "python_dependencies",
                        )
                    )
            _validate_query_inputs(
                transform.query_inputs,
                parameter_definitions=parameter_definitions,
                definition_path=transform_path,
                diagnostics=diagnostics,
            )
            for name, reference in transform.inputs.items():
                message = _reference_error(
                    reference,
                    sources=dashboard.sources,
                    dataset_transforms=dashboard.dataset_transforms,
                    interactive_transforms=dashboard.interactive_transforms,
                    allow_interactive=False,
                )
                if message:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Input {name}: {message}",
                            str(transform_path),
                            f"inputs.{name}",
                        )
                    )
            for name in transform.input_schemas:
                if name not in transform.inputs:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Input schema references undeclared input: {name}",
                            str(transform_path),
                            f"input_schemas.{name}",
                        )
                    )

        for transform_path, transform in dashboard.interactive_transforms.values():
            code_path = _code_path(transform_path, transform.code)
            if not _is_within(transform_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Interactive Transform definition must stay inside its Dashboard folder",
                        str(transform_path),
                        "interactive_transforms",
                        "interactive_definition_outside_dashboard",
                    )
                )
            if not _is_within(code_path, dashboard.root):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Interactive Transform code must stay inside its Dashboard folder",
                        str(code_path),
                        "code",
                        "interactive_code_outside_dashboard",
                    )
                )
            elif not code_path.exists():
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Interactive Transform code does not exist",
                        str(code_path),
                        "code",
                    )
                )
            if transform.runtime in {"browser-js", "browser-python"} and not _is_within(
                code_path, transform_path.parent
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "Browser Interactive Transform code must stay inside the "
                        "Transform definition folder",
                        str(code_path),
                        "code",
                        "browser_code_outside_transform_package",
                    )
                )
            for dependency in transform.code_dependencies:
                dependency_path = _code_path(transform_path, dependency)
                if not _is_within(dependency_path, dashboard.root):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Interactive Transform code dependency must stay inside its Dashboard folder",
                            str(dependency_path),
                            "code_dependencies",
                            "code_dependency_outside_dashboard",
                        )
                    )
                elif not dependency_path.exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Interactive Transform code dependency does not exist",
                            str(dependency_path),
                            "code_dependencies",
                            "interactive_code_dependency_missing",
                        )
                    )
                elif transform.runtime in {"browser-js", "browser-python"} and not _is_within(
                    dependency_path, transform_path.parent
                ):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "Browser code dependency must stay inside the Transform "
                            "definition folder",
                            str(dependency_path),
                            "code_dependencies",
                            "browser_dependency_outside_transform_package",
                        )
                    )
            if transform.runtime == "server-python":
                for dependency in transform.python_dependencies:
                    if message := _python_dependency_error(dependency):
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                message,
                                str(transform_path),
                                "python_dependencies",
                                "python_dependency_unavailable",
                            )
                        )
            elif transform.runtime == "browser-python":
                for dependency in transform.python_dependencies:
                    result = _browser_python_dependency_diagnostic(
                        dependency, workspace.definition.runtime.pyodide_version
                    )
                    if result:
                        level, code, message = result
                        diagnostics.append(
                            Diagnostic(
                                level,
                                message,
                                str(transform_path),
                                "python_dependencies",
                                code,
                                {"dependency": dependency},
                            )
                        )
            _validate_query_inputs(
                transform.query_inputs,
                parameter_definitions=parameter_definitions,
                definition_path=transform_path,
                diagnostics=diagnostics,
            )
            for alias, control_key in transform.compute_inputs.items():
                if control_key not in compute_control_keys:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown Compute Control: {control_key}",
                            str(transform_path),
                            f"compute_inputs.{alias}",
                            "interactive_compute_control_unknown",
                        )
                    )
            for alias, control_key in transform.selection_inputs.items():
                if control_key not in selection_control_keys:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Unknown Selection Control: {control_key}",
                            str(transform_path),
                            f"selection_inputs.{alias}",
                            "interactive_selection_control_unknown",
                        )
                    )
            for name, reference in transform.inputs.items():
                message = _reference_error(
                    reference,
                    sources=dashboard.sources,
                    dataset_transforms=dashboard.dataset_transforms,
                    interactive_transforms=dashboard.interactive_transforms,
                    allow_interactive=True,
                )
                if message:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Input {name}: {message}",
                            str(transform_path),
                            f"inputs.{name}",
                        )
                    )
            for name in transform.input_schemas:
                if name not in transform.inputs:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Input schema references undeclared input: {name}",
                            str(transform_path),
                            f"input_schemas.{name}",
                            "interactive_input_schema_unknown",
                        )
                    )

        # Recovery-only diagnostics for a graph that could not be compiled. A
        # valid Dashboard never builds a second runtime DAG here.
        dataset_graph: dict[str, set[str]] = (
            {}
            if dependency_contract
            else {
                transform_id: {
                    parsed.node_id.split(":", 1)[1]
                    for reference in transform.inputs.values()
                    if (parsed := _safe_output_reference(reference)) is not None
                    and parsed.node_id.startswith("dataset:")
                    and parsed.node_id.split(":", 1)[1] in dashboard.dataset_transforms
                }
                for transform_id, (_, transform) in dashboard.dataset_transforms.items()
            }
        )
        if cycle := _cycle_nodes(dataset_graph):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Dataset Transform dependency graph contains a cycle: {', '.join(cycle)}",
                    definition_path,
                    "dataset_transforms",
                    "dataset_cycle",
                    {"nodes": cycle},
                )
            )

        interactive_graph: dict[str, set[str]] = (
            {}
            if dependency_contract
            else {
                transform_id: {
                    parsed.node_id.split(":", 1)[1]
                    for reference in transform.inputs.values()
                    if (parsed := _safe_output_reference(reference)) is not None
                    and parsed.node_id.startswith("interactive:")
                    and parsed.node_id.split(":", 1)[1] in dashboard.interactive_transforms
                }
                for transform_id, (_, transform) in dashboard.interactive_transforms.items()
            }
        )
        if cycle := _cycle_nodes(interactive_graph):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"Interactive Transform dependency graph contains a cycle: {', '.join(cycle)}",
                    definition_path,
                    "interactive_transforms",
                    "interactive_cycle",
                    {"nodes": cycle},
                )
            )

        for transform_id, (transform_path, transform) in dashboard.interactive_transforms.items():
            ancestors = (
                dependency_contract.interactive_ancestors(transform_id)
                if dependency_contract is not None
                else set()
            )
            if transform.export.mode == "interactive":
                invalid_ancestors = []
                for ancestor in sorted(ancestors):
                    dependency = dashboard.interactive_transforms[ancestor][1]
                    stateful_snapshot = dependency.export.mode != "interactive" and bool(
                        dependency.compute_inputs or dependency.selection_inputs
                    )
                    unavailable = dependency.export.mode == "unavailable"
                    if stateful_snapshot or unavailable:
                        invalid_ancestors.append(ancestor)
                if invalid_ancestors:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "An interactive export cannot depend on stateful snapshot/unavailable "
                            "Interactive Transforms: " + ", ".join(invalid_ancestors),
                            str(transform_path),
                            "export.mode",
                            "interactive_export_dependency_not_portable",
                            {"dependency_chain": invalid_ancestors},
                        )
                    )

            if (
                transform.runtime == "browser-python"
                and transform.export.assets == "bundle"
                and not workspace.definition.runtime.pyodide_bundle_path
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "browser-python export.assets=bundle requires "
                        "workspace runtime.pyodide_bundle_path",
                        str(transform_path),
                        "export.assets",
                        "pyodide_bundle_not_configured",
                    )
                )

        browser_python_asset_modes = {
            transform.export.assets
            for _, transform in dashboard.interactive_transforms.values()
            if transform.runtime == "browser-python"
            and transform.export.mode != "unavailable"
            and transform.export.assets is not None
        }
        if len(browser_python_asset_modes) > 1:
            diagnostics.append(
                Diagnostic(
                    "error",
                    "All browser-python Interactive Transforms in one Dashboard must "
                    "use the same export.assets policy",
                    definition_path,
                    "interactive_transforms",
                    "pyodide_asset_policy_ambiguous",
                    {"policies": sorted(browser_python_asset_modes)},
                )
            )

        trigger_consumers: dict[str, list[tuple[str, str]]] = {
            control_key: [] for control_key in compute_control_keys
        }
        for transform_id, (_, transform) in dashboard.interactive_transforms.items():
            for control_key in transform.compute_inputs.values():
                trigger_consumers.setdefault(control_key, []).append(
                    (transform_id, transform.trigger)
                )
        for control_key, consumers in trigger_consumers.items():
            triggers = {trigger for _, trigger in consumers}
            if len(triggers) > 1:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Compute Control {control_key} has consumers with incompatible "
                        f"triggers: {', '.join(sorted(triggers))}",
                        definition_path,
                        "controls",
                        "compute_trigger_ambiguous",
                        {
                            "control": control_key,
                            "consumers": [
                                {"transform": identifier, "trigger": trigger}
                                for identifier, trigger in consumers
                            ],
                        },
                    )
                )

        for view in dashboard.definition.views:
            for name, reference in view.input_refs.items():
                message = _reference_error(
                    reference,
                    sources=dashboard.sources,
                    dataset_transforms=dashboard.dataset_transforms,
                    interactive_transforms=dashboard.interactive_transforms,
                    allow_interactive=True,
                )
                if message:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"View {view.id} input {name}: {message}",
                            definition_path,
                            "views.inputs",
                        )
                    )
                elif name == "main":
                    output_kind = _reference_kind(reference, dashboard)
                    output_definition = _reference_output_definition(reference, dashboard)
                    table_templates = {
                        "line",
                        "bar",
                        "stacked-bar",
                        "pie",
                        "scatter",
                        "heatmap",
                        "radar",
                        "table",
                        "perspective",
                    }
                    if view.template in table_templates and output_kind not in {None, "table"}:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"View {view.id} template {view.template} requires a table input, got {output_kind}",
                                definition_path,
                                "views.input",
                            )
                        )
                    if view.template == "metric" and output_kind == "table" and not view.value:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"View {view.id} metric requires value for a table input",
                                definition_path,
                                "views.value",
                            )
                        )
                    if (
                        output_kind == "table"
                        and output_definition is not None
                        and output_definition.schema_
                    ):
                        declared_fields = {column.name for column in output_definition.schema_}
                        unknown_fields = sorted(referenced_view_fields(view) - declared_fields)
                        if unknown_fields:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    f"View {view.id} references undeclared table fields: "
                                    + ", ".join(unknown_fields),
                                    definition_path,
                                    "views",
                                    "view_field_unknown",
                                    {
                                        "view": view.id,
                                        "reference": reference,
                                        "unknown": unknown_fields,
                                        "declared": sorted(declared_fields),
                                    },
                                )
                            )
                        selection_fields = {
                            field
                            for item in control_contract.get(view.id, [])
                            if item.kind == "selection" and item.binding is not None
                            for field in (
                                item.definition.path_fields or [item.binding.field or item.id]
                            )
                        }
                        unknown_selection_fields = sorted(selection_fields - declared_fields)
                        if unknown_selection_fields:
                            diagnostics.append(
                                Diagnostic(
                                    "error",
                                    f"View {view.id} Selection contract references "
                                    "undeclared table fields: "
                                    + ", ".join(unknown_selection_fields),
                                    definition_path,
                                    "views.selection_bindings",
                                    "selection_field_unknown",
                                    {
                                        "view": view.id,
                                        "reference": reference,
                                        "unknown": unknown_selection_fields,
                                        "declared": sorted(declared_fields),
                                    },
                                )
                            )

        for reference in dashboard.definition.canvas.inputs:
            message = _reference_error(
                reference,
                sources=dashboard.sources,
                dataset_transforms=dashboard.dataset_transforms,
                interactive_transforms=dashboard.interactive_transforms,
                allow_interactive=True,
            )
            if message:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Canvas input: {message}",
                        definition_path,
                        "canvas.inputs",
                    )
                )

        section_ids: set[str] = set()
        assigned_views: set[str] = set()
        repeat_templates = {"small-multiples", "selection-gallery"}
        for section in dashboard.definition.sections:
            if section.id in section_ids:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Duplicate section id: {section.id}",
                        definition_path,
                        "sections",
                    )
                )
            section_ids.add(section.id)
            if section.template in repeat_templates and not section.repeat:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Section {section.id} template {section.template} requires repeat",
                        definition_path,
                        "sections.repeat",
                    )
                )
            if section.repeat and section.template not in repeat_templates:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Section {section.id} repeat requires a repeat Section template",
                        definition_path,
                        "sections.template",
                    )
                )
            for view_id in section.views:
                if view_id not in view_ids:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Section references unknown View: {view_id}",
                            definition_path,
                            "sections.views",
                        )
                    )
                if view_id in assigned_views:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"View belongs to more than one Section: {view_id}",
                            definition_path,
                            "sections.views",
                        )
                    )
                assigned_views.add(view_id)
            if section.repeat:
                repeat_view = section.repeat.view or (section.views[0] if section.views else None)
                if repeat_view not in section.views:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Section {section.id} repeat View must appear in sections.views",
                            definition_path,
                            "sections.repeat.view",
                        )
                    )
                if len(section.views) != 1:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Section {section.id} repeat supports exactly one View blueprint",
                            definition_path,
                            "sections.views",
                        )
                    )
                if section.repeat.input:
                    message = _reference_error(
                        section.repeat.input,
                        sources=dashboard.sources,
                        dataset_transforms=dashboard.dataset_transforms,
                        interactive_transforms=dashboard.interactive_transforms,
                        allow_interactive=True,
                    )
                    if message:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Section {section.id} repeat input: {message}",
                                definition_path,
                                "sections.repeat.input",
                            )
                        )
                if section.template == "selection-gallery":
                    selection_ids = {
                        item.id for item in section.controls if item.kind == "selection"
                    }
                    if not selection_ids:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Section {section.id} selection-gallery requires a Section Control with kind=selection",
                                definition_path,
                                "sections.controls",
                            )
                        )
                    elif section.repeat.selection and section.repeat.selection not in selection_ids:
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                f"Section {section.id} repeat references an unknown Section Control with kind=selection",
                                definition_path,
                                "sections.repeat.selection",
                            )
                        )

        for view_id, controls in control_contract.items():
            ids = [item.id for item in controls]
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            if duplicates:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Control ids shadow each other for View {view_id}: {', '.join(duplicates)}",
                        definition_path,
                        "controls",
                    )
                )
            view = dashboard.views[view_id]
            selection_ids = {item.id for item in controls if item.kind == "selection"}
            for selection_id in sorted(set(view.selection_bindings) - selection_ids):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"View {view_id} binds unknown Selection: {selection_id}",
                        definition_path,
                        "selection_bindings",
                    )
                )

        canvas = dashboard.definition.canvas
        for field in ("template",):
            value = getattr(canvas, field)
            if value and not (dashboard.root / value).exists():
                diagnostics.append(
                    Diagnostic(
                        "error",
                        f"Canvas {field} does not exist",
                        str(dashboard.root / value),
                        f"canvas.{field}",
                    )
                )
        for field, values in (("styles", canvas.styles), ("scripts", canvas.scripts)):
            for value in values:
                if not (dashboard.root / value).exists():
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            f"Presentation asset does not exist: {value}",
                            str(dashboard.root / value),
                            f"canvas.{field}",
                            "presentation_asset_missing",
                        )
                    )
    return diagnostics


def dashboard_validation_diagnostics(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
) -> list[Diagnostic]:
    """Return global and dashboard-local diagnostics without leaking sibling failures."""
    other_roots = [
        entry.path.resolve()
        for entry in workspace.catalog
        if entry.path.resolve() != dashboard.root.resolve()
    ]
    selected: list[Diagnostic] = []
    for diagnostic in validate_workspace(workspace):
        if not diagnostic.file:
            selected.append(diagnostic)
            continue
        raw = Path(diagnostic.file).expanduser()
        path = raw.resolve() if raw.is_absolute() else (workspace.root / raw).resolve()
        if _is_within(path, dashboard.root):
            selected.append(diagnostic)
        elif not any(_is_within(path, root) for root in other_roots):
            selected.append(diagnostic)
    return selected
