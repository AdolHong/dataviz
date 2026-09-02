from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from dataviz.errors import ValidationFailure
from dataviz.protocols import (
    ANALYSIS_CATALOG_SCHEMA,
    ANALYSIS_DESCRIBE_SCHEMA,
    ANALYSIS_ENTRY_SCHEMA,
    ANALYSIS_EVIDENCE_SCHEMA,
    ANALYSIS_RESULT_SCHEMA,
)
from dataviz.workspace.models import OutputSemanticsDefinition


class AnalysisContract(BaseModel):
    """Strict core with forward-compatible detail/debug extensions."""

    model_config = ConfigDict(extra="allow", populate_by_name=False)


class AnalysisDashboardReference(AnalysisContract):
    id: str
    title: str = ""
    path: str


class AnalysisEntry(AnalysisContract):
    schema_: Literal[ANALYSIS_ENTRY_SCHEMA] = Field(alias="schema")
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
    source_types: list[str] | None = None
    adapters: list[str] | None = None
    query_parameters: list[str] = Field(default_factory=list)
    query_bindings: dict[str, Any] | None = None
    parameter_contracts: list[dict[str, Any]] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)
    control_contracts: list[dict[str, Any]] = Field(default_factory=list)
    output: dict[str, Any] | None = None
    outputs: list[Any] = Field(default_factory=list)
    inputs: dict[str, str] = Field(default_factory=dict)
    node_id: str | None = None
    output_name: str | None = None
    view_id: str | None = None
    presentation: dict[str, Any] | None = None
    base_inputs: list[str] = Field(default_factory=list)
    upstream_outputs: list[str] = Field(default_factory=list)
    downstream_views: list[str] = Field(default_factory=list)
    match_reasons: list[Any] = Field(default_factory=list)
    equivalence_hash: str | None = None
    definition_path: str | None = None
    code_paths: list[str] | None = None
    implementation_assets: list[dict[str, Any]] | None = None
    definition_hash: str | None = None
    representative: dict[str, str] | None = None
    occurrence_count: int | None = Field(default=None, ge=1)
    references: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)


class AnalysisCatalog(AnalysisContract):
    schema_: Literal[ANALYSIS_CATALOG_SCHEMA] = Field(alias="schema")
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
    schema_: Literal[ANALYSIS_DESCRIBE_SCHEMA] = Field(alias="schema")
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
    transport: str | None = None
    storage: dict[str, Any] | None = None
    logical_value_hash: str | None = None


class AnalysisControlRevision(AnalysisContract):
    effective_revision: int = Field(ge=0)
    applied_revision: int | None = Field(default=None, ge=0)
    stale: bool

    @model_validator(mode="after")
    def validate_revision_order_and_staleness(self):
        if (
            self.applied_revision is not None
            and self.applied_revision > self.effective_revision
        ):
            raise ValueError("applied revision cannot exceed effective revision")
        if self.stale != (self.applied_revision != self.effective_revision):
            raise ValueError("Control stale flag must match its revision delta")
        return self


class AnalysisAppliedControlState(AnalysisContract):
    value: Any
    revision: int = Field(ge=0)
    intent: Literal["all_available", "explicit"] | None = None


class AnalysisWriterProvenance(AnalysisContract):
    revision: int = Field(ge=0)
    action_id: str = Field(min_length=1, max_length=128)
    source_view: str = Field(min_length=1)
    source_layer: str | None = Field(default=None, min_length=1)
    action: Literal["select", "select_many", "clear", "reset"]


class AnalysisConsumerRevision(AnalysisContract):
    trigger: Literal["auto", "apply", "manual"]
    stale: bool
    controls: dict[str, AnalysisControlRevision] = Field(min_length=1)
    applied_control_state: dict[str, AnalysisAppliedControlState] = Field(
        default_factory=dict
    )
    applied_writer_provenance: dict[str, AnalysisWriterProvenance] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_consumer_staleness(self):
        if self.stale != any(value.stale for value in self.controls.values()):
            raise ValueError("Consumer stale flag must match its Control revisions")
        expected = {
            key
            for key, value in self.controls.items()
            if value.applied_revision is not None
        }
        if set(self.applied_control_state) != expected:
            raise ValueError(
                "consumer applied Control state must cover every applied revision"
            )
        if any(
            self.applied_control_state[key].revision
            != self.controls[key].applied_revision
            for key in expected
        ):
            raise ValueError(
                "consumer applied Control state revision must match applied revision"
            )
        if not set(self.applied_writer_provenance) <= expected:
            raise ValueError(
                "consumer writer provenance must reference an applied Control state"
            )
        if any(
            value.revision != self.applied_control_state[key].revision
            for key, value in self.applied_writer_provenance.items()
        ):
            raise ValueError(
                "consumer writer provenance revision must match applied Control state"
            )
        return self


