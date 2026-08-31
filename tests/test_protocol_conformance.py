from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from dataviz.errors import DatavizError
from dataviz.documentation import docs_catalog
from dataviz.execution.control_filter import apply_control_filters
from dataviz.execution.outputs import validate_output_destination
from dataviz.execution.parameter_domains import (
    _project_choices,
    _resolve_dynamic_value,
)
from dataviz.execution.parameters import project_query_inputs, query_input_contract
from dataviz.protocols import CURRENT_PROTOCOL_SCHEMAS, protocol_registry
from dataviz.schema_docs import schema_catalog
from dataviz.state_snapshot import normalize_consumer_revision
from dataviz.value_contract import ValueContractViolation, json_value_signature
from dataviz.workspace.models import QueryParameterDefinition


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "conformance"


def _cases(name: str) -> list[dict[str, Any]]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))[
        "cases"
    ]


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if "$integer" in value:
        return int(value["$integer"])
    if "$number" in value:
        return math.nan
    if "$boolean" in value:
        return bool(value["$boolean"])
    if "$unsupported" in value:
        return lambda: None
    return {key: _decode(item) for key, item in value.items()}


def _error_code(error: BaseException) -> str | None:
    if isinstance(error, DatavizError):
        return error.details.get("code")
    return getattr(error, "code", None)


