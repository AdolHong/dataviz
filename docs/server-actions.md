# Server Actions — implementation design

Status: available since 0.22.0; save feedback and timing guidance extended in 0.22.1.

## Save feedback and diagnosis

Use `dataviz docs action-save --format json` for the complete standalone SQLite
example: setup, external auth, reading Source, Python Action and a Renderer with
save/progress/refresh recovery. Run the example only in a new isolated directory.

`invoke` and `refresh` share a per-Canvas serial queue (up to 50 waiting requests).
Each payload is copied at invocation; each request retains its own request ID.
`status` bypasses the queue. Queue waiting does not consume the RPC timeout.
`onProgress` first receives `{status: "queued", request_id, position, submitted: false}`;
this is local queue evidence, **not a durable server receipt or proof of saving**.
Position is the initial waiting position, not a live counter. `submitting` marks dispatch,
not confirmed acceptance. Existing receipt progress follows dispatch.
The queue is memory-only: closing/reloading the Canvas discards unsent requests.
The browser requests an unload warning while work remains; do not rely on that warning for durability.
Action refresh can advance queued requests to its new Run, but a different Query Run cannot.
`action_not_submitted` means no write was sent for that invocation; a prior uncertain
write cancels waiting requests rather than retrying them. Check the uncertain request's receipt first.
A failed/superseded page sync also cancels unsent requests: recover the sync before submitting again.
Definitive write failures (such as a revision conflict) do not prevent independent queued requests from running.
No writes are merged, retried automatically, or executed concurrently. Version conflicts
remain the Python handler's responsibility; queued payload revisions are not rewritten.

`onProgress(receipt)` receives the full receipt after dispatch and may repeat. Confirm saving
only when `receipt.status === 'succeeded'`. Even a fast server refresh publishes
success before browser synchronization. `refresh.status === 'ready'` does not
mean browser rendering has completed; `invoke()` also waits for that client work.
Handle saved-but-refresh-failed and superseded outcomes separately. Retry only
refresh with the same request ID; failed/unknown writes do not prove rollback.

Optional receipt `timings` describe preparation, worker startup, user module
loading, Python execution and dispatch-to-outcome in milliseconds. The latter
encloses other stages; do not sum it with them or call Python time database time.
`refresh.timings` exposes scheduling and per-node execution/reuse evidence. A
reused node's old duration is not new execution. Browser responses add transient
`client_timings` for confirmation, preparation and Runtime updates, not exact
network or paint times. These do not enter persistent receipts or business Results.

Compare `/api/workspace` → `server.package_version` with the CLI version; restart
an older server after upgrading. Verify an applied Run, a declared Action and
`context.actions.available`. Static validation does not prove database access.

Authoring discovery is available through `dataviz docs server-actions --format json`
and `dataviz schemas server-action --full --format json`. Documentation search
includes writeback and CRUD terms. The AI Skill routes authors here and separates
permission to develop an Action from permission to invoke real writes.
`dataviz scaffold server-action.python --id save-record` emits a fail-closed
Python starter, not a preconfigured CRUD service. Implement it before invocation.
`dataviz inspect context <workspace> <dashboard> --focus action:<id>` returns the
declared code/helpers, refresh allowlist and logical bindings without resolving
credentials, loading unrelated Sources or executing the Action.

Action definitions, Python and declared helpers participate in hot reload as a
Canvas change, not a query invalidation. Bundles include local code and list the
external resource binding names as unconfigured; external mutable stores,
credentials and private receipts are not copied. Keep mutable stores outside the
Dashboard directory and shared static Asset closure: Bundle still copies those
declared portable files, and trusted Python is not a filesystem sandbox.

Implemented core: dashboard loading and standalone lowering, bounded Python
worker, external resource resolution, durable receipts, success/error redaction,
selective Source execution with applied-Run artifact reuse, and Source cache
epochs shared across sessions. Server API, bounded admission, applied-Run pins,
refresh scheduling/retry and current-Run fences have integration coverage. The
worker executes captured code/dependency bytes, not later edits to live files.
The Renderer bridge now supports `context.actions.available`,
`invoke(action, payload, {requestId, onProgress})`, `status(action, requestId)` and
`refresh(action, requestId)`. Invocation resolves to the write/refresh receipt;
write failure or uncertain transport rejects with `error.requestId` and, when
known, `error.receipt`. A successful write with a client refresh error must be
shown as saved with refresh failed, not as an unsaved checkbox. Refresh retries
use the same request ID and never invoke Python again.

The Shell prepares changed Output transports, checks the current frame and Run,
then synchronously adopts the new Run in Shell and Canvas before publishing the
Output delta through the existing dependency scheduler. Query drafts and
unaffected View instances remain in place. Unchanged hydrated outputs receive
updated transport ownership without being fetched again. Unrelated in-flight
Interactive Transforms are not globally cancelled by an Action refresh.

Targeted JSON/Arrow browser flows passed in Chromium, Firefox and WebKit: in-place
updates, draft preservation, source-to-browser-transform propagation, unchanged
View instances, view-only redraw, client transport failure and refresh retry,
repeated invocations, and unavailable writes in portable HTML. These are targeted
flows, not a claim that the full three-browser suites have run for this feature.

