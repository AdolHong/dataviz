from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dataviz.value_contract import validate_control_definition


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ContextDefinition(Model):
    language: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    currency: str | None = None


class NavigationItem(Model):
    kind: Literal["dashboard", "folder"] = "dashboard"
    id: str
    title: str
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
    arrow_js: str = "https://cdn.jsdelivr.net/npm/apache-arrow@21.1.0/Arrow.es2015.min.js"
    perspective_version: str = "5.2.0"
    pyodide_version: str = "314.0.4"
    pyodide_asset_policy: Literal["cdn", "bundle"] = "cdn"
    pyodide_index_url: str = "https://cdn.jsdelivr.net/pyodide/v314.0.4/full/"
    pyodide_bundle_path: str | None = None
    browser_table_transport: Literal["auto", "json", "arrow"] = "auto"
    arrow_min_rows: int = Field(2_000, ge=1)
    arrow_chunk_bytes: int = Field(524_288, ge=65_536, le=8_388_608)
    max_workers: int = Field(4, ge=1)
    max_concurrent_runs: int = Field(4, ge=1)
    max_embedded_rows: int = Field(100_000, ge=1)
    max_embedded_bytes: int = Field(25_000_000, ge=1)
    max_retained_runs: int = Field(100, ge=1)
    max_retained_interactions_per_run: int = Field(200, ge=1)
    max_retained_run_events: int = Field(2_000, ge=10)
    max_retained_interaction_events: int = Field(2_000, ge=10)
    run_retention_seconds: int | None = Field(604_800, ge=1)
    max_retained_cache_entries: int = Field(500, ge=1)
    cache_retention_seconds: int | None = Field(2_592_000, ge=1)

    @model_validator(mode="after")
    def validate_pyodide_assets(self):
        if self.pyodide_asset_policy == "bundle" and not self.pyodide_bundle_path:
            raise ValueError(
                "runtime.pyodide_bundle_path is required when pyodide_asset_policy=bundle"
            )
        return self


class WorkspaceDefinition(Model):
    schema_: Literal["dataviz/workspace/v1"] = Field(alias="schema")
    kind: Literal["workspace"] = "workspace"
    id: str
    title: str
    description: str = ""
    context: ContextDefinition = Field(default_factory=ContextDefinition)
    folders: list[WorkspaceFolderDefinition] = Field(default_factory=list)
    runtime: RuntimeDefinition = Field(default_factory=RuntimeDefinition)


class Choice(Model):
    label: str
    value: Any
    group: str | None = None
    description: str = ""
    keywords: list[str] = Field(default_factory=list)


class _ValueControlDefinition(Model):
    id: str
    type: Literal[
        "string",
        "number",
        "integer",
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
    min: float | int | None = None
    max: float | int | None = None
    step: float | int | None = None
    placeholder: str = ""

    @model_validator(mode="after")
    def validate_value_contract(self):
        return validate_control_definition(self)


class QueryParameterDefinition(_ValueControlDefinition):
    """State that creates a new immutable Query Run when committed."""

    @model_validator(mode="after")
    def validate_static_choices(self):
        if self.type in {"single_select", "multi_select"} and not self.choices:
            raise ValueError(
                "Query Parameter select controls require explicit choices"
            )
        return self


class ComputeParameterDefinition(_ValueControlDefinition):
    """State used only by Interactive Transforms after a Query Run exists."""

    @model_validator(mode="after")
    def validate_static_choices(self):
        if self.type in {"single_select", "multi_select"} and not self.choices:
            raise ValueError(
                "Compute Parameter select controls require explicit choices"
            )
        return self


class SelectionDefinition(_ValueControlDefinition):
    """A browser-side selection applied after sources have been loaded."""

    field: str | None = None
    path_fields: list[str] = Field(default_factory=list, min_length=0)
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


class RepeatDefinition(Model):
    """Create multiple instances from one declarative View blueprint."""

    view: str | None = None
    input: str | None = None
    by: list[str] = Field(min_length=1)
    selection: str | None = None
    title: str = "{value}"
    limit: int | None = Field(None, ge=1)
    order_by: str | None = None
    order: Literal["asc", "desc"] = "asc"
    render: Literal["lazy", "eager"] = "lazy"
    searchable: bool = True
    search_placeholder: str = "Search groups…"
    page_size: int = Field(40, ge=1, le=500)
    recycle_offscreen: bool = True
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
    ] = "stack"
    columns: int | None = None
    css_class: str = ""
    selections: list[SelectionDefinition] = Field(default_factory=list)
    views: list[str] = Field(default_factory=list)
    repeat: RepeatDefinition | None = None


