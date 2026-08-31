"""Immutable loaded Workspace snapshots and their lazy compiled contracts."""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from threading import Lock
from typing import Any


from dataviz.errors import Diagnostic, WorkspaceError
from dataviz.execution.dependencies import (
    DashboardDependencyContract,
    compile_dashboard_dependencies,
)
from dataviz.execution.parameter_domains import (
    ParameterDomainContract,
    compile_parameter_domain_contract,
)
from dataviz.layout import DashboardLayoutContract, compile_layout_contract
from dataviz.workspace.models import (
    DashboardDefinition,
    DatasetTransformDefinition,
    DeclarativeViewDefinition,
    InteractiveTransformDefinition,
    NavigationItem,
    ParameterDomainDefinition,
    PresentationDefinition,
    SourceDefinition,
    TrashItemDefinition,
    WorkspaceDefinition,
)
from dataviz.workspace.naming import (
    decode_dashboard_name,
)


@dataclass(slots=True)
class LoadedDashboard:
    root: Path
    definition_path: Path
    definition: DashboardDefinition
    logic_definition: DashboardDefinition
    sources: dict[str, tuple[Path, SourceDefinition]]
    parameter_domains: dict[str, tuple[Path, ParameterDomainDefinition]]
    dataset_transforms: dict[str, tuple[Path, DatasetTransformDefinition]]
    interactive_transforms: dict[str, tuple[Path, InteractiveTransformDefinition]]
    views: dict[str, DeclarativeViewDefinition]
    presentation_path: Path | None = None
    presentation: PresentationDefinition | None = None
    presentation_diagnostics: list[Diagnostic] | None = None
    readme: str = ""
    # Internal execution metadata for an immutable, one-run Analysis Variant.
    # This is never populated by Workspace loading and is not part of the DSL.
    analysis_overlay: dict[str, Any] | None = None
    _dependency_contract: DashboardDependencyContract | None = dataclass_field(
        default=None,
        init=False,
        repr=False,
    )
    _dependency_contract_lock: Lock = dataclass_field(
        default_factory=Lock,
        init=False,
        repr=False,
    )
    _layout_contract: DashboardLayoutContract | None = dataclass_field(
        default=None,
        init=False,
        repr=False,
    )
    _layout_contract_lock: Lock = dataclass_field(
        default_factory=Lock,
        init=False,
        repr=False,
    )
    _parameter_domain_contract: ParameterDomainContract | None = dataclass_field(
        default=None,
        init=False,
        repr=False,
    )
    _parameter_domain_contract_lock: Lock = dataclass_field(
        default_factory=Lock,
        init=False,
        repr=False,
    )

    @property
    def dependency_contract(self) -> DashboardDependencyContract:
        """Return the one compiled graph owned by this immutable load snapshot.

        Workspace hot reload creates a new ``LoadedDashboard``. Every consumer
        inside one snapshot therefore observes the exact same Query, Control,
        Interactive and View dependency graph instead of independently deriving
        relationships from the mutable DSL model.
        """

        if self._dependency_contract is None:
            with self._dependency_contract_lock:
                if self._dependency_contract is None:
                    self._dependency_contract = compile_dashboard_dependencies(self)
        return self._dependency_contract

    @property
    def layout_contract(self) -> DashboardLayoutContract:
        """Return the only compiled owner of declarative page structure."""

        if self._layout_contract is None:
            with self._layout_contract_lock:
                if self._layout_contract is None:
                    self._layout_contract = compile_layout_contract(self)
        return self._layout_contract

    @property
    def parameter_domain_contract(self) -> ParameterDomainContract:
        if self._parameter_domain_contract is None:
            with self._parameter_domain_contract_lock:
                if self._parameter_domain_contract is None:
                    self._parameter_domain_contract = compile_parameter_domain_contract(self)
        return self._parameter_domain_contract

    @property
    def canvas_name(self) -> str:
        """Filesystem-owned display name used by navigation and sharing."""
        try:
            return decode_dashboard_name(self.root.name).leaf
        except WorkspaceError:
            return self.root.name

    @property
    def title(self) -> str:
        """Page title, falling back to the filesystem Canvas Name."""
        return self.definition.title.strip() or self.canvas_name


@dataclass(slots=True)
class DashboardCatalogEntry:
    """One runtime navigation entry, including unavailable workspace references."""

    id: str
    canvas_name: str
    title: str
    path: Path
    relative_path: str
    status: str
    dashboard: LoadedDashboard | None = None
    discovered: bool = False
    message: str | None = None
    parent_id: str | None = None
    logical_path: str = ""

    @property
    def runnable(self) -> bool:
        return self.dashboard is not None


@dataclass(slots=True)
class LoadedWorkspace:
    root: Path
    definition_path: Path
    definition: WorkspaceDefinition
    dashboards: dict[str, LoadedDashboard]
    catalog: list[DashboardCatalogEntry]
    load_diagnostics: list[Diagnostic]
    navigation: list[NavigationItem]
    trash: list[TrashItemDefinition]
    readme: str = ""

    @property
    def state_dir(self) -> Path:
        return self.root / ".dataviz"

    def dashboard(self, identifier: str) -> LoadedDashboard:
        if identifier in self.dashboards:
            return self.dashboards[identifier]
        raise WorkspaceError(f"Unknown dashboard: {identifier}")

    def catalog_entry(self, identifier: str) -> DashboardCatalogEntry:
        for entry in self.catalog:
            if entry.id == identifier:
                return entry
        raise WorkspaceError(f"Unknown dashboard: {identifier}")
