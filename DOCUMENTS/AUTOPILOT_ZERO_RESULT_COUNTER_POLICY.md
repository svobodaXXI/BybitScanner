# AUTOPILOT Zero-Result Counter Policy

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

A completed trade whose final realized result is exactly zero after all actual attributable costs is neutral for STOP-counter logic.

- `NET_REALIZED_TRADE_RESULT > 0` -> qualifying profit -> decrement applicable STOP counters by 1, floored at 0.
- qualifying protective STOP with `NET_REALIZED_TRADE_RESULT < 0` -> increment applicable STOP counters by 1.
- `NET_REALIZED_TRADE_RESULT == 0` -> no counter change.

Actual attributable costs include executed trading fees and realized funding already assigned to the trade, consistent with the previously accepted recovery-win definition.

This policy applies to both local and global STOP-counter accounting where that trade participates.
