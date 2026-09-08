# AUTOPILOT Override Midnight Recovery Continuity Decision

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE
Date: 2026-09-08

## Accepted decision

An active emergency override changes only the currently permitted effective risk size. It does not suspend or replace the internal STOP-protection and recovery state machine.

Therefore, at the fixed trading-day boundary of 00:00 MSK, the normal daily recovery relaxation still applies even while emergency override is active.

If the internal recovery restriction is below 100%, the internal restriction becomes one risk-size level milder according to the already accepted day-boundary rule, and the associated recovery-progress accumulator is reset to 0.

Example:
- effective size under active override: 100%
- hidden/internal recovery restriction before midnight: 25%
- at 00:00 MSK: internal recovery restriction becomes 50%
- recovery progress becomes 0
- effective size remains governed by the active override until that override terminates under its own accepted rule

This preserves separation between:
1. effective permission granted by emergency override; and
2. the underlying diagnostic/protective recovery state.

Emergency override must not freeze, erase, or bypass the normal internal day-boundary recovery mechanics.
