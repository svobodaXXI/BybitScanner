# MIRROR RETEST R0 — account risk limit and the shared interface it needs

**Status:** independent calculation implemented and tested; **shared-file wiring NOT started** (needs agreement).
Economics of the strategy remain `NOT PROVEN`. Nothing here is Robot admission or a trading permission.

## Accepted formula (unchanged)

`R0 = min(account risk limit, 0.5 * net idea potential)` — `RETEST_BOX_CHAIN_IMPLEMENTATION_PLAN.md` §2a rule 11 / §5,
already implemented as `retest_campaign.freeze_campaign_r0`. No new account-risk percentage is introduced.

## What is the "account risk limit" in the existing Robot

Existing account-level gates (read, not changed):

| Gate | Where | Loss-denominated? |
|---|---|---|
| PAPER daily-loss gate: blocks at `block_pct` (−10) of the 00:00 MSK baseline equity, resumes above −7 | `terminal/application/robot_autopilot.py` (`daily_loss_gate_facts`, `DAILY_LOSS_BLOCK_PCT`), facts assembled in `robot_autopilot_shadow.py` | **yes (USDT headroom)** |
| 19 RO aggregate cap, `RO_USDT = 250` | `terminal/application/robot_portfolio.py` | no (notional slots) |
| per-asset 2 RO, correlation, cluster, direction | `robot_portfolio.DEFERRED` — not evaluated | — |
| symbol ownership, mandatory STOP/TAKE, continuity/protection health | Robot admission / protection | no |

The only loss-denominated account gate is the daily-loss gate, so:

```text
headroom = current_adjusted_equity - baseline_equity * (1 + block_pct / 100)      # distance to the existing block
limit    = headroom - sum(worst_case_loss_to_STOP of every open position and pending entry)
R0       = min(limit, 0.5 * net idea potential)
```

`block_pct` is read from the gate facts, not hard-coded. 19 RO / ownership / protection gates stay separate and mandatory;
this budget does not replace them (plan §5).

## Implemented (independent, pure) — `retest_account_risk.py`

- `daily_loss_headroom_usdt(daily_gate)`; `account_risk_limit(daily_gate, committed_worst_case_usdt)`;
  `freeze_r0(idea_potential_net_usdt, daily_gate, committed_worst_case_usdt)`;
  `position_worst_case_loss_usdt(direction, quantity, entry_price, stop_price, fee_rate)`.
- Fail-closed: disabled / unavailable / malformed gate, unknown or negative obligation, unknown potential → `WAIT`;
  latched gate, exhausted headroom or limit, non-positive potential → `DENY`; a position without a valid STOP has
  unknown worst case → `WAIT`. Unrealized PnL is already inside the gate's adjusted equity, so subtracting the full
  worst case is deliberately conservative.

## Shared interface still required (not implemented — owner/coordinator agreement first)

Read-only, owner-thread, same transaction as the admission check (plan §5: budget check atomic with ownership):

1. **`daily_loss_gate` facts on demand.** Today they exist only inside an Autopilot decision (`robot_autopilot_shadow.py`,
   `_daily_loss_gate` → `robot_autopilot.daily_loss_gate_facts`) and have no read accessor. Need one function returning the
   same mapping (`enabled`, `data_available`, `latched`, `baseline_equity_usdt`, `current_adjusted_equity_usdt`, `block_pct`).
2. **Account obligations list.** For every open position and pending entry: `direction`, `quantity`, `entry_price` (average
   entry; limit price for pending), and the protective `stop_price`; plus the documented PAPER per-side fee rate
   (`paper_runtime.py:1228`). Sources exist (`position_projections`, `protection_projections`, `paper_limit_orders`) but no
   single read function exposes them in this shape.
3. A MIRROR adapter must call (1) and (2) once per decision and pass the result unchanged; it must not cache across decisions.

Files that would be touched by the wiring (**not touched now**): `terminal/application/robot_autopilot_shadow.py`,
`terminal/application/robot_autopilot.py`, `terminal/application/robot_portfolio.py`, `terminal/runtime/paper_runtime.py`.

## Boundaries kept

No change to Robot, Scanner, admission, protection, API or Workspace; no PAPER_AUTO, backend, PAPER DB or LIVE access.
