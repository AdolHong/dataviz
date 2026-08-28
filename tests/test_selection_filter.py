from __future__ import annotations

import pandas as pd

from dataviz.execution.selection_filter import apply_selection_filters


def _filter(
    *,
    control_id: str,
    value,
    control_type: str = "multiple_select",
    field: str | None = None,
    path_fields: list[str] | None = None,
    operator: str = "auto",
):
    return {
        "id": control_id,
        "definition": {
            "id": control_id,
            "kind": "selection",
            "type": control_type,
            "field": field,
            "path_fields": path_fields or [],
        },
        "binding": {"field": field or control_id, "operator": operator},
        "value": value,
    }


def test_selection_filters_are_include_only_and_ignore_unrelated_tables():
    frame = pd.DataFrame(
        [
            {"province": "广东", "city": "深圳", "value": 10},
            {"province": "广东", "city": "佛山", "value": 20},
            {"province": "福建", "city": "厦门", "value": 30},
        ]
    )

    selected = apply_selection_filters(
        frame,
        [_filter(control_id="province", value=["广东"], field="province")],
    )
    assert selected.to_dict(orient="records") == [
        {"province": "广东", "city": "深圳", "value": 10},
        {"province": "广东", "city": "佛山", "value": 20},
    ]

    unrelated = frame[["value"]]
    assert apply_selection_filters(
        unrelated,
        [_filter(control_id="province", value=["广东"], field="province")],
    ).equals(unrelated)


def test_explicit_empty_selection_means_zero_rows_not_all_rows():
    frame = pd.DataFrame(
        [
            {"region": "north", "value": 1},
            {"region": "south", "value": 2},
        ]
    )

    selected = apply_selection_filters(
        frame,
        [_filter(control_id="region", value=[], field="region")],
    )

    assert selected.empty
    assert list(selected.columns) == ["region", "value"]


def test_selection_filters_support_path_date_and_numeric_contracts():
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
            field="day",
        ),
        _filter(
            control_id="minimum",
            value=25,
            control_type="single_input",
            field="value",
            operator="gte",
        ),
    ]

    assert apply_selection_filters(frame, filters).to_dict(orient="records") == [
        {"province": "福建", "city": "厦门", "day": "2026-08-23", "value": 30}
    ]
