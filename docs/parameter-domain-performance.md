# Parameter Domain performance

Each Dashboard owns its SQL Parameter Domain definition and SQL. The Server builds an immutable Parquet generation that the same Dashboard may reuse across users and tabs; different Dashboards never share the query definition or generation. Browser Lookup responses stay bounded; parent filtering, search, paging, and selected-label hydration read the same pinned generation and do not rerun Domain SQL.

The fixed maintainer benchmark covers 10K, 100K, and 250K rows:

```bash
PYTHONPATH=src .venv/bin/python benchmarks/parameter-domains/benchmark.py \
  --output benchmarks/results/parameter-domain-lookup-$(date +%F).json
```

The JSON evidence records materialization time, first-page Lookup, exact search, parent filtering, cursor paging, Parquet size, response size, and bounded-page assertions. Timings are characterization evidence rather than universal performance budgets because Adapter, disk, CPU, and candidate shape differ across Workspaces.
