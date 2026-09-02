from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Any, Literal

from dataviz.analysis.browser import run_browser_outputs
from dataviz.analysis.catalog import ensure_analysis_catalog
from dataviz.analysis.contracts import validate_analysis_result_producer
from dataviz.analysis.inspection import analysis_reference_closure
from dataviz.analysis.overlay import build_analysis_variant
from dataviz.analysis.results import AnalysisResultStore
from dataviz.analysis.usage import (
    output_analysis_usage,
    record_usage_best_effort,
)
from dataviz.artifacts import ArtifactStore
from dataviz.auth import AdapterResolver
from dataviz.errors import DatavizError, ValidationFailure
from dataviz.execution import (
    Executor,
    InteractionExecutor,
    resolve_dashboard_query_parameter_state,
)
from dataviz.execution.plan import compile_plan
from dataviz.execution.references import parse_output_reference
from dataviz.execution.outputs import validate_output_destination
from dataviz.filesystem import sha256_file
from dataviz.input_state import state_from_values
from dataviz.protocols import ANALYSIS_RESULT_SCHEMA
from dataviz.rendering import CanvasRenderer
from dataviz.state_snapshot import (
    applied_control_state_for_consumers,
    applied_revisions_for_consumers,
    normalize_consumer_revisions,
)
from dataviz.target_reference import parse_target_reference
from dataviz.workspace import load_workspace
from dataviz.workspace.assets import resolve_workspace_asset_reference
from dataviz.workspace.controls import scoped_control_registry
from dataviz.workspace.loading.loaded_types import LoadedWorkspace


RunRuntime = Literal["auto", "server", "browser"]
RunDetail = Literal["summary", "debug", "full"]


@dataclass(frozen=True, slots=True)
class RunRequest:
    """One explicit, immutable Target execution request.

    The request contains canonical application values. CLI syntax and HTTP payload
    parsing belong to their adapters and are intentionally absent here.
    """

    workspace: Path
    target: str
    also: tuple[str, ...] = ()
    query_parameter_state: dict[str, Any] = field(default_factory=dict)
    controls: dict[str, Any] = field(default_factory=dict)
    output_name: str | None = None
    runtime: RunRuntime = "auto"
    preview_rows: int = 10
    refresh: bool = False
    refresh_catalog: bool = False
    allow_network: bool = False
    timeout_seconds: float = 60.0
    detail: RunDetail = "summary"
    overlay: Path | None = None
    dry_run: bool = False
    from_result_id: str | None = None


def analysis_entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        key: entry.get(key)
        for key in (
            "schema",
            "reference",
            "kind",
            "stage",
            "title",
            "purpose",
            "grain",
            "caveats",
            "visibility",
            "assurance",
            "time",
            "measures",
            "relationships",
            "semantic_source",
            "semantic_status",
            "semantic_missing",
            "trust_status",
            "runtime",
            "source_type",
            "query_parameters",
            "parameter_contracts",
            "controls",
            "control_contracts",
            "output",
            "outputs",
            "inputs",
            "base_inputs",
            "upstream_outputs",
            "downstream_views",
            "match_reasons",
            "equivalence_hash",
            "representative",
            "occurrence_count",
            "references",
            "usage",
        )
        if entry.get(key) not in (None, "", (), [])
    } | {"dashboard": entry["dashboard"]}


def _invalid(message: str, *, code: str = "analysis_run_request_invalid") -> None:
    raise ValidationFailure(message, details={"code": code})


def _local_reference(entry: dict[str, Any]) -> str:
    return entry["reference"].split("::", 1)[1]


def _reachable_nodes(dashboard, entry: dict[str, Any]) -> set[str]:
    references = (
        entry.get("inputs", {}).values()
        if entry.get("kind") == "view"
        else [entry["reference"]]
    )
    return analysis_reference_closure(dashboard, references)


def _overlay_payload(variant) -> dict[str, Any]:
    return {
        "schema": "dataviz/analysis-overlay-result/v1",
        "analysis_run_id": variant.analysis_run_id,
        "overlay_hash": variant.overlay_hash,
        "manifest": str(variant.manifest_path),
        "changes": variant.manifest["changes"],
    }


def _target_payload(
    requested: dict[str, Any], executed: dict[str, Any]
) -> dict[str, Any]:
    payload: dict[str, Any] = {"target": analysis_entry_summary(requested)}
    if requested["reference"] != executed["reference"]:
        payload["resolved_target"] = analysis_entry_summary(executed)
        payload["presentation"] = requested.get("presentation", {})
        payload["view_input"] = {
            name: reference
            for name, reference in requested.get("inputs", {}).items()
            if reference == executed["reference"]
        }
    return payload


def analysis_artifact_value(store: ArtifactStore, artifact, limit: int) -> tuple[Any, bool]:
    value = store.read_value(artifact)
    truncated = False
    if artifact.kind == "table":
        frame = value.head(limit)
        truncated = int(artifact.metadata.get("row_count", 0)) > limit
        value = json.loads(frame.to_json(orient="records", date_format="iso"))
    return value, truncated