@pytest.mark.parametrize("case", _cases("input-binding"), ids=lambda item: item["id"])
def test_python_input_binding_conformance(case: dict[str, Any]):
    payload = case["input"]
    try:
        if case["operation"] == "canonicalize":
            actual = query_input_contract(payload["binding"])
        elif case["operation"] == "signature":
            actual = json.dumps(
                {
                    alias: query_input_contract(binding)
                    for alias, binding in sorted(payload["inputs"].items())
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        else:
            actual = project_query_inputs(
                {"result": payload["binding"]},
                {payload["binding"]["parameter"]: payload["value"]},
                {payload["binding"]["parameter"]: payload["intent"]},
            )["result"]
    except Exception as error:
        assert _error_code(error) == case.get("expected_error_code")
    else:
        assert "expected_error_code" not in case
        assert actual == case["expected"]


@pytest.mark.parametrize("case", _cases("control-filter"), ids=lambda item: item["id"])
def test_python_control_filter_conformance(case: dict[str, Any]):
    payload = case["input"]
    if case["operation"] == "path_filter":
        frame = pd.DataFrame(payload["rows"], columns=["level", "value"])
        item = {
            "definition": {"type": "multiple_select", "value_type": "text"},
            "consumer_binding": {
                "mode": "filter",
                "field": ["level", "value"],
                "inputs": ["main"],
                "empty": "match_none",
                "operator": "auto",
            },
            "value": payload["value"],
        }
        expected = case["expected"]
    else:
        frame = pd.DataFrame({"value": payload["rows"]})
        control_type = payload.get("control_type") or (
            "range_input"
            if payload["operator"] == "between"
            else "multiple_select"
            if payload["operator"] == "in"
            else "single_input"
        )
        item = {
            "definition": {
                "type": control_type,
                "value_type": payload["value_type"],
            },
            "consumer_binding": {
                "mode": "filter",
                "field": "value",
                "inputs": ["main"],
                "empty": payload.get("empty", "match_none"),
                "operator": payload["operator"],
            },
            "value": payload["value"],
        }
        expected = [{"value": value} for value in case.get("expected", [])]
    try:
        actual = apply_control_filters(frame, [item]).to_dict(orient="records")
    except Exception as error:
        assert _error_code(error) == case.get("expected_error_code")
    else:
        assert "expected_error_code" not in case
        if case["operation"] == "path_filter":
            assert [[item["level"], item["value"]] for item in actual] == expected
        else:
            assert actual == expected


@pytest.mark.parametrize("case", _cases("value-signature"), ids=lambda item: item["id"])
def test_python_value_signature_conformance(case: dict[str, Any]):
    try:
        actual = json_value_signature(_decode(case["input"]))
    except ValueContractViolation as error:
        assert error.code == case.get("expected_error_code")
    else:
        assert "expected_error_code" not in case
        assert actual == case["expected"]


@pytest.mark.parametrize("case", _cases("consumer-revision"), ids=lambda item: item["id"])
def test_python_consumer_revision_conformance(case: dict[str, Any]):
    payload = _decode(case["input"])
    try:
        actual = normalize_consumer_revision(payload["effective"], payload["applied"])
    except Exception as error:
        assert _error_code(error) == case.get("expected_error_code")
    else:
        assert "expected_error_code" not in case
        assert actual == case["expected"]


@pytest.mark.parametrize("case", _cases("output-capability"), ids=lambda item: item["id"])
def test_python_output_capability_conformance(case: dict[str, Any]):
    payload = case["input"]
    try:
        validate_output_destination(**payload)
    except Exception as error:
        assert _error_code(error) == case.get("expected_error_code")
    else:
        assert "expected_error_code" not in case


@pytest.mark.parametrize(
    "case",
    _cases("parameter-domain-projection"),
    ids=lambda item: item["id"],
)
def test_python_parameter_domain_projection_conformance(case: dict[str, Any]):
    parameter = QueryParameterDefinition.model_validate(case["parameter"])
    try:
        choices = _project_choices(
            parameter,
            pd.DataFrame(case["rows"]),
            case["values"],
        )
        value, intent = _resolve_dynamic_value(
            parameter,
            choices,
            supplied=True,
            raw_value=case["raw_value"],
            initialized=True,
            intent=case["intent"],
            strict=False,
            preserve_unavailable=False,
        )
    except Exception as error:
        assert _error_code(error) == case.get("expected_error_code")
    else:
        assert "expected_error_code" not in case
        assert choices == case["expected_choices"]
        assert {"value": value, "intent": intent} == case["expected"]


def test_javascript_runtime_and_web_component_share_conformance_corpus():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for cross-Runtime conformance")
    completed = subprocess.run(
        [node, str(ROOT / "tests" / "js" / "protocol-conformance.mjs")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_generated_canvas_runtime_is_valid_javascript():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for Runtime bundle syntax validation")
    completed = subprocess.run(
        [
            node,
            "--check",
            str(ROOT / "src" / "dataviz" / "server" / "static" / "canvas-runtime.js"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_schema_catalog_uses_the_canonical_protocol_registry():
    assert schema_catalog()["protocol_registry"] == protocol_registry()


def test_current_protocol_surfaces_share_one_canonical_version_map():
    assert protocol_registry()["current"] == CURRENT_PROTOCOL_SCHEMAS
    documented = docs_catalog()["strict-schema"]["current"]
    assert documented == {
        key: CURRENT_PROTOCOL_SCHEMAS[key]
        for key in documented
    }


def test_product_architecture_current_version_table_matches_protocols():
    text = (ROOT / "docs" / "product-architecture.md").read_text(encoding="utf-8")
    current_section = text.split("## 2.", 1)[0]
    labels = {
        "Workspace": "workspace",
        "Dashboard": "dashboard",
        "Presentation": "presentation",
        "Source": "source",
        "Dataset Transform": "dataset_transform",
        "Interactive Transform": "interactive_transform",
        "Dependency Contract": "dependency_contract",
        "State Snapshot": "state_snapshot",
        "Browser Runtime": "runtime",
        "Analysis Result": "analysis_result",
        "Analysis Evidence": "analysis_evidence",
        "Layout Contract": "layout_contract",
        "Workspace Change": "workspace_change",
    }
    for label, key in labels.items():
        match = re.search(
            rf"^{re.escape(label)}\s+(dataviz/\S+)$",
            current_section,
            flags=re.MULTILINE,
        )
        assert match, f"Missing current version row for {label}"
        assert match.group(1) == CURRENT_PROTOCOL_SCHEMAS[key]


def test_design_and_plan_baselines_match_current_protocols():
    keys = (
        "dashboard",
        "parameter_domain",
        "parameter_domain_contract",
        "parameter_domain_resolution",
        "presentation",
        "source",
        "dataset_transform",
        "interactive_transform",
        "dependency_contract",
        "layout_contract",
        "state_snapshot",
        "runtime",
        "analysis_result",
        "analysis_evidence",
    )
    for document in ("DESIGN.md", "plan.md"):
        baseline = "\n".join(
            (ROOT / document).read_text(encoding="utf-8").splitlines()[:30]
        )
        for key in keys:
            assert CURRENT_PROTOCOL_SCHEMAS[key] in baseline, (
                f"{document} current baseline is missing "
                f"{CURRENT_PROTOCOL_SCHEMAS[key]}"
            )
