# AUTOPILOT Global STOP Score Floor Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

The global AUTOPILOT STOP-score has a hard lower bound of `0`.

Profitable completed AUTOPILOT trades may reduce the global STOP-score according to the already accepted accounting rules, including fractional `0.5` reductions where applicable, but the resulting global STOP-score must never become negative.

Formally:

`global_stop_score = max(0, global_stop_score + delta)`

Examples:
- `0.5 - 1.0 -> 0`
- `0.25 - 0.5 -> 0`
- `0 - 0.5 -> 0`

No negative STOP-score is retained as a profit credit or reserve against future STOP events.
