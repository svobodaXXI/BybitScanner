from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
from typing import Mapping

from terminal.domain.models import Category, Price, Quantity, Symbol
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_http_server import (
    ProtectionIngressOverflow,
    SerializedPaperRuntime,
)
from terminal.runtime.paper_runtime import PaperRuntime


RUNTIME_REPLAY_SCHEMA_VERSION = 1


class _ReplayBookProvider:
    def get_book(self, _symbol: Symbol) -> None:
        return None


@dataclass(frozen=True)
class RuntimeReplayEvent:
    event_id: str
    symbol: str
    coverage_role: str
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    received_at_ms: int
    source_generation: int
    source_sequence: int
    source_update_id: int
    source_event_at_ms: int
    source_matching_engine_cts_ms: int | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "RuntimeReplayEvent":
        required = {
            "event_id",
            "symbol",
            "coverage_role",
            "bid",
            "ask",
            "received_at_ms",
            "source_generation",
            "source_sequence",
            "source_update_id",
            "source_event_at_ms",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise ValueError(f"runtime replay event missing fields: {', '.join(missing)}")
        event_id = str(payload["event_id"]).strip()
        symbol = str(payload["symbol"]).strip().upper()
        coverage_role = str(payload["coverage_role"]).strip().upper()
        if not event_id or not symbol or not coverage_role:
            raise ValueError("runtime replay event identity fields must be non-empty")
        bid = Decimal(str(payload["bid"]))
        ask = Decimal(str(payload["ask"]))
        bid_size = Decimal(str(payload.get("bid_size", "1")))
        ask_size = Decimal(str(payload.get("ask_size", "1")))
        if bid <= 0 or ask <= 0 or bid >= ask or bid_size <= 0 or ask_size <= 0:
            raise ValueError("runtime replay event book must have positive bid < ask and size")
        return cls(
            event_id=event_id,
            symbol=symbol,
            coverage_role=coverage_role,
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            received_at_ms=int(payload["received_at_ms"]),
            source_generation=int(payload["source_generation"]),
            source_sequence=int(payload["source_sequence"]),
            source_update_id=int(payload["source_update_id"]),
            source_event_at_ms=int(payload["source_event_at_ms"]),
            source_matching_engine_cts_ms=(
                None
                if payload.get("source_matching_engine_cts_ms") is None
                else int(payload["source_matching_engine_cts_ms"])
            ),
        )

    def book(self) -> NormalizedOrderBook:
        return NormalizedOrderBook(
            symbol=Symbol(self.symbol),
            bids=(PriceLevel(Price(self.bid), Quantity(self.bid_size)),),
            asks=(PriceLevel(Price(self.ask), Quantity(self.ask_size)),),
            health=BookHealth.READY,
            received_at_ms=self.received_at_ms,
            available_depth=1,
            source_generation=self.source_generation,
            source_sequence=self.source_sequence,
            source_update_id=self.source_update_id,
            source_event_at_ms=self.source_event_at_ms,
            source_matching_engine_cts_ms=self.source_matching_engine_cts_ms,
        )


@dataclass(frozen=True)
class RuntimeReplayFixture:
    name: str
    events: tuple[RuntimeReplayEvent, ...]

    @classmethod
    def load(cls, path: str | Path) -> "RuntimeReplayFixture":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema_version") != RUNTIME_REPLAY_SCHEMA_VERSION:
            raise ValueError(
                "unsupported runtime replay schema_version "
                f"{payload.get('schema_version')!r}"
            )
        name = str(payload.get("name", "")).strip()
        raw_events = payload.get("events")
        if not name or not isinstance(raw_events, list) or not raw_events:
            raise ValueError("runtime replay fixture requires name and non-empty events")
        return cls(
            name=name,
            events=tuple(RuntimeReplayEvent.from_mapping(item) for item in raw_events),
        )


@dataclass(frozen=True)
class RuntimeReplayResult:
    processed_event_ids: tuple[str, ...]
    overflow_event_ids: tuple[str, ...]
    event_errors: tuple[str, ...]
    metrics: Mapping[str, object]
    continuity_loss: tuple[str, str] | None

    @property
    def metric_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self.metrics))


def _instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR,
        "BTCUSDT",
        "LinearPerpetual",
        "Trading",
        "BTC",
        "USDT",
        "USDT",
        Decimal("0.5"),
        Decimal("1000000"),
        Decimal("0.5"),
        Decimal("0.001"),
        Decimal("100"),
        Decimal("50"),
        Decimal("0.001"),
        Decimal("5"),
    )


def _make_runtime(database_path: Path) -> PaperRuntime:
    primary = _instrument()
    return PaperRuntime(
        database_path,
        book_provider=_ReplayBookProvider(),
        instrument_snapshot=primary,
        instrument_provider=lambda symbol: replace(primary, symbol=symbol),
    )


def run_runtime_replay(
    fixture: RuntimeReplayFixture,
    *,
    protection_ingress_capacity: int = 64,
) -> RuntimeReplayResult:
    """Replay ordered Robot market events through the production owner boundary.

    Producer delivery is continuous: every fixture event is offered with
    SerializedPaperRuntime.enqueue() before the single final completion fence.
    There is deliberately no owner-drain call between events or batches.
    """
    processed: list[str] = []
    overflows: list[str] = []
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as temp:
        owner = SerializedPaperRuntime(
            lambda: _make_runtime(Path(temp) / "paper_runtime.sqlite3"),
            protection_ingress_capacity=protection_ingress_capacity,
        )
        try:
            for event in fixture.events:
                book = event.book()

                def process(runtime: PaperRuntime, *, event=event, book=book) -> None:
                    try:
                        runtime.process_robot_market_event(
                            event.symbol,
                            book,
                            event_id=event.event_id,
                            received_at_ms=event.received_at_ms,
                        )
                    except BaseException as exc:
                        errors.append(
                            f"{event.event_id}:{type(exc).__name__}:{exc}"
                        )
                        raise
                    else:
                        processed.append(event.event_id)

                try:
                    owner.enqueue(
                        process,
                        symbol=event.symbol,
                        coverage_role=event.coverage_role,
                    )
                except ProtectionIngressOverflow:
                    overflows.append(event.event_id)

            # One fence after producer completion is allowed. It proves that all
            # admitted FIFO events ahead of it have finished; unlike the old
            # synthetic test, it never paces or drains the producer mid-stream.
            owner.call(lambda runtime: None, timeout=30.0)
            continuity_loss = owner.call(
                lambda runtime: runtime.robot_protection_continuity_loss(),
                timeout=30.0,
            )
            metrics = dict(owner.protection_ingress_metrics())
            return RuntimeReplayResult(
                processed_event_ids=tuple(processed),
                overflow_event_ids=tuple(overflows),
                event_errors=tuple(errors),
                metrics=metrics,
                continuity_loss=continuity_loss,
            )
        finally:
            owner.close()
