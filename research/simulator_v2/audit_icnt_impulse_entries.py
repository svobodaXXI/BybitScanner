"""Causal, read-only ICNT entry quality audit from prior owner-verified L2 run.

No new orders or replays. Reconstruct only the two completed source M1 windows
and the last strictly pre-decision L2 book for each original virtual entry.
Not a trained filter, venue fill proof, or strategy optimization.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from robot_entry_flow_evidence import (
    TakerPrint, aggregate_taker_prints, compare_flow_windows,
    normalize_bybit_taker_print, permits_paper_entry,
    plan_impulse_protected_entry, recognize_impulse_signal,
)
from research.simulator_v2.historical_orderbook import BookState, iter_pinned_orderbook

TRADE_SHA = "47f3d3ea153374fe759adc81d2b340f5557d0fef84e90d28862d1a1239b0718a"
BOOK_SHA = "79b032aafc5c97ea3790947cdd72347af83c88b9a1360aa219cdef5f5cbe54df"
BASELINE_SHA = "fcf7b658757aa969357a4319a79f42c0e905090f"
SYMBOL = "ICNTUSDT"
M = 60_000
TICK = Decimal("0.0001")
FEE = Decimal("0.0006")
MAX_RAW_ROWS = 2_000_000


def _file_hash(path: Path, expected: str) -> None:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= 512_000_000):
        raise ValueError("missing or unsafe pinned input")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b""):
            h.update(chunk)
    if h.hexdigest() != expected:
        raise ValueError("original archive identity mismatch")


def _baseline(path: Path) -> tuple[dict, ...]:
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size > 3_000_000):
        raise ValueError("bounded prior comparison receipt required")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if (receipt.get("state") != "VIRTUAL_L2_PARTIAL_BE_COMPARISON_CONDITIONAL"
            or receipt.get("code_sha") != BASELINE_SHA
            or receipt.get("trade_gzip_sha256") != TRADE_SHA
            or receipt.get("l2_sha256") != BOOK_SHA):
        raise ValueError("prior owner-verified comparison identity mismatch")
    scenarios = receipt.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 4:
        raise ValueError("four original frozen scenarios required")
    base = scenarios[0]
    if base.get("threshold_percent") != "BASE" or base.get("state") != "CONDITIONAL_VIRTUAL_L2":
        raise ValueError("missing original unchanged baseline")
    report = base["result"]
    if (report.get("symbol") != SYMBOL
            or report.get("execution_model") !=
            "SIMULATION_HISTORICAL_TAKER_L2_EVENT_TIME_NOT_REAL_BYBIT_FILLS"
            or Decimal(str(report.get("realized_net_pnl"))) != Decimal("-2.15403408000")
            or report.get("final_position_quantity") not in ("0", 0)):
        raise ValueError("baseline virtual trading evidence drift")
    rows = report.get("l2_episodes")
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError("four baseline virtual entry episodes required")
    result = []
    last_entry = -1
    for row in rows:
        sig, entry = row.get("signal_ms"), row.get("entry_ms")
        if (type(sig) is not int or sig % M != 0
                or type(entry) is not int or sig >= entry
                or entry <= last_entry or not isinstance(row.get("order_id"), str)
                or row.get("direction") not in ("LONG", "SHORT")
                or row.get("exit_reason") not in ("STOP", "TAKE")):
            raise ValueError("uncorrelated or noncausal original entry")
        if any(row.get(key) is None for key in (
            "planned_stop_price", "planned_take_price", "signal_structural_extreme",
            "entry_price", "net_pnl_usdt",
        )):
            raise ValueError("original entry lacks structural evidence")
        result.append(row)
        last_entry = entry
    return tuple(result)


def _focused_trades(path: Path, rows: tuple[dict, ...]) -> dict[int, tuple[TakerPrint, ...]]:
    """Read exactly original gzip and retain only two closed minutes per decision."""
    _file_hash(path, TRADE_SHA)
    needed = {
        stamp for row in rows for stamp in (row["signal_ms"] - 2*M, row["signal_ms"] - M)
    }
    if min(needed) < 0:
        raise ValueError("missing two previous completed trading minutes")
    per_minute: dict[int, list[TakerPrint]] = {t: [] for t in needed}
    seen: set[str] = set()
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
                or not {"timestamp", "symbol", "trdMatchID", "price", "size", "side"}
                    .issubset(reader.fieldnames)):
            raise ValueError("original trade fields unavailable")
        for i, raw in enumerate(reader):
            if i >= MAX_RAW_ROWS:
                raise ValueError("original archive exceeds bounded row budget")
            try:
                stamp = Decimal(str(raw["timestamp"]))
            except (ArithmeticError, ValueError, TypeError) as exc:
                raise ValueError("invalid archive timestamp") from exc
            if not stamp.is_finite() or stamp < 0:
                raise ValueError("invalid trade timestamp")
            at = int(stamp * 1000)
            minute = at // M * M
            if minute not in needed:
                continue
            print_ = normalize_bybit_taker_print(raw, layout="PUBLIC_TRADE_ARCHIVE")
            if print_.symbol != SYMBOL or print_.trade_id in seen:
                raise ValueError("foreign or duplicated selected trade")
            seen.add(print_.trade_id)
            per_minute[minute].append(print_)
    if any(not items for items in per_minute.values()):
        raise ValueError("missing trades in one of the original decision windows")
    return {
        t: tuple(sorted(items, key=lambda v: (v.event_ms, v.trade_id)))
        for t, items in per_minute.items()
    }


def _predecision_books(path: Path, rows: tuple[dict, ...]) -> dict[int, BookState | None]:
    """Exclude future and equal-ms books because channel chronology is unknown."""
    decisions = sorted({row["signal_ms"] for row in rows})
    start = decisions[0] - M
    current: BookState | None = None
    observed = {}
    cursor = iter_pinned_orderbook(
        path, symbol=SYMBOL, depth=200, sha256=BOOK_SHA,
        start_ms=start, end_exclusive_ms=decisions[-1],
    )
    pending = 0
    for book in cursor:
        while pending < len(decisions) and decisions[pending] <= book.available_at_ms:
            observed[decisions[pending]] = current
            pending += 1
        if pending >= len(decisions):
            break
        current = book
    while pending < len(decisions):
        observed[decisions[pending]] = current
        pending += 1
    return observed


def _optional_str(v) -> str | None:
    return None if v is None else str(v)


def _book_features(book: BookState | None, decision_ms: int) -> dict:
    if book is None or book.available_at_ms >= decision_ms:
        return {"l2_predecision_status": "UNKNOWN"}
    age = decision_ms - book.available_at_ms
    if age > 250:
        return {"l2_predecision_status": "STALE", "book_age_ms": age}
    bid, ask = book.best_bid[0], book.best_ask[0]
    mid = (bid + ask) / 2
    bid_qty = sum((size for _, size in book.bids[:5]), Decimal(0))
    ask_qty = sum((size for _, size in book.asks[:5]), Decimal(0))
    total = bid_qty + ask_qty
    return {
        "l2_predecision_status": "OBSERVED_QUOTE_NOT_QUEUE_PROOF",
        "book_at_ms": book.available_at_ms,
        "book_age_ms": age,
        "spread_bps": str((ask - bid) / mid * 10_000),
        "bid_top5_qty": str(bid_qty),
        "ask_top5_qty": str(ask_qty),
        "top5_size_imbalance": str((bid_qty - ask_qty) / total) if total else None,
        "refill_proven": False,
    }


def decision_features(row: dict, tape: dict[int, tuple[TakerPrint, ...]],
                      book: BookState | None) -> dict:
    at = row["signal_ms"]
    prev_prints = tape[at - 2*M]
    curr_prints = tape[at - M]
    prev = aggregate_taker_prints(prev_prints, symbol=SYMBOL,
                                   start_ms=at-2*M, end_ms=at-M)
    now = aggregate_taker_prints(curr_prints, symbol=SYMBOL,
                                  start_ms=at-M, end_ms=at)
    transition = compare_flow_windows(prev, now, decision_ms=at)
    current_low = min(p.price for p in curr_prints)
    current_high = max(p.price for p in curr_prints)
    signal = recognize_impulse_signal(
        transition, closed_at_ms=at, candle_open=now.start_price,
        candle_close=now.end_price, candle_low=current_low,
        candle_high=current_high,
    )
    if (signal is None or signal.direction != row["direction"]
            or signal.structural_extreme != Decimal(row["signal_structural_extreme"])
            or not permits_paper_entry(row["direction"], transition)):
        raise ValueError("original Scanner/Robot admission cannot be reproduced")
    plan = plan_impulse_protected_entry(
        signal, tick_size=TICK, quantity=Decimal("1000"),
        max_notional_usdt=Decimal("1000"), max_risk_usdt=Decimal("50"),
        entry_fee_rate=FEE, exit_fee_rate=FEE,
        quantity_step=Decimal("1"), minimum_quantity=Decimal("1"),
    )
    if (plan.entry_price != Decimal(row["planned_entry_price"])
            if row.get("planned_entry_price") is not None else False):
        raise ValueError("original planned entry price drift")
    if (plan.stop_price != Decimal(row["planned_stop_price"])
            or plan.take_price != Decimal(row["planned_take_price"])
            or plan.quantity != Decimal(row["quantity"])):
        raise ValueError("original shared risk plan cannot be reproduced")

    risk_bps = abs(plan.entry_price - plan.stop_price) / plan.entry_price * 10_000
    range_ = current_high - current_low
    direction_close_location = (
        (now.end_price - current_low) / range_ if row["direction"] == "LONG"
        else (current_high - now.end_price) / range_
    ) if range_ else None
    return {
        "order_id": row["order_id"],
        "outcome": row["exit_reason"],
        "virtual_net_pnl_usdt": row["net_pnl_usdt"],
        "execution_flags": row["evidence_flags"],
        "direction": row["direction"],
        "signal_ms": at,
        "entry_ms": row["entry_ms"],
        "signal_to_model_entry_ms": row["entry_ms"] - at,
        "planned_entry": str(plan.entry_price),
        "virtual_entry_price": row["entry_price"],
        "planned_stop": str(plan.stop_price),
        "planned_take": str(plan.take_price),
        "stop_distance_bps": str(risk_bps),
        "projected_fee_aware_rr": str(plan.projected_net_rr),
        "previous_closed_m1_delta_fraction": _optional_str(prev.delta_fraction),
        "current_closed_m1_delta_fraction": _optional_str(now.delta_fraction),
        "previous_buy_notional": str(prev.buy_notional_usdt),
        "current_buy_notional": str(now.buy_notional_usdt),
        "previous_sell_notional": str(prev.sell_notional_usdt),
        "current_sell_notional": str(now.sell_notional_usdt),
        "current_m1_change_bps": str(now.price_change_bps),
        "direction_close_location_in_m1_range": _optional_str(direction_close_location),
        "buy_wave_accelerating": transition.buy_wave_accelerating,
        "sell_wave_accelerating": transition.sell_wave_accelerating,
        "buy_impact_fading": transition.buy_impact_fading,
        "sell_impact_fading": transition.sell_impact_fading,
        "absorption_observed": transition.sell_absorption_candidate if row["direction"] == "LONG"
                               else transition.buy_absorption_candidate,
        "oi_gate": "OFF",
        **_book_features(book, at),
    }


def analyze(*, baseline: Path, trades: Path, l2: Path) -> dict:
    rows = _baseline(baseline)
    tape = _focused_trades(trades, rows)
    books = _predecision_books(l2, rows)
    report = [decision_features(row, tape, books[row["signal_ms"]]) for row in rows]
    return {
        "state": "CAUSAL_ENTRY_EVIDENCE_RECONSTRUCTED_MODEL_ONLY",
        "symbol": SYMBOL,
        "original_baseline_sha": BASELINE_SHA,
        "original_trade_sha256": TRADE_SHA,
        "original_l2_sha256": BOOK_SHA,
        "count": len(report),
        "verified_causal_admissions": len(report),
        "no_future_trade_or_book": True,
        "hypothesis_not_proven": True,
        "strategy_parameters_not_changed": True,
        "episodes": report,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    for arg in ("repo", "baseline", "trades", "l2", "out", "code-sha"):
        p.add_argument("--" + arg, required=True)
    args = p.parse_args()
    root = Path(args.repo)
    if subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
    ).strip() != args.code_sha:
        raise ValueError("exact isolated GitHub research SHA required")
    output = Path(args.out)
    if output.exists() or output.parent.is_symlink():
        raise ValueError("refusing to overwrite owner-owned evidence")
    report = analyze(
        baseline=Path(args.baseline), trades=Path(args.trades), l2=Path(args.l2),
    )
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("AUDIT_STATUS=" + report["state"])
    for i, row in enumerate(report["episodes"], 1):
        print(
            f"ENTRY_{i}={row['direction']} {row['outcome']} "
            f"delta_prev={row['previous_closed_m1_delta_fraction']} "
            f"delta_now={row['current_closed_m1_delta_fraction']} "
            f"m1_bps={row['current_m1_change_bps']} "
            f"close_location={row['direction_close_location_in_m1_range']} "
            f"risk_bps={row['stop_distance_bps']} "
            f"rr={row['projected_fee_aware_rr']} "
            f"lag_ms={row['signal_to_model_entry_ms']} "
            f"book={row['l2_predecision_status']} "
            f"imbalance={row.get('top5_size_imbalance')} "
            f"flags={','.join(row['execution_flags']) or 'MODEL_ONLY'}"
        )
    print("FILTER_ADVANTAGE=UNPROVEN")
    print("REPORT=" + str(output))


if __name__ == "__main__":
    main()
