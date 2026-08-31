from __future__ import annotations

from typing import Any


WORKSPACE_SCHEMA = "dataviz/workspace/v1"
DASHBOARD_SCHEMA = "dataviz/dashboard/v13"
PARAMETER_DOMAIN_SCHEMA = "dataviz/parameter-domain/v1"
PARAMETER_DOMAIN_CONTRACT_SCHEMA = "dataviz/parameter-domain-contract/v2"
PARAMETER_DOMAIN_RESOLUTION_SCHEMA = "dataviz/parameter-domain-resolution/v2"
PRESENTATION_SCHEMA = "dataviz/presentation/v2"
SOURCE_SCHEMA = "dataviz/source/v3"
DATASET_TRANSFORM_SCHEMA = "dataviz/dataset-transform/v3"
INTERACTIVE_TRANSFORM_SCHEMA = "dataviz/interactive-transform/v4"
DEPENDENCY_CONTRACT_SCHEMA = "dataviz/dependency-contract/v10"
LAYOUT_CONTRACT_SCHEMA = "dataviz/layout-contract/v1"
STATE_SNAPSHOT_SCHEMA = "dataviz/state-snapshot/v4"
RUNTIME_PROTOCOL_SCHEMA = "dataviz/runtime/v9"
TARGET_REFERENCE_SCHEMA = "dataviz/target-reference/v1"
ANALYSIS_ENTRY_SCHEMA = "dataviz/analysis-entry/v1"
ANALYSIS_CATALOG_SCHEMA = "dataviz/analysis-catalog/v1"
ANALYSIS_DESCRIBE_SCHEMA = "dataviz/analysis-describe/v1"
ANALYSIS_RESULT_SCHEMA = "dataviz/analysis-result/v3"
ANALYSIS_EVIDENCE_SCHEMA = "dataviz/analysis-evidence/v3"
WORKSPACE_CHANGE_SCHEMA = "dataviz/workspace-change/v1"


CURRENT_PROTOCOL_SCHEMAS: dict[str, str] = {
    "workspace": WORKSPACE_SCHEMA,
    "dashboard": DASHBOARD_SCHEMA,
    "parameter_domain": PARAMETER_DOMAIN_SCHEMA,
    "parameter_domain_contract": PARAMETER_DOMAIN_CONTRACT_SCHEMA,
    "parameter_domain_resolution": PARAMETER_DOMAIN_RESOLUTION_SCHEMA,
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
}


PROTOCOL_BOUNDARIES: tuple[dict[str, Any], ...] = (
    {
        "boundary": "authoring-dashboard",
        "schema": DASHBOARD_SCHEMA,
        "owner": "workspace.models",
        "producer": "Dashboard author / scaffold",
        "consumer": "Workspace loader and compiler",
        "persisted": True,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": "control-filter,multi-view-writer",
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
        "consumer": "Dashboard Shell, resolver and inspect",
        "persisted": False,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": "parameter-domain-projection,input-binding",
    },
    {
        "boundary": "parameter-domain-resolution",
        "schema": PARAMETER_DOMAIN_RESOLUTION_SCHEMA,
        "owner": "execution.parameter_domains",
        "producer": "Parameter Domain compiler and resolver",
        "consumer": "Dashboard Shell and parameters options CLI",
        "persisted": False,
        "strictness": "exact-current",
        "compatibility": "package-lockstep",
        "conformance_suite": "parameter-domain-projection,value-signature,input-binding",
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
            "input-binding,control-filter,consumer-revision,multi-view-writer"
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
            "multi-view-writer"
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
        "classification": "private lockstep semantic breaking",
        "decision": "parameter-domain contract v2 and resolution v2; author schema unchanged",
        "reason": "projection edges now execute locally while query_inputs alone request a new snapshot",
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
