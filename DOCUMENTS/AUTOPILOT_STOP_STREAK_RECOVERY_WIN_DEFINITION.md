# BybitScanner — AUTOPILOT Stop-Streak Recovery: Winning Trade Definition

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

For recovery from stop-streak risk reduction, a trade counts as a winning trade only after the trade is fully closed and its final realized result is strictly positive after actual trading costs.

The result must include, where applicable:

- entry trading fees;
- exit trading fees;
- realized funding payments/receipts attributable to the trade;
- actual executed entry and exit prices.

A trade with positive gross price movement but non-positive final net result does not increment recovery progress.

Conceptually:

`NET_REALIZED_TRADE_RESULT > 0 -> RECOVERY_PROGRESS + 1`

`NET_REALIZED_TRADE_RESULT <= 0 -> not a winning trade`

This definition is used together with the previously accepted recovery-score rule, where winning trades increment recovery progress and losing trades decrement it.

This document records design only and does not authorize runtime implementation.
