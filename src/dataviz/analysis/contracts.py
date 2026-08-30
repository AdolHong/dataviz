from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from dataviz.workspace.models import OutputSemanticsDefinition


ANALYSIS_ENTRY_SCHEMA = "dataviz/analysis-entry/v1"
ANALYSIS_CATALOG_SCHEMA = "dataviz/analysis-catalog/v1"
ANALYSIS_RESULT_SCHEMA = "dataviz/analysis-result/v1"
ANALYSIS_DESCRIBE_SCHEMA = "dataviz/analysis-describe/v1"


class AnalysisContract(BaseModel):
    """Strict core with forward-compatible detail/debug extensions."""

    model_config = ConfigDict(extra="allow", populate_by_name=False)


class AnalysisDashboardReference(AnalysisContract):
    id: str
    title: str = ""
    path: str


class AnalysisEntry(AnalysisContract):
    schema_: Literal["dataviz/analysis-entry/v1"] = Field(alias="schema")
    reference: str
    dashboard: AnalysisDashboardReference
    kind: Literal["source", "base_output", "derived_output", "view"]
    stage: Literal["base", "derived", "presentation"]
    title: str
    purpose: str = ""
    grain: str | None = None
    caveats: list[str] = Field(default_factory=list)
    visibility: Literal["public", "internal"] = "public"
    assurance: dict[str, Any] = Field(default_factory=dict)
    time: dict[str, Any] | None = None
    measures: dict[str, Any] = Field(default_factory=dict)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    semantic_source: Literal["declared", "inferred"] | None = None
    semantic_status: Literal["complete", "incomplete"] | None = None
    semantic_missing: list[str] = Field(default_factory=list)
    trust_status: Literal["draft", "reviewed", "certified", "deprecated"] | None = None
    runtime: Any = None
    source_type: str | None = None
    query_parameters: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)
    equivalence_hash: str | None = None
    representative: dict[str, str] | None = None
    occurrence_count: int | None = Field(default=None, ge=1)
    references: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)


class AnalysisCatalog(AnalysisContract):
    schema_: Literal["dataviz/analysis-catalog/v1"] = Field(alias="schema")
    generation: str
    count: int = Field(ge=0)
    entries: list[AnalysisEntry]
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    stale: bool = False


class AnalysisDescribeItem(AnalysisContract):
    status: Literal["ready", "error"]
    requested_reference: str
    entry: AnalysisEntry | dict[str, Any] | None = None
    invocation: dict[str, Any] = Field(default_factory=dict)
    closure: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class AnalysisDescribe(AnalysisContract):
    schema_: Literal["dataviz/analysis-describe/v1"] = Field(alias="schema")
    generation: str
    count: int = Field(ge=0)
    items: list[AnalysisDescribeItem]


class AnalysisOutputResult(AnalysisContract):
    reference: str
    kind: str
    rows: int | None = None
    schema_: list[dict[str, Any]] = Field(default_factory=list, alias="schema")
    content_hash: str
    duration_ms: int | float | None = None
    preview: Any = None
    truncated: bool = False
    run_id: str


class AnalysisResult(AnalysisContract):
    schema_: Literal["dataviz/analysis-result/v1"] = Field(alias="schema")
    status: Literal["ready", "partial", "failed", "cancelled"]
    generation: str | None = None
    target: AnalysisEntry | dict[str, Any] | None = None
    query_parameters: dict[str, Any] = Field(default_factory=dict)
    effective_controls: dict[str, Any] = Field(default_factory=dict)
    outputs: list[AnalysisOutputResult] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    timing: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class AnalysisEvidence(AnalysisContract):
    schema_: Literal["dataviz/analysis-evidence/v1"] = Field(alias="schema")
    evidence_id: str
    created_at: str
    status: Literal["draft", "reviewed"] = "draft"
    question: str
    conclusions: list[str] = Field(min_length=1)
    assertions: list[str] = Field(default_factory=list)
    result_hash: str
    result_source: str
    generated_by: str
    reviewer: str = ""
    target: dict[str, Any]
    outputs: list[dict[str, Any]]
    lineage: dict[str, Any]
    snapshot: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_reviewer_for_reviewed_evidence(self):
        if self.status == "reviewed" and not self.reviewer.strip():
            raise ValueError("reviewed Analysis Evidence requires reviewer")
        return self


class AnalysisPromotion(AnalysisContract):
    schema_: Literal["dataviz/analysis-promotion/v1"] = Field(alias="schema")
    status: Literal["ready", "invalid"]
    kind: Literal["semantics", "assertion", "new_output"]
    evidence_id: str
    operations: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    workspace_valid: bool


class SemanticsPromotionProposal(AnalysisContract):
    schema_: Literal["dataviz/analysis-promote/v1"] = Field(alias="schema")
    kind: Literal["semantics"]
    target: str
    semantics: OutputSemanticsDefinition


class AssertionPromotionProposal(AnalysisContract):
    schema_: Literal["dataviz/analysis-promote/v1"] = Field(alias="schema")
    kind: Literal["assertion"]
    target: str
    path: str = ""
    include_snapshot: bool = False


class NewOutputPromotionProposal(AnalysisContract):
    schema_: Literal["dataviz/analysis-promote/v1"] = Field(alias="schema")
    kind: Literal["new_output"]
    files: dict[str, str] = Field(min_length=1)
    expected_sha256: dict[str, str] = Field(default_factory=dict)
    expected_new_references: list[str] = Field(min_length=1)


AnalysisPromoteProposal = (
    SemanticsPromotionProposal
    | AssertionPromotionProposal
    | NewOutputPromotionProposal
)
ANALYSIS_PROMOTE_ADAPTER = TypeAdapter(AnalysisPromoteProposal)


def validate_analysis_entry(value: dict[str, Any]) -> dict[str, Any]:
    return AnalysisEntry.model_validate(value).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )


def validate_analysis_catalog(value: dict[str, Any]) -> dict[str, Any]:
    return AnalysisCatalog.model_validate(value).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )


def validate_analysis_describe(value: dict[str, Any]) -> dict[str, Any]:
    return AnalysisDescribe.model_validate(value).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )


def validate_analysis_result(value: dict[str, Any]) -> dict[str, Any]:
    return AnalysisResult.model_validate(value).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
