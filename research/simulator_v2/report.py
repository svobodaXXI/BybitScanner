"""Deterministic, offline-only SIMULATION report over verified closed M1 candles.

This evaluates a manual test schedule of already admitted virtual MARKET
requests. It does NOT decide trades, run Scanner/Robot, or claim strategy
profitability. Historical input must be verified by the existing cache loader.
No network, account credentials, PAPER, or other runtime connections are used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable, Mapping

from research.simulator_v2.cache import _checksum, _rows, iter_cached_m1_chunks
from research.simulator_v2.history import HistoryChunk, MINUTE_MS, SOURCE_ID_RE
from research.historical_market_replay import Candle
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.virtual_account import VirtualAccountSnapshot
from research.simulator_v2.virtual_exchange import MarketRequest

DAY_MS = 86_400_000


@dataclass(frozen=True)
class DailyEquity:
    utc_date: str
    last_closed_ms: int
    balance: Decimal
    equity: Decimal
    realized_net_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal

    def to_payload(self) -> dict[str, str | int]:
        return {
            "utc_date": self.utc_date,
            "last_closed_ms": self.last_closed_ms,
            "balance": str(self.balance),
            "equity": str(self.equity),
            "realized_net_pnl": str(self.realized_net_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "fees": str(self.fees),
        }


@dataclass(frozen=True)
class ReplayReport:
    simulation_run_id: str
    symbol: str
    source_id: str
    first_open_ms: int
    last_closed_ms: int
    minutes: int
    chunks: int
    chunk_sha256: tuple[str, ...]
    initial_balance: Decimal
    final_balance: Decimal
    final_equity: Decimal
    final_position_quantity: Decimal
    realized_net_pnl: Decimal
    unrealized_pnl: Decimal
    total_net_pnl: Decimal
    total_fees: Decimal
    return_percent: Decimal
    max_drawdown_percent: Decimal
    virtual_fills: int
    pending_order_id: str | None
    daily_equity: tuple[DailyEquity, ...]
    namespace: str = "SIMULATION"
    scenario_type: str = "EXPLICIT_TEST_ORDERS_NOT_STRATEGY"

    def to_payload(self) -> dict[str, object]:
        return {
            "namespace": self.namespace,
            "scenario_type": self.scenario_type,
            "simulation_run_id": self.simulation_run_id,
            "symbol": self.symbol,
            "source_id": self.source_id,
            "first_open_ms": self.first_open_ms,
            "last_closed_ms": self.last_closed_ms,
            "minutes": self.minutes,
            "chunks": self.chunks,
            "chunk_sha256": list(self.chunk_sha256),
            "initial_balance": str(self.initial_balance),
            "final_balance": str(self.final_balance),
            "final_equity": str(self.final_equity),
            "final_position_quantity": str(self.final_position_quantity),
            "realized_net_pnl": str(self.realized_net_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "total_net_pnl": str(self.total_net_pnl),
            "total_fees": str(self.total_fees),
            "return_percent": str(self.return_percent),
            "max_drawdown_percent": str(self.max_drawdown_percent),
            "virtual_fills": self.virtual_fills,
            "pending_order_id": self.pending_order_id,
            "daily_equity": [day.to_payload() for day in self.daily_equity],
        }


def run_verified_chunks(
    session: VirtualReplaySession,
    chunks: Iterable[HistoryChunk],
    *,
    order_schedule: Mapping[int, MarketRequest] | None = None,
    on_committed_m1: Callable[[VirtualReplaySession, Candle], None] | None = None,
) -> ReplayReport:
    """Single-use, synchronous run of already verified chunks.

    Requests are explicit preapproved SCENARIO inputs keyed by the M1 close
    timestamp. No strategy logic is inferred; the schedule must not be used
    to claim causal Robot performance. The passed session is mutated by design.
    A rejected/partial archive raises without producing a success report.
    """
    if not isinstance(session, VirtualReplaySession):
        raise TypeError("an isolated VirtualReplaySession is required")
    if session.virtual_time_ms is not None or session.account.fills:
        raise ValueError("report requires a new, unused SIMULATION session")
    if order_schedule is None:
        order_schedule = {}
    if not isinstance(order_schedule, Mapping):
        raise TypeError("schedule must be a mapping of closed-M1 time to request")
    if on_committed_m1 is not None and not callable(on_committed_m1):
        raise TypeError("SIMULATION M1 callback must be callable")
    if on_committed_m1 is not None and order_schedule:
        raise ValueError("cannot combine strategy replay with manual order schedule")
    for timestamp, request in order_schedule.items():
        if type(timestamp) is not int or timestamp < 0 or timestamp % MINUTE_MS:
            raise ValueError("schedule uses an invalid M1 close timestamp")
        if not isinstance(request, MarketRequest) or request.namespace != "SIMULATION":
            raise ValueError("schedule accepts only internal virtual MARKET requests")

    first_open = previous_end = None
    source_id = None
    hashes: list[str] = []
    seen_scheduled: set[int] = set()
    minutes = 0
    peak = session.account.initial_balance
    max_drawdown = Decimal(0)
    days: list[DailyEquity] = []
    active_day: int | None = None
    latest_snapshot: VirtualAccountSnapshot | None = None

    for chunk in chunks:
        if not isinstance(chunk, HistoryChunk) or chunk.symbol != session.account.symbol:
            raise ValueError("foreign or invalid SIMULATION market chunk")
        if not chunk.candles or chunk.start_ms < 0 or chunk.end_ms <= chunk.start_ms:
            raise ValueError("empty or invalid market chunk")
        if chunk.end_ms - chunk.start_ms != len(chunk.candles) * MINUTE_MS:
            raise ValueError("market chunk duration does not match its candles")
        if previous_end is not None and previous_end != chunk.start_ms:
            raise ValueError("market archive has a gap or overlapping chunks")
        if not isinstance(chunk.source_id, str) or not SOURCE_ID_RE.fullmatch(chunk.source_id):
            raise ValueError("invalid SIMULATION market source identity")
        if _checksum(_rows(chunk.candles)) != chunk.sha256:
            raise ValueError("SIMULATION market chunk checksum mismatch")
        if source_id is not None and source_id != chunk.source_id:
            raise ValueError("market source changed during virtual replay")
        if source_id is None:
            source_id = chunk.source_id
        if first_open is None:
            first_open = chunk.start_ms
        # Prevalidate the entire chunk before moving virtual time.
        for i, candle in enumerate(chunk.candles):
            if candle.start_ms != chunk.start_ms + i * MINUTE_MS or candle.interval_ms != MINUTE_MS:
                raise ValueError("market chunk contains an invalid candle sequence")
        for candle in chunk.candles:
            current_day = candle.start_ms // DAY_MS
            if active_day is not None and current_day != active_day:
                assert latest_snapshot is not None
                days.append(_day_entry(active_day, latest_snapshot))
            latest_snapshot = session.step(candle)
            # Only committed closed M1 may trigger a new strategy LIMIT; its
            # fill is eligible at the NEXT M1. Callback error blocks report.
            if on_committed_m1 is not None:
                on_committed_m1(session, candle)
            minutes += 1
            active_day = current_day
            if latest_snapshot.equity > peak:
                peak = latest_snapshot.equity
            drawdown = (peak - latest_snapshot.equity) * 100 / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            request = order_schedule.get(candle.end_ms)
            if request is not None:
                session.submit(request)
                seen_scheduled.add(candle.end_ms)
        previous_end = chunk.end_ms
        hashes.append(chunk.sha256)

    if latest_snapshot is None or active_day is None or first_open is None:
        raise ValueError("no complete closed M1 candles in virtual replay")
    if len(seen_scheduled) != len(order_schedule):
        raise ValueError("order schedule references a minute outside the archive")
    days.append(_day_entry(active_day, latest_snapshot))
    return ReplayReport(
        simulation_run_id=session.account.simulation_run_id,
        symbol=session.account.symbol, source_id=source_id,
        first_open_ms=first_open, last_closed_ms=previous_end,
        minutes=minutes, chunks=len(hashes), chunk_sha256=tuple(hashes),
        initial_balance=latest_snapshot.initial_balance,
        final_balance=latest_snapshot.balance,
        final_equity=latest_snapshot.equity,
        final_position_quantity=latest_snapshot.position_quantity,
        realized_net_pnl=latest_snapshot.realized_net_pnl,
        unrealized_pnl=latest_snapshot.unrealized_pnl,
        total_net_pnl=latest_snapshot.total_net_pnl,
        total_fees=latest_snapshot.fees,
        return_percent=(latest_snapshot.equity - latest_snapshot.initial_balance)
        * 100 / latest_snapshot.initial_balance,
        max_drawdown_percent=max_drawdown,
        virtual_fills=latest_snapshot.applied_fills,
        pending_order_id=(session.exchange.pending.order_id
                          if session.exchange.pending is not None else None),
        daily_equity=tuple(days),
    )


def _day_entry(day_number: int, snapshot: VirtualAccountSnapshot) -> DailyEquity:
    return DailyEquity(
        utc_date=datetime.fromtimestamp(day_number * 86400, timezone.utc).date().isoformat(),
        last_closed_ms=snapshot.as_of_ms, balance=snapshot.balance,
        equity=snapshot.equity, realized_net_pnl=snapshot.realized_net_pnl,
        unrealized_pnl=snapshot.unrealized_pnl, fees=snapshot.fees,
    )


def run_cached_archive(
    *, cache_dir: Path, simulation_run_id: str, symbol: str,
    initial_balance: Decimal, start_ms: int, end_ms: int,
    latest_closed_boundary_ms: int,
    source_id: str = "BYBIT_PUBLIC_V5_M1", chunk_minutes: int = 1440,
    taker_fee_rate: Decimal = Decimal("0.0006"),
    order_schedule: Mapping[int, MarketRequest] | None = None,
) -> ReplayReport:
    """Strict offline run: missing cache chunks always fail, NEVER fetch.

    To prepare the archive first, call iter_cached_m1_chunks separately using
    a public read-only market fetcher, then call this offline-only entrypoint.
    """
    def no_network(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("SIMULATION archive incomplete; offline replay cannot fetch")

    market = iter_cached_m1_chunks(
        cache_dir=cache_dir, symbol=symbol, start_ms=start_ms,
        end_ms=end_ms, latest_closed_boundary_ms=latest_closed_boundary_ms,
        chunk_minutes=chunk_minutes, source_id=source_id,
        fetch_candles=no_network,
    )
    session = VirtualReplaySession(
        simulation_run_id=simulation_run_id, symbol=symbol,
        initial_balance=initial_balance, taker_fee_rate=taker_fee_rate,
    )
    return run_verified_chunks(session, market, order_schedule=order_schedule)
