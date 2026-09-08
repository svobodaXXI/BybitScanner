# AUTOPILOT Local STOP-series scope

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

A local STOP-series trigger affects only the instrument whose local STOP counter reached the trigger threshold.

Accepted trigger threshold: 5 STOP events.

When a local instrument reaches its STOP-series threshold:
- only that instrument enters its recovery pause and local reduced-size ladder;
- other instruments continue trading according to their own local state and the current global AUTOPILOT state;
- the STOP events from that instrument still contribute to the global STOP counter;
- therefore a sufficiently broad accumulation of STOPs across instruments can still trigger the global recovery ladder.

The effective trade-size limit for any instrument remains the stricter of its local recovery level and the global AUTOPILOT recovery level.

This decision is independent of daily-loss and other portfolio-risk gates; the strictest active gate wins.
