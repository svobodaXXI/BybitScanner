# AUTOPILOT Global Recovery Profit Scope Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

Any completed profitable AUTOPILOT trade contributes `+1` to global recovery progress.

This is portfolio-scoped behavior: the profitable trade does not need to be on an instrument that participated in the global STOP trigger and does not need to have local recovery active.

## Notes

- Profitability is determined by final realized net result after actual costs, according to the already accepted trade-result rules.
- Break-even remains neutral.
- Global recovery otherwise follows the already accepted shared recovery ladder and step rules.
