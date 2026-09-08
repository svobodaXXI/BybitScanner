# AUTOPILOT Global STOP Score — Fractional Trigger Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

The global STOP score may be fractional.

Global STOP protection triggers when:

- `global_stop_score >= 5.0`, and
- the already accepted multi-instrument diversity requirement is satisfied.

Therefore an overshoot is valid and must trigger protection. Example:

- current global STOP score = `4.5`;
- next qualifying STOP adds `+1.0`;
- resulting score = `5.5`;
- if the distribution/diversity rule is satisfied at that moment, global protection triggers.

The trigger condition is threshold-based (`>= 5.0`), not equality-based (`== 5.0`).

## Related accepted rules

- Qualifying negative protective STOP contributes `+1`.
- A profitable completed AUTOPILOT trade on an instrument with zero current global STOP contribution may reduce the aggregate global STOP score by `0.5` without reducing another instrument's contribution.
- A later qualifying STOP on that same instrument still contributes a normal `+1` and creates/increases that instrument's contribution.
- One instrument alone cannot activate global protection; accepted diversity/distribution requirements remain independently mandatory.
