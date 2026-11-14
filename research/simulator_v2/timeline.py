"""Isolated M1 virtual-time feed for the future Scanner/Robot SIMULATION.

This is infrastructure, NOT a strategy, Robot, or exchange simulator.
It reuses research.historical_market_replay.Candle and the existing closed
higher-timeframe accumulator. No filesystem, network, API keys or PAPER access.

IMPORTANT: stages must be pure/read-only or idempotent for a given minute.
A failed stage pauses without publishing its minute; resume retries that minute.
Future real Scanner/Robot integration must preserve this same fail-closed barrier
with isolated transactional state. Do not connect production runtime directly.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Callable, Mapping

from research.historical_market_replay import Candle
from research.historical_candle_feed import (
    ClosedHigherTimeframeFeed, FIVE_MINUTES_MS,
)

MINUTE_MS = 60_000
HOUR_MS = 3_600_000
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,30}$")


@dataclass(frozen=True)
class MinuteFrame:
    """Only already-CLOSED market information at one virtual UTC minute."""
    symbol: str
    simulation_run_id: str
    virtual_time_ms: int
    minute: Candle
    latest_closed_5m: Candle | None
    newly_closed_5m: Candle | None
    latest_closed_1h: Candle | None
    newly_closed_1h: Candle | None


@dataclass(frozen=True)
class StageFact:
    """Exact fact emitted by a supplied stage. No inferred trading statuses."""
    kind: str
    entity_id: str = ""
    details: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.kind or not self.kind.strip():
            raise ValueError("stage event kind is required")
        if any(
            not isinstance(pair, tuple) or len(pair) != 2
            or any(not isinstance(value, str) for value in pair)
            for pair in self.details
        ):
            raise ValueError("stage event details must be string pairs")


@dataclass(frozen=True)
class SimulationEvent:
    event_id: str
    sequence: int
    simulation_run_id: str
    symbol: str
    virtual_time_ms: int
    source: str
    kind: str
    entity_id: str = ""
    details: tuple[tuple[str, str], ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "simulation_run_id": self.simulation_run_id,
            "namespace": "SIMULATION",
            "symbol": self.symbol,
            "virtual_time_ms": self.virtual_time_ms,
            "source": self.source,
            "kind": self.kind,
            "entity_id": self.entity_id,
            "details": dict(self.details),
        }


Stage = Callable[[MinuteFrame, tuple[SimulationEvent, ...]], tuple[StageFact, ...]]


class StepBlocked(RuntimeError):
    """One virtual minute could not commit. No later bar may be processed."""


class IsolatedTimeline:
    """One symbol, one run, one committed minute at a time.

    Scanner -> Robot -> Exchange callbacks are not installed by default.
    Market-only use is safe without them; this does NOT claim Robot integration.
    A callback's facts are staged until the entire minute completes.
    """

    def __init__(
        self, *, simulation_run_id: str, symbol: str,
        scanner: Stage | None = None,
        robot: Stage | None = None,
        exchange: Stage | None = None,
    ) -> None:
        if not RUN_ID_RE.fullmatch(simulation_run_id):
            raise ValueError("invalid SIMULATION run ID")
        if not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT"):
            raise ValueError("invalid single-run symbol")
        self.simulation_run_id = simulation_run_id
        self.symbol = symbol
        self._stages = (
            ("SCANNER", scanner), ("ROBOT", robot), ("EXCHANGE", exchange),
        )
        self._journal: list[SimulationEvent] = []
        self._last_close_ms: int | None = None
        self._pending_5m: tuple[Candle, ...] = ()
        self._latest_5m: Candle | None = None
        self._latest_1h: Candle | None = None
        self._higher = ClosedHigherTimeframeFeed()
        self.paused_stage: str | None = None
        self.paused_reason: str | None = None

    @property
    def virtual_time_ms(self) -> int | None:
        return self._last_close_ms

    @property
    def events(self) -> tuple[SimulationEvent, ...]:
        return tuple(self._journal)

    @property
    def processed_minutes(self) -> int:
        return sum(event.kind == "M1_CLOSED" and event.source == "MARKET"
                   for event in self._journal)

    def resume(self) -> None:
        """Allow retry after correcting the failing adapter, not skip a bar."""
        self.paused_stage = self.paused_reason = None

    def events_at(self, virtual_time_ms: int) -> tuple[SimulationEvent, ...]:
        """Rewind projection never mutates the authoritative run journal."""
        if self._last_close_ms is None or virtual_time_ms > self._last_close_ms:
            raise ValueError("virtual cursor is beyond committed history")
        return tuple(e for e in self._journal if e.virtual_time_ms <= virtual_time_ms)

    def step(self, minute: Candle) -> MinuteFrame:
        if self.paused_stage is not None:
            raise StepBlocked(
                f"paused in {self.paused_stage}: {self.paused_reason}; "
                "resume before retrying the same minute"
            )
        if not isinstance(minute, Candle) or minute.interval_ms != MINUTE_MS:
            raise ValueError("M1 closed Candle required")
        if minute.start_ms % MINUTE_MS:
            raise ValueError("unaligned UTC M1 candle")
        if self._last_close_ms is not None and minute.start_ms != self._last_close_ms:
            raise ValueError("missing, duplicate, or out-of-order M1 candle")

        # Work on temporary state. A callback error cannot expose a half-minute
        # of new data to the journal or advance the virtual market cursor.
        pending = tuple(
            b for b in self._pending_5m
            if b.start_ms // FIVE_MINUTES_MS == minute.start_ms // FIVE_MINUTES_MS
        ) + (minute,)
        new_5m = None
        if minute.end_ms % FIVE_MINUTES_MS == 0:
            if len(pending) == 5 and pending[0].start_ms == minute.end_ms - FIVE_MINUTES_MS:
                new_5m = Candle(
                    start_ms=pending[0].start_ms,
                    interval_ms=FIVE_MINUTES_MS,
                    open=pending[0].open,
                    high=max(bar.high for bar in pending),
                    low=min(bar.low for bar in pending),
                    close=pending[-1].close,
                    volume=sum((bar.volume for bar in pending), Decimal(0)),
                )
            pending = ()
        higher = deepcopy(self._higher)
        latest_1h = self._latest_1h
        new_1h = None
        if new_5m is not None:
            latest_1h, _, new_1h, _ = higher.observe_closed_five_minute(new_5m)
        latest_5m = new_5m or self._latest_5m
        frame = MinuteFrame(
            self.symbol, self.simulation_run_id, minute.end_ms, minute,
            latest_5m, new_5m, latest_1h, new_1h,
        )
        staged: list[SimulationEvent] = []

        def record(source: str, fact: StageFact) -> None:
            sequence = len(self._journal) + len(staged) + 1
            staged.append(SimulationEvent(
                event_id=f"SIMULATION:{self.simulation_run_id}:{sequence}",
                sequence=sequence, simulation_run_id=self.simulation_run_id,
                symbol=self.symbol, virtual_time_ms=minute.end_ms,
                source=source, kind=fact.kind,
                entity_id=fact.entity_id, details=fact.details,
            ))

        record("MARKET", StageFact("M1_CLOSED"))
        if new_5m is not None:
            record("MARKET", StageFact("M5_CLOSED"))
        if new_1h is not None:
            record("MARKET", StageFact("H1_CLOSED"))
        stage_name = "SCANNER"
        try:
            for stage_name, callback in self._stages:
                if callback is None:
                    continue
                facts = callback(frame, tuple(staged))
                if not isinstance(facts, tuple) or any(
                    not isinstance(fact, StageFact) for fact in facts
                ):
                    raise TypeError(f"{stage_name} must return a tuple of StageFact")
                for fact in facts:
                    record(stage_name, fact)
        except Exception as exc:
            self.paused_stage = stage_name
            self.paused_reason = f"{type(exc).__name__}: {exc}"
            raise StepBlocked(self.paused_reason) from exc

        self._pending_5m = pending
        self._higher = higher
        self._latest_5m = latest_5m
        self._latest_1h = latest_1h
        self._last_close_ms = minute.end_ms
        self._journal.extend(staged)
        return frame
