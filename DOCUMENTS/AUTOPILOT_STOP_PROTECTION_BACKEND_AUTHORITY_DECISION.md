# AUTOPILOT STOP Protection — Backend Authority Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

The authoritative STOP-protection state lives in backend/runtime as part of the risk engine.

Frontend/AUTOPILOT UI is non-authoritative for STOP-protection state. It may:
- display the current backend-derived STOP/recovery state;
- send explicit user commands such as emergency override requests;
- render restrictions and recovery progress.

Frontend must not own or reconstruct protection counters, recovery state, pause state, effective STOP size restriction, or trigger state as an independent source of truth.

## Rationale

STOP protection must remain correct when the browser/phone UI is closed, refreshed, disconnected, or restarted. The protection state must therefore be independent of frontend lifecycle and survive UI restarts.

This also preserves the intended architecture:

`STRATEGY -> PORTFOLIO RISK ENGINE -> ACCOUNT-SCOPED ORDER INTENT -> EXECUTION ADAPTER`

STOP protection is a risk-engine responsibility before execution, not a presentation-layer responsibility.

## Implementation consequence

PAPER implementation should first introduce a backend/runtime STOP-protection state machine and persistence/recovery path. Frontend work should consume backend state only after the backend authority is established.