class AnalysisConsumerRevisions(AnalysisContract):
    views: dict[str, AnalysisConsumerRevision] = Field(default_factory=dict)
    transforms: dict[str, AnalysisConsumerRevision] = Field(default_factory=dict)


class AnalysisResult(AnalysisContract):
    schema_: Literal[ANALYSIS_RESULT_SCHEMA] = Field(alias="schema")
    status: Literal["ready", "partial", "failed", "cancelled"]
    generation: str | None = None
    target: AnalysisEntry | dict[str, Any] | None = None
    query_parameter_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    effective_controls: dict[str, Any] = Field(default_factory=dict)
    consumer_revisions: AnalysisConsumerRevisions = Field(
        default_factory=AnalysisConsumerRevisions
    )
    outputs: list[AnalysisOutputResult] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    timing: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    resolved_target: AnalysisEntry | dict[str, Any] | None = None
    presentation: dict[str, Any] = Field(default_factory=dict)
    view_input: dict[str, str] = Field(default_factory=dict)
    renderability: dict[str, Any] = Field(default_factory=dict)
    overlay: dict[str, Any] | None = None
    nodes: dict[str, Any] | None = None
    browser: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    result_id: str | None = None
    result_path: str | None = None


class AnalysisEvidence(AnalysisContract):
    schema_: Literal[ANALYSIS_EVIDENCE_SCHEMA] = Field(alias="schema")
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
    consumer_revisions: AnalysisConsumerRevisions = Field(
        default_factory=AnalysisConsumerRevisions
    )
    diagnostics: dict[str, Any] = Field(default_factory=dict)
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
    """Read a persisted Result while retaining forward-compatible fields."""

    return AnalysisResult.model_validate(value).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )


def _reject_producer_extras(value: Any, *, path: str = "result") -> None:
    if isinstance(value, BaseModel):
        if value.model_extra:
            fields = sorted(value.model_extra)
            raise ValidationFailure(
                f"Analysis producer emitted unknown field(s) at {path}: "
                + ", ".join(fields),
                details={
                    "code": "analysis_producer_unknown_field",
                    "path": path,
                    "fields": fields,
                },
            )
        for name in type(value).model_fields:
            _reject_producer_extras(getattr(value, name), path=f"{path}.{name}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_producer_extras(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_producer_extras(item, path=f"{path}.{key}")


def _validate_analysis_producer(
    model_type: type[BaseModel],
    value: dict[str, Any],
    *,
    path: str,
) -> dict[str, Any]:
    model = model_type.model_validate(value)
    _reject_producer_extras(model, path=path)
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def validate_analysis_entry_producer(value: dict[str, Any]) -> dict[str, Any]:
    return _validate_analysis_producer(AnalysisEntry, value, path="entry")


def validate_analysis_catalog_producer(value: dict[str, Any]) -> dict[str, Any]:
    return _validate_analysis_producer(AnalysisCatalog, value, path="catalog")


def validate_analysis_describe_producer(value: dict[str, Any]) -> dict[str, Any]:
    return _validate_analysis_producer(AnalysisDescribe, value, path="describe")


def validate_analysis_result_producer(value: dict[str, Any]) -> dict[str, Any]:
    """Validate Dataviz-produced Results without weakening tolerant readers."""

    return _validate_analysis_producer(AnalysisResult, value, path="result")


def validate_analysis_evidence_producer(value: dict[str, Any]) -> dict[str, Any]:
    return _validate_analysis_producer(AnalysisEvidence, value, path="evidence")


def validate_analysis_promotion_producer(value: dict[str, Any]) -> dict[str, Any]:
    return _validate_analysis_producer(AnalysisPromotion, value, path="promotion")
