"""Isolated H-017 BLUE opening counterfactual. Never a trading instruction.

Consumes already generated MARKET_ONLY research previews; all hypothetical
fills, costs and PnL are returned in a distinct, in-memory SIMULATION report.
An opening beyond the frozen blue slope is NOT a validated owner setup until
geometry and execution timing are accepted on the owner's own examples.

Assumptions: adverse slippage at actual M5 OPEN, 0.7% fixed stop recomputed
from that fill, owner 1R recheck, 20 funded 10 USDT slots including entry fees,
taker fees at both ends, first M5 intrabar stop before take if ambiguous,
worse actual OPEN for a stop gap, no automatic expiry or final liquidation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from research.historical_candle_feed import FIVE_MINUTES_MS
from research.h017_local_risk import H017LocalRiskPolicy


def positive(value: object, name: str, *, allow_zero: bool = False) -> Decimal:
    try:
        number = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not number.is_finite() or (number < 0 if allow_zero else number <= 0):
        raise ValueError(f"invalid {name}")
    return number


@dataclass(frozen=True)
class Position:
    trade_id: str
    side: str
    quantity: Decimal
    start_ms: int
    entry: Decimal
    stop: Decimal
    target: Decimal
    fee_open: Decimal
    notional: Decimal


def simulate_blue_open_scenario(
    document: dict[str, object], *,
    taker_fee_rate: object = "0.0006",
    adverse_slippage_rate: object = "0.0002",
) -> dict[str, object]:
    """Pure deterministic open-trigger portfolio; NEVER modify MARKET_ONLY."""
    if (document.get("source"), document.get("mode")) != ("SIMULATION", "MARKET_ONLY"):
        raise ValueError("counterfactual requires SIMULATION MARKET_ONLY")
    run_id = document.get("simulation_run_id")
    if (not isinstance(run_id, str) or not 1 <= len(run_id) <= 100
        or not all(c.isascii() and (c.isalnum() or c in "-_") for c in run_id)):
        raise ValueError("invalid SIMULATION identity")
    fee = positive(taker_fee_rate, "taker fee", allow_zero=True)
    slip = positive(adverse_slippage_rate, "adverse slippage", allow_zero=True)
    if fee >= 1 or slip >= 1:
        raise ValueError("cost rate must be below 1")
    events = document.get("events")
    previews = document.get("h017_blue_risk_previews")
    if not isinstance(events, list) or not isinstance(previews, list) or not events:
        raise ValueError("missing market events / candidate previews")
    if len(events) > 50000 or len(previews) > len(events):
        raise ValueError("invalid research history size")
    bars: list[dict[str, object]] = []
    by_open: dict[int, dict[str, object]] = {}
    for index, event in enumerate(events):
        if (not isinstance(event, dict) or event.get("source") != "SIMULATION"
            or event.get("simulation_run_id") != run_id
            or event.get("kind") != "CANDLE_CLOSED"
            or event.get("sequence") != index + 1
            or not isinstance(event.get("candle"), dict)):
            raise ValueError("foreign or executable event in market history")
        raw = event["candle"]
        start, end = raw.get("start_ms"), raw.get("end_ms")
        if (type(start) is not int or type(end) is not int or start < 0
            or end != start + FIVE_MINUTES_MS or event.get("time_ms") != end
            or (bars and start != bars[-1]["end_ms"])):
            raise ValueError("nonclosed, duplicate or missing M5 market bar")
        candle = {k: positive(raw.get(k), k) for k in ("open", "high", "low", "close")}
        if candle["low"] > min(candle["open"], candle["close"]) or candle["high"] < max(
            candle["open"], candle["close"]
        ):
            raise ValueError("invalid market OHLC")
        candle.update(start_ms=start, end_ms=end)
        bars.append(candle)
        by_open[start] = candle

    candidates: dict[int, dict[str, object]] = {}
    previous_open = -1
    for preview in previews:
        if not isinstance(preview, dict):
            raise ValueError("invalid candidate record")
        start = preview.get("open_ms")
        bar = by_open.get(start)
        if (type(start) is not int or bar is None or start <= previous_open
            or preview.get("source") != "SIMULATION"
            or preview.get("kind") != "BLUE_5M_OPEN"
            or preview.get("classification") != "UNVALIDATED_GEOMETRY_ONLY"
            or preview.get("time_ms") != bar["end_ms"]
            or preview.get("side") not in ("LONG", "SHORT")
            or preview.get("risk_status") not in ("RISK_PASS", "RISK_BELOW_1R")
            or type(preview.get("trend_version")) is not int
            or type(preview.get("blue_available_at_ms")) is not int
            or preview["trend_version"] > start or preview["blue_available_at_ms"] > start
            or "trade_id" in preview):
            raise ValueError("future, fabricated or unaligned candidate")
        if positive(preview.get("entry_price"), "entry") != bar["open"]:
            raise ValueError("candidate OPEN differs from market OPEN")
        side = preview["side"]
        target = positive(preview.get("target_price"), "frozen target")
        initial_stop = bar["open"] * (Decimal("0.993") if side == "LONG" else Decimal("1.007"))
        reward = target - bar["open"] if side == "LONG" else bar["open"] - target
        if (preview["risk_status"] == "RISK_PASS") != (reward >= abs(initial_stop - bar["open"])):
            raise ValueError("candidate's risk cohort disagrees with frozen target")
        if preview["risk_status"] == "RISK_PASS":
            if positive(preview.get("stop_price"), "frozen stop") != initial_stop:
                raise ValueError("wrong original fixed stop")
            quantity = positive(preview.get("quantity"), "preview size")
            if quantity * bar["open"] > Decimal("10.000000000000000001"):
                raise ValueError("preview allocates more than a ten-USDT slot")
        elif "stop_price" in preview or "quantity" in preview:
            raise ValueError("rejected preview carries execution fields")
        candidates[start] = preview
        previous_open = start

    policy = H017LocalRiskPolicy()
    starting_cash = policy.initial_cash
    cash = starting_cash
    reserved = Decimal(0)
    positions: list[Position] = []
    completed: list[dict[str, object]] = []
    counts = {
        "rejected_preview_below_1r": 0, "rejected_after_slippage_1r": 0,
        "skipped_slots_full": 0, "skipped_insufficient_cash": 0,
        "hypothetical_fills": 0, "hypothetical_exits": 0,
        "stops": 0, "takes": 0, "ambiguous_both_stop_first": 0,
    }
    peak_slots = 0
    peak_equity = starting_cash
    max_drawdown = Decimal(0)
    closed_net = Decimal(0)
    last_mark = starting_cash

    for bar in bars:
        candidate = candidates.get(bar["start_ms"])
        if candidate is not None:
            if candidate["risk_status"] == "RISK_BELOW_1R":
                counts["rejected_preview_below_1r"] += 1
            else:
                side = candidate["side"]
                open_fill = bar["open"] * (1 + slip if side == "LONG" else 1 - slip)
                # Reuse the owner's already implemented H-017 proposal, not an
                # invented 1R target; apply it at slipped actual OPEN.
                intent = policy.proposal(
                    side=side, expected_entry=open_fill,
                    target=candidate["target_price"],
                )
                if intent is None:
                    counts["rejected_after_slippage_1r"] += 1
                elif len(positions) >= policy.max_open_positions:
                    counts["skipped_slots_full"] += 1
                else:
                    qty = min(
                        intent.quantity,
                        (policy.slot_budget / (open_fill * (1 + fee))).quantize(
                            Decimal("1e-18"), rounding=ROUND_DOWN),
                    )
                    notional = qty * open_fill
                    entry_fee = notional * fee
                    if qty <= 0 or cash - reserved < notional + entry_fee:
                        counts["skipped_insufficient_cash"] += 1
                    else:
                        trade_id = f"SIMULATION:{run_id}:{counts['hypothetical_fills'] + 1}"
                        positions.append(Position(
                            trade_id, side, qty, bar["start_ms"], open_fill,
                            intent.stop, intent.take, entry_fee, notional,
                        ))
                        reserved += notional
                        cash -= entry_fee
                        counts["hypothetical_fills"] += 1
                        peak_slots = max(peak_slots, len(positions))

        remaining: list[Position] = []
        for pos in positions:
            if pos.side == "LONG":
                hit_stop = bar["low"] <= pos.stop
                hit_take = bar["high"] >= pos.target
                exit_reference = min(bar["open"], pos.stop) if hit_stop else pos.target
                exit_fill = exit_reference * (1 - slip)
                pnl = (exit_fill - pos.entry) * pos.quantity
            else:
                hit_stop = bar["high"] >= pos.stop
                hit_take = bar["low"] <= pos.target
                exit_reference = max(bar["open"], pos.stop) if hit_stop else pos.target
                exit_fill = exit_reference * (1 + slip)
                pnl = (pos.entry - exit_fill) * pos.quantity
            if not hit_stop and not hit_take:
                remaining.append(pos)
                continue
            exit_fee = exit_fill * pos.quantity * fee
            net = pnl - pos.fee_open - exit_fee
            cash += pnl - exit_fee
            closed_net += net
            counts["hypothetical_exits"] += 1
            counts["stops" if hit_stop else "takes"] += 1
            if hit_stop and hit_take:
                counts["ambiguous_both_stop_first"] += 1
            completed.append({
                "source": "SIMULATION", "trade_id": pos.trade_id,
                "side": pos.side, "entry_ms": pos.start_ms,
                "exit_ms": bar["end_ms"], "entry": str(pos.entry),
                "exit": str(exit_fill), "quantity": str(pos.quantity),
                "reason": "STOP_BOTH_SAME_M5" if hit_stop and hit_take
                    else "STOP" if hit_stop else "TAKE",
                "fees_usdt": str(pos.fee_open + exit_fee),
                "net_pnl_usdt": str(net),
            })
        positions = remaining
        # Rebuild reserved nominal from the open ledger, not by cumulative
        # Decimal subtraction (which may leave tiny NEGATIVE dust at flat).
        reserved = sum((pos.notional for pos in positions), Decimal(0))
        last_mark = cash + sum(
            (bar["close"] - pos.entry) * pos.quantity
            * (1 if pos.side == "LONG" else -1)
            for pos in positions
        )
        peak_equity = max(peak_equity, last_mark)
        max_drawdown = max(max_drawdown, (peak_equity - last_mark) / peak_equity)
        if not Decimal(0) <= reserved <= cash:
            raise AssertionError(f"counterfactual slot accounting inconsistent: t={bar['start_ms']} cash={cash} reserved={reserved} opens={len(positions)} last={completed[-1] if completed else None}")

    return {
        "source": "SIMULATION",
        "scenario": "H017_BLUE_OPEN_COUNTERFACTUAL_UNVALIDATED",
        "simulation_run_id": run_id,
        "assumptions": {
            "taker_fee_rate_each_side": str(fee),
            "adverse_slippage_rate_each_side": str(slip),
            "intrabar_same_m5_policy": "STOP_FIRST",
            "stop": "FIXED_0.7_PERCENT_OF_SLIPPED_ENTRY",
            "signal_timing": "BLUE_LINE_BEYOND_OPEN_WITH_PREVIOUSLY_CONFIRMED_GEOMETRY",
            "target": "FROZEN_H1_2_4_AT_OPEN",
            "end_of_history": "OPEN_POSITIONS_MARKED_NOT_LIQUIDATED",
            "max_concurrent_slots": policy.max_open_positions,
            "slot_budget_usdt_including_entry_fee": str(policy.slot_budget),
        },
        "initial_cash_usdt": str(starting_cash),
        "realized_cash_usdt": str(cash),
        "net_pnl_closed_trades_usdt": str(closed_net),
        "mark_to_market_equity_before_unrealized_exit_cost_usdt": str(last_mark),
        "max_mark_to_market_drawdown_fraction": str(max_drawdown),
        "peak_simultaneous_slots": peak_slots,
        "open_slots_end": len(positions),
        "counts": counts,
        "closed_simulated_trades": completed,
        "open_simulated_positions": [
            {"trade_id": pos.trade_id, "side": pos.side, "entry_ms": pos.start_ms,
             "entry_price": str(pos.entry), "quantity": str(pos.quantity),
             "stop_price": str(pos.stop), "target_price": str(pos.target)}
            for pos in positions
        ],
        "geometry_owner_verified": False,
        "production_ready": False,
    }
