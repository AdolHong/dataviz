from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from dataviz.errors import ExecutionFailure
from dataviz.execution import resolve_query_parameters
from dataviz.execution.parameters import project_query_inputs
from dataviz.value_contract import normalize_control_value
from dataviz.workspace.controls import (
    initial_selection_states,
    resolve_compute_values,
    resolve_selection_states,
)
from dataviz.workspace.models import (
    CacheDefinition,
    Choice,
    ComputeControlDefinition,
    DashboardDefinition,
    DeclarativeViewDefinition,
    InteractiveExportDefinition,
    InteractiveTransformDefinition,
    QueryParameterDefinition,
    SelectionControlDefinition,
    SqlSourceDefinition,
)


def static_options(choices):
    return {"mode": "static", "choices": choices}


def test_relative_date_defaults_resolve_once_in_workspace_timezone_and_project_parts():
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v7",
            "id": "relative-dates",
            "query_parameters": [
                {
                    "id": "job_date_range",
                    "type": "date_range",
                    "required": True,
                    "default": {
                        "mode": "relative",
                        "anchor": "today",
                        "start_offset": "-3d",
                        "end_offset": "-1d",
                    },
                }
            ],
        }
    )
    dashboard = SimpleNamespace(definition=definition)
    # 16:30 UTC is already the next calendar day in Asia/Shanghai.
    values = resolve_query_parameters(
        dashboard,
        None,
        timezone_name="Asia/Shanghai",
        current_time=datetime(2026, 8, 24, 16, 30, tzinfo=timezone.utc),
    )
    source = SqlSourceDefinition.model_validate(
        {
            "schema": "dataviz/source/v2",
            "id": "sales",
            "type": "sql",
            "adapter": "warehouse",
            "code": "sales.sql",
            "query_inputs": {
                "start_date": {
                    "parameter": "job_date_range",
                    "part": "start",
                },
                "end_date": {
                    "parameter": "job_date_range",
                    "part": "end",
                },
            },
            "outputs": {"main": {"kind": "table"}},
        }
    )

    assert values == {"job_date_range": ["2026-08-22", "2026-08-24"]}
    assert project_query_inputs(source.query_inputs, values) == {
        "start_date": "2026-08-22",
        "end_date": "2026-08-24",
    }


def test_relative_date_default_contract_rejects_ambiguous_or_reversed_expressions():
    with pytest.raises(ValidationError, match="integer day offset"):
        QueryParameterDefinition.model_validate(
            {
                "id": "date",
                "type": "date",
                "default": {"mode": "relative", "anchor": "today", "offset": "-1week"},
            }
        )
    with pytest.raises(ValidationError, match="start_offset cannot be after"):
        QueryParameterDefinition.model_validate(
            {
                "id": "dates",
                "type": "date_range",
                "default": {
                    "mode": "relative",
                    "anchor": "today",
                    "start_offset": "+1d",
                    "end_offset": "-1d",
                },
            }
        )
    with pytest.raises(ValidationError, match="only valid for Query Parameters"):
        ComputeControlDefinition.model_validate(
            {
                "id": "date",
                "kind": "compute",
                "type": "date",
                "default": {"mode": "relative", "anchor": "today", "offset": "-1d"},
            }
        )


def test_control_defaults_are_validated_when_the_dsl_is_loaded():
    with pytest.raises(ValidationError, match="value must be an integer"):
        QueryParameterDefinition(id="count", type="integer", default=1.5)
    with pytest.raises(ValidationError, match="value must be at least 1"):
        ComputeControlDefinition(
            id="count", kind="compute", type="integer", default=0, min=1, max=10
        )
    with pytest.raises(ValidationError, match="not one of the declared choices"):
        SelectionControlDefinition(
            id="region",
            kind="selection",
            type="single_select",
            default="missing",
            options=static_options([Choice(label="North", value="north")]),
        )
    with pytest.raises(ValidationError, match="required controls cannot be clearable"):
        SelectionControlDefinition(
            id="region",
            kind="selection",
            type="multi_select",
            required=True,
            clearable=True,
            options=static_options([Choice(label="North", value="north")]),
        )
    optional_single = SelectionControlDefinition(
        id="region",
        kind="selection",
        type="single_select",
        clearable=True,
        options=static_options([Choice(label="North", value="north")]),
    )
    assert optional_single.clearable is True


