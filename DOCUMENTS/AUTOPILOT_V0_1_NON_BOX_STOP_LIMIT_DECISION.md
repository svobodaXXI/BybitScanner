# BybitScanner — AUTOPILOT v0.1 Non-Box STOP Limit Decision (RM-STRUCT-2)

Version: 1.0
Date: 2026-10-17
Status: ACCEPTED (owner decision) / PAPER
Supersedes for non-Box patterns: the 2% threshold and fallback of
`AUTOPILOT_V0_1_STOP_FALLBACK_DECISION.md` and RM-STRUCT-1 (Wedge LONG 1.5% fallback).

## Decision

For every Robot pattern except Ikigai Box (Wedge LONG/SHORT, L-shape LONG/SHORT),
the maximum STOP distance from the actual entry price is **1.5%**
(`robot_protection.MAX_STOP_DISTANCE`).

## New entries — reject, never tighten

Before a new entry is placed, the correct structural STOP must be on the protective
side of the planned entry and within 1.5% of it. Otherwise the entry is rejected with
reason `SKIPPED_STOP_BEYOND_LIMIT`; the STOP is never pulled inside the structure only
to satisfy the limit. Checked routes:

- Wedge initial retest LIMIT: candidate terminated `INVALIDATED`, no LIMIT placed;
  `execution.entry_rr_filter` records `structural_extreme` and `max_stop_distance`.
- Wedge LIMIT reprice: the amend is not made; the original resting order is kept
  (same as a poor-RR reprice).
- Wedge late-admission Market: decision `SKIPPED_STOP_BEYOND_LIMIT`, no Market order;
  re-evaluated on the next tick like the other late-admission skips.
- L-shape retest LIMIT: frozen `l_shape.stop` must be within 1.5% of the LIMIT price,
  else `SKIPPED_STOP_BEYOND_LIMIT`.

The STOP check runs before the RR gate. RR (`MIN_ENTRY_RR`, L-shape net RR 2:1),
fees, tick size and fail-closed handling are unchanged.

## Filled positions — fallback stays

A filled position must always get a STOP (CR-PAPER-PROTECTION-LIFECYCLE-001). If the
actual fill moves the structural STOP to the wrong side or beyond 1.5% (late Market
VWAP, LIMIT fill price), `structural_stop()` places the fallback exactly 1.5% from the
actual average entry, LONG below and SHORT above. A LIMIT fill is never worse than its
LIMIT price, so the pre-entry check bounds the LIMIT routes. L-shape post-fill
protection keeps the frozen STOP unchanged. Later fills never widen an existing STOP
(`tighten_stop`). Positions opened before this change keep their existing protection.

## Excluded

Ikigai Box STOP/RR policy (`box_stop_for_actual_entry`, Box plan) is unchanged.

# END_OF_DOCUMENT
