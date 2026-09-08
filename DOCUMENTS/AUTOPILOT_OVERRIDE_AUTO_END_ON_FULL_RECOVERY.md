# AUTOPILOT — Emergency override auto-end on full recovery

Status: ACTIVE / DESIGN-ONLY
Date: 2026-09-08
Implementation authorization: NONE

## Accepted decision

If an emergency override is active and the internal recovery state reaches 100%, the override ends automatically.

Rationale:
- the override only bypasses an active protection restriction;
- once the internal protection state is fully recovered, there is nothing left to bypass;
- keeping an override flag active after full recovery would create stale state and ambiguous semantics.

## Resulting behavior

- Internal recovery accounting continues while override is active.
- If internal recovery reaches 100%, the recovery cycle is complete.
- At that moment, emergency override is cleared automatically.
- Normal AUTOPILOT risk rules remain in force thereafter.
