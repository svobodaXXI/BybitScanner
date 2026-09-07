# AUTOPILOT Recovery: second STOP-series failure

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

If AUTOPILOT is already in the 50% recovery-size mode and the STOP-series protection triggers again, new entries are paused again and risk is reduced further rather than escalated to a full entry block.

The second recovery pause is doubled relative to the ordinary recovery pause, and the post-pause recovery size is reduced from 50% to 25% of the strategy-requested size.

Flow:

`NORMAL SIZE -> STOP-series protection -> pause -> 50% RECOVERY SIZE -> STOP-series protection again -> 2x PAUSE -> 25% RECOVERY SIZE`

During the doubled pause:
- no new positions;
- no position increases / additions;
- existing positions continue normal protection and risk-reduction management;
- STOP / TAKE / closing / emergency risk reduction remain allowed.

After the doubled pause completes, AUTOPILOT may resume new entries at 25% recovery size, subject to all other active portfolio-risk gates.

The recovery-progress rules remain unchanged: profitable closed trades after actual costs add +1, losing trades subtract 1 without going below zero, and normal size is restored only when the required recovery score reaches the number of STOPs that originally triggered recovery.

The exact ordinary pause length remains NEEDS VALIDATION on PAPER; the second pause is exactly 2x that validated value.

This decision is independent of the daily-loss blocker and other portfolio risk gates; the strictest active gate wins.
