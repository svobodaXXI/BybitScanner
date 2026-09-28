from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
from typing import Callable, Mapping

import requests

from terminal.domain.models import Category, Price, Quantity, Symbol, TradingAccountId
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_http_server import (
    ProtectionIngressOverflow,
    RobotProtectionCoverageManager,
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
    # Ingress metrics captured after the producer finished but before the owner
    # hold was released (only when owner_held_during_production=True).
    saturated_metrics: Mapping[str, object] | None = None

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


def _make_runtime(database_path: Path, *, geometry_index_provider=None) -> PaperRuntime:
    primary = _instrument()
    return PaperRuntime(
        database_path,
        book_provider=_ReplayBookProvider(),
        instrument_snapshot=primary,
        instrument_provider=lambda symbol: replace(primary, symbol=symbol),
        robot_latest_geometry_index_provider=geometry_index_provider,
    )


def _seed_pre_limit_candidates(
    runtime: PaperRuntime,
    symbols: tuple[str, ...],
    fixture_name: str,
    *,
    recovery_status: str,
    reason: str | None = None,
) -> None:
    """Durable APPROVED / RETEST_DETECTED candidates with NO limit_order_id.

    This is the incident's lifecycle state: no resting entry LIMIT exists, so no
    book event can fill anything yet.
    """
    account = TradingAccountId("paper")
    for index, symbol in enumerate(symbols):
        record, _ = runtime.store.create_robot_candidate(
            candidate_id=f"replay-pre-limit-{symbol.lower()}",
            trading_account_id=account, symbol=Symbol(symbol), status="APPROVED",
            signal_snapshot={"symbol": symbol, "pattern": "Falling Wedge",
                             "replay_fixture": fixture_name},
            approved_at_ms=1_000 + index, updated_at_ms=1_000 + index,
        )
        runtime.store.save_robot_candidate_state(
            record.candidate_id, status="APPROVED",
            robot_state={"phase": "RETEST_DETECTED", "execution": {}},
            expected_revision=record.state_revision, updated_at_ms=2_000 + index,
        )
    state = runtime.store.get_robot_runtime_state(account)
    runtime.store.update_robot_runtime_state(
        account, mode="ROBOT_RUNNING", recovery_status=recovery_status, reason=reason,
        expected_version=state.version, updated_at_ms=max(3_000, state.updated_at_ms + 1),
    )


def _offer(
    owner: SerializedPaperRuntime,
    event: RuntimeReplayEvent,
    *,
    processed: list[str],
    overflows: list[str],
    errors: list[str],
) -> None:
    """Offer one fixture event directly to the production protection enqueue boundary."""
    book = event.book()

    def process(runtime: PaperRuntime) -> None:
        try:
            runtime.process_robot_market_event(
                event.symbol,
                book,
                event_id=event.event_id,
                received_at_ms=event.received_at_ms,
            )
        except BaseException as exc:
            errors.append(f"{event.event_id}:{type(exc).__name__}:{exc}")
            raise
        else:
            processed.append(event.event_id)

    try:
        owner.enqueue(process, symbol=event.symbol, coverage_role=event.coverage_role)
    except ProtectionIngressOverflow:
        overflows.append(event.event_id)


def _hold_owner(
    owner: SerializedPaperRuntime, name: str,
) -> tuple[threading.Thread, threading.Event]:
    """Hold the owner inside one ordinary call() task, proven entered by handshake."""
    entered = threading.Event()
    release = threading.Event()

    def hold(_runtime: PaperRuntime) -> None:
        entered.set()
        release.wait(timeout=60.0)

    holder = threading.Thread(
        target=owner.call, args=(hold,), kwargs={"timeout": 60.0}, name=name, daemon=True,
    )
    holder.start()
    if not entered.wait(timeout=30.0):
        release.set()
        raise RuntimeError("runtime replay owner hold was never entered")
    return holder, release


def run_runtime_replay(
    fixture: RuntimeReplayFixture,
    *,
    protection_ingress_capacity: int = 64,
    owner_held_during_production: bool = False,
) -> RuntimeReplayResult:
    """Replay ordered Robot market events through the production owner boundary.

    Producer delivery is continuous: every fixture event is offered with
    SerializedPaperRuntime.enqueue() before the single final completion fence.
    There is deliberately no owner-drain call between events or batches.

    ``owner_held_during_production`` is a saturation characterization, not a
    product scenario: the owner is held for the whole stream so the ingress
    boundary and its fail-closed signals can be frozen exactly.
    """
    processed: list[str] = []
    overflows: list[str] = []
    errors: list[str] = []
    saturated_metrics: Mapping[str, object] | None = None

    with tempfile.TemporaryDirectory() as temp:
        owner = SerializedPaperRuntime(
            lambda: _make_runtime(Path(temp) / "paper_runtime.sqlite3"),
            protection_ingress_capacity=protection_ingress_capacity,
        )
        release = threading.Event()
        try:
            holder = None
            if owner_held_during_production:
                holder, release = _hold_owner(owner, "runtime-replay-owner-hold")
            for event in fixture.events:
                _offer(owner, event, processed=processed, overflows=overflows, errors=errors)
            if holder is not None:
                saturated_metrics = dict(owner.protection_ingress_metrics())
                release.set()
                holder.join(timeout=60.0)

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
                saturated_metrics=saturated_metrics,
            )
        finally:
            release.set()
            owner.close()


