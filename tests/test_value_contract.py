from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from dataviz.errors import ExecutionFailure
from dataviz.execution.parameters import (
    normalize_query_parameter_state,
    project_query_inputs,
    resolve_query_parameter_states,
)
from dataviz.value_contract import normalize_control_value
from dataviz.workspace.controls import (
    project_control_values,
    resolve_control_states,
)
from dataviz.workspace.models import (
    CacheDefinition,
    Choice,
    ControlDefinition,
    DashboardDefinition,
    DeclarativeViewDefinition,
    InteractiveExportDefinition,
    InteractiveTransformDefinition,
    QueryParameterDefinition,
    SqlSourceDefinition,
)


def static_options(choices):
    return {"mode": "static", "choices": choices}


def initial_control_states(definition):
    return resolve_control_states(definition, None, phase="canvas-hydration")


def resolve_control_values(definition, provided=None):
    payload = None
    if provided is not None:
        payload = {
            key: {"value": value, "revision": 0}
            for key, value in provided.items()
        }
    return project_control_values(
        definition,
        resolve_control_states(definition, payload),
    )


def test_relative_date_defaults_resolve_once_in_workspace_timezone_and_project_parts():
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v17",
            "id": "relative-dates",
            "query_parameters": [
                {
                    "id": "job_date_range",
                    "type": "range_input", "value_type": "date",
                    "required": True,
                    "default": [
                        {"mode": "relative", "anchor": "today", "offset": "-3d"},
                        {"mode": "relative", "anchor": "today", "offset": "-1d"},
                    ],
                }
            ],
        }
    )
    dashboard = SimpleNamespace(definition=definition)
    # 16:30 UTC is already the next calendar day in Asia/Shanghai.
    values = resolve_query_parameter_states(
        dashboard.definition.query_parameters,
        None,
        timezone_name="Asia/Shanghai",
        current_time=datetime(2026, 8, 24, 16, 30, tzinfo=timezone.utc),
    )
    source = SqlSourceDefinition.model_validate(
        {
            "schema": "dataviz/source/v6",
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

    assert values == {"job_date_range": {"value": ["2026-08-22", "2026-08-24"]}}
    assert project_query_inputs(source.query_inputs, values) == {
        "start_date": "2026-08-22",
        "end_date": "2026-08-24",
    }


def test_query_parameter_selection_distinguishes_all_include_exclude_and_none():
    definition = QueryParameterDefinition.model_validate(
        {
            "id": "items",
            "type": "multiple_select",
            "value_type": "text",
            "default": {"mode": "all"},
            "options": {
                "mode": "static",
                "choices": [
                    {"label": "A", "value": "A"},
                    {"label": "B", "value": "B"},
                ],
            },
        }
    )
    bindings = {
        "item_values": "items",
        "item_selection": {"parameter": "items", "projection": "selection"},
        "item_state": {"parameter": "items", "projection": "state"},
    }

    assert normalize_query_parameter_state(definition, {"selection": "all", "value": []}) == {
        "selection": "all", "value": []
    }
    assert normalize_query_parameter_state(
        definition, {"selection": "exclude", "value": ["B"]}
    ) == {"selection": "exclude", "value": ["B"]}
    state = {"items": {"selection": "include", "value": ["A"]}}
    assert project_query_inputs(bindings, state) == {
        "item_values": ["A"],
        "item_selection": "include",
        "item_state": {"selection": "include", "value": ["A"]},
    }
    with pytest.raises(Exception, match="non-empty selection"):
        normalize_query_parameter_state(
            definition.model_copy(update={"required": True}),
            {"selection": "none", "value": []},
        )


def test_relative_date_default_contract_rejects_ambiguous_or_reversed_expressions():
    with pytest.raises(ValidationError, match="integer day offset"):
        QueryParameterDefinition.model_validate(
            {
                "id": "date",
                "type": "single_input", "value_type": "date",
                "default": {"mode": "relative", "anchor": "today", "offset": "-1week"},
            }
        )
    with pytest.raises(ValidationError, match="start offset cannot be after"):
        QueryParameterDefinition.model_validate(
            {
                "id": "dates",
                "type": "range_input", "value_type": "date",
                "default": [
                    {"mode": "relative", "anchor": "today", "offset": "+1d"},
                    {"mode": "relative", "anchor": "today", "offset": "-1d"},
                ],
            }
        )
    with pytest.raises(ValidationError, match="exactly two fixed or relative Date Atoms"):
        QueryParameterDefinition.model_validate(
            {
                "id": "dates",
                "type": "range_input",
                "value_type": "date",
                "default": {
                    "mode": "relative",
                    "anchor": "today",
                    "start_offset": "-7d",
                    "end_offset": "-1d",
                },
            }
        )
    with pytest.raises(ValidationError, match="only valid for Query Parameters"):
        ControlDefinition.model_validate(
            {
                "id": "date",

                "type": "single_input", "value_type": "date",
                "default": {"mode": "relative", "anchor": "today", "offset": "-1d"},
            }
        )


def test_date_range_default_allows_fixed_and_relative_endpoints():
    definition = QueryParameterDefinition.model_validate(
        {
            "id": "period",
            "type": "range_input",
            "value_type": "date",
            "default": [
                "2026-08-01",
                {"mode": "relative", "anchor": "today", "offset": "-1d"},
            ],
        }
    )
    dashboard = SimpleNamespace(
        definition=DashboardDefinition.model_validate(
            {
                "schema": "dataviz/dashboard/v17",
                "id": "mixed-date-range",
                "query_parameters": [definition.model_dump(mode="json")],
            }
        )
    )

    assert resolve_query_parameter_states(
        dashboard.definition.query_parameters,
        None,
        timezone_name="Asia/Shanghai",
        current_time=datetime(2026, 8, 24, 8, tzinfo=timezone.utc),
    ) == {"period": {"value": ["2026-08-01", "2026-08-23"]}}


def test_control_defaults_are_validated_when_the_dsl_is_loaded():
    with pytest.raises(ValidationError, match="value must be an integer"):
        QueryParameterDefinition(id="count", type="single_input", value_type="integer", default=1.5)
    with pytest.raises(ValidationError, match="value must be at least 1"):
        ControlDefinition(
            id="count", type="single_input", value_type="integer", default=0, min=1, max=10
        )
    with pytest.raises(ValidationError, match="not one of the declared choices"):
        ControlDefinition(
            id="region",
                        type="single_select", value_type="text",
            initial={"mode": "value", "value": "missing"},
            options=static_options([Choice(label="North", value="north")]),
        )
    with pytest.raises(ValidationError, match="required controls cannot be clearable"):
        ControlDefinition(
            id="region",
                        type="multiple_select", value_type="text",
            required=True,
            clearable=True,
            options=static_options([Choice(label="North", value="north")]),
        )
    optional_single = ControlDefinition(
        id="region",
                type="single_select", value_type="text",
        clearable=True,
        options=static_options([Choice(label="North", value="north")]),
    )
    assert optional_single.clearable is True


def test_select_option_domains_separate_static_values_from_inferred_intent():
    with pytest.raises(ValidationError, match="use initial instead of default"):
        ControlDefinition.model_validate(
            {
                "id": "city",

                "type": "multiple_select", "value_type": "text",
                "field": "city",
                "default": ["Shenzhen"],
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError, match="options.mode=static"):
        QueryParameterDefinition.model_validate(
            {
                "id": "city",
                "type": "single_select", "value_type": "text",
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError):
        ControlDefinition.model_validate(
            {
                "id": "city",

                "type": "multiple_select", "value_type": "text",
                "choices": [{"label": "Shenzhen", "value": "Shenzhen"}],
            }
        )

    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v17",
            "id": "option-intents",
            "controls": [
                {
                    "id": "city",

                    "type": "multiple_select", "value_type": "text",
                    "field": "city",
                    "options": {"mode": "infer"},
                },
                {
                    "id": "store",

                    "type": "multiple_select", "value_type": "text",
                    "field": "store",
                    "initial": {"mode": "empty"},
                    "options": {"mode": "infer"},
                },
                {
                    "id": "region",

                    "type": "multiple_select", "value_type": "text",
                    "field": "region",
                    "initial": {"mode": "values", "values": ["north"]},
                    "options": {
                        "mode": "static",
                        "choices": [{"label": "North", "value": "north"}],
                    },
                },
            ],
        }
    )

    assert initial_control_states(definition) == {
        "dashboard:option-intents/city": {
            "intent": "all_available",
            "value": [],
            "revision": 0,
        },
        "dashboard:option-intents/store": {
            "intent": "explicit",
            "value": [],
            "revision": 0,
        },
        "dashboard:option-intents/region": {
            "intent": "explicit",
            "value": ["north"],
            "revision": 0,
        },
    }

    required_inferred = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v17",
            "id": "required-inferred",
            "controls": [
                {
                    "id": "city",

                    "type": "single_select", "value_type": "text",
                    "field": "city",
                    "required": True,
                    "options": {"mode": "infer"},
                }
            ],
        }
    )
    with pytest.raises(ExecutionFailure, match="a value is required"):
        resolve_control_states(required_inferred, {})
    assert resolve_control_states(
        required_inferred,
        {},
        phase="canvas-hydration",
    ) == {
        "dashboard:required-inferred/city": {
            "value": None,
            "revision": 0,
        }
    }


