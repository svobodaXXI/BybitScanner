# AUTOPILOT full-size recovery progress reset decision

Status: ACTIVE / DESIGN-ONLY
Date: 2026-09-08
Implementation authorization: NONE

## Accepted decision

If the active STOP-protection size restriction is already at 100% at the 00:00 MSK trading-day boundary, any non-zero recovery-progress value is reset to 0.

Rationale:
- 100% size means the recovery cycle is complete;
- stale progress must not carry into a future restriction cycle;
- a future deterioration must start a fresh recovery-progress cycle under the normal STOP-protection rules.

This is consistent with the accepted rule that full recovery to 100% ends recovery mode and with the accepted midnight behavior that a day-boundary relaxation resets recovery progress when it advances one restriction level.
