"""Offline, deterministic, in-memory market replay. No PAPER/runtime imports or IO.

Strategies see a *closed* bar only. A submitted intent fills no earlier than the
next bar open; stops/takes use adverse (stop-first) ordering when both are hit.
This kernel is not an approved trading strategy or a live execution adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, Literal, Sequence

Side = Literal["LONG", "SHORT"]


def _decimal(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid replay decimal") from exc
    if not number.is_finite():
        raise ValueError("non-finite replay decimal")
    return number


@dataclass(frozen=True)
class Candle:
    start_ms: int
    interval_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.interval_ms <= 0:
            raise ValueError("invalid candle time")
        for key in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, key, _decimal(getattr(self, key)))
        if min(self.open, self.high, self.low, self.close) <= 0 or self.volume < 0:
            raise ValueError("invalid candle price or volume")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("invalid candle OHLC range")

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.interval_ms


@dataclass(frozen=True)
class EntryIntent:
    side: Side
    quantity: Decimal
    stop: Decimal
    take: Decimal

    def __post_init__(self) -> None:
        if self.side not in ("LONG", "SHORT"):
            raise ValueError("unsupported replay side")
        for key in ("quantity", "stop", "take"):
            object.__setattr__(self, key, _decimal(getattr(self, key)))
        if min(self.quantity, self.stop, self.take) <= 0:
            raise ValueError("entry size and protection must be positive")


@dataclass(frozen=True)
class ClosedBarView:
    """Information released at a completed candle's end; no future bars."""

    bar: Candle
    closed_history: tuple[Candle, ...]
    signal_time_ms: int
    in_position: bool


@dataclass(frozen=True)
class SimulatedTrade:
    trade_id: str
    side: Side
    quantity: Decimal
    entry_time_ms: int
    entry_price: Decimal
    exit_time_ms: int
    exit_price: Decimal
    exit_reason: str
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    source: str = "SIMULATION"


@dataclass(frozen=True)
class ReplayResult:
    simulation_run_id: str
    source: str
    trades: tuple[SimulatedTrade, ...]
    initial_cash: Decimal
    realized_cash: Decimal
    open_position: bool
    final_mark_to_market_equity: Decimal
    processed_bars: int


def replay_candles(
    *,
    simulation_run_id: str,
    candles: Sequence[Candle],
    on_closed_bar: Callable[[ClosedBarView], EntryIntent | None],
    initial_cash: Decimal = Decimal("5000"),
    taker_fee_rate: Decimal = Decimal("0.0006"),
    adverse_slippage_rate: Decimal = Decimal("0"),
) -> ReplayResult:
    """Run an isolated chronological simulation without network, file or DB writes.

    No leverage/margin is modelled: initial entry notional must be cash-funded.
    Outputs are entirely in memory, never a PAPER trade or report.
    """
    if not simulation_run_id or not simulation_run_id.strip() or any(
        not (c.isalnum() or c in "-_") for c in simulation_run_id
    ):
        raise ValueError("simulation_run_id must be a non-empty safe identifier")
    cash = _decimal(initial_cash)
    fee_rate = _decimal(taker_fee_rate)
    slip = _decimal(adverse_slippage_rate)
    if cash <= 0 or not (Decimal("0") <= fee_rate < 1) or not (Decimal("0") <= slip < 1):
        raise ValueError("invalid replay capital or costs")
    bars = tuple(candles)
    if not bars:
        raise ValueError("replay needs historical candles")
    for i, bar in enumerate(bars):
        if not isinstance(bar, Candle):
            raise TypeError("replay accepts Candle objects only")
        if i and bar.start_ms < bars[i - 1].end_ms:
            raise ValueError("overlapping or non-chronological candles")

    trades: list[SimulatedTrade] = []
    pending: EntryIntent | None = None
    position: tuple[EntryIntent, Decimal, int, Decimal] | None = None
    history: list[Candle] = []

    def entry_fill(price: Decimal, side: Side) -> Decimal:
        return price * (1 + slip if side == "LONG" else 1 - slip)

    def exit_fill(price: Decimal, side: Side) -> Decimal:
        return price * (1 - slip if side == "LONG" else 1 + slip)

    for bar in bars:
        # At bar open: only current OPEN is known. Its HIGH/LOW/CLOSE cannot
        # influence entry; pending requests were created at a *previous* close.
        if pending is not None:
            executable = entry_fill(bar.open, pending.side)
            if (
                (pending.side == "LONG" and not pending.stop < executable < pending.take)
                or (pending.side == "SHORT" and not pending.take < executable < pending.stop)
            ):
                pending = None  # stale/gap-invalidated entry; do not chase
            else:
                entry_fee = executable * pending.quantity * fee_rate
                if executable * pending.quantity + entry_fee <= cash:
                    position = (pending, executable, bar.start_ms, entry_fee)
                    cash -= entry_fee
                pending = None

        if position is not None:
            intent, entry, entry_ms, entry_fee = position
            # Gap through stop is filled at worse open, never at an ideal stop.
            if intent.side == "LONG":
                stop_hit = bar.low <= intent.stop
                take_hit = bar.high >= intent.take
                exit_reference = min(bar.open, intent.stop) if stop_hit else intent.take
            else:
                stop_hit = bar.high >= intent.stop
                take_hit = bar.low <= intent.take
                exit_reference = max(bar.open, intent.stop) if stop_hit else intent.take
            if stop_hit or take_hit:
                exit_price = exit_fill(exit_reference, intent.side)
                exit_fee = exit_price * intent.quantity * fee_rate
                direction = Decimal(1) if intent.side == "LONG" else Decimal(-1)
                gross = (exit_price - entry) * intent.quantity * direction
                net = gross - entry_fee - exit_fee
                cash += gross - exit_fee
                trades.append(
                    SimulatedTrade(
                        trade_id=f"SIMULATION:{simulation_run_id}:{len(trades) + 1}",
                        side=intent.side,
                        quantity=intent.quantity,
                        entry_time_ms=entry_ms,
                        entry_price=entry,
                        exit_time_ms=bar.end_ms,
                        exit_price=exit_price,
                        exit_reason="STOP" if stop_hit else "TAKE",
                        gross_pnl=gross,
                        fees=entry_fee + exit_fee,
                        net_pnl=net,
                    )
                )
                position = None

        history.append(bar)
        # A strategy is called only AFTER bar completion; the view is frozen
        # to bars released up to this moment (not future/final pivot data).
        response = on_closed_bar(
            ClosedBarView(bar, tuple(history), bar.end_ms, position is not None)
        )
        if response is not None:
            if not isinstance(response, EntryIntent):
                raise TypeError("strategy must return EntryIntent or None")
            if position is None and pending is None:
                pending = response

    equity = cash
    if position is not None:
        intent, entry, _, _ = position
        direction = Decimal(1) if intent.side == "LONG" else Decimal(-1)
        equity += (bars[-1].close - entry) * intent.quantity * direction
    return ReplayResult(
        simulation_run_id=simulation_run_id,
        source="SIMULATION",
        trades=tuple(trades),
        initial_cash=_decimal(initial_cash),
        realized_cash=cash,
        open_position=position is not None,
        final_mark_to_market_equity=equity,
        processed_bars=len(bars),
    )
