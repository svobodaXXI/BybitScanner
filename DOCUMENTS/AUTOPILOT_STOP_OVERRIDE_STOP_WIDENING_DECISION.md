# AUTOPILOT STOP override: STOP widening decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

Even while an emergency STOP-protection override is active, AUTOPILOT must not move an existing protective STOP farther from price if that increases risk on the open position.

The override may remove STOP-protection pauses and size restrictions according to the accepted override rules, but it does not bypass the rule that protective STOP modifications during a protection/recovery condition must be risk-neutral or risk-reducing.

Allowed:
- leave the protective STOP unchanged;
- tighten the protective STOP toward price so that position risk is reduced.

Blocked:
- widen the protective STOP away from price when that increases the potential loss on the existing position.

This restriction remains in force even when emergency override is active.
