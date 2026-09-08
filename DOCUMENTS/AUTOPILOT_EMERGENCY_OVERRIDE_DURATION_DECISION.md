# AUTOPILOT Emergency Override Duration Decision

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE
Date: 2026-09-08

## Accepted decision

Emergency override removes only the currently active STOP-protection restriction and does not erase STOP counters or recovery state.

The override remains effective only until the next new qualifying protection trigger.

When the protection conditions are reached again, the applicable STOP-protection restriction is automatically re-applied using the preserved risk history.

The override event must remain auditable in the journal.

## Rationale

This keeps emergency operator authority available without turning override into an indefinite bypass of the risk engine.
