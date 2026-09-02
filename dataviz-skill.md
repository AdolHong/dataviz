---
name: dataviz
description: Build, inspect, analyze, validate, run, and maintain Dataviz dashboards and reusable data contracts. Use for Dataviz Workspace authoring, analytical view design, Catalog reuse, immutable Result analysis, or long-term Dashboard maintenance; do not use for unrelated generic charting tasks.
---

# Dataviz

Use Dataviz to turn explicit data contracts into reusable analysis, trustworthy Dashboards, immutable Results, and reviewable Evidence. Optimize first for correct analytical meaning and low-friction reuse; visual polish comes after the data contract is proven.

## Choose the work mode

Route the task before loading documentation:

| User intent | Start here | Primary outcome |
| --- | --- | --- |
| Create a Dashboard | `dataviz docs quickstart` | A minimal validated Dashboard |
| Modify an existing Dashboard | `dataviz tree <workspace>` + focused `dataviz inspect context` | A scoped change without unrelated rewrites |
| Find and analyze existing data | `dataviz docs analysis-quickstart` + `dataviz catalog search` | Reuse an existing canonical Target |
| Read an earlier execution | `dataviz result inspect <workspace> <result-id>` | Inspect the immutable Result without rerunning |
| Maintain a Workspace | `dataviz docs maintenance` | Stable semantics, validated contracts, controlled cleanup |

Do not load the entire Runtime architecture by default. Do not create a new Source or calculation until Catalog exploration shows that an appropriate reusable Output does not already exist.

## Operating principles

- Treat the installed CLI, generated schemas, and Component Registry as the current source of truth. Do not recall fields or commands from an older Dataviz release.
- Prefer semantic reuse over duplicated business definitions: discover an existing Output, understand its contract, then run it. Keep ordinary business SQL Dashboard-local; share only stable static Workspace Assets and genuinely common Parameter Domains.
- Prove `Source → Named Output` before spending time on chart options, CSS, or custom rendering.
- Keep query logic, interactive computation, rendering, and presentation in their respective layers.
- Run an expensive computation once. Use its immutable `result_id` for inspection, pagination, export, report generation, and Evidence.
- Use canonical Target References. Never invent removed aliases such as `src_*`, `base_*`, `drv_*`, or `view_*`.
- Preserve stable IDs and Output names. They are public coordinates used by Catalog, Result, Evidence, and downstream Dashboards.
- Never place credentials in a Dashboard. Adapters and secrets belong to Workspace configuration and its external secret boundary.

## Read documentation progressively

Use the smallest route that can answer the current question.

### New Dashboard

Start with the minimal closure:

```bash
dataviz docs --task minimal --format json
```

It exposes only the ordinary `Adapter → Source → View → Layout` path. Escalate only when the requirement proves it is necessary:

```bash
dataviz docs --task interactive --format json
dataviz docs --task custom-renderer --format json
dataviz docs --task cascading-selection --format json
dataviz docs --task view-filter --format json
dataviz docs --task browser-compute --format json
dataviz docs --task map-view --format json
dataviz docs --task entity-select --format json
```

- Use `interactive` only when a post-query Control must filter inputs, provide a calculation value, or produce a Derived Output.
- Use `dataviz docs query-parameters --format json` for query-time SQL-backed choices or Parameter Domain cascades. The `cascading-selection` task is specifically for post-query Control candidate cascades over an already loaded Base Output.
- Use `custom-renderer` only when built-in Views plus Plotly trace/layout/config overrides cannot express the required behavior.
- Use `map-view` for native longitude/latitude points or values joined to an allowlisted local GeoJSON Asset; do not begin with Custom Renderer code.
- Use `entity-select` for a searchable large Query Parameter catalog; it scaffolds existing Domain/select/filter contracts and does not create an Entity Runtime.
- When a component is already known, route directly with `dataviz docs --component <component-id> --format json`.

### Existing Dashboard

Read the real compiled dependency closure rather than the whole repository:

```bash
dataviz tree <workspace>
dataviz inspect context <workspace> <dashboard> --focus view:<id> --format json
dataviz inspect dependencies <workspace> <dashboard> --format json
dataviz inspect layout <workspace> <dashboard> --format json
dataviz inspect query <workspace> <dashboard> --source <source-id> --query-param key=value --format json
```