def _artifact_evidence(reference: str, artifact) -> dict[str, Any]:
    return {
        "reference": reference,
        "artifact_id": artifact.artifact_id,
        "kind": artifact.kind,
        "rows": artifact.metadata.get("row_count"),
        "content_hash": artifact.content_hash,
    }


def _finite_state_summary(state: dict[str, Any], *, limit: int = 20) -> dict[str, Any]:
    raw = state.get("value")
    values = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
    return {
        **({"selection": state["selection"]} if "selection" in state else {}),
        "operand_count": len(values),
        "operands": values[:limit],
        "operands_truncated": len(values) > limit,
    }


def _execution_diagnostics(dashboard, query_result, interactions=()) -> dict[str, Any]:
    """Project only empty/failure causes proven by completed execution records."""

    evidence: list[dict[str, Any]] = []
    for node_id, node in query_result.nodes.items():
        if node.status == "empty":
            reason = "source_zero_rows" if node.node_type == "source" else "transform_zero_rows"
            item: dict[str, Any] = {"reason": reason, "node": node_id}
            query = node.diagnostics.get("query") if isinstance(node.diagnostics, dict) else None
            if isinstance(query, dict) and query.get("query_filters"):
                item["filters"] = {
                    key: {
                        name: value.get(name)
                        for name in ("parameter", "selection", "predicate")
                        if value.get(name) is not None
                    }
                    for key, value in query["query_filters"].items()
                }
            evidence.append(item)
        elif node.status == "unavailable" and (node.error or {}).get("type") == "dependency_failed":
            evidence.append({"reason": "upstream_failed", "node": node_id})
    for interaction in interactions:
        for node_id, node in interaction.nodes.items():
            if node.status == "empty":
                transform_id = node_id.split(":", 1)[-1]
                bindings = dashboard.dependency_contract.interactive_control_inputs.get(
                    transform_id, {}
                )
                filters = {
                    alias: {
                        "control": binding["control"],
                        **_finite_state_summary(
                            interaction.control_state.get(binding["control"], {})
                        ),
                    }
                    for alias, binding in bindings.items()
                    if binding.get("mode") == "filter"
                }
                evidence.append(
                    {
                        "reason": "control_filter_zero_rows" if filters else "transform_zero_rows",
                        "node": node_id,
                        **({"filters": filters} if filters else {}),
                    }
                )
            elif node.status == "unavailable" and (node.error or {}).get("type") == "dependency_failed":
                evidence.append({"reason": "upstream_failed", "node": node_id})
    return {"empty": evidence} if evidence else {}


def analysis_artifact_payload(
    *,
    entry: dict[str, Any],
    artifact,
    value: Any,
    truncated: bool,
    run_id: str,
    duration_ms: int | None,
) -> dict[str, Any]:
    return {
        "reference": entry["reference"],
        "kind": artifact.kind,
        "rows": artifact.metadata.get("row_count"),
        "schema": artifact.schema_ or [],
        "content_hash": artifact.content_hash,
        "duration_ms": duration_ms,
        "preview": value,
        "truncated": truncated,
        "run_id": run_id,
    }


def analysis_artifact_binding(loaded, dashboard, entry, store, artifact) -> dict[str, Any]:
    node_id = str(entry.get("node_id") or "")
    if node_id.startswith("source:"):
        source_id = node_id.split(":", 1)[1]
        definition_path, definition = dashboard.sources[source_id]
        if definition.type == "file":
            if definition.adapter:
                path = AdapterResolver(loaded.root).resolve_path(
                    definition.adapter,
                    definition.path,
                    dashboard.definition.adapters,
                )
            else:
                asset = resolve_workspace_asset_reference(
                    loaded.root,
                    loaded.definition.assets,
                    definition.path,
                    hash_content=False,
                )
                path = asset.path if asset is not None else (
                    definition_path.parent / definition.path
                ).resolve()
            return {
                "source_path": path,
                "format": definition.format or path.suffix.lstrip(".").lower(),
                "options": definition.options,
                "content_hash": sha256_file(path),
            }
    return {
        "artifact_path": store.resolve(artifact),
        "format": artifact.format,
        "content_hash": artifact.content_hash,
    }


def _record_success(workspace: Path, entries: list[dict[str, Any]]) -> None:
    references = {
        entry["reference"]
        for entry in entries
        if entry.get("kind") in {"base_output", "derived_output"}
    }
    for reference in sorted(references):
        record_usage_best_effort(workspace, output_analysis_usage(reference))


