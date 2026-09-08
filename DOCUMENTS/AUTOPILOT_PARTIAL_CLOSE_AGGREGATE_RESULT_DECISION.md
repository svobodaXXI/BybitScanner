# AUTOPILOT Partial-Close Aggregate Result Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

For STOP/recovery accounting, partial closes do not create separate completed trades.

When the position is finally fully closed, the system evaluates the aggregate realized result of the entire position lifecycle.

The aggregate result includes:
- realized P/L from all partial closes;
- realized P/L from the final closing execution;
- all actual trading fees attributable to the position lifecycle;
- actual funding charged or received during the lifecycle.

STOP/recovery classification is performed only after the position is fully closed and is based on this final aggregate net result.

Therefore, the result of only the last closing fragment must never be used as the trade result for STOP/recovery accounting.
