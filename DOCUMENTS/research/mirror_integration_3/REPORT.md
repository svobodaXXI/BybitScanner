# MIRROR-INTEGRATION-3 — OBSERVE_ONLY sidecar over existing read interfaces

**Status:** implemented and verified on saved data; **no shared file changed**; ready for a separate runtime acceptance.
Economics remain `NOT PROVEN`. Every record is `OBSERVE_ONLY`, `executable=False`, `admission_allowed=False`.

## What is reused (no parallel system)

| Need | Existing interface reused |
|---|---|
| Off-owner database reads | `SQLiteStore.open_reader` + `read_snapshot` (query_only, WAL; the A6 SHADOW observer's read path) |
| New Wedge candidates | durable arrival audit `load_robot_auto_decision_heads` + envelopes `robot_candidate_store.load_candidate` |
| Daily-loss gate snapshot | `paper_daily_equity_facts_in_transaction` + `robot_autopilot.daily_loss_gate_facts` (+ same-day latch rows via `load_robot_auto_decisions_for_admission`), `daily_loss_gate_enabled` |
| Obligations | `load_open_position_projections`, `load_open_robot_trades`, `load_robot_candidates_by_status`, `load_active_paper_limits` |
| Bounded observation queue | `paper_runtime._BestEffortDiagnosticsWriter` (full queue → drop and count, never blocks) |
| Detection / R0 / policy | `geometry.naked_retest`, `retest_account_risk` (#552), `mirror_retest_robot_bridge` (#547) via `mirror_retest_observer` (#557) |

## Safety properties (tested)

- **STOP/TAKE priority:** a cycle does no read at all while `protection_busy()` returns anything but `False` or raises.
  The sidecar never calls the owner (`runtime.call`), never opens a writer, never submits orders.
- **Daily limit is not a permission:** headroom is only the upper bound in `R0 = min(limit, 0.5 × potential)`; decisions
  stay WAIT/BLOCK even with a healthy gate.
- **Fail-closed:** unreadable DB → no observation (`read_failures`); account-facts error → `WAIT r0_wait`; open exposure
  without Robot STOP terms or a pending entry → obligation unknown → WAIT; data gap → one `DATA_GAP WAIT`, cursor held
  until the missing candle arrives.
- **Duplicates:** a candidate ref or the same `(symbol, scanner_formation_id)` is tracked once; re-runs emit nothing new.

## Verification

Tests `tests/test_mirror_retest_sidecar.py` (12): real saved case (1000LUNCUSDT, RETEST-4 boundary, Bybit public klines),
repeated candidates, missing candle + resume, unavailable R0, unreadable DB, healthy gate still never ALLOW, overloaded
queue, protection preemption (busy / unknown / raising), static no-trading guard.

Saved-data replay (read-only copy of the restored PAPER DB, copied candidate envelopes, RETEST-4 kline cache):

| metric | value |
|---|---|
| Wedge refs in the arrival audit | 656 (envelopes on PC: 438) |
| tracked / duplicates / unusable | 341 / 5 / 310 |
| observations (only cached-kline candidates have candles) | 10 breakout WAIT, 8 retest-proven BLOCK, 1 unproven BLOCK |
| second cycle | 0 new records |
| executable / admission-allowed | 0 / 0 |
| account snapshot from the copy | gate available, not latched, headroom 521.29 USDT, obligations 0 |
| R0 reason | `idea_potential_unknown` (no net-potential source yet) |

## Remaining blockers before live observation (no runtime change made)

1. **Idea net potential source.** R0 needs the candidate's after-cost potential; no existing interface publishes it for
   Wedge candidates. Proposal: compute from the frozen snapshot target/stop in the sidecar (independent) once the owner
   confirms the target definition for MIRROR.
2. **Live closed candles.** Only the saved cache source exists. A live source must use public klines off the owner (as
   RETEST-4 did) — part of runtime acceptance.
3. **`protection_busy` in live:** bind to `GET /api/robot/protection-health` (`healthy`, `ingress.current_pending`) — a
   read of an existing route; requires the runtime-acceptance approval to run beside PAPER_AUTO.
4. Running the sidecar against the working PAPER DB (read-only reader) is itself a runtime step: owner approval required.

## Files

new: `mirror_retest_sidecar.py`, `tests/test_mirror_retest_sidecar.py`, this report. No Robot, Scanner, Telegram,
admission, protection, API or Workspace file changed; no overlap with open terminal PRs (#546, #549–#556).