def test_select_option_domains_separate_static_values_from_inferred_intent():
    with pytest.raises(ValidationError, match="cannot declare default"):
        SelectionControlDefinition.model_validate(
            {
                "id": "city",
                "kind": "selection",
                "type": "multi_select",
                "field": "city",
                "default": ["Shenzhen"],
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError, match="options.mode=static"):
        QueryParameterDefinition.model_validate(
            {
                "id": "city",
                "type": "single_select",
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError):
        SelectionControlDefinition.model_validate(
            {
                "id": "city",
                "kind": "selection",
                "type": "multi_select",
                "choices": [{"label": "Shenzhen", "value": "Shenzhen"}],
            }
        )

    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v7",
            "id": "option-intents",
            "controls": [
                {
                    "id": "city",
                    "kind": "selection",
                    "type": "multi_select",
                    "field": "city",
                    "options": {"mode": "infer"},
                },
                {
                    "id": "store",
                    "kind": "selection",
                    "type": "multi_select",
                    "field": "store",
                    "options": {"mode": "infer", "initial": "empty"},
                },
                {
                    "id": "region",
                    "kind": "selection",
                    "type": "multi_select",
                    "field": "region",
                    "default": ["north"],
                    "options": {
                        "mode": "static",
                        "choices": [{"label": "North", "value": "north"}],
                    },
                },
            ],
        }
    )

    assert initial_selection_states(definition) == {
        "dashboard:option-intents/city": {
            "intent": "all_available",
            "values": [],
        },
        "dashboard:option-intents/store": {
            "intent": "explicit",
            "values": [],
        },
        "dashboard:option-intents/region": {
            "intent": "explicit",
            "values": ["north"],
        },
    }

    required_inferred = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v7",
            "id": "required-inferred",
            "controls": [
                {
                    "id": "city",
                    "kind": "selection",
                    "type": "single_select",
                    "field": "city",
                    "required": True,
                    "options": {"mode": "infer"},
                }
            ],
        }
    )
    with pytest.raises(ExecutionFailure, match="a value is required"):
        resolve_selection_states(required_inferred, {})
    assert resolve_selection_states(
        required_inferred,
        {},
        phase="canvas-hydration",
    ) == {
        "dashboard:required-inferred/city": {
            "intent": "explicit",
            "values": [],
        }
    }


