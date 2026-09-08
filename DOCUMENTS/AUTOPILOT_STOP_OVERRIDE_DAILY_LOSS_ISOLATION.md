# AUTOPILOT STOP Override vs Daily-Loss Protection

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

Emergency override for STOP-series protection does **not** bypass the independent daily-loss blocker.

### Semantics
- STOP emergency override may bypass active STOP-series pause and STOP-series size restrictions according to the separately accepted override rules.
- Daily-loss protection remains an independent risk-control layer.
- If the daily-loss blocker is active, new risk-increasing entries remain blocked even while STOP emergency override is active.
- STOP emergency override must not reset, clear, suspend, or otherwise modify daily-loss state.
- Any future ability to bypass daily-loss protection, if ever introduced, requires a separate explicit design decision and separate confirmation path.

## Rationale

The STOP-series mechanism and the daily-loss mechanism protect against different failure modes and therefore remain independent safety gates.
