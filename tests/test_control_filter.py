from __future__ import annotations

import pandas as pd
import pytest

from dataviz.execution.control_filter import apply_control_filters
from dataviz.input_state import initial_input_state
from dataviz.workspace.models import ControlDefinition


def _filter(
    *,
    control_id: str,
    value,
    control_type: str = "multiple_select",
    field: str | None = None,
    path_fields: list[str] | None = None,
    operator: str = "auto",
    value_type: str = "text",
):
    return {
        "id": control_id,
        "definition": {
            "id": control_id,

            "type": control_type,
            "value_type": value_type,
            "field": field,
            "path_fields": path_fields or [],
        },
        "consumer_binding": {
            "field": field or control_id,
            "operator": operator,
            "empty": "match_none",
        },
        "value": value,
    }


def test_control_filters_are_include_only_and_ignore_unrelated_tables():
    frame = pd.DataFrame(
        [
            {"province": "广东", "city": "深圳", "value": 10},
            {"province": "广东", "city": "佛山", "value": 20},
            {"province": "福建", "city": "厦门", "value": 30},
        ]
    )

    selected = apply_control_filters(
        frame,
        [_filter(control_id="province", value=["广东"], field="province")],
    )
    assert selected.to_dict(orient="records") == [
        {"province": "广东", "city": "深圳", "value": 10},
        {"province": "广东", "city": "佛山", "value": 20},
    ]

    unrelated = frame[["value"]]
    assert apply_control_filters(
        unrelated,
        [_filter(control_id="province", value=["广东"], field="province")],
    ).equals(unrelated)


def test_match_none_empty_filter_means_zero_rows_not_all_rows():
    frame = pd.DataFrame(
        [
            {"region": "north", "value": 1},
            {"region": "south", "value": 2},
        ]
    )

    selected = apply_control_filters(
        frame,
        [_filter(control_id="region", value=[], field="region")],
    )

    assert selected.empty
    assert list(selected.columns) == ["region", "value"]


def test_all_available_intent_is_not_reinterpreted_as_an_explicit_empty_set():
    frame = pd.DataFrame(
        [
            {"region": "north", "value": 1},
            {"region": "south", "value": 2},
        ]
    )
    control_filter = _filter(control_id="region", value=[], field="region")
    control_filter["state"] = {
        "value": [],
        "revision": 0,
        "intent": "all_available",
    }

    selected = apply_control_filters(frame, [control_filter])

    assert selected.equals(frame)


@pytest.mark.parametrize("empty", ["match_none", "passthrough"])
def test_static_all_available_keeps_the_resolved_whitelist(empty):
    definition = ControlDefinition.model_validate({
        "id": "region", "type": "multiple_select", "value_type": "text",
        "initial": {"mode": "all"},
        "options": {"mode": "static", "choices": [{"value": "north", "label": "North"}]},
    })
    state = initial_input_state(definition).as_dict()
    item = _filter(control_id="region", value=state["value"], field="region")
    item["definition"] = definition.model_dump(mode="json")
    item["state"] = state
    item["consumer_binding"]["empty"] = empty
    frame = pd.DataFrame({"region": ["north", "south"]})
    assert apply_control_filters(frame, [item]).to_dict("records") == [{"region": "north"}]


def test_control_filters_support_path_date_and_numeric_contracts():
    frame = pd.DataFrame(
        [
            {"province": "广东", "city": "深圳", "day": "2026-08-20", "value": 10},
            {"province": "广东", "city": "佛山", "day": "2026-08-22", "value": 20},
            {"province": "福建", "city": "厦门", "day": "2026-08-23", "value": 30},
        ]
    )
    filters = [
        _filter(
            control_id="place",
            value=[["广东", "佛山"], ["福建", "厦门"]],
            path_fields=["province", "city"],
        ),
        _filter(
            control_id="day",
            value=["2026-08-21", "2026-08-23"],
            control_type="range_input",
            value_type="date",
            field="day",
        ),
        _filter(
            control_id="minimum",
            value=25,
            control_type="single_input",
            value_type="number",
            field="value",
            operator="gte",
        ),
    ]

    assert apply_control_filters(frame, filters).to_dict(orient="records") == [
        {"province": "福建", "city": "厦门", "day": "2026-08-23", "value": 30}
    ]
