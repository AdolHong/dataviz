from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlparse

from dataviz.execution.fingerprint import query_contract_fingerprint
from dataviz.execution.node_support import hash_path
from dataviz.execution.plan import compile_plan
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace


ReloadImpact = Literal["navigation", "canvas", "analysis", "query", "server"]
_IMPACT_PRIORITY: dict[ReloadImpact, int] = {
    "navigation": 0,
    "canvas": 1,
    "analysis": 2,
    "query": 3,
    "server": 4,
}
_IGNORED_PARTS = {
    ".dataviz",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "shared_caches",
}


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_hash(path: Path) -> str:
    try:
        return hash_path(path)
    except (OSError, ValueError):
        return "<unavailable>"


def _definition_assets(
    definition_path: Path,
    definition: Any,
) -> dict[str, str]:
    values: list[str] = []
    code = getattr(definition, "code", None)
    if code:
        values.append(code)
    values.extend(getattr(definition, "code_dependencies", []))
    return {
        str((definition_path.parent / value).resolve()): _safe_hash(
            (definition_path.parent / value).resolve()
        )
        for value in values
    }


def _query_signature(dashboard: LoadedDashboard) -> str:
    try:
        plan = compile_plan(dashboard)
        contract = query_contract_fingerprint(dashboard, plan.nodes)
    except Exception as error:  # validation owns the user-facing diagnostic
        contract = f"<invalid:{type(error).__name__}:{error}>"
    code_inputs: dict[str, str] = {}
    for definition_path, definition in dashboard.sources.values():
        code_inputs.update(_definition_assets(definition_path, definition))
    for definition_path, definition in dashboard.dataset_transforms.values():
        code_inputs.update(_definition_assets(definition_path, definition))
    return _digest({"contract": contract, "code": code_inputs})


def _query_file_inputs(dashboard: LoadedDashboard) -> tuple[str, ...]:
    """Return data files by path without hashing potentially multi-GB inputs."""
    values: set[str] = set()
    for definition_path, definition in dashboard.sources.values():
        if getattr(definition, "type", None) == "file":
            values.add(str((definition_path.parent / definition.path).resolve()))
    return tuple(sorted(values))


def _analysis_signature(dashboard: LoadedDashboard) -> str:
    transforms: list[dict[str, Any]] = []
    for identifier, (definition_path, definition) in sorted(
        dashboard.interactive_transforms.items()
    ):
        transforms.append(
            {
                "id": identifier,
                "definition": definition.model_dump(mode="json", by_alias=True),
                "assets": _definition_assets(definition_path, definition),
            }
        )
    logic = dashboard.logic_definition
    controls = {
        "dashboard": [
            item.model_dump(mode="json", by_alias=True) for item in logic.controls
        ],
        "sections": {
            section.id: [
                item.model_dump(mode="json", by_alias=True)
                for item in section.controls
            ]
            for section in logic.sections
        },
        "views": {
            view.id: {
                "controls": [
                    item.model_dump(mode="json", by_alias=True)
                    for item in view.controls
                ],
                "selection_bindings": {
                    key: (
                        value
                        if isinstance(value, str)
                        else value.model_dump(mode="json", by_alias=True)
                    )
                    for key, value in view.selection_bindings.items()
                },
            }
            for view in logic.views
        },
    }
    return _digest({"transforms": transforms, "controls": controls})


def _canvas_signature(dashboard: LoadedDashboard) -> str:
    """Fingerprint only files and declarations that can alter the rendered Canvas."""
    definition = dashboard.definition
    asset_paths: set[Path] = set()
    for value in [
        definition.canvas.template,
        *definition.canvas.styles,
        *definition.canvas.scripts,
    ]:
        if value:
            asset_paths.add((dashboard.root / value).resolve())
    for view in definition.views:
        if view.template != "image" or not view.url:
            continue
        parsed = urlparse(view.url)
        if not parsed.scheme and not parsed.netloc:
            asset_paths.add((dashboard.root / parsed.path).resolve())
    readme_path = dashboard.root / "README.md"
    if readme_path.is_file():
        asset_paths.add(readme_path.resolve())
    return _digest(
        {
            "definition": definition.model_dump(mode="json", by_alias=True),
            "assets": {
                str(path): _safe_hash(path)
                for path in sorted(asset_paths, key=str)
            },
        }
    )


