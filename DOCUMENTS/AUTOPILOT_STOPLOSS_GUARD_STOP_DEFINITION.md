# BybitScanner — AUTOPILOT Stoploss Guard: What Counts as a Stop

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

For the consecutive-stop protection / recovery mechanism, only an actual protective STOP execution with a negative final trade result increments the stop-series count.

Included:

- protective STOP triggered and trade closes with net result < 0.

Not included merely because the trade is negative:

- strategy-directed early exit before STOP;
- manual close;
- emergency close;
- other non-STOP exit paths.

Rationale:

- the stop-series guard is intended to detect repeated full setup failures that reached the predefined protective invalidation level;
- a strategy that recognizes deterioration and exits earlier should not be penalized as though a full STOP was hit;
- other loss types remain visible in the diary and in daily/account-level PnL controls.

Net result should use the same realized trade accounting semantics already accepted for recovery scoring, including actual trading fees and funding where applicable.

This is a design decision only and does not authorize runtime changes.

# END_OF_DOCUMENT
