"""Machine-readable discovery and execution support for Dataviz analyses."""

from dataviz.analysis.catalog import (
    ANALYSIS_CATALOG_SCHEMA,
    ANALYSIS_ENTRY_SCHEMA,
    AnalysisCatalog,
    ensure_analysis_catalog,
    refresh_analysis_catalog_async,
)
from dataviz.analysis.contracts import (
    AnalysisCatalog as AnalysisCatalogContract,
    AnalysisDescribe,
    AnalysisEvidence,
    AnalysisEntry,
    AnalysisPromotion,
    AnalysisResult,
    validate_analysis_catalog,
    validate_analysis_catalog_producer,
    validate_analysis_describe,
    validate_analysis_describe_producer,
    validate_analysis_evidence_producer,
    validate_analysis_entry_producer,
    validate_analysis_promotion_producer,
    validate_analysis_result,
    validate_analysis_result_producer,
)
from dataviz.analysis.overlay import (
    ANALYSIS_OVERLAY_SCHEMA,
    AnalysisVariant,
    build_analysis_variant,
)
from dataviz.analysis.inspection import (
    analysis_reference_closure,
    inspect_analysis_closure,
)
from dataviz.analysis.evidence import (
    build_promotion_preview,
    create_analysis_evidence,
    load_analysis_evidence,
    load_promotion_proposal,
)
from dataviz.analysis.usage import (
    UsageKey,
    dashboard_query_usage,
    output_analysis_usage,
    read_usage,
    read_usage_best_effort,
    record_usage,
    record_usage_best_effort,
)
from dataviz.analysis.runner import RunRequest, run_analysis

__all__ = [
    "ANALYSIS_CATALOG_SCHEMA",
    "ANALYSIS_ENTRY_SCHEMA",
    "AnalysisCatalogContract",
    "AnalysisDescribe",
    "ensure_analysis_catalog",
    "refresh_analysis_catalog_async",
    "AnalysisCatalog",
    "AnalysisEntry",
    "AnalysisEvidence",
    "AnalysisPromotion",
    "AnalysisResult",
    "validate_analysis_catalog",
    "validate_analysis_catalog_producer",
    "validate_analysis_describe",
    "validate_analysis_describe_producer",
    "validate_analysis_evidence_producer",
    "validate_analysis_entry_producer",
    "validate_analysis_promotion_producer",
    "validate_analysis_result",
    "validate_analysis_result_producer",
    "ANALYSIS_OVERLAY_SCHEMA",
    "AnalysisVariant",
    "build_analysis_variant",
    "analysis_reference_closure",
    "inspect_analysis_closure",
    "create_analysis_evidence",
    "load_analysis_evidence",
    "load_promotion_proposal",
    "build_promotion_preview",
    "UsageKey",
    "dashboard_query_usage",
    "output_analysis_usage",
    "read_usage",
    "read_usage_best_effort",
    "record_usage",
    "record_usage_best_effort",
    "RunRequest",
    "run_analysis",
]