@dataclass(frozen=True, slots=True)
class DashboardSemanticSnapshot:
    root: str
    query: str
    query_files: tuple[str, ...]
    analysis: str
    canvas: str


@dataclass(frozen=True, slots=True)
class WorkspaceSemanticSnapshot:
    dashboards: dict[str, DashboardSemanticSnapshot]
    catalog: dict[str, tuple[str, str, str | None, str]]
    query_environment: str
    server_environment: str

    @classmethod
    def from_workspace(cls, workspace: LoadedWorkspace) -> "WorkspaceSemanticSnapshot":
        dashboards = {
            identifier: DashboardSemanticSnapshot(
                root=str(dashboard.root.resolve()),
                query=_query_signature(dashboard),
                query_files=_query_file_inputs(dashboard),
                analysis=_analysis_signature(dashboard),
                canvas=_canvas_signature(dashboard),
            )
            for identifier, dashboard in workspace.dashboards.items()
        }
        catalog = {
            entry.id: (
                str(entry.path.resolve()),
                entry.status,
                entry.parent_id,
                entry.logical_path,
            )
            for entry in workspace.catalog
        }
        definition = workspace.definition
        query_environment = _digest(
            {
                "context": definition.context.model_dump(mode="json", by_alias=True),
            }
        )
        server_environment = _digest(
            {
                "id": definition.id,
                "runtime": definition.runtime.model_dump(mode="json", by_alias=True),
            }
        )
        return cls(
            dashboards=dashboards,
            catalog=catalog,
            query_environment=query_environment,
            server_environment=server_environment,
        )


def classify_workspace_change(
    previous: WorkspaceSemanticSnapshot,
    current: WorkspaceSemanticSnapshot,
    changed_paths: set[str],
) -> tuple[dict[str, ReloadImpact], bool]:
    """Classify hot reload by semantic boundary, never by filename alone."""

    impacts: dict[str, ReloadImpact] = {}

    def promote(identifier: str, impact: ReloadImpact) -> None:
        existing = impacts.get(identifier)
        if existing is None or _IMPACT_PRIORITY[impact] > _IMPACT_PRIORITY[existing]:
            impacts[identifier] = impact

    previous_ids = set(previous.dashboards)
    current_ids = set(current.dashboards)
    for identifier in sorted(previous_ids | current_ids):
        before = previous.dashboards.get(identifier)
        after = current.dashboards.get(identifier)
        if before is None or after is None:
            promote(identifier, "canvas")
            continue
        query_files = {Path(path) for path in before.query_files} | {
            Path(path) for path in after.query_files
        }
        query_file_changed = any(
            Path(path).resolve() == candidate.resolve()
            for path in changed_paths
            for candidate in query_files
        )
        if before.query != after.query or query_file_changed:
            promote(identifier, "query")
        elif before.analysis != after.analysis:
            promote(identifier, "analysis")
        elif before.canvas != after.canvas:
            promote(identifier, "canvas")
        elif before.root != after.root:
            promote(identifier, "navigation")

    navigation_changed = previous.catalog != current.catalog
    if previous.query_environment != current.query_environment:
        for identifier in current_ids:
            promote(identifier, "query")
    if previous.server_environment != current.server_environment:
        for identifier in current_ids:
            promote(identifier, "server")

    adapter_changed = any(
        Path(path).name.startswith("adapter") and Path(path).suffix in {".yaml", ".yml"}
        for path in changed_paths
    )
    if adapter_changed:
        for identifier in current_ids:
            promote(identifier, "query")

    return impacts, navigation_changed


@dataclass(frozen=True, slots=True)
class WorkspaceChangeEvent:
    revision: int
    status: Literal["ready", "invalid"]
    changes: dict[str, ReloadImpact] = field(default_factory=dict)
    navigation_changed: bool = False
    changed_paths: tuple[str, ...] = ()
    diagnostics: tuple[dict[str, Any], ...] = ()
    message: str = ""
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "dataviz/workspace-change/v1",
            "revision": self.revision,
            "status": self.status,
            "changes": [
                {"dashboard_id": identifier, "impact": impact}
                for identifier, impact in sorted(self.changes.items())
            ],
            "navigation_changed": self.navigation_changed,
            "changed_paths": list(self.changed_paths),
            "diagnostics": list(self.diagnostics),
            "message": self.message,
            "timestamp": self.timestamp,
        }


