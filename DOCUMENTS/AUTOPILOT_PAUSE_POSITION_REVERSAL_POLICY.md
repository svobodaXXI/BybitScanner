# AUTOPILOT Pause Position Reversal Policy

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE
Date: 2026-09-08

## Accepted decision

While STOP-protection pause is active, AUTOPILOT may reduce or close existing risk, but it must not create new opposite-side exposure as part of an immediate reversal.

Concretely:
- closing an existing LONG is allowed;
- closing an existing SHORT is allowed;
- partial risk reduction is allowed;
- protective STOP/TAKE and other risk-reducing exits remain allowed;
- immediately opening a new SHORT after closing LONG is forbidden during the pause;
- immediately opening a new LONG after closing SHORT is forbidden during the pause;
- a new entry in either direction becomes eligible only after the relevant pause has ended and normal admission rules are satisfied.

Rationale: a reversal contains a new-entry leg and therefore creates new risk. The pause blocks creation or increase of risk while preserving all risk-reducing actions.
