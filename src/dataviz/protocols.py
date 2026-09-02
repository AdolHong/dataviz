from __future__ import annotations

from typing import Any


WORKSPACE_SCHEMA = "dataviz/workspace/v2"
DASHBOARD_SCHEMA = "dataviz/dashboard/v18"
PARAMETER_DOMAIN_SCHEMA = "dataviz/parameter-domain/v2"
PARAMETER_DOMAIN_CONTRACT_SCHEMA = "dataviz/parameter-domain-contract/v3"
PARAMETER_LOOKUP_SCHEMA = "dataviz/parameter-lookup/v1"
PARAMETER_MATERIALIZATION_SCHEMA = "dataviz/parameter-materialization/v1"
QUERY_INSPECTION_SCHEMA = "dataviz/query-inspection/v1"
PRESENTATION_SCHEMA = "dataviz/presentation/v2"
SOURCE_SCHEMA = "dataviz/source/v6"
DATASET_TRANSFORM_SCHEMA = "dataviz/dataset-transform/v3"
INTERACTIVE_TRANSFORM_SCHEMA = "dataviz/interactive-transform/v4"
DEPENDENCY_CONTRACT_SCHEMA = "dataviz/dependency-contract/v13"
LAYOUT_CONTRACT_SCHEMA = "dataviz/layout-contract/v1"
STATE_SNAPSHOT_SCHEMA = "dataviz/state-snapshot/v6"
RUNTIME_PROTOCOL_SCHEMA = "dataviz/runtime/v14"
TARGET_REFERENCE_SCHEMA = "dataviz/target-reference/v1"
ANALYSIS_ENTRY_SCHEMA = "dataviz/analysis-entry/v1"
ANALYSIS_CATALOG_SCHEMA = "dataviz/analysis-catalog/v1"
ANALYSIS_DESCRIBE_SCHEMA = "dataviz/analysis-describe/v1"
ANALYSIS_RESULT_SCHEMA = "dataviz/analysis-result/v5"
ANALYSIS_EVIDENCE_SCHEMA = "dataviz/analysis-evidence/v5"
WORKSPACE_CHANGE_SCHEMA = "dataviz/workspace-change/v1"
DASHBOARD_BUNDLE_SCHEMA = "dataviz/dashboard-bundle/v2"
REPORT_MANIFEST_SCHEMA = "dataviz/report-manifest/v3"


CURRENT_PROTOCOL_SCHEMAS: dict[str, str] = {
    "workspace": WORKSPACE_SCHEMA,
    "dashboard": DASHBOARD_SCHEMA,
    "parameter_domain": PARAMETER_DOMAIN_SCHEMA,
    "parameter_domain_contract": PARAMETER_DOMAIN_CONTRACT_SCHEMA,
    "parameter_lookup": PARAMETER_LOOKUP_SCHEMA,
    "parameter_materialization": PARAMETER_MATERIALIZATION_SCHEMA,
    "query_inspection": QUERY_INSPECTION_SCHEMA,
    "presentation": PRESENTATION_SCHEMA,
    "source": SOURCE_SCHEMA,
    "dataset_transform": DATASET_TRANSFORM_SCHEMA,
    "interactive_transform": INTERACTIVE_TRANSFORM_SCHEMA,
    "dependency_contract": DEPENDENCY_CONTRACT_SCHEMA,
    "layout_contract": LAYOUT_CONTRACT_SCHEMA,
    "state_snapshot": STATE_SNAPSHOT_SCHEMA,
    "runtime": RUNTIME_PROTOCOL_SCHEMA,
    "target_reference": TARGET_REFERENCE_SCHEMA,
    "analysis_entry": ANALYSIS_ENTRY_SCHEMA,
    "analysis_catalog": ANALYSIS_CATALOG_SCHEMA,
    "analysis_describe": ANALYSIS_DESCRIBE_SCHEMA,
    "analysis_result": ANALYSIS_RESULT_SCHEMA,
    "analysis_evidence": ANALYSIS_EVIDENCE_SCHEMA,
    "workspace_change": WORKSPACE_CHANGE_SCHEMA,
    "dashboard_bundle": DASHBOARD_BUNDLE_SCHEMA,
    "report_manifest": REPORT_MANIFEST_SCHEMA,
}


