# Browser test resources

`test_browser_runtime.py` automatically reuses `dataviz-tool/.browser-test-assets/`
when present. This directory is git-ignored and is not part of the package.
`DATAVIZ_E2E_ASSET_DIR` can select another cache directory.

The cache contains real upstream resources, not decoder or renderer mocks:

| File | Source | SHA-256 |
| --- | --- | --- |
| `Arrow.es2015.min.js` | `https://cdn.jsdelivr.net/npm/apache-arrow@21.1.0/Arrow.es2015.min.js` | `d3f0ded2a2bdd1208232b942f8e4810f7a402564fac3c78b4574158cd542acb9` |
| `world_110m.json` | `https://cdn.plot.ly/un/world_110m.json` | `e1bf51740ad28396265e52123ea7315d692f112664ab2cb0f1ea76a96fe1bb0a` |

Download these two files once into that directory, then run the browser suite
normally. The fixture validates their hashes and fulfills only the exact URLs
above from local files. An incomplete or mismatched cache fails explicitly;
without a cache directory, the original network behavior remains unchanged.
Plotly's map URL is not versioned: review changes before updating its checksum.

This isolates repeated CDN latency from interaction tests. It does not make the
whole suite offline, validate CDN availability, or change production defaults.
CLI-owned browsers and separately created browser contexts retain their normal
resource loading behavior. Report cached-resource usage with test results.

## Analysis interaction stability

`test_analysis_stability_workflow` runs three independent rounds using the
`stable_analysis` fixture in `tests/conftest.py`. Each uses an isolated SQLite
database, a six-item candidate catalog and 100,001 server-only fact rows.
The test checks category changes, native Table selection/highlighting, Plotly
filtering, annotation save/refresh, clear/empty/error recovery, rapid changes,
and reloading the same Run. No manual highlight or redundant value subscription
is used as a workaround. Network assertions reject full fact-table downloads.

Run the same workflow for each engine:

```sh
DATAVIZ_BROWSER=chromium .venv/bin/python -m pytest tests/e2e/test_browser_runtime.py -k analysis_stability_workflow
DATAVIZ_BROWSER=firefox .venv/bin/python -m pytest tests/e2e/test_browser_runtime.py -k analysis_stability_workflow
DATAVIZ_BROWSER=webkit .venv/bin/python -m pytest tests/e2e/test_browser_runtime.py -k analysis_stability_workflow
```

Failures retain bounded console errors, slow/pending request timing, document
readiness and Control initialization phase in the captured output. A timeout
followed by a passing retry is not proof that its cause was fixed; keep both
results in the release record. This targeted matrix does not replace the full
browser suite or an installation smoke test.
