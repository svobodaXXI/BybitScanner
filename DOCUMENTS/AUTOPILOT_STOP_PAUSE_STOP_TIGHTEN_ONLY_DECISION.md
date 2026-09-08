# AUTOPILOT STOP-protection pause — protective STOP modification rule

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

While a STOP-protection pause is active, AUTOPILOT must not move an existing protective STOP farther away from current price if that would increase open-position risk.

Allowed during the pause:
- leave the protective STOP unchanged;
- move the protective STOP closer to current price when this reduces risk;
- execute other already-accepted risk-reducing actions.

Blocked during the pause:
- widening the protective STOP;
- moving the STOP farther from price in a way that increases the maximum loss on the current position;
- any equivalent action that increases exposure/risk while STOP protection is active.

This restriction applies independently of ordinary strategy requests. Emergency override behavior is governed by its separate accepted rules.
