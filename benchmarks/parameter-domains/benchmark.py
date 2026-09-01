"""Reproducible Parameter Materialization/Lookup benchmark.

Run from the repository root:

    PYTHONPATH=src .venv/bin/python benchmarks/parameter-domains/benchmark.py \
      --output benchmarks/results/parameter-domain-lookup-YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable

from dataviz import __version__
from dataviz.execution.parameter_materializations import ParameterMaterializationStore
from dataviz.filesystem import atomic_write_text
from dataviz.workspace import load_workspace


FIXED_ROW_COUNTS = (10_000, 100_000, 250_000)


def _elapsed(action: Callable[[], Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    value = action()
    return value, round((time.perf_counter() - started) * 1000, 3)


def _workspace(root: Path, rows: int) -> Path:
    dashboard = root / "dashboards" / "parameter-scale"
    domains = root / "parameter_domains"
    auth = root / "auth"
    dashboard.mkdir(parents=True)
    domains.mkdir()
    auth.mkdir()
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v1\nkind: workspace\nid: parameter-scale\n"
        "title: Parameter scale benchmark\n",
        encoding="utf-8",
    )
    (auth / "adapters.yaml").write_text(
        "adapters:\n  benchmark:\n    type: duckdb\n    database: ':memory:'\n",
        encoding="utf-8",
    )
    (domains / "items.yaml").write_text(
        """schema: dataviz/parameter-domain/v2
kind: parameter_domain
id: items
type: sql
adapter: warehouse
code: items.sql
max_rows: 300000
max_bytes: 1073741824
materialization: {refresh_after_seconds: 43200, expire_after_seconds: 604800}
""",
        encoding="utf-8",
    )
    (domains / "items.sql").write_text(
        f"""select
  'D' || cast(i % 10 as varchar) as division,
  'C' || cast(i % 100 as varchar) as category,
  'S' || cast(i % 1000 as varchar) as subcategory,
  'ITEM-' || lpad(cast(i as varchar), 6, '0') as item_nbr,
  '商品 ' || cast(i as varchar) as item_name,
  'item ' || cast(i as varchar) as item_keywords
from range({rows}) values(i)
""",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v14
kind: dashboard
id: parameter-scale
title: Parameter scale
adapters: {warehouse: benchmark}
parameter_domains: [workspace:/parameter_domains/items.yaml]
query_parameters:
  - id: division
    type: multiple_select
    value_type: text
    default: {mode: all}
    options:
      mode: domain
      source: items
      value_field: division
  - id: item_nbr
    type: multiple_select
    value_type: text
    default: {mode: all}
    options:
      mode: domain
      source: items
      value_field: item_nbr
      label_field: item_name
      keywords_field: item_keywords
      depends_on: {division: {field: division}}
""",
        encoding="utf-8",
    )
    return root


def run_case(rows: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"dataviz-parameter-{rows}-") as temporary:
        root = _workspace(Path(temporary) / "workspace", rows)
        loaded = load_workspace(root)
        dashboard = loaded.dashboard("parameter-scale")
        store = ParameterMaterializationStore(loaded)
        record, build_ms = _elapsed(lambda: store.build(dashboard, "items"))
        first, first_ms = _elapsed(lambda: store.lookup(dashboard, "item_nbr", limit=50))
        exact, exact_ms = _elapsed(
            lambda: store.lookup(
                dashboard,
                "item_nbr",
                search=f"ITEM-{rows - 1:06d}",
                limit=50,
            )
        )
        parent, parent_ms = _elapsed(
            lambda: store.lookup(
                dashboard,
                "item_nbr",
                parent_states={"division": {"selection": "include", "value": ["D7"]}},
                limit=50,
            )
        )
        second, second_ms = _elapsed(
            lambda: store.lookup(
                dashboard,
                "item_nbr",
                limit=50,
                cursor=first["next_cursor"],
            )
        )
        response_bytes = len(
            json.dumps(first, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        return {
            "rows": rows,
            "generation": record.generation,
            "parquet_bytes": record.data_path.stat().st_size if record.data_path else 0,
            "build_ms": build_ms,
            "first_lookup_ms": first_ms,
            "exact_search_ms": exact_ms,
            "parent_filter_ms": parent_ms,
            "second_page_ms": second_ms,
            "first_page_items": len(first["items"]),
            "second_page_items": len(second["items"]),
            "exact_search_total": exact["total"],
            "parent_filter_total": parent["total"],
            "response_bytes": response_bytes,
            "bounded": len(first["items"]) <= 50 and not first["selected_items"],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/results") / f"parameter-domain-lookup-{date.today()}.json",
    )
    arguments = parser.parse_args()
    payload = {
        "schema": "dataviz/parameter-domain-benchmark/v1",
        "date": date.today().isoformat(),
        "dataviz_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "row_counts": list(FIXED_ROW_COUNTS),
        "cases": [run_case(rows) for rows in FIXED_ROW_COUNTS],
    }
    atomic_write_text(
        arguments.output,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
