# Browser test resources

## One command

```sh
.venv/bin/python scripts/test_browsers.py --fetch-assets
```

This verifies/downloads the pinned real resources once, then runs the complete
suite in isolated Chromium, Firefox and WebKit processes (three in parallel;
use `--jobs 1` for serial diagnosis). It does not install browsers;
install those once with `.venv/bin/python -m playwright install chromium firefox webkit`.
Each run gets its own `.test-evidence/<timestamp>/` directory, per-browser logs,
failure traces and a `summary.json`. A failed browser does not prevent the other
two from running, and any failure makes the command exit nonzero. No automatic
retry hides the first result. Reusing an existing evidence log is refused.
CI uses the same entry point per matrix engine, with the resource cache keyed by
the manifest hash. A cache hit still verifies each file's SHA-256 before testing.

For a targeted diagnostic (not a full release gate):

```sh
.venv/bin/python scripts/test_browsers.py --browsers webkit -- -k plotly_area_selection_gesture
```

After the first download, omit `--fetch-assets` to require the verified cache.
The authoritative exact URLs, MIME types and SHA-256 values are in `assets.json`.
It includes Perspective 5.4.0's actual viewer, engine WASM, Worker, datagrid and
chart modules; no Perspective renderer is replaced by a mock. Updates must
review upstream bytes and update the manifest, not disable hash verification.

## Failure artifacts

For synthetic fixtures, set `DATAVIZ_E2E_ARTIFACT_DIR=/tmp/dataviz-evidence`.
Runtime browser tests then retain a Playwright trace and viewport screenshot on
test failure, grouped by browser and a hash of the test identity. Passing tests
discard the trace. CI uploads failures with a seven-day retention period.
Open a trace with `playwright show-trace /path/to/0-trace.zip`.

**Raw traces and screenshots can contain DOM, network payloads and business
values.** This is opt-in locally and intended only for synthetic test fixtures,
not arbitrary customer dashboards. The bounded console diagnosis is separate;
raw artifacts are not claimed to be redacted. CLI-owned browser contexts do not
currently use the Runtime page fixture and therefore are not covered by this
artifact lifecycle. The self-test deliberately fails a nested pytest run and
checks that only the failed test retains a valid trace and PNG.

`test_browser_runtime.py` automatically reuses `dataviz-tool/.browser-test-assets/`
when present. This directory is git-ignored and is not part of the package.
`DATAVIZ_E2E_ASSET_DIR` can select another cache directory.

The cache contains real upstream resources, not decoder or renderer mocks:

| File | Source | SHA-256 |
| --- | --- | --- |
| `Arrow.es2015.min.js` | `https://cdn.jsdelivr.net/npm/apache-arrow@21.1.0/Arrow.es2015.min.js` | `d3f0ded2a2bdd1208232b942f8e4810f7a402564fac3c78b4574158cd542acb9` |
| `world_110m.json` | `https://cdn.plot.ly/un/world_110m.json` | `e1bf51740ad28396265e52123ea7315d692f112664ab2cb0f1ea76a96fe1bb0a` |

The table above lists the original two cache resources; `assets.json` additionally
pins Perspective's complete runtime resource set. Use the command above to
prepare all files. The shared fixture validates hashes and fulfills only exact
manifest URLs. An incomplete or mismatched cache fails explicitly;
without a cache directory, the original network behavior remains unchanged.
Plotly's map URL is not versioned: review changes before updating its checksum.

This isolates repeated CDN latency and resulting layout movement from interaction
tests. It does not promise the whole suite is offline, validate CDN availability,
or change production defaults. To diagnose production network loading separately,
run direct pytest without a cache directory; do not mistake that external-network
check for the reproducible interaction release gate.
The shared fixture also injects these exact resources into in-process CLI-owned
browser pages, including offline analysis runs. Other URLs retain their network
policy; this does not test CDN availability. Subprocess-owned browsers retain
their normal resource loading behavior. Report cached-resource usage with results.

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
