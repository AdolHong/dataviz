from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from dataviz.artifacts import ArtifactDescriptor, ArtifactStore
from dataviz.workspace.models import CacheDefinition


class NodeCache:
    def __init__(self, workspace_root: Path, namespace: str | None = None):
        self.workspace_root = workspace_root
        self.root = workspace_root / ".dataviz" / "cache"
        self.root.mkdir(parents=True, exist_ok=True)
        self.namespace = namespace
        self.memory: dict[str, list[ArtifactDescriptor]] = {}

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
    ) -> list[ArtifactDescriptor] | None:
        if policy.mode == "none":
            return None
        if key in self.memory:
            return self.memory[key]
        if policy.mode not in {"ttl", "persistent"}:
            return None
        metadata_path = self.policy_root(policy) / key / "result.json"
        if not metadata_path.exists():
            return None
        if policy.mode == "ttl" and policy.ttl_seconds is not None:
            if time.time() - metadata_path.stat().st_mtime > policy.ttl_seconds:
                return None
        values = [ArtifactDescriptor.model_validate(item) for item in json.loads(metadata_path.read_text("utf-8"))]
        self.memory[key] = values
        return values

    def save(self, key: str, policy: CacheDefinition, artifacts: list[ArtifactDescriptor], store: ArtifactStore) -> None:
        if policy.mode == "none":
            return
        if policy.mode == "session":
            self.memory[key] = artifacts
            return
        cache_dir = self.policy_root(policy) / key
        artifact_dir = cache_dir / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        cached: list[ArtifactDescriptor] = []
        for artifact in artifacts:
            source = store.resolve(artifact)
            if not source:
                cached.append(artifact)
                continue
            destination = artifact_dir / source.name
            shutil.copy2(source, destination)
            relative = str(destination.relative_to(self.workspace_root))
            cached.append(artifact.model_copy(update={"path": relative}))
        (cache_dir / "result.json").write_text(
            json.dumps([item.model_dump(by_alias=True) for item in cached], ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        self.memory[key] = cached