class CanvasDefinition(Model):
    template: str | None = None
    style: str | None = None
    script: str | None = None
    use_default_style: bool = True
    client_libraries: list[Literal["plotly", "echarts", "perspective"]] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)


class LayoutDefinition(Model):
    template: Literal["overview", "monitoring", "report", "exploration", "freeform"] = "overview"
    columns: int = 12
    gap: int = 18


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
    css_class: str = ""


class PresentationViewDefinition(Model):
    span: int | None = Field(None, ge=1, le=24)
    min_height: int | None = Field(None, ge=1)
    container: Literal["panel", "metric", "chart", "table", "plain", "elevated"] | None = None
    css_class: str = ""
    engine: Literal["plotly", "echarts"] | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class DateRangePresetDefinition(Model):
    label: str
    start: str
    end: str


class PresentationSelectorDefinition(Model):
    template: Literal[
        "auto",
        "select",
        "segmented",
        "checkbox-group",
        "cascader",
        "date-range",
        "tree-select",
    ] = "auto"
    variant: Literal["default", "tags", "radio"] = "default"
    show_unavailable: bool = False
    search: Literal["auto", "always", "never"] = "auto"
    virtual: Literal["auto", "always", "never"] = "auto"
    search_threshold: int = Field(9, ge=0)
    virtual_threshold: int = Field(200, ge=1)
    max_visible_tags: int = Field(2, ge=0, le=20)
    max_selected: int | None = Field(None, ge=1)
    hide_selected: bool = False
    search_placeholder: str = "Search options…"
    empty_text: str = "No matching options"
    placeholder: str = "Choose…"
    all_label: str = "All"
    select_all_label: str = "Select all"
    invert_label: str = "Invert"
    clear_label: str = "Clear"
    level_labels: list[str] = Field(default_factory=list)
    path_separator: str = " / "
    hierarchy_selection: Literal["leaf", "cascade"] = "leaf"
    checked_strategy: Literal["all", "parent", "child"] = "child"
    start_label: str = "Start"
    end_label: str = "End"
    min: str | None = None
    max: str | None = None
    allow_open_range: bool = False
    presets: list[DateRangePresetDefinition] = Field(default_factory=list)
    item_height: int = Field(38, ge=28, le=80)
    viewport_height: int = Field(304, ge=120, le=720)
    overscan: int = Field(5, ge=1, le=40)
    default_expand_depth: int = Field(0, ge=0, le=12)
    css_class: str = ""


class PresentationAssetsDefinition(Model):
    css: list[str] = Field(default_factory=list)
    js: list[str] = Field(default_factory=list)


class PresentationCanvasDefinition(Model):
    template: str | None = None
    use_default_style: bool | None = None
    client_libraries: list[Literal["plotly", "echarts", "perspective"]] = Field(default_factory=list)


