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

## TRADING-2 fixes (2026-10-20)

- **R0 is marks-aware:** the account limit now uses Autopilot's own daily-loss gate (`robot_autopilot_shadow._daily_loss_gate`)
  with the runtime's fresh mark snapshot (`PaperRuntime._prepare_autopilot_daily_marks`, passed by the runtime wiring), minus
  committed worst cases of open positions (Robot STOP terms) and pending Box grids (frozen whole-grid net STOP loss).
  No second risk calculation.
- **Explicit MIRROR attempts block:** once an active campaign in the Box direction exists, any refusal except
  `no_active_campaign` / `direction_mismatch` / `boundary_not_beyond_box_take` is `BLOCKED` and the Box candidate is
  `INVALIDATED` before any order (unknown R0, campaign gate, bad terms). A Box with no campaign is unchanged.
- **Bounded network:** no kline request while the next 5m candle after the cursor cannot have closed; campaign replays are
  cached per boundary in-process (only new closed candles are fetched; terminal campaigns are never replayed).

## Remaining obstacles before PAPER acceptance

1. **Owner permission** to set `BYBITSCANNER_MIRROR_RETEST_ROBOT=1` on a PAPER runtime.
2. **L-shape attempts** are not wired (only IKIGAI_BOX). L-shape uses position-level TAKE protection, not owned EXIT limits.
3. **Pending non-Box entries** (Wedge/L-shape limits of other candidates) still have no provable worst case -> R0 unknown
   -> MIRROR attempts are blocked while such an entry rests.
4. **`RETEST_UNPROVEN`** (1m data present but still ambiguous) ends the campaign without an exit: the remainder stays under
   STOP; the owner has not defined this case.
5. Partial TAKE per slot is floored to the quantity step; a slot whose 25 % is below one step is held whole to the retest.
6. Exit at the retest is a MARKET after the closed 5m candle proves the touch, so the price can be worse than the line.

## MIRROR → PAPER E2E (2026-10-25)

- **Campaign sources extended:** besides Wedge Robot candidates, the Box attachment now reads live Scanner MIRROR
  candidates (#619 `mirror_scanner` state: fresh ≤2 candles, FULL_BODY body ≥ 0.5 ATR, not duplicate, still `UNTESTED`)
  via `mirror_retest_robot.scanner_level_sources`. Any level source (Wedge/Triangle, HORN, L-shape, Box, swing) qualifies.
- **The Robot stays authoritative:** it replays the level itself on closed 5m candles; the Scanner breakout must agree
  (direction; the same breakout candle for 5m levels). Retested / stale / weak / gap / unreadable state → never a source;
  unreadable state defers the attempt without orders.
- **Dedup:** one breakout seen through a Wedge line and a Scanner level is one campaign (Wedge wins ties, then the smallest
  boundary id) → one `campaign_id`, one R0 budget.
- Linked Box children of a Wedge parent keep using only that parent's campaign.
- Entry/STOP/TAKE/RR/fees/R0/invalidation are unchanged owner rules above; no new strategy parameters.
- Proof: `tests/test_mirror_scanner_paper_e2e.py` — real `observe_mirror_levels` signal → Box attempt ATTACHED →
  P1 2 @ 93.5, STOP 90.65 → 25 % 0.5 @ 99.2 → BE STOP 92.25 → retest close 1.5 @ 109.9 → realized 27.45, fees 0.24087
  (0.06 %/side), Net +27.20913 USDT on an isolated temp PAPER DB.
