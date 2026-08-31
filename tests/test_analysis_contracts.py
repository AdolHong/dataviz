from __future__ import annotations

import pytest

from dataviz.analysis.contracts import (
    validate_analysis_catalog_producer,
    validate_analysis_result,
    validate_analysis_result_producer,
)
from dataviz.errors import ValidationFailure
from dataviz.protocols import (
    ANALYSIS_CATALOG_SCHEMA,
    ANALYSIS_ENTRY_SCHEMA,
    ANALYSIS_RESULT_SCHEMA,
)


def _failed_result() -> dict:
    return {
        "schema": ANALYSIS_RESULT_SCHEMA,
        "status": "failed",
        "error": {"code": "expected_failure"},
    }


def test_analysis_result_reader_retains_forward_compatible_unknown_fields():
    payload = {**_failed_result(), "future_extension": {"enabled": True}}

    assert validate_analysis_result(payload)["future_extension"] == {"enabled": True}


def test_analysis_result_producer_rejects_top_level_field_typo():
    payload = {**_failed_result(), "effective_control": {}}

    with pytest.raises(ValidationFailure) as caught:
        validate_analysis_result_producer(payload)

    assert caught.value.details == {
        "code": "analysis_producer_unknown_field",
        "path": "result",
        "fields": ["effective_control"],
    }


def test_analysis_result_producer_rejects_nested_field_typo():
    payload = {
        "schema": ANALYSIS_RESULT_SCHEMA,
        "status": "ready",
        "outputs": [
            {
                "reference": "sales::source:orders/main",
                "kind": "table",
                "content_hash": "a" * 64,
                "run_id": "run_test",
                "logical_value_hahs": "b" * 64,
            }
        ],
    }

    with pytest.raises(ValidationFailure) as caught:
        validate_analysis_result_producer(payload)

    assert caught.value.details["path"] == "result.outputs[0]"
    assert caught.value.details["fields"] == ["logical_value_hahs"]


def test_analysis_catalog_producer_rejects_nested_entry_field_typo():
    payload = {
        "schema": ANALYSIS_CATALOG_SCHEMA,
        "generation": "catalog-test",
        "count": 1,
        "entries": [
            {
                "schema": ANALYSIS_ENTRY_SCHEMA,
                "reference": "sales::source:orders/main",
                "dashboard": {"id": "sales", "path": "dashboards/sales"},
                "kind": "source",
                "stage": "base",
                "title": "Orders",
                "query_paramters": [],
            }
        ],
    }

    with pytest.raises(ValidationFailure) as caught:
        validate_analysis_catalog_producer(payload)

    assert caught.value.details["path"] == "catalog.entries[0]"
    assert caught.value.details["fields"] == ["query_paramters"]
