# BybitScanner — AUTOPILOT Global STOP Pending-Diversity Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

The global AUTOPILOT STOP protection has two simultaneous trigger conditions:

1. the accumulated global qualifying STOP count has reached at least `5`;
2. qualifying STOP activity satisfies the accepted multi-instrument distribution rule: at least two instruments participate and the second instrument contributes at least `2` STOPs (minimum 5-STOP distribution `3+2`).

If the global STOP count reaches `5` or more before the distribution condition is satisfied, the global count is **not reset**.

It remains accumulated and continues to accept subsequent qualifying STOP events until the distribution condition is satisfied.

Example:

- BTC = 5, ETH = 0 -> no global protection; preserve accumulated global STOP state.
- BTC = 5, ETH = 1 -> no global protection; preserve accumulated global STOP state.
- BTC = 5, ETH = 2 -> diversity condition is now satisfied; global protection may trigger, subject to all other applicable gates.

The global STOP accumulation is reset only after an actual global protection trigger, according to the accepted post-trigger reset policy.

This avoids losing global stress memory merely because the first five STOPs came from one locally failing instrument.

# END_OF_DOCUMENT
