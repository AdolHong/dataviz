from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from dataviz.errors import ExecutionFailure
from dataviz.execution import resolve_query_parameters
from dataviz.execution.interactive import resolve_compute_parameters
from dataviz.value_contract import normalize_control_value
from dataviz.workspace.models import (
    CacheDefinition,
    Choice,
    ComputeParameterDefinition,
    DashboardDefinition,
    DeclarativeViewDefinition,
    InteractiveExportDefinition,
    InteractiveTransformDefinition,
    QueryParameterDefinition,
    SelectionDefinition,
)
from dataviz.workspace.selections import resolve_selection_values


def test_control_defaults_are_validated_when_the_dsl_is_loaded():
    with pytest.raises(ValidationError, match="value must be an integer"):
        QueryParameterDefinition(id="count", type="integer", default=1.5)
    with pytest.raises(ValidationError, match="value must be at least 1"):
        ComputeParameterDefinition(
            id="count", type="integer", default=0, min=1, max=10
        )
    with pytest.raises(ValidationError, match="not one of the declared choices"):
        SelectionDefinition(
            id="region",
            type="single_select",
            default="missing",
            choices=[Choice(label="North", value="north")],
        )


def test_view_templates_reject_ignored_fields_and_require_real_renderer_paths():
    table = DeclarativeViewDefinition(
        id="detail",
        template="table",
        input="source:data/main",
        columns=["category", "value"],
    )
    assert table.columns == ["category", "value"]

    with pytest.raises(ValidationError, match="does not use fields: x"):
        DeclarativeViewDefinition(
            id="detail",
            template="table",
            input="source:data/main",
            x="category",
        )
    with pytest.raises(ValidationError, match="requires engine=echarts"):
        DeclarativeViewDefinition(
            id="radar",
            template="radar",
            input="source:data/main",
            label="entity",
            columns=["quality", "speed"],
        )
    with pytest.raises(ValidationError, match="requires one of: input, text"):
        DeclarativeViewDefinition(id="note", template="markdown")
    with pytest.raises(ValidationError, match="does not support aggregate=none"):
        DeclarativeViewDefinition(
            id="total",
            template="metric",
            input="source:data/main",
            value="amount",
            aggregate="none",
        )
    with pytest.raises(ValidationError, match="engine=echarts does not use config"):
        DeclarativeViewDefinition(
            id="chart",
            template="bar",
            engine="echarts",
            input="source:data/main",
            x="category",
            y="amount",
            config={"responsive": True},
        )

    radar = DeclarativeViewDefinition(
        id="radar",
        template="radar",
        engine="echarts",
        input="source:data/main",
        label="entity",
        columns=["quality", "speed"],
    )
    assert radar.engine == "echarts"


def test_date_range_empty_and_open_values_have_one_canonical_shape():
    definition = SelectionDefinition(id="period", type="date_range")

    assert normalize_control_value(definition, "") == []
    assert normalize_control_value(definition, ["", ""]) == []
    assert normalize_control_value(definition, ["2026-01-01", ""]) == [
        "2026-01-01",
        "",
    ]
    with pytest.raises(Exception, match="start cannot be after end"):
        normalize_control_value(definition, ["2026-02-01", "2026-01-01"])


def test_portable_numbers_and_dates_reject_browser_python_ambiguities():
    number = ComputeParameterDefinition(id="ratio", type="number")
    integer = ComputeParameterDefinition(id="identifier", type="integer")
    day = QueryParameterDefinition(id="day", type="date")

    for value in (" ", "0x10", "0b10", "1_000"):
        with pytest.raises(Exception, match="must be a number"):
            normalize_control_value(number, value)
    assert normalize_control_value(number, "12.0") == 12
    assert isinstance(normalize_control_value(number, "12.0"), int)
    assert normalize_control_value(number, "-1.25e2") == -125.0
    with pytest.raises(Exception, match="exact JavaScript range"):
        normalize_control_value(integer, 9_007_199_254_740_992)
    with pytest.raises(Exception, match="exact JavaScript range"):
        normalize_control_value(number, 9_007_199_254_740_992)
    with pytest.raises(ValidationError, match="exact JavaScript range"):
        SelectionDefinition(
            id="unsafe-choice",
            type="single_select",
            choices=[Choice(label="unsafe", value=9_007_199_254_740_992)],
        )
    with pytest.raises(Exception, match="YYYY-MM-DD"):
        normalize_control_value(day, "20260824")
    assert normalize_control_value(day, "2026-08-24") == "2026-08-24"


def test_query_compute_and_selection_resolvers_share_strict_contracts():
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v2",
            "id": "contract",
            "query_parameters": [{"id": "batch", "type": "integer", "default": 7}],
            "compute_parameters": [
                {"id": "factor", "type": "integer", "default": 2},
                {"id": "delay", "type": "number", "default": 0},
            ],
            "dashboard_selections": [
                {
                    "id": "region",
                    "type": "multi_select",
                    "field": "region",
                    "choices": [
                        {"label": "North", "value": "north"},
                        {"label": "South", "value": "south"},
                    ],
                }
            ],
            "views": [
                {
                    "id": "result",
                    "template": "metric",
                    "input": "source:result/main",
                }
            ],
        }
    )
    dashboard = SimpleNamespace(definition=definition)

    with pytest.raises(ExecutionFailure) as query_error:
        resolve_query_parameters(dashboard, {"batch": 1.5})
    assert query_error.value.details["code"] == "query_parameter_invalid_type"

    with pytest.raises(ExecutionFailure) as compute_error:
        resolve_compute_parameters(dashboard, {"factor": 2.5, "delay": 0})
    assert compute_error.value.details["code"] == "compute_parameter_invalid_type"

    with pytest.raises(ExecutionFailure) as alias_error:
        resolve_selection_values(definition, {"region": ["north"]})
    assert alias_error.value.details == {
        "code": "selection_unknown",
        "keys": ["region"],
    }

    resolved, _ = resolve_selection_values(
        definition,
        {"dashboard:contract/region": ["north"]},
    )
    assert resolved == {"dashboard:contract/region": ["north"]}


def test_typed_choice_values_round_trip_to_the_declared_json_value():
    definition = ComputeParameterDefinition(
        id="mode",
        type="single_select",
        choices=[
            Choice(label="One", value=1),
            Choice(label="Enabled", value=True),
        ],
    )

    assert normalize_control_value(definition, "1") == 1
    assert normalize_control_value(definition, "true") is True


def test_browser_cache_is_tab_local_while_server_cache_can_be_workspace_scoped():
    with pytest.raises(ValidationError, match="Browser Runtime cache supports only"):
        InteractiveTransformDefinition(
            schema="dataviz/interactive-transform/v1",
            id="browser",
            runtime="browser-js",
            code="transform.js",
            export=InteractiveExportDefinition(mode="interactive"),
            outputs={"main": {"kind": "table"}},
            cache=CacheDefinition(
                mode="ttl",
                scope="workspace",
                ttl_seconds=60,
            ),
        )

    server = InteractiveTransformDefinition(
        schema="dataviz/interactive-transform/v1",
        id="server",
        runtime="server-python",
        code="transform.py",
        export=InteractiveExportDefinition(mode="snapshot"),
        outputs={"main": {"kind": "table"}},
        cache=CacheDefinition(
            mode="ttl",
            scope="workspace",
            ttl_seconds=60,
        ),
    )
    assert server.cache.scope == "workspace"
