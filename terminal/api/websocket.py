"""Framework-neutral snapshot-first presentation subscription protocol."""

from __future__ import annotations

from dataclasses import replace
from enum import Enum
from typing import Callable, Mapping
from uuid import uuid4

from terminal.api.models import (
    EventEnvelope, EventType, PresentationChannel, PROTOCOL_VERSION,
    SubscriptionOperation, SubscriptionRequest, SubscriptionResult, to_primitive,
)
from terminal.api.projections import EventStreamBoundary, TerminalSnapshot


class EventDisposition(str, Enum):
    APPLY = "apply"
    IGNORE_STALE = "ignore_stale"
    FRESH_SNAPSHOT_REQUIRED = "fresh_snapshot_required"


_EVENT_CHANNEL = {
    EventType.POSITION_CHANGED: PresentationChannel.POSITION,
    EventType.ORDER_ADDED: PresentationChannel.ORDERS,
    EventType.ORDER_UPDATED: PresentationChannel.ORDERS,
    EventType.ORDER_REMOVED: PresentationChannel.ORDERS,
    EventType.EXECUTION_RECORDED: PresentationChannel.EXECUTIONS,
    EventType.PROTECTION_CHANGED: PresentationChannel.PROTECTION,
    EventType.CLEANUP_CHANGED: PresentationChannel.CLEANUP,
    EventType.CONNECTIVITY_CHANGED: PresentationChannel.CONNECTIVITY,
    EventType.TRUST_CHANGED: PresentationChannel.CONNECTIVITY,
    EventType.WARNING_CHANGED: PresentationChannel.WARNINGS,
}


class PresentationCursor:
    def __init__(self, snapshot: TerminalSnapshot) -> None:
        self.stream_id = snapshot.event_stream.stream_id
        self.snapshot_id = snapshot.snapshot_id
        self.last_sequence = snapshot.event_stream.initial_event_sequence
        self.reconciliation_generation = snapshot.reconciliation_generation
        self.entity_versions: dict[str, int] = {}

    def assess(self, event: EventEnvelope) -> EventDisposition:
        if event.stream_id != self.stream_id or event.snapshot_id != self.snapshot_id:
            return EventDisposition.IGNORE_STALE
        if event.reconciliation_generation < self.reconciliation_generation:
            return EventDisposition.IGNORE_STALE
        if event.event_sequence <= self.last_sequence:
            return EventDisposition.IGNORE_STALE
        if event.event_sequence != self.last_sequence + 1:
            return EventDisposition.FRESH_SNAPSHOT_REQUIRED
        if event.entity_version < self.entity_versions.get(event.entity_id, -1):
            return EventDisposition.IGNORE_STALE
        return EventDisposition.APPLY

    def apply(self, event: EventEnvelope) -> EventDisposition:
        disposition = self.assess(event)
        if disposition is EventDisposition.APPLY:
            self.last_sequence = event.event_sequence
            self.reconciliation_generation = max(
                self.reconciliation_generation, event.reconciliation_generation,
            )
            self.entity_versions[event.entity_id] = event.entity_version
        return disposition


SnapshotFactory = Callable[[str, str, str], TerminalSnapshot]


class PresentationStreamSession:
    def __init__(self, symbol: str, channels: tuple[PresentationChannel, ...], factory: SnapshotFactory) -> None:
        self.symbol = symbol.upper()
        self.channels = tuple(dict.fromkeys(channels))
        self.stream_id = uuid4().hex
        self.snapshot_id = uuid4().hex
        snapshot = factory(self.symbol, self.stream_id, self.snapshot_id)
        self.snapshot = replace(
            snapshot, snapshot_id=self.snapshot_id,
            event_stream=EventStreamBoundary(self.stream_id, 0),
        )
        self._sequence = 0
        self._entity_versions: dict[str, int] = {}
        self._final_order_updates: set[str] = set()

    def initial_snapshot_event(self) -> EventEnvelope:
        return self.emit(
            EventType.SNAPSHOT_REPLACED, "snapshot", 1,
            {"snapshot": to_primitive(self.snapshot)},
            reconciliation_generation=self.snapshot.reconciliation_generation,
        )

    def emit(
        self, event_type: EventType, entity_id: str, entity_version: int,
        payload: Mapping[str, object], *, reconciliation_generation: int,
        exchange_sequence: int | None = None,
    ) -> EventEnvelope:
        channel = _EVENT_CHANNEL.get(event_type)
        if channel is not None and channel not in self.channels:
            raise ValueError("event channel is not subscribed")
        payload_symbol = payload.get("symbol")
        if payload_symbol is not None and str(payload_symbol).upper() != self.symbol:
            raise ValueError("event symbol is outside the presentation subscription")
        if event_type is EventType.ORDER_REMOVED and entity_id not in self._final_order_updates:
            raise ValueError("order_removed requires a preceding final order_updated event")
        previous = self._entity_versions.get(entity_id, -1)
        if entity_version < previous:
            raise ValueError("cannot emit a stale entity version")
        self._sequence += 1
        self._entity_versions[entity_id] = entity_version
        if event_type is EventType.ORDER_UPDATED and payload.get("status") in {
            "cancelled", "filled", "rejected", "deactivated",
        }:
            self._final_order_updates.add(entity_id)
        return EventEnvelope(
            PROTOCOL_VERSION, self.stream_id, self.snapshot_id, self._sequence,
            reconciliation_generation, entity_id, entity_version, exchange_sequence,
            event_type, payload,
        )

    def heartbeat(self) -> EventEnvelope:
        return self.emit(
            EventType.HEARTBEAT, "stream", self._sequence + 1,
            {"service_alive": True, "trading_ready": False},
            reconciliation_generation=self.snapshot.reconciliation_generation,
        )


class SubscriptionService:
    def __init__(self, snapshot_factory: SnapshotFactory) -> None:
        self._snapshot_factory = snapshot_factory
        self._session: PresentationStreamSession | None = None

    @property
    def session(self) -> PresentationStreamSession | None:
        return self._session

    def handle(self, request: SubscriptionRequest) -> SubscriptionResult:
        if request.operation is SubscriptionOperation.PING:
            return SubscriptionResult(SubscriptionOperation.PONG, True, None, (), nonce=request.nonce)
        if request.operation is SubscriptionOperation.PONG:
            return SubscriptionResult(request.operation, True, None, (), nonce=request.nonce)
        if request.operation is SubscriptionOperation.UNSUBSCRIBE_ALL:
            self._session = None
            return SubscriptionResult(request.operation, True, None, ())
        if request.operation is SubscriptionOperation.UNSUBSCRIBE:
            if self._session is not None and (
                request.symbol is None or self._session.symbol == request.symbol.upper()
            ):
                self._session = None
            return SubscriptionResult(request.operation, True, request.symbol, request.channels)
        if request.operation is SubscriptionOperation.SUBSCRIBE:
            if not request.symbol or not request.channels:
                return SubscriptionResult(request.operation, False, request.symbol, request.channels)
            symbol = request.symbol.upper()
            switched = self._session is None or self._session.symbol != symbol
            if switched:
                self._session = PresentationStreamSession(symbol, request.channels, self._snapshot_factory)
            else:
                self._session.channels = tuple(dict.fromkeys(self._session.channels + request.channels))
            return SubscriptionResult(
                request.operation, True, symbol, self._session.channels,
                fresh_snapshot_required=switched,
            )
        raise ValueError("unsupported subscription operation")