def test_query_defaults_and_control_initial_policies_are_explicitly_separate():
    choices = [
        {"label": "Alpha", "value": "alpha"},
        {"label": "Beta", "value": "beta"},
    ]
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v17",
            "id": "select-initials",
            "query_parameters": [
                {
                    "id": "models",
                    "type": "multiple_select",
                    "value_type": "text",
                    "default": {"mode": "all"},
                    "options": {"mode": "static", "choices": choices},
                },
                {
                    "id": "primary",
                    "type": "single_select",
                    "value_type": "text",
                    "default": {"mode": "first"},
                    "options": {"mode": "static", "choices": choices},
                },
            ],
            "controls": [
                {
                    "id": "comparison",

                    "type": "multiple_select",
                    "value_type": "text",
                    "initial": {"mode": "values", "values": ["beta"]},
                    "options": {"mode": "static", "choices": choices},
                },
                {
                    "id": "focus",

                    "field": "model",
                    "type": "single_select",
                    "value_type": "text",
                    "initial": {"mode": "empty"},
                    "options": {"mode": "infer"},
                },
            ],
        }
    )

    assert resolve_query_parameter_states(
        definition.query_parameters,
        None,
        timezone_name="Asia/Shanghai",
    ) == {
        "models": {"selection": "all", "value": []},
        "primary": {"value": "alpha"},
    }
    assert resolve_control_values(definition, None) == {
        "dashboard:select-initials/comparison": ["beta"],
        "dashboard:select-initials/focus": None,
    }
    assert initial_control_states(definition)[
        "dashboard:select-initials/focus"
    ] == {"value": None, "revision": 0}


