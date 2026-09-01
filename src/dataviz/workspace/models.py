from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from dataviz.identifiers import STABLE_ID_PATTERN, StableId
from dataviz.protocols import (
    DASHBOARD_SCHEMA,
    DATASET_TRANSFORM_SCHEMA,
    INTERACTIVE_TRANSFORM_SCHEMA,
    PARAMETER_DOMAIN_SCHEMA,
    PRESENTATION_SCHEMA,
    SOURCE_SCHEMA,
    WORKSPACE_SCHEMA,
)
from dataviz.relative_dates import is_relative_date_default
from dataviz.value_contract import validate_control_definition
from dataviz.view_contracts import validate_view_contract


class Model(BaseModel):
    # YAML/JSON accepts only public DSL names. Python attribute names such as
    # ``schema_`` exist solely to avoid keyword collisions and are not aliases.
    model_config = ConfigDict(extra="forbid", populate_by_name=False)


class ContextDefinition(Model):
    language: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    currency: str | None = None

    @model_validator(mode="after")
    def validate_timezone(self):
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown IANA timezone: {self.timezone}") from error
        return self


class QueryInputProjectionDefinition(Model):
    """Bind one node-local input name to a canonical Query Parameter value."""

    parameter: StableId
    projection: Literal["value", "selection", "active", "state"] = "value"
    part: Literal["start", "end"] | None = None

    @model_validator(mode="after")
    def validate_projection(self):
        if self.projection != "value" and self.part is not None:
            raise ValueError(
                f"query input projection={self.projection} cannot use part"
            )
        return self


QueryInputBindingDefinition = StableId | QueryInputProjectionDefinition


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


class WorkspaceAssetDefinition(Model):
    """One reusable local file owned by the Workspace.

    Registration does not expose the file to a browser. A Dashboard must list
    the Asset explicitly before the Canvas Runtime may read it.
    """

    path: str = Field(min_length=1)
    media_type: str | None = None

    @field_validator("path")
    @classmethod
    def require_relative_local_path(cls, value: str) -> str:
        candidate = Path(value)
        if candidate.is_absolute() or value.startswith(("asset:", "http:", "https:")):
            raise ValueError("Workspace Asset path must be relative to workspace.yaml")
        return value


class RuntimeDefinition(Model):
    # Plotly ships with the Python package and is always embedded into exported
    # reports. Accepting arbitrary strings here used to imply a configurability
    # that the renderer never implemented.
    plotly_js: Literal["bundled"] = "bundled"
    arrow_js: str = "https://cdn.jsdelivr.net/npm/apache-arrow@21.1.0/Arrow.es2015.min.js"
    perspective_version: str = "5.2.0"
    browser_table_transport: Literal["auto", "json", "arrow"] = "auto"
    arrow_min_rows: int = Field(2_000, ge=1)
    arrow_chunk_bytes: int = Field(524_288, ge=65_536, le=8_388_608)
    max_workers: int = Field(4, ge=1)
    max_concurrent_runs: int = Field(4, ge=1)
    max_concurrent_interactions: int = Field(4, ge=1)
    max_embedded_rows: int = Field(100_000, ge=1)
    max_embedded_bytes: int = Field(25_000_000, ge=1)
    max_retained_runs: int = Field(100, ge=1)
    max_retained_interactions_per_run: int = Field(200, ge=1)
    max_retained_run_events: int = Field(2_000, ge=10)
    max_retained_interaction_events: int = Field(2_000, ge=10)
    run_retention_seconds: int | None = Field(604_800, ge=1)
    max_retained_cache_entries: int = Field(500, ge=1)
    cache_retention_seconds: int | None = Field(2_592_000, ge=1)

class WorkspaceDefinition(Model):
    schema_: Literal[WORKSPACE_SCHEMA] = Field(alias="schema")
    kind: Literal["workspace"] = "workspace"
    id: StableId
    title: str
    description: str = ""
    context: ContextDefinition = Field(default_factory=ContextDefinition)
    folders: list[WorkspaceFolderDefinition] = Field(default_factory=list)
    assets: dict[StableId, WorkspaceAssetDefinition] = Field(default_factory=dict)
    runtime: RuntimeDefinition = Field(default_factory=RuntimeDefinition)


class Choice(Model):
    label: str
    value: Any
    group: str | None = None
    description: str = ""
    keywords: list[str] = Field(default_factory=list)


class StaticOptionDomainDefinition(Model):
    """A closed business enumeration owned by the Dashboard definition."""

    mode: Literal["static"]
    choices: list[Choice] = Field(min_length=1)


