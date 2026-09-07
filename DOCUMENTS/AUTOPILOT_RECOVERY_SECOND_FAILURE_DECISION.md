# AUTOPILOT Recovery: second STOP-series failure

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

If AUTOPILOT is already in the 50% recovery-size mode and the STOP-series protection triggers again, new risk is escalated to a full entry block.

Flow:

`NORMAL SIZE -> STOP-series protection -> pause -> 50% RECOVERY SIZE -> STOP-series protection again -> FULL NEW-ENTRY BLOCK`

While fully blocked:
- no new positions;
- no position increases / additions;
- existing positions continue normal protection and risk-reduction management;
- STOP / TAKE / closing / emergency risk reduction remain allowed;
- the ordinary recovery pause alone does not automatically re-enable entries.

A separate, stronger recovery/reset condition must be defined before automatic trading can resume from this state.

This decision is independent of the daily-loss blocker and other portfolio risk gates; the strictest active gate wins.
