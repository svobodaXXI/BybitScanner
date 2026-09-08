# BybitScanner — AUTOPILOT Robot v0.1 Signal Expiry Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

## Decision

For Robot v0.1, after a user-approved Falling Wedge 1m signal enters the waiting-for-breakout state, the candidate expires on the first of these events:

1. scanner invalidates the originating pattern/signal; or
2. 20 additional closed 1m candles elapse after approval without a qualifying breakout.

The robot must consume the existing scanner lifecycle/invalidation signal rather than implement a parallel pattern-validity engine.

The 20-candle timeout is a prototype safety/liveness guard against indefinitely retained stale candidates and is `NEEDS VALIDATION` as a trading parameter.

On expiry, the candidate transitions to `EXPIRED`, creates no exposure-increasing order, and remains available to downstream event/history/diary consumers.

# END_OF_DOCUMENT
