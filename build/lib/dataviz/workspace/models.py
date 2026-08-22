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
    id: str
    title: str
    dashboard: str
    route: str | None = None
    order: int = 0


class RuntimeDefinition(Model):
    plotly_js: str = "bundled"
    echarts_js: str = "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"
    max_workers: int = 4


class WorkspaceDefinition(Model):
    schema_: str = Field("dataviz/workspace/v1", alias="schema")
    kind: Literal["workspace"] = "workspace"
    id: str
    title: str
    description: str = ""
    context: ContextDefinition = Field(default_factory=ContextDefinition)
    navigation: list[NavigationItem] = Field(default_factory=list)
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


class FilterDefinition(ParameterDefinition):
    """A value applied after sources have been loaded."""


class FilterBindingDefinition(Model):
    field: str | None = None
    operator: Literal["auto", "equals", "in", "between", "contains"] = "auto"


class ViewDefinition(Model):
    widget: str
    filters: list[FilterDefinition] = Field(default_factory=list)
    filter_bindings: dict[str, str | FilterBindingDefinition] = Field(default_factory=dict)


class SectionDefinition(Model):
    id: str
    title: str
    description: str = ""
    filters: list[FilterDefinition] = Field(default_factory=list)
    views: list[str | ViewDefinition] = Field(default_factory=list)


class CanvasDefinition(Model):
    template: str | None = None
    style: str | None = None
    script: str | None = None
    use_default_style: bool = True


class LayoutItem(Model):
    widget: str
    x: int = 0
    y: int = 0
    width: int = 6
    height: int = 3
    css_class: str = ""


class LayoutDefinition(Model):
    columns: int = 12
    row_height: int = 92
    gap: int = 18
    items: list[LayoutItem] = Field(default_factory=list)


class DashboardDefinition(Model):
    schema_: str = Field("dataviz/dashboard/v1", alias="schema")
    kind: Literal["dashboard"] = "dashboard"
    id: str
    title: str
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    query_parameters: list[ParameterDefinition] = Field(
        default_factory=list,
        validation_alias=AliasChoices("query_parameters", "parameters"),
    )
    dashboard_filters: list[FilterDefinition] = Field(default_factory=list)
    sections: list[SectionDefinition] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    widgets: list[str] = Field(default_factory=list)
    layout: LayoutDefinition = Field(default_factory=LayoutDefinition)
    canvas: CanvasDefinition = Field(default_factory=CanvasDefinition)


class CacheDefinition(Model):
    mode: Literal["none", "session", "ttl", "persistent"] = "session"
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
    code: str | None = None
    connection: str | None = None
    entrypoint: str = "load"
    params: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    cache: CacheDefinition = Field(default_factory=CacheDefinition)


class WidgetOutputDefinition(Model):
    type: Literal["auto", "plotly", "echarts", "matplotlib", "table", "text", "image"] = "auto"
    title: str | None = None


class WidgetDefinition(Model):
    schema_: str = Field("dataviz/widget/v1", alias="schema")
    kind: Literal["widget"] = "widget"
    id: str
    title: str
    description: str = ""
    code: str
    entrypoint: str = "render"
    depends_on: list[str] = Field(default_factory=list)
    params: list[str] = Field(default_factory=list)
    output: WidgetOutputDefinition = Field(default_factory=WidgetOutputDefinition)


class ConnectionDefinition(Model):
    type: str = "sqlalchemy"
    url: str | None = None
    env: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ConnectionsFile(Model):
    connections: dict[str, ConnectionDefinition] = Field(default_factory=dict)
