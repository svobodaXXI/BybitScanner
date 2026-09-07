# AUTOPILOT minimum recovery floor and new-day reset

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

The minimum recovery-size floor is 12.5% of the strategy-requested size.

Once AUTOPILOT reaches the 12.5% recovery-size floor, additional STOP-series triggers do not reduce size below 12.5%. Instead, only the pause multiplier continues to increase linearly.

Examples:
- first qualifying STOP series -> pause N -> 50% size;
- second qualifying STOP series -> pause 2N -> 25% size;
- third qualifying STOP series -> pause 3N -> 12.5% size;
- fourth qualifying STOP series while already at 12.5% -> pause 4N -> remain at 12.5%;
- fifth qualifying STOP series -> pause 5N -> remain at 12.5%;
- and so on.

A qualifying STOP series is 5 STOP events under the accepted STOP-series counting policy.

## New trading day reset

At the AUTOPILOT trading-day boundary (00:00 MSK), the restriction state moves one size level toward normal and the pause severity resets to the shortest/base pause N.

Therefore, if the previous trading day ended at the minimum 12.5% recovery-size floor, the new trading day starts at:
- 25% recovery size;
- base pause N for the next qualifying STOP-series trigger;
- no carry-over of the previous day's enlarged pause multiplier such as 4N, 5N, etc.

The same one-level relaxation applies generally to the recovery size state at the new trading day, subject to any stricter independent portfolio-risk gate such as the daily-loss blocker.
