from __future__ import annotations

from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Any
import uuid

import yaml

from dataviz.analysis.catalog import ensure_analysis_catalog
from dataviz.analysis.contracts import (
    ANALYSIS_PROMOTE_ADAPTER,
    AnalysisEvidence,
    AnalysisPromotion,
    AssertionPromotionProposal,
    NewOutputPromotionProposal,
    SemanticsPromotionProposal,
    validate_analysis_evidence_producer,
    validate_analysis_promotion_producer,
    validate_analysis_result,
)
from dataviz.errors import ValidationFailure
from dataviz.filesystem import atomic_write_text
from dataviz.protocols import ANALYSIS_EVIDENCE_SCHEMA
from dataviz.semantic_validation import validate_workspace_semantics
from dataviz.workspace import load_workspace, validate_workspace


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def create_analysis_evidence(
    workspace: Path,
    result: dict[str, Any],
    *,
    result_source: str,
    question: str,
    conclusions: list[str],
    assertions: list[str] | None = None,
    generated_by: str,
    reviewer: str = "",
    status: str = "draft",
    snapshot_rows: int = 0,
) -> tuple[AnalysisEvidence, Path]:
    root = workspace.resolve()
    validated = validate_analysis_result(result)
    if validated["status"] not in {"ready", "partial"}:
        raise ValidationFailure(
            "Only a ready/partial Analysis Result can become Evidence",
            details={
                "code": "analysis_evidence_result_not_ready",
                "status": validated["status"],
            },
        )
    if status == "reviewed" and not reviewer.strip():
        raise ValidationFailure(
            "Reviewed Evidence requires --reviewer",
            details={"code": "analysis_evidence_reviewer_required"},
        )
    result_hash = _sha256(_json_bytes(validated))
    evidence_id = f"evidence_{result_hash[:10]}_{uuid.uuid4().hex[:8]}"
    snapshots: list[dict[str, Any]] = []
    output_evidence: list[dict[str, Any]] = []
    for output in validated.get("outputs", []):
        output_evidence.append(
            {
                key: output.get(key)
                for key in ("reference", "kind", "rows", "schema", "content_hash")
                if output.get(key) is not None
            }
        )
        if snapshot_rows > 0 and output.get("kind") == "table":
            snapshots.append(
                {
                    "reference": output["reference"],
                    "rows": list(output.get("preview") or [])[:snapshot_rows],
                    "source_truncated": bool(output.get("truncated")),
                }
            )
    evidence = AnalysisEvidence.model_validate(
        validate_analysis_evidence_producer(
            {
                "schema": ANALYSIS_EVIDENCE_SCHEMA,
                "evidence_id": evidence_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": status,
                "question": question.strip(),
                "conclusions": [
                    value.strip() for value in conclusions if value.strip()
                ],
                "assertions": [
                    value.strip() for value in (assertions or []) if value.strip()
                ],
                "result_hash": result_hash,
                "result_source": result_source,
                "generated_by": generated_by.strip(),
                "reviewer": reviewer.strip(),
                "target": validated.get("target") or {},
                "outputs": output_evidence,
                "lineage": validated.get("lineage", {}),
                "consumer_revisions": validated.get(
                    "consumer_revisions", {"views": {}, "transforms": {}}
                ),
                "snapshot": snapshots,
            }
        )
    )
    destination = root / ".dataviz" / "analysis-evidence" / f"{evidence_id}.json"
    atomic_write_text(
        destination,
        json.dumps(
            evidence.model_dump(mode="json", by_alias=True, exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return evidence, destination


def load_analysis_evidence(workspace: Path, value: str) -> tuple[AnalysisEvidence, Path]:
    root = workspace.resolve()
    candidate = Path(value)
    if candidate.name == value and not candidate.suffix:
        candidate = root / ".dataviz" / "analysis-evidence" / f"{value}.json"
    elif not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    if not candidate.is_file():
        raise ValidationFailure(
            f"Analysis Evidence not found: {value}",
            details={"code": "analysis_evidence_not_found", "evidence": value},
        )
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        return AnalysisEvidence.model_validate(payload), candidate
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValidationFailure(
            f"Invalid Analysis Evidence: {value}",
            details={"code": "analysis_evidence_invalid", "reason": str(error)},
        ) from error


def load_promotion_proposal(path: Path) -> Any:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return ANALYSIS_PROMOTE_ADAPTER.validate_python(value)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise ValidationFailure(
            f"Invalid Analysis Promotion proposal: {path}",
            details={"code": "analysis_promotion_proposal_invalid", "reason": str(error)},
        ) from error


def _safe_workspace_path(root: Path, value: str, *, prefix: str | None = None) -> Path:
    if Path(value).is_absolute() or value.startswith("."):
        raise ValidationFailure(
            f"Promotion path must be Workspace-relative: {value}",
            details={"code": "analysis_promotion_path_invalid", "path": value},
        )
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path.is_relative_to(root / ".dataviz"):
        raise ValidationFailure(
            f"Promotion path escapes allowed Workspace assets: {value}",
            details={"code": "analysis_promotion_path_invalid", "path": value},
        )
    if prefix and not path.is_relative_to(root / prefix):
        raise ValidationFailure(
            f"Promotion path must be inside {prefix}/: {value}",
            details={"code": "analysis_promotion_path_invalid", "path": value},
        )
    return path


def _operation(root: Path, path: Path, before: str, after: str) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative}",
            tofile=f"b/{relative}",
        )
    )
    return {
        "path": relative,
        "action": "update" if before else "create",
        "before_sha256": _sha256(before.encode("utf-8")) if before else None,
        "after_sha256": _sha256(after.encode("utf-8")),
        "diff": diff,
        "content": after,
    }


