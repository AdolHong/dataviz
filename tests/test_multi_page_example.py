import importlib.util
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from dataviz.execution import Executor
from dataviz.workspace import load_workspace, validate_workspace


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "multi-page-workspace"


def test_example_pages_run_independently_without_auth(tmp_path):
    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".dataviz", "__pycache__"))
    workspace = load_workspace(root)
    assert validate_workspace(workspace) == []
    assert not (root / "auth").exists()
    for page_id in ("annual", "history"):
        result = Executor(workspace).run("holiday", page_id=page_id)
        assert result.status == "ready"
        assert set(result.nodes) == {f"source:{page_id}"}
        assert result.outputs[f"source:{page_id}/main"].metadata["row_count"] == 3
        assert result.outputs[f"source:{page_id}/daily"].metadata["row_count"] == 45


def test_synthetic_sales_are_deterministic_and_reconcile():
    spec = importlib.util.spec_from_file_location("demo_sales", EXAMPLE / "dashboards/holiday/sales.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    annual = module.load(SimpleNamespace(query_inputs={"year": 2025}))
    history = module.load(SimpleNamespace(query_inputs={"years": [2025], "category": "水果"}))
    expected = annual["main"].query("category == '水果'").reset_index(drop=True)
    assert expected.equals(history["main"])
    assert history["daily"].equals(module.load(SimpleNamespace(
        query_inputs={"years": [2025, 2025], "category": "水果"}))["daily"])
    for row in annual["main"].itertuples():
        daily = annual["daily"].query("category == @row.category")
        assert row.actual_qty == daily.actual_qty.sum()
        assert row.net_uplift_qty == row.actual_qty - row.baseline_qty
        assert row.uplift_pct == round(row.net_uplift_qty / row.baseline_qty * 100, 2)
    assert module.load(SimpleNamespace(query_inputs={"years": [], "category": "水果"}))["main"].empty
    with pytest.raises(ValueError, match="2023"):
        module.load(SimpleNamespace(query_inputs={"year": 2030}))
