# AUTOPILOT STOP counter: profitable-trade decrement scope

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

When a trade closes with a positive final realized result after actual costs, it decrements both active STOP counters by 1:

- the local instrument STOP counter for that symbol;
- the global AUTOPILOT STOP counter.

Neither counter may go below zero.

Conceptually:

`LOCAL_STOP_COUNTER = max(0, LOCAL_STOP_COUNTER - 1)`

`GLOBAL_STOP_COUNTER = max(0, GLOBAL_STOP_COUNTER - 1)`

This uses the already accepted profitable-trade definition: the trade must be fully closed and have final net realized result > 0 after actual trading fees and realized funding attributable to the trade.

A STOP event continues to increment the relevant local counter and the global counter according to the accepted STOP-event definition.

This document defines counter decrement scope only. Other recovery and risk-gate rules remain unchanged.