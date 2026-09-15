"""Durable user state for standalone inputs; not an automatically evicted cache."""
import os
import sys
from pathlib import Path

from dataviz.errors import WorkspaceError


def standalone_state_home() -> Path:
    explicit = os.environ.get("DATAVIZ_STATE_DIR")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            raise WorkspaceError("DATAVIZ_STATE_DIR must be an absolute path")
        return path.resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Dataviz"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Dataviz"
    xdg = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    if not xdg.is_absolute():
        raise WorkspaceError("XDG_STATE_HOME must be an absolute path")
    return xdg / "dataviz"