Use `dataviz schemas <schema> --full --format json` only when exact fields are needed. Use `dataviz components list` to discover components, `dataviz components show <component-id> --format json` for one contract, and `dataviz components check --format json` to validate installed packages. Use `dataviz scaffold <recipe> --format json` for a small current-schema example instead of copying an old Dashboard.

Use `inspect query` before running when the question is how canonical Query Parameter state becomes `query_filter` predicates and bound values. It is an explanation only: `executed: false` means row counts, cache hits, timings, and failures remain Result/Execution evidence. Use `dataviz docs --search '<term>'` or `dataviz docs troubleshooting` when a diagnostic or Runtime boundary is unclear. Read architecture documents only when changing the Runtime itself.

## Quick start: build a Dashboard

For a new runnable Workspace with a built-in `hello` Dashboard:

```bash
dataviz init <workspace>
dataviz tree <workspace>
```

When the task already has a chosen Dashboard ID or needs a focused recipe, choose one current recipe from `dataviz scaffold --list --format json`, then run `dataviz scaffold <recipe> ...`.

Build in this order:

1. Define the business question and Output semantics.
2. Configure the Workspace Adapter without embedding credentials in the Dashboard.
3. Implement the Source and declare stable typed Outputs.
4. Add a Server Dataset Transform only when reusable query-time processing is required.
5. Point a built-in View at a proven Named Output.
6. Add Query Parameters only for values that must create a new immutable query result.
7. Add Controls and Interactive Transforms only for post-query exploration or computation.
8. Add Presentation overrides and custom CSS after behavior is correct.
9. Use a Custom Renderer only after the built-in View and native Plotly paths are insufficient.

Use a tight verification loop:

```bash
dataviz validate <workspace> --dashboard <dashboard-id> --format json
dataviz run <workspace> <dashboard-id>
dataviz result inspect <workspace> <result-id>
dataviz report <workspace> <result-id> --output report.html
dataviz visual-check <workspace> <dashboard-id> --target both
dataviz serve <workspace> --port 8080
```

`validate` is the zero-query static gate and should run after every meaningful change. Run real data only after static validation passes.

## Analysis design: think before choosing a chart

Before editing a View, answer these questions:

1. What judgment or decision must the user make?
2. What are the metric definition, row grain, denominator, and time range?
3. What is the comparison: history, target, peers, cohort, or another baseline?
4. Does the analysis need total, composition, distribution, relationship, anomaly, or uncertainty?
5. Is a chart genuinely better than a Table or Metric?
6. Only then, which Plotly encoding and interaction best communicate the answer?

Form a compact analysis brief before implementation:

```yaml
decision: What decision should this view support?
metric: Exact measure and unit
grain: What one row or mark represents
denominator: Required when the metric is a rate or share
time_range: Included dates, calendar, and timezone
comparison: History, target, peer, cohort, or baseline
analytical_lens: total | composition | distribution | relationship | anomaly | uncertainty
medium: metric | table | chart
reason: Why this medium answers the question with the least ambiguity
```

Infer obvious facts from existing contracts. Ask the user only when a missing answer would materially change the metric, comparison, or decision; do not turn the six questions into a ritual questionnaire.

### Choose the analytical medium

- Use **Metric** for one current value when status, target delta, or change is the main message.
- Use **Table** for exact lookup, ranking, audit, reconciliation, many dimensions, or when users need sorting, search, pagination, and row-level detail.
- Use **Perspective** only when the end user needs to change grouping, aggregation, pivot, or analytical dimensions at runtime.
- Use **Chart** when position, shape, trend, distribution, relationship, flow, or uncertainty makes the pattern materially easier to understand.

Prefer these analytical mappings:

| Question | Default expression |
| --- | --- |
| Which category is larger or ranks higher? | Bar; horizontal when labels are long |
| How does a measure change over ordered time? | Line |
| How do total and components change together? | Stacked bar or stacked area |
| What does one variable's distribution look like? | Histogram |
| How do distributions differ across groups? | Boxplot |
| Are two measures related or are there outliers? | Scatter; size may encode a third measure |
| Which two-dimensional combinations are high or low? | Heatmap |
| Why did a value change from A to B? | Waterfall |
| Where does a staged process lose users or volume? | Funnel |
| Where does quantity flow? | Sankey |
| Which parts dominate a hierarchy? | Treemap; use tree/sunburst when hierarchy itself matters |
| Where is a geographic pattern meaningful? | Map, only when location is part of the analytical question |
| What range or forecast uncertainty should be expected? | Line with interval/confidence band |