class InferredOptionDomainDefinition(Model):
    """An option domain inferred from immutable query-stage table outputs."""

    mode: Literal["infer"]
    source: str | None = Field(
        default=None,
        description=(
            "Optional Base Named Output used as the option domain. When omitted, "
            "Dataviz traces consuming Views through Interactive Transforms to their "
            "immutable Base Outputs."
        ),
    )


class ParameterDomainParentDefinition(Model):
    """Filter one Parameter Domain projection by a direct parent draft value."""

    field: str = Field(min_length=1)


class ParameterDomainOptionDefinition(Model):
    """Project one Query Parameter's choices from a shared pre-query table."""

    mode: Literal["domain"]
    source: StableId
    value_field: str = Field(min_length=1)
    label_field: str | None = Field(default=None, min_length=1)
    description_field: str | None = Field(default=None, min_length=1)
    group_field: str | None = Field(default=None, min_length=1)
    keywords_field: str | None = Field(default=None, min_length=1)
    sort_field: str | None = Field(default=None, min_length=1)
    disabled_field: str | None = Field(default=None, min_length=1)
    depends_on: dict[StableId, ParameterDomainParentDefinition] = Field(
        default_factory=dict
    )


OptionDomainDefinition = Annotated[
    StaticOptionDomainDefinition
    | InferredOptionDomainDefinition
    | ParameterDomainOptionDefinition,
    Field(discriminator="mode"),
]


class SelectInitialDefinition(Model):
    """Initial value policy for post-query Control selects."""

    mode: Literal["all", "empty", "values", "first", "value"]
    values: list[Any] | None = None
    value: Any = None

    @model_validator(mode="after")
    def validate_shape(self):
        if self.mode == "values":
            if not self.values:
                raise ValueError("initial mode=values requires a non-empty values list")
            if "value" in self.model_fields_set:
                raise ValueError("initial mode=values does not accept value")
        elif self.mode == "value":
            if "value" not in self.model_fields_set or self.value is None:
                raise ValueError("initial mode=value requires value")
            if self.values is not None:
                raise ValueError("initial mode=value does not accept values")
        elif self.values is not None or "value" in self.model_fields_set:
            raise ValueError(f"initial mode={self.mode} does not accept value or values")
        return self


class QuerySelectDefaultDefinition(Model):
    """Compact default policy for one Query Parameter select."""

    mode: Literal["first", "value", "none", "all", "include", "exclude"]
    value: Any = None
    values: list[Any] | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        if self.mode == "value":
            if "value" not in self.model_fields_set or self.value is None:
                raise ValueError("default mode=value requires value")
            if self.values is not None:
                raise ValueError("default mode=value does not accept values")
        elif self.mode in {"include", "exclude"}:
            if not self.values:
                raise ValueError(f"default mode={self.mode} requires non-empty values")
            if "value" in self.model_fields_set:
                raise ValueError(f"default mode={self.mode} does not accept value")
        elif self.values is not None or "value" in self.model_fields_set:
            raise ValueError(f"default mode={self.mode} does not accept value or values")
        return self


ControlDependencyReference = Annotated[
    str,
    StringConstraints(
        pattern=rf"^(?:dashboard|section|view)\.{STABLE_ID_PATTERN}$"
    ),
]


class ViewControlBindingDefinition(Model):
    """Bind one View interaction outlet to one canonical Control state."""

    control: ControlDependencyReference
    field: str | None = None


class _ValueControlDefinition(Model):
    _is_query_parameter: ClassVar[bool] = False
    id: StableId
    type: Literal[
        "single_input",
        "multiple_input",
        "single_select",
        "multiple_select",
        "range_input",
    ]
    value_type: Literal["text", "integer", "number", "boolean", "date"]
    label: str | None = None
    description: str = ""
    default: Any = None
    initial: SelectInitialDefinition | None = None
    required: bool = False
    clearable: bool | None = None
    options: OptionDomainDefinition | None = None
    suggestions: list[Choice] = Field(default_factory=list)
    min: float | int | None = None
    max: float | int | None = None
    step: float | int | None = None
    min_date: str | None = None
    max_date: str | None = None
    max_length: int | None = Field(None, ge=1)
    max_selected: int | None = Field(None, ge=1)
    max_items: int | None = Field(None, ge=1)
    allow_empty: tuple[bool, bool] = (False, False)
    placeholder: str = ""

    @model_validator(mode="after")
    def validate_value_contract(self):
        return validate_control_definition(self)