The current Server endpoints are:

- `POST /api/dashboards/{dashboard}/actions/{action}`: JSON `session_id`, `run_id`,
  `request_id`, `payload`. The Run must be the current completed applied Run.
- `GET /api/dashboards/{dashboard}/actions/{action}/{request_id}?session_id=...`:
  read the receipt and refresh progress. This never executes Python.
- `POST /api/dashboards/{dashboard}/actions/{action}/{request_id}/refresh`: JSON
  `session_id`; explicitly retry failed refresh, without repeating Python.

Mutating browser calls require the same Server origin and JSON content type.
Missing Origin is allowed for non-browser clients. This is CSRF protection, not
authentication: the existing trusted/local Server boundary still applies.
Receipts use `Cache-Control: no-store`. Capacity rejection happens before a new
invocation is claimed. A completed receipt remains available after code changes;
reusing its ID with another payload or applied Run is a conflict.

## Why a separate execution boundary

Source and Transform describe reproducible reads and calculations. Their cache,
retry and invalidation behavior is unsuitable for mutations. An Action is an
explicit invocation of trusted dashboard-local Python. Buttons, checkboxes,
forms and Custom Renderers are callers, not owners of persistence semantics.
CRUD, validation and business computation remain Python, not a new SQL/CRUD DSL.

Dashboard `server_actions` contains inline definitions or local YAML paths:

```yaml
server_actions:
  - id: save_annotation
    code: actions/annotations.py
    entrypoint: execute
    resources:
      annotations: annotations_database
    invalidates: [source:annotations, view:details]
```

External definitions use `schema: dataviz/server-action/v1`. Resource values are
Adapter names resolved through the dashboard's bindings and external auth
environment. Only declared aliases are exposed to Action Python. Credentials,
resource paths and executable code never come from a browser payload. Trusted
Python is not sandboxed: declarations constrain platform access, not arbitrary
Python filesystem/network capabilities. Resource configuration is not user
authentication or authorization.

An invocation supplies a JSON object payload and request ID. Python validates
business inputs before writing and returns a JSON result. The platform does not
invent an annotation-specific schema. Python owns transactions: there is no
promise of an atomic transaction across a database, files and external services.

## Author-owned transaction example

For example, an existing SQL table `records(id, value, revision)` can be updated
optimistically. Declare `resources: {store: records_database}` and
`invalidates: [source:records]` in the Action; configure `records_database` as a
SQLAlchemy Adapter in external auth. Table creation/migration is a separate,
explicit operation. This is ordinary author Python, not a built-in record model:

```python
from sqlalchemy import create_engine, text


def execute(context):
    payload = context.payload
    record_id = payload.get("id")
    value = payload.get("value")
    revision = payload.get("expected_revision")
    if not isinstance(record_id, str) or not record_id or len(record_id) > 128:
        raise ValueError("A bounded business record ID is required")
    if not isinstance(value, str) or len(value) > 1000:
        raise ValueError("value must be text of at most 1000 characters")
    if type(revision) is not int or revision < 0:
        raise ValueError("expected_revision must be a non-negative integer")
    engine = create_engine(context.resources.config("store")["url"])
    try:
        with engine.begin() as connection:
            updated = connection.execute(text(
                "UPDATE records SET value=:value, revision=revision+1 "
                "WHERE id=:id AND revision=:revision"
            ), {"id": record_id, "value": value, "revision": revision})
            if updated.rowcount != 1:
                raise ValueError("Record missing or changed; read its latest revision")
    finally:
        engine.dispose()
    context.invalidate("source:records")
    return {"saved": True, "id": record_id, "revision": revision + 1}
```

Inserts, deletes, reads and richer calculations use the same context. For files,
resolve a declared root with `context.resources.path("files", "records.json")`;
the Python author owns locking, conflict checks and atomic replacement. Do not
accept a free-form server path from the payload. A database transaction does not
make a subsequent file write or Result refresh part of the same transaction.
If a file Adapter omits `root`, the ordinary Adapter configuration base applies
(including external standalone auth), not the worker's current directory. The
resolver snapshots that absolute root before dispatch; the worker rejects an
unresolved root instead of guessing a path.

## CLI invocation and recovery

The CLI is a client of the same Server API, not a second execution engine. It
requires an existing current, completed **Server Run ID**, not a stored Result ID.
It does not query a database to create an implicit Run for an Action.

```bash
dataviz actions invoke <dashboard> <action> --server http://127.0.0.1:8080 --session-id <session> --run-id <run> --request-id <request> --payload-file payload.json
dataviz actions status <dashboard> <action> --server http://127.0.0.1:8080 --session-id <session> --request-id <request>
dataviz actions refresh <dashboard> <action> --server http://127.0.0.1:8080 --session-id <session> --request-id <request>
```

