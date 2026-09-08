# BybitScanner — AUTOPILOT Stop-Loss Recovery Rule

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

After a stop-loss cluster triggers the AUTOPILOT protective sequence:

`STOP-LOSS SERIES -> COOLING-OFF -> REDUCED SIZE`

AUTOPILOT must not return to normal/full position size merely because a timer expires.

Return to normal/full size requires a recovery count equal to the number of stop-loss exits in the triggering stop-loss series.

Conceptually:

`triggering_stop_count = N`

`required_profitable_recovery_trades = N`

Example:

- 4 qualifying stop-loss exits trigger the protection;
- after cooling-off, AUTOPILOT resumes at reduced size;
- normal/full size is restored only after 4 qualifying profitable recovery trades.

This ties risk restoration to evidence that the strategy/market interaction has recovered, while making the recovery requirement proportional to the severity of the stop-loss series that caused the defensive state.

Still `NEEDS VALIDATION` / separate follow-up decisions:

- whether qualifying profitable recovery trades must be consecutive;
- whether a new losing/stop trade resets, decrements, or otherwise changes recovery progress;
- exact definition of a qualifying profitable recovery trade (for example net-positive after fees/funding and whether partial exits count);
- exact stop-series trigger count/window and reduced-size fraction.

This document records design only and does not authorize PAPER or LIVE runtime changes.
