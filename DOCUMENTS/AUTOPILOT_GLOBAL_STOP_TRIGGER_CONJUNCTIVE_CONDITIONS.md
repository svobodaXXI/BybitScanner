# AUTOPILOT Global STOP Trigger — Conjunctive Conditions

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

Global STOP protection activates only when both trigger conditions are true at the same time:

1. `global_stop_score >= 5`;
2. the accepted multi-instrument contribution/distribution rule is satisfied.

A historical crossing of the score threshold does not latch the trigger by itself.

Example:
- global score reaches `5.5` but contribution diversity is not yet sufficient -> no global trigger;
- a profitable trade reduces the score to `5.0` -> still no trigger unless diversity is also sufficient at that same moment;
- if later diversity becomes sufficient while score remains `>= 5`, the global trigger may activate.

The score may be fractional because accepted global accounting can apply `0.5` reductions in specified cases.