class _ReplayOrderBook:
    def __init__(self) -> None:
        self.payload: dict[str, object] = {}

    def snapshot(self) -> dict[str, object]:
        return dict(self.payload)


class _ReplaySymbolContext:
    """Test-only stand-in for a hub SymbolContext: no websocket, no network."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.reconnect_count = 0
        self.public_orderbook = _ReplayOrderBook()
        self._update_listeners: dict[str, object] = {}
        self._disconnect_listeners: dict[str, object] = {}

    def add_update_listener(self, name, listener) -> None:
        self._update_listeners[name] = listener

    def remove_update_listener(self, name) -> None:
        self._update_listeners.pop(name, None)

    def add_disconnect_listener(self, name, listener) -> None:
        self._disconnect_listeners[name] = listener

    def remove_disconnect_listener(self, name) -> None:
        self._disconnect_listeners.pop(name, None)

    def publish(self, event: RuntimeReplayEvent) -> None:
        self.public_orderbook.payload = {
            "state": "READY",
            "symbol": event.symbol,
            "bids": [{"price": str(event.bid), "size": str(event.bid_size)}],
            "asks": [{"price": str(event.ask), "size": str(event.ask_size)}],
            "receivedAt": event.received_at_ms,
            "sequence": event.source_sequence,
            "updateId": event.source_update_id,
            "timestamp": event.source_event_at_ms,
            "messageType": "delta",
        }
        for listener in tuple(self._update_listeners.values()):
            listener(event.event_id)


class _ReplayHub:
    def __init__(self) -> None:
        self.contexts: dict[str, _ReplaySymbolContext] = {}

    def subscribe(self, symbol: str) -> _ReplaySymbolContext:
        return self.contexts.setdefault(symbol, _ReplaySymbolContext(symbol))

    def discard(self, context: _ReplaySymbolContext) -> None:
        self.contexts.pop(context.symbol, None)


class _OfflineRecoverySession:
    """Refuses every REST recovery snapshot request; nothing leaves the process."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        self.requests.append((url, dict(params or {})))
        raise requests.ConnectionError("runtime replay is offline")


