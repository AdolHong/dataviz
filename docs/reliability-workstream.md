# Reliability and authoring experience workstream

Scope: improve existing contracts and verification without adding DSL, changing
the package version, or publishing a release. Local acceptance is recorded below;
remote CI results are not implied.

## Acceptance and evidence

| Review requirement | Implementation and executable evidence |
| --- | --- |
| Executable CI commands | Corrected `components check`; `test_quality_workflow.py` invokes the actual CLI, not a string-only assertion. |
| Gate distribution publication | Distribution job needs Python contracts, macOS installation, JS syntax and the three-engine browser matrix. CLI-owned Chromium is installed alongside the matrix engine. Workflow tests verify prerequisites and manifest ordering after installation checks. |
| Bind packages to source and tests | `release_evidence.py` records source revision, CI run, successful gates and archive SHA-256 hashes. Tests reject failed/cancelled/skipped gates and missing formats; changing bytes changes the recorded hash. This is provenance, not a cryptographic signature. |
| Keep actionable browser evidence | Opt-in runtime fixture retains screenshots/trace on setup or call failure, discards successful traces; bounded metadata timeline and request diagnostics avoid business text. CI retains failure artifacts seven days. |
| Test evidence collection itself | `test_failure_artifacts.py` starts a real nested pytest process with intentional setup/call failures and success. It checks valid trace ZIPs, PNGs and no success artifacts; a second test verifies the 60-event timeline bound and omission of business text. Both pass in Chromium, Firefox and WebKit. |
| State-transition regressions | The journeys profile selects initialization, late navigation, focus/shortcuts, reload, save versus refresh and sibling-page cases. Fifteen Chromium cases passed; the scenario map below identifies assertions, not merely page loads. |
| Discoverable View diagnosis | Author-mode View signal → Copy diagnosis now uses current status instead of unconditional ready; absent evidence is unknown. Reports include input sizes, revisions, Control intent/domain, changed references and render timing without raw values/errors. Unit tests cover error/waiting/ready/cancelled, stale failure evidence, actual explicit intent and privacy bounds. A real Inspector copy test passes. |
| Current, executable authoring guidance | Reconciled DESIGN.md, design-language and product-architecture descriptions of current Parameters/Controls labels, W/E, side-panel defaults and Header-only Run. Existing authoring tests validate documentation examples against schemas and execute minimal/interactive/custom-renderer scaffolds through validation, execution and HTML reporting. Documentation/search tests exercise CLI routes. |
| Explicit verification scope | check_quality.py offers targeted/journeys/full, prints exact commands, requires a targeted area and never retries or releases. Profile tests perform real pytest collection and prohibit reduced full selectors. |

## State-transition scenario map

Tests live in `tests/e2e/test_browser_runtime.py` (names below omit `test_`).

- `server_compute_waits_for_required_control_domain`: delayed/empty candidate
  domains, no premature required-empty compute, recovery when ready.
- `navigation_supersedes_slow_page_and_lookup_requests`: change target while
  old work is pending; late responses must not replace the selected page.
- `query_reload_restores_visible_date_range_and_single_select`: restore submitted
  query values both during execution and after completion.
- `operation_panel_shortcuts_and_responsive_state`: focus in shell/canvas,
  editable protection, repeated toggle and unavailable controls.
- `server_action_updates_canvas_in_place_and_preserves_query_draft`: successful
  write with failed refresh, refresh-only retry, queued independent submissions,
  preserved query draft and no unnecessary sales query.
- `shared_action_marks_sibling_page_without_querying`: bounded cross-page
  invalidation without querying the inactive page.
- `analysis_stability_workflow`: repeated integrated selection/analysis paths.
- `portable_query_tray_uses_shared_sidebar_for_clicks_and_shortcuts`: exported
  read-only query evidence; Header clicks and W/E share the same sidebar,
  with switching, Escape, narrow-screen focus and no Run/Share actions.

## Developer entry points

Run from the repository using its development interpreter:

```sh
.venv/bin/python scripts/check_quality.py targeted --area docs
.venv/bin/python scripts/check_quality.py targeted --area actions
.venv/bin/python scripts/check_quality.py journeys --browser chromium
.venv/bin/python scripts/check_quality.py full --browser firefox
```

`--dry-run` prints the command list without executing. Targeted profiles select
non-browser modules; journeys selects state transitions. Full runs all
non-browser and E2E tests for the chosen engine; repeat with
chromium/firefox/webkit for a matrix. CLI-owned tests retain their own engine.
No profile builds, publishes, retries failures or upgrades an external system.

## Boundaries

- Runtime failure artifacts are opt-in via `DATAVIZ_E2E_ARTIFACT_DIR`; raw
  Playwright traces and screenshots are **not redacted**. Use synthetic fixtures,
  never customer-data sessions. CLI-owned contexts and failures occurring only
  during final teardown are outside this runtime fixture's automatic capture.
- Default copied View diagnosis excludes business values, titles and raw errors;
  configuration IDs/references remain. Review before sharing. Raw Inspector
  section copies are explicitly outside this safe projection.
- The bounded test timeline samples document/View transitions, not every
  internal event, and is not a production telemetry system.
- Existing optional CDN cache only covers its explicitly pinned Arrow/map
  assets. Other external dependencies can still fail; a local pass does not
  establish offline operation or remote CDN availability.
- Full three-browser suites and clean-install publication are enforced by CI,
  but were not rerun in full locally for this workstream. Local verification is
  the non-browser suite, Chromium core journeys and affected browser tests.
  Remote CI execution and release publication have not been performed.

## Local verification

- Full non-browser suite: 742 passed, 98 E2E cases deselected; one upstream
  Starlette/httpx deprecation warning (not a test failure).
- Chromium core journeys: 15 passed.
- Affected diagnosis/panel/evidence cases: Chromium 5 passed; Firefox and WebKit
  3 passed each. After the final diagnostic correction, Chromium Inspector copy
  passed again. Expanded setup/call artifact probes and bounded timeline:
  2 passed per engine.
- Ruff, JavaScript syntax, generated runtime freshness and diff whitespace
  checks passed. Package remains 0.24.5; no build or release was requested.
