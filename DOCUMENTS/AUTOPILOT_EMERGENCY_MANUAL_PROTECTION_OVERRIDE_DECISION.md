# AUTOPILOT Emergency Manual Protection Override Decision

Status: ACTIVE / DESIGN-ONLY

Implementation authorization: NONE

Date: 2026-09-08

## Accepted decision

Manual bypass of an active AUTOPILOT STOP-protection restriction is allowed only through a dedicated emergency override flow.

The emergency override must require:
- explicit separate confirmation;
- a clear warning that the operator is bypassing an active risk-protection state;
- durable audit logging of the override event.

A normal one-click/manual reset that silently returns AUTOPILOT to 100% risk is not allowed.

This decision does not change the already accepted ability to reduce risk, close positions, or stop AUTOPILOT during a protection pause.
