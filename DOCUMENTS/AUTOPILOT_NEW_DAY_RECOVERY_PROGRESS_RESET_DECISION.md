# AUTOPILOT New-Day Recovery Progress Reset Decision

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE
Date: 2026-09-08

## Accepted decision

At the fixed trading-day boundary of 00:00 MSK, if an active STOP-recovery restriction is automatically relaxed by one risk-size level, the accumulated recovery progress for that restriction is reset to 0.

Example:

- before 00:00 MSK: 12.5% size, recovery progress 4/5;
- new-day rule relaxes one level: 25%;
- after the boundary: recovery progress becomes 0/5, not 4/5.

This prevents the new-day one-step relaxation from combining with nearly completed prior-day recovery progress to produce an immediate second size increase after only one additional profitable trade.

The previously accepted new-day rules remain unchanged:

- trading day boundary is 00:00 MSK;
- active recovery restriction becomes one risk-size level milder;
- if the prior day ended at 12.5%, the new day starts at 25%;
- the pause multiplier resets to the shortest base pause N;
- active STOP counters decrease by exactly 1, floor 0.
