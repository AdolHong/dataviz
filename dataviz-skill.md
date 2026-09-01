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
| Modify an existing Dashboard | `dataviz tree` + focused `dataviz inspect context` | A scoped change without unrelated rewrites |
| Find and analyze existing data | `dataviz docs analysis-quickstart` + `dataviz catalog` | Reuse an existing canonical Target |
| Read an earlier execution | `dataviz result` | Inspect the immutable Result without rerunning |
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
```

Use `dataviz schemas <schema> --full --format json` only when exact fields are needed. Use `dataviz components list` to discover components, `dataviz components show <component-id> --format json` for one contract, and `dataviz components check --format json` to validate installed packages. Use `dataviz scaffold <recipe> --format json` for a small current-schema example instead of copying an old Dashboard.

Use `dataviz docs --search '<term>'` or `dataviz docs troubleshooting` when a diagnostic or Runtime boundary is unclear. Read architecture documents only when changing the Runtime itself.

## Quick start: build a Dashboard

For a new runnable Workspace with a built-in `hello` Dashboard:

```bash
dataviz init <workspace>
dataviz tree <workspace>
```

When the task already has a chosen Dashboard ID or needs a focused recipe, use `dataviz scaffold minimal|interactive|custom-renderer` instead.

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

```yaml
# Point locations
- id: stores
  template: map
  mark: point
  input: source:stores/main
  longitude: longitude
  latitude: latitude
  label: store_name

# GeoJSON regions; china-city must be registered in workspace.yaml and allowlisted in dashboard.assets
- id: city-sales
  template: map
  mark: region
  input: source:city-sales/main
  geojson: china-city
  data_key: city_code
  feature_key: properties.adcode
  color: revenue
  label: city_name
```

Keep one row per region key before rendering. Point coordinates must be finite; region data keys and GeoJSON feature keys must be unique and joinable. Use `options.trace`, `options.layout`, and `config` for Plotly styling. Read `dataviz docs maps --format json` before using Custom Renderer code.

Native Map viewport follows the rendered coordinate/region-key set: changing the City refits the detail map, while changing only the selected Store preserves the current city view. Do not bind viewport state to the highlight Control or add a callback that manually calls Plotly relayout.

For geographic Overview → Detail, keep the overview unfiltered and use one compound writer action instead of callback chains or sequential Control writes:

```yaml
# Overview: primary Store highlight plus contextual City write.
control_binding:
  control: dashboard.store
  field: store_nbr
  writes:
    - {control: dashboard.city, field: city}

# Detail: filter by City and keep writing only Store.
control_inputs:
  city: {mode: filter, control: dashboard.city, field: city, inputs: [main], empty: match_none}
