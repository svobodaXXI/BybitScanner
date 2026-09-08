# AUTOPILOT STOP Counter Trigger Reset Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

When an applicable AUTOPILOT STOP counter reaches the protection threshold of 5 qualifying STOP events:

1. The corresponding protection action is triggered.
2. That counter is immediately reset to 0.
3. A further escalation requires a new accumulation of 5 qualifying STOP events under the active counting scope.

Conceptually:

`STOP_COUNTER == 5 -> TRIGGER_PROTECTION -> STOP_COUNTER = 0`

This applies to whichever counter is authoritative in the current state, including directional local counters before local recovery activation, symbol-local recovery counters after local protection activation, and the global AUTOPILOT counter.

Existing accepted decay behavior remains unchanged:
- qualifying STOP: `+1`;
- qualifying profitable completed trade: `-1`;
- daily boundary at 00:00 MSK: `-1`;
- counter floor: `0`.

This decision replaces any behavior where a triggered counter remains at 5 and therefore causes near-immediate repeated escalation.