def test_non_select_inputs_share_typed_defaults_without_select_reconciliation():
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v17",
            "id": "typed-input-defaults",
            "query_parameters": [
                {
                    "id": "count",
                    "type": "single_input",
                    "value_type": "integer",
                    "default": "3",
                    "min": 1,
                    "max": 9,
                },
                {
                    "id": "tags",
                    "type": "multiple_input",
                    "value_type": "text",
                    "default": ["alpha", "beta"],
                },
            ],
            "controls": [
                {
                    "id": "window",

                    "type": "range_input",
                    "value_type": "number",
                    "default": [0.25, 0.75],
                    "min": 0,
                    "max": 1,
                    "step": 0.05,
                },
                {
                    "id": "enabled",

                    "field": "enabled",
                    "type": "single_input",
                    "value_type": "boolean",
                    "default": False,
                },
                {
                    "id": "period",

                    "field": "day",
                    "type": "range_input",
                    "value_type": "date",
                    "default": ["2026-08-01", "2026-08-28"],
                },
            ],
        }
    )

    assert resolve_query_parameter_states(
        definition.query_parameters,
        None,
        timezone_name="Asia/Shanghai",
    ) == {"count": {"value": 3}, "tags": {"value": ["alpha", "beta"]}}
    assert resolve_control_values(definition, None) == {
        "dashboard:typed-input-defaults/window": [0.25, 0.75],
        "dashboard:typed-input-defaults/enabled": False,
        "dashboard:typed-input-defaults/period": ["2026-08-01", "2026-08-28"],
    }
    assert initial_control_states(definition) == {
        "dashboard:typed-input-defaults/window": {
            "value": [0.25, 0.75],
            "revision": 0,
        },
        "dashboard:typed-input-defaults/enabled": {
            "value": False,
            "revision": 0,
        },
        "dashboard:typed-input-defaults/period": {
            "value": ["2026-08-01", "2026-08-28"],
            "revision": 0,
        },
    }

    with pytest.raises(ValidationError, match="Input should be None"):
        QueryParameterDefinition.model_validate(
            {
                "id": "count",
                "type": "single_input",
                "value_type": "integer",
                "initial": {"mode": "value", "value": 3},
            }
        )