Use pie/donut only for a small, stable set of categories where rough part-to-whole comparison is sufficient. Avoid a map merely because a location field exists, a gauge when a Metric plus target delta is clearer, radar for precise comparison, dual axes without a defensible shared reading, 3D decoration, and rainbow palettes without semantic meaning.

After the analytical choice:

1. Start with a built-in declarative Plotly View when it represents the question.
2. Use declarative Plotly `options.trace`, `options.layout`, and View `config` for richer encodings and interactions.
3. Use `context.charts.plotly` in a Custom Renderer only for functions, imperative events, or lifecycle behavior that cannot remain declarative.
4. Use the official Plotly Gallery and source examples as implementation references, not as the ontology for choosing a chart.

Keep one Section focused on one analytical question. Titles should name the subject; descriptions should explain the metric, comparison, or how to read the result—not repeat implementation IDs.

### Native geographic analysis

Use a map only when geographic position or region shape changes the judgment. Prefer Bar or Table for precise regional ranking.

Start with `dataviz docs --task map-view --format json`, then read `dataviz docs maps --format json` for point, GeoJSON region, `layers`, viewport, Asset, and Overview → Detail contracts. Use one Map View with explicit `layers` when region boundaries and point locations must share a viewport; each Layer owns its input and optional Control binding, while the View keeps one Plotly lifecycle and one ControlRuntime. Keep the overview independent of detail filters. When one gesture must update several Controls, use the documented compound writer action; do not emulate an atomic selection with callback chains or sequential writes.

When a national GeoJSON is too large but the result covers only a few regions, clip it in a server Python Dataset Transform and emit the reduced geography as a Named Output. Normalize administrative codes, handle municipalities, Polygon/MultiPolygon, invalid geometry, and derive the viewport from the reduced feature/point set. This is ordinary Transform code, not a reason to add GIS DSL.

## Reuse existing Dashboard knowledge

Use the physical tree for project navigation and Catalog for semantic discovery:

```bash
dataviz tree <workspace>
dataviz catalog list <workspace>
dataviz catalog search <workspace> '收入|销售|日期' --top 10
```

Catalog search is grep-like regular expression search. Search business synonyms when vocabulary is uncertain, then describe promising targets before execution:

```bash
dataviz catalog describe <workspace> \
  '<dashboard>::source:<source-id>/<output>' \
  '<dashboard>::interactive:<transform-id>/<output>' \
  --format json
```

Evaluate more than the title:

- `purpose`: which question the Output answers;
- `grain`: what one row represents;
- metric units, aggregation, denominator, and time meaning;
- Query Parameters and Controls required to run it;
- lineage and downstream View consumers;
- caveats, visibility, assurance status, owner, review date, and evidence.

A Catalog hit is not automatically trustworthy. Prefer reviewed or certified public Outputs when their semantics match. Do not reuse an Output with incompatible grain or denominator merely because field names look similar.

Use the returned canonical Target Reference verbatim. Supported forms are:

```text
<dashboard-id>
<dashboard-id>::source:<source-id>
<dashboard-id>::source:<source-id>/<output-name>
<dashboard-id>::dataset:<transform-id>/<output-name>
<dashboard-id>::interactive:<transform-id>/<output-name>
<dashboard-id>::view:<view-id>
```

If no suitable Output exists, create one with reusable semantics rather than hiding the new definition inside a View. Public Outputs should at least explain `title`, `purpose`, and `grain`; add caveats, assurance, measures, time meaning, and relationships where relevant.

## Run data once and reuse the Result

Describe a Target before running when its invocation contract is not already known:

```bash
dataviz catalog describe <workspace> '<target-reference>' --format json
dataviz run <workspace> '<target-reference>' \
  --query-param region=华东 \
  --control dashboard:<dashboard-id>/<control-id>=1.2
```

