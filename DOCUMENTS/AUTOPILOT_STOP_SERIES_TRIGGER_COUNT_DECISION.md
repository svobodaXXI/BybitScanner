# AUTOPILOT STOP-series trigger count

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

A STOP-series protection trigger is reached at exactly 5 qualifying STOP events.

`STOP_SERIES_TRIGGER_COUNT = 5`

A qualifying STOP event remains defined by the previously accepted rule: only an actual protective STOP execution with a negative final trade result counts toward this protection. Early strategy exits, manual closes, and other exit reasons do not increment the STOP-series count by themselves.

The previously accepted combined STOP-series logic remains in force:
- 5 qualifying STOPs in a consecutive series can trigger protection;
- 5 qualifying STOPs inside the configured rolling time/candle window can also trigger protection even if they are not strictly consecutive.

The exact rolling window remains NEEDS VALIDATION on PAPER.

This fixed count of 5 applies at every recovery restriction level. Each newly triggered set of 5 qualifying STOPs advances the recovery restriction algorithm by one level, subject to the already accepted pause and sizing rules.