control_binding: {control: dashboard.store, field: store_nbr}
```

All fields must come from the same selected datum. One gesture is atomic: if any target is invalid, none commit. A multi-row gesture may write a single-value context Control only when every selected row projects the same distinct value. Do not make the overview consume the detail Controls, and do not emulate this transaction with sequential events.

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
- When a Query Parameter needs SQL-backed choices, define one Parameter Domain relation and project stable `value_field` / `label_field` pairs from it. Do not use a normal Source or Interactive Transform to populate Query Parameter options.
- For a large searchable entity catalog, start with `dataviz scaffold query-parameter.entity-select --id <parameter> --format json`. The Recipe composes the existing Parameter Domain, Domain-backed `multiple_select`, search metadata, and Source `query_filters`; it does not introduce a new parameter type.
- SQL Domains are always Server-side Workspace shared materializations. Browser Pickers use Lookup search, generation-bound cursor pagination, and local predicates over one immutable generation; they never receive the raw relation or rerun SQL for each parent edit.
- Reuse an explicit `workspace:/parameter_domains/...` Workspace Parameter Domain when several Dashboards share one candidate catalog. It is not a Workspace Asset. Sharing requires the same definition/code hash, Adapter identity, and visibility scope; never merge unrelated Domains merely because SQL text happens to match.
- Candidate discovery is optional for AI. Use `dataviz parameters prewarm`, `status`, `lookup`, or `refresh` only when candidate exploration is useful. If the value is known, pass canonical Query Parameter state directly to `dataviz run`; Run neither builds nor validates against the UI candidate catalog.
- Candidate-backed `multiple_select` uses `all/include/exclude/none`. `all` and `none` carry no operands; `include` and `exclude` carry only finite operands. Never expand All into every candidate, invent an `ALL` member, or serialize 99,999 included values after excluding one item.
- A Source may consume `selection`, finite `value` operands, `active`, or complete `state`. Prefer `query_filters` plus `{{ dataviz_filter:<name> }}` for ordinary SQL predicates. Declare `empty: passthrough` when an empty `multiple_input` or candidate `multiple_select` `none` means no SQL restriction; use `empty: match_none` when it means zero rows. `all` always compiles to `TRUE`, include/exclude to parameterized `IN/NOT IN`. Never hand-expand either form or invent an `ALL` sentinel.
- For a searchable Item picker whose blank state means “do not filter,” use a Domain-backed `multiple_select` with `default: {mode: none}`, `clearable: true`, and a Source `query_filters` binding with `empty: passthrough`. Lookup remains paged and Server-side; the canonical state stores only finite selected Items. Do not relabel `none` as `all` or add an `item_active` workaround.
- Treat the last successful Query's canonical Query Parameter state as one committed snapshot. Query Panel Revert restores it through the dependency topology without running Query; a committed operand missing from the latest generation remains visible as unavailable because a Domain is not a Source whitelist.
- One materialized relation may project Division, Category, Subcategory, Item, or several independent lists. `depends_on` filters the materialized relation and never triggers a remote SQL query: a `single_select` parent is one inclusive scalar, while a `multiple_select` parent uses `all/include/exclude/none`. Omit `depends_on` when lists should not cascade.
- Use `dataviz bundle <workspace> <dashboard> <destination>` to create a new standalone Workspace snapshot. The destination must be absent or empty; Bundle never imports into, merges with, synchronizes, or overwrites an existing Workspace.
- Bundle copies the referenced shared Domain definition/SQL, Workspace Asset and non-sensitive binding closure, but never unrelated files, `.dataviz` materializations or credentials. The copied resources are private snapshot dependencies and no longer track the source Workspace.
- Keep ordinary SQL and files Dashboard-local by default. Share only stable Workspace Assets and genuinely common Parameter Domains; do not create generic shared Sources, Transforms, Views, or business SQL merely to remove small duplication.
- Keep files used by only one Dashboard inside that Dashboard. When GeoJSON, dictionaries, images, or static data must be shared, register them once under `workspace.yaml: assets`. Registration is private: add an ID to `dashboard.yaml: assets` only when browser code must read it through `context.assets`; a File Source may independently use `path: asset:<id>` with an explicit format.
- Custom Renderers use `await context.assets.json|text|bytes|blob|url(<id>)`. Do not branch on Server versus HTML transport: Server uses a safe ETag URL, while portable HTML inlines the same declared dependency. Read `dataviz docs workspace-assets --format json` before adding a shared file.
- Never use `../../`, absolute Downloads paths, remote URLs, or Parameter Domain as a generic file-sharing workaround. `inspect context` exposes only referenced Asset metadata, and `dataviz bundle` copies only the actual Browser/File Source closure into a fresh snapshot.
- Sources are the only external data entry. Server Dataset Transforms create Base Outputs; Interactive Transforms create Derived Outputs.
- Renderers consume Named Outputs and View descriptors. Do not put SQL, model inference, or reusable business calculations in Presentation JavaScript.
- Use Plotly as the author chart interface and the default TanStack-based Table for tabular presentation. Do not introduce another chart/table stack casually.
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