class PresentationDefinition(Model):
    schema_: Literal["dataviz/presentation/v1"] = Field(alias="schema")
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
        "radar",
        "table",
        "perspective",
        "markdown",
        "image",
        "custom",
    ]
    renderer: str | None = None
    engine: Literal["plotly", "echarts"] = "plotly"
    input: str | None = None
    inputs: dict[str, str] = Field(default_factory=dict)
    x: str | None = None
    y: str | list[str] | None = None
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
    selections: list[SelectionDefinition] = Field(default_factory=list)
    selection_bindings: dict[str, str | SelectionBindingDefinition] = Field(default_factory=dict)

    @property
    def input_ref(self) -> str | None:
        """Return the primary named output consumed by this View."""
        return self.input or self.inputs.get("main")

    @property
    def input_refs(self) -> dict[str, str]:
        refs = dict(self.inputs)
        if self.input:
            refs.setdefault("main", self.input)
        return refs


class DashboardDefinition(Model):
    schema_: Literal["dataviz/dashboard/v2"] = Field(alias="schema")
    kind: Literal["dashboard"] = "dashboard"
    id: str
    title: str = ""
    subtitle: str = ""
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    adapters: dict[str, str] = Field(default_factory=dict)
    query_parameters: list[QueryParameterDefinition] = Field(default_factory=list)
    compute_parameters: list[ComputeParameterDefinition] = Field(default_factory=list)
    dashboard_selections: list[SelectionDefinition] = Field(default_factory=list)
    sections: list[SectionDefinition] = Field(default_factory=list)
    sources: list[str | dict[str, Any]] = Field(default_factory=list)
    dataset_transforms: list[str | dict[str, Any]] = Field(default_factory=list)
    interactive_transforms: list[str | dict[str, Any]] = Field(default_factory=list)
    views: list[DeclarativeViewDefinition] = Field(default_factory=list)
    layout: LayoutDefinition = Field(default_factory=LayoutDefinition)
    theme: ThemeDefinition = Field(default_factory=ThemeDefinition)
    canvas: CanvasDefinition = Field(default_factory=CanvasDefinition)

class ColumnDefinition(Model):
    """A lightweight table schema contract used at node boundaries."""

    name: str
    dtype: str | None = None
    required: bool = True
    nullable: bool | None = None


class OutputDefinition(Model):
    """Declared contract for one stable, named node output."""

    kind: Literal[
        "table", "scalar", "object", "text", "html", "chart", "image", "file"
    ] = "table"
    format: str | None = None
    mime_type: str | None = None
    description: str = ""
    schema_: list[ColumnDefinition] = Field(default_factory=list, alias="schema")
    required: bool = True


class CacheDefinition(Model):
    mode: Literal["none", "session", "ttl", "persistent"] = "session"
    scope: Literal["tab", "workspace"] = "tab"
    ttl_seconds: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def validate_ttl(self):
        if self.mode == "ttl" and self.ttl_seconds is None:
            raise ValueError("cache.ttl_seconds is required when cache.mode=ttl")
        if self.mode != "ttl" and self.ttl_seconds is not None:
            raise ValueError("cache.ttl_seconds is only valid when cache.mode=ttl")
        if self.mode in {"none", "session"} and self.scope != "tab":
            raise ValueError(f"cache.scope=workspace is not meaningful for mode={self.mode}")
        return self


class SourceDefinition(Model):
    schema_: Literal["dataviz/source/v1"] = Field(alias="schema")
    kind: Literal["source"] = "source"
    id: str
    name: str | None = None
    description: str = ""
    type: Literal["file", "sql", "python"]
    path: str | None = None
    format: str | None = None
    code: str | None = None
    adapter: str | None = None
    entrypoint: str = "load"
    query_params: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, OutputDefinition] = Field(min_length=1)
    code_dependencies: list[str] = Field(default_factory=list)
    python_dependencies: list[str] = Field(default_factory=list)
    timeout_seconds: float | None = Field(None, gt=0)
    timeout_retries: int | None = Field(None, ge=0, le=5)
    cache: CacheDefinition = Field(default_factory=CacheDefinition)

    @model_validator(mode="after")
    def apply_execution_defaults(self):
        # File reads are local and synchronous. SQL and Python Sources must not
        # run forever merely because the author omitted an operational setting.
        if self.type in {"sql", "python"} and self.timeout_seconds is None:
            self.timeout_seconds = 120.0
        if self.type == "sql" and self.timeout_retries is None:
            self.timeout_retries = 1
        return self