def test_selection_dependency_authoring_contract_is_explicit_and_strict():
    definition = SelectionControlDefinition.model_validate(
        {
            "id": "dates",
            "kind": "selection",
            "type": "multi_select",
            "field": "job_date",
            "depends_on": ["dashboard.province", "section.city", "view.dow"],
            "options": {"mode": "infer"},
        }
    )
    assert definition.depends_on == [
        "dashboard.province",
        "section.city",
        "view.dow",
    ]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SelectionControlDefinition.model_validate(
            {
                "id": "dates",
                "kind": "selection",
                "type": "multi_select",
                "cascade": True,
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError, match="String should match pattern"):
        SelectionControlDefinition.model_validate(
            {
                "id": "dates",
                "kind": "selection",
                "type": "multi_select",
                "depends_on": ["dow"],
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError, match="duplicate references"):
        SelectionControlDefinition.model_validate(
            {
                "id": "dates",
                "kind": "selection",
                "type": "multi_select",
                "depends_on": ["view.dow", "view.dow"],
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError, match="only valid for single_select or multi_select"):
        SelectionControlDefinition.model_validate(
            {
                "id": "threshold",
                "kind": "selection",
                "type": "number",
                "depends_on": ["view.dow"],
            }
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
    definition = SelectionControlDefinition(
        id="period",
        kind="selection",
        type="date_range",
        allow_empty=(False, True),
    )

    assert normalize_control_value(definition, "") == []
    assert normalize_control_value(definition, ["", ""]) == []
    assert normalize_control_value(definition, ["2026-01-01", ""]) == [
        "2026-01-01",
        "",
    ]
    with pytest.raises(Exception, match="requires a start date"):
        normalize_control_value(definition, ["", "2026-01-31"])
    with pytest.raises(Exception, match="start cannot be after end"):
        normalize_control_value(definition, ["2026-02-01", "2026-01-01"])


def test_text_suggestions_remain_open_strings_and_obey_length_contracts():
    definition = QueryParameterDefinition(
        id="scenario",
        type="string",
        max_length=8,
        suggestions=[
            Choice(label="Base", value="base"),
            Choice(label="Upside", value="upside"),
        ],
    )

    assert normalize_control_value(definition, "custom") == "custom"
    with pytest.raises(Exception, match="longer than 8"):
        normalize_control_value(definition, "custom-value")
    with pytest.raises(ValidationError, match="suggestion values must be unique"):
        QueryParameterDefinition(
            id="duplicate",
            type="string",
            suggestions=[
                Choice(label="A", value="same"),
                Choice(label="B", value="same"),
            ],
        )
    with pytest.raises(ValidationError, match="suggestions are only valid for string"):
        QueryParameterDefinition(
            id="count",
            type="integer",
            suggestions=[Choice(label="One", value="1")],
        )


def test_date_bounds_and_hierarchical_selection_shapes_are_strict():
    day = QueryParameterDefinition(
        id="day",
        type="date",
        min_date="2026-01-01",
        max_date="2026-12-31",
    )
    assert normalize_control_value(day, "2026-08-24") == "2026-08-24"
    with pytest.raises(Exception, match="cannot be before"):
        normalize_control_value(day, "2025-12-31")

    single_path = SelectionControlDefinition(
        id="district",
        kind="selection",
        type="single_select",
        path_fields=["province", "city", "district"],
        options={"mode": "infer"},
    )
    assert normalize_control_value(single_path, ["Fujian", "Xiamen", "Siming"]) == [
        "Fujian",
        "Xiamen",
        "Siming",
    ]
    with pytest.raises(Exception, match="3-level path"):
        normalize_control_value(single_path, ["Fujian", "Xiamen"])

    multiple_paths = SelectionControlDefinition(
        id="districts",
        kind="selection",
        type="multi_select",
        path_fields=["province", "city", "district"],
        options={"mode": "infer"},
        max_selected=2,
    )
    values = [
        ["Fujian", "Xiamen", "Siming"],
        ["Fujian", "Quanzhou", "Fengze"],
    ]
    assert normalize_control_value(multiple_paths, values) == values
    with pytest.raises(Exception, match="at most 2"):
        normalize_control_value(
            multiple_paths,
            [*values, ["Guangdong", "Shenzhen", "Nanshan"]],
        )


def test_portable_numbers_and_dates_reject_browser_python_ambiguities():
    number = ComputeControlDefinition(id="ratio", kind="compute", type="number")
    integer = ComputeControlDefinition(
        id="identifier", kind="compute", type="integer"
    )
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
        SelectionControlDefinition(
            id="unsafe-choice",
            kind="selection",
            type="single_select",
            options=static_options(
                [Choice(label="unsafe", value=9_007_199_254_740_992)]
            ),
        )
    with pytest.raises(Exception, match="YYYY-MM-DD"):
        normalize_control_value(day, "20260824")
    assert normalize_control_value(day, "2026-08-24") == "2026-08-24"


def test_query_compute_and_selection_resolvers_share_strict_contracts():
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v7",
            "id": "contract",
            "query_parameters": [{"id": "batch", "type": "integer", "default": 7}],
            "controls": [
                {"id": "factor", "kind": "compute", "type": "integer", "default": 2},
                {"id": "delay", "kind": "compute", "type": "number", "default": 0},
                {
                    "id": "region",
                    "kind": "selection",
                    "type": "multi_select",
                    "field": "region",
                    "options": {
                        "mode": "static",
                        "choices": [
                            {"label": "North", "value": "north"},
                            {"label": "South", "value": "south"},
                        ],
                    },
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
        resolve_query_parameters(
            dashboard, {"batch": 1.5}, timezone_name="Asia/Shanghai"
        )
    assert query_error.value.details["code"] == "query_parameter_invalid_type"

    with pytest.raises(ExecutionFailure) as compute_error:
        resolve_compute_values(
            definition,
            {
                "dashboard:contract/factor": 2.5,
                "dashboard:contract/delay": 0,
            },
        )
    assert compute_error.value.details["code"] == "compute_control_invalid_type"

    with pytest.raises(ExecutionFailure) as alias_error:
        resolve_selection_states(
            definition,
            {"region": {"intent": "explicit", "values": ["north"]}},
        )
    assert alias_error.value.details == {
        "code": "selection_control_unknown",
        "keys": ["region"],
    }

    resolved = resolve_selection_states(
        definition,
        {
            "dashboard:contract/region": {
                "intent": "explicit",
                "values": ["north"],
            }
        },
    )
    assert resolved == {
        "dashboard:contract/region": {
            "intent": "explicit",
            "values": ["north"],
        }
    }


def test_typed_choice_values_round_trip_to_the_declared_json_value():
    definition = ComputeControlDefinition(
        id="mode",
        kind="compute",
        type="single_select",
        options=static_options(
            [
                Choice(label="One", value=1),
                Choice(label="Enabled", value=True),
            ]
        ),
    )

    assert normalize_control_value(definition, "1") == 1
    assert normalize_control_value(definition, "true") is True


def test_browser_cache_is_tab_local_while_server_cache_can_be_workspace_scoped():
    with pytest.raises(ValidationError, match="Browser Runtime cache supports only"):
        InteractiveTransformDefinition(
            schema="dataviz/interactive-transform/v2",
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
        schema="dataviz/interactive-transform/v2",
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
