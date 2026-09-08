# BybitScanner — Robot v0.1 Duplicate Signal Policy

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

## Decision

For Robot v0.1, after a user approves a Falling Wedge 1m candidate, repeated scanner signals referring to the same symbol and the same wedge instance are treated as duplicates and ignored while the current candidate remains active.

One approval creates one immutable decision snapshot. Subsequent duplicate scanner updates must not silently mutate the accepted geometry, potential, entry assumptions, or lifecycle state of that candidate.

The duplicate fence remains active until the current candidate reaches a terminal lifecycle state, including `EXPIRED`, `REJECTED`, `CANCELLED`, `OPEN`/subsequent managed trade completion as defined by the robot lifecycle, or `CLOSED`.

A genuinely different pattern instance is a separate candidate and must be identified by scanner/pattern identity rather than by symbol alone.

## Architectural intent

- preserve one approval = one deterministic trade idea;
- prevent moving-target behavior after user approval;
- reuse scanner identity instead of creating robot-side pattern matching;
- avoid duplicate robot state and duplicate execution attempts;
- keep the policy compatible with future multi-symbol and concurrent candidate handling.

# END_OF_DOCUMENT
