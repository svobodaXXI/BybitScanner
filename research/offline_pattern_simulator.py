"""Pure offline, closed-bar simulation kernel for research-only pattern adapters.

No exchange, credential, Robot, PAPER database or wall-clock dependencies.
Signals must be computed by their caller using candles through signal bar only.
All money uses Decimal; an ambiguous intrabar STOP/TAKE resolves at STOP.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping


def D(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("non-finite numerical input")
    return result


@dataclass(frozen=True)
class Candle:
    time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        if self.time_ms < 0 or min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("invalid candle")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("inconsistent OHLC")


@dataclass(frozen=True)
class Signal:
    """Decision known at the CLOSE of candle at index signal_index."""
    signal_index: int
    pattern: str
    side: str
    stop: Decimal
    take: Decimal


@dataclass(frozen=True)
class Trade:
    pattern: str
    side: str
    signal_time_ms: int
    entry_time_ms: int
    exit_time_ms: int
    entry: Decimal
    exit: Decimal
    exit_reason: str
    quantity: Decimal
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal


@dataclass(frozen=True)
class Result:
    simulation_run_id: str
    namespace: str
    initial_equity: Decimal
    final_equity: Decimal
    max_drawdown: Decimal
    trades: tuple[Trade, ...]
    equity_curve: tuple[Decimal, ...]


def simulate(
    candles: Iterable[Candle],
    signals: Iterable[Signal],
    *,
    simulation_run_id: str,
    initial_equity: Decimal = Decimal("1000"),
    notional: Decimal = Decimal("100"),
    fee_rate: Decimal = Decimal("0.0006"),
    slippage_rate: Decimal = Decimal("0.0002"),
) -> Result:
    """Next-open entry, stop/take on subsequent OHLC, no look-ahead or order endpoints.

    Only one position at a time. A signal at close i may first execute at open i+1.
    Last bar signals cannot execute. Signals overlapping an active trade are skipped.
    If an exit gap crosses a stop, the worse gap-open fill is used.
    """
    if not simulation_run_id or "/" in simulation_run_id or "\\" in simulation_run_id:
        raise ValueError("invalid SIMULATION run identity")
    initial_equity, notional = D(initial_equity), D(notional)
    fee_rate, slippage_rate = D(fee_rate), D(slippage_rate)
    if initial_equity <= 0 or notional <= 0 or not (0 <= fee_rate < 1) or not (0 <= slippage_rate < 1):
        raise ValueError("invalid simulation costs or capital")
    bars = tuple(candles)
    if not bars or any(b.time_ms <= a.time_ms for a, b in zip(bars, bars[1:])):
        raise ValueError("candles must have strictly increasing timestamps")
    decisions: dict[int, Signal] = {}
    for signal in signals:
        if signal.signal_index < 0 or signal.signal_index >= len(bars):
            raise ValueError("signal index outside history")
        if signal.signal_index in decisions:
            raise ValueError("multiple simultaneous signals require explicit selection")
        if not signal.pattern.strip() or signal.side not in ("LONG", "SHORT"):
            raise ValueError("invalid signal identity/side")
        if min(signal.stop, signal.take) <= 0:
            raise ValueError("invalid exit levels")
        decisions[signal.signal_index] = signal
    equity = initial_equity
    high_water = equity
    max_dd = Decimal("0")
    curve = [equity]
    trades: list[Trade] = []
    active: tuple[Signal, int, Decimal, Decimal] | None = None
    for i, bar in enumerate(bars):
        if active is None and (i - 1) in decisions:
            s = decisions[i - 1]
            entry = bar.open * (1 + slippage_rate if s.side == "LONG" else 1 - slippage_rate)
            if (s.side == "LONG" and s.stop < entry < s.take) or (
                s.side == "SHORT" and s.take < entry < s.stop
            ):
                active = (s, i, entry, notional / entry)
            else:
                # A stale or already crossed setup is not admitted.
                active = None
        if active is not None:
            s, entry_index, entry, qty = active
            stop_hit = bar.low <= s.stop if s.side == "LONG" else bar.high >= s.stop
            take_hit = bar.high >= s.take if s.side == "LONG" else bar.low <= s.take
            if stop_hit or take_hit or i == len(bars) - 1:
                reason = "STOP" if stop_hit else "TAKE" if take_hit else "END"
                target = s.stop if stop_hit else s.take if take_hit else bar.close
                # Gap at the first tradable price takes precedence over a stop target.
                if stop_hit and ((s.side == "LONG" and bar.open < target) or
                                 (s.side == "SHORT" and bar.open > target)):
                    target = bar.open
                exit_price = target * (1 - slippage_rate if s.side == "LONG" else 1 + slippage_rate)
                gross = (exit_price - entry) * qty * (1 if s.side == "LONG" else -1)
                fees = (entry + exit_price) * qty * fee_rate
                net = gross - fees
                equity += net
                trades.append(Trade(s.pattern, s.side, bars[s.signal_index].time_ms,
                                    bars[entry_index].time_ms, bar.time_ms, entry,
                                    exit_price, reason, qty, gross, fees, net))
                active = None
        high_water = max(high_water, equity)
        max_dd = max(max_dd, high_water - equity)
        curve.append(equity)
    return Result(simulation_run_id, "SIMULATION", initial_equity, equity,
                  max_dd, tuple(trades), tuple(curve))


def candles_from_rows(rows: Iterable[Mapping[str, object]]) -> tuple[Candle, ...]:
    """Adapt the existing historical replay's time/open/high/low/close rows."""
    return tuple(Candle(int(row["time"]), D(row["open"]), D(row["high"]),
                        D(row["low"]), D(row["close"])) for row in rows)
