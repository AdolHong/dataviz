from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from dataviz.errors import ExecutionFailure


def load_module(path: Path) -> ModuleType:
    if not path.exists():
        raise ExecutionFailure("Python code file does not exist", file=path)
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    module_name = f"dataviz_workspace_{digest}_{path.stat().st_mtime_ns}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ExecutionFailure("Unable to import Python file", file=path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    code_root = str(path.parent)
    inserted = code_root not in sys.path
    if inserted:
        sys.path.insert(0, code_root)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ExecutionFailure(f"Failed to import Python file: {exc}", file=path) from exc
    return module


def load_entrypoint(path: Path, name: str):
    module = load_module(path)
    function = getattr(module, name, None)
    if not callable(function):
        raise ExecutionFailure(f"Python entrypoint is not callable: {name}", file=path)
    return function
