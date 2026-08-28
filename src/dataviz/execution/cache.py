from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.execution.node_support import hash_path
from dataviz.execution.outputs import OutputBundle
from dataviz.filesystem import atomic_write_text
from dataviz.workspace.models import CacheDefinition


_CACHE_LOCKS_GUARD = threading.Lock()
_CACHE_LOCKS: dict[Path, threading.RLock] = {}


def _cache_lock(workspace_root: Path) -> threading.RLock:
    key = workspace_root.resolve()
    with _CACHE_LOCKS_GUARD:
        return _CACHE_LOCKS.setdefault(key, threading.RLock())


class NodeCache:
    def __init__(
        self,
        workspace_root: Path,
        namespace: str | None = None,
        *,
        key_salt: str | None = None,
    ):
        self.workspace_root = workspace_root.resolve()
        self.root = self.workspace_root / ".dataviz" / "cache"
        self.root.mkdir(parents=True, exist_ok=True)
        self.namespace = namespace
        self.key_salt = key_salt
        self.memory: dict[str, tuple[float, OutputBundle]] = {}
        self.lock = _cache_lock(self.workspace_root)

    def policy_root(self, policy: CacheDefinition) -> Path:
        if policy.scope == "workspace":
            return self.root / "workspace"
        namespace = self.namespace or "cli"
        digest = hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:24]
        return self.root / "tabs" / digest

    def key(self, payload: dict[str, Any]) -> str:
        effective = (
            {"analysis_cache_salt": self.key_salt, "payload": payload}
            if self.key_salt is not None
            else payload
        )
        raw = json.dumps(effective, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _validate_key(key: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("Invalid cache key")

    @staticmethod
    def _artifacts_exist(values: OutputBundle, store: ArtifactStore) -> bool:
        for descriptor in values.values():
            path = store.resolve_managed(descriptor)
            if not path.is_file():
                return False
            if hash_path(path) != descriptor.content_hash:
                return False
        return True

    @staticmethod
    def _materialize(values: OutputBundle, store: ArtifactStore) -> OutputBundle:
        return {
            name: store.materialize(descriptor)
            for name, descriptor in values.items()
        }

    def load(
        self, key: str, policy: CacheDefinition, store: ArtifactStore
    ) -> OutputBundle | None:
        self._validate_key(key)
        with self.lock:
            if policy.mode == "none":
                return None
            if key in self.memory:
                created_at, values = self.memory[key]
                expired = (
                    policy.mode == "ttl"
                    and policy.ttl_seconds is not None
                    and time.time() - created_at > policy.ttl_seconds
                )
                try:
                    available = self._artifacts_exist(values, store)
                except ValueError:
                    available = False
                if not expired and available:
                    try:
                        return self._materialize(values, store)
                    except (OSError, ValueError):
                        self.memory.pop(key, None)
                        return None
                self.memory.pop(key, None)
            if policy.mode not in {"ttl", "persistent"}:
                return None
            metadata_path = self.policy_root(policy) / key / "result.json"
            if not metadata_path.exists():
                return None
            try:
                modified_at = metadata_path.stat().st_mtime
                if policy.mode == "ttl" and policy.ttl_seconds is not None:
                    if time.time() - modified_at > policy.ttl_seconds:
                        shutil.rmtree(metadata_path.parent, ignore_errors=True)
                        return None
                raw = json.loads(metadata_path.read_text("utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("Cache result must be an object")
                values = {
                    name: ArtifactDescriptor.model_validate(item)
                    for name, item in raw.items()
                }
                if not self._artifacts_exist(values, store):
                    raise ValueError("Cache artifact is missing")
            except (OSError, json.JSONDecodeError, TypeError, ValueError, ValidationError):
                shutil.rmtree(metadata_path.parent, ignore_errors=True)
                self.memory.pop(key, None)
                return None
            self.memory[key] = (modified_at, values)
            try:
                return self._materialize(values, store)
            except (OSError, ValueError):
                self.memory.pop(key, None)
                shutil.rmtree(metadata_path.parent, ignore_errors=True)
                return None

    def save(self, key: str, policy: CacheDefinition, outputs: OutputBundle, store: ArtifactStore) -> None:
        self._validate_key(key)
        with self.lock:
            if policy.mode == "none":
                return
            if policy.mode == "session":
                self.memory[key] = (
                    time.time(),
                    {name: value.model_copy(deep=True) for name, value in outputs.items()},
                )
                return
            cache_dir = self.policy_root(policy) / key
            versions = cache_dir / "versions"
            version = uuid.uuid4().hex
            staging = versions / f".{version}.tmp"
            published = versions / version
            artifact_dir = staging / "artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=False)
            cached: OutputBundle = {}
            committed = False
            try:
                for name, artifact in outputs.items():
                    source = store.resolve(artifact)
                    staged_destination = artifact_dir / source.name
                    shutil.copy2(source, staged_destination)
                    final_destination = published / "artifacts" / source.name
                    relative = str(final_destination.relative_to(self.workspace_root))
                    cached[name] = artifact.model_copy(update={"path": relative})
                metadata = json.dumps(
                    {name: item.model_dump(by_alias=True) for name, item in cached.items()},
                    ensure_ascii=False,
                    default=str,
                )
                staging.replace(published)
                atomic_write_text(cache_dir / "result.json", metadata)
                committed = True
            except OSError:
                return
            finally:
                shutil.rmtree(staging, ignore_errors=True)
                if not committed:
                    shutil.rmtree(published, ignore_errors=True)
            stale_unversioned_artifacts = cache_dir / "artifacts"
            shutil.rmtree(stale_unversioned_artifacts, ignore_errors=True)
            try:
                old_versions = [child for child in versions.iterdir() if child != published]
            except OSError:
                old_versions = []
            for child in old_versions:
                shutil.rmtree(child, ignore_errors=True)
            self.memory[key] = (
                time.time(),
                {name: value.model_copy(deep=True) for name, value in cached.items()},
            )

    def prune_memory(
        self,
        *,
        max_entries: int | None = None,
        max_age_seconds: float | None = None,
        now: float | None = None,
    ) -> int:
        """Bound one tab's in-memory cache without changing persistent entries."""
        with self.lock:
            current = time.time() if now is None else now
            expired = {
                key
                for key, (created_at, _) in self.memory.items()
                if max_age_seconds is not None and current - created_at > max_age_seconds
            }
            if max_entries is not None:
                newest = sorted(
                    self.memory,
                    key=lambda key: self.memory[key][0],
                    reverse=True,
                )
                expired.update(newest[max_entries:])
            for key in expired:
                self.memory.pop(key, None)
            return len(expired)
