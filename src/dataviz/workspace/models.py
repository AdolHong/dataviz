from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ContextDefinition(Model):
    language: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    currency: str | None = None


class NavigationItem(Model):
    kind: Literal["dashboard", "folder"] = "dashboard"
    id: str
    title: str
    dashboard: str | None = None
    route: str | None = None
    order: int = 0
    children: list["NavigationItem"] = Field(default_factory=list)


class TrashItemDefinition(Model):
    trash_id: str
    original_parent_id: str | None = None
    trashed_at: str
    item: NavigationItem


class WorkspaceFolderDefinition(Model):
    path: str
    order: int = 0


class RuntimeDefinition(Model):
    plotly_js: str = "bundled"
    echarts_js: str = "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"
    perspective_version: str = "5.2.0"
    max_workers: int = 4


class WorkspaceDefinition(Model):
    schema_: str = Field("dataviz/workspace/v1", alias="schema")
    kind: Literal["workspace"] = "workspace"
    id: str
    title: str
    description: str = ""
    context: ContextDefinition = Field(default_factory=ContextDefinition)
    navigation: list[NavigationItem] = Field(default_factory=list)
    trash: list[TrashItemDefinition] = Field(default_factory=list)
    folders: list[WorkspaceFolderDefinition] = Field(default_factory=list)
    runtime: RuntimeDefinition = Field(default_factory=RuntimeDefinition)


class Choice(Model):
    label: str
    value: Any


class ParameterDefinition(Model):
    id: str
    type: Literal[
        "string",
        "number",
        "boolean",
        "date",
        "date_range",
        "single_select",
        "multi_select",
    ] = "string"
    label: str | None = None
    description: str = ""
    default: Any = None
    required: bool = False
    choices: list[Choice] = Field(default_factory=list)


class SelectionDefinition(ParameterDefinition):
    """A browser-side selection applied after sources have been loaded."""

    field: str | None = None
    path_fields: list[str] = Field(default_factory=list, min_length=0)
    mode: Literal["include", "exclude"] = "include"
    cascade: bool = True


class SelectionBindingDefinition(Model):
    field: str | None = None
    operator: Literal[
        "auto",
        "equals",
        "in",
        "between",
        "contains",
        "gte",
        "lte",
        "gt",
        "lt",
    ] = "auto"


class ViewDefinition(Model):
    widget: str
    selections: list[SelectionDefinition] = Field(
        default_factory=list,
        validation_alias=AliasChoices("selections", "filters"),
    )
    selection_bindings: dict[str, str | SelectionBindingDefinition] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("selection_bindings", "filter_bindings"),
    )

    @property
    def filters(self) -> list[SelectionDefinition]:
        """Deprecated compatibility alias for pre-selection dashboards."""
        return self.selections

    @property
    def filter_bindings(self) -> dict[str, str | SelectionBindingDefinition]:
        """Deprecated compatibility alias for pre-selection dashboards."""
        return self.selection_bindings


class RepeatDefinition(Model):
    """Create multiple instances from one declarative View blueprint."""

    view: str | None = None
    source: str | None = None
    by: list[str] = Field(min_length=1)
    selection: str | None = None
    title: str = "{value}"
    limit: int | None = Field(None, ge=1)
    order_by: str | None = None
    order: Literal["asc", "desc"] = "asc"
    render: Literal["lazy", "eager"] = "lazy"
    empty_text: str = "Choose one or more items to compare."


class SectionDefinition(Model):
    id: str
    title: str
    description: str = ""
    template: Literal[
        "single",
        "stack",
        "grid",
        "split",
        "hero-metrics",
        "chart-and-table",
        "comparison",
        "band",
        "small-multiples",
        "selection-gallery",
    ] = "grid"
    columns: int | None = None
    css_class: str = Field("", validation_alias=AliasChoices("css_class", "class"))
    selections: list[SelectionDefinition] = Field(
        default_factory=list,
        validation_alias=AliasChoices("selections", "filters"),
    )
    views: list[str | ViewDefinition] = Field(default_factory=list)
    repeat: RepeatDefinition | None = None

    @property
    def filters(self) -> list[SelectionDefinition]:
        """Deprecated compatibility alias for pre-selection dashboards."""
        return self.selections


