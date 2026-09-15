"""Watch authoring inputs, while keeping each installed generation immutable."""
from __future__ import annotations

import json
import threading
import sqlite3
from pathlib import Path

from dataviz.server.hot_reload import WorkspaceFileWatcher
from dataviz.standalone import prepare_input
from dataviz.errors import WorkspaceError


def local_auto_eligible(workspace) -> bool:
    """Local file, unbound Python and readonly bound SQL inputs, no domains.

    Python analysis is author-supplied trusted code, not a sandbox. An external
    Adapter is never silently classified as a local read. Unbound Python is
    author-trusted code; this classification cannot inspect its side effects.
    """
    metadata_path = workspace.root / ".dataviz" / "standalone.json"
    if not metadata_path.is_file():
        return False
    metadata = json.loads(metadata_path.read_text())
    bound = set(metadata.get("data_adapters", {}))
    if not workspace.dashboards:
        return False
    projections = []
    for dashboard in workspace.dashboards.values():
        pages = dashboard.project_definition.pages if dashboard.project_definition else []
        projections.extend(workspace.dashboard(dashboard.definition.id, page.id) for page in pages)
        if not pages:
            projections.append(dashboard)
    for dashboard in projections:
        if dashboard.parameter_domains:
            return False
        for _, source in dashboard.sources.values():
            if source.type == "file" and not getattr(source, "adapter", None):
                continue
            if source.type == "python" and source.adapter is None and not metadata.get("auth"):
                continue
            if source.type == "sql" and source.adapter in bound:
                continue
            return False
    return True


class StandaloneInput:
    def __init__(self, source: Path, root: Path, *, auth=None, data=None):
        self.source = (source / "dashboard.yaml" if source.is_dir() else source).resolve()
        self.root = root
        self.auth = auth
        self.data = data
        self.lock = threading.RLock()
        self.paths = self._dependencies(root)
        self.signature = self.scan()

    @staticmethod
    def _dependencies(root):
        metadata = json.loads((root / ".dataviz" / "standalone.json").read_text())
        return tuple(Path(value) for value in metadata["dependencies"])

    def scan(self):
        result = {}
        for path in self.paths:
            try:
                stat = path.stat()
                result[str(path)] = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            except OSError:
                result[str(path)] = None
        return result

    def prepare(self):
        with self.lock:
            before = self.scan()
            if before == self.signature:
                return self.root
            attempted = set()
            try:
                root, _ = prepare_input(self.source, auth=self.auth, data=self.data, _dependencies=attempted)
            except (OSError, sqlite3.Error) as error:
                raise WorkspaceError("Local input could not be read", file=self.source,
                                     details={"reason": str(error)}) from error
            finally:
                self.paths = tuple(set(self.paths) | attempted)
            after = self.scan()
            if any(after.get(path) != stamp for path, stamp in before.items()):
                raise WorkspaceError("Inputs changed while loading; waiting for a stable edit", file=self.source)
            self.paths = self._dependencies(root)
            self.root = root
            # Do not swallow edits made during compilation. Their next scan
            # must differ so another complete generation can be installed.
            self.signature = {str(path): before.get(str(path)) for path in self.paths}
            return root

    def watcher(self, callback):
        owner = self

        class InputWatcher(WorkspaceFileWatcher):
            def _scan(self):
                return owner.scan()

        return InputWatcher(self.source.parent, callback)