class QueryParameterDefinition(_ValueControlDefinition):
    """State that creates a new immutable Query Run when committed."""

    _is_query_parameter: ClassVar[bool] = True
    initial: None = Field(default=None, exclude=True)
    default: QuerySelectDefaultDefinition | Any = None
    max_explicit_values: int = Field(500, ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_option_domain(self):
        if self.type in {"single_select", "multiple_select"} and not isinstance(
            self.options,
            (StaticOptionDomainDefinition, ParameterDomainOptionDefinition),
        ):
            raise ValueError(
                "Query Parameter select controls require options.mode=static or options.mode=domain"
            )
        if self.initial is not None:
            raise ValueError("Query Parameters use default; initial is not supported")
        if self.type not in {"single_select", "multiple_select"} and isinstance(
            self.default, QuerySelectDefaultDefinition
        ):
            raise ValueError("structured default policies are only valid for select Query Parameters")
        return self


class ControlDefinition(_ValueControlDefinition):
    """Typed post-query state; consumer bindings own filter/value semantics."""

    field: str | None = None
    path_fields: list[str] = Field(default_factory=list, min_length=0)
    depends_on: list[ControlDependencyReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_option_domain_contract(self):
        if is_relative_date_default(self.default):
            raise ValueError("relative defaults are only valid for Query Parameters")
        if self.type in {"single_select", "multiple_select"} and self.options is None:
            raise ValueError(
                "Control select inputs require options.mode=static or options.mode=infer"
            )
        if self.depends_on and self.type not in {"single_select", "multiple_select"}:
            raise ValueError(
                "Control depends_on is only valid for single_select or multiple_select inputs"
            )
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("Control depends_on cannot contain duplicate references")
        return self


ScopedControlDefinition = ControlDefinition


class ControlValueInputDefinition(Model):
    """Pass one Control projection to a consumer-local alias."""

    mode: Literal["value"] = "value"
    control: str = Field(min_length=1)
    projection: Literal["value", "present", "intent"] = "value"


class ControlFilterInputDefinition(Model):
    """Apply one Control as an include filter to explicit table inputs."""

    mode: Literal["filter"]
    control: str = Field(min_length=1)
    field: str | list[str]
    inputs: list[StableId] = Field(min_length=1)
    empty: Literal["passthrough", "match_none"]
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

    @model_validator(mode="after")
    def validate_fields(self):
        values = self.field if isinstance(self.field, list) else [self.field]
        if not values or any(not str(value).strip() for value in values):
            raise ValueError("filter field must contain one or more non-empty names")
        if len(values) != len(set(values)):
            raise ValueError("filter field cannot contain duplicates")
        if len(self.inputs) != len(set(self.inputs)):
            raise ValueError("filter inputs cannot contain duplicates")
        return self


ControlInputObjectDefinition = Annotated[
    ControlValueInputDefinition | ControlFilterInputDefinition,
    Field(discriminator="mode"),
]
ControlInputBindingDefinition = str | ControlInputObjectDefinition


class RepeatDefinition(Model):
    """Create multiple instances from one declarative View blueprint."""

    view: StableId | None = None
    input: str | None = None
    by: list[str] = Field(min_length=1)
    control: str | None = None
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
    id: StableId
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
    columns: int | None = Field(None, ge=1, le=24)
    css_class: str = ""
    controls: list[ScopedControlDefinition] = Field(default_factory=list)
    views: list[StableId] = Field(default_factory=list)
    repeat: RepeatDefinition | None = None


class CanvasDefinition(Model):
    template: str | None = None
    use_default_style: bool = True
    client_libraries: list[Literal["plotly", "perspective"]] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)


class LayoutDefinition(Model):
    template: Literal["overview", "monitoring", "report", "exploration", "freeform"] = "overview"
    columns: int = Field(12, ge=1, le=24)
    gap: int = Field(18, ge=0)


class ThemeDefinition(Model):
    preset: Literal["plain", "editorial", "terminal", "business"] = "business"
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


class PresentationSectionDefinition(Model):
    css_class: str = ""
    controls: PresentationControlPanelDefinition | None = None


class PresentationViewDefinition(Model):
    min_height: int | None = Field(None, ge=1)
    container: Literal["panel", "metric", "chart", "table", "plain", "elevated"] | None = None
    css_class: str = ""
    options: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    controls: PresentationControlPanelDefinition | None = None


class DateRangePresetDefinition(Model):
    label: str
    start: str
    end: str


class SliderMarkDefinition(Model):
    value: float
    label: str


class PresentationControlComponentDefinition(Model):
    """Presentation-only choice of one independently packaged Data Entry component."""

    component: Literal[
        "auto",
        "input",
        "multiple-input",
        "input-number",
        "auto-complete",
        "checkbox",
        "switch",
        "radio-group",
        "select",
        "checkbox-group",
        "cascader",
        "date-picker",
        "range-picker",
        "slider",
        "tree-select",
    ] = "auto"
    span: Literal[1, 2] = 1
    multiline: bool = False
    min_rows: int = Field(2, ge=1, le=40)
    max_rows: int = Field(6, ge=1, le=80)
    show_count: bool = False
    prefix: str = ""
    suffix: str = ""
    number_controls: bool = True
    show_input: bool = False
    tooltip: Literal["auto", "always", "never"] = "auto"
    marks: list[SliderMarkDefinition] = Field(default_factory=list)
    checked_label: str = ""
    unchecked_label: str = ""
    option_type: Literal["default", "button"] = "default"
    button_style: Literal["outline", "solid"] = "outline"
    show_unavailable: bool = False
    search: Literal["auto", "always", "never"] = "auto"
    virtual: Literal["auto", "always", "never"] = "auto"
    search_threshold: int = Field(9, ge=0)
    virtual_threshold: int = Field(200, ge=1)
    max_tag_count: int = Field(2, ge=0, le=20)
    hide_selected: bool = False
    search_placeholder: str = "Search options…"
    empty_text: str = "No matching options"
    select_all_label: str = "Select all"
    invert_label: str = "Invert"
    clear_label: str = "Clear"
    level_labels: list[str] = Field(default_factory=list)
    path_separator: str = " / "
    selection_strategy: Literal["leaf", "cascade"] = "leaf"
    show_checked_strategy: Literal["all", "parent", "child"] = "child"
    start_label: str = "Start"
    end_label: str = "End"
    presets: list[DateRangePresetDefinition] = Field(default_factory=list)
    item_height: int = Field(38, ge=28, le=80)
    viewport_height: int = Field(304, ge=120, le=720)
    overscan: int = Field(5, ge=1, le=40)
    default_expand_depth: int = Field(0, ge=0, le=12)
    css_class: str = ""

    @model_validator(mode="after")
    def validate_component_options(self):
        common = {"component", "css_class", "span"}
        options = {
            "auto": set(),
            "input": {"multiline", "min_rows", "max_rows", "show_count", "prefix", "suffix"},
            "multiple-input": {"prefix", "suffix"},
            "input-number": {"prefix", "suffix", "number_controls"},
            "auto-complete": {"search_placeholder", "empty_text"},
            "checkbox": set(),
            "switch": {"checked_label", "unchecked_label"},
            "radio-group": {"option_type", "button_style", "show_unavailable"},
            "select": {
                "show_unavailable", "search", "virtual", "search_threshold",
                "virtual_threshold", "max_tag_count", "hide_selected",
                "search_placeholder", "empty_text", "select_all_label", "invert_label",
                "clear_label", "item_height", "viewport_height", "overscan",
            },
            "checkbox-group": {
                "show_unavailable",
            },
            "cascader": {
                "show_unavailable", "search", "search_placeholder", "empty_text",
                "clear_label", "level_labels", "path_separator", "selection_strategy",
                "show_checked_strategy", "max_tag_count",
            },
            "date-picker": {"clear_label"},
            "range-picker": {"start_label", "end_label", "presets", "clear_label"},
            "slider": {"show_input", "tooltip", "marks"},
            "tree-select": {
                "show_unavailable", "search", "search_placeholder", "empty_text",
                "clear_label", "level_labels", "path_separator", "selection_strategy",
                "show_checked_strategy", "max_tag_count", "default_expand_depth",
            },
        }
        explicit = set(self.model_fields_set) - common
        unsupported = explicit - options[self.component]
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValueError(
                f"{self.component} does not accept presentation options: {names}"
            )
        if self.min_rows > self.max_rows:
            raise ValueError("min_rows cannot be greater than max_rows")
        return self


class PresentationAssetsDefinition(Model):
    css: list[str] = Field(default_factory=list)
    js: list[str] = Field(default_factory=list)


class PresentationCanvasDefinition(Model):
    template: str | None = None
    use_default_style: bool | None = None
    client_libraries: list[Literal["plotly", "perspective"]] = Field(default_factory=list)


class PresentationControlPanelDefinition(Model):
    """Visual layout for one shared Dashboard control tray.

    The panel may change density and composition, but it never owns parameter,
    Selection, cascade, validation or execution state.
    """

    template: Literal["auto", "stack", "grid"] = "auto"
    width: Literal["auto", "compact", "regular", "wide"] = "auto"
    columns: int | None = Field(None, ge=1, le=6)
    column_width: int | None = Field(None, ge=160, le=600)
    density: Literal["compact", "comfortable"] = "comfortable"

    @model_validator(mode="after")
    def validate_stack_columns(self):
        if self.template == "stack" and self.columns not in {None, 1}:
            raise ValueError("stack control panels may only use columns: 1")
        return self


class PresentationControlPanelsDefinition(Model):
    query: PresentationControlPanelDefinition = Field(default_factory=PresentationControlPanelDefinition)
    dashboard: PresentationControlPanelDefinition = Field(default_factory=PresentationControlPanelDefinition)


class PresentationStateSummaryItemDefinition(Model):
    label: str | None = None
    hidden: bool = False
    order: int = 0
    formatter: Literal["auto", "value", "count", "date_range"] = "auto"


class PresentationStateSummaryDefinition(Model):
    enabled: bool = False
    max_values: int = Field(3, ge=1, le=20)
    items: dict[str, PresentationStateSummaryItemDefinition] = Field(default_factory=dict)


class PresentationDefinition(Model):
    schema_: Literal[PRESENTATION_SCHEMA] = Field(alias="schema")
    kind: Literal["presentation"] = "presentation"
    dashboard: StableId
    theme: PresentationThemeDefinition = Field(default_factory=PresentationThemeDefinition)
    sections: dict[StableId, PresentationSectionDefinition] = Field(default_factory=dict)
    views: dict[StableId, PresentationViewDefinition] = Field(default_factory=dict)
    control_components: dict[str, PresentationControlComponentDefinition] = Field(default_factory=dict)
    control_panels: PresentationControlPanelsDefinition = Field(default_factory=PresentationControlPanelsDefinition)
    state_summary: PresentationStateSummaryDefinition = Field(default_factory=PresentationStateSummaryDefinition)
    assets: PresentationAssetsDefinition = Field(default_factory=PresentationAssetsDefinition)
    canvas: PresentationCanvasDefinition = Field(default_factory=PresentationCanvasDefinition)


class DeclarativeViewDefinition(Model):
    id: StableId
    title: str | None = None
    description: str = ""
    span: int | None = Field(None, ge=1, le=24)
    template: Literal[
        "metric",
        "line",
        "bar",
        "stacked-bar",
        "pie",
        "scatter",
        "heatmap",
        "radar",
        "map",
        "table",
        "perspective",
        "markdown",
        "image",
        "custom",
    ]
    renderer: str | None = None
    input: str | None = None
    inputs: dict[StableId, str] = Field(default_factory=dict)
    x: str | None = None
    y: str | list[str] | None = None
    z: str | None = None
    value: str | None = None
    label: str | None = None
    series: str | None = None
    color: str | None = None
    size: str | None = None
    mark: Literal["point", "region"] | None = None
    longitude: str | None = None
    latitude: str | None = None
    geojson: StableId | None = None
    data_key: str | None = None
    feature_key: str | None = None
    columns: list[str] = Field(default_factory=list)
    aggregate: Literal["sum", "mean", "min", "max", "count", "none"] | None = None
    sort: str | None = None
    limit: int | None = Field(None, ge=1)
    text: str | None = None
    url: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    controls: list[ScopedControlDefinition] = Field(default_factory=list)
    control_inputs: dict[StableId, ControlInputBindingDefinition] = Field(
        default_factory=dict
    )
    control_binding: ControlDependencyReference | ViewControlBindingDefinition | None = None

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

    @model_validator(mode="after")
    def validate_template_contract(self):
        return validate_view_contract(self)


class DashboardDefinition(Model):
    schema_: Literal[DASHBOARD_SCHEMA] = Field(alias="schema")
    kind: Literal["dashboard"] = "dashboard"
    id: StableId
    title: str = ""
    subtitle: str = ""
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    adapters: dict[StableId, StableId] = Field(default_factory=dict)
    assets: list[StableId] = Field(default_factory=list)
    parameter_domains: list[str | dict[str, Any]] = Field(default_factory=list)
    query_parameters: list[QueryParameterDefinition] = Field(default_factory=list)
    controls: list[ScopedControlDefinition] = Field(default_factory=list)
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

    name: str = Field(min_length=1)
    dtype: str | None = None
    required: bool = True
    nullable: bool | None = None


class OutputSemanticsDefinition(Model):
    """Business meaning attached to one reusable Named Output.

    Runtime fields continue to describe how data is stored.  This contract
    describes why an AI or another author should reuse it.
    """

    class AssuranceDefinition(Model):
        status: Literal["draft", "reviewed", "certified", "deprecated"] = "draft"
        owner: str = ""
        reviewed_at: date | None = None
        evidence: list[str] = Field(default_factory=list)
        reason: str = ""
        replacement: str = ""

        @model_validator(mode="after")
        def validate_assurance(self):
            if self.status in {"reviewed", "certified"}:
                missing = [
                    name
                    for name, value in (
                        ("owner", self.owner),
                        ("reviewed_at", self.reviewed_at),
                        ("evidence", self.evidence),
                    )
                    if not value
                ]
                if missing:
                    raise ValueError(
                        f"assurance.status={self.status} requires " + ", ".join(missing)
                    )
            if self.status == "deprecated" and not (
                self.reason.strip() or self.replacement.strip()
            ):
                raise ValueError(
                    "assurance.status=deprecated requires reason or replacement"
                )
            return self

    class TimeDefinition(Model):
        field: str
        timezone: str = ""
        meaning: str = ""

        @model_validator(mode="after")
        def validate_timezone(self):
            if self.timezone:
                try:
                    ZoneInfo(self.timezone)
                except ZoneInfoNotFoundError as error:
                    raise ValueError(
                        f"unknown IANA timezone: {self.timezone}"
                    ) from error
            return self

    class MeasureDefinition(Model):
        unit: str = ""
        aggregation: Literal[
            "sum", "mean", "min", "max", "count", "distinct_count", "none"
        ] = "none"

    class RelationshipDefinition(Model):
        fields: list[str] = Field(min_length=1)
        cardinality: Literal[
            "one-to-one", "one-to-many", "many-to-one", "many-to-many"
        ]
        target: str = ""

    visibility: Literal["public", "internal"] = "internal"
    title: str = ""
    purpose: str = ""
    grain: str = ""
    caveats: list[str] = Field(default_factory=list)
    assurance: AssuranceDefinition = Field(default_factory=AssuranceDefinition)
    time: TimeDefinition | None = None
    measures: dict[str, MeasureDefinition] = Field(default_factory=dict)
    relationships: list[RelationshipDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_public_meaning(self):
        if self.visibility == "public":
            missing = [
                name
                for name in ("title", "purpose", "grain")
                if not str(getattr(self, name)).strip()
            ]
            if missing:
                raise ValueError(
                    "public Output semantics require non-empty " + ", ".join(missing)
                )
        return self


class OutputDefinition(Model):
    """Declared contract for one stable, named node output."""

    kind: Literal[
        "table", "scalar", "object", "text", "html", "chart", "image", "file"
    ] = "table"
    format: str | None = None
    mime_type: str | None = None
    description: str = ""
    semantics: OutputSemanticsDefinition | None = None
    schema_: list[ColumnDefinition] = Field(default_factory=list, alias="schema")
    required: bool = True

    @model_validator(mode="after")
    def validate_storage_contract(self):
        """Reject metadata that the Artifact Store would otherwise ignore."""
        if self.kind != "table" and self.schema_:
            raise ValueError("output.schema is only valid for kind=table")
        schema_names = [column.name for column in self.schema_]
        duplicate_names = sorted(
            {name for name in schema_names if schema_names.count(name) > 1}
        )
        if duplicate_names:
            raise ValueError(
                "output.schema contains duplicate columns: "
                + ", ".join(duplicate_names)
            )

        fixed_storage = {
            "table": ("parquet", "application/vnd.apache.parquet"),
            "scalar": ("json", "application/json"),
            "object": ("json", "application/json"),
            "chart": ("json", "application/json"),
            "html": ("html", "text/html"),
        }
        if self.kind in fixed_storage:
            expected_format, expected_mime = fixed_storage[self.kind]
            if self.format not in {None, expected_format}:
                raise ValueError(
                    f"kind={self.kind} is stored as format={expected_format}; "
                    f"format={self.format!r} is not supported"
                )
            if self.mime_type not in {None, expected_mime}:
                raise ValueError(
                    f"kind={self.kind} uses mime_type={expected_mime}; "
                    f"mime_type={self.mime_type!r} is not supported"
                )
        elif self.kind == "text":
            text_formats = {None, "text", "plain", "markdown"}
            if self.format not in text_formats:
                raise ValueError(
                    "kind=text supports format text, plain, or markdown"
                )
            expected_mime = (
                "text/markdown" if self.format == "markdown" else "text/plain"
            )
            if self.mime_type not in {None, expected_mime}:
                raise ValueError(
                    f"kind=text with format={self.format or 'text'} uses "
                    f"mime_type={expected_mime}"
                )
        return self


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


class ParameterDomainDefinition(Model):
    """A shared materialized SQL catalog used only for Query Parameter choices."""

    schema_: Literal[PARAMETER_DOMAIN_SCHEMA] = Field(alias="schema")
    kind: Literal["parameter_domain"] = "parameter_domain"
    id: StableId
    name: str | None = None
    description: str = ""
    type: Literal["sql"] = "sql"
    adapter: StableId
    code: str
    timeout_seconds: float = Field(30.0, gt=0)
    timeout_retries: int = Field(0, ge=0, le=5)
    max_rows: int = Field(500_000, ge=1, le=10_000_000)
    max_bytes: int = Field(536_870_912, ge=1)
    materialization: "ParameterDomainMaterializationDefinition" = Field(
        default_factory=lambda: ParameterDomainMaterializationDefinition()
    )

    @model_validator(mode="after")
    def validate_materialization_guard(self):
        if self.materialization.expire_after_seconds <= self.materialization.refresh_after_seconds:
            raise ValueError(
                "materialization.expire_after_seconds must be greater than refresh_after_seconds"
            )
        return self


class ParameterDomainMaterializationDefinition(Model):
    refresh_after_seconds: int = Field(43_200, ge=1)
    expire_after_seconds: int = Field(604_800, ge=2)


class _SourceDefinition(Model):
    """Fields shared by every strict Source variant."""

    schema_: Literal[SOURCE_SCHEMA] = Field(alias="schema")
    kind: Literal["source"] = "source"
    id: StableId
    name: str | None = None
    description: str = ""
    outputs: dict[StableId, OutputDefinition] = Field(min_length=1)
    cache: CacheDefinition = Field(default_factory=CacheDefinition)


class FileSourceDefinition(_SourceDefinition):
    type: Literal["file"]
    path: str
    format: Literal[
        "csv", "txt", "parquet", "pq", "json", "jsonl", "xlsx", "xls"
    ] | None = None
    adapter: StableId | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_known_file_format(self):
        if self.format is not None:
            return self
        if self.path.startswith("asset:"):
            raise ValueError("File Source using asset:<id> must declare format explicitly")
        suffix = self.path.rsplit(".", 1)[-1].lower() if "." in self.path else ""
        supported = {"csv", "txt", "parquet", "pq", "json", "jsonl", "xlsx", "xls"}
        if suffix not in supported:
            raise ValueError(
                "File Source path has no supported extension; declare format explicitly"
            )
        return self

    @model_validator(mode="after")
    def require_single_table_output(self):
        if self.path.startswith("asset:") and self.adapter is not None:
            raise ValueError("File Source asset:<id> cannot also declare an adapter")
        if set(self.outputs) != {"main"} or self.outputs["main"].kind != "table":
            raise ValueError("File Source outputs must be exactly main: {kind: table}")
        return self


class SqlSourceDefinition(_SourceDefinition):
    type: Literal["sql"]
    code: str
    adapter: StableId
    query_inputs: dict[StableId, QueryInputBindingDefinition] = Field(default_factory=dict)
    query_filters: dict[StableId, "SqlQueryFilterDefinition"] = Field(default_factory=dict)
    timeout_seconds: float = Field(120.0, gt=0)
    timeout_retries: int = Field(1, ge=0, le=5)

    @model_validator(mode="after")
    def require_single_table_output(self):
        if set(self.outputs) != {"main"} or self.outputs["main"].kind != "table":
            raise ValueError("SQL Source outputs must be exactly main: {kind: table}")
        return self


class SqlQueryFilterDefinition(Model):
    parameter: StableId
    field: str = Field(min_length=1)
    empty: Literal["passthrough", "match_none"]

    @model_validator(mode="after")
    def validate_field(self):
        import re

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", self.field):
            raise ValueError("query filter field must be a dot-qualified SQL identifier")
        return self


class PythonSourceDefinition(_SourceDefinition):
    type: Literal["python"]
    code: str
    adapter: StableId | None = None
    entrypoint: str = "load"
    query_inputs: dict[StableId, QueryInputBindingDefinition] = Field(default_factory=dict)
    code_dependencies: list[str] = Field(default_factory=list)
    python_dependencies: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(120.0, gt=0)


SourceDefinition = Annotated[
    FileSourceDefinition | SqlSourceDefinition | PythonSourceDefinition,
    Field(discriminator="type"),
]
SOURCE_DEFINITION_ADAPTER = TypeAdapter(SourceDefinition)


class DatasetTransformDefinition(Model):
    schema_: Literal[DATASET_TRANSFORM_SCHEMA] = Field(alias="schema")
    kind: Literal["dataset_transform"] = "dataset_transform"
    id: StableId
    name: str | None = None
    description: str = ""
    runtime: Literal["server-python"] = "server-python"
    code: str
    entrypoint: str = "transform"
    inputs: dict[StableId, str] = Field(default_factory=dict)
    input_schemas: dict[StableId, list[ColumnDefinition]] = Field(default_factory=dict)
    query_inputs: dict[StableId, QueryInputBindingDefinition] = Field(default_factory=dict)
    outputs: dict[StableId, OutputDefinition] = Field(min_length=1)
    code_dependencies: list[str] = Field(default_factory=list)
    python_dependencies: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(120.0, gt=0)
    cache: CacheDefinition = Field(default_factory=CacheDefinition)

    @model_validator(mode="after")
    def validate_input_schema_columns(self):
        _require_unique_input_schema_columns(self.input_schemas)
        return self


class InteractiveExportDefinition(Model):
    mode: Literal["interactive", "snapshot", "unavailable"]
    reason: str = ""

    @model_validator(mode="after")
    def require_unavailable_reason(self):
        if self.mode == "unavailable" and not self.reason.strip():
            raise ValueError("export.reason is required when export.mode is unavailable")
        return self


class InteractiveTransformDefinition(Model):
    schema_: Literal[INTERACTIVE_TRANSFORM_SCHEMA] = Field(alias="schema")
    kind: Literal["interactive_transform"] = "interactive_transform"
    id: StableId
    name: str | None = None
    description: str = ""
    runtime: Literal["server-python", "browser-js"]
    code: str
    entrypoint: str = "transform"
    inputs: dict[StableId, str] = Field(default_factory=dict)
    input_schemas: dict[StableId, list[ColumnDefinition]] = Field(default_factory=dict)
    query_inputs: dict[StableId, QueryInputBindingDefinition] = Field(default_factory=dict)
    control_inputs: dict[StableId, ControlInputBindingDefinition] = Field(
        default_factory=dict
    )
    trigger: Literal["apply", "auto", "manual"] = "auto"
    debounce_ms: int = Field(300, ge=0, le=10_000)
    export: InteractiveExportDefinition
    outputs: dict[StableId, OutputDefinition] = Field(min_length=1)
    code_dependencies: list[str] = Field(default_factory=list)
    python_dependencies: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(30.0, gt=0)
    cache: CacheDefinition = Field(default_factory=CacheDefinition)

    @model_validator(mode="before")
    @classmethod
    def default_trigger_for_runtime(cls, value):
        if isinstance(value, dict) and "trigger" not in value:
            value = dict(value)
            value["trigger"] = (
                "apply" if value.get("runtime") == "server-python" else "auto"
            )
        return value

    @model_validator(mode="after")
    def validate_runtime_contract(self):
        _require_unique_input_schema_columns(self.input_schemas)
        if self.runtime == "server-python" and self.export.mode == "interactive":
            raise ValueError(
                "server-python cannot use export.mode=interactive; choose snapshot or unavailable"
            )
        if self.runtime == "browser-js" and self.python_dependencies:
            raise ValueError("browser-js cannot declare python_dependencies")
        if self.runtime == "browser-js" and (
            self.cache.mode not in {"none", "session"} or self.cache.scope != "tab"
        ):
            raise ValueError(
                "Browser Runtime cache supports only mode none/session with scope tab"
            )
        return self


def _require_unique_input_schema_columns(
    schemas: dict[StableId, list[ColumnDefinition]],
) -> None:
    for input_name, schema in schemas.items():
        names = [column.name for column in schema]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(
                f"input_schemas.{input_name} contains duplicate columns: "
                + ", ".join(duplicates)
            )


class AdapterDefinition(Model):
    type: str = "sqlalchemy"
    description: str = ""
    visibility_scope: str = "default"
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
    adapters: dict[StableId, AdapterDefinition] = Field(default_factory=dict)
