# AUTOPILOT STOP Counter — No Rolling Window Decision

Status: ACTIVE / DESIGN-ONLY  
Implementation authorization: NONE  
Date: 2026-09-08

## Decision

Remove the separate rolling-window STOP-frequency trigger from AUTOPILOT recovery protection.

The protection uses the already accepted accumulated counter model instead:

- qualifying protective STOP: `+1`;
- qualifying profitable fully closed trade: `-1`;
- counter floor: `0`;
- protection trigger threshold: `5`.

Conceptually:

`STOP_COUNTER = max(0, STOP_COUNTER + stop_delta - profit_delta)`

with each qualifying STOP contributing `+1` and each qualifying profitable trade contributing `-1`.

When the relevant counter reaches `5`, the corresponding local or global protection is triggered according to the already accepted scoping rules.

## Rationale

A separate rolling-window rule largely duplicates the accumulated-counter mechanism because profits already decay the counter and therefore naturally distinguish a persistent bad run from ordinary mixed outcomes.

Removing the rolling window makes the mechanism simpler to reason about and avoids introducing an arbitrary lookback-window parameter that would otherwise require validation.

## Superseded design point

Any earlier proposal that used two independent STOP-series trigger paths — consecutive/accumulated plus STOP frequency inside a bounded rolling window — is superseded by this decision.

There is no separate rolling-window trigger in the current design.
