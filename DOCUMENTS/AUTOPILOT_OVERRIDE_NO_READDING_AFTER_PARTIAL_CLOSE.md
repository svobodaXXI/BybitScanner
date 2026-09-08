# AUTOPILOT Emergency Override — No Re-adding After Partial Close

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

During STOP-series protection or while its emergency override is active, if an already-open position has been partially reduced, AUTOPILOT must not increase that same position again.

This prohibition applies even when the requested increase would only restore the position to its prior size.

Allowed actions remain risk-reducing only for the existing position: partial close, full close, keeping the protective STOP unchanged, or tightening the protective STOP.

Emergency override may restore permission for new entries according to the accepted override rules, but it does not permit re-adding exposure to an already-open position after that position has been reduced.
