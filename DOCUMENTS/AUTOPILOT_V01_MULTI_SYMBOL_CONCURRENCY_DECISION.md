# BybitScanner — AUTOPILOT v0.1 Multi-Symbol Concurrency Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

## Decision

Robot v0.1 may manage multiple approved candidates and multiple open PAPER trades concurrently across different symbols.

For any one symbol, at most one robot-controlled trade idea may be active at a time.

An active robot-controlled idea includes candidate / approved / waiting-breakout / entry-pending / open / exit-pending states until the idea reaches a terminal lifecycle state.

## Rationale

- validates real multi-symbol lifecycle early;
- avoids artificial single-trade bottlenecks;
- avoids premature complexity from aggregating multiple robot-owned ideas into one symbol position;
- preserves a clean path to future portfolio/risk admission without duplicating execution state.

## Reuse constraint

Robot concurrency management must consume the existing authoritative account/position/execution state and must not create a parallel position ledger.

# END_OF_DOCUMENT
