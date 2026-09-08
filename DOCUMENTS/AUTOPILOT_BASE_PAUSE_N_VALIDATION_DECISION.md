# AUTOPILOT Base Pause N Validation Decision

Status: ACTIVE / DESIGN-ONLY
Date: 2026-09-08
Implementation authorization: NONE

## Decision

The base cooling-off pause `N` after the first qualifying 5-STOP protection trigger is not fixed to a concrete candle count during design.

`N` remains a tunable parameter to be selected from PAPER evidence.

The escalation ladder itself is fixed:

- first trigger: pause `N`
- second trigger: pause `2N`
- third trigger: pause `3N`
- further triggers: `4N`, `5N`, ...

Recovery-size floor remains `12.5%`; further triggers at that floor can lengthen the pause but do not reduce size below `12.5%`.

At the next trading-day boundary (00:00 MSK), the previously accepted day-reset policy applies, including resetting an inherited long pause to the base pause `N` while rolling the restriction one step softer.

## Validation note

The concrete candle count represented by `N` is `NEEDS VALIDATION` and should be fitted using PAPER statistics rather than guessed during design.
