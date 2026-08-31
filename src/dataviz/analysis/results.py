from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import uuid
from typing import Any, Iterator

import pandas as pd

from dataviz.errors import ValidationFailure
from dataviz.filesystem import atomic_copy_file, atomic_write_text, sha256_file


RESULT_MANIFEST_SCHEMA = "dataviz/analysis-result-manifest/v1"
RESULT_INDEX_SCHEMA = "dataviz/analysis-result-index/v1"
RESULT_RETENTION_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _result_id() -> str:
    return f"result_{_now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:10]}"


def _storage_name(reference: str) -> str:
    """Create an internal filename key without exposing another public identifier."""

    tail = reference.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", tail).strip("-.") or "output"
    digest = hashlib.sha256(reference.encode("utf-8")).hexdigest()[:12]
    return f"{readable}-{digest}"


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5.0)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            result_id TEXT PRIMARY KEY,
            relative_path TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_accessed_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata VALUES ('schema', ?)",
        (RESULT_INDEX_SCHEMA,),
    )
    return connection


class AnalysisResultStore:
    """Publish and read immutable Analysis Results without re-running a DAG."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.root = self.workspace / ".dataviz" / "results"
        self.index_path = self.root / "index.sqlite"
        self.lock_path = self.root / "results.lock"
        self.staging_root = self.root / ".staging"
        self.trash_root = self.root / ".trash"
        self.leases_root = self.root / ".leases"

    @contextmanager
    def lease(self, result_id: str) -> Iterator[None]:
        """Prevent opportunistic GC while another process reads a Result."""

        self.leases_root.mkdir(parents=True, exist_ok=True)
        lease = self.leases_root / f"{result_id}-{os.getpid()}-{uuid.uuid4().hex}"
        atomic_write_text(lease, _iso() + "\n")
        try:
            yield
        finally:
            lease.unlink(missing_ok=True)

    def rebuild_index(self) -> int:
        """Recreate the disposable lookup index from immutable manifests."""

        self.root.mkdir(parents=True, exist_ok=True)
        rebuilt = 0
        with _exclusive_lock(self.lock_path):
            replacement = self.root / f".index-{uuid.uuid4().hex}.sqlite"
            connection = _connect(replacement)
            try:
                for path in sorted(self.root.glob("result_*/manifest.json")):
                    try:
                        manifest = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if manifest.get("schema") != RESULT_MANIFEST_SCHEMA:
                        continue
                    result_id = str(manifest.get("result_id") or "")
                    created_at = str(manifest.get("created_at") or _iso())
                    connection.execute(
                        "INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?, ?)",
                        (
                            result_id,
                            path.parent.name,
                            str(manifest.get("status") or "ready"),
                            created_at,
                            created_at,
                        ),
                    )
                    rebuilt += 1
                connection.commit()
            finally:
                connection.close()
            for suffix in ("-wal", "-shm"):
                Path(str(replacement) + suffix).unlink(missing_ok=True)
            os.replace(replacement, self.index_path)
        return rebuilt

    def publish(
        self,
        result: dict[str, Any],
        bindings: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        result_id = _result_id()
        created_at = _iso()
        staging = self.staging_root / result_id
        destination = self.root / result_id
        outputs_root = staging / "outputs"
        outputs_root.mkdir(parents=True, exist_ok=False)
        manifest_outputs: list[dict[str, Any]] = []
        try:
            for output in result.get("outputs", []):
                reference = str(output["reference"])
                storage_name = _storage_name(reference)
                binding = bindings.get(reference)
                if binding is None:
                    raise ValueError(f"Missing Result materialization for {reference}")
                stored = self._materialize_output(
                    outputs_root, storage_name, output, binding
                )
                published_output = {
                    **output,
                    "content_hash": stored["content_hash"],
                    "storage": stored,
                }
                logical_hash = output.get("content_hash")
                if logical_hash and logical_hash != stored["content_hash"]:
                    published_output["logical_value_hash"] = logical_hash
                manifest_outputs.append(published_output)
            immutable_result = dict(result)
            immutable_result["result_id"] = result_id
            immutable_result["result_path"] = (
                Path(".dataviz") / "results" / result_id
            ).as_posix()
            immutable_result["outputs"] = manifest_outputs
            report_binding = bindings.get("__report__")
            if report_binding is not None:
                report_source = Path(report_binding["source_path"]).resolve()
                if not report_source.is_file():
                    raise ValueError(f"Result report snapshot is not readable: {report_source}")
                report_target = staging / "report.html"
                report_hash = atomic_copy_file(report_source, report_target)
                renderability = dict(immutable_result.get("renderability") or {})
                renderability.update(
                    {
                        "renderable": True,
                        "snapshot": "report.html",
                        "content_hash": report_hash,
                    }
                )
                immutable_result["renderability"] = renderability
            quoted_workspace = json.dumps(str(self.workspace), ensure_ascii=False)
            immutable_result["next_actions"] = [
                f"dataviz result inspect {quoted_workspace} {result_id}",
                f"dataviz result show {quoted_workspace} {result_id}",
            ]
            manifest = {
                "schema": RESULT_MANIFEST_SCHEMA,
                "result_id": result_id,
                "status": immutable_result.get("status", "ready"),
                "created_at": created_at,
                "result": immutable_result,
            }
            atomic_write_text(
                staging / "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
            )
            with _exclusive_lock(self.lock_path):
                if destination.exists():
                    raise RuntimeError(f"Analysis Result already exists: {result_id}")
                os.replace(staging, destination)
                connection = _connect(self.index_path)
                try:
                    connection.execute(
                        "INSERT INTO results VALUES (?, ?, ?, ?, ?)",
                        (
                            result_id,
                            destination.name,
                            manifest["status"],
                            created_at,
                            created_at,
                        ),
                    )
                    connection.commit()
                finally:
                    connection.close()
            return immutable_result
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def _materialize_output(
        self,
        outputs_root: Path,
        storage_name: str,
        output: dict[str, Any],
        binding: dict[str, Any],
    ) -> dict[str, Any]:
        source_path = binding.get("source_path")
        if source_path is not None:
            source = Path(source_path).resolve()
            if not source.is_file():
                raise ValueError(f"File Source is not readable: {source}")
            expected = str(binding.get("content_hash") or sha256_file(source))
            actual = sha256_file(source)
            if actual != expected:
                raise ValueError(f"File Source changed while publishing Result: {source}")
            try:
                display_path = source.relative_to(self.workspace).as_posix()
                path_kind = "workspace-relative"
            except ValueError:
                display_path = str(source)
                path_kind = "absolute"
            return {
                "mode": "source-receipt",
                "path": display_path,
                "path_kind": path_kind,
                "size_bytes": source.stat().st_size,
                "content_hash": actual,
                "format": binding.get("format") or source.suffix.lstrip(".").lower(),
                "options": binding.get("options") or {},
                "read_at": _iso(),
            }

        artifact_path = binding.get("artifact_path")
        if artifact_path is not None:
            source = Path(artifact_path).resolve()
            expected = str(binding.get("content_hash") or output["content_hash"])
            suffix = source.suffix or ".bin"
            destination = outputs_root / f"{storage_name}{suffix}"
            actual = atomic_copy_file(source, destination, expected_sha256=expected)
            return {
                "mode": "managed",
                "path": (Path("outputs") / destination.name).as_posix(),
                "format": binding.get("format") or suffix.lstrip("."),
                "size_bytes": destination.stat().st_size,
                "content_hash": actual,
            }

        value = binding.get("value")
        kind = str(output.get("kind") or binding.get("kind") or "object")
        if kind == "table":
            frame = value if isinstance(value, pd.DataFrame) else pd.DataFrame(value)
            destination = outputs_root / f"{storage_name}.parquet"
            frame.to_parquet(destination, index=False)
            format_name = "parquet"
        elif kind in {"text", "html"}:
            suffix = ".html" if kind == "html" else ".txt"
            destination = outputs_root / f"{storage_name}{suffix}"
            atomic_write_text(destination, str(value))
            format_name = kind
        else:
            destination = outputs_root / f"{storage_name}.json"
            atomic_write_text(
                destination,
                json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str),
            )
            format_name = "json"
        return {
            "mode": "managed",
            "path": (Path("outputs") / destination.name).as_posix(),
            "format": format_name,
            "size_bytes": destination.stat().st_size,
            "content_hash": sha256_file(destination),
        }

    def _scan_manifest(self, result_id: str) -> Path | None:
        candidate = self.root / result_id / "manifest.json"
        return candidate if candidate.is_file() else None

    def manifest_path(self, result_id: str) -> Path:
        if not re.fullmatch(r"result_[0-9]{8}_[0-9]{6}_[0-9a-f]{10}", result_id):
            raise ValidationFailure(
                f"Invalid Analysis Result id: {result_id}",
                details={"code": "analysis_result_id_invalid", "result_id": result_id},
            )
        path: Path | None = None
        if not self.index_path.is_file() and self.root.is_dir():
            self.rebuild_index()
        if self.index_path.is_file():
            connection = _connect(self.index_path)
            try:
                row = connection.execute(
                    "SELECT relative_path FROM results WHERE result_id = ?",
                    (result_id,),
                ).fetchone()
                if row:
                    candidate = self.root / str(row[0]) / "manifest.json"
                    if candidate.is_file():
                        path = candidate
            finally:
                connection.close()
        path = path or self._scan_manifest(result_id)
        if path is None:
            raise ValidationFailure(
                f"Unknown Analysis Result: {result_id}",
                details={"code": "analysis_result_unknown", "result_id": result_id},
            )
        self._touch(result_id, path.parent.name)
        return path

    def load(self, result_id: str) -> dict[str, Any]:
        path = self.manifest_path(result_id)
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValidationFailure(
                f"Analysis Result manifest is unreadable: {result_id}",
                details={"code": "analysis_result_manifest_invalid", "result_id": result_id},
            ) from error
        if manifest.get("schema") != RESULT_MANIFEST_SCHEMA:
            raise ValidationFailure(
                f"Unsupported Analysis Result manifest: {result_id}",
                details={"code": "analysis_result_manifest_schema_invalid"},
            )
        return manifest

    def list(self, *, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        """List immutable Results from the disposable index, newest first."""

        if limit < 1:
            raise ValueError("Result list limit must be positive")
        if not self.index_path.is_file():
            self.rebuild_index()
        connection = _connect(self.index_path)
        try:
            if status is None:
                rows = connection.execute(
                    """
                    SELECT result_id, relative_path, status, created_at, last_accessed_at
                    FROM results ORDER BY created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT result_id, relative_path, status, created_at, last_accessed_at
                    FROM results WHERE status = ? ORDER BY created_at DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        finally:
            connection.close()
        values: list[dict[str, Any]] = []
        for result_id, relative_path, result_status, created_at, last_accessed_at in rows:
            target: dict[str, Any] = {}
            output_count = 0
            try:
                manifest = json.loads(
                    (self.root / relative_path / "manifest.json").read_text(encoding="utf-8")
                )
                target = manifest.get("result", {}).get("target") or {}
                output_count = len(manifest.get("result", {}).get("outputs", []))
            except (OSError, json.JSONDecodeError):
                pass
            values.append(
                {
                    "result_id": result_id,
                    "status": result_status,
                    "created_at": created_at,
                    "last_accessed_at": last_accessed_at,
                    "target": target,
                    "outputs": output_count,
                }
            )
        return values

    def _touch(self, result_id: str, relative_path: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        connection = _connect(self.index_path)
        try:
            now = _iso()
            status = "ready"
            manifest_path = self.root / relative_path / "manifest.json"
            try:
                status = str(json.loads(manifest_path.read_text(encoding="utf-8"))["status"])
            except (OSError, KeyError, json.JSONDecodeError):
                pass
            connection.execute(
                """
                INSERT INTO results VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(result_id) DO UPDATE SET
                    relative_path=excluded.relative_path,
                    status=excluded.status,
                    last_accessed_at=excluded.last_accessed_at
                """,
                (result_id, relative_path, status, now, now),
            )
            connection.commit()
        finally:
            connection.close()

    def resolve_output(
        self, manifest: dict[str, Any], reference: str | None
    ) -> dict[str, Any]:
        outputs = list(manifest["result"].get("outputs", []))
        if reference is None:
            if len(outputs) != 1:
                raise ValidationFailure(
                    "This Result contains multiple Outputs; choose one by canonical reference",
                    details={
                        "code": "analysis_result_output_required",
                        "outputs": [item["reference"] for item in outputs],
                    },
                )
            return outputs[0]
        raw = reference.strip()
        matches = [
            item
            for item in outputs
            if raw == item.get("reference")
        ]
        if len(matches) != 1:
            raise ValidationFailure(
                f"Unknown Result Output: {reference}",
                details={
                    "code": "analysis_result_output_unknown",
                    "output": reference,
                    "available": [item["reference"] for item in outputs],
                },
            )
        return matches[0]

    def read_output(
        self,
        manifest: dict[str, Any],
        output: dict[str, Any],
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Any, int | None]:
        storage = output["storage"]
        if storage["mode"] == "source-receipt":
            path = (
                self.workspace / storage["path"]
                if storage.get("path_kind") == "workspace-relative"
                else Path(storage["path"])
            ).resolve()
            if not path.is_file():
                raise ValidationFailure(
                    "The File Source used by this Result no longer exists",
                    details={"code": "analysis_result_source_missing", "path": storage["path"]},
                )
            if sha256_file(path) != storage["content_hash"]:
                raise ValidationFailure(
                    "The File Source used by this Result has changed",
                    details={"code": "analysis_result_source_changed", "path": storage["path"]},
                )
            value = self._read_source(path, storage["format"], storage.get("options") or {})
        else:
            result_root = self.root / manifest["result_id"]
            path = (result_root / storage["path"]).resolve()
            if not path.is_relative_to(result_root.resolve()) or not path.is_file():
                raise ValidationFailure(
                    "Managed Result Artifact is missing",
                    details={"code": "analysis_result_artifact_missing"},
                )
            if sha256_file(path) != storage["content_hash"]:
                raise ValidationFailure(
                    "Managed Result Artifact hash does not match",
                    details={"code": "analysis_result_artifact_changed"},
                )
            if output.get("kind") == "table":
                value = pd.read_parquet(path)
            elif output.get("kind") in {"text", "html"}:
                value = path.read_text(encoding="utf-8")
            else:
                value = json.loads(path.read_text(encoding="utf-8"))
        if output.get("kind") == "table":
            total = len(value)
            return value.iloc[offset : offset + limit], total
        return value, None

    @staticmethod
    def _read_source(path: Path, format_name: str, options: dict[str, Any]) -> pd.DataFrame:
        normalized = format_name.casefold()
        if normalized in {"csv", "txt"}:
            return pd.read_csv(path, **options)
        if normalized in {"parquet", "pq"}:
            return pd.read_parquet(path, **options)
        if normalized in {"json", "jsonl"}:
            effective = dict(options)
            if normalized == "jsonl":
                effective.setdefault("lines", True)
            return pd.read_json(path, **effective)
        if normalized in {"xlsx", "xls"}:
            return pd.read_excel(path, **options)
        raise ValidationFailure(
            f"Unsupported File Source format in Result: {format_name}",
            details={"code": "analysis_result_source_format_unsupported"},
        )

    def export_output(
        self, manifest: dict[str, Any], output: dict[str, Any], destination: Path
    ) -> Path:
        storage = output["storage"]
        if storage["mode"] == "source-receipt":
            source = (
                self.workspace / storage["path"]
                if storage.get("path_kind") == "workspace-relative"
                else Path(storage["path"])
            ).resolve()
            if not source.is_file():
                raise ValidationFailure(
                    "The File Source used by this Result no longer exists",
                    details={"code": "analysis_result_source_missing", "path": storage["path"]},
                )
        else:
            source = (self.root / manifest["result_id"] / storage["path"]).resolve()
        if sha256_file(source) != storage["content_hash"]:
            raise ValidationFailure(
                "The Result Output source has changed",
                details={"code": "analysis_result_source_changed", "path": str(source)},
            )
        target = destination.expanduser().resolve()
        if target.exists() and target.is_dir():
            target = target / source.name
        atomic_copy_file(source, target, expected_sha256=storage["content_hash"])
        return target

    def cleanup(self, *, retention_days: int = RESULT_RETENTION_DAYS) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.index_path.is_file():
            self.rebuild_index()
        marker = self.root / ".last-gc"
        now = _now()
        if marker.is_file():
            try:
                last = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
                if now - last < timedelta(days=1):
                    return {"status": "skipped", "removed": 0}
            except (OSError, ValueError):
                pass
        removed = 0
        cutoff = now - timedelta(days=retention_days)
        with _exclusive_lock(self.lock_path):
            if self.leases_root.is_dir():
                stale_lease_cutoff = now.timestamp() - 3600
                for lease in self.leases_root.iterdir():
                    try:
                        if lease.is_file() and lease.stat().st_mtime < stale_lease_cutoff:
                            lease.unlink(missing_ok=True)
                    except OSError:
                        continue
            connection = _connect(self.index_path)
            try:
                rows = connection.execute(
                    "SELECT result_id, relative_path, last_accessed_at FROM results"
                ).fetchall()
                for result_id, relative_path, accessed in rows:
                    try:
                        expired = datetime.fromisoformat(accessed) < cutoff
                    except ValueError:
                        expired = False
                    if not expired or any(self.leases_root.glob(f"{result_id}-*")):
                        continue
                    source = self.root / relative_path
                    trash = self.trash_root / f"{result_id}-{uuid.uuid4().hex[:8]}"
                    self.trash_root.mkdir(parents=True, exist_ok=True)
                    if source.exists():
                        os.replace(source, trash)
                        shutil.rmtree(trash, ignore_errors=True)
                    connection.execute("DELETE FROM results WHERE result_id = ?", (result_id,))
                    removed += 1
                connection.commit()
            finally:
                connection.close()
            atomic_write_text(marker, _iso(now) + "\n")
        return {"status": "ready", "removed": removed}


def result_manifest_hash(manifest: dict[str, Any]) -> str:
    content = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
