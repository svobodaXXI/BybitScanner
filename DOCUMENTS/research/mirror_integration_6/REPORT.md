# MIRROR-INTEGRATION-6 — per-cycle database cost of the OBSERVE_ONLY sidecar

**Status:** the cost found in INTEGRATION-5 is removed for empty cycles; behaviour and OBSERVE_ONLY are unchanged.
Only `mirror_retest_sidecar.py` changed (MIRROR file). No Robot/Scanner/backend/frontend/shared persistence change, no
runtime started, PAPER DB untouched (measurements on the read-only PC copy, `db_unchanged=true`).

## Measured cause (no tracemalloc, same DB copy, BelowNormal, notebook)

Every cycle did two full reads even when nothing had changed (`profile_before_f53c207.json`, min of 3):

| Read | CPU s | wall s |
|---|---|---|
| `load_robot_auto_decision_heads` (arrivals; window functions over the whole audit) | 2.39 | 6.36 |
| `read_account_facts` (R0 snapshot), of which `load_robot_auto_decisions_for_admission` ≈ all | 4.70 | 8.26 |
| everything else in it (`paper_daily_equity_facts…`, open trades/positions/candidates/limits) | ≤ 0.05 each | |
| `count_robot_auto_decisions` | 0.016 | 0.010 |

The R0 cost sits in the shared same-day **daily-loss latch** sub-query: it `json_extract`s `facts_json` of PAPER_AUTO
decisions newest-first until one matches today's Moscow date. On this copy (last decision on 2026-10-19, measured on the
20th MSK) nothing matches, so it scans every row. On a live DB with a same-day decision it stops early, so this copy is
the worst case — but it is exactly the state at every day change before the first decision. That shared query was **not**
changed (Robot module).

## Fix (MIRROR sidecar only)

1. **Arrivals:** the Autopilot audit is append-only (triggers reject UPDATE/DELETE), so its row count is a valid change
   marker. A cycle reads the count (existing `count_robot_auto_decisions`, 16 ms) and re-reads arrivals only when it changed.
2. **R0 account facts:** read lazily (`_LazyAccountFacts`) — fresh from the DB at the moment a decision in an active
   campaign needs them, at most once per cycle, never carried to another cycle (no stale data in a decision). Read failure
   → empty facts → `WAIT r0_wait`, exactly as before. `RETEST_PROVEN`, gap-before-breakout and empty cycles never read them.
3. New metrics: `arrival_reads`, `arrival_reads_skipped`, `account_reads`, `account_read_failures`.

## Before / after (same copy, 364 tracked candidates, `load_*.json`)

| | before `f53c207` | after |
|---|---|---|
| first cycle (tracks 364 candidates) | 10.28 s CPU / 15.7 s wall | 5.33 s / 7.0 s |
| **each empty cycle** (5 measured) | **6.23–7.31 s CPU** / 9–15 s wall | **0.00–0.016 s CPU** / 0.014 s wall |
| empty cycles 2–6 total | 32.5 s CPU / 53.9 s wall | 0.064 s / 0.07 s |
| cycle with one breakout event | 7.42 s / 12.6 s | 4.25 s / 5.4 s (one lazy R0 read) |
| empty cycle after the event | 5.98 s / 9.8 s | 0.016 s / 0.016 s |
| decision of the event | `NAKED_BREAKOUT WAIT [r0_wait:daily_gate_data_unavailable, policy_wait:robot_execution_not_authorized, observe_only]` | identical |

## Tests

277 pass across the MIRROR/retest suite (14 files), including 7 new in `tests/test_mirror_retest_sidecar_load.py`:
empty cycles read neither arrivals nor R0; R0 read only for the breakout and not for the retest; R0 fresh per cycle (one read
for two breakouts in one cycle, another read in a later cycle); a new arrival is picked up on the next cycle; a read
error changes nothing and the next cycle recovers; a failed R0 read waits and is counted; a restart re-reads arrivals and
duplicates nothing in the journal. Every record stays `OBSERVE_ONLY`, `executable=False`, `admission_allowed=False`.

## Residual cost and next step

- An event in an active campaign still pays one R0 read (≈4–5 s CPU on this worst-case copy), and any new audit row
  (every Autopilot evaluation) triggers one arrivals read (≈2.4 s CPU). Both are bounded by real events now, not by the
  cycle rate. Cutting them further needs a change to the shared queries (owner/Robot decision), not in MIRROR.
- Still missing before an OBSERVE_ONLY runtime acceptance: a runner/launcher for the sidecar (owner decision) and a short
  real-time dry run with the backend up to exercise the healthy protection gate and measure close→record latency on the PC.
