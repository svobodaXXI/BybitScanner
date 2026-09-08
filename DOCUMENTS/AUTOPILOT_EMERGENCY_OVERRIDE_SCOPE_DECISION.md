# AUTOPILOT Emergency Override Scope Decision

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE
Date: 2026-09-08

## Accepted decision

Emergency override is not addressable to a single protection scope.

When emergency override is explicitly activated, it temporarily removes **all currently active STOP-protection restrictions at once**, including:
- local instrument protection restrictions;
- global AUTOPILOT protection restrictions.

The operator does not choose a subset of active STOP-protection restrictions to bypass.

## Existing override invariants remain unchanged

- Override requires a separate explicit emergency confirmation.
- Override action must be journaled.
- Override removes the currently enforced restrictions but does not erase the underlying STOP counters or recovery state.
- Recovery accounting continues while override is active.
- Normal 00:00 MSK recovery relaxation continues internally while override is active.
- Override automatically ends if the internal protection state fully recovers to 100%.
- Otherwise, override remains in effect only until the next new qualifying protection trigger, at which point protection is re-applied.

## Consequence

Emergency override is intentionally a whole-protection bypass rather than a per-symbol or per-scope bypass. This keeps the emergency control model simple and explicit while preserving the underlying diagnostic/risk history.