`--payload` accepts an inline JSON object instead of `--payload-file`. Keep the
request ID when recovering from uncertainty. Each command makes one request,
without redirects, ambient proxies, polling or automatic retries. `--timeout`
limits the client's HTTP wait; it does not cancel server-side writes. The JSON
receipt separates Action `status` and `refresh.status`; `running` requires a
later status check. Failed/unknown writes or failed refresh return a nonzero exit
code while preserving the received receipt. A failed refresh does not erase a
successful write. After code changes, refresh may require a new explicit query;
never treat that as permission to repeat the write.

## Writes and outcomes

Persist a receipt before dispatch. Same request ID and same invocation returns
the existing receipt; reuse with different input is rejected. Never automatically
rerun Python after timeout, disconnect, restart or refresh failure. A timeout or
lost worker is an indeterminate outcome, not proof that no write occurred.
Receipt identity includes dashboard, action and invocation context. Store receipt
metadata separately from immutable Results; do not retain credentials in it.

Mutable files and databases are explicitly externally bound. In particular they
must not live in a standalone dashboard's content-addressed generated snapshot.
Bundles copy Action code and declarations, not credentials or mutable stores.
Portable HTML is read-only and exposes unavailability, not a live write endpoint.

## Invalidation and selective refresh

`invalidates` is the maximum allowed effect set, validated against the loaded
dashboard before execution. Python requests a subset through
`context.invalidate("source:annotations")`. An undeclared effect is an error.
Effects are scheduled only after successful Action completion. A Python failure
may follow a committed write, so failure feedback must not imply rollback.

- `source:<id>` reruns that Source and its downstream dependency closure. Reuse
  unaffected outputs from the applied Result, not a fresh query of unrelated
  Sources. Create a new Query Run with immutable Base Outputs; never modify the
  old Run or an already sealed Result. Public Result sealing remains an explicit
  sharing/export operation, as with ordinary Server queries.
- `view:<id>` requests a redraw with current inputs. It does not implicitly query
  every upstream Source. Authors request Source invalidation explicitly when data
  changed.
- Refresh uses the applied query state, not edited but unsubmitted parameters.
- An Action completed for an old Run cannot replace a newer query's Run. Check
  dashboard revision and current Run identity before scheduling and publishing.
- Invalidate affected cache identities so a later ordinary Run cannot return
  pre-write cached data. Unrelated caches stay valid.
- Report Action outcome and refresh outcome independently. Refresh can be retried
  without executing Python again. A failed refresh after a successful write is
  displayed as “saved; refresh failed”.

## Acceptance gates

1. Validate local code, unique IDs, resource declarations and effect references
   without executing Python or opening a writable database.
2. Python can perform database/file create, read, update and delete using external
   bindings. Undeclared aliases and escaping file paths fail clearly.
3. Explicit invocation, payload JSON validation, bounded execution, receipts,
   duplicate submission, crash/timeout uncertainty and redacted failures.
4. Refresh Source A and dependants while Source B is not executed; old Run
   artifacts remain readable and unchanged; subsequent cache lookup respects invalidation.
5. View-only invalidation does not query; stale Action/refresh cannot overwrite a
   newer Run; refresh failure cannot cause duplicate writes.
6. Renderer bridge, server API and CLI share execution semantics. Static HTML
   cannot invoke Actions. Standalone, auth, Bundle and reload cover Action code.
7. Documentation, Schema discovery, scaffold and skill reflect implemented APIs;
   server/worker, browser interaction and concurrency regression tests pass.

## Acceptance evidence

Verified on 2026-09-08 against the working tree:

| Gate | Executable evidence |
| --- | --- |
| 1 | `test_server_actions.py`: strict definition/payload checks, duplicate IDs, unknown refresh references and standalone loading without Python execution |
| 2 | Real SQLite and file CRUD tests, external aliases/root checks, and the documented transaction example with stale-revision rollback |
| 3 | Atomic concurrent receipt claim, restart/timeout no-replay, captured code/helpers, result/error secret redaction; CLI transport never retries |
| 4 | Selective Source + Dataset refresh with unchanged sales branch, old Run/artifact checks, cross-session cache epochs |
| 5 | `test_server_action_api.py`: view-only redraw, failed refresh retry without another write, newer-query fences and refresh CAS race tests |
| 6 | CLI against the real Server service, Renderer JSON/Arrow flows, standalone lowering, Bundle binding/code closure and watcher/helper change tests |
| 7 | Documentation search, Schema discovery, scaffold model validation/fail-closed starter and focused Action context tests; AI Skill routes to the current contract |

The final non-browser suite passed **676 tests** (77 e2e tests excluded from that
command). Chromium, Firefox and WebKit each passed the **two Action JSON/Arrow
flows**, including draft preservation, partial refresh, transport failure/retry,
repeated writes and portable read-only behavior. These six checks are not the
full browser matrix. Runtime generated-source consistency, Ruff and diff checks
passed. No package version bump, release build or installation smoke was performed
for this work. The existing Starlette/httpx deprecation warning remains.

Resource-root follow-up: six regression cases reproduced and then verified the
omitted-root fix across standalone auth file/directory/Workspace bindings, real
file CRUD, traversal rejection and worker rejection of unresolved roots. The
non-browser suite subsequently passed **682 tests** (77 e2e excluded). Browsers
and release packaging were not rerun for this backend-only correction.
