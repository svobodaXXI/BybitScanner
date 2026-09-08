# AUTOPILOT Emergency Override State Preservation Decision

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE
Date: 2026-09-08

## Accepted decision

An emergency manual override removes only the currently enforced STOP-protection restriction. It does not erase the underlying STOP counters or recovery state.

Required semantics:
- override may temporarily return the affected AUTOPILOT scope to 100% risk size;
- existing STOP-counter state is preserved;
- existing recovery state/progress is preserved;
- the override action must be explicitly confirmed as an emergency action;
- the override event must be journaled/audited;
- subsequent qualifying failures continue from the preserved risk history and may re-apply protection according to the normal rules.

Rationale: emergency override is an operational bypass of the current restriction, not a history reset. Diagnostic/risk history must remain intact.