def test_selection_dependency_authoring_contract_is_explicit_and_strict():
    definition = ControlDefinition.model_validate(
        {
            "id": "dates",

            "type": "multiple_select", "value_type": "text",
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
        ControlDefinition.model_validate(
            {
                "id": "dates",

                "type": "multiple_select", "value_type": "text",
                "cascade": True,
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError, match="String should match pattern"):
        ControlDefinition.model_validate(
            {
                "id": "dates",

                "type": "multiple_select", "value_type": "text",
                "depends_on": ["dow"],
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError, match="duplicate references"):
        ControlDefinition.model_validate(
            {
                "id": "dates",

                "type": "multiple_select", "value_type": "text",
                "depends_on": ["view.dow", "view.dow"],
                "options": {"mode": "infer"},
            }
        )
    with pytest.raises(ValidationError, match="only valid for single_select or multiple_select"):
        ControlDefinition.model_validate(
            {
                "id": "threshold",

                "type": "single_input", "value_type": "number",
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
    radar = DeclarativeViewDefinition(
        id="radar",
        template="radar",
        input="source:data/main",
        label="entity",
        columns=["quality", "speed"],
    )
    assert radar.template == "radar"
    point_map = DeclarativeViewDefinition(
        id="stores",
        template="map",
        input="source:stores/main",
        mark="point",
        longitude="longitude",
        latitude="latitude",
        label="store_name",
    )
    assert point_map.mark == "point"
    region_map = DeclarativeViewDefinition(
        id="regions",
        template="map",
        input="source:regions/main",
        mark="region",
        geojson="china-city",
        data_key="city_code",
        feature_key="properties.adcode",
        color="revenue",
    )
    assert region_map.geojson == "china-city"
    with pytest.raises(ValidationError, match="mark=point requires: latitude"):
        DeclarativeViewDefinition(
            id="broken-point",
            template="map",
            input="source:stores/main",
            mark="point",
            longitude="longitude",
        )
    with pytest.raises(ValidationError, match="mark=region requires: feature_key, color"):
        DeclarativeViewDefinition(
            id="broken-region",
            template="map",
            input="source:regions/main",
            mark="region",
            geojson="china-city",
            data_key="city_code",
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
    with pytest.raises(ValidationError):
        DeclarativeViewDefinition(
            id="chart",
            template="bar",
            engine="alternate",
            input="source:data/main",
            x="category",
            y="amount",
        )


def test_date_range_empty_and_open_values_have_one_canonical_shape():
    definition = ControlDefinition(
        id="period",
                type="range_input", value_type="date",
        allow_empty=(False, True),
    )

    assert normalize_control_value(definition, "") == []
    assert normalize_control_value(definition, ["", ""]) == []
    assert normalize_control_value(definition, ["2026-01-01", ""]) == [
        "2026-01-01",
        "",
    ]
    with pytest.raises(Exception, match="requires a start value"):
        normalize_control_value(definition, ["", "2026-01-31"])
    with pytest.raises(Exception, match="start cannot be after end"):
        normalize_control_value(definition, ["2026-02-01", "2026-01-01"])


def test_text_suggestions_remain_open_strings_and_obey_length_contracts():
    definition = QueryParameterDefinition(
        id="scenario",
        type="single_input", value_type="text",
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
            type="single_input", value_type="text",
            suggestions=[
                Choice(label="A", value="same"),
                Choice(label="B", value="same"),
            ],
        )
    with pytest.raises(ValidationError, match="suggestions are only valid for single_input/text"):
        QueryParameterDefinition(
            id="count",
            type="single_input", value_type="integer",
            suggestions=[Choice(label="One", value="1")],
        )


def test_date_bounds_and_hierarchical_selection_shapes_are_strict():
    day = QueryParameterDefinition(
        id="day",
        type="single_input", value_type="date",
        min_date="2026-01-01",
        max_date="2026-12-31",
    )
    assert normalize_control_value(day, "2026-08-24") == "2026-08-24"
    with pytest.raises(Exception, match="cannot be before"):
        normalize_control_value(day, "2025-12-31")

    single_path = ControlDefinition(
        id="district",
                type="single_select", value_type="text",
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

    multiple_paths = ControlDefinition(
        id="districts",
                type="multiple_select", value_type="text",
        path_fields=["province", "city", "district"],
        options={"mode": "infer"},
        initial={"mode": "empty"},
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


def test_multiple_input_normalizes_typed_values_and_enforces_list_contracts():
    identifiers = QueryParameterDefinition(
        id="identifiers",
        type="multiple_input",
        value_type="integer",
        min=1,
        max_items=3,
    )

    assert normalize_control_value(identifiers, "1, 2, 3") == [1, 2, 3]
    with pytest.raises(Exception, match="integer"):
        normalize_control_value(identifiers, [1, 2.5])
    with pytest.raises(Exception, match="unique"):
        normalize_control_value(identifiers, [1, 1])
    with pytest.raises(Exception, match="at most 3"):
        normalize_control_value(identifiers, [1, 2, 3, 4])


def test_numeric_range_input_uses_one_ordered_typed_pair():
    integer_range = ControlDefinition(
        id="integer-range",
                type="range_input",
        value_type="integer",
        min=0,
        max=10,
        step=2,
    )
    number_range = ControlDefinition(
        id="number-range",
                type="range_input",
        value_type="number",
        min=0,
        max=1,
        step=0.05,
    )

    assert normalize_control_value(integer_range, "2,8") == [2, 8]
    assert normalize_control_value(number_range, [0.25, 0.75]) == [0.25, 0.75]
    with pytest.raises(Exception, match="start cannot be after end"):
        normalize_control_value(integer_range, [8, 2])
    with pytest.raises(Exception, match="step 2"):
        normalize_control_value(integer_range, [1, 8])


def test_portable_numbers_and_dates_reject_cross_runtime_ambiguities():
    number = ControlDefinition(id="ratio", type="single_input", value_type="number")
    integer = ControlDefinition(
        id="identifier", type="single_input", value_type="integer"
    )
    day = QueryParameterDefinition(id="day", type="single_input", value_type="date")

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
        ControlDefinition(
            id="unsafe-choice",
                        type="single_select", value_type="integer",
            options=static_options(
                [Choice(label="unsafe", value=9_007_199_254_740_992)]
            ),
        )
    with pytest.raises(Exception, match="YYYY-MM-DD"):
        normalize_control_value(day, "20260824")
    assert normalize_control_value(day, "2026-08-24") == "2026-08-24"


def test_query_and_control_resolvers_share_strict_contracts():
    definition = DashboardDefinition.model_validate(
        {
            "schema": "dataviz/dashboard/v17",
            "id": "contract",
            "query_parameters": [{"id": "batch", "type": "single_input", "value_type": "integer", "default": 7}],
            "controls": [
                {"id": "factor", "type": "single_input", "value_type": "integer", "default": 2},
                {"id": "delay", "type": "single_input", "value_type": "number", "default": 0},
                {
                    "id": "region",

                    "type": "multiple_select", "value_type": "text",
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
        resolve_query_parameter_states(
            dashboard.definition.query_parameters,
            {"batch": {"value": 1.5}},
            timezone_name="Asia/Shanghai",
        )
    assert query_error.value.details["code"] == "query_parameter_invalid_type"

    with pytest.raises(ExecutionFailure) as compute_error:
        resolve_control_values(
            definition,
            {
                "dashboard:contract/factor": 2.5,
                "dashboard:contract/delay": 0,
            },
        )
    assert compute_error.value.details["code"] == "control_state_invalid_type"

    with pytest.raises(ExecutionFailure) as alias_error:
        resolve_control_states(
            definition,
            {
                "region": {
                    "intent": "explicit",
                    "value": ["north"],
                    "revision": 0,
                }
            },
        )
    assert alias_error.value.details == {
        "code": "control_state_unknown",
        "keys": ["region"],
    }

    resolved = resolve_control_states(
        definition,
        {
            "dashboard:contract/region": {
                "intent": "explicit",
                "value": ["north"],
                "revision": 0,
            }
        },
    )
    assert resolved == {
        "dashboard:contract/factor": {
            "value": 2,
            "revision": 0,
        },
        "dashboard:contract/delay": {
            "value": 0,
            "revision": 0,
        },
        "dashboard:contract/region": {
            "intent": "explicit",
            "value": ["north"],
            "revision": 0,
        }
    }


def test_typed_choice_values_round_trip_to_the_declared_json_value():
    definition = ControlDefinition(
        id="mode",
                type="single_select", value_type="integer",
        options=static_options(
            [
                Choice(label="One", value=1),
                Choice(label="Two", value=2),
            ]
        ),
    )

    assert normalize_control_value(definition, "1") == 1
    assert normalize_control_value(definition, "2") == 2


def test_browser_cache_is_tab_local_while_server_cache_can_be_workspace_scoped():
    with pytest.raises(ValidationError, match="Browser Runtime cache supports only"):
        InteractiveTransformDefinition(
            schema="dataviz/interactive-transform/v4",
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
        schema="dataviz/interactive-transform/v4",
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
