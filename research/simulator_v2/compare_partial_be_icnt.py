"""Offline three-way partial TAKE / fee-aware BE feasibility study for ICNT L2.

RESEARCH-ONLY: evaluates frozen original virtual episodes, marketable LIMIT
depth, and existing MIRROR break-even policy. No orders are actually submitted,
no partial fill is proven, and no alternative PnL is projected or optimized.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from retest_campaign import (
    STOP_NET_BREAK_EVEN, net_break_even_remainder_stop,
)
from research.simulator_v2.historical_orderbook import (
    BookState, iter_pinned_orderbook,
)
from robot_entry_flow_evidence import (
    TakerPrint, normalize_bybit_taker_print,
)

SOURCE_CODE_SHA = "9bf927b52eec8fc5266948fa7a65d33a206af2f1"
L2_SHA = "79b032aafc5c97ea3790947cdd72347af83c88b9a1360aa219cdef5f5cbe54df"
TRADE_SHA = "47f3d3ea153374fe759adc81d2b340f5557d0fef84e90d28862d1a1239b0718a"
SYMBOL = "ICNTUSDT"
DAY_START = 1794268800000
DAY_END = 1794355200000
FRACTIONS = (Decimal("0.25"), Decimal("0.50"), Decimal("0.75"))
PARTIAL_SHARE = Decimal("0.25")
TICK = Decimal("0.0001")  # original one-shot research settings
QTY_STEP = Decimal("1")
EXIT_FEE = Decimal("0.0006")  # conservative taker fee for both legs
SLIPPAGE = Decimal("0.005")  # existing MIRROR research STOP slippage reserve
MAX_ARCHIVE_SIZE = 512_000_000
MAX_TRADE_ROWS = 2_000_000


def _sha(path: Path, expected: str) -> None:
    if (not isinstance(path, Path) or path.is_symlink()
            or not path.is_file() or not 0 < path.stat().st_size <= MAX_ARCHIVE_SIZE):
        raise ValueError("missing, linked or oversized pinned source")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError("pinned market archive SHA-256 mismatch")


def validated_episodes(receipt: dict) -> list[dict]:
    if (not isinstance(receipt, dict)
            or receipt.get("state") != "VIRTUAL_L2_PROBE_CONDITIONAL"
            or receipt.get("code_sha") != SOURCE_CODE_SHA
            or receipt.get("l2_sha256") != L2_SHA
            or receipt.get("trade_gzip_sha256") != TRADE_SHA
            or not isinstance(receipt.get("result"), dict)):
        raise ValueError("original verified conditional L2 run required")
    result = receipt["result"]
    if (result.get("symbol") != SYMBOL
            or result.get("execution_model") !=
            "SIMULATION_HISTORICAL_TAKER_L2_EVENT_TIME_NOT_REAL_BYBIT_FILLS"):
        raise ValueError("original L2 execution provenance missing")
    episodes = result.get("l2_episodes")
    if not isinstance(episodes, list) or len(episodes) != 4:
        raise ValueError("expected exactly four original closed virtual episodes")
    verified = []
    cumulative = Decimal("0")
    last_exit = DAY_START
    for row in episodes:
        if (not isinstance(row, dict)
                or row.get("exit_reason") not in ("STOP", "TAKE")
                or row.get("direction") not in ("LONG", "SHORT")
                or not isinstance(row.get("evidence_flags"), list)):
            raise ValueError("original episode structure invalid")
        entry_ms, exit_ms = row.get("entry_ms"), row.get("exit_ms")
        if (type(entry_ms) is not int or type(exit_ms) is not int
                or not DAY_START <= last_exit < entry_ms < exit_ms < DAY_END):
            raise ValueError("original episodes overlap or violate event-time")
        values = {}
        for key in (
            "entry_price", "exit_price", "planned_take_price",
            "planned_stop_price", "quantity", "entry_fee", "exit_fee",
            "net_pnl_usdt",
        ):
            try:
                value = Decimal(str(row[key]))
            except (KeyError, ValueError, ArithmeticError) as exc:
                raise ValueError(f"invalid original episode {key}") from exc
            if not value.is_finite() or (value <= 0 and key != "net_pnl_usdt"):
                raise ValueError(f"invalid original episode {key}")
            values[key] = value
        direction = row["direction"]
        entry, take, stop = (values[x] for x in
                             ("entry_price", "planned_take_price", "planned_stop_price"))
        if not ((stop < entry < take) if direction == "LONG"
                else (take < entry < stop)):
            raise ValueError("invalid original protective price geometry")
        if values["quantity"] % QTY_STEP:
            raise ValueError("original quantity violates pinned step")
        if (values["entry_price"] * values["quantity"] > Decimal("1000")
                or not row.get("order_id")):
            raise ValueError("original episode exposure not pinned")
        gross = (
            (values["exit_price"] - entry) * values["quantity"]
            if direction == "LONG" else
            (entry - values["exit_price"]) * values["quantity"]
        )
        if gross - values["entry_fee"] - values["exit_fee"] != values["net_pnl_usdt"]:
            raise ValueError("original per-episode PnL reconciliation failed")
        cumulative += values["net_pnl_usdt"]
        verified.append({**row, **{k: v for k, v in values.items()}})
        last_exit = exit_ms
    if (cumulative != Decimal(str(result.get("realized_net_pnl")))
            or Decimal(str(result.get("final_balance"))) !=
            Decimal(str(result.get("initial_balance"))) + cumulative):
        raise ValueError("original virtual ledger not reconciled")
    return verified


def focused_tape(source: Path, episodes: list[dict]) -> list[TakerPrint]:
    """Read only original in-position prints; verify whole gzip CRC by EOF."""
    _sha(source, TRADE_SHA)
    selected = []
    seen = set()
    with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        needed = {"timestamp", "symbol", "side", "price", "size", "trdMatchID"}
        if not reader.fieldnames or not needed.issubset(reader.fieldnames):
            raise ValueError("original public taker CSV fields unavailable")
        for i, row in enumerate(reader):
            if i >= MAX_TRADE_ROWS:
                raise ValueError("original public trade budget exceeded")
            try:
                stamp = Decimal(str(row["timestamp"]))
            except (TypeError, ValueError, ArithmeticError) as exc:
                raise ValueError("invalid public trade timestamp") from exc
            if not stamp.is_finite() or stamp < 0:
                raise ValueError("invalid public trade timestamp")
            ms = int(stamp * 1000)
            if not any(ep["entry_ms"] < ms < ep["exit_ms"] for ep in episodes):
                continue
            trade = normalize_bybit_taker_print(row, layout="PUBLIC_TRADE_ARCHIVE")
            if trade.symbol != SYMBOL or trade.trade_id in seen:
                raise ValueError("duplicate or foreign in-position trade")
            seen.add(trade.trade_id)
            selected.append(trade)
    return selected


def _limit(entry: Decimal, take: Decimal, direction: str,
           fraction: Decimal) -> Decimal:
    raw = entry + (take - entry) * fraction
    rounding = ROUND_CEILING if direction == "LONG" else ROUND_FLOOR
    return (raw / TICK).to_integral_value(rounding=rounding) * TICK


def _full_depth(book: BookState, direction: str, limit: Decimal,
                quantity: Decimal) -> bool:
    """Marketable LIMIT, pessimistically priced at limit, not book VWAP."""
    levels = book.bids if direction == "LONG" else book.asks
    remaining = quantity
    for price, size in levels:
        if (price < limit if direction == "LONG" else price > limit):
            break
        remaining -= min(remaining, size)
        if remaining == 0:
            return True
    return False


def _be_plan(ep: dict, limit: Decimal, quantity: Decimal,
             book: BookState):
    direction = ep["direction"]
    mark = book.best_bid[0] if direction == "LONG" else book.best_ask[0]
    from geometry.naked_retest import CAMPAIGN_LONG, CAMPAIGN_SHORT
    return net_break_even_remainder_stop(
        campaign_direction=CAMPAIGN_LONG if direction == "LONG" else CAMPAIGN_SHORT,
        partial_take_confirmed=True,
        protection_preserved=True,
        current_stop_price=ep["planned_stop_price"],
        mark_price=mark,
        entry_qty=ep["quantity"],
        entry_avg_price=ep["entry_price"],
        entry_fees_usdt=ep["entry_fee"],
        partial_qty=quantity,
        partial_avg_price=limit,
        partial_fees_usdt=quantity * limit * EXIT_FEE,
        funding_usdt=Decimal("0"),
        remainder_exit_fee_rate=EXIT_FEE,
        slippage_price=mark * SLIPPAGE,
        tick_size=TICK,
    )


def evaluate(episodes: list[dict], trades: list[TakerPrint],
             books) -> dict:
    """Bounded original-lifetime diagnostics, never a hypothetical fill ledger."""
    if len(episodes) != 4:
        raise ValueError("four frozen episodes required")
    scenarios = []
    for index, ep in enumerate(episodes, 1):
        qty = (ep["quantity"] * PARTIAL_SHARE / QTY_STEP).to_integral_value(
            rounding=ROUND_FLOOR) * QTY_STEP
        if qty <= 0 or qty >= ep["quantity"]:
            raise ValueError("partial position quantity cannot be represented")
        for frac in FRACTIONS:
            target = _limit(ep["entry_price"], ep["planned_take_price"],
                            ep["direction"], frac)
            if (not ep["planned_stop_price"] < ep["entry_price"] < target
                    if ep["direction"] == "LONG"
                    else not ep["planned_stop_price"] > ep["entry_price"] > target):
                raise ValueError("invalid partial target geometry")
            scenarios.append({
                "episode": index, "order_id": ep["order_id"],
                "direction": ep["direction"], "fraction": frac,
                "partial_qty": qty, "threshold": target,
                "favorable_trade_peak": ep["entry_price"],
                "trade_cross_ms": None,
                "book_cross_ms": None,
                "full_depth_ms": None,
                "be_eligible_ms": None,
                "be_stop": None, "be_reason": None,
                "be_net_at_stop": None,
                "original_flags": ep["evidence_flags"],
                "entry_ms": ep["entry_ms"], "exit_ms": ep["exit_ms"],
            })
    for trade in trades:
        for scenario in scenarios:
            if not scenario["entry_ms"] < trade.event_ms < scenario["exit_ms"]:
                continue
            is_long = scenario["direction"] == "LONG"
            current = scenario["favorable_trade_peak"]
            if (trade.price > current if is_long else trade.price < current):
                scenario["favorable_trade_peak"] = trade.price
            if (scenario["trade_cross_ms"] is None
                    and ((trade.price > scenario["threshold"] and trade.side == "Buy")
                         if is_long else
                         (trade.price < scenario["threshold"] and trade.side == "Sell"))):
                scenario["trade_cross_ms"] = trade.event_ms
    for book in books:
        if not isinstance(book, BookState) or book.symbol != SYMBOL:
            raise ValueError("original same-symbol book states required")
        for scenario in scenarios:
            if not scenario["entry_ms"] < book.available_at_ms < scenario["exit_ms"]:
                continue
            is_long = scenario["direction"] == "LONG"
            mark = book.best_bid[0] if is_long else book.best_ask[0]
            if (scenario["book_cross_ms"] is None
                    and (mark >= scenario["threshold"] if is_long
                         else mark <= scenario["threshold"])):
                scenario["book_cross_ms"] = book.available_at_ms
            if scenario["full_depth_ms"] is None:
                if not _full_depth(book, scenario["direction"],
                                   scenario["threshold"], scenario["partial_qty"]):
                    continue
                scenario["full_depth_ms"] = book.available_at_ms
            if scenario["be_eligible_ms"] is not None:
                continue
            ep = episodes[scenario["episode"] - 1]
            result = _be_plan(ep, scenario["threshold"], scenario["partial_qty"], book)
            if scenario["be_reason"] is None:
                scenario["be_reason"] = result.reason
            if result.decision == STOP_NET_BREAK_EVEN:
                scenario["be_eligible_ms"] = book.available_at_ms
                scenario["be_stop"] = result.stop_price
                scenario["be_net_at_stop"] = result.net_pnl_usdt
    summarized = []
    for scenario in scenarios:
        ep = episodes[scenario["episode"] - 1]
        best = scenario["favorable_trade_peak"]
        mfe = (best - ep["entry_price"]) if ep["direction"] == "LONG" else (ep["entry_price"] - best)
        potential = abs(ep["planned_take_price"] - ep["entry_price"])
        assert potential > 0
        eligible = scenario["be_eligible_ms"] is not None
        candidate = scenario["full_depth_ms"] is not None
        summarized.append({
            "episode": scenario["episode"],
            "direction": scenario["direction"],
            "threshold_fraction": str(scenario["fraction"]),
            "partial_qty": str(scenario["partial_qty"]),
            "partial_limit_price": str(scenario["threshold"]),
            "original_entry_ms": scenario["entry_ms"],
            "original_exit_ms": scenario["exit_ms"],
            "mfe_trade_price": str(best),
            "mfe_price_distance": str(mfe),
            "mfe_fraction_of_original_take": str(mfe / potential),
            "first_aggressive_trade_through_ms": scenario["trade_cross_ms"],
            "first_book_threshold_cross_ms": scenario["book_cross_ms"],
            "first_full_depth_book_ms": scenario["full_depth_ms"],
            "be_price_placeable_book_ms": scenario["be_eligible_ms"],
            "hypothetical_net_be_stop": (
                str(scenario["be_stop"]) if eligible else None
            ),
            "hypothetical_net_at_be_stop": (
                str(scenario["be_net_at_stop"]) if eligible else None
            ),
            "be_first_reason": scenario["be_reason"],
            "entry_evidence_flags": scenario["original_flags"],
            "assessment": (
                "CONDITIONAL_BE_PRICE_CANDIDATE" if eligible else
                "FULL_DEPTH_ONLY_BE_NOT_PLACEABLE" if candidate else
                "NO_FULL_DEPTH_PARTIAL_CANDIDATE"
            ),
            "partial_fill_confirmed": False,
            "be_stop_amend_confirmed": False,
            "counterfactual_pnl_usdt": None,
        })
    comparison = []
    for frac in FRACTIONS:
        rows = [r for r in summarized if Decimal(r["threshold_fraction"]) == frac]
        comparison.append({
            "fraction_of_entry_to_take": str(frac),
            "episodes": len(rows),
            "aggressive_tape_through_count": sum(
                r["first_aggressive_trade_through_ms"] is not None for r in rows
            ),
            "full_25pct_partial_depth_candidate_count": sum(
                r["first_full_depth_book_ms"] is not None for r in rows
            ),
            "be_price_placeable_candidate_count": sum(
                r["be_price_placeable_book_ms"] is not None for r in rows
            ),
            "confirmed_partial_fills": 0,
            "confirmed_be_stop_amendments": 0,
            "scenario_net_pnl_usdt": None,
        })
    return {"summary": comparison, "episodes": summarized}


def analyze(*, receipt: Path, trades: Path, l2: Path) -> dict:
    if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 2_000_000:
        raise ValueError("original virtual result missing or oversized")
    with receipt.open("r", encoding="utf-8") as handle:
        original = json.load(handle)
    episodes = validated_episodes(original)
    tape = focused_tape(trades, episodes)
    begin = min(ep["entry_ms"] for ep in episodes)
    end = max(ep["exit_ms"] for ep in episodes) + 1
    book_states = iter_pinned_orderbook(
        l2, symbol=SYMBOL, depth=200, sha256=L2_SHA,
        start_ms=begin, end_exclusive_ms=end,
    )
    results = evaluate(episodes, tape, book_states)
    return {
        "schema": "ICNT_L2_PARTIAL_BE_RESEARCH_V1",
        "source_code_sha": SOURCE_CODE_SHA,
        "base_virtual_pnl_usdt": str(Decimal(str(original["result"]["realized_net_pnl"]))),
        "base_status": original["state"],
        "trade_archive_sha256": TRADE_SHA, "l2_sha256": L2_SHA,
        "partial_qty_fraction": str(PARTIAL_SHARE),
        "threshold_fractions": [str(f) for f in FRACTIONS],
        "net_be_policy": "EXISTING_RETEST_CAMPAIGN_NET_BREAK_EVEN_REMAINDER_STOP",
        "adverse_slippage_reserve_fraction": str(SLIPPAGE),
        "execution_model": "L2_MARKETABLE_LIMIT_FEASIBILITY_NOT_EXECUTED",
        "limitations": [
            "A historical quote does not prove that a counterfactual order was accepted or filled",
            "Original entry and exit windows are frozen; a BE amendment changes later admission",
            "Partial fills, order queue, STOP updates and scenario PnL are not simulated",
            "Original entry/STOP models remain conditional; these are not venue executions",
        ],
        **results,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--trades", type=Path, required=True)
    p.add_argument("--l2", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--code-sha", required=True)
    args = p.parse_args()
    head = subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True,
    ).strip()
    if head != args.code_sha or not (args.repo / "AGENTS.md").is_file():
        raise ValueError("exact isolated repository SHA required")
    if args.out.exists():
        raise ValueError("do not overwrite earlier owner report")
    output = analyze(receipt=args.baseline, trades=args.trades, l2=args.l2)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print("RESEARCH_STATUS=CONDITIONAL_FEASIBILITY_NOT_VIRTUAL_PNL")
    print("BASE_PNL_USDT=" + output["base_virtual_pnl_usdt"])
    for row in output["summary"]:
        print(
            f"THRESHOLD_{int(Decimal(row['fraction_of_entry_to_take']) * 100)}="
            f"tape_through={row['aggressive_tape_through_count']}/4 "
            f"l2_full_depth={row['full_25pct_partial_depth_candidate_count']}/4 "
            f"be_possible={row['be_price_placeable_candidate_count']}/4"
        )
    for episode in range(1, 5):
        selected = [
            row for row in output["episodes"] if row["episode"] == episode
        ]
        print(
            f"EPISODE_{episode}_MFE_R="
            f"{Decimal(selected[0]['mfe_fraction_of_original_take']):.3f} "
            + " ".join(
                f"T{int(Decimal(r['threshold_fraction']) * 100)}="
                f"{r['assessment']}" for r in selected
            )
        )
    print("COUNTERFACTUAL_PNL=UNPROVEN")
    print("REPORT=" + str(args.out))


if __name__ == "__main__":
    main()
