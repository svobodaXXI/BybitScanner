# AUTOPILOT Global STOP — Profit From Zero-Contribution Instrument

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

If a profitable completed AUTOPILOT trade occurs on an instrument whose current instrument-level contribution to the global STOP state is `0`, that trade reduces the aggregate global STOP score by `0.5`.

The `0.5` reduction is applied only to the aggregate global STOP score. It does not decrement another instrument's contribution ledger.

Example before profit:
- BTC contribution = 3
- ETH contribution = 2
- SOL contribution = 0
- aggregate global STOP score = 5

After a profitable SOL trade:
- BTC contribution = 3
- ETH contribution = 2
- SOL contribution = 0
- aggregate global STOP score = 4.5

This rule is distinct from a profitable trade on an instrument that has a positive global STOP contribution, where the accepted rule is to decrement that instrument's own contribution and the aggregate global score accordingly.

Break-even trades remain neutral.
