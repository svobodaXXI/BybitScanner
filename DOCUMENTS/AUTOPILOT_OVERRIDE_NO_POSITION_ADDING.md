# AUTOPILOT Emergency Override — No Position Adding

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

Emergency override for STOP-protection may re-enable new entries, but it does not allow increasing the size of an already open position.

While emergency override is active:
- new entries may be allowed subject to all other independent risk gates;
- adding volume to an existing open position remains prohibited;
- protective STOP widening remains prohibited;
- daily-loss protection remains independent and cannot be bypassed by STOP override.

This preserves the distinction between temporarily restoring entry capability and increasing risk on an already-open trade.
