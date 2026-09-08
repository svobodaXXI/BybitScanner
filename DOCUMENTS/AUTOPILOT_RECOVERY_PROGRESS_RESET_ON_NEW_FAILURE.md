# BybitScanner — AUTOPILOT Recovery Progress Reset on New Failure

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record what happens to recovery progress when a new protection event fires before the current recovery cycle is completed.

## ACCEPTED DESIGN

If a new STOP-protection trigger fires while AUTOPILOT is already in recovery mode, the current recovery progress is reset to `0`.

The new, stricter recovery level therefore starts a fresh recovery cycle from `0/5`.

Example:

`25% size, recovery progress 4/5 -> new STOP trigger -> 12.5% size, recovery progress 0/5`

Old recovery progress is not carried forward across a new protection event.

This rule applies together with the accepted one-step recovery ladder:

`12.5% -> 25% -> 50% -> 100%`

Each upward step requires a fresh completed recovery target of 5 units.

# END_OF_DOCUMENT
