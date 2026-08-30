"""Stable Workspace loading façade.

Physical ownership is split by responsibility under ``workspace.loading``.
Existing callers intentionally keep importing this module so refactoring does
not alter the public Python API, CLI diagnostics, or Runtime contracts.
"""

from dataviz.workspace.loading.catalog_navigation import load_workspace
from dataviz.workspace.loading.contract_validation import (
    dashboard_validation_diagnostics,
    validate_workspace,
)
from dataviz.workspace.loading.loaded_types import (
    DashboardCatalogEntry,
    LoadedDashboard,
    LoadedWorkspace,
)
from dataviz.workspace.loading.parse_load import (
    load_dashboard,
    parse_model,
    parse_source_definition,
    read_yaml,
)

__all__ = [
    "DashboardCatalogEntry",
    "LoadedDashboard",
    "LoadedWorkspace",
    "dashboard_validation_diagnostics",
    "load_dashboard",
    "load_workspace",
    "parse_model",
    "parse_source_definition",
    "read_yaml",
    "validate_workspace",
]
