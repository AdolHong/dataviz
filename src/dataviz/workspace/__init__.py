"""Public Workspace API without eager cross-module imports.

The loader validates content templates while the content compiler depends on the
Control contract. Lazy exports keep those owner modules independent and make
``dataviz.workspace.controls`` safe to import directly.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "compile_control_contract": ("dataviz.workspace.controls", "compile_control_contract"),
    "resolve_compute_values": ("dataviz.workspace.controls", "resolve_compute_values"),
    "resolve_control_values": ("dataviz.workspace.controls", "resolve_control_values"),
    "resolve_selection_states": ("dataviz.workspace.controls", "resolve_selection_states"),
    "project_selection_values": ("dataviz.workspace.controls", "project_selection_values"),
    "scoped_control_registry": ("dataviz.workspace.controls", "scoped_control_registry"),
    "DashboardCatalogEntry": ("dataviz.workspace.loader", "DashboardCatalogEntry"),
    "LoadedDashboard": ("dataviz.workspace.loader", "LoadedDashboard"),
    "LoadedWorkspace": ("dataviz.workspace.loader", "LoadedWorkspace"),
    "dashboard_validation_diagnostics": (
        "dataviz.workspace.loader",
        "dashboard_validation_diagnostics",
    ),
    "load_workspace": ("dataviz.workspace.loader", "load_workspace"),
    "validate_workspace": ("dataviz.workspace.loader", "validate_workspace"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