class CanvasDefinition(Model):
    template: str | None = None
    style: str | None = None
    script: str | None = None
    use_default_style: bool = True
    client_selections: bool = Field(
        False,
        validation_alias=AliasChoices("client_selections", "client_filters"),
    )
    client_sources: list[str] = Field(default_factory=list)
    client_libraries: list[Literal["plotly", "echarts", "perspective"]] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)

    @property
    def client_filters(self) -> bool:
        """Deprecated compatibility alias for pre-selection dashboards."""
        return self.client_selections


class LayoutItem(Model):
    widget: str = Field(validation_alias=AliasChoices("widget", "view"))
    x: int = 0
    y: int = 0
    width: int = 6
    height: int = 3
    min_height: int | None = None
    css_class: str = ""


class LayoutDefinition(Model):
    template: Literal["overview", "monitoring", "report", "exploration", "freeform"] = "overview"
    columns: int = 12
    row_height: int = 92
    gap: int = 18
    items: list[LayoutItem] = Field(default_factory=list)


class ThemeDefinition(Model):
    preset: Literal["plain", "editorial", "terminal", "business"] = "plain"
    accent: str | None = None
    background: str | None = None
    panel: str | None = None
    ink: str | None = None
    density: Literal["compact", "comfortable", "spacious"] = "comfortable"


class PresentationThemeDefinition(Model):
    preset: Literal["plain", "editorial", "terminal", "business"] | None = None
    accent: str | None = None
    background: str | None = None
    panel: str | None = None
    ink: str | None = None
    density: Literal["compact", "comfortable", "spacious"] | None = None


class PresentationLayoutDefinition(Model):
    template: Literal["overview", "monitoring", "report", "exploration", "freeform"] | None = None
    columns: int | None = Field(None, ge=1, le=24)
    row_height: int | None = Field(None, ge=1)
    gap: int | None = Field(None, ge=0)


class PresentationSectionDefinition(Model):
    template: Literal[
        "single",
        "stack",
        "grid",
        "split",
        "hero-metrics",
        "chart-and-table",
        "comparison",
        "band",
        "small-multiples",
        "selection-gallery",
    ] | None = None
    columns: int | None = Field(None, ge=1, le=24)
    css_class: str = Field("", validation_alias=AliasChoices("css_class", "class"))


class PresentationViewDefinition(Model):
    width: int | None = Field(None, ge=1, le=24)
    height: int | None = Field(None, ge=1)
    container: Literal["panel", "metric", "chart", "table", "plain", "elevated"] | None = None
    css_class: str = Field("", validation_alias=AliasChoices("css_class", "class"))
    engine: Literal["plotly", "echarts"] | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class PresentationSelectorDefinition(Model):
    template: Literal["auto", "chips", "dropdown", "searchable", "cascader"] = "auto"
    show_unavailable: bool = False
    search_placeholder: str = "Search options…"
    empty_text: str = "No matching options"
    placeholder: str = "Choose…"
    level_labels: list[str] = Field(default_factory=list)
    path_separator: str = " / "
    css_class: str = Field("", validation_alias=AliasChoices("css_class", "class"))


class PresentationAssetsDefinition(Model):
    css: list[str] = Field(default_factory=list)
    js: list[str] = Field(default_factory=list)


class PresentationCanvasDefinition(Model):
    template: str | None = None
    use_default_style: bool | None = None
    client_libraries: list[Literal["plotly", "echarts", "perspective"]] = Field(default_factory=list)


class PresentationDefinition(Model):
    schema_: str = Field("dataviz/presentation/v1", alias="schema")
    kind: Literal["presentation"] = "presentation"
    dashboard: str
    theme: PresentationThemeDefinition = Field(default_factory=PresentationThemeDefinition)
    layout: PresentationLayoutDefinition = Field(default_factory=PresentationLayoutDefinition)
    sections: dict[str, PresentationSectionDefinition] = Field(default_factory=dict)
    views: dict[str, PresentationViewDefinition] = Field(default_factory=dict)
    selectors: dict[str, PresentationSelectorDefinition] = Field(default_factory=dict)
    assets: PresentationAssetsDefinition = Field(default_factory=PresentationAssetsDefinition)
    canvas: PresentationCanvasDefinition = Field(default_factory=PresentationCanvasDefinition)


