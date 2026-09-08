# AUTOPILOT Global STOP — Midnight score-only decay decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

At `00:00 MSK`, the daily decay for the global STOP state reduces only the aggregate global STOP-score by exactly `1`, with a floor at `0`.

Per-instrument global STOP contributions are not changed by the midnight decay.

This remains valid even when the aggregate global STOP-score has diverged from the sum of per-instrument contributions because of accepted `-0.5` credits from profitable trades on instruments whose current contribution is already `0`.

## Example

Before midnight:
- BTC contribution = 3
- ETH contribution = 2
- SOL contribution = 0
- aggregate global STOP-score = 4.5

At `00:00 MSK`:
- aggregate global STOP-score: `4.5 -> 3.5`
- BTC contribution remains `3`
- ETH contribution remains `2`
- SOL contribution remains `0`

## Trigger semantics preserved

Global protection still requires both conditions to be true at the same time:
1. aggregate global STOP-score `>= 5`;
2. current contribution distribution satisfies the accepted multi-instrument diversity rule.

The aggregate score is authoritative for the threshold; the per-instrument contribution ledger is authoritative only for the diversity test.
