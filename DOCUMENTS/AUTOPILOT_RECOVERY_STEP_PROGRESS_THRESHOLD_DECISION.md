# BybitScanner — AUTOPILOT Recovery Step Progress Threshold Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record the accepted rule for how much recovery progress is required to move upward by one risk-size step after stop-loss protection has reduced AUTOPILOT size.

## ACCEPTED DESIGN

Each upward recovery step requires exactly `5` units of recovery progress.

The recovery ladder is therefore:

- `12.5% -> 25%` requires `5` recovery units;
- `25% -> 50%` requires another `5` recovery units;
- `50% -> 100%` requires another `5` recovery units.

Recovery is stepwise. Completing one recovery target restores only one size level, never multiple levels at once.

The existing recovery-score semantics remain:

- qualifying profitable completed trade: `progress += 1`;
- qualifying losing completed trade: `progress -= 1`;
- break-even final net result exactly `0`: no progress change;
- progress floor is `0`.

After a step is completed, the next step starts a new recovery cycle with a fresh target of `5` units.

This rule is separate from the STOP counter that triggers a protection level. The STOP counter also has threshold `5`, but it is a distinct state variable.

# END_OF_DOCUMENT