PROTOCOL_BOUNDARIES: tuple[dict[str, Any], ...] = (
    {
        "boundary": "query-inspection",
        "schema": QUERY_INSPECTION_SCHEMA,
        "owner": "execution.query_inspection/sources.sql",
        "producer": "dataviz inspect query",
        "consumer": "Dashboard authors and AI tooling",
        "persisted": False,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": "query-parameter-state,sql-query-filter,redaction",
    },
    {
        "boundary": "portable-report-manifest",
        "schema": REPORT_MANIFEST_SCHEMA,
        "owner": "rendering.canvas",
        "producer": "dataviz report/export",
        "consumer": "Portable HTML audit and share tooling",
        "persisted": True,
        "strictness": "exact-current",
        "compatibility": "major-revision",
        "conformance_suite": "workspace-assets,portable-html",
    },
    {
        "boundary": "portable-dashboard-bundle",
        "schema": DASHBOARD_BUNDLE_SCHEMA,
        "owner": "workspace.bundle",
        "producer": "dataviz bundle",
        "consumer": "Workspace loader and bundle merge",
        "persisted": True,
        "strictness": "exact-current",
        "compatibility": "major-revision",
        "conformance_suite": "dashboard-bundle",
    },
    {
        "boundary": "authoring-dashboard",
        "schema": DASHBOARD_SCHEMA,
        "owner": "workspace.models",
        "producer": "Dashboard author / scaffold",
        "consumer": "Workspace loader and compiler",
        "persisted": True,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": "control-filter,multi-view-writer,compound-control-writer",
    },
    {
        "boundary": "authoring-source",
        "schema": SOURCE_SCHEMA,
        "owner": "workspace.models/sources.sql",
        "producer": "Dashboard author / scaffold",
        "consumer": "Workspace loader and Query executor",
        "persisted": True,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": "query-parameter-state,sql-query-filter",
    },
    {
        "boundary": "authoring-interactive-transform",
        "schema": INTERACTIVE_TRANSFORM_SCHEMA,
        "owner": "workspace.models",
        "producer": "Dashboard author / scaffold",
        "consumer": "Dependency compiler and Interactive Runtime",
        "persisted": True,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": "input-binding,control-filter,output-capability",
    },
    {
        "boundary": "parameter-domain-contract",
        "schema": PARAMETER_DOMAIN_CONTRACT_SCHEMA,
        "owner": "execution.parameter_domains",
        "producer": "Parameter Domain compiler",
        "consumer": "Dashboard Shell, Lookup and inspect",
        "persisted": False,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": "query-parameter-state,input-binding",
    },
    {
        "boundary": "parameter-domain-lookup",
        "schema": PARAMETER_LOOKUP_SCHEMA,
        "owner": "execution.parameter_materializations",
        "producer": "Workspace materialization store",
        "consumer": "Dashboard Shell and parameters lookup CLI",
        "persisted": False,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": "query-parameter-state,value-signature,input-binding",
    },
    {
        "boundary": "parameter-domain-materialization",
        "schema": PARAMETER_MATERIALIZATION_SCHEMA,
        "owner": "execution.parameter_materializations",
        "producer": "Workspace materialization builder",
        "consumer": "Parameter Lookup, refresh/status CLI and prune",
        "persisted": True,
        "strictness": "exact-current",
        "compatibility": "major-revision",
        "conformance_suite": "parameter-materialization-lifecycle",
    },
    {
        "boundary": "dependency-projection",
        "schema": DEPENDENCY_CONTRACT_SCHEMA,
        "owner": "execution.dependencies",
        "producer": "Dependency compiler",
        "consumer": "Python execution, Canvas Runtime, inspect and Web Component",
        "persisted": False,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": (
            "input-binding,control-filter,consumer-revision,multi-view-writer,"
            "compound-control-writer"
        ),
    },
    {
        "boundary": "browser-runtime-wire",
        "schema": RUNTIME_PROTOCOL_SCHEMA,
        "owner": "rendering.canvas",
        "producer": "Server/portable Canvas renderer",
        "consumer": "Canvas Runtime and Web Component adapter",
        "persisted": "embedded-in-html",
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": (
            "input-binding,control-filter,value-signature,output-capability,"
            "multi-view-writer,compound-control-writer"
        ),
    },
    {
        "boundary": "state-snapshot",
        "schema": STATE_SNAPSHOT_SCHEMA,
        "owner": "state_snapshot",
        "producer": "Python and Canvas state projector",
        "consumer": "Result, Evidence, report and tab restore",
        "persisted": True,
        "strictness": "strict-known-shape",
        "compatibility": "major-revision",
        "conformance_suite": "consumer-revision,value-signature,multi-view-writer",
    },
    {
        "boundary": "analysis-result",
        "schema": ANALYSIS_RESULT_SCHEMA,
        "owner": "analysis.contracts/results",
        "producer": "dataviz run",
        "consumer": "result/evidence commands",
        "persisted": True,
        "strictness": "tolerant-reader-extra-allow",
        "compatibility": "major-revision",
        "conformance_suite": (
            "consumer-revision,output-capability,multi-view-writer"
        ),
    },
    {
        "boundary": "analysis-evidence",
        "schema": ANALYSIS_EVIDENCE_SCHEMA,
        "owner": "analysis.contracts/evidence",
        "producer": "evidence create",
        "consumer": "evidence review and promotion",
        "persisted": True,
        "strictness": "strict-canonical-fields",
        "compatibility": "major-revision",
        "conformance_suite": "consumer-revision,multi-view-writer",
    },
    {
        "boundary": "output-destination-error",
        "schema": None,
        "owner": "execution.outputs",
        "producer": "CLI/report preflight",
        "consumer": "CLI, HTTP and AI clients",
        "persisted": False,
        "strictness": "stable-error-code-and-details",
        "compatibility": "additive-error-contract",
        "conformance_suite": "output-capability",
    },
)