class DatasetTransformDefinition(Model):
    schema_: Literal["dataviz/dataset-transform/v1"] = Field(alias="schema")
    kind: Literal["dataset_transform"] = "dataset_transform"
    id: str
    name: str | None = None
    description: str = ""
    runtime: Literal["server-python"] = "server-python"
    code: str
    entrypoint: str = "transform"
    inputs: dict[str, str] = Field(default_factory=dict)
    input_schemas: dict[str, list[ColumnDefinition]] = Field(default_factory=dict)
    query_params: list[str] = Field(default_factory=list)
    outputs: dict[str, OutputDefinition] = Field(min_length=1)
    code_dependencies: list[str] = Field(default_factory=list)
    python_dependencies: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(120.0, gt=0)
    cache: CacheDefinition = Field(default_factory=CacheDefinition)


class InteractiveExportDefinition(Model):
    mode: Literal["interactive", "snapshot", "unavailable"]
    assets: Literal["cdn", "bundle"] | None = None
    reason: str = ""

    @model_validator(mode="after")
    def require_unavailable_reason(self):
        if self.mode == "unavailable" and not self.reason.strip():
            raise ValueError("export.reason is required when export.mode is unavailable")
        return self


class InteractiveTransformDefinition(Model):
    schema_: Literal["dataviz/interactive-transform/v1"] = Field(alias="schema")
    kind: Literal["interactive_transform"] = "interactive_transform"
    id: str
    name: str | None = None
    description: str = ""
    runtime: Literal["server-python", "browser-python", "browser-js"]
    code: str
    entrypoint: str = "transform"
    inputs: dict[str, str] = Field(default_factory=dict)
    input_schemas: dict[str, list[ColumnDefinition]] = Field(default_factory=dict)
    query_params: list[str] = Field(default_factory=list)
    compute_params: list[str] = Field(default_factory=list)
    selections: list[str] = Field(default_factory=list)
    trigger: Literal["apply", "auto", "manual"] = "apply"
    debounce_ms: int = Field(300, ge=0, le=10_000)
    export: InteractiveExportDefinition
    outputs: dict[str, OutputDefinition] = Field(min_length=1)
    code_dependencies: list[str] = Field(default_factory=list)
    python_dependencies: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(30.0, gt=0)
    cache: CacheDefinition = Field(default_factory=CacheDefinition)

    @model_validator(mode="after")
    def validate_runtime_contract(self):
        if self.runtime == "server-python" and self.export.mode == "interactive":
            raise ValueError(
                "server-python cannot use export.mode=interactive; choose snapshot or unavailable"
            )
        if self.runtime == "browser-js" and self.python_dependencies:
            raise ValueError("browser-js cannot declare python_dependencies")
        if self.runtime == "browser-js" and self.export.assets is not None:
            raise ValueError("browser-js does not use export.assets")
        if (
            self.runtime == "browser-python"
            and self.export.mode == "interactive"
            and self.export.assets is None
        ):
            raise ValueError(
                "browser-python with export.mode=interactive must declare "
                "export.assets as cdn or bundle"
            )
        if self.runtime != "browser-python" and self.export.assets is not None:
            raise ValueError("export.assets is only valid for browser-python")
        if self.export.mode != "interactive" and self.export.assets is not None:
            raise ValueError("export.assets is only valid when export.mode is interactive")
        if self.runtime in {"browser-js", "browser-python"} and (
            self.cache.mode not in {"none", "session"} or self.cache.scope != "tab"
        ):
            raise ValueError(
                "Browser Runtime cache supports only mode none/session with scope tab"
            )
        return self


class AdapterDefinition(Model):
    type: str = "sqlalchemy"
    description: str = ""
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
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


class AdaptersFile(Model):
    adapters: dict[str, AdapterDefinition] = Field(default_factory=dict)