Use `--also '<target-reference>'` to seal compatible additional Outputs in the same execution. Let `--runtime auto` select the declared Runtime unless debugging a specific Runtime boundary. Use `--allow-network` only when the target explicitly requires external browser access.

To debug a Dataset Transform without querying its upstream Source again, run the same canonical Transform Target with `--from-result <result-id>`. Dataviz accepts only the Transform's declared direct inputs when reference, kind, Schema, and stored Artifact hash remain compatible; mismatch fails and never falls back to the database. This creates a new immutable Result and leaves the input Result unchanged. Do not use it for Dashboard or Interactive targets.

The terminal preview is not the stored result size. `run` executes the full reachable DAG, seals the complete native Artifacts, and returns a `result_id`; `--preview-rows` changes only stdout. Do not rerun just to see more rows.

Read the sealed Result instead:

```bash
dataviz result inspect <workspace> <result-id> --detail full
dataviz result show <workspace> <result-id> '<output-reference>' --offset 0 --limit 100
dataviz result export <workspace> <result-id> '<output-reference>' --to <destination>
dataviz report <workspace> <result-id> --output report.html
```

- `result show` paginates without executing the Dashboard again.
- `result inspect` exposes lineage, parameters, Controls, per-consumer effective/applied revisions, hashes, timings, storage, and provenance progressively. A stale manual/apply consumer means the sealed Output used an older Control revision; do not describe it as if it consumed the latest value.
- `result export` copies one selected native Artifact; it does not convert formats or mutate the Result.
- A directly read File Source may be represented by an immutable path/hash receipt instead of a redundant copy.

Use an Analysis Overlay only for an explicitly temporary experiment that substitutes SQL, Python/JavaScript code, or a compatible File input without changing the real Dashboard. Validate the Overlay with `dataviz run ... --overlay <file> --dry-run`; do not treat Overlay execution as a remote security sandbox.

## Maintain Dashboards for long-term reuse

### Preserve semantic quality

- Give every reusable Output a meaningful title, purpose, and grain. Do not merely repeat its technical ID.
- Keep rate denominators, currency/unit, aggregation, timezone/calendar, exclusions, and caveats explicit.
- Project public SQL fields explicitly; avoid `SELECT *` so upstream schema drift cannot silently change the contract.
- Deprecate a semantic contract with a reason and replacement instead of silently changing its meaning.
- Record reviewed conclusions as Evidence; Evidence preserves the Result's consumer revision audit. Use `evidence promote --dry-run` to generate a reviewable patch rather than mutating production definitions implicitly.

### Preserve architectural boundaries

- Query Parameters change query identity; Controls own post-query typed state. Each View or Interactive Transform declares whether it consumes that state as a filter or a value. Do not substitute one lifecycle for the other merely for UI convenience.
- SQL-backed Query Parameter choices belong to Parameter Domains, not Sources or Interactive Transforms. Candidate discovery is optional for AI: known values may be passed directly as canonical Query Parameter state without loading the UI catalog.
- Candidate-backed `multiple_select` uses `all/include/exclude/none`; compact states never expand the full candidate relation. Prefer Source `query_filters` and explicitly choose whether an empty selection passes through or matches no rows. Read `dataviz docs query-parameters --format json` before implementing SQL-backed choices, cascades, Revert, or large entity lookup.
- Treat page reload and initial Dashboard hydration as compact-state restoration, not as a new parent edit. URL/tab/committed `include` or `exclude` operands must survive while Lookup restores labels; values absent from the latest generation remain unavailable instead of being silently removed.
- When debugging Query Parameters in Server, enable the Query Card `{ }` author projection to see selection mode, operand counts, available/unavailable counts, dependencies, and the latest deterministic reconciliation. It is read-only and does not replace `inspect query` or Result evidence.
- Keep ordinary SQL and files Dashboard-local. Share only genuinely common Parameter Domains and stable Workspace Assets. Read `dataviz docs workspace-assets --format json` before registering shared files or creating a Bundle; never use parent traversal or absolute local paths as a portability shortcut.
- Sources are the only external data entry. Server Dataset Transforms create Base Outputs; Interactive Transforms create Derived Outputs.
- Browser Interactive Transform code reads only YAML-declared aliases: `context.inputs.<alias>`, `context.query_inputs.<alias>`, and `context.control_inputs.<alias>`. `mode: filter` is applied before execution; `mode: value` appears in `control_inputs`. Never use the removed `context.selections` API.
- Renderers consume Named Outputs and View descriptors. Do not put SQL, model inference, or reusable business calculations in Presentation JavaScript.
- A Custom View declares its primary `input` and may add named `inputs` aliases; read them as `descriptor.inputs.main` and `descriptor.inputs.<alias>`. Keep geography, stores, summaries, and other relations separate; do not concatenate unrelated tables with a synthetic `row_kind` merely to pass them to one Renderer. `descriptor.rows` is only the primary-input shortcut.
- During Interactive Transform recomputation, an already mounted View may keep its prior content with an `updating` signal. Treat it as visual continuity only: new consumer evidence is committed only after the current generation succeeds. In Server author mode, inspect an Interactive node to see the Control/Input cause, changed Outputs, affected Views, and confirmation that no Query ran.
- Use Plotly as the author chart interface and the default TanStack-based Table for tabular presentation. Do not introduce another chart/table stack casually.
- For declarative Table presentation, reuse `labels`, `formats`, `align`, `widths`, and `wrap`; use `options.emphasis.columns` only to statically emphasize a few important columns. Conditional formatting and custom cells belong to TanStack/Custom Renderer code, not another DSL.
- Keep Dashboard logic in `dashboard.yaml`; keep optional visual overrides in `presentation.yaml` and narrowly scoped assets.

