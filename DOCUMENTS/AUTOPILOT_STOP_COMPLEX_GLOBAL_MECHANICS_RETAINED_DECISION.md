# AUTOPILOT STOP — Complex Global Mechanics Retained

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

The previously accepted global STOP protection mechanics are retained as-is.

This includes:
- aggregate global STOP-score may be fractional;
- the `0.5` reduction rule for a profitable completed trade on an instrument whose current global STOP contribution is already `0`;
- aggregate global STOP-score is tracked separately from per-instrument global STOP contributions;
- aggregate score and the sum of instrument contributions may diverge;
- global trigger requires both the aggregate threshold condition and the accepted instrument-distribution condition;
- midnight relaxation may reduce the aggregate global STOP-score without changing per-instrument contribution values, per the already accepted rule.

The proposed simplification that would remove fractional score, eliminate score/contribution divergence, and force global score to equal the sum of contributions is explicitly rejected for now.

## Rationale

The user chose to preserve the already accepted design rather than revise prior decisions solely to simplify implementation.

## Consequence

Do not silently collapse the current model into a single integer counter or recompute aggregate global STOP-score from the contribution ledger unless a later explicit design decision changes this architecture.
