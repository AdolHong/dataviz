from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
from typing import Any, Mapping

import pandas as pd

from dataviz.errors import ValidationFailure
from dataviz.filesystem import atomic_write_text, sha256_file
from dataviz.value_contract import json_compatible_value, json_value_signature


PARAMETER_OPTIONS_MANIFEST_SCHEMA = "dataviz/parameter-options-manifest/v1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _options_id() -> str:
    return f"options_{_now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:10]}"


def _storage_name(domain_id: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", domain_id).strip("-.") or "domain"
    digest = hashlib.sha256(domain_id.encode("utf-8")).hexdigest()[:10]
    return f"{readable}-{digest}.parquet"


def _signature(value: Any) -> str:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    elif hasattr(value, "item") and callable(value.item):
        value = value.item()
    return json_value_signature(json_compatible_value(value))


class ParameterOptionsStore:
    """Store immutable, bounded Parameter Domain snapshots for optional AI discovery."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.root = self.workspace / ".dataviz" / "parameter-options"
        self.staging_root = self.root / ".staging"

    def publish(
        self,
        *,
        dashboard: str,
        generation: str,
        query_parameters: Mapping[str, Any],
        frames: Mapping[str, pd.DataFrame],
        metadata: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        options_id = _options_id()
        staging = self.staging_root / options_id
        destination = self.root / options_id
        tables_root = staging / "tables"
        tables_root.mkdir(parents=True, exist_ok=False)
        tables: list[dict[str, Any]] = []
        try:
            for domain_id, frame in sorted(frames.items()):
                filename = _storage_name(domain_id)
                path = tables_root / filename
                frame.to_parquet(path, index=False)
                tables.append(
                    {
                        "domain": domain_id,
                        "rows": len(frame),
                        "columns": list(frame.columns),
                        "content_hash": sha256_file(path),
                        "storage": (Path("tables") / filename).as_posix(),
                        "source": dict(metadata.get(domain_id) or {}),
                    }
                )
            created_at = _now().isoformat()
            manifest = {
                "schema": PARAMETER_OPTIONS_MANIFEST_SCHEMA,
                "options_id": options_id,
                "status": "ready",
                "created_at": created_at,
                "dashboard": dashboard,
                "generation": generation,
                "query_parameters": dict(query_parameters),
                "tables": tables,
            }
            atomic_write_text(
                staging / "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
            )
            self.root.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise RuntimeError(f"Parameter options snapshot already exists: {options_id}")
            os.replace(staging, destination)
            return {
                **manifest,
                "options_path": (
                    Path(".dataviz") / "parameter-options" / options_id
                ).as_posix(),
            }
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def load(self, options_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"options_[0-9]{8}_[0-9]{6}_[0-9a-f]{10}", options_id):
            raise ValidationFailure(
                f"Invalid Parameter options id: {options_id}",
                details={"code": "parameter_options_id_invalid", "options_id": options_id},
            )
        path = self.root / options_id / "manifest.json"
        if not path.is_file():
            raise ValidationFailure(
                f"Unknown Parameter options snapshot: {options_id}",
                details={"code": "parameter_options_unknown", "options_id": options_id},
            )
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValidationFailure(
                f"Parameter options manifest is unreadable: {options_id}",
                details={"code": "parameter_options_manifest_invalid"},
            ) from error
        if manifest.get("schema") != PARAMETER_OPTIONS_MANIFEST_SCHEMA:
            raise ValidationFailure(
                f"Unsupported Parameter options manifest: {options_id}",
                details={"code": "parameter_options_manifest_schema_invalid"},
            )
        return manifest

    def read(
        self,
        manifest: Mapping[str, Any],
        *,
        domain: str | None,
        filters: Mapping[str, Any],
        columns: list[str] | None,
        offset: int,
        limit: int,
    ) -> tuple[str, pd.DataFrame, int]:
        tables = list(manifest.get("tables") or [])
        if domain is None:
            if len(tables) != 1:
                raise ValidationFailure(
                    "This options snapshot contains multiple Domains; choose --domain",
                    details={
                        "code": "parameter_options_domain_required",
                        "domains": [item["domain"] for item in tables],
                    },
                )
            table = tables[0]
        else:
            table = next((item for item in tables if item["domain"] == domain), None)
            if table is None:
                raise ValidationFailure(
                    f"Unknown Parameter Domain in snapshot: {domain}",
                    details={
                        "code": "parameter_options_domain_unknown",
                        "domain": domain,
                        "domains": [item["domain"] for item in tables],
                    },
                )
        options_id = str(manifest["options_id"])
        root = (self.root / options_id).resolve()
        path = (root / table["storage"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValidationFailure(
                "Parameter options table is missing",
                details={"code": "parameter_options_table_missing"},
            )
        if sha256_file(path) != table["content_hash"]:
            raise ValidationFailure(
                "Parameter options table hash does not match",
                details={"code": "parameter_options_table_changed"},
            )
        frame = pd.read_parquet(path)
        unknown_filters = sorted(set(filters) - set(frame.columns))
        if unknown_filters:
            raise ValidationFailure(
                "Unknown Parameter options filter columns: " + ", ".join(unknown_filters),
                details={
                    "code": "parameter_options_filter_unknown",
                    "columns": unknown_filters,
                },
            )
        for key, expected in filters.items():
            expected_values = expected if isinstance(expected, list) else [expected]
            signatures = {_signature(value) for value in expected_values}
            frame = frame[frame[key].map(_signature).isin(signatures)]
        if columns:
            unknown_columns = sorted(set(columns) - set(frame.columns))
            if unknown_columns:
                raise ValidationFailure(
                    "Unknown Parameter options columns: " + ", ".join(unknown_columns),
                    details={
                        "code": "parameter_options_column_unknown",
                        "columns": unknown_columns,
                    },
                )
            frame = frame.loc[:, columns]
        total = len(frame)
        return str(table["domain"]), frame.iloc[offset : offset + limit], total
