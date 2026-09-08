# BybitScanner — AUTOPILOT Global Full-Recovery Reset Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

When the global AUTOPILOT protection has fully recovered back to `100%` risk-size eligibility:

- global recovery progress resets to `0`;
- global STOP counter resets to `0`;
- the next global protection cycle starts from a clean state;
- local per-instrument counters and local recovery states are not altered by this global reset.

This preserves independence between global and local protection state while ensuring that a completed global recovery cycle does not carry stale global failure/recovery memory into the next cycle.

# END_OF_DOCUMENT
