from __future__ import annotations

import json
from pathlib import Path
import shutil

from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.protocols import QUERY_INSPECTION_SCHEMA


FEATURES = Path("examples/feature-showcase")


def test_inspect_query_projects_canonical_filters_without_execution_or_materialization(
    tmp_path: Path,
):
    workspace = tmp_path / "workspace"
    shutil.copytree(
        FEATURES,
        workspace,
        ignore=shutil.ignore_patterns(".dataviz", "__pycache__", "*.pyc"),
    )
    materializations = workspace / ".dataviz" / "parameter-materializations"

    result = CliRunner().invoke(
        app,
        [
            "inspect",
            "query",
            str(workspace),
            "parameter-domain-lab",
            "--source",
            "metrics",
            "--query-param",
            'provinces={"selection":"include","value":["GD"]}',
            "--query-param",
            'cities={"selection":"exclude","value":["SZ"]}',
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == QUERY_INSPECTION_SCHEMA
    assert payload["executed"] is False
    assert payload["query"]["query_filters"]["province_scope"]["predicate"]
    assert "NOT" in payload["query"]["query_filters"]["city_scope"]["predicate"]
    cities = next(item for item in payload["parameters"] if item["id"] == "cities")
    assert cities["domain_evidence"]["status"] in {
        "missing",
        "unavailable",
    }
    assert not materializations.exists()
