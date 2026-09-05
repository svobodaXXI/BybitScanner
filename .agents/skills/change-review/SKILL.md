---
name: change-review
description: Read-only, defect-focused review of a BybitScanner change when review is requested or before material/high-risk behavioral acceptance; not routine completion, unknown-cause diagnosis, or trivial copy/cosmetic edits.
---

# Change Review

Review the authorized delta for concrete defects in execution/order lifecycle, STOP/TAKE, sizing, PnL,
reconciliation, state/concurrency, connectivity, market-data ownership, persistence, security or other material
behavior. Start with the scoped diff; follow callers, ownership, data flow and side effects only where needed.

Check:
- contract compatibility, lifecycle and failure semantics, fail-closed behavior, and data/backward compatibility;
- stale or cross-account state, duplicated/missed execution and unsafe fallback paths;
- whether verification exercises the actual failure class, not a mock shortcut or assertion that mirrors implementation;
- whether each material acceptance claim has current evidence for that exact scope and environment.

Use the evidence criteria in `ASSISTANT_PROTOCOL.md` §7.2. Identify missing critical regression coverage or
unsupported acceptance claims; do not demand a test for every line or equate build success with behavior/phone
acceptance. Review does not replace completion evidence on tasks that need no review.

Report actionable defects only:
- `BLOCKER`: unsafe or correctness-critical;
- `HIGH`: likely material regression;
- `MEDIUM`: real defect with bounded impact;
- `LOW`: objectively actionable minor defect.

Each finding identifies severity, path/line or symbol, evidence, consequence and relevance to this change.
If none exist, state "No material defects found in reviewed scope" and name that scope; never claim perfection.

Keep the review read-only. Do not expand scope, refactor, rename for taste or report speculative abstractions.
If a defect is found, separate the review from the authorized fix and subsequent fresh verification. Unknown-cause
investigation belongs to `systematic-debugging`; ordinary completion does not trigger another skill.