class _BoundedReconcileStall:
    """Condition-driven bounded stall of the production ``robot_reconcile()`` owner task.

    The long owner task is ``PaperRuntime.robot_reconcile()`` submitted through
    ``SerializedPaperRuntime.call()`` exactly as ``BackendRuntimeIntentPorts`` does.
    Its per-candidate geometry lookup (the 2026-09-27 incident's 9 s owner step) is the
    injected ``robot_latest_geometry_index_provider``: each lookup stays blocked until
    the producer has offered ``events_per_lookup`` more stream events. Handshakes only,
    never sleeps. The producer waits neither for ingress processing nor for the owner:
    between lookups it waits only for the long task to reach its next lookup or finish.
    """

    def __init__(self, events_per_lookup: int) -> None:
        if events_per_lookup <= 0:
            raise ValueError("events_per_lookup must be positive")
        self.events_per_lookup = events_per_lookup
        self.lookup_threads: list[str] = []
        self.stall_event_ids: list[tuple[str, ...]] = []
        self.pending_at_release = 0
        self.outcome = "not started"
        self._progress = threading.Condition()
        self._started = 0
        self._released = 0
        self._done = False

    def geometry_index(self, _symbol: str, _snapshot: Mapping[str, object]) -> int:
        with self._progress:
            index = self._started
            self._started += 1
            self.lookup_threads.append(threading.current_thread().name)
            self._progress.notify_all()
            if not self._progress.wait_for(lambda: self._released > index, timeout=30.0):
                raise RuntimeError("runtime replay stall was never released")
        return 0

    def release_all(self) -> None:
        with self._progress:
            self._released = 1 << 30
            self._progress.notify_all()

    def start(self, owner: SerializedPaperRuntime) -> threading.Thread:
        def run() -> None:
            try:
                result = owner.call(lambda runtime: runtime.robot_reconcile(), timeout=60.0)
                self.outcome = f"success={result.success} reason={result.reason}"
            except BaseException as exc:
                self.outcome = f"{type(exc).__name__}:{exc}"
            finally:
                with self._progress:
                    self._done = True
                    self._progress.notify_all()

        thread = threading.Thread(target=run, name="runtime-replay-reconcile", daemon=True)
        thread.start()
        return thread

    def _next_stall(self) -> bool:
        with self._progress:
            if not self._progress.wait_for(
                lambda: self._done or self._started > self._released, timeout=30.0,
            ):
                raise RuntimeError("runtime replay reconcile never reached a lookup")
            return self._started > self._released

    def drive(
        self,
        events: tuple[RuntimeReplayEvent, ...],
        offer: Callable[[RuntimeReplayEvent], None],
        pending: Callable[[], int],
    ) -> None:
        """Offer every stream event continuously across the stalls; no drain between."""
        stalled = self._next_stall()
        current: list[str] = []

        def close_stall() -> None:
            self.pending_at_release = max(self.pending_at_release, pending())
            self.stall_event_ids.append(tuple(current))

        for event in events:
            if stalled and len(current) == self.events_per_lookup:
                close_stall()
                current = []
                with self._progress:
                    self._released += 1
                    self._progress.notify_all()
                stalled = self._next_stall()
            offer(event)
            if stalled:
                current.append(event.event_id)
        if current:
            close_stall()


@dataclass(frozen=True)
class ManagerStallReplayResult:
    # Durable lifecycle state the replay started from.
    seeded_pre_limit: bool
    # Manager view right after the first production resync().
    covered_roles: Mapping[str, str]
    # Stall mechanism.
    stall_event_ids: tuple[tuple[str, ...], ...]
    lookup_threads: tuple[str, ...]
    pending_at_stall_release: int
    reconcile_outcome: str
    # Producer stream, partitioned by what the production manager did with each event.
    unsubscribed_event_ids: tuple[str, ...]
    delivered_event_ids: tuple[str, ...]
    admitted_event_ids: tuple[str, ...]
    overflow_event_ids: tuple[str, ...]
    suppressed_event_ids: tuple[str, ...]
    fence_overflows: int
    processed_event_ids: tuple[str, ...]
    # Health when the producer completed, and after the single final fence.
    health_after_producer: Mapping[str, object]
    final_health: Mapping[str, object]
    event_errors: tuple[str, ...]


