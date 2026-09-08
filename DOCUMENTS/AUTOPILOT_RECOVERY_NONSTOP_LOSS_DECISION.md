# BybitScanner — AUTOPILOT Recovery Non-STOP Loss Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

During reduced-size recovery mode, a completed trade with final net realized result below zero that was NOT closed by the qualifying protective STOP:

- decreases recovery progress by exactly 1;
- does NOT increment the STOP counter;
- recovery progress remains floored at 0.

Thus recovery quality and protective-STOP accumulation remain separate mechanisms.

Concept:

`NON_STOP_LOSS -> RECOVERY_PROGRESS = max(0, RECOVERY_PROGRESS - 1)`

`NON_STOP_LOSS -> STOP_COUNTER unchanged`

Break-even / exactly zero remains neutral under the separately accepted rule.

# END_OF_DOCUMENT
