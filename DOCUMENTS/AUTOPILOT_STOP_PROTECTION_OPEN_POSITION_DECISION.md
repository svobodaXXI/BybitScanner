# BybitScanner — AUTOPILOT STOP Protection: Existing Positions

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

When a local or global STOP-series protection triggers, it does not force-close already open positions.

The protection gates only new risk:
- no new entries while the applicable pause is active;
- no position-size increases / averaging that would increase risk while the applicable pause is active;
- existing positions continue to be managed by their already-defined STOP, TAKE PROFIT, strategy exit, emergency exit, and other ordinary risk-management logic.

This applies to both local instrument protection and global AUTOPILOT protection.

Existing positions remain subject to all other independent risk gates and emergency controls.

# END_OF_DOCUMENT
