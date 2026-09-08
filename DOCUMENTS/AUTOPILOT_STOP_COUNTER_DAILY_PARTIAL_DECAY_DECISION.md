# AUTOPILOT STOP counter daily partial decay

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

At the AUTOPILOT trading-day boundary (00:00 MSK), STOP counters are not fully reset.

Instead, both the global STOP counter and each local per-instrument STOP counter partially decay.

The exact amount of daily decay is not yet fixed and remains to be decided in the next design step.

Rules already accepted and unchanged:
- protective STOP event with negative final result after actual costs: +1 to the relevant local counter and +1 to the global counter;
- profitable fully closed trade after actual costs: -1 from the relevant local counter and -1 from the global counter, floor 0;
- STOP-series trigger threshold: 5;
- global and local protection levels coexist; the stricter active size restriction wins;
- recovery size floor is 12.5%;
- a new trading day moves the recovery-size restriction one level softer and resets pause severity to the base pause N.

This document records only the accepted principle of partial daily STOP-counter decay. The numeric decrement is still unresolved.
