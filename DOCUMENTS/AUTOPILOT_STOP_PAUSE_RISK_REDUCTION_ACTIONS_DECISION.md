# BybitScanner — AUTOPILOT STOP Pause Risk-Reduction Actions Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

During a STOP-protection pause, actions that reduce or close existing risk remain allowed.

Allowed during the pause include:

- partial position reduction;
- full position close;
- tightening or otherwise moving protective STOP in a risk-reducing direction;
- TAKE PROFIT execution;
- ordinary strategy exit logic that reduces or closes exposure;
- emergency risk-reduction / emergency close paths.

The pause blocks only actions that create new risk or increase existing risk.

Therefore, the protection is an admission gate on new/increased exposure, not a freeze on risk-reducing management of already-open positions.

This applies alongside the previously accepted rule that STOP-protection activation does not force-close already-open positions.

# END_OF_DOCUMENT
