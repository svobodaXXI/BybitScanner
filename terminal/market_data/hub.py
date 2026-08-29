"""Long-lived owner of Bybit public subscriptions and reusable symbol contexts."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

import websocket

from terminal.market_data.instrument_registry import InstrumentRegistry


class _BookBuffer(Protocol):
    symbol: str
    depth: int
    def apply_message(self, message: dict) -> str: ...
    def wait_until_ready(self, timeout: float) -> bool: ...
    def set_update_consumer(self, consumer) -> None: ...
    def snapshot(self) -> dict: ...
    def mark_connecting(self) -> None: ...
    def mark_disconnected(self) -> None: ...
    def close(self) -> None: ...


class _TradeBuffer(Protocol):
    symbol: str
    def apply_message(self, message: dict) -> str: ...
    def snapshot_after(self, after: int) -> list[dict]: ...
    def close(self) -> None: ...


@dataclass(slots=True)
class SymbolContext:
    symbol: str
    public_orderbook: _BookBuffer
    public_trades: _TradeBuffer
    public_klines: dict[str, object]
    generation: int = 0
    subscription_state: str = "NOT_SUBSCRIBED"
    reconnect_count: int = 0
    last_error: str | None = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def wait_until_ready(self, timeout: float) -> bool:
        return self.public_orderbook.wait_until_ready(timeout)

    def health_snapshot(self) -> dict[str, object]:
        book = self.public_orderbook.snapshot()
        candles = [
            buffer.snapshot()
            for buffer in self.public_klines.values()
            if hasattr(buffer, "snapshot")
        ]
        trades = self.public_trades.snapshot_after(0)
        return {
            "symbol": self.symbol,
            "state": "READY" if book.get("state") == "READY" else "NOT_READY",
            "subscription_state": self.subscription_state,
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
            "last_book_ts": book.get("receivedAt", 0),
            "last_trade_ts": max((item.get("ended_at_ms", 0) for item in trades), default=0),
            "last_candle_ts": max((item.get("receivedAt", 0) for item in candles), default=0),
            "book_sequence": book.get("sequence", 0),
            "book_version": book.get("version", 0),
        }

    def close(self) -> None:
        self.public_orderbook.set_update_consumer(None)
        self.public_orderbook.close()
        self.public_trades.close()
        for buffer in self.public_klines.values():
            buffer.close()


class MarketDataHub:
    """Own one reconnecting public WebSocket and dispatch into symbol contexts."""

    URL = "wss://stream.bybit.com/v5/public/linear"

    def __init__(
        self,
        instruments: InstrumentRegistry,
        context_factory: Callable[[str, object], SymbolContext],
        *,
        connection_factory: Callable[..., object] = websocket.create_connection,
        reconnect_delay: float = 1.5,
    ) -> None:
        self._instruments = instruments
        self._context_factory = context_factory
        self._connection_factory = connection_factory
        self._reconnect_delay = reconnect_delay
        self._contexts: dict[str, SymbolContext] = {}
        self._lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self._ws = None
        self._thread = threading.Thread(target=self._run, name="bybit-market-data-hub", daemon=True)
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._thread.start()

    def subscribe(self, symbol: str) -> SymbolContext:
        instrument = self._instruments.get(symbol)
        normalized = instrument.symbol
        created = False
        with self._lock:
            context = self._contexts.get(normalized)
            if context is None:
                context = self._context_factory(normalized, instrument.tick_size)
                self._contexts[normalized] = context
                created = True
            ws = self._ws
        if created and ws is not None:
            self._send_subscribe(ws, context)
        return context

    def get(self, symbol: str) -> SymbolContext:
        normalized = self._instruments.get(symbol).symbol
        with self._lock:
            context = self._contexts.get(normalized)
        if context is None:
            raise LookupError(f"symbol context is not subscribed: {normalized}")
        return context

    def list_contexts(self) -> tuple[SymbolContext, ...]:
        with self._lock:
            return tuple(self._contexts[symbol] for symbol in sorted(self._contexts))

    def discard(self, context: SymbolContext) -> None:
        with self._lock:
            if self._contexts.get(context.symbol) is not context:
                return
            del self._contexts[context.symbol]
        context.close()

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            ws = self._ws
            self._ws = None
            contexts = tuple(self._contexts.values())
            self._contexts.clear()
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        if self._started and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        for context in contexts:
            context.close()

    def _topics(self, context: SymbolContext) -> list[str]:
        return [
            f"orderbook.{context.public_orderbook.depth}.{context.symbol}",
            f"publicTrade.{context.symbol}",
        ]

    def _send_subscribe(self, ws, context: SymbolContext) -> None:
        context.subscription_state = "SUBSCRIBING"
        with self._send_lock:
            ws.send(json.dumps({"op": "subscribe", "args": self._topics(context)}))

    def _run(self) -> None:
        while not self._stop.is_set():
            ws = None
            try:
                with self._lock:
                    contexts = tuple(self._contexts.values())
                for context in contexts:
                    context.public_orderbook.mark_connecting()
                    context.subscription_state = "CONNECTING"
                ws = self._connection_factory(self.URL, timeout=1)
                with self._lock:
                    self._ws = ws
                    contexts = tuple(self._contexts.values())
                for context in contexts:
                    self._send_subscribe(ws, context)
                while not self._stop.is_set():
                    try:
                        message = json.loads(ws.recv())
                    except websocket.WebSocketTimeoutException:
                        continue
                    self._dispatch(message)
            except Exception as exc:
                if not self._stop.is_set():
                    with self._lock:
                        contexts = tuple(self._contexts.values())
                    for context in contexts:
                        context.subscription_state = "DISCONNECTED"
                        context.reconnect_count += 1
                        context.last_error = type(exc).__name__
                        context.public_orderbook.mark_disconnected()
                    self._stop.wait(self._reconnect_delay)
            finally:
                with self._lock:
                    if self._ws is ws:
                        self._ws = None
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass

    def _dispatch(self, message: object) -> None:
        if not isinstance(message, dict):
            return
        topic = message.get("topic")
        if not isinstance(topic, str):
            return
        symbol = topic.rsplit(".", 1)[-1]
        with self._lock:
            context = self._contexts.get(symbol)
        if context is None:
            return
        if topic.startswith("orderbook."):
            applied = context.public_orderbook.apply_message(message)
        elif topic.startswith("publicTrade."):
            applied = context.public_trades.apply_message(message)
        else:
            return
        if applied == "APPLIED":
            context.subscription_state = "SUBSCRIBED"
            context.last_error = None
