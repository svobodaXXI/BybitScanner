# BybitScanner — AUTOPILOT Robot v0.1 Volume Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

## Decision

Robot v0.1 uses a fixed intended trade volume of `1 WV` (`1 РО`) for every accepted trade candidate.

The robot does not implement a separate sizing engine. It emits only the intended size in WV units. Conversion to instrument quantity, normalization, rounding and authoritative instrument constraints remain owned by the existing common sizing/execution path.

## Rationale

- minimizes prototype configuration and state;
- maximizes reuse of the existing WV/quantity machinery;
- avoids duplicate sizing semantics;
- keeps Robot policy account-neutral and execution-adapter-neutral;
- preserves a clean extension point for future dynamic sizing without changing the execution contract.

## Explicit non-goals for v0.1

- no score-based sizing;
- no volatility-based sizing;
- no risk-equalized sizing;
- no user-adjustable Robot volume setting;
- no separate Robot quantity calculation.

# END_OF_DOCUMENT
