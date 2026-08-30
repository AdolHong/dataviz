# TanStack Table Runtime

Dataviz bundles the framework-agnostic TanStack Table Core so Server pages and
portable HTML use one deterministic Table Runtime without React or a CDN.

- `@tanstack/table-core`: 9.2.4
- `@tanstack/store`: 0.11.1 (transitive Runtime dependency)
- bundle tool: esbuild 0.28.2
- source entry: `tools/tanstack_table_runtime_entry.js`
- upstream: <https://github.com/TanStack/table>

To refresh the vendored bundle, install those exact npm versions in a temporary
directory, bundle the source entry as a minified browser IIFE, then run
`python tools/build_tanstack_table_runtime.py`.

The upstream packages are distributed under the MIT License. Their notices are
kept beside the bundle.
