# AUTOPILOT Emergency Override — New Entry After Full Close

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

If a position has been fully closed while STOP protection is active, and the emergency STOP override is active, AUTOPILOT may open a new position on the same instrument.

This is treated as a new entry, not as an increase of the prior position.

## Constraints

- Increasing an already-open position remains forbidden under the accepted override rules.
- Re-expanding a protective STOP remains forbidden even under emergency override.
- Daily-loss protection remains independent and is not bypassed by the STOP emergency override.
- The internal STOP recovery state continues to evolve according to the accepted recovery rules.
