from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Literal
import uuid

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from dataviz.errors import ValidationFailure
from dataviz.execution.node_support import hash_path
from dataviz.filesystem import atomic_write_text
from dataviz.sql_contract import sql_parameter_names
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


ANALYSIS_OVERLAY_SCHEMA = "dataviz/analysis-overlay/v1"


class _OverlayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisReplacement(_OverlayModel):
    code: str | None = None
    path: str | None = None
    format: Literal[
        "csv", "txt", "parquet", "pq", "json", "jsonl", "xlsx", "xls"
    ] | None = None
    code_dependencies: list[str] | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("replacement must declare code, path, format, or code_dependencies")
        return self


class AnalysisOverlayDefinition(_OverlayModel):
    schema_: Literal[ANALYSIS_OVERLAY_SCHEMA] = Field(alias="schema")
    replacements: dict[str, AnalysisReplacement] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class AnalysisVariant:
    dashboard: LoadedDashboard
    overlay_hash: str
    analysis_run_id: str
    manifest: dict[str, Any]
    manifest_path: Path

    @property
    def cache_namespace(self) -> str:
        return f"analysis-overlay:{self.overlay_hash}"

    def write_manifest(self, *, status: str, evidence: dict[str, Any] | None = None) -> None:
        payload = {**self.manifest, "status": status}
        if evidence:
            payload["evidence"] = evidence
        atomic_write_text(
            self.manifest_path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )


def _failure(message: str, *, code: str, **details: Any) -> ValidationFailure:
    return ValidationFailure(message, details={"code": code, **details})


def _read_overlay(value: str, *, cwd: Path | None = None) -> tuple[AnalysisOverlayDefinition, Path]:
    if value == "-":
        source = sys.stdin.read()
        base = (cwd or Path.cwd()).resolve()
        label = "<stdin>"
    else:
        overlay_path = Path(value).expanduser().resolve()
        if not overlay_path.is_file():
            raise _failure(
                "Analysis Overlay does not exist",
                code="analysis_overlay_not_found",
                path=str(overlay_path),
            )
        source = overlay_path.read_text(encoding="utf-8")
        base = overlay_path.parent
        label = str(overlay_path)
    try:
        raw = yaml.safe_load(source)
        definition = AnalysisOverlayDefinition.model_validate(raw)
    except (yaml.YAMLError, ValidationError, TypeError) as error:
        details = (
            error.errors(include_url=False, include_context=False, include_input=False)
            if isinstance(error, ValidationError)
            else str(error)
        )
        raise _failure(
            "Analysis Overlay is invalid",
            code="analysis_overlay_invalid",
            path=label,
            errors=details,
        ) from error
    return definition, base


