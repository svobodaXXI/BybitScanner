"""Opt-in, local-only SHADOW bridge from existing Bybit publicTrade to shared Robot evidence.

No extra WebSocket, Scanner decision, risk gate, order API, background process
or persistence. Trade-frame delivery cannot prove a complete exchange tape;
evidence is exploratory and MUST NOT authorize a Robot entry.
"""
from __future__ import annotations

import time
from typing import Protocol, Callable

from robot_entry_flow_evidence import (
    CompletedFlowObserver, FlowTransition, TakerPrint, normalize_bybit_taker_print,
)

MINUTE_MS = 60_000
MAX_PACKET_PRINTS = 2_000
MAX_MINUTE_PRINTS = 20_000
MAX_RECEIVE_LAG_MS = 120_000


class ReadOnlyTradeContext(Protocol):
    symbol: str
    reconnect_count: int
    trades_subscription_state: str
    trade_bootstrap_complete: bool

    def add_trade_listener(self, name: str, callback: Callable[[dict, int], None]) -> None: ...
    def remove_trade_listener(self, name: str) -> None: ...
    def add_disconnect_listener(self, name: str, callback: Callable[[int, str], None]) -> None: ...
    def remove_disconnect_listener(self, name: str) -> None: ...


class LocalRobotFlowShadow:
    """One explicitly attached symbol context, best-effort immutable evidence.

    A partial minute after attach, reconnect or malformed/oversize data is
    quarantined. Closed windows are compared only after a later trade frame
    arrives and only at its actual receipt time. No feed-coverage attestation.
    """

    coverage = "OBSERVED_WS_FRAMES_NOT_COMPLETE_EXCHANGE_TAPE"

    def __init__(
        self, context: ReadOnlyTradeContext, *, started_at_ms: int | None = None,
    ) -> None:
        if started_at_ms is None:
            started_at_ms = int(time.time() * 1000)
        if type(started_at_ms) is not int or started_at_ms < 0:
            raise ValueError("invalid observer attach time")
        self._context = context
        self._name = f"local-flow-shadow:{id(self)}"
        self._observer = CompletedFlowObserver(symbol=context.symbol, window_ms=MINUTE_MS)
        self._generation = context.reconnect_count
        self._minute_start: int | None = None
        self._minute_prints: list[TakerPrint] = []
        self._minute_ids: set[str] = set()
        self._last_event_ms: int | None = None
        self._last_received_ms = started_at_ms
        self._quarantine_before = (started_at_ms // MINUTE_MS + 1) * MINUTE_MS
        self._closed = False
        self._fresh_connect_pending = False
        self.latest_transition: FlowTransition | None = None
        self.observed_windows = 0
        context.add_trade_listener(self._name, self._on_packet)
        try:
            context.add_disconnect_listener(self._name, self._on_disconnect)
        except Exception:
            context.remove_trade_listener(self._name)
            raise

    def _invalidate(self, at_ms: int) -> None:
        self._observer = CompletedFlowObserver(
            symbol=self._context.symbol, window_ms=MINUTE_MS,
        )
        self._minute_start = None
        self._minute_prints.clear()
        self._minute_ids.clear()
        self._last_event_ms = None
        self.latest_transition = None
        self._quarantine_before = (at_ms // MINUTE_MS + 1) * MINUTE_MS

    def _on_disconnect(self, generation: int, reason: str) -> None:
        if self._closed:
            return
        self._generation = generation
        self._invalidate(self._last_received_ms)
        self._fresh_connect_pending = True

    def _on_packet(self, message: dict, received_at_ms: int) -> None:
        if self._closed:
            return
        if type(received_at_ms) is not int or received_at_ms < self._last_received_ms:
            self._invalidate(self._last_received_ms)
            return
        self._last_received_ms = received_at_ms
        if self._fresh_connect_pending:
            # A disconnect has no reliable receive time for the next session.
            # Fence the entire first observed minute after reconnect.
            self._fresh_connect_pending = False
            self._invalidate(received_at_ms)
            return
        context = self._context
        if (context.reconnect_count != self._generation
                or context.trades_subscription_state != "SUBSCRIBED"
                or context.trade_bootstrap_complete is not True):
            self._generation = context.reconnect_count
            self._invalidate(received_at_ms)
            return
        data = message.get("data") if isinstance(message, dict) else None
        if not isinstance(data, list) or len(data) > MAX_PACKET_PRINTS:
            self._invalidate(received_at_ms)
            return
        if not data:
            return
        try:
            prints = [
                normalize_bybit_taker_print(raw, layout="WS_PUBLIC_TRADE")
                for raw in data
            ]
            if any(
                p.symbol != context.symbol or p.event_ms > received_at_ms
                or received_at_ms - p.event_ms > MAX_RECEIVE_LAG_MS
                for p in prints
            ):
                raise ValueError("foreign, future or stale live taker print")
        except (TypeError, ValueError, AttributeError):
            self._invalidate(received_at_ms)
            return
        for trade in sorted(prints, key=lambda p: (p.event_ms, p.trade_id)):
            if trade.event_ms < self._quarantine_before:
                continue
            minute = trade.event_ms // MINUTE_MS * MINUTE_MS
            if self._minute_start is not None and minute > self._minute_start:
                try:
                    value = self._observer.observe_closed(
                        tuple(self._minute_prints), start_ms=self._minute_start,
                        end_ms=self._minute_start + MINUTE_MS,
                        observed_at_ms=received_at_ms,
                        source_id=f"BYBIT_PUBLIC_WS_{context.symbol}_{self._generation}",
                    )
                except (ValueError, TypeError):
                    self._invalidate(received_at_ms)
                    return
                self.latest_transition = value
                if value is not None:
                    self.observed_windows += 1
                self._minute_prints.clear()
                self._minute_ids.clear()
                self._last_event_ms = None
                self._minute_start = minute
            elif self._minute_start is None:
                self._minute_start = minute
            if minute < self._minute_start or (
                self._last_event_ms is not None and trade.event_ms < self._last_event_ms
            ) or trade.trade_id in self._minute_ids:
                self._invalidate(received_at_ms)
                return
            if len(self._minute_prints) >= MAX_MINUTE_PRINTS:
                self._invalidate(received_at_ms)
                return
            self._minute_prints.append(trade)
            self._minute_ids.add(trade.trade_id)
            self._last_event_ms = trade.event_ms

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._context.remove_trade_listener(self._name)
        self._context.remove_disconnect_listener(self._name)
        self._invalidate(self._last_received_ms)