def _replace_output_semantics(
    root: Path,
    entry: dict[str, Any],
    proposal: SemanticsPromotionProposal,
) -> dict[str, Any]:
    path = _safe_workspace_path(root, entry["definition_path"])
    before = path.read_text(encoding="utf-8")
    document = yaml.safe_load(before)
    node_type, node_identifier = entry["node_id"].split(":", 1)
    owner = document
    if document.get("kind") == "dashboard":
        collection_name = {
            "source": "sources",
            "dataset": "dataset_transforms",
            "interactive": "interactive_transforms",
        }[node_type]
        owner = next(
            (
                item
                for item in document.get(collection_name, [])
                if isinstance(item, dict) and item.get("id") == node_identifier
            ),
            None,
        )
    if not isinstance(owner, dict):
        raise ValidationFailure(
            f"Cannot locate Output owner for {entry['reference']}",
            details={"code": "analysis_promotion_target_uneditable"},
        )
    outputs = owner.get("outputs")
    if not isinstance(outputs, dict) or entry["output_name"] not in outputs:
        raise ValidationFailure(
            f"Cannot locate Output {entry['reference']}",
            details={"code": "analysis_promotion_target_uneditable"},
        )
    outputs[entry["output_name"]]["semantics"] = proposal.semantics.model_dump(
        mode="json", exclude_none=True
    )
    after = yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
    return _operation(root, path, before, after)


def _assertion_operation(
    root: Path,
    evidence: AnalysisEvidence,
    entry: dict[str, Any],
    proposal: AssertionPromotionProposal,
) -> dict[str, Any]:
    dashboard_path = root / entry["dashboard"]["path"]
    relative = proposal.path or f"analysis_contracts/{evidence.evidence_id}.yaml"
    path = _safe_workspace_path(dashboard_path, relative)
    output = next(
        (value for value in evidence.outputs if value.get("reference") == entry["reference"]),
        None,
    )
    if output is None:
        raise ValidationFailure(
            "Evidence does not contain the Promotion target Output",
            details={"code": "analysis_promotion_evidence_target_mismatch"},
        )
    payload: dict[str, Any] = {
        "schema": "dataviz/analysis-assertion/v1",
        "kind": "analysis_assertion",
        "evidence": evidence.evidence_id,
        "result_hash": evidence.result_hash,
        "target": entry["reference"],
        "expected": {
            key: output.get(key)
            for key in ("content_hash", "rows", "schema")
            if output.get(key) is not None
        },
        "lineage": evidence.lineage,
        "assertions": evidence.assertions,
    }
    if proposal.include_snapshot:
        payload["snapshot"] = next(
            (
                value["rows"]
                for value in evidence.snapshot
                if value.get("reference") == entry["reference"]
            ),
            [],
        )
    before = path.read_text(encoding="utf-8") if path.is_file() else ""
    after = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    return _operation(root, path, before, after)


def _new_output_operations(
    root: Path, proposal: NewOutputPromotionProposal
) -> list[dict[str, Any]]:
    operations = []
    for relative, content in sorted(proposal.files.items()):
        path = _safe_workspace_path(root, relative, prefix="dashboards")
        before = path.read_text(encoding="utf-8") if path.is_file() else ""
        expected = proposal.expected_sha256.get(relative)
        if before and not expected:
            raise ValidationFailure(
                f"Replacing {relative} requires expected_sha256",
                details={"code": "analysis_promotion_expected_hash_required", "path": relative},
            )
        if expected and _sha256(before.encode("utf-8")) != expected:
            raise ValidationFailure(
                f"Promotion input changed since the proposal was prepared: {relative}",
                details={"code": "analysis_promotion_expected_hash_mismatch", "path": relative},
            )
        operations.append(_operation(root, path, before, content))
    return operations