def run_manager_stall_replay(
    fixture: RuntimeReplayFixture,
    *,
    stall_events_per_lookup: int,
    protection_ingress_capacity: int = 64,
) -> ManagerStallReplayResult:
    """Replay pre-LIMIT lifecycle candidates across a bounded owner stall, via the manager.

    Production path under test:
    ``RobotProtectionCoverageManager.resync()`` role discovery -> hub subscription ->
    ``_on_update`` -> ``SerializedPaperRuntime.enqueue`` -> ``PaperRuntime.
    process_robot_market_event``. Only the hub, its symbol contexts and the REST
    recovery session are offline doubles. The producer models the exchange stream: every
    fixture event happens, but only events for symbols the manager subscribed reach it.
    There is no mid-stream drain or fence; one fence follows producer completion.
    """
    symbols = tuple(dict.fromkeys(event.symbol for event in fixture.events))
    stall = _BoundedReconcileStall(stall_events_per_lookup)
    unsubscribed: list[str] = []
    delivered: list[str] = []
    admitted: list[str] = []
    overflowed: list[str] = []
    suppressed: list[str] = []
    processed: list[str] = []
    errors: list[str] = []
    fence_overflows = 0
    current_event: list[str | None] = [None]

    with tempfile.TemporaryDirectory() as temp:
        owner = SerializedPaperRuntime(
            lambda: _make_runtime(
                Path(temp) / "paper_runtime.sqlite3",
                geometry_index_provider=stall.geometry_index,
            ),
            protection_ingress_capacity=protection_ingress_capacity,
        )
        hub = _ReplayHub()
        manager = RobotProtectionCoverageManager(
            hub, owner, resync_interval_s=3600.0, recovery_session=_OfflineRecoverySession(),
        )
        reconciler: threading.Thread | None = None
        try:
            def seed(runtime: PaperRuntime) -> bool:
                _seed_pre_limit_candidates(
                    runtime, symbols, fixture.name,
                    recovery_status="RECONCILIATION_REQUIRED",
                    reason="maintenance reconciliation requested",
                )
                original = runtime.process_robot_market_event

                def recording(symbol, book, *, event_id, received_at_ms):
                    try:
                        result = original(
                            symbol, book, event_id=event_id, received_at_ms=received_at_ms,
                        )
                    except BaseException as exc:
                        errors.append(f"{event_id}:{type(exc).__name__}:{exc}")
                        raise
                    processed.append(event_id)
                    return result

                runtime.process_robot_market_event = recording
                account = TradingAccountId("paper")
                return all(
                    (state.robot_state or {}).get("phase") == "RETEST_DETECTED"
                    and not ((state.robot_state or {}).get("execution") or {}).get("limit_order_id")
                    and not runtime.store.load_active_paper_limits(account, state.symbol)
                    for state in runtime.store.load_active_robot_candidate_states(account)
                )

            seeded_pre_limit = owner.call(seed, timeout=30.0)

            production_enqueue = owner.enqueue

            def observed_enqueue(operation, *, symbol="", coverage_role="UNKNOWN"):
                nonlocal fence_overflows
                try:
                    production_enqueue(operation, symbol=symbol, coverage_role=coverage_role)
                except ProtectionIngressOverflow:
                    if symbol:
                        overflowed.append(current_event[0])
                    else:
                        fence_overflows += 1
                    raise
                if symbol:
                    admitted.append(current_event[0])

            owner.enqueue = observed_enqueue

            manager.resync()
            covered_roles = dict(manager.health()["coverage_roles"])

            reconciler = stall.start(owner)

            def offer(event: RuntimeReplayEvent) -> None:
                context = hub.contexts.get(event.symbol)
                if context is None:
                    unsubscribed.append(event.event_id)
                    return
                delivered.append(event.event_id)
                current_event[0] = event.event_id
                seen = len(admitted) + len(overflowed)
                context.publish(event)
                if len(admitted) + len(overflowed) == seen:
                    suppressed.append(event.event_id)

            stall.drive(
                fixture.events, offer,
                lambda: int(owner.protection_ingress_metrics()["current_pending"]),
            )
            current_event[0] = None
            health_after_producer = manager.health()

            stall.release_all()
            reconciler.join(timeout=60.0)
            # One fence after producer completion, as in run_runtime_replay().
            owner.call(lambda runtime: None, timeout=30.0)
            return ManagerStallReplayResult(
                seeded_pre_limit=seeded_pre_limit,
                covered_roles=covered_roles,
                stall_event_ids=tuple(stall.stall_event_ids),
                lookup_threads=tuple(stall.lookup_threads),
                pending_at_stall_release=stall.pending_at_release,
                reconcile_outcome=stall.outcome,
                unsubscribed_event_ids=tuple(unsubscribed),
                delivered_event_ids=tuple(delivered),
                admitted_event_ids=tuple(admitted),
                overflow_event_ids=tuple(overflowed),
                suppressed_event_ids=tuple(suppressed),
                fence_overflows=fence_overflows,
                processed_event_ids=tuple(processed),
                health_after_producer=health_after_producer,
                final_health=manager.health(),
                event_errors=tuple(errors),
            )
        finally:
            stall.release_all()
            manager.close()
            owner.close()


