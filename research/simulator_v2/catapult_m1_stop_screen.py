"""Offline STOP-only Wedge M1 screen; never an executable catapult study.

Accepts owner-provided PAPER episode facts + public Bybit M1, not venue orderbook
or Robot host-receipt data. Alternative exits use a future bar's reported OPEN
as an *illustrative assumption* with a separately declared adverse slippage
allowance, never as an evidenced fill. All decisions use earlier COMPLETE bars.
No network, storage, market subscriptions, orders, Robot imports or tuning.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

D = Decimal
MINUTE_MS = 60_000
BPS = D("10000")


class M1ScreenBlocked(ValueError):
    """Archive/provenance gap means no quantitative claim is permissible."""


def _d(value: object, field: str, *, positive: bool = False) -> Decimal:
    try:
        parsed = D(str(value))
    except (ValueError, ArithmeticError, TypeError) as exc:
        raise M1ScreenBlocked(f"invalid {field}") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise M1ScreenBlocked(f"invalid {field}")
    return parsed


def _millis(value: object) -> int:
    if isinstance(value, bool):
        raise M1ScreenBlocked("invalid timestamp")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise M1ScreenBlocked("invalid timestamp") from exc
    if n < 0 or str(n) != str(value):
        raise M1ScreenBlocked("invalid timestamp")
    return n


def _next_minute(ms: int) -> int:
    return (ms + MINUTE_MS - 1) // MINUTE_MS * MINUTE_MS


@dataclass(frozen=True)
class FixedM1Probe:
    timeout_minutes: int
    min_favorable_bps: Decimal
    adverse_slippage_bps: Decimal

    def __post_init__(self) -> None:
        if type(self.timeout_minutes) is not int or self.timeout_minutes <= 0:
            raise M1ScreenBlocked("positive whole-minute timeout required")
        if _d(self.min_favorable_bps, "min_favorable_bps") <= 0:
            raise M1ScreenBlocked("positive followthrough threshold required")
        if _d(self.adverse_slippage_bps, "adverse_slippage_bps") < 0:
            raise M1ScreenBlocked("negative slippage impossible")
        if self.adverse_slippage_bps >= BPS:
            raise M1ScreenBlocked("slippage exceeds supported range")


def _candles(item: Mapping) -> dict[int, tuple[Decimal, Decimal, Decimal, Decimal]]:
    if item.get("status") != "COUNT_MATCH" or not isinstance(item.get("candles"), list):
        raise M1ScreenBlocked("M1 source count not confirmed")
    bars = item["candles"]
    if not bars or len(bars) != int(item.get("expected_count", -1)):
        raise M1ScreenBlocked("M1 coverage mismatch")
    result = {}
    for c in bars:
        if not isinstance(c, list) or len(c) < 5:
            raise M1ScreenBlocked("invalid M1 candle")
        t = _millis(c[0])
        op, hi, lo, cl = (_d(v, "M1 OHLC", positive=True) for v in c[1:5])
        if (t % MINUTE_MS != 0 or t in result or
                hi < max(op, cl) or lo > min(op, cl)):
            raise M1ScreenBlocked("corrupt or repeated M1 candle")
        result[t] = op, hi, lo, cl
    times = sorted(result)
    if any(b - a != MINUTE_MS for a, b in zip(times, times[1:])):
        raise M1ScreenBlocked("incomplete M1 timeline")
    return result


def screen_stop_only_wedge_episodes(
    facts: Mapping, m1: Mapping, probe: FixedM1Probe,
) -> dict[str, object]:
    """Return source-backed *conditional* aggregate, NEVER estimated real savings.

    No non-STOP controls and no original frozen STOP data are present in this
    archive; this must not be selected/optimized as a Robot strategy.
    """
    if not isinstance(probe, FixedM1Probe):
        raise M1ScreenBlocked("immutable study settings required")
    if (m1.get("source") != "BYBIT_V5_PUBLIC_LINEAR_M1"
            or facts.get("source_revision") != m1.get("source_revision_reference")):
        raise M1ScreenBlocked("unmatched PAPER/venue provenance")
    episodes, items = facts.get("episodes"), m1.get("items")
    if not isinstance(episodes, list) or not episodes or not isinstance(items, list):
        raise M1ScreenBlocked("missing observed episodes or M1 source")
    by_symbol = {}
    for i in items:
        symbol = i.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol in by_symbol:
            raise M1ScreenBlocked("M1 symbol missing or duplicate")
        by_symbol[symbol] = _candles(i)

    baseline, proxy = D("0"), D("0")
    would_close, original_stop_first, followed = 0, 0, 0
    identifiers = set()
    for row in episodes:
        f, w = row.get("facts"), row.get("wedge")
        if (row.get("facts_status") != 200 or row.get("wedge_status") != 200
                or not isinstance(f, dict) or not isinstance(w, dict)
                or f.get("namespace") != "PAPER_READ_ONLY"
                or f.get("source") != "PAPER_EXECUTIONS_ATTRIBUTED"
                or f.get("owner") != "ROBOT"
                or f.get("cohort") != "ROBOT"
                or w.get("exit_reason") != "STOP"
                or f.get("source_revision") != facts["source_revision"]
                or w.get("source_revision") != facts["source_revision"]
                or f.get("trade_episode_id") != w.get("trade_episode_id")
                or f.get("symbol") != w.get("symbol")
                or f.get("side") not in ("LONG", "SHORT")):
            raise M1ScreenBlocked("unverified native STOP episode")
        trade_id = f.get("trade_episode_id")
        symbol = f["symbol"]
        if not trade_id or trade_id in identifiers or symbol not in by_symbol:
            raise M1ScreenBlocked("episode id duplicate or M1 symbol unavailable")
        identifiers.add(trade_id)
        allocations = f.get("execution_allocations")
        if (not isinstance(allocations, list) or len(allocations) != 2
                or [a.get("allocation_role") for a in allocations] != ["OPEN", "CLOSE"]
                or any(a.get("controller") != "ROBOT" for a in allocations)):
            raise M1ScreenBlocked("unsupported execution attribution")
        op, cl = allocations
        qty, close_qty = _d(op["allocated_quantity"], "qty", positive=True), _d(cl["allocated_quantity"], "close qty", positive=True)
        entry, exit_price = _d(op["execution_price"], "entry", positive=True), _d(cl["execution_price"], "exit", positive=True)
        entry_fee, exit_fee = _d(op["allocated_fee"], "entry fee"), _d(cl["allocated_fee"], "exit fee")
        direction = f["side"]
        if (qty != close_qty or entry_fee < 0 or exit_fee < 0
                or op.get("order_side") != ("Buy" if direction == "LONG" else "Sell")
                or cl.get("order_side") != ("Sell" if direction == "LONG" else "Buy")):
            raise M1ScreenBlocked("inconsistent native fill/fee/side")
        t0, t1 = _millis(op["occurred_at_ms"]), _millis(cl["occurred_at_ms"])
        if (t0 >= t1 or t0 != f.get("opened_at_ms")
                or t1 != f.get("closed_at_ms")):
            raise M1ScreenBlocked("ambiguous native execution timeline")
        sign = D("1") if direction == "LONG" else D("-1")
        booked = _d(f["pnl_usdt"], "realized net")
        recomputed = sign * qty * (exit_price - entry) - entry_fee - exit_fee
        if abs(recomputed - booked) > D("0.000000001"):
            raise M1ScreenBlocked("PAPER closed net PnL doesn't reconcile")
        baseline += booked
        decision = _next_minute(t0 + probe.timeout_minutes * MINUTE_MS)
        if decision >= t1:
            original_stop_first += 1
            proxy += booked
            continue
        bars = by_symbol[symbol]
        if decision not in bars:
            raise M1ScreenBlocked("proposed M1-open quote absent")
        first_complete_start = _next_minute(t0)
        previous = [bars[t] for t in range(first_complete_start, decision, MINUTE_MS)
                    if t in bars]
        expected = (decision - first_complete_start) // MINUTE_MS
        if len(previous) != expected:
            raise M1ScreenBlocked("causal full-M1 lookback gap")
        best = (max([entry] + [c[1] for c in previous]) if sign > 0
                else min([entry] + [c[2] for c in previous]))
        favorable_bps = sign * (best - entry) / entry * BPS
        if favorable_bps >= probe.min_favorable_bps:
            followed += 1
            proxy += booked
            continue
        # This is an illustrative open, NOT a venue quote/Robot fill.
        quote_proxy = bars[decision][0]
        slip = probe.adverse_slippage_bps / BPS
        assumed_fill = quote_proxy * (D("1") - sign * slip)
        # Infer venue fee-rate only from this real trade's known close fee.
        assumed_exit_fee_rate = exit_fee / (exit_price * qty)
        projected = (sign * qty * (assumed_fill - entry) - entry_fee
                     - assumed_fill * qty * assumed_exit_fee_rate)
        proxy += projected
        would_close += 1

    return {
        "status": "INDICATIVE_M1_OPEN_PRICE_PROXY_NOT_EXECUTABLE",
        "validation": "STOP_ONLY_SELECTED_LOSERS_NO_HOLDOUT",
        "trading_authorized": False,
        "source_complete_l2_publictrade": False,
        "episode_count": len(episodes),
        "conditional_early_exits": would_close,
        "baseline_stop_first": original_stop_first,
        "followthrough_observed": followed,
        "baseline_realized_net_usdt": str(baseline),
        "conditional_proxy_net_usdt": str(proxy),
        "hypothetical_delta_usdt_not_realized": str(proxy - baseline),
        "assumed_slippage_bps": str(probe.adverse_slippage_bps),
        "entry_fee": "ACTUAL_EXECUTION",
        "exit_fee": "INFERRED_ACTUAL_EXECUTION_RATE",
        "alternative_fill": "NEXT_RECORDED_PUBLIC_M1_OPEN_NOT_PROVEN_EXECUTABLE",
    }