### Change one layer at a time

When debugging, progress in this order:

1. Source and Query Parameter contract;
2. Base Named Output and Dataset Transform;
3. Controls and Interactive Transform;
4. View field mapping;
5. Layout and Presentation;
6. browser geometry and interaction.

Do not simultaneously rewrite SQL, Transform code, View fields, and CSS. Compare failures against the last proven layer and use stable diagnostic codes.

### Validate behavior and presentation

```bash
dataviz validate <workspace> --dashboard <dashboard> --strict
dataviz inspect dependencies <workspace> <dashboard> --format json
dataviz inspect layout <workspace> <dashboard> --format json
dataviz visual-check <workspace> <dashboard> --target both
```

Check populated, empty, loading, error, stale, cancelled, and unavailable states when applicable. Verify narrow viewports, keyboard focus, overlays, scrolling, Table/Perspective wheel boundaries, Renderer resize/dispose, and parity between Server and portable report output.

`serve` hot reload does not authorize an expensive rerun: query-contract changes mark the current Result outdated and wait for an explicit Run. Preserve that boundary.

### Control stored artifacts

Result, Execution Artifact, shared Parameter Materialization, and cache cleanup is explicit and preview-first:

```bash
dataviz prune <workspace>
dataviz prune <workspace> --keep-results 20 --result-max-age-days 30
dataviz prune <workspace> --all --apply
```

Do not delete `.dataviz` paths manually while executions or readers may be active. External exports and original File Sources are outside prune ownership.

### Upgrade deliberately

Before adopting syntax from another Dashboard or release:

```bash
dataviz version
dataviz docs quickstart
dataviz schemas <schema> --full --format json
dataviz validate <workspace> --strict
```

Dataviz accepts the current strict DSL and does not promise deprecated aliases or automatic migration. Remove stale code and documentation instead of maintaining parallel old/new paths.

## Definition of done

A Dataviz task is complete when:

- the analysis question, metric contract, grain, comparison, and chosen medium agree;
- existing Catalog knowledge was reused or the reason for a new Output is clear;
- static validation passes without hidden query execution;
- the intended Target runs once and produces an inspectable immutable Result;
- the Result data, lineage, and parameters were checked—not only the first preview rows;
- the Dashboard/report renders correctly in the required browsers and viewports;
- business logic remains outside Presentation and Renderer code;
- reusable Output semantics and caveats are discoverable for the next human or AI;
- tests and focused documentation are updated in proportion to the change.

In the final report, state the outcome first, then the changed contracts/files, validation and browser evidence, the produced Result or package artifact when relevant, and any remaining limitation. Do not claim analytical correctness from a successful render alone.