@dataclass(frozen=True)
class OwnerStallReplayResult:
    processed_event_ids: tuple[str, ...]
    overflow_event_ids: tuple[str, ...]
    event_errors: tuple[str, ...]
    # Fixture events offered while each stalled reconcile lookup was running.
    stall_event_ids: tuple[tuple[str, ...], ...]
    lookup_threads: tuple[str, ...]
    pending_at_stall_release: int
    reconcile_outcome: str
    metrics: Mapping[str, object]


def run_owner_stall_replay(
    fixture: RuntimeReplayFixture,
    *,
    stall_events_per_lookup: int,
    protection_ingress_capacity: int = 64,
) -> OwnerStallReplayResult:
    """Lower-level characterization: the same bounded stall, events offered DIRECTLY.

    Every fixture event goes straight to ``SerializedPaperRuntime.enqueue()``,
    bypassing the coverage manager and therefore any lifecycle/role decision. It
    characterizes the ingress itself under a bounded stall; it is not the R2 product
    contract because no lifecycle change can make it stop receiving these events.
    """
    symbols = tuple(dict.fromkeys(event.symbol for event in fixture.events))
    stall = _BoundedReconcileStall(stall_events_per_lookup)
    processed: list[str] = []
    overflows: list[str] = []
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as temp:
        owner = SerializedPaperRuntime(
            lambda: _make_runtime(
                Path(temp) / "paper_runtime.sqlite3",
                geometry_index_provider=stall.geometry_index,
            ),
            protection_ingress_capacity=protection_ingress_capacity,
        )
        try:
            owner.call(
                lambda runtime: _seed_pre_limit_candidates(
                    runtime, symbols, fixture.name,
                    recovery_status="RECONCILIATION_REQUIRED",
                    reason="maintenance reconciliation requested",
                ),
                timeout=30.0,
            )
            reconciler = stall.start(owner)
            stall.drive(
                fixture.events,
                lambda event: _offer(
                    owner, event, processed=processed, overflows=overflows, errors=errors,
                ),
                lambda: int(owner.protection_ingress_metrics()["current_pending"]),
            )
            stall.release_all()
            reconciler.join(timeout=60.0)

            # One fence after producer completion, as in run_runtime_replay().
            owner.call(lambda runtime: None, timeout=30.0)
            return OwnerStallReplayResult(
                processed_event_ids=tuple(processed),
                overflow_event_ids=tuple(overflows),
                event_errors=tuple(errors),
                stall_event_ids=tuple(stall.stall_event_ids),
                lookup_threads=tuple(stall.lookup_threads),
                pending_at_stall_release=stall.pending_at_release,
                reconcile_outcome=stall.outcome,
                metrics=dict(owner.protection_ingress_metrics()),
            )
        finally:
            stall.release_all()
            owner.close()


@dataclass(frozen=True)
class CoverageManagerReplayResult:
    covered_roles: Mapping[str, str]
    admitted_event_ids: tuple[str, ...]
    overflow_event_ids: tuple[str, ...]
    suppressed_event_ids: tuple[str, ...]
    fence_overflows: int
    processed_event_ids: tuple[str, ...]
    saturated_metrics: Mapping[str, object]
    health_during_overflow: Mapping[str, object]
    health_after_resync: Mapping[str, object]
    durable_continuity_loss: tuple[str, str] | None
    recovery_requests: tuple[tuple[str, dict], ...]


