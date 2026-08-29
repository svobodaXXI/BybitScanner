---
name: change-review
description: Perform a read-only, defect-focused review of a BybitScanner change before high-risk or material behavioral acceptance; skip trivial documentation, copy, and isolated cosmetic changes.
---

# Change Review

Use this read-only review for material changes involving execution, order lifecycle, submission/cancellation, STOP/TAKE, quantity or working volume, PnL, reconciliation, connectivity or fail-closed behavior, market-data ownership, robot control, persistence/state transitions, security, cross-boundary architecture, concurrency, async lifecycle, or large multi-file behavior. Apply proportional judgment; ordinary typos, copy changes, cosmetic CSS, and tiny deterministic edits usually do not need it.

1. Establish the intended task, exact current-slice files, pre-existing dirty scope, and applicable contracts or invariants. Review only the authorized slice.
2. Read the scoped diff first. Inspect callers, ownership, data flow, side effects, and boundaries only where risk or a suspicious hunk warrants it.
3. Check contract compatibility, lifecycle and failure semantics, fail-closed behavior, and backward/data compatibility where applicable.
4. Examine verification for missing critical regressions, assertions that prove the wrong behavior, fake coverage, or acceptance claims unsupported by the exercised path. Do not demand a test for every line.
5. Report only actionable defects that can cause incorrect behavior, regression, corrupt/stale state, duplicated or missed execution, incorrect PnL/risk, crash, unsafe fallback, contract violation, or materially incorrect UI behavior.

Do not edit files, expand scope, propose taste-based renaming/formatting, or report speculative abstractions and refactors without a concrete defect. If a defect is found, leave implementation or debugging for a separate step, followed by fresh verification.

Use these severities:

- `BLOCKER`: unsafe or correctness-critical;
- `HIGH`: likely material regression;
- `MEDIUM`: real defect with bounded impact;
- `LOW`: objectively actionable minor defect only.

Format each finding as `[SEVERITY] path:line-or-symbol — defect`, followed briefly by evidence, consequence, and why it belongs to the reviewed change. Put findings first, ordered by severity. If none exist, write `No material defects found in reviewed scope.` and name the reviewed scope; never claim perfection.

After implementation, use `proof-before-done` for final claims. If verification fails for an unknown reason, use `systematic-debugging`; load other skill bodies only when their workflow actually applies.