def _resolve_asset(base: Path, value: str, *, target: str, field: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if not path.is_file():
        raise _failure(
            "Analysis Overlay asset does not exist",
            code="analysis_overlay_asset_not_found",
            target=target,
            field=field,
            path=str(path),
        )
    return path


def _asset_record(
    base: Path,
    value: str,
    *,
    target: str,
    field: str,
    index: int | None = None,
) -> tuple[str, dict[str, Any]]:
    path = _resolve_asset(base, value, target=target, field=field)
    logical_field = f"{field}[{index}]" if index is not None else field
    try:
        display_path = path.relative_to(base).as_posix()
    except ValueError:
        display_path = str(path)
    return str(path), {
        "target": target,
        "field": logical_field,
        "path": display_path,
        "resolved_path": str(path),
        "content_hash": hash_path(path),
        "bytes": path.stat().st_size,
    }


def _original_asset(
    definition_path: Path,
    value: str,
    *,
    target: str,
    field: str,
    index: int | None = None,
) -> dict[str, Any]:
    path = (definition_path.parent / value).resolve()
    logical_field = f"{field}[{index}]" if index is not None else field
    return {
        "target": target,
        "field": logical_field,
        "path": str(path),
        "content_hash": hash_path(path) if path.is_file() else None,
        "bytes": path.stat().st_size if path.is_file() else None,
    }


def _allowed_fields(node_kind: str, definition: Any) -> set[str]:
    if node_kind == "source" and definition.type == "file":
        return {"path", "format"}
    if node_kind == "source" and definition.type == "sql":
        return {"code"}
    return {"code", "code_dependencies"}


def _node(
    dashboard: LoadedDashboard, target: str
) -> tuple[str, str, Path, Any]:
    if ":" not in target:
        raise _failure(
            "Overlay replacement key must be source:<id>, dataset:<id>, or interactive:<id>",
            code="analysis_overlay_target_invalid",
            target=target,
        )
    kind, identifier = target.split(":", 1)
    collection = {
        "source": dashboard.sources,
        "dataset": dashboard.dataset_transforms,
        "interactive": dashboard.interactive_transforms,
    }.get(kind)
    if collection is None or identifier not in collection:
        raise _failure(
            "Analysis Overlay target does not exist in this Dashboard",
            code="analysis_overlay_target_unknown",
            target=target,
            dashboard=dashboard.definition.id,
        )
    definition_path, definition = collection[identifier]
    return kind, identifier, definition_path, definition


def build_analysis_variant(
    workspace: LoadedWorkspace,
    dashboard: LoadedDashboard,
    overlay: str,
    *,
    reachable_nodes: set[str] | None = None,
    cwd: Path | None = None,
) -> AnalysisVariant:
    definition, base = _read_overlay(overlay, cwd=cwd)
    sources = dict(dashboard.sources)
    datasets = dict(dashboard.dataset_transforms)
    interactions = dict(dashboard.interactive_transforms)
    changes: list[dict[str, Any]] = []
    external_assets: list[dict[str, Any]] = []

    for target, replacement in sorted(definition.replacements.items()):
        kind, identifier, definition_path, original = _node(dashboard, target)
        if reachable_nodes is not None and target not in reachable_nodes:
            raise _failure(
                "Analysis Overlay replacement cannot affect the requested target",
                code="analysis_overlay_target_unreachable",
                target=target,
                reachable_nodes=sorted(reachable_nodes),
            )
        provided = set(replacement.model_fields_set)
        allowed = _allowed_fields(kind, original)
        invalid = sorted(provided - allowed)
        if invalid:
            raise _failure(
                "Analysis Overlay replacement changes fields unsupported by this node type",
                code="analysis_overlay_field_not_allowed",
                target=target,
                node_type=(getattr(original, "type", None) or kind),
                fields=invalid,
                allowed=sorted(allowed),
            )
        if kind == "source" and original.type == "file" and original.adapter:
            raise _failure(
                "A File Source using an Adapter cannot be redirected by Analysis Overlay",
                code="analysis_overlay_adapter_path_forbidden",
                target=target,
            )

        updates: dict[str, Any] = {}
        replacement_assets: list[dict[str, Any]] = []
        original_assets: list[dict[str, Any]] = []
        for field in ("code", "path"):
            value = getattr(replacement, field)
            if field not in provided or value is None:
                continue
            current = getattr(original, field, None)
            if current:
                original_assets.append(
                    _original_asset(definition_path, current, target=target, field=field)
                )
            resolved, record = _asset_record(base, value, target=target, field=field)
            updates[field] = resolved
            replacement_assets.append(record)
            external_assets.append(record)
        if "format" in provided:
            updates["format"] = replacement.format
        if "code_dependencies" in provided:
            resolved_dependencies: list[str] = []
            for index, value in enumerate(replacement.code_dependencies or []):
                resolved, record = _asset_record(
                    base,
                    value,
                    target=target,
                    field="code_dependencies",
                    index=index,
                )
                resolved_dependencies.append(resolved)
                replacement_assets.append(record)
                external_assets.append(record)
            for index, value in enumerate(getattr(original, "code_dependencies", ())):
                original_assets.append(
                    _original_asset(
                        definition_path,
                        value,
                        target=target,
                        field="code_dependencies",
                        index=index,
                    )
                )
            updates["code_dependencies"] = resolved_dependencies

        if kind == "source" and original.type == "sql" and "code" in updates:
            sql = Path(updates["code"]).read_text(encoding="utf-8")
            declared = set(original.query_inputs)
            referenced = sql_parameter_names(sql)
            if referenced != declared:
                raise _failure(
                    "Replacement SQL must preserve the Source query input contract",
                    code="analysis_overlay_sql_parameters_changed",
                    target=target,
                    missing=sorted(declared - referenced),
                    undeclared=sorted(referenced - declared),
                )

        payload = original.model_dump(mode="python", by_alias=True)
        payload.update(updates)
        try:
            updated = type(original).model_validate(payload)
        except ValidationError as error:
            raise _failure(
                "Analysis Overlay produced an invalid node definition",
                code="analysis_overlay_definition_invalid",
                target=target,
                errors=error.errors(
                    include_url=False, include_context=False, include_input=False
                ),
            ) from error
        if kind == "source":
            sources[identifier] = (definition_path, updated)
        elif kind == "dataset":
            datasets[identifier] = (definition_path, updated)
        else:
            interactions[identifier] = (definition_path, updated)
        changes.append(
            {
                "target": target,
                "fields": sorted(provided),
                "original_assets": original_assets,
                "replacement_assets": replacement_assets,
            }
        )

    canonical = {
        "schema": ANALYSIS_OVERLAY_SCHEMA,
        "dashboard": dashboard.definition.id,
        "changes": changes,
    }
    overlay_hash = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    analysis_run_id = f"analysis_{overlay_hash[:10]}_{uuid.uuid4().hex[:10]}"
    manifest_dir = workspace.state_dir / "analysis-runs" / analysis_run_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "manifest.json"
    manifest = {
        "schema": "dataviz/analysis-run/v1",
        "analysis_run_id": analysis_run_id,
        "workspace": workspace.definition.id,
        "dashboard": dashboard.definition.id,
        "overlay_hash": overlay_hash,
        "changes": changes,
        "snapshot_assets": False,
    }
    variant_dashboard = replace(
        dashboard,
        sources=sources,
        dataset_transforms=datasets,
        interactive_transforms=interactions,
        analysis_overlay={
            "hash": overlay_hash,
            "assets": external_assets,
        },
    )
    variant = AnalysisVariant(
        dashboard=variant_dashboard,
        overlay_hash=overlay_hash,
        analysis_run_id=analysis_run_id,
        manifest=manifest,
        manifest_path=manifest_path,
    )
    variant.write_manifest(status="planned")
    return variant