def seal_analysis_result(
    workspace: Path,
    payload: dict[str, Any],
    bindings: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Validate and publish one immutable Result through the canonical Store."""

    normalized = dict(payload)
    if normalized.get("status") == "error":
        normalized["status"] = "failed"
    validated = validate_analysis_result_producer(normalized)
    published = AnalysisResultStore(workspace).publish(validated, bindings)
    return validate_analysis_result_producer(published)


def _seal_failure(
    request: RunRequest,
    *,
    target: dict[str, Any],
    generation: str | None,
    query_parameter_state: dict[str, Any],
    effective_controls: dict[str, Any] | None = None,
    error: dict[str, Any],
    status: Literal["failed", "cancelled"] = "failed",
    lineage: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return seal_analysis_result(
        request.workspace,
        {
            "schema": ANALYSIS_RESULT_SCHEMA,
            "status": status,
            "generation": generation,
            "target": analysis_entry_summary(target),
            "query_parameter_state": query_parameter_state,
            "effective_controls": effective_controls or {},
            "outputs": [],
            "lineage": lineage or {},
            "provenance": provenance or {},
            "timing": {},
            "error": error,
        },
        {},
    )


def _preflight_request(request: RunRequest) -> None:
    if request.runtime not in {"auto", "server", "browser"}:
        _invalid("--runtime must be auto, server, or browser")
    if request.detail not in {"summary", "debug", "full"}:
        _invalid("--detail must be summary, debug, or full")
    if request.preview_rows < 1:
        _invalid("preview_rows must be at least 1")
    if request.timeout_seconds <= 0:
        _invalid("timeout_seconds must be positive")
    if request.dry_run and request.overlay is None:
        _invalid("--dry-run requires --overlay")
    if request.from_result_id and request.overlay is not None:
        _invalid("--from-result cannot be combined with --overlay")


def _output_definition(dashboard, reference: str):
    parsed = parse_output_reference(reference)
    kind, identifier = parsed.node_id.split(":", 1)
    if kind == "source":
        definition = dashboard.sources[identifier][1]
    elif kind == "dataset":
        definition = dashboard.dataset_transforms[identifier][1]
    else:
        raise ValidationFailure(
            f"Result input must be a base Named Output: {reference}",
            details={"code": "analysis_result_input_kind_invalid", "reference": reference},
        )
    return definition.outputs[parsed.output]


def _result_seed_inputs(request: RunRequest, dashboard, entry) -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]
]:
    result_id = request.from_result_id
    assert result_id is not None
    node_id = str(entry.get("node_id") or "")
    if entry.get("kind") != "base_output" or not node_id.startswith("dataset:"):
        _invalid(
            "--from-result currently supports Dataset Transform Outputs only",
            code="analysis_from_result_target_invalid",
        )
    if request.query_parameter_state:
        _invalid(
            "--from-result restores the input Result Query Parameters; do not pass --query-param",
            code="analysis_from_result_parameter_override",
        )
    input_references = dashboard.dependency_contract.data_inputs[node_id]
    store = AnalysisResultStore(request.workspace)
    with store.lease(result_id):
        manifest = store.load(result_id)
        previous = manifest.get("result") or {}
        if previous.get("status") not in {"ready", "partial"}:
            raise ValidationFailure(
                "Only a ready/partial Result can provide Transform inputs",
                details={
                    "code": "analysis_from_result_not_ready",
                    "result_id": result_id,
                    "status": previous.get("status"),
                },
            )
        available = {
            str(item.get("reference", "")).split("::", 1)[-1]: item
            for item in previous.get("outputs", [])
        }
        seeds: dict[str, dict[str, Any]] = {}
        provenance_inputs: list[dict[str, Any]] = []
        for alias, reference in input_references.items():
            output = available.get(reference)
            if output is None:
                raise ValidationFailure(
                    f"Result {result_id} does not contain required input {reference}",
                    details={
                        "code": "analysis_from_result_input_missing",
                        "result_id": result_id,
                        "input": alias,
                        "reference": reference,
                        "available": sorted(available),
                    },
                )
            expected = _output_definition(dashboard, reference)
            if output.get("kind") != expected.kind:
                raise ValidationFailure(
                    f"Result input {reference} is {output.get('kind')}, expected {expected.kind}",
                    details={
                        "code": "analysis_from_result_kind_mismatch",
                        "reference": reference,
                        "expected": expected.kind,
                        "actual": output.get("kind"),
                    },
                )
            expected_schema = [
                item.model_dump(mode="json") for item in (expected.schema_ or [])
            ]
            actual_schema = list(output.get("schema") or [])
            if expected_schema and actual_schema and expected_schema != actual_schema:
                raise ValidationFailure(
                    f"Result input {reference} Schema differs from the current Output contract",
                    details={
                        "code": "analysis_from_result_schema_mismatch",
                        "reference": reference,
                        "expected": expected_schema,
                        "actual": actual_schema,
                    },
                )
            rows = output.get("rows")
            limit = max(1, int(rows)) if isinstance(rows, int) else 2_147_483_647
            value, total = store.read_output(manifest, output, limit=limit)
            if total is not None and rows is not None and total != rows:
                raise ValidationFailure(
                    f"Result input {reference} row count changed while reading",
                    details={"code": "analysis_from_result_row_count_mismatch"},
                )
            seeds[reference] = {
                "value": value,
                "result_id": result_id,
                "reference": output.get("reference"),
                "content_hash": output.get("content_hash"),
            }
            provenance_inputs.append(
                {
                    "alias": alias,
                    "reference": output.get("reference"),
                    "kind": output.get("kind"),
                    "rows": output.get("rows"),
                    "content_hash": output.get("content_hash"),
                }
            )
        query_state = dict(previous.get("query_parameter_state") or {})
    return query_state, seeds, {
        "result_id": result_id,
        "inputs": provenance_inputs,
    }


def _resolve_parameters(loaded, dashboard, states: dict[str, Any]):
    timezone_name = loaded.definition.context.timezone
    resolved = resolve_dashboard_query_parameter_state(
        dashboard,
        states,
        timezone_name=timezone_name,
    )
    return resolved


def _run_dashboard(
    request: RunRequest,
    loaded: LoadedWorkspace,
    catalog,
    dashboard_id: str,
) -> dict[str, Any]:
    if any((
        request.also,
        request.controls,
        request.output_name,
        request.overlay,
        request.dry_run,
        request.from_result_id,
    )):
        _invalid(
            "Dashboard targets do not accept --also, --control, --output, --overlay, or --from-result"
        )
    executor = Executor(loaded)
    dashboard = executor.ensure_valid(dashboard_id)
    query_state = _resolve_parameters(loaded, dashboard, request.query_parameter_state)
    compile_plan(dashboard, targets=None)
    target = {
        "reference": dashboard_id,
        "kind": "dashboard",
        "title": dashboard.title,
        "dashboard": {
            "id": dashboard_id,
            "title": dashboard.title,
            "path": dashboard.root.relative_to(loaded.root).as_posix(),
        },
    }

    started = time.perf_counter()
    try:
        execution = executor.run(
            dashboard_id,
            query_parameter_state=query_state,
            refresh=request.refresh,
            _dashboard=dashboard,
        )
    except BaseException as exc:
        cancelled = isinstance(exc, KeyboardInterrupt) or exc.__class__.__name__ == "Abort"
        error = (
            {"code": "execution_cancelled", "message": "Execution cancelled"}
            if cancelled
            else exc.as_dict()
            if isinstance(exc, DatavizError)
            else {"type": type(exc).__name__, "message": str(exc)}
        )
        try:
            return _seal_failure(
                request,
                target=target,
                generation=catalog.generation,
                query_parameter_state=query_state,
                error=error,
                status="cancelled" if cancelled else "failed",
            )
        except Exception:
            raise exc from None
    store = ArtifactStore(loaded.root, execution.run_id)
    outputs: list[dict[str, Any]] = []
    bindings: dict[str, dict[str, Any]] = {}
    for local_reference, artifact in sorted(execution.outputs.items()):
        canonical = f"{dashboard_id}::{local_reference}"
        try:
            entry = catalog.resolve(canonical)
        except Exception:
            continue
        value, truncated = analysis_artifact_value(store, artifact, request.preview_rows)
        node = execution.nodes.get(local_reference.split("/", 1)[0])
        outputs.append(
            analysis_artifact_payload(
                entry=entry,
                artifact=artifact,
                value=value,
                truncated=truncated,
                run_id=execution.run_id,
                duration_ms=node.duration_ms if node else None,
            )
        )
        bindings[canonical] = analysis_artifact_binding(
            loaded, dashboard, entry, store, artifact
        )
    if execution.status in {"ready", "partial"}:
        report_source = (
            loaded.root / ".dataviz" / "runs" / execution.run_id / "dashboard-result.html"
        )
        try:
            CanvasRenderer(loaded).write_report(dashboard, execution, report_source)
            bindings["__report__"] = {"source_path": report_source}
        except Exception:
            pass
    payload: dict[str, Any] = {
        "schema": ANALYSIS_RESULT_SCHEMA,
        "status": execution.status,
        "generation": catalog.generation,
        "target": target,
        "query_parameter_state": execution.query_parameter_state,
        "effective_controls": {},
        "outputs": outputs,
        "lineage": {
            "query_nodes": execution.query_nodes,
            "query_targets": execution.query_targets,
        },
        "provenance": {
            "catalog_generation": catalog.generation,
            "query_contract_hash": execution.query_contract_hash,
            "artifacts": [
                _artifact_evidence(reference, artifact)
                for reference, artifact in sorted(execution.outputs.items())
            ],
        },
        "renderability": {
            "kind": "dashboard",
            "renderable": execution.status in {"ready", "partial"},
            "dashboard": dashboard_id,
        },
        "timing": {"query_ms": round((time.perf_counter() - started) * 1000, 2)},
        "diagnostics": _execution_diagnostics(dashboard, execution),
    }
    failed_nodes = [node for node in execution.nodes.values() if node.status == "error"]
    if failed_nodes:
        payload["error"] = failed_nodes[0].error
    if request.detail == "full":
        payload["execution"] = execution.model_dump(mode="json", by_alias=True)
    elif request.detail == "debug":
        payload["nodes"] = {
            key: value.model_dump(mode="json", by_alias=True)
            for key, value in execution.nodes.items()
        }
    return seal_analysis_result(request.workspace, payload, bindings)


def _resolve_target_entries(request: RunRequest, catalog):
    parsed = parse_target_reference(request.target)
    if parsed.kind == "dashboard":
        return parsed, None, None, []
    entry = catalog.resolve(parsed.canonical)
    requested = entry
    additional = [
        catalog.resolve(parse_target_reference(value).canonical)
        for value in request.also
    ]
    if entry["kind"] == "view":
        inputs = entry.get("inputs", {})
        if request.output_name is not None:
            if request.output_name not in inputs:
                _invalid("Unknown View input; choose " + "|".join(sorted(inputs)))
            view_entries = [catalog.resolve(inputs[request.output_name])]
        else:
            view_entries = [catalog.resolve(value) for value in inputs.values()]
        if not view_entries:
            _invalid("This View has no executable data inputs")
        entry = view_entries[0]
        additional = [*view_entries[1:], *additional]
    if additional:
        batch = [entry, *additional]
        if len({item["dashboard"]["id"] for item in batch}) != 1:
            _invalid("--also targets must belong to the same Dashboard")
        kinds = {item["kind"] for item in batch}
        if kinds == {"base_output"}:
            pass
        elif kinds == {"derived_output"}:
            groups = {
                "server" if item["runtime"] == "server-python" else "browser"
                for item in batch
            }
            if len(groups) != 1:
                _invalid("--also cannot mix top-level Server and Browser Derived Outputs")
        else:
            _invalid(
                "--also requires all targets to be Base Outputs or all to be Derived Outputs"
            )
    return parsed, requested, entry, additional


def _run_data_target(
    request: RunRequest,
    loaded: LoadedWorkspace,
    catalog,
    requested_entry: dict[str, Any],
    entry: dict[str, Any],
    additional_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    dashboard_id = entry["dashboard"]["id"]
    executor = Executor(loaded)
    dashboard = loaded.dashboard(dashboard_id)
    variant = None
    if request.overlay is not None:
        reachable_nodes = set().union(
            *(
                _reachable_nodes(dashboard, item)
                for item in [entry, *additional_entries]
            )
        )
        variant = build_analysis_variant(
            loaded,
            dashboard,
            request.overlay,
            reachable_nodes=reachable_nodes,
        )
        dashboard = variant.dashboard
        if request.dry_run:
            variant.write_manifest(
                status="explained",
                evidence={
                    "target": entry["reference"],
                    "reachable_nodes": sorted(reachable_nodes),
                },
            )
            return {
                "schema": "dataviz/analysis-overlay-explanation/v1",
                "status": "ready",
                **_target_payload(requested_entry, entry),
                "reachable_nodes": sorted(reachable_nodes),
                "overlay": _overlay_payload(variant),
            }

    seeded_outputs: dict[str, dict[str, Any]] = {}
    input_result_provenance: dict[str, Any] | None = None
    if request.from_result_id:
        query_state, seeded_outputs, input_result_provenance = _result_seed_inputs(
            request,
            dashboard,
            entry,
        )
        query_state = _resolve_parameters(loaded, dashboard, query_state)
    else:
        query_state = _resolve_parameters(loaded, dashboard, request.query_parameter_state)
    output_name = None if requested_entry.get("kind") == "view" else request.output_name
    executor_options = (
        {
            "cache_namespace": variant.cache_namespace,
            "cache_salt": variant.overlay_hash,
        }
        if variant is not None
        else {}
    )
    result_started = False
    if entry["kind"] in {"source", "base_output"}:
        if request.controls:
            _invalid("Base execution does not accept --control")
        if request.runtime == "browser":
            _invalid("Source and Base Outputs execute on the server")
        if entry["kind"] == "source":
            source_outputs = {
                value.rsplit("/", 1)[1]: value.split("::", 1)[1]
                for value in entry.get("outputs", ())
            }
            if output_name:
                if output_name not in source_outputs:
                    _invalid(
                        f"Unknown Source Output {output_name}; choose "
                        + "|".join(sorted(source_outputs))
                    )
                target_references = [source_outputs[output_name]]
            else:
                target_references = list(source_outputs.values())
        else:
            if output_name:
                _invalid("Base Output references already identify one output")
            target_references = [
                _local_reference(item) for item in [entry, *additional_entries]
            ]
        if variant is None:
            dashboard = executor.ensure_valid(dashboard_id)
        compile_plan(dashboard, targets=target_references)
        control_state = None
        declared_runtime = None
    elif entry["kind"] == "derived_output":
        declared_runtime = entry["runtime"]
        if request.runtime == "server" and declared_runtime != "server-python":
            _invalid(f"{declared_runtime} requires --runtime browser or auto")
        if request.runtime == "browser" and declared_runtime == "server-python":
            _invalid("server-python requires --runtime server or auto")
        execution_entries = [entry, *additional_entries]
        if declared_runtime != "server-python":
            for item in execution_entries:
                transform_id = item["node_id"].split(":", 1)[1]
                output_definition = dashboard.interactive_transforms[transform_id][1].outputs[
                    item["output_name"]
                ]
                validate_output_destination(
                    producer_runtime="browser-js",
                    output_kind=output_definition.kind,
                    destination="cli_result",
                )
        controls = scoped_control_registry(dashboard.definition)
        unknown_controls = sorted(set(request.controls) - set(controls))
        if unknown_controls:
            _invalid("Unknown Control key: " + ", ".join(unknown_controls))
        control_state = state_from_values(
            dashboard.definition,
            request.controls,
            phase=(
                "canvas-hydration"
                if declared_runtime != "server-python"
                else "execution"
            ),
        )
        if variant is None:
            dashboard = executor.ensure_valid(dashboard_id)
        target_references = list(
            dict.fromkeys(
                value.split("::", 1)[1]
                for item in execution_entries
                for value in item.get("base_inputs", ())
            )
        )
        compile_plan(dashboard, targets=target_references)
    else:
        _invalid(f"Analysis target cannot be executed: {entry['kind']}")

    if variant is not None:
        variant.write_manifest(
            status="running",
            evidence={"target": entry["reference"]},
        )
    try:
        started = time.perf_counter()
        result_started = True
        query_result = Executor(loaded, **executor_options).run(
            dashboard_id,
            query_parameter_state=query_state,
            targets=target_references,
            refresh=request.refresh,
            run_id=variant.analysis_run_id if variant is not None else None,
            seeded_outputs=seeded_outputs,
            _dashboard=dashboard,
        )
        query_ms = round((time.perf_counter() - started) * 1000, 2)
        if entry["kind"] in {"source", "base_output"}:
            published = _finish_base(
                request,
                loaded,
                catalog,
                dashboard,
                requested_entry,
                entry,
                additional_entries,
                query_result,
                target_references,
                query_ms,
                variant,
                input_result_provenance,
            )
        else:
            published = _finish_derived(
                request,
                loaded,
                catalog,
                dashboard,
                requested_entry,
                entry,
                additional_entries,
                query_result,
                control_state,
                declared_runtime,
                query_ms,
                variant,
                executor_options,
            )
        return published
    except BaseException as exc:
        cancelled = isinstance(exc, KeyboardInterrupt) or exc.__class__.__name__ == "Abort"
        if variant is not None:
            variant.write_manifest(
                status="cancelled" if cancelled else "error",
                evidence={"error_type": type(exc).__name__, "message": str(exc)},
            )
        if not result_started:
            raise
        error = (
            {"code": "execution_cancelled", "message": "Execution cancelled"}
            if cancelled
            else exc.as_dict()
            if isinstance(exc, DatavizError)
            else {"type": type(exc).__name__, "message": str(exc)}
        )
        try:
            return _seal_failure(
                request,
                target=requested_entry,
                generation=catalog.generation,
                query_parameter_state=query_state,
                effective_controls=control_state or {},
                error=error,
                status="cancelled" if cancelled else "failed",
            )
        except Exception:
            raise exc from None


def _finish_base(
    request,
    loaded,
    catalog,
    dashboard,
    requested_entry,
    entry,
    additional_entries,
    result,
    target_references,
    query_ms,
    variant,
    input_result_provenance,
):
    artifacts = [(target, result.outputs.get(target)) for target in target_references]
    missing = [target for target, artifact in artifacts if artifact is None]
    if missing:
        node = result.nodes.get(missing[0].split("/", 1)[0])
        if variant is not None:
            variant.write_manifest(
                status="error",
                evidence={"run_id": result.run_id, "missing_outputs": missing},
            )
        return _seal_failure(
            request,
            target=requested_entry,
            generation=catalog.generation,
            query_parameter_state=result.query_parameter_state,
            error=node.error if node else {
                "code": "analysis_output_unavailable",
                "message": "Named Output was not produced",
            },
            lineage={
                "query_nodes": result.query_nodes,
                "query_targets": result.query_targets,
            },
            provenance={
                "query_contract_hash": result.query_contract_hash,
                **(
                    {"input_result": input_result_provenance}
                    if input_result_provenance
                    else {}
                ),
            },
        )
    store = ArtifactStore(loaded.root, result.run_id)
    outputs = []
    bindings: dict[str, dict[str, Any]] = {}
    for local_reference, artifact in artifacts:
        value, truncated = analysis_artifact_value(store, artifact, request.preview_rows)
        target_entry = catalog.resolve(f"{dashboard.definition.id}::{local_reference}")
        node = result.nodes.get(local_reference.split("/", 1)[0])
        outputs.append(
            analysis_artifact_payload(
                entry=target_entry,
                artifact=artifact,
                value=value,
                truncated=truncated,
                run_id=result.run_id,
                duration_ms=node.duration_ms if node else None,
            )
        )
        bindings[target_entry["reference"]] = analysis_artifact_binding(
            loaded, dashboard, target_entry, store, artifact
        )
    payload: dict[str, Any] = {
        "schema": ANALYSIS_RESULT_SCHEMA,
        "status": result.status,
        "generation": catalog.generation,
        **_target_payload(requested_entry, entry),
        "query_parameter_state": result.query_parameter_state,
        "effective_controls": {},
        "outputs": outputs,
        "lineage": {
            "query_nodes": result.query_nodes,
            "query_targets": result.query_targets,
        },
        "provenance": {
            "catalog_generation": catalog.generation,
            "definition_hash": entry.get("definition_hash"),
            "query_contract_hash": result.query_contract_hash,
            "artifacts": [
                _artifact_evidence(reference, artifact)
                for reference, artifact in sorted(result.outputs.items())
            ],
            **(
                {"input_result": input_result_provenance}
                if input_result_provenance
                else {}
            ),
        },
        "timing": {"query_ms": query_ms},
        "diagnostics": _execution_diagnostics(dashboard, result),
    }
    if variant is not None:
        payload["overlay"] = _overlay_payload(variant)
    if request.detail == "debug":
        payload["nodes"] = {
            key: value.model_dump(mode="json", by_alias=True)
            for key, value in result.nodes.items()
        }
    elif request.detail == "full":
        payload["execution"] = result.model_dump(mode="json", by_alias=True)
    if variant is not None:
        variant.write_manifest(status="ready", evidence={"run_id": result.run_id})
    _record_success(request.workspace, [entry, *additional_entries])
    return seal_analysis_result(request.workspace, payload, bindings)


def _finish_derived(
    request,
    loaded,
    catalog,
    dashboard,
    requested_entry,
    entry,
    additional_entries,
    run_result,
    control_state,
    declared_runtime,
    query_ms,
    variant,
    executor_options,
):
    execution_entries = [entry, *additional_entries]
    if declared_runtime != "server-python":
        browser_batch = run_browser_outputs(
            loaded,
            dashboard,
            run_result,
            targets=[
                (item["node_id"].split(":", 1)[1], item["output_name"])
                for item in execution_entries
            ],
            control_state=control_state,
            refresh=request.refresh,
            allow_network=request.allow_network,
            timeout_seconds=request.timeout_seconds,
            cache_salt=variant.overlay_hash if variant is not None else None,
        )
        bindings: dict[str, dict[str, Any]] = {}
        outputs = []
        for target_entry, extracted in zip(
            execution_entries, browser_batch["outputs"], strict=True
        ):
            rows = extracted["rows"]
            value = extracted["value"]
            outputs.append(
                {
                    "reference": target_entry["reference"],
                    "kind": extracted["kind"],
                    "rows": rows,
                    "schema": extracted["schema"],
                    "content_hash": extracted["content_hash"],
                    "transport": extracted.get("transport", "json"),
                    "duration_ms": browser_batch["duration_ms"],
                    "preview": (
                        value[: request.preview_rows]
                        if extracted["kind"] == "table"
                        else value
                    ),
                    "truncated": bool(rows is not None and rows > request.preview_rows),
                    "run_id": run_result.run_id,
                }
            )
            bindings[target_entry["reference"]] = {
                "value": value,
                "kind": extracted["kind"],
            }
        payload: dict[str, Any] = {
            "schema": ANALYSIS_RESULT_SCHEMA,
            "status": "ready",
            "generation": catalog.generation,
            **_target_payload(requested_entry, entry),
            "query_parameter_state": run_result.query_parameter_state,
            "effective_controls": control_state,
            "consumer_revisions": browser_batch["consumer_revisions"],
            "outputs": outputs,
            "lineage": {
                "query_nodes": run_result.query_nodes,
                "interactive_nodes": entry.get("upstream_outputs", [])
                + [entry["reference"]],
                "base_inputs": entry.get("base_inputs", []),
                "server_interactions": browser_batch["server_interactions"],
            },
            "provenance": {
                "catalog_generation": catalog.generation,
                "definition_hash": entry.get("definition_hash"),
                "query_contract_hash": run_result.query_contract_hash,
                "base_artifacts": [
                    _artifact_evidence(reference, artifact)
                    for reference, artifact in sorted(run_result.outputs.items())
                ],
                "runtime": declared_runtime,
            },
            "timing": {"query_ms": query_ms, **browser_batch["timing"]},
            "diagnostics": _execution_diagnostics(dashboard, run_result),
        }
        if variant is not None:
            payload["overlay"] = _overlay_payload(variant)
        if request.detail in {"debug", "full"}:
            payload["browser"] = {
                "timing": browser_batch["timing"],
                "metrics": browser_batch["metrics"],
                "console_errors": browser_batch["console_errors"],
                "network_allowed": request.allow_network,
            }
        if request.detail == "full":
            payload["execution"] = {
                "query": run_result.model_dump(mode="json", by_alias=True)
            }
        if variant is not None:
            variant.write_manifest(status="ready", evidence={"run_id": run_result.run_id})
        _record_success(request.workspace, execution_entries)
        return seal_analysis_result(request.workspace, payload, bindings)

    started = time.perf_counter()
    interaction_executor = InteractionExecutor(loaded, **executor_options)
    interactions = []
    for target_entry in execution_entries:
        transform_id = target_entry["node_id"].split(":", 1)[1]
        interaction = interaction_executor.execute(
            run_result,
            transform_id,
            control_state=control_state,
            refresh=request.refresh,
            _dashboard=dashboard,
        )
        local_reference = _local_reference(target_entry)
        artifact = interaction.outputs.get(local_reference)
        if artifact is None:
            node = interaction.nodes.get(target_entry["node_id"])
            if variant is not None:
                variant.write_manifest(
                    status="error",
                    evidence={
                        "run_id": run_result.run_id,
                        "interaction_status": interaction.status,
                        "target": target_entry["reference"],
                    },
                )
            return _seal_failure(
                request,
                target=requested_entry,
                generation=catalog.generation,
                query_parameter_state=run_result.query_parameter_state,
                effective_controls=control_state,
                error=node.error if node else {
                    "code": "analysis_output_unavailable",
                    "message": "Interactive Output was not produced",
                },
                lineage={
                    "query_nodes": run_result.query_nodes,
                    "interactive_nodes": list(interaction.nodes),
                },
                provenance={"query_contract_hash": run_result.query_contract_hash},
            )
        interactions.append((target_entry, interaction, artifact))
    interaction_ms = round((time.perf_counter() - started) * 1000, 2)
    store = ArtifactStore(loaded.root, run_result.run_id)
    outputs = []
    bindings: dict[str, dict[str, Any]] = {}
    for target_entry, interaction, artifact in interactions:
        value, truncated = analysis_artifact_value(store, artifact, request.preview_rows)
        node = interaction.nodes.get(target_entry["node_id"])
        outputs.append(
            analysis_artifact_payload(
                entry=target_entry,
                artifact=artifact,
                value=value,
                truncated=truncated,
                run_id=run_result.run_id,
                duration_ms=node.duration_ms if node else None,
            )
        )
        bindings[target_entry["reference"]] = analysis_artifact_binding(
            loaded, dashboard, target_entry, store, artifact
        )
    last_interaction = interactions[-1][1]
    interactive_nodes = list(
        dict.fromkeys(
            node_id
            for _target_entry, interaction, _artifact in interactions
            for node_id in interaction.nodes
        )
    )
    applied_revisions = applied_revisions_for_consumers(
        dashboard,
        last_interaction.control_state,
        transform_ids={
            node_id.split(":", 1)[1]
            for node_id in interactive_nodes
            if node_id.startswith("interactive:")
        },
    )
    applied_control_state = applied_control_state_for_consumers(
        dashboard,
        last_interaction.control_state,
        transform_ids={
            node_id.split(":", 1)[1]
            for node_id in interactive_nodes
            if node_id.startswith("interactive:")
        },
    )
    payload = {
        "schema": ANALYSIS_RESULT_SCHEMA,
        "status": "ready",
        "generation": catalog.generation,
        **_target_payload(requested_entry, entry),
        "query_parameter_state": run_result.query_parameter_state,
        "effective_controls": last_interaction.control_state,
        "consumer_revisions": normalize_consumer_revisions(
            dashboard,
            last_interaction.control_state,
            applied_revisions,
            applied_control_state,
        ),
        "outputs": outputs,
        "lineage": {
            "query_nodes": run_result.query_nodes,
            "interactive_nodes": interactive_nodes,
            "base_inputs": list(
                dict.fromkeys(
                    value
                    for target_entry in execution_entries
                    for value in target_entry.get("base_inputs", [])
                )
            ),
        },
        "provenance": {
            "catalog_generation": catalog.generation,
            "definition_hashes": {
                target_entry["reference"]: target_entry.get("definition_hash")
                for target_entry in execution_entries
            },
            "query_contract_hash": run_result.query_contract_hash,
            "base_artifacts": [
                _artifact_evidence(reference, artifact)
                for reference, artifact in sorted(run_result.outputs.items())
            ],
            "runtime": "server-python",
        },
        "timing": {"query_ms": query_ms, "interactive_ms": interaction_ms},
        "diagnostics": _execution_diagnostics(
            dashboard,
            run_result,
            [interaction for _target, interaction, _artifact in interactions],
        ),
    }
    if variant is not None:
        payload["overlay"] = _overlay_payload(variant)
    if request.detail == "debug":
        payload["nodes"] = {
            "query": {
                key: value.model_dump(mode="json", by_alias=True)
                for key, value in run_result.nodes.items()
            },
            "interactive": [
                {
                    "target": target_entry["reference"],
                    "nodes": {
                        key: value.model_dump(mode="json", by_alias=True)
                        for key, value in interaction.nodes.items()
                    },
                }
                for target_entry, interaction, _artifact in interactions
            ],
        }
    elif request.detail == "full":
        payload["execution"] = {
            "query": run_result.model_dump(mode="json", by_alias=True),
            "interactions": [
                interaction.model_dump(mode="json", by_alias=True)
                for _target_entry, interaction, _artifact in interactions
            ],
        }
    if variant is not None:
        variant.write_manifest(status="ready", evidence={"run_id": run_result.run_id})
    _record_success(request.workspace, execution_entries)
    return seal_analysis_result(request.workspace, payload, bindings)


def run_analysis(
    request: RunRequest,
    dependencies: LoadedWorkspace | None = None,
) -> dict[str, Any]:
    """Execute one explicit Target and return its canonical immutable Result.

    ``dependencies`` may provide one already-loaded immutable Workspace snapshot.
    It is deliberately not a service container or a second execution authority.
    """

    _preflight_request(request)
    workspace = request.workspace.resolve()
    loaded = dependencies or load_workspace(workspace)
    if loaded.root.resolve() != workspace:
        raise ValidationFailure(
            "Run dependencies do not belong to the requested Workspace",
            details={"code": "analysis_run_workspace_mismatch"},
        )
    catalog = ensure_analysis_catalog(workspace, refresh=request.refresh_catalog)
    parsed, requested, entry, additional = _resolve_target_entries(request, catalog)
    if parsed.kind == "dashboard":
        return _run_dashboard(request, loaded, catalog, parsed.dashboard)
    assert requested is not None and entry is not None
    return _run_data_target(
        request,
        loaded,
        catalog,
        requested,
        entry,
        additional,
    )


__all__ = [
    "RunRequest",
    "analysis_artifact_binding",
    "analysis_artifact_payload",
    "analysis_artifact_value",
    "analysis_entry_summary",
    "run_analysis",
    "seal_analysis_result",
]
