# BybitScanner — AUTOPILOT Profitable STOP Event Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record how a protective STOP exit is classified when the completed trade remains profitable after all actual costs.

## ACCEPTED DESIGN

A protective STOP execution increases the STOP counter only when the completed trade's final realized net result is negative after actual executed prices, fees, and funding.

Therefore:

- protective STOP with final realized net result `< 0` -> qualifying STOP event, STOP counter `+1`;
- protective STOP with final realized net result `= 0` -> neutral, STOP counter unchanged;
- protective STOP with final realized net result `> 0` -> profitable completed trade, not a qualifying STOP event, STOP counter unchanged by the STOP classification.

Recovery-progress treatment remains governed by the accepted net-result rules:

- final realized net result `> 0` -> recovery progress `+1`;
- final realized net result `= 0` -> recovery progress unchanged;
- final realized net result `< 0` -> recovery progress `-1`, floor `0`.

The event type alone does not override the final economic outcome for STOP-counter classification.

# END_OF_DOCUMENT
