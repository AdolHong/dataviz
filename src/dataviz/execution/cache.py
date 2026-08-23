from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.execution.outputs import OutputBundle
from dataviz.workspace.models import CacheDefinition


class NodeCache:
    def __init__(self, workspace_root: Path, namespace: str | None = None):
        self.workspace_root = workspace_root
        self.root = workspace_root / ".dataviz" / "cache"
        self.root.mkdir(parents=True, exist_ok=True)
        self.namespace = namespace
        self.memory: dict[str, tuple[float, OutputBundle]] = {}

    def policy_root(self, policy: CacheDefinition) -> Path:
        if policy.scope == "workspace":
            return self.root / "workspace"
        namespace = self.namespace or "cli"
        digest = hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:24]
        return self.root / "tabs" / digest

    def key(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def load(
        self, key: str, policy: CacheDefinition, store: ArtifactStore
    ) -> OutputBundle | None:
        if policy.mode == "none":
            return None
        if key in self.memory:
            created_at, values = self.memory[key]
            expired = (
                policy.mode == "ttl"
                and policy.ttl_seconds is not None
                and time.time() - created_at > policy.ttl_seconds
            )
            missing = any(
                descriptor.path
                and not (self.workspace_root / descriptor.path).exists()
                for descriptor in values.values()
            )
            if not expired and not missing:
                return values
            self.memory.pop(key, None)
        if policy.mode not in {"ttl", "persistent"}:
            return None
        metadata_path = self.policy_root(policy) / key / "result.json"
        if not metadata_path.exists():
            return None
        if policy.mode == "ttl" and policy.ttl_seconds is not None:
            if time.time() - metadata_path.stat().st_mtime > policy.ttl_seconds:
                shutil.rmtree(metadata_path.parent, ignore_errors=True)
                return None
        raw = json.loads(metadata_path.read_text("utf-8"))
        values = {name: ArtifactDescriptor.model_validate(item) for name, item in raw.items()}
        self.memory[key] = (metadata_path.stat().st_mtime, values)
        return values

    def save(self, key: str, policy: CacheDefinition, outputs: OutputBundle, store: ArtifactStore) -> None:
        if policy.mode == "none":
            return
        if policy.mode == "session":
            self.memory[key] = (time.time(), outputs)
            return
        cache_dir = self.policy_root(policy) / key
        artifact_dir = cache_dir / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        cached: OutputBundle = {}
        for name, artifact in outputs.items():
            source = store.resolve(artifact)
            if not source:
                cached[name] = artifact
                continue
            destination = artifact_dir / source.name
            shutil.copy2(source, destination)
            relative = str(destination.relative_to(self.workspace_root))
            cached[name] = artifact.model_copy(update={"path": relative})
        (cache_dir / "result.json").write_text(
            json.dumps(
                {name: item.model_dump(by_alias=True) for name, item in cached.items()},
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )
        self.memory[key] = (time.time(), cached)

    def prune_memory(
        self,
        *,
        max_entries: int | None = None,
        max_age_seconds: float | None = None,
        now: float | None = None,
    ) -> int:
        """Bound one tab's in-memory cache without changing persistent entries."""
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