PROTOCOL_CHANGE_RECORDS: tuple[dict[str, str], ...] = (
    {
        "change": "atomic-compound-control-writer",
        "classification": "authoring and private lockstep additive",
        "decision": (
            "dashboard v17, dependency contract v12, runtime v13 and component registry 6.0.0; "
            "state snapshot v5 and analysis result/evidence v4 unchanged"
        ),
        "reason": (
            "one View gesture may project the same selected datum into a primary Control and "
            "declared context Controls; the unique ControlRuntime validates and commits the "
            "whole action atomically while existing per-Control provenance shares one action id"
        ),
    },
    {
        "change": "sql-query-filter-empty-policy",
        "classification": "authoring semantic additive and exact-current",
        "decision": "source v5; dashboard/query state/runtime/result unchanged",
        "reason": (
            "each SQL query_filter explicitly maps an empty multiple_input or "
            "multiple_select none state to passthrough or match_none while all "
            "continues to mean the complete candidate universe"
        ),
    },
    {
        "change": "shared-parameter-materialization-and-compact-query-state",
        "classification": "authoring, private lockstep and persisted semantic breaking",
        "decision": (
            "dashboard v14, parameter domain v2, parameter domain contract v3, "
            "parameter lookup v1, parameter materialization v1, source v4, "
            "dependency contract v11, runtime v10, state snapshot v5, "
            "analysis result v4 and analysis evidence v4"
        ),
        "reason": (
            "SQL candidate relations are shared immutable Server materializations; "
            "Lookup owns search, parent predicates and cursor pages; candidate-backed "
            "multiple select persists all/include/exclude/none without expanding the universe"
        ),
    },
    {
        "change": "multi-view-control-writer-provenance",
        "classification": "authoring, private lockstep and persisted semantic breaking",
        "decision": (
            "dashboard v13, dependency contract v10, runtime v9, state snapshot v4, "
            "analysis result v3 and analysis evidence v3"
        ),
        "reason": (
            "one Control may have ordered writer edges, actions and rejections identify "
            "their source View, and persisted consumer evidence records the writer that "
            "produced each applied revision"
        ),
    },
    {
        "change": "single-control-authority-and-applied-state-evidence",
        "classification": "private lockstep and persisted semantic breaking",
        "decision": (
            "dependency contract v9, runtime v8, state snapshot v3, "
            "analysis result v2 and analysis evidence v2"
        ),
        "reason": (
            "the Host channel now carries typed versioned actions and persisted "
            "consumer evidence includes the exact Control state captured at start"
        ),
    },
    {
        "change": "parameter-domain-local-projection",
        "classification": "superseded historical private lockstep change",
        "decision": (
            "parameter-domain contract v2 and resolution v2; superseded by "
            "shared-parameter-materialization-and-compact-query-state"
        ),
        "reason": (
            "records the former client-relation generation only; current Runtime no "
            "longer ships complete relations or supports Domain query_inputs"
        ),
    },
    {
        "change": "query-input-projection-parity",
        "classification": "implementation parity fix",
        "decision": "no independent bump; shipped with runtime v7",
        "reason": "value/present/intent was already present in the author and Python contract",
    },
    {
        "change": "between-zero-truthiness",
        "classification": "implementation parity fix",
        "decision": "no independent bump; shipped with runtime v7",
        "reason": "zero was already a valid declared numeric boundary",
    },
    {
        "change": "typed-control-comparison",
        "classification": "semantic breaking",
        "decision": "dashboard v12, interactive-transform v4, dependency v8, runtime v7",
        "reason": "comparison results and invalid operator/value behavior are observable",
    },
    {
        "change": "browser-asset-destination-preflight",
        "classification": "additive-but-current-reader-incompatible",
        "decision": "stable error contract; author declarations remain accepted",
        "reason": "the unsupported destination now fails before execution instead of reaching Path()",
    },
    {
        "change": "analysis-text-html-native-storage",
        "classification": "implementation parity fix",
        "decision": "analysis-result v1 unchanged",
        "reason": "the persisted bytes now match the existing kind and MIME contract without shape change",
    },
)


def protocol_registry() -> dict[str, Any]:
    return {
        "current": dict(CURRENT_PROTOCOL_SCHEMAS),
        "boundaries": [
            {
                **item,
                "current_revision": item["schema"] or "unversioned-stable-error",
            }
            for item in PROTOCOL_BOUNDARIES
        ],
        "change_records": [dict(item) for item in PROTOCOL_CHANGE_RECORDS],
    }


def current_protocol_schemas() -> dict[str, str]:
    """Return a copy of the only current-version mapping exposed by the package."""

    return dict(CURRENT_PROTOCOL_SCHEMAS)
