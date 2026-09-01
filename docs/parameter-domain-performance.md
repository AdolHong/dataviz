# Parameter Domain performance

SQL Parameter Domains are built once as immutable Workspace-shared Parquet generations. Browser Lookup responses stay bounded to 50 rows by default and 100 rows at most; parent filtering, search, paging, and selected-label hydration read the same pinned generation and do not rerun Domain SQL.

The fixed maintainer benchmark covers 10K, 100K, and 250K rows:

```bash
PYTHONPATH=src .venv/bin/python benchmarks/parameter-domains/benchmark.py \
  --output benchmarks/results/parameter-domain-lookup-$(date +%F).json
```

The JSON evidence records materialization time, first-page Lookup, exact search, parent filtering, cursor paging, Parquet size, response size, and bounded-page assertions. Timings are characterization evidence rather than universal performance budgets because Adapter, disk, CPU, and candidate shape differ across Workspaces.
