# BybitScanner — AUTOPILOT Global/Local Counter Independence Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

When a GLOBAL STOP protection trigger fires, all LOCAL per-instrument STOP counters and local recovery state remain unchanged.

Global and local protection layers are independent state machines.

For any instrument under both layers, the effective position-size restriction is the stricter of the applicable global and local restrictions.

Therefore, a global protection event must not reset, forgive, or otherwise weaken a problematic instrument's local history.

# END_OF_DOCUMENT
