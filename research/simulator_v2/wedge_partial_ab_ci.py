"""Bounded public-archive Wedge A/B study. SIMULATION only, never production.

Uses the repository's original Wedge Scanner/Robot and protected virtual LIMIT.
Variant B is an independent, per-entry OHLC counterfactual; it never mutates
the native Robot, exchange or PAPER/runtime. Trading days are fixed ex ante.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D, ROUND_DOWN, ROUND_UP
from pathlib import Path
import hashlib
import json
import tempfile
from urllib.request import Request, urlopen

from research.simulator_v2.trade_archive import MAX_ARCHIVE_BYTES, parse_local_trade_day
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.wedge_backtest import run_verified_wedge_chunks
from research.simulator_v2.wedge_observer import WedgeScannerConfig
from research.simulator_v2.wedge_robot_observer import SimWedgeRobotConfig
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings

SYMBOL = "ICNTUSDT"
DAYS = tuple(date(2026, 11, 7) + timedelta(days=i) for i in range(4))
FEE = D("0.0006")
TICK = D("0.0001")
STEP = D("1")
FRACTION = D("0.25")
TRIGGER_R = D("2")
INITIAL_BALANCE = D("5000")
# These are frozen *research* terms from the earlier ICNT episode, NOT a
# historical exchange metadata snapshot or production 1-WV allocation.
CONTRACTS_PER_WV = D("862")


def timestamp(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)


def archives():
    """Only completed UTC days, official public trade archive, strict provenance."""
    end_boundary = timestamp(DAYS[-1] + timedelta(days=1))
    with tempfile.TemporaryDirectory(prefix="wedge-ab-official-") as temp:
        chunks, provenance = [], []
        for day in DAYS:
            name = f"{SYMBOL}{day.isoformat()}.csv.gz"
            url = f"https://public.bybit.com/trading/{SYMBOL}/{name}"
            path = Path(temp) / name
            request = Request(url, method="GET", headers={
                "User-Agent": "BybitScanner-SimulatorV2-Research/1.0",
            })
            n = 0
            with urlopen(request, timeout=35) as response, path.open("xb") as output:
                if response.geturl() != url:
                    raise ValueError("unapproved public archive redirect")
                while True:
                    buf = response.read(1024 * 1024)
                    if not buf:
                        break
                    n += len(buf)
                    if n > MAX_ARCHIVE_BYTES:
                        raise ValueError("public trade archive exceeds hard cap")
                    output.write(buf)
            chunk, digest = parse_local_trade_day(
                path, symbol=SYMBOL, utc_day=day,
                latest_closed_boundary_ms=end_boundary,
            )
            chunks.append(chunk)
            provenance.append({
                "day": day.isoformat(), "source_url": url,
                "raw_archive_sha256": digest, "derived_m1_sha256": chunk.sha256,
                "bytes": n, "bars": len(chunk.candles),
            })
        yield tuple(chunks), provenance


def model_one(candles, entry, original_exit, stop, take, variant):
    """Next-open, stop-first, tighten-only fee-aware B; no invented fills."""
    side = "LONG" if entry.side == "BUY" else "SHORT"
    sign = D(1) if side == "LONG" else D(-1)
    size = entry.quantity
    remaining = size
    entry_price = entry.price
    entry_fee = entry.fee
    realized_gross = D(0)
    exit_fees = D(0)
    partials = 0
    partial_queued = False
    partial_done = False
    active_stop = stop
    peak = D(0)
    dd = D(0)
    exit_reason = "OPEN"
    exit_time = None
    exit_price = None
    for bar in candles:
        if bar.start_ms < entry.virtual_time_ms:
            continue
        # A command only exists after the previous bar CLOSED. Existing
        # protection wins on an adverse/terminal opening gap.
        open_terminal = (
            bar.open <= active_stop or bar.open >= take
            if side == "LONG" else
            bar.open >= active_stop or bar.open <= take
        )
        if variant == "B" and partial_queued and not open_terminal:
            q = (remaining * FRACTION / STEP).to_integral_value(rounding=ROUND_DOWN) * STEP
            if 0 < q < remaining:
                fill = bar.open
                realized_gross += (fill - entry_price) * sign * q
                exit_fees += fill * q * FEE
                remaining -= q
                partials += 1
                partial_done = True
                # Fee-aware threshold includes all entry and exit fees.
                if side == "LONG":
                    target = ((remaining * entry_price - realized_gross + entry_fee + exit_fees)
                              / (remaining * (1 - FEE)))
                    candidate = (target / TICK).to_integral_value(rounding=ROUND_UP) * TICK
                    if active_stop < candidate < bar.open:
                        active_stop = candidate
                else:
                    target = ((remaining * entry_price + realized_gross - entry_fee - exit_fees)
                              / (remaining * (1 + FEE)))
                    candidate = (target / TICK).to_integral_value(rounding=ROUND_DOWN) * TICK
                    if bar.open < candidate < active_stop:
                        active_stop = candidate
            partial_queued = False
        if side == "LONG":
            stop_hit = bar.low <= active_stop
            take_hit = bar.high >= take
            ref = min(bar.open, active_stop) if stop_hit else take
        else:
            stop_hit = bar.high >= active_stop
            take_hit = bar.low <= take
            ref = max(bar.open, active_stop) if stop_hit else take
        if stop_hit or take_hit:
            realized_gross += (ref - entry_price) * sign * remaining
            exit_fees += ref * remaining * FEE
            remaining = D(0)
            exit_reason = "STOP" if stop_hit else "TAKE"
            exit_time = bar.end_ms
            exit_price = ref
        equity = realized_gross - entry_fee - exit_fees
        if remaining:
            equity += (bar.close - entry_price) * sign * remaining
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
        if not remaining:
            break
        if variant == "B" and not partial_done and not partial_queued:
            risk = (entry_price - stop) * sign
            trigger = entry_price + sign * TRIGGER_R * risk
            if risk > 0 and (bar.high >= trigger if side == "LONG" else bar.low <= trigger):
                partial_queued = True
    net = realized_gross - entry_fee - exit_fees if not remaining else None
    return {
        "net": str(net) if net is not None else None,
        "reason": exit_reason, "exit_time": exit_time,
        "exit_price": str(exit_price) if exit_price is not None else None,
        "partials": partials, "max_close_mark_dd": str(dd),
        "open_quantity": str(remaining),
    }


def main() -> None:
    with open("wedge_ab_result.json", "w", encoding="utf-8") as outcome:
        try:
            data = study()
        except Exception as exc:
            data = {
                "status": "DATA_BLOCKED", "error_type": type(exc).__name__,
                "error": str(exc)[:280], "namespace": "SIMULATION",
            }
            json.dump(data, outcome, indent=2)
            print(json.dumps(data))
            raise
        json.dump(data, outcome, indent=2)
        print(json.dumps(data, indent=2))


def study():
    chunks, provenance = next(archives())
    session = VirtualReplaySession(
        simulation_run_id="icnt_wedge_ab_20261107",
        symbol=SYMBOL, initial_balance=INITIAL_BALANCE,
        wedge_scanner_config=WedgeScannerConfig(window_bars=50, mode="hunter", min_score=50),
        wedge_robot_config=SimWedgeRobotConfig(
            selected_patterns=frozenset({"Falling Wedge", "Rising Wedge"}), tick_size=TICK,
        ),
        wedge_risk_settings=SimWedgeRiskSettings(
            tick_size=TICK, contracts_per_working_volume=CONTRACTS_PER_WV,
            quantity_step=STEP, minimum_quantity=STEP,
            max_notional_usdt=D("5000"), max_risk_usdt=D("500"),
            entry_fee_rate=FEE, exit_fee_rate=FEE,
        ),
    )
    protections = {}
    native_submit = session.submit_protected_preview

    def capture(preview):
        native_submit(preview)
        protections[preview.request.order_id] = {
            "stop": preview.stop_price, "take": preview.take_price,
        }

    session.submit_protected_preview = capture
    result = run_verified_wedge_chunks(
        session, chunks, start_ms=timestamp(DAYS[0]),
        end_inclusive_ms=timestamp(DAYS[-1] + timedelta(days=1)) - 60000,
    )
    fills = {fill.fill_id: fill for fill in session.account.fills}
    bars = [bar for chunk in chunks for bar in chunk.candles]
    comparisons, excluded = [], []
    for order_id, protection in protections.items():
        entry = fills.get(order_id + "_fill")
        if entry is None:
            continue  # native limit never filled
        exits = [
            (reason, fills[order_id + "_" + reason.lower() + "_fill"])
            for reason in ("STOP", "TAKE")
            if order_id + "_" + reason.lower() + "_fill" in fills
        ]
        if len(exits) != 1:
            excluded.append({"id": order_id, "reason": "OPEN_OR_UNPROVEN_EXIT"})
            continue
        reason, original_exit = exits[0]
        if original_exit.virtual_time_ms <= entry.virtual_time_ms:
            excluded.append({"id": order_id, "reason": "ENTRY_BAR_EXIT_AMBIGUOUS"})
            continue
        a = model_one(bars, entry, original_exit, protection["stop"], protection["take"], "A")
        # STRICT parity with ORIGINAL native virtual exchange before evaluating B.
        baseline_net = (
            (original_exit.price - entry.price) *
            (D(1) if entry.side == "BUY" else D(-1)) * entry.quantity
            - entry.fee - original_exit.fee
        )
        if (a["reason"] != reason or a["exit_time"] != original_exit.virtual_time_ms
                or a["exit_price"] != str(original_exit.price)
                or a["net"] is None or D(a["net"]) != baseline_net):
            excluded.append({"id": order_id, "reason": "NATIVE_BASELINE_PARITY_FAILURE"})
            continue
        b = model_one(bars, entry, original_exit, protection["stop"], protection["take"], "B")
        if b["net"] is None:
            excluded.append({"id": order_id, "reason": "B_POSITION_REMAINS_OPEN"})
            continue
        comparisons.append({
            "entry_id": order_id, "side": entry.side,
            "entry_time_ms": entry.virtual_time_ms,
            "A": a, "B": b, "difference": str(D(b["net"]) - D(a["net"])),
        })
    sum_a = sum((D(x["A"]["net"]) for x in comparisons), D(0))
    sum_b = sum((D(x["B"]["net"]) for x in comparisons), D(0))
    return {
        "namespace": "SIMULATION", "status": "COMPLETE" if comparisons else "DATA_INSUFFICIENT",
        "scope": "ICNTUSDT " + DAYS[0].isoformat() + " through " + DAYS[-1].isoformat() + " UTC completed days", 
        "uncovered_days": {"2026-11-11": "two missing trade-derived M1; no imputation", "2026-11-12": "separate contiguous window not yet checked"},
        "nov_13": "not included: UTC day incomplete at study design time",
        "source_type": "BYBIT_PUBLIC_TRADES_DERIVED_M1_NOT_OFFICIAL_KLINE",
        "provenance": provenance, "native_scanner_observations": result.scanner_wedge_observations,
        "native_robot_retests": result.robot_retests_in_period,
        "native_protected_limits": result.submitted_protected_limits,
        "native_stop_exits": result.stop_exits, "native_take_exits": result.take_exits,
        "native_virtual_fills": result.report.virtual_fills,
        "matched_trade_count": len(comparisons), "excluded": excluded,
        "A_net_usdt": str(sum_a), "B_net_usdt": str(sum_b),
        "B_minus_A_usdt": str(sum_b - sum_a),
        "A_STOP": sum(x["A"]["reason"] == "STOP" for x in comparisons),
        "A_TAKE": sum(x["A"]["reason"] == "TAKE" for x in comparisons),
        "B_STOP": sum(x["B"]["reason"] == "STOP" for x in comparisons),
        "B_TAKE": sum(x["B"]["reason"] == "TAKE" for x in comparisons),
        "B_partial_fills": sum(x["B"]["partials"] for x in comparisons),
        "max_per_trade_close_mark_DD_A": str(max((D(x["A"]["max_close_mark_dd"]) for x in comparisons), default=D(0))),
        "max_per_trade_close_mark_DD_B": str(max((D(x["B"]["max_close_mark_dd"]) for x in comparisons), default=D(0))),
        "trades": comparisons,
        "limitations": [
            "Trade-level paired counterfactual, NOT a native portfolio B run or trading recommendation.",
            "Current ICNT tick/step (attested 2026-11-13) are not a historical metadata snapshot.",
            "Fixed research sizing 862 contracts per 1 WV, not asserted production sizing.",
            "OHLC stop-first and next-open partial are modeled; no venue fill/queue proof.",
            "Max DD is worst per-trade close-mark drawdown, not portfolio max drawdown.",
            "A/B outcomes use the same original Scanner/Robot entry decisions; altered B exits do not change later admissions.",
        ],
    }


if __name__ == "__main__":
    main()
