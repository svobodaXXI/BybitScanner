# AUTOPILOT Recovery: progressive STOP-series ladder

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

AUTOPILOT uses a progressive recovery ladder after repeated STOP-series protection triggers.

Base recovery step:

`NORMAL SIZE -> STOP-series protection -> N-candle pause -> 50% RECOVERY SIZE`

If STOP-series protection triggers again while already in recovery, the algorithm advances one restriction level:

- pause multiplier increases linearly by one step: `N`, `2N`, `3N`, `4N`, ...;
- allowed recovery size is halved at each new restriction level: `50%`, `25%`, `12.5%`, `6.25%`, ... of strategy-requested size;
- after the required pause completes, entries may resume at the new reduced size, subject to all other active portfolio-risk gates.

Examples:

`100% -> STOP series -> N pause -> 50%`

`50% -> STOP series -> 2N pause -> 25%`

`25% -> STOP series -> 3N pause -> 12.5%`

Further repeated STOP-series failures continue by the same rule unless a later design decision introduces a hard minimum size or terminal block.

During every recovery pause:
- no new positions;
- no position increases / additions;
- existing positions continue normal protection and risk-reduction management;
- STOP / TAKE / closing / emergency risk reduction remain allowed.

## Next trading day rollback

At the start of the next AUTOPILOT trading day (00:00 MSK), the active recovery restriction is reduced by exactly one level, not reset directly to normal size.

Examples:
- if the previous day ended at `12.5%`, the new day starts at `25%`;
- if it ended at `25%`, the new day starts at `50%`;
- if it ended at `50%`, the new day starts at normal `100%` size.

This one-level rollback is subject to all stricter active gates, including the daily-loss blocker, account/data health checks, portfolio caps, correlation/directional-heat limits, and any other fail-closed conditions.

## Recovery progress

Previously accepted recovery-progress rules remain in force:
- profitable fully closed trades after actual costs add `+1`;
- losing trades subtract `1` without going below zero;
- full normal size is restored when the required recovery score reaches the number of STOPs that originally triggered recovery, unless the active ladder level or a stricter risk gate requires a smaller maximum size.

The exact base pause length `N` remains NEEDS VALIDATION on PAPER.