class WorkspaceChangeJournal:
    def __init__(self, *, max_events: int = 200):
        self.max_events = max_events
        self._revision = 0
        self._events: list[WorkspaceChangeEvent] = []
        self._lock = threading.Lock()

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    @property
    def latest(self) -> WorkspaceChangeEvent | None:
        with self._lock:
            return self._events[-1] if self._events else None

    def publish(
        self,
        *,
        status: Literal["ready", "invalid"],
        changes: dict[str, ReloadImpact] | None = None,
        navigation_changed: bool = False,
        changed_paths: set[str] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
        message: str = "",
    ) -> WorkspaceChangeEvent:
        with self._lock:
            self._revision += 1
            event = WorkspaceChangeEvent(
                revision=self._revision,
                status=status,
                changes=dict(changes or {}),
                navigation_changed=navigation_changed,
                changed_paths=tuple(sorted(changed_paths or set())[:100]),
                diagnostics=tuple((diagnostics or [])[:50]),
                message=message,
            )
            self._events.append(event)
            if len(self._events) > self.max_events:
                del self._events[: len(self._events) - self.max_events]
            return event

    def after(self, revision: int) -> list[WorkspaceChangeEvent]:
        with self._lock:
            return [event for event in self._events if event.revision > revision]


FileState = dict[str, tuple[int, int]]


class WorkspaceFileWatcher:
    """Portable, dependency-free Workspace watcher with debounced batches."""

    def __init__(
        self,
        root: Path,
        callback: Callable[[set[str]], None],
        *,
        poll_interval: float = 0.25,
        debounce_seconds: float = 0.15,
    ):
        self.root = root.resolve()
        self.callback = callback
        self.poll_interval = poll_interval
        self.debounce_seconds = debounce_seconds
        self._files = self._scan()
        self._pending: set[str] = set()
        self._changed_at = 0.0
        self._state_lock = threading.Lock()
        self._callback_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="dataviz-workspace-watch",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.poll_interval * 4))
        self._thread = None

    def flush(self) -> bool:
        """Synchronously publish edits before an action captures a Workspace snapshot."""
        current = self._scan()
        with self._state_lock:
            self._pending.update(
                path
                for path in set(self._files) | set(current)
                if self._files.get(path) != current.get(path)
            )
            self._files = current
            batch = set(self._pending)
            self._pending.clear()
            self._changed_at = 0.0
        # Waiting for this lock also joins a batch already removed from
        # ``_pending`` by the watcher thread but not yet published.
        with self._callback_lock:
            if batch:
                self.callback(batch)
        return bool(batch)

    def _scan(self) -> FileState:
        files: FileState = {}
        for directory, names, filenames in os.walk(self.root):
            names[:] = [name for name in names if name not in _IGNORED_PARTS]
            base = Path(directory)
            for filename in filenames:
                path = base / filename
                try:
                    stat = path.stat()
                except OSError:
                    continue
                files[str(path.resolve())] = (stat.st_mtime_ns, stat.st_size)
        return files

    def _run(self) -> None:
        while not self._stop.wait(self.poll_interval):
            current = self._scan()
            with self._state_lock:
                changed = {
                    path
                    for path in set(self._files) | set(current)
                    if self._files.get(path) != current.get(path)
                }
                self._files = current
                if changed:
                    self._pending.update(changed)
                    self._changed_at = time.monotonic()
                ready = bool(
                    self._pending
                    and time.monotonic() - self._changed_at >= self.debounce_seconds
                )
                batch = set(self._pending) if ready else set()
                if ready:
                    self._pending.clear()
                    self._changed_at = 0.0
            if batch:
                try:
                    with self._callback_lock:
                        self.callback(batch)
                except Exception:
                    # The callback publishes structured diagnostics. A watcher
                    # thread must survive a malformed intermediate editor write.
                    continue
