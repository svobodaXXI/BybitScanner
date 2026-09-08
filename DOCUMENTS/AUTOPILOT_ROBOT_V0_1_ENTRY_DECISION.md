# BybitScanner — Robot v0.1 Entry Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Decision

For the first PAPER robot prototype, Falling Wedge LONG entry occurs immediately after the first closed 1m candle closes above the Falling Wedge upper boundary.

The robot does not wait for a retest or a second confirmation candle in v0.1.

Entry execution intent is PAPER Market LONG and must be routed through the existing shared trading intent / order / execution lifecycle. The robot must not implement a separate market-entry execution path.

## Reuse / authority constraints

- Wedge identity and upper boundary come from the existing Scanner / Wedge / Geometry outputs.
- Closed-candle data comes from the existing market-data path.
- Breakout semantics should reuse the existing breakout / confirmation capability when its current contract matches this decision; otherwise only the smallest adapter/policy layer may be added, without creating a second authoritative breakout computation.
- Actual entry price is the execution fill returned by the existing PAPER execution lifecycle.
- Robot v0.1 owns only the strategy/orchestration decision that this event should create an entry intent.

## Deferred

Not part of v0.1:
- retest entry;
- second-candle confirmation;
- intrabar crossing entry;
- volume/ATR/candlestick filters;
- LIVE execution.

# END_OF_DOCUMENT
