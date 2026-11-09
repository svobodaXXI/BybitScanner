"""Causal multi-pattern orchestration for the existing offline SIMULATION replay.

No second execution engine, exchange orders, credentials, filesystem, or PAPER
ledger access. Adapters receive only CLOSED 5m bars and closed H1/H4 context.
Adapter order is the explicit tie-break priority for simultaneous setups.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping, Sequence

from research.historical_candle_feed import (
    FIVE_MINUTES_MS, ClosedMultiTimeframeView, replay_with_closed_context,
)
from research.historical_market_replay import (
    Candle, EntryIntent, ReplayResult, ReplayVisualEvent, SimulatedTrade,
)


@dataclass(frozen=True)
class PatternAdapter:
    """Caller-provided strategy; NEVER supply it candles beyond the current close."""
    name: str
    on_closed_context: Callable[[ClosedMultiTimeframeView], EntryIntent | None]


@dataclass(frozen=True)
class PatternDecision:
    signal_time_ms: int
    candidates: tuple[str, ...]
    submitted_pattern: str | None


@dataclass(frozen=True)
class PatternTrade:
    pattern: str
    trade: SimulatedTrade


@dataclass(frozen=True)
class PatternPerformance:
    pattern: str
    candidate_signals: int
    completed_trades: int
    net_pnl: Decimal
    fees: Decimal
    win_rate: Decimal | None
    profit_factor: Decimal | None


@dataclass(frozen=True)
class PatternSimulation:
    replay: ReplayResult
    decisions: tuple[PatternDecision, ...]
    completed_trades: tuple[PatternTrade, ...]
    per_pattern: tuple[PatternPerformance, ...]
    visual_events: tuple[ReplayVisualEvent, ...]
    closed_trade_drawdown: Decimal


def candles_from_rows(rows: Sequence[Mapping[str, object]]) -> tuple[Candle, ...]:
    """Reuse the public historical replay's time/OHLCV row format."""
    return tuple(Candle(
        start_ms=int(row["time"]), interval_ms=FIVE_MINUTES_MS,
        open=row["open"], high=row["high"], low=row["low"],
        close=row["close"], volume=row["volume"],
    ) for row in rows)


def simulate_patterns(
    *,
    simulation_run_id: str,
    candles: Sequence[Candle],
    adapters: Sequence[PatternAdapter],
    geometry_warmup_candles: Sequence[Candle] = (),
    initial_cash: Decimal = Decimal("5000"),
    taker_fee_rate: Decimal = Decimal("0.0006"),
    adverse_slippage_rate: Decimal = Decimal("0.0002"),
    minimum_reward_risk: Decimal | None = None,
    maximum_stop_fraction: Decimal | None = None,
) -> PatternSimulation:
    """Run a single-position multi-pattern historical experiment.

    Only the next bar OPEN can fill a just-closed-bar decision. In a collision,
    first adapter in `adapters` wins; all candidates remain in the decision
    trace. Positions and exits use the existing research executor. Metrics
    exclude unrealized PnL; the original replay reports marked equity
    separately. No strategy is considered approved just by being an adapter.
    """
    names = tuple(a.name for a in adapters)
    if not names or any(not n or not n.strip() for n in names) or len(set(names)) != len(names):
        raise ValueError("provide unique, named pattern adapters in priority order")
    bars = tuple(candles)
    if not bars or any(b.interval_ms != FIVE_MINUTES_MS or
                       b.start_ms % FIVE_MINUTES_MS for b in bars):
        raise ValueError("simulation requires UTC-aligned 5m candles")
    if any(b.start_ms != a.end_ms for a, b in zip(bars, bars[1:])):
        raise ValueError("missing/overlapping historical candle; refusing simulation")

    submitted: dict[int, str] = {}
    decisions: list[PatternDecision] = []
    events: list[ReplayVisualEvent] = []

    def choose(view: ClosedMultiTimeframeView) -> EntryIntent | None:
        found: list[tuple[str, EntryIntent]] = []
        for adapter in adapters:
            intent = adapter.on_closed_context(view)
            if intent is not None:
                if not isinstance(intent, EntryIntent):
                    raise TypeError(f"{adapter.name} must return EntryIntent or None")
                found.append((adapter.name, intent))
        chosen = found[0] if found and not view.five_minute.in_position else None
        decision_time = view.five_minute.signal_time_ms
        decisions.append(PatternDecision(
            decision_time, tuple(name for name, _ in found),
            chosen[0] if chosen is not None else None,
        ))
        if chosen is not None:
            submitted[decision_time] = chosen[0]
            return chosen[1]
        return None

    replay = replay_with_closed_context(
        simulation_run_id=simulation_run_id,
        candles=bars,
        geometry_warmup_candles=geometry_warmup_candles,
        on_closed_context=choose,
        on_visual_event=events.append,
        max_open_positions=1,
        initial_cash=initial_cash,
        taker_fee_rate=taker_fee_rate,
        adverse_slippage_rate=adverse_slippage_rate,
        minimum_reward_risk=minimum_reward_risk,
        maximum_stop_fraction=maximum_stop_fraction,
    )

    # An entry at bar i's OPEN is attributable only to the decision at the
    # immediately preceding CLOSED bar. Reject anything else, never guess.
    preceding_close = {
        bars[i].start_ms: bars[i - 1].end_ms for i in range(1, len(bars))
    }
    labelled: list[PatternTrade] = []
    for trade in replay.trades:
        signal_time = preceding_close.get(trade.entry_time_ms)
        pattern = submitted.get(signal_time) if signal_time is not None else None
        if pattern is None:
            raise ValueError("simulated fill lacks a causal pattern decision")
        labelled.append(PatternTrade(pattern, trade))

    grouped: list[PatternPerformance] = []
    for name in names:
        associated = [item.trade for item in labelled if item.pattern == name]
        winners = [t.net_pnl for t in associated if t.net_pnl > 0]
        losses = [-t.net_pnl for t in associated if t.net_pnl < 0]
        profit_factor = (
            sum(winners, Decimal(0)) / sum(losses, Decimal(0))
            if losses else None
        )
        grouped.append(PatternPerformance(
            pattern=name,
            candidate_signals=sum(name in d.candidates for d in decisions),
            completed_trades=len(associated),
            net_pnl=sum((t.net_pnl for t in associated), Decimal(0)),
            fees=sum((t.fees for t in associated), Decimal(0)),
            win_rate=Decimal(len(winners)) / len(associated) if associated else None,
            profit_factor=profit_factor,
        ))

    closed_balance = replay.initial_cash
    high_water = closed_balance
    max_drawdown = Decimal(0)
    for trade in replay.trades:
        closed_balance += trade.net_pnl
        high_water = max(high_water, closed_balance)
        max_drawdown = max(max_drawdown, high_water - closed_balance)

    return PatternSimulation(
        replay=replay,
        decisions=tuple(decisions),
        completed_trades=tuple(labelled),
        per_pattern=tuple(grouped),
        visual_events=tuple(events),
        closed_trade_drawdown=max_drawdown,
    )
