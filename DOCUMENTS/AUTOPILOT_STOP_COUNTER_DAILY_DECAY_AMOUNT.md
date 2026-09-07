# AUTOPILOT STOP Counter: daily decay amount

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

At the AUTOPILOT trading-day boundary (`00:00 MSK`), every active STOP counter decays by exactly 1, but never below zero.

This applies independently to:
- the global AUTOPILOT STOP counter;
- each local per-instrument STOP counter.

Rule:

`NEW_COUNTER = max(0, OLD_COUNTER - 1)`

Examples:
- global `4 -> 3`;
- BTC local `2 -> 1`;
- ETH local `1 -> 0`;
- any `0 -> 0`.

This daily decay is separate from the already accepted recovery-size/day-boundary rule. A new trading day may also move the risk-size restriction one level toward normal and reset the pause multiplier to the shortest/base pause, while STOP counters retain memory through this one-point decay rather than full reset.
