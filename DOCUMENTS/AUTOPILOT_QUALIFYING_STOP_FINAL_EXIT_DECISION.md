Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

# AUTOPILOT Qualifying STOP Final-Exit Decision

Accepted decision:

A completed position counts as a qualifying STOP event only when BOTH conditions are true:

1. The final remaining portion of the position is closed by the protective STOP.
2. The final net result of the whole position lifecycle is negative after all actual realized P/L, partial exits, fees, and funding are included.

Consequences:

- If the position finishes net-negative but the final remaining portion is closed by strategy exit, TAKE, manual close, emergency close, or another non-protective-STOP exit, the position is NOT a qualifying STOP.
- A protective STOP on an earlier partial exit does not by itself make the whole position a qualifying STOP if the final closing event is not the protective STOP.
- Partial closes remain intermediate lifecycle events and do not independently increment STOP/recovery counters.
- The position-level final result remains the authoritative P/L result for classifying the completed trade.
