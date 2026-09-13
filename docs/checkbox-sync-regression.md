# Checkbox snapshot / activation race (2026-09-13)

## First failure and diagnosis

The full Firefox run failed
`test_selection_cascade_popovers_view_isolation_and_table_wheel`: the final
Guangdong click completed in Playwright, but Guangdong remained unselected.
The downstream city list correctly contained only the two Fujian cities,
instead of the expected four. This was not evidence of slow city loading.

Original evidence is retained locally under
`.test-evidence/user-full-20260913-browsers/`, including the Firefox trace at
`failures/firefox/0080ef390ae4417e/0-trace.zip`.
A single instrumented rerun passed; that did not resolve the first failure.

A deterministic component probe then invoked the production
`select._syncChoiceControl()` between pointer down/up and between Space
keydown/up. Both failed on the unfixed implementation in Firefox:
`.test-evidence/checkbox-sync-before.log` (2 failed).
The original trace does not identify the precise intervening snapshot; this
probe establishes a real race matching its lost-activation symptom.

## Fix and regression boundary

Checkbox group sync previously replaced every button, even with unchanged
options and values. Removing the pressed/focused node interrupts activation.
Sync now reconciles buttons by option value, preserving unchanged button and
label nodes. Selection handlers still resolve the current native option, so
replacing native options does not leave captured, detached option state.

No DSL, styling, host scheduling, timeout or retry policy changed. The
Impeccable hardening guidance is applied to concurrent interaction and focus
continuity, not a visual redesign.

`tests/e2e/components/test_checkbox_sync.py` covers pointer and keyboard
activation across sync, option replacement/reordering/removal, updated labels,
selection limits, required selection and disabled state. It uses real component
assets without a server or arbitrary waits. The original end-to-end regression
remains intact.

## Bounded verification

- Three-browser component suite: 15 passed per engine, including both new
  activation cases (`.test-evidence/20260913T021354268570Z/`).
- After adding the option/constraint case, targeted checkbox tests: 4 passed
  per engine (`.test-evidence/20260913T021534433485Z/`).
- Original failing E2E: 1 passed per engine
  (`.test-evidence/20260913T021425597670Z/`).
- Non-browser runtime, declarative and authoring checks: 156 passed,
  recorded in `.test-evidence/checkbox-sync-contracts.log`.

These are scoped post-fix results, not a claim that the full matrix was rerun
on the modified product. No package or version change is part of this fix.
