# AUTOPILOT Global Recovery Loss Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

During global STOP-protection recovery, every completed AUTOPILOT trade with final realized net result < 0 after actual costs decreases global recovery progress by 1, with floor 0, even when the exit was not caused by a qualifying protective STOP.

## Related arithmetic

- profitable completed AUTOPILOT trade: global recovery +1;
- losing completed AUTOPILOT trade: global recovery -1;
- break-even completed trade: neutral;
- qualifying protective STOP is still handled by the separate STOP-trigger logic in addition to recovery deterioration rules where applicable.

This keeps global recovery symmetric with the accepted local recovery arithmetic and makes the portfolio-level recovery state reflect actual AUTOPILOT trade outcomes rather than STOP exits only.