class DeclarativeViewDefinition(Model):
    id: str
    title: str | None = None
    description: str = ""
    template: Literal[
        "metric",
        "line",
        "bar",
        "stacked-bar",
        "pie",
        "scatter",
        "heatmap",
        "table",
        "perspective",
        "markdown",
        "image",
    ]
    engine: Literal["plotly", "echarts"] = "plotly"
    source: str | None = None
    sources: list[str] = Field(default_factory=list)
    x: str | None = None
    y: str | None = None
    z: str | None = None
    value: str | None = None
    label: str | None = None
    series: str | None = None
    color: str | None = None
    size: str | None = None
    columns: list[str] = Field(default_factory=list)
    aggregate: Literal["sum", "mean", "min", "max", "count", "none"] | None = None
    sort: str | None = None
    limit: int | None = None
    text: str | None = None
    url: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    selections: list[SelectionDefinition] = Field(
        default_factory=list,
        validation_alias=AliasChoices("selections", "filters"),
    )
    selection_bindings: dict[str, str | SelectionBindingDefinition] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("selection_bindings", "filter_bindings"),
    )

    @property
    def filters(self) -> list[SelectionDefinition]:
        """Deprecated compatibility alias for pre-selection dashboards."""
        return self.selections

    @property
    def filter_bindings(self) -> dict[str, str | SelectionBindingDefinition]:
        """Deprecated compatibility alias for pre-selection dashboards."""
        return self.selection_bindings

    @property
    def source_ids(self) -> list[str]:
        return list(dict.fromkeys(([self.source] if self.source else []) + self.sources))


class DashboardDefinition(Model):
    schema_: str = Field("dataviz/dashboard/v1", alias="schema")
    kind: Literal["dashboard"] = "dashboard"
    id: str
    title: str = ""
    subtitle: str = ""
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    adapters: dict[str, str] = Field(default_factory=dict)
    query_parameters: list[ParameterDefinition] = Field(
        default_factory=list,
        validation_alias=AliasChoices("query_parameters", "parameters"),
    )
    dashboard_selections: list[SelectionDefinition] = Field(
        default_factory=list,
        validation_alias=AliasChoices("dashboard_selections", "dashboard_filters", "filters"),
    )
    sections: list[SectionDefinition] = Field(default_factory=list)
    sources: list[str | dict[str, Any]] = Field(default_factory=list)
    widgets: list[str] = Field(default_factory=list)
    views: list[DeclarativeViewDefinition] = Field(default_factory=list)
    layout: LayoutDefinition = Field(default_factory=LayoutDefinition)
    theme: ThemeDefinition = Field(default_factory=ThemeDefinition)
    canvas: CanvasDefinition = Field(default_factory=CanvasDefinition)

    @property
    def dashboard_filters(self) -> list[SelectionDefinition]:
        """Deprecated compatibility alias for pre-selection dashboards."""
        return self.dashboard_selections


# Public import aliases keep Python integrations working while YAML and runtime
# output use the clearer selection terminology.
FilterDefinition = SelectionDefinition
FilterBindingDefinition = SelectionBindingDefinition


class CacheDefinition(Model):
    mode: Literal["none", "session", "ttl", "persistent"] = "session"
    scope: Literal["tab", "workspace"] = "tab"
    ttl_seconds: int | None = None


class SourceDefinition(Model):
    schema_: str = Field("dataviz/source/v1", alias="schema")
    kind: Literal["datasource", "source"] = "datasource"
    id: str
    name: str | None = None
    description: str = ""
    type: Literal["file", "sql", "python"]
    path: str | None = None
    format: str | None = None
    code: str | None = Field(None, validation_alias=AliasChoices("code", "query"))
    adapter: str | None = None
    connection: str | None = None
    entrypoint: str = "load"
    params: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    cache: CacheDefinition = Field(default_factory=CacheDefinition)


class WidgetOutputDefinition(Model):
    type: Literal[
        "auto", "plotly", "echarts", "matplotlib", "table", "perspective", "text", "image"
    ] = "auto"
    title: str | None = None


class WidgetDefinition(Model):
    schema_: str = Field("dataviz/widget/v1", alias="schema")
    kind: Literal["widget"] = "widget"
    id: str
    title: str
    description: str = ""
    runtime: Literal["browser"] = "browser"
    code: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    params: list[str] = Field(default_factory=list)
    output: WidgetOutputDefinition = Field(default_factory=WidgetOutputDefinition)


class AdapterDefinition(Model):
    type: str = "sqlalchemy"
    url: str | None = None
    env: str | None = None
    database: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    username_env: str | None = None
    password_env: str | None = None
    root: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class AdaptersFile(Model):
    adapters: dict[str, AdapterDefinition] = Field(default_factory=dict)


ConnectionDefinition = AdapterDefinition


class ConnectionsFile(Model):
    connections: dict[str, AdapterDefinition] = Field(default_factory=dict)
