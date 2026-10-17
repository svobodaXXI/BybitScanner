# BybitScanner — AUTOPILOT v0.1 Non-Box STOP Limit Decision (RM-STRUCT-2)

Version: 1.1
Date: 2026-10-17
Status: ACCEPTED (owner decision) / PAPER
Supersedes for non-Box patterns: the 2% threshold and fallback of
`AUTOPILOT_V0_1_STOP_FALLBACK_DECISION.md` and RM-STRUCT-1 (Wedge LONG 1.5% fallback).

Amendment v1.0 → v1.1 (owner correction): v1.0 rejected new entries whose
structural STOP was beyond the limit (`SKIPPED_STOP_BEYOND_LIMIT`). That
contradicted the owner decision and is removed. Distance alone never rejects an entry.

## Decision

For every Robot pattern except Ikigai Box (Wedge LONG/SHORT, L-shape LONG/SHORT),
the maximum STOP distance from the entry price is **1.5%**
(`robot_protection.MAX_STOP_DISTANCE`):

1. Compute the STOP beyond the structural extreme (Wedge: extreme -/+ one tick;
   L-shape: frozen `l_shape.stop`).
2. If it is on the protective side of entry and its distance is <= 1.5%, use it.
3. If the distance is > 1.5%, or the structural STOP is unavailable or on the wrong
   side of entry, use the fallback exactly 1.5% from entry: LONG below, SHORT above
   (`robot_protection.limited_stop`).

The entry is not rejected only because the structural STOP is farther than 1.5%.

## Where it applies

The same STOP is used for planning and protection:

- Wedge retest LIMIT RR gate, LIMIT reprice RR gate and late-admission Market RR
  gate: entry = planned LIMIT price / projected VWAP.
- Wedge post-fill protection (`build_protection_plan`): entry = actual average entry.
- L-shape retest LIMIT net-RR gate and post-fill protection
  (`build_l_shape_protection_plan`).

RR thresholds (`MIN_ENTRY_RR`, L-shape net RR 2:1), fees, tick size, fail-closed
handling, `tighten_stop` (later fills never widen STOP) and the other safety gates are
unchanged. Positions opened before this change keep their existing protection.

## Excluded

Ikigai Box STOP/RR policy (`box_stop_for_actual_entry`, Box plan) is unchanged.

# END_OF_DOCUMENT