def _validate_operations(
    root: Path,
    operations: list[dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]], Path, TemporaryDirectory[str]]:
    temporary = TemporaryDirectory(prefix="dataviz-analysis-promote-")
    copied = Path(temporary.name) / "workspace"
    shutil.copytree(
        root,
        copied,
        ignore=shutil.ignore_patterns(".dataviz", "shared_caches", "__pycache__", "*.pyc"),
    )
    for operation in operations:
        destination = copied / operation["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(operation["content"], encoding="utf-8")
    try:
        loaded = load_workspace(copied)
        diagnostics = [
            item.as_dict()
            for item in [*validate_workspace(loaded), *validate_workspace_semantics(loaded)]
        ]
    except Exception as error:
        diagnostics = [
            {
                "level": "error",
                "code": "analysis_promotion_workspace_invalid",
                "message": str(error),
            }
        ]
    valid = not any(item.get("level") == "error" for item in diagnostics)
    return valid, diagnostics, copied, temporary


def build_promotion_preview(
    workspace: Path,
    evidence: AnalysisEvidence,
    proposal: Any,
) -> AnalysisPromotion:
    root = workspace.resolve()
    catalog = ensure_analysis_catalog(root)
    if isinstance(proposal, SemanticsPromotionProposal):
        entry = catalog.resolve(proposal.target)
        if entry["kind"] not in {"base_output", "derived_output"}:
            raise ValidationFailure(
                "Semantics Promotion requires a Base/Derived Output",
                details={"code": "analysis_promotion_target_invalid"},
            )
        if not any(
            output.get("reference") == entry["reference"]
            for output in evidence.outputs
        ):
            raise ValidationFailure(
                "Evidence does not contain the Promotion target Output",
                details={"code": "analysis_promotion_evidence_target_mismatch"},
            )
        if (
            proposal.semantics.assurance.status in {"reviewed", "certified"}
            and evidence.status != "reviewed"
        ):
            raise ValidationFailure(
                "Reviewed/certified semantics require reviewed Analysis Evidence",
                details={"code": "analysis_promotion_review_required"},
            )
        operations = [_replace_output_semantics(root, entry, proposal)]
        kind = "semantics"
    elif isinstance(proposal, AssertionPromotionProposal):
        entry = catalog.resolve(proposal.target)
        operations = [_assertion_operation(root, evidence, entry, proposal)]
        kind = "assertion"
    elif isinstance(proposal, NewOutputPromotionProposal):
        operations = _new_output_operations(root, proposal)
        kind = "new_output"
    else:  # pragma: no cover - TypeAdapter owns proposal variants.
        raise AssertionError("Unknown Analysis Promotion proposal")

    valid, diagnostics, copied, temporary = _validate_operations(root, operations)
    try:
        if valid and isinstance(proposal, NewOutputPromotionProposal):
            before_references = {entry["reference"] for entry in catalog.entries}
            promoted = ensure_analysis_catalog(copied, refresh=True)
            for reference in proposal.expected_new_references:
                if reference in before_references:
                    diagnostics.append(
                        {
                            "level": "error",
                            "code": "analysis_promotion_output_not_new",
                            "message": f"Expected new Output already exists: {reference}",
                        }
                    )
                    continue
                try:
                    entry = promoted.resolve(reference)
                except ValidationFailure:
                    diagnostics.append(
                        {
                            "level": "error",
                            "code": "analysis_promotion_output_missing",
                            "message": f"Expected new Output was not created: {reference}",
                        }
                    )
                    continue
                if entry.get("assurance", {}).get("status", "draft") != "draft":
                    diagnostics.append(
                        {
                            "level": "error",
                            "code": "analysis_promotion_new_output_not_draft",
                            "message": f"New Output must start as draft: {reference}",
                        }
                    )
            valid = not any(item.get("level") == "error" for item in diagnostics)
    finally:
        temporary.cleanup()
    return AnalysisPromotion.model_validate(
        validate_analysis_promotion_producer(
            {
                "schema": "dataviz/analysis-promotion/v1",
                "status": "ready" if valid else "invalid",
                "kind": kind,
                "evidence_id": evidence.evidence_id,
                "operations": operations,
                "diagnostics": diagnostics,
                "workspace_valid": valid,
            }
        )
    )
