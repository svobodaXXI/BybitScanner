# AUTOPILOT STOP counter profit-decay decision

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

For the STOP-series protection counter, each completed profitable trade reduces the accumulated STOP counter by exactly 1, but never below zero.

Concept:

`STOP_COUNTER = max(0, STOP_COUNTER - 1)` after each qualifying profitable completed trade.

A qualifying profitable trade uses the already accepted recovery win definition: the trade must be fully closed and its final realized result after actual costs must be strictly positive.

Examples:
- `STOP, STOP, STOP, PROFIT` -> counter `3 -> 2`;
- `STOP, PROFIT, PROFIT` -> counter `1 -> 0` and remains at zero;
- break-even / non-positive result does not reduce the counter.

The STOP-series trigger threshold remains 5.

The recovery-size floor remains 12.5%; repeated protection events may lengthen the pause, but volume is not reduced below 12.5%.

This decision is independent of daily-loss and other portfolio-risk gates; the strictest active gate wins.