def run_coverage_manager_replay(
    fixture: RuntimeReplayFixture,
    *,
    protection_ingress_capacity: int = 64,
) -> CoverageManagerReplayResult:
    """Saturation characterization through the production RobotProtectionCoverageManager.

    The owner is held (handshake-proven) while the producer publishes the whole
    stream, then released; the production resync() retry path runs once afterwards.
    Freezes the fail-closed signals of a saturated ingress, not a product scenario.
    """
    symbols = tuple(dict.fromkeys(event.symbol for event in fixture.events))
    admitted: list[str] = []
    overflowed: list[str] = []
    suppressed: list[str] = []
    fence_overflows = 0
    processed: list[str] = []
    current_event: list[str | None] = [None]

    with tempfile.TemporaryDirectory() as temp:
        owner = SerializedPaperRuntime(
            lambda: _make_runtime(Path(temp) / "paper_runtime.sqlite3"),
            protection_ingress_capacity=protection_ingress_capacity,
        )
        release = threading.Event()
        manager: RobotProtectionCoverageManager | None = None
        try:
            def seed(runtime: PaperRuntime) -> None:
                _seed_pre_limit_candidates(
                    runtime, symbols, fixture.name, recovery_status="READY",
                )
                original = runtime.process_robot_market_event

                def recording(symbol, book, *, event_id, received_at_ms):
                    result = original(symbol, book, event_id=event_id, received_at_ms=received_at_ms)
                    processed.append(event_id)
                    return result

                runtime.process_robot_market_event = recording

            owner.call(seed, timeout=30.0)

            production_enqueue = owner.enqueue

            def observed_enqueue(operation, *, symbol="", coverage_role="UNKNOWN"):
                nonlocal fence_overflows
                try:
                    production_enqueue(operation, symbol=symbol, coverage_role=coverage_role)
                except ProtectionIngressOverflow:
                    if symbol:
                        overflowed.append(current_event[0])
                    else:
                        fence_overflows += 1
                    raise
                if symbol:
                    admitted.append(current_event[0])

            owner.enqueue = observed_enqueue

            hub = _ReplayHub()
            session = _OfflineRecoverySession()
            manager = RobotProtectionCoverageManager(
                hub, owner, resync_interval_s=3600.0, recovery_session=session,
            )
            manager.resync()
            covered_roles = dict(manager.health()["coverage_roles"])

            holder, release = _hold_owner(owner, "coverage-replay-owner-hold")
            for event in fixture.events:
                current_event[0] = event.event_id
                before = len(admitted) + len(overflowed)
                hub.contexts[event.symbol].publish(event)
                if len(admitted) + len(overflowed) == before:
                    suppressed.append(event.event_id)
            current_event[0] = None

            saturated_metrics = dict(owner.protection_ingress_metrics())
            health_during = manager.health()
            release.set()
            holder.join(timeout=60.0)
            owner.call(lambda runtime: None, timeout=30.0)

            # Production watchdog retry: re-fence durably and attempt REST recovery.
            manager.resync()
            owner.call(lambda runtime: None, timeout=30.0)
            durable = owner.call(
                lambda runtime: runtime.robot_protection_continuity_loss(), timeout=30.0,
            )
            return CoverageManagerReplayResult(
                covered_roles=covered_roles,
                admitted_event_ids=tuple(admitted),
                overflow_event_ids=tuple(overflowed),
                suppressed_event_ids=tuple(suppressed),
                fence_overflows=fence_overflows,
                processed_event_ids=tuple(processed),
                saturated_metrics=saturated_metrics,
                health_during_overflow=health_during,
                health_after_resync=manager.health(),
                durable_continuity_loss=durable,
                recovery_requests=tuple(session.requests),
            )
        finally:
            release.set()
            if manager is not None:
                manager.close()
            owner.close()