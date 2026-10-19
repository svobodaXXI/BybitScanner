"""MIRROR RETEST-6: one bounded historical replay of the full mirror-retest strategy.

Offline, cache-only, over the 67 RETEST-4/5 naked-breakout boundaries. Baseline
retest: physical touch (k = 0), ambiguous 5m touches settled by the 1m candles
inside them, remainder closed at the next 1m open after detection (RETEST-5).

Reused contracts (called, not reimplemented):
- signals: ``geometry.ikigai_box.detect_ikigai_box``, ``geometry.l_shape``
  detection and ``l_shape_signal_plan`` eligibility;
- Box plan: ``terminal.paper.ikigai_box_plan.approved_first_grid`` +
  ``plan_ikigai_box`` with the documented 0.0006 fee (paper_runtime.py:1228);
- L-shape: ``robot_l_shape`` frozen terms, retest transition, invalidation and
  ``build_initial_retest_limit`` (reference -/+ 2 ticks, 1 WV);
- campaign: ``retest_campaign.entry_gate`` and
  ``net_break_even_remainder_stop``.

Execution evidence is OHLC-inferred only (IKIGAI_BOX_STRATEGY_SPEC: a wick never
proves a fill): a LIMIT counts as filled only on a 1m trade-through, at its
price; a TAKE in the same 1m candle as the fill is not assumed; STOP and TAKE
both reachable in one later candle is AMBIGUOUS and reported as pessimistic /
optimistic bounds. STOP fills at its price (no stop slippage is documented).
Anything a contract does not define is classified NOT_EVALUABLE instead of
being decided here. Results are in % of 1 WV notional.
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass, field
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from geometry import l_shape as LS  # noqa: E402
from geometry.ikigai_box import detect_ikigai_box  # noqa: E402
from geometry.naked_retest import PHASE_CAMPAIGN_ACTIVE, Boundary  # noqa: E402
import robot_l_shape as RLS  # noqa: E402
from retest_campaign import (  # noqa: E402
    DECISION_ALLOW,
    PARTIAL_TAKE_FRACTION,
    STOP_NET_BREAK_EVEN,
    entry_gate,
    net_break_even_remainder_stop,
    open_campaign_budget,
)
from terminal.paper.ikigai_box_plan import approved_first_grid, plan_ikigai_box  # noqa: E402
from tools.research_mirror_retest_4 import COARSE_MS, FINE_MS, candles  # noqa: E402

FEE = Decimal("0.0006")       # documented PAPER per-side fee (LIMIT and MARKET)
BOX_WINDOW = 90               # trailing candles handed to the prefix-only Box detector
ONE = Decimal(1)

FILLED_NONE = "NO_FILL"
CLOSED = "CLOSED"
AMBIGUOUS = "AMBIGUOUS_ORDER"
OPEN_AT_END = "OPEN_AT_WINDOW_END"
NOT_EVALUABLE = "NOT_EVALUABLE"


def d(x) -> Decimal:
    return Decimal(str(x))


def through(direction: str, side: str, price: Decimal, candle) -> bool:
    """Trade-through of a resting order: entry BUY / exit SELL etc. by side."""

    long_entry = direction == "LONG"
    buy = (side == "entry") == long_entry
    return d(candle["low"]) < price if buy else d(candle["high"]) > price


def stop_hit(direction: str, stop: Decimal, candle) -> bool:
    return d(candle["low"]) <= stop if direction == "LONG" else d(candle["high"]) >= stop


@dataclass
class Trade:
    direction: str
    entries: list            # [(price, qty)] resting LIMITs from start_ms
    stop: Decimal
    take: Decimal
    start_ms: int
    take_fraction: Decimal   # 1 for the baseline, 0.25 for the mirror variant
    tick: Decimal
    retest_exit: dict | None = None   # {"time_ms", "price"}: campaign remainder exit
    events: list = field(default_factory=list)


def _pnl(direction, fills, exits) -> Decimal:
    sign = ONE if direction == "LONG" else -ONE
    cost = sum(p * q for p, q in fills)
    out = sum(p * q for p, q in exits)
    assert abs(sum(q for _, q in exits) - sum(q for _, q in fills)) < Decimal("1e-12")
    return sign * (out - cost) - FEE * (cost + out)


def simulate(trade: Trade, fine) -> dict:
    """Replay one attempt on closed 1m candles (OHLC-inferred execution).

    Returns ``status``, ``end_ms`` (when the symbol is free again; None = not
    before the window end) and PnL for the supplied quantities.
    """

    t = trade
    pending = list(t.entries)
    fills, exits = [], []
    stop = t.stop
    mirror = t.take_fraction < ONE
    partial_done = False
    remaining = Decimal(0)
    for candle in fine:
        if candle["open_time_ms"] < t.start_ms:
            continue
        if t.retest_exit and candle["open_time_ms"] >= t.retest_exit["time_ms"]:
            # Campaign retest: cancel unfilled entries, close the remainder (rule 7).
            if not fills:
                return {"status": FILLED_NONE, "reason": "retest_before_fill", "end_ms": t.retest_exit["time_ms"]}
            exits.append((d(t.retest_exit["price"]), remaining))
            return {"status": CLOSED, "exit": "RETEST", "pnl": _pnl(t.direction, fills, exits),
                    "fills": len(fills), "partial_take": partial_done, "end_ms": t.retest_exit["time_ms"]}
        new = [(p, q) for p, q in pending if through(t.direction, "entry", p, candle)]
        if new and partial_done:
            return {"status": NOT_EVALUABLE, "reason": "grid_fill_after_partial_take", "end_ms": None}
        had_position = bool(fills)
        for item in new:
            pending.remove(item)
            fills.append(item)
            remaining += item[1]
        if not fills:
            continue
        hit_stop = stop_hit(t.direction, stop, candle)
        # A TAKE in the fill candle itself is never assumed (wick != fill).
        hit_take = had_position and not partial_done and through(t.direction, "exit", t.take, candle)
        if hit_stop and hit_take:
            pessimistic = exits + [(stop, remaining)]
            return {"status": AMBIGUOUS, "reason": "stop_and_take_in_one_candle",
                    "pnl_pessimistic": _pnl(t.direction, fills, pessimistic),
                    "pnl_optimistic": None if mirror else _pnl(t.direction, fills, exits + [(t.take, remaining)]),
                    "fills": len(fills), "end_ms": None}
        if hit_stop:
            exits.append((stop, remaining))
            return {"status": CLOSED, "exit": "STOP" if stop == t.stop else "BREAK_EVEN_STOP",
                    "pnl": _pnl(t.direction, fills, exits), "fills": len(fills),
                    "partial_take": partial_done, "end_ms": candle["close_time_ms"]}
        if hit_take and not mirror:
            exits.append((t.take, remaining))
            return {"status": CLOSED, "exit": "TAKE", "pnl": _pnl(t.direction, fills, exits),
                    "fills": len(fills), "unfilled_limits_cancelled": len(pending),
                    "end_ms": candle["close_time_ms"]}
        if hit_take:
            take_qty = remaining * t.take_fraction
            exits.append((t.take, take_qty))
            remaining -= take_qty
            partial_done = True
            qty = sum(q for _, q in fills)
            notional = sum(p * q for p, q in fills)
            plan = net_break_even_remainder_stop(
                campaign_direction=t.direction, partial_take_confirmed=True, protection_preserved=True,
                current_stop_price=stop, mark_price=d(candle["close"]), entry_qty=qty,
                entry_avg_price=notional / qty, entry_fees_usdt=FEE * notional, partial_qty=take_qty,
                partial_avg_price=t.take, partial_fees_usdt=FEE * t.take * take_qty,
                funding_usdt=Decimal(0), remainder_exit_fee_rate=FEE, slippage_price=Decimal(0),
                tick_size=t.tick)
            if plan.decision == STOP_NET_BREAK_EVEN:
                stop = plan.stop_price
            t.events.append({"partial_take_ms": candle["close_time_ms"], "be_stop": plan.decision,
                             "be_reason": plan.reason})
    if not fills:
        return {"status": FILLED_NONE, "reason": "no_trade_through_in_window", "end_ms": None}
    return {"status": OPEN_AT_END, "end_ms": None}


def infer_tick(raw_rows) -> Decimal:
    decimals = 0
    for row in raw_rows:
        for value in row[1:5]:
            if "." in value:
                decimals = max(decimals, len(value.rstrip("0").split(".")[1]))
    return Decimal(1).scaleb(-decimals)


def box_signals(df, rows, start, end, camp):
    seen, out = set(), []
    for i, row in enumerate(rows):
        if row["close_time_ms"] <= start or (end is not None and row["close_time_ms"] >= end):
            continue
        lo = max(0, i - BOX_WINDOW + 1)
        box = detect_ikigai_box(df.iloc[lo: i + 1].reset_index(drop=True), as_of_index=i - lo)
        if box is None or box.direction != camp:
            continue
        key = (rows[lo + box.anchor_start_index]["open_time_ms"], rows[lo + box.anchor_end_index]["open_time_ms"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": "BOX", "decision_ms": row["close_time_ms"], "formation": box, "identity": key})
    return out


def lshape_signals(df, rows, start, end, camp):
    series = LS._series(df)
    atr = LS._atr_values(df, LS.DEFAULT_PARAMETERS.atr_period)
    out = []
    if not series or not atr:
        return out
    for i, row in enumerate(rows):
        if row["close_time_ms"] <= start or (end is not None and row["close_time_ms"] >= end):
            continue
        form = LS._detect_at(series, atr, i, LS.DEFAULT_PARAMETERS)
        if form is None or form.direction != camp:
            continue
        plan = LS.l_shape_signal_plan(form)
        out.append({"kind": "L-SHAPE", "decision_ms": row["close_time_ms"], "formation": form,
                    "plan": plan, "index": i})
    return out


def box_trade(sig, tick, camp, retest_exit, fraction):
    f = sig["formation"]
    try:
        prices, take = approved_first_grid(direction=camp, frozen_f1=d(f.fibonacci_1_0),
                                           frozen_f1618=d(f.fibonacci_1_618), tick_size=tick)
        plan = plan_ikigai_box(direction=camp, limit_prices=prices, limit_quantities=(ONE,) * 4,
                               working_quantity=Decimal(4), frozen_f1=d(f.fibonacci_1_0),
                               frozen_f1618=d(f.fibonacci_1_618), tick_size=tick, entry_fee_rate=FEE,
                               target_fee_rate=FEE, stop_fee_rate=FEE, take_price=take)
    except ValueError as exc:
        return None, f"box_plan_rejected: {exc}"
    avg = sum(prices) / 4
    scale = ONE / avg  # 1 WV notional across the four slices
    entries = [(p, scale / 4) for p in prices]
    trade = Trade(camp, entries, plan.stop_price, plan.take_price, sig["decision_ms"], fraction, tick, retest_exit)
    worst = sum(q * (abs(p - plan.stop_price) + FEE * (p + plan.stop_price)) for p, q in entries)
    return trade, {"avg": avg, "worst_loss": worst}


def lshape_trade(sig, tick, camp, rows, tf_ms, fine, retest_exit, fraction):
    plan = sig["plan"]
    if not plan.eligible:
        return None, f"lshape_not_eligible: {plan.rejection}"
    form = sig["formation"]
    breakout_ms = rows[sig["index"]]["close_time_ms"]
    snapshot = {"pattern": "L-shape", "symbol": "X", "l_shape": {
        "direction": camp, "source_timeframe": str(tf_ms // 60_000), "breakout_time_ms": breakout_ms,
        "reference": str(plan.reference), "target": str(plan.target), "stop": str(plan.stop),
        "structural_stop": str(plan.structural_stop), "stop_kind": plan.stop_kind,
        "potential_percent": str(plan.potential_percent), "reward_risk": str(plan.reward_risk)}}
    candidate = {"status": "APPROVED", "candidate_id": "replay", "signal_snapshot": snapshot}
    try:
        state, _ = RLS.initialize_state(candidate)
    except RLS.RobotLShapeError as exc:
        return None, f"lshape_terms_rejected: {exc}"
    for row in rows:
        if row["close_time_ms"] <= breakout_ms:
            continue
        if retest_exit and row["close_time_ms"] > retest_exit["time_ms"]:
            return None, "campaign_retest_before_lshape_retest"
        state, event = RLS.process_closed_candle(snapshot, state, {
            "time_ms": row["close_time_ms"], "high": str(row["high"]), "low": str(row["low"])})
        if event == RLS.EVENT_RETEST:
            break
        if state["phase"] == RLS.PHASE_INVALIDATED:
            return None, f"lshape_invalidated_before_entry: {event}"
    else:
        return None, "lshape_retest_not_in_window"
    entry = RLS.build_initial_retest_limit(candidate, state, tick_size=tick)
    price = entry.request.limit_price
    terms = RLS.frozen_terms(snapshot)
    trade = Trade(camp, [(price, ONE / price)], terms.stop, terms.target, state["retest_time_ms"],
                  fraction, tick, retest_exit)
    worst = (ONE / price) * (abs(price - terms.stop) + FEE * (price + terms.stop))
    return trade, {"avg": price, "worst_loss": worst}


def favourable_line_value(boundary: Boundary, camp: str, at_ms: int) -> Decimal | None:
    """Conservative fixed retest price at decision (plan section 5), else None (WAIT)."""

    slope = boundary.slope_per_ms
    if (camp == "LONG" and slope < 0) or (camp == "SHORT" and slope > 0):
        return None   # line moves toward the entry: no fixed conservative scenario
    return d(boundary.price_at(at_ms))


def main() -> int:
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    parser = argparse.ArgumentParser()
    parser.add_argument("--retest4", type=Path, required=True)
    parser.add_argument("--retest5", type=Path, required=True)
    parser.add_argument("--klines", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    r4 = json.loads(args.retest4.read_text(encoding="utf-8"))
    r5 = {c["boundary_id"]: c for c in json.loads(args.retest5.read_text(encoding="utf-8"))["cases_detail"]}

    ledger = []
    for item in r4["manifest"]:
        cid, bid = item["boundary_id"].split(":")[0], item["boundary_id"]
        case5 = r5[bid]
        camp = "LONG" if item["breakout_direction"] == "DOWN" else "SHORT"
        boundary = Boundary(bid, item["anchor_time_ms"], item["anchor_price"], item["slope_per_ms"], item["as_of_ms"])
        raw5 = json.loads((args.klines / f"{cid}_5.json").read_text())
        raw1 = [json.loads((args.klines / f"{cid}_1_{p}.json").read_text()) for p in (0, 1)]
        tick = infer_tick(raw5["rows"] + raw1[0]["rows"] + raw1[1]["rows"])
        coarse = candles(raw5, COARSE_MS)
        fine = sorted(candles(raw1[0], FINE_MS) + candles(raw1[1], FINE_MS), key=lambda c: c["open_time_ms"])
        start = item["breakout_close_time_ms"]
        retest_exit = case5["phys_market"]
        end = retest_exit["time_ms"] if retest_exit else None
        signals = []
        for tf_rows, tf_ms in ((coarse, COARSE_MS), (fine, FINE_MS)):
            df = pd.DataFrame(tf_rows)
            for sig in box_signals(df, tf_rows, start, end, camp) + lshape_signals(df, tf_rows, start, end, camp):
                sig["tf"] = tf_ms // 60_000
                sig["rows"], sig["tf_ms"] = tf_rows, tf_ms
                signals.append(sig)
        signals.sort(key=lambda s: s["decision_ms"])

        for strategy, fraction in (("BASE", ONE), ("MIRROR", Decimal(str(PARTIAL_TAKE_FRACTION)))):
            # R0's account-risk-limit part is not owner-defined: only the plan-section-5
            # potential part (0.5 * P_remaining, cap only shrinks) is evaluated.
            budget = open_campaign_budget(1e18)
            realized_loss = Decimal(0)
            busy_until = -1          # None = symbol busy until the window end
            for sig in signals:
                rec = {"strategy": strategy, "boundary_id": bid, "symbol": item["symbol"], "kind": sig["kind"],
                       "tf": sig["tf"], "decision_ms": sig["decision_ms"], "campaign": camp}
                exit_ref = retest_exit if strategy == "MIRROR" else None
                if sig["kind"] == "BOX":
                    trade, info = box_trade(sig, tick, camp, exit_ref, fraction)
                else:
                    trade, info = lshape_trade(sig, tick, camp, sig["rows"], sig["tf_ms"], fine, exit_ref, fraction)
                if trade is None:
                    rec.update(status="SIGNAL_REJECTED", reason=info)
                    ledger.append(rec)
                    continue
                if busy_until is None or trade.start_ms < busy_until:
                    rec.update(status="SKIPPED_SYMBOL_BUSY")
                    ledger.append(rec)
                    continue
                if strategy == "MIRROR":
                    target = favourable_line_value(boundary, camp, trade.start_ms)
                    if target is None:
                        rec.update(status="NOT_ADMITTED", reason="no_fixed_conservative_retest_price")
                        ledger.append(rec)
                        continue
                    sign = ONE if camp == "LONG" else -ONE
                    qty = sum(q for _, q in trade.entries)
                    reward = qty * (sign * (target - info["avg"]) - FEE * (info["avg"] + target))
                    gate = entry_gate(budget, campaign_phase=PHASE_CAMPAIGN_ACTIVE, data_reliable=True,
                                      realized_loss_costs_usdt=float(realized_loss),
                                      live_pending_worst_case_usdt=0.0,
                                      new_attempt_worst_case_usdt=float(info["worst_loss"]),
                                      remaining_net_reward_usdt=float(reward))
                    budget = gate.budget
                    rec.update(gate=gate.reason, reward_to_line_pct=float(reward * 100),
                               worst_loss_pct=float(info["worst_loss"] * 100))
                    if gate.decision != DECISION_ALLOW:
                        rec.update(status="NOT_ADMITTED", reason=gate.reason)
                        ledger.append(rec)
                        continue
                result = simulate(trade, fine)
                rec.update(result, events=trade.events)
                for key in ("pnl", "pnl_pessimistic", "pnl_optimistic"):
                    if rec.get(key) is not None:
                        rec[key] = float(rec[key] * 100)  # % of 1 WV notional
                ledger.append(rec)
                busy_until = result["end_ms"]
                if strategy == "MIRROR" and result["status"] == CLOSED and result["pnl"] < 0:
                    realized_loss += -result["pnl"]

    summary = {}
    for strategy in ("BASE", "MIRROR"):
        rows = [r for r in ledger if r["strategy"] == strategy]
        closed = [r for r in rows if r.get("status") == CLOSED]
        amb = [r for r in rows if r.get("status") == AMBIGUOUS]
        summary[strategy] = {
            "signals": len(rows),
            "status": {s: sum(r.get("status") == s for r in rows) for s in sorted({r.get("status") for r in rows})},
            "closed": len(closed),
            "net_pnl_pct_wv_closed": sum(r["pnl"] for r in closed),
            "wins": sum(r["pnl"] > 0 for r in closed), "losses": sum(r["pnl"] <= 0 for r in closed),
            "exits": {e: sum(r.get("exit") == e for r in closed) for e in sorted({r.get("exit") for r in closed})},
            "ambiguous_bounds_pct_wv": [sum(r["pnl_pessimistic"] for r in amb), sum(r["pnl_optimistic"] for r in amb)],
            "boundaries_with_trades": len({r["boundary_id"] for r in closed}),
        }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "ledger.json").write_text(json.dumps(ledger, indent=1, default=str), encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
