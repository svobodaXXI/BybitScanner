# AUTOPILOT Directional Counter Reset After Full Recovery Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

When an instrument fully recovers from local recovery mode back to 100% ordinary size:

- the instrument exits the shared local recovery state;
- separate directional STOP counters are re-enabled for LONG and SHORT;
- both directional counters restart from zero;
- old pre-recovery directional STOP history does not carry into the newly recovered 100% state.

Conceptually:

`LOCAL_RECOVERY_COMPLETE -> LOCAL_SIZE = 100% -> LONG_STOP_COUNTER = 0 -> SHORT_STOP_COUNTER = 0`

This applies only to the local directional counters for that instrument. Global AUTOPILOT protection state remains governed by its own accepted rules.
