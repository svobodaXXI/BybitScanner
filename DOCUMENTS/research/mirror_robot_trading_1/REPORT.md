# MIRROR ROBOT TRADING INTEGRATION-1 — MIRROR RETEST inside the existing PAPER Robot

**Status:** implemented and tested in code; **OFF by default** (`BYBITSCANNER_MIRROR_RETEST_ROBOT=1` enables it).
Not activated anywhere; no runtime, PAPER DB or LIVE touched. Economics remain `NOT PROVEN` (RETEST-5/6/7).

## What trades, and through which existing mechanism

MIRROR is an overlay on **IKIGAI_BOX attempts** of the existing Robot (`terminal/application/robot_breakout_monitor.py`).
No second engine: every order, fill, STOP, ownership proof and Net PnL is the Box Robot's own.

| Lifecycle step (owner rules §2/§2a/§5) | Implementation | Existing mechanism reused |
|---|---|---|
| Campaign: naked break of a frozen Wedge boundary, direction back to it | `mirror_retest_robot.find_active_campaign` replays `geometry.naked_retest` over closed 5m candles (1m proof for ambiguous touches) from the Wedge candidate's frozen `robot_geometry`; most recent ACTIVE campaign in the Box direction, proven up to now | Wedge `robot_candidates`, public closed klines (`BybitClosedKlineSource`) |
| Attempt admission + R0 | Once per Box candidate, **before any Box order exists**: direction match, boundary beyond the Box TAKE, `R0 = min(account risk limit, 0.5 × net potential)` frozen at the first attempt, `retest_campaign.entry_gate` over realized losses + live worst cases of earlier attempts. Durable `robot_state.execution["mirror"]` (`ATTACHED` / `NOT_ATTACHED` + reason). Not attached → plain Box, unchanged | Box admission/ownership/gates stay first; account limit = `retest_account_risk.account_risk_limit` (daily-loss headroom − committed worst cases) |
| Entry | unchanged Box grid/MARKET catch-up | Box catch-up + ownership |
| Partial TAKE 25 % | EXIT LIMIT per filled slot for `floor(25 % × slot, qty step)` at the frozen Box TAKE | Box-owned EXIT LIMIT (`create_box_owned_paper_limit`) |
| After partial TAKE | untouched entries cancelled; remainder STOP → whole-trade net break-even (`net_break_even_remainder_stop`: fees, 0.5 % slippage allowance, tick rounding), only if tighter and placeable; current STOP kept otherwise | shared Box STOP amend (`submit_stop_amend`) |
| Remainder 75 % | held under STOP; campaign advanced by each new closed 5m candle | — |
| Exit at first proven retest | durable close intent, then Box-owned **EXIT MARKET slot 0** for the exact remaining quantity; other owned limits cancelled first | the existing aggregate-close slot (emergency/manual close) |
| Close + Net PnL | flat → shared `_finalize_box_take_if_flat`: `exit_reason=TAKE` (the campaign TAKE; no schema change), realized PnL and fees from the Box ownership proof over all legs; `execution["mirror"]["exit"]` records `MIRROR_RETEST` | `close_robot_trade` |
| Retest before any fill | owned entries cancelled, candidate `INVALIDATED` (no new attempt after the retest) | `_invalidate_pre_entry_candidate` |
| Repeated attempts | each new Box attempt is gated against the same campaign's frozen R0; profits never restore budget | `entry_gate` |

Safety: any doubt → plain Box or keep current protection. A data gap blocks the campaign (`data_blocked`, no exit, no new
attempt). Missing 1m proof holds the candle (never `RETEST_UNPROVEN` from missing data). Every action id is deterministic;
the close intent is durable before the market is sent; slot-0 ownership is reserved before submission → no duplicate
execution after a restart. A monitor without the policy (the owner-path monitor of `process_authoritative_fill`) still
honours the durable MIRROR exits/STOP, because all behaviour is read from `execution["mirror"]`.

## Files

- `mirror_retest_robot.py` (new): policy, campaign replay, attachment gate, partial EXIT specs, retest close plan,
  break-even STOP, env-gated `build_runtime_policy`.
- `terminal/application/robot_breakout_monitor.py`: optional `mirror_policy`; hooks in the Box path (attach, partial EXIT
  specs, STOP override, retest advance/close). Without a policy and without `execution["mirror"]` the Box path takes the previous
  branches (verified by the existing Robot suites).
- `terminal/runtime/paper_runtime.py`: passes `build_runtime_policy(...)` (returns `None` unless the flag is `1`).
- `tests/test_mirror_robot_box_cycle.py`: full cycle, restart, owner-path monitor, flag off, no campaign, R0 unknown,
  boundary not beyond TAKE, data gap, retest before fill, budget/R0 rules, 1m-proof hold.

## Remaining obstacles before PAPER acceptance

1. **Owner permission** to set `BYBITSCANNER_MIRROR_RETEST_ROBOT=1` on a PAPER runtime.
2. **L-shape attempts** are not wired (only IKIGAI_BOX). L-shape uses position-level TAKE protection, not owned EXIT limits.
3. **Account risk limit** comes from `read_account_facts` without runtime marks: with any open position the daily gate is
   unavailable → no R0 → MIRROR never attaches. A marks-aware read (as Autopilot has) is needed for real use.
4. **Network in the monitor thread:** attachment replays ≤ 5 Wedges × ≤ 3 kline calls; each open MIRROR trade costs one
   kline call per tick. Acceptable for a bounded PAPER test; a background evaluator would be better.
5. **`RETEST_UNPROVEN`** (1m data present but still ambiguous) ends the campaign without an exit: the remainder stays under
   STOP; the owner has not defined this case.
6. Partial TAKE per slot is floored to the quantity step; a slot whose 25 % is below one step is held whole to the retest.
7. Exit at the retest is a MARKET after the closed 5m candle proves the touch (not a resting LIMIT at the line), so the
   price can be worse than the line by the post-candle move.
