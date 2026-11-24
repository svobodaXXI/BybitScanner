"""Long-lived owner of Bybit public subscriptions and reusable symbol contexts."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol

import websocket

from terminal.market_data.instrument_registry import InstrumentRegistry
from terminal.market_data.impulse_observation import PublicTradeObservation
from terminal.runtime.incident_telemetry import report_incident

LOGGER = logging.getLogger(__name__)

_REASON_MAX_CHARS = 200
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@]+@")
_QUERY_STRING = re.compile(r"\?[^\s'\"]*")
_BOT_TOKEN = re.compile(r"\bbot\d+:[A-Za-z0-9_-]+")


def _safe_reason(error: BaseException) -> str:
    """Bounded one-line exception text without URL credentials, queries or bot tokens."""
    text = " ".join(str(error).split())
    text = _URL_CREDENTIALS.sub(r"\1<redacted>@", text)
    text = _QUERY_STRING.sub("?<redacted>", text)
    text = _BOT_TOKEN.sub("bot<redacted>", text)
    return text[:_REASON_MAX_CHARS]


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
    book_subscription_state: str = "NOT_SUBSCRIBED"
    trades_subscription_state: str = "NOT_SUBSCRIBED"
    trade_bootstrap_complete: bool = False
    impulse_observation: PublicTradeObservation = field(init=False)
    reconnect_count: int = 0
    last_error: str | None = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    _update_listeners: dict[str, Callable[[str], None]] = field(default_factory=dict)
    _disconnect_listeners: dict[str, Callable[[int, str], None]] = field(default_factory=dict)
    _listener_lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.impulse_observation = PublicTradeObservation(self.symbol)

    def add_update_listener(self, name: str, callback: Callable[[str], None]) -> None:
        """Register ``callback`` under ``name`` without disturbing any other
        listener already registered on this symbol's book buffer.

        Independent consumers (Workspace display, Robot protection coverage)
        must coexist on the same ``public_orderbook`` single-consumer slot;
        this fan-out owns that slot exclusively once any listener exists.
        """
        if not name:
            raise ValueError("update listener name must be non-empty")
        with self._listener_lock:
            first = not self._update_listeners
            self._update_listeners[name] = callback
        if first:
            self.public_orderbook.set_update_consumer(self._dispatch_update)

    def remove_update_listener(self, name: str) -> None:
        with self._listener_lock:
            self._update_listeners.pop(name, None)
            empty = not self._update_listeners
        if empty:
            self.public_orderbook.set_update_consumer(None)

    def add_disconnect_listener(
        self, name: str, callback: Callable[[int, str], None],
    ) -> None:
        if not name:
            raise ValueError("disconnect listener name must be non-empty")
        with self._listener_lock:
            self._disconnect_listeners[name] = callback

    def remove_disconnect_listener(self, name: str) -> None:
        with self._listener_lock:
            self._disconnect_listeners.pop(name, None)

    def has_update_listeners(self) -> bool:
        with self._listener_lock:
            return bool(self._update_listeners)

    def has_listeners(self) -> bool:
        with self._listener_lock:
            return bool(self._update_listeners or self._disconnect_listeners)

    def _dispatch_update(self, book_update_id: str) -> None:
        with self._listener_lock:
            listeners = tuple(self._update_listeners.values())
        for listener in listeners:
            try:
                listener(book_update_id)
            except Exception:
                LOGGER.exception(
                    "Symbol context update listener failed; symbol=%s book_update_id=%s",
                    self.symbol, book_update_id,
                )

    def _dispatch_disconnect(self, generation: int, reason: str) -> None:
        with self._listener_lock:
            listeners = tuple(self._disconnect_listeners.values())
        for listener in listeners:
            try:
                listener(generation, reason)
            except Exception:
                LOGGER.exception(
                    "Symbol context disconnect listener failed; "
                    "symbol=%s generation=%s reason=%s",
                    self.symbol, generation, reason,
                )

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
            "book_subscription_state": self.book_subscription_state,
            "trades_subscription_state": self.trades_subscription_state,
            "trade_bootstrap_complete": self.trade_bootstrap_complete,
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
            "last_book_ts": book.get("receivedAt", 0),
            "last_trade_ts": max((item.get("ended_at_ms", 0) for item in trades), default=0),
            "last_candle_ts": max((item.get("receivedAt", 0) for item in candles), default=0),
            "book_sequence": book.get("sequence", 0),
            "book_version": book.get("version", 0),
        }

    def close(self) -> None:
        with self._listener_lock:
            self._update_listeners.clear()
            self._disconnect_listeners.clear()
        self.public_orderbook.set_update_consumer(None)
        self.public_orderbook.close()
        self.public_trades.close()
        for buffer in self.public_klines.values():
            buffer.close()


@dataclass(slots=True)
class _FlowOnlyContext:
    """One passive public-data watch, separate from protection coverage.

    No trading book buffer, 15s candle producer, native kline threads, owner listener,
    entry right or independent WebSocket. Existing full SymbolContext always
    takes precedence, including on later Robot coverage arm.
    """
    symbol: str
    trades_subscription_state: str = "NOT_SUBSCRIBED"
    trade_bootstrap_complete: bool = False
    impulse_observation: PublicTradeObservation = field(init=False)
    capture_book: bool = False
    book_frames: deque[tuple[int, dict]] = field(default_factory=lambda: deque(maxlen=1024))

    @property
    def book_topic(self) -> str:
        return f"orderbook.200.{self.symbol}"

    def topics(self) -> list[str]:
        topics = [f"publicTrade.{self.symbol}"]
        if self.capture_book:
            topics.append(self.book_topic)
        return topics

    def __post_init__(self) -> None:
        self.impulse_observation = PublicTradeObservation(self.symbol)
        self.impulse_observation.enable_certification_buffer()


@dataclass(slots=True)
class _ProtectedResearchCapture:
    """Opt-in raw ingress witness for an ALREADY protected book.

    This is not a book buffer or a second subscription. No synthetic baseline:
    until an actual post-opt-in vendor snapshot arrives, deltas are discarded.
    Overflow and reconnect invalidate the whole witness, not just its oldest row.
    """
    context: SymbolContext
    owner_token: object | None = field(default=None, repr=False)
    capture_book: bool = field(default=True, init=False)
    book_frames: deque[tuple[int, dict]] = field(
        default_factory=lambda: deque(maxlen=1024),
    )
    # Never presented as a reconstructed book: delta-only ingress is a
    # bounded candidate tape for a future independently verified REST anchor.
    # A host must match exact vendor u/seq/cts before using any such delta.
    rest_anchor_candidates: deque[tuple[int, dict]] = field(
        default_factory=lambda: deque(maxlen=1024),
    )
    _active: bool = True
    _epoch: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _detached_tape_snapshot(self, *, protected: bool) -> dict[str, object]:
        """Detach one epoch without copying under the protection ingress lock."""
        with self._lock:
            symbol = self.context.symbol
            depth = self.context.public_orderbook.depth
            epoch = self._epoch
            active = self._active
            raw = tuple(self.book_frames if protected else self.rest_anchor_candidates)
        frames = deepcopy(raw)  # Copying large frames must not block on_book.
        with self._lock:
            stable = epoch == self._epoch and active == self._active
        return {
            "symbol": symbol, "depth": depth, "epoch": epoch,
            "active": active and stable, "frames": frames if stable else (),
            "source_complete": False, "trading_authorized": False,
        }

    def rest_anchor_tape_snapshot(self) -> dict[str, object]:
        """Orphan deltas are never promoted to a reconstructed book."""
        return self._detached_tape_snapshot(protected=False)

    def protected_book_tape_snapshot(self) -> dict[str, object]:
        """Original snapshot-first raw book tape, only when explicitly opted in."""
        return self._detached_tape_snapshot(protected=True)

    def protected_book_tape_token(self) -> tuple[int, bool, int]:
        """O(1) epoch/length fence; ordinary appends advance length."""
        with self._lock:
            return self._epoch, self._active, len(self.book_frames)

    @property
    def impulse_observation(self) -> PublicTradeObservation:
        return self.context.impulse_observation

    def on_book(self, received_at_ms: int, frame: dict, applied: str) -> None:
        with self._lock:
            if not self._active:
                return
            kind = frame.get("type")
            if applied != "APPLIED" or kind not in ("snapshot", "delta"):
                self._epoch += 1
                self.book_frames.clear()
                self.rest_anchor_candidates.clear()
                return
            if kind == "snapshot":
                self._epoch += 1
                self.book_frames.clear()
                self.rest_anchor_candidates.clear()
                self.book_frames.append((received_at_ms, frame))
                return
            if self.book_frames:
                if len(self.book_frames) == self.book_frames.maxlen:
                    self._epoch += 1
                    self.book_frames.clear()
                    self.rest_anchor_candidates.clear()
                    return  # No prefix truncation masquerading as continuity.
                self.book_frames.append((received_at_ms, frame))
                return
            # An orphan delta is NOT a book state. Retain it only for a
            # separate source-provenance matcher; do not export as L2 proof.
            if len(self.rest_anchor_candidates) == self.rest_anchor_candidates.maxlen:
                self._epoch += 1
                self.rest_anchor_candidates.clear()
                return
            self.rest_anchor_candidates.append((received_at_ms, frame))

    def reset(self) -> None:
        with self._lock:
            self._epoch += 1
            self.book_frames.clear()
            self.rest_anchor_candidates.clear()

    def close(self) -> None:
        with self._lock:
            self._epoch += 1
            self._active = False
            self.book_frames.clear()
            self.rest_anchor_candidates.clear()


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
        # At most ONE opt-in, trade-only watch on the EXISTING WebSocket.
        # It never enters list_contexts(), Workspace or protection coverage.
        self._flow_only: dict[str, _FlowOnlyContext] = {}
        # At most one optional raw-frame witness for an EXISTING full context.
        # No new subscription, vendor buffer, listeners or protection owner.
        self._protected_research: _ProtectedResearchCapture | None = None
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
            former = None
            if context is None:
                # Protected full-context ownership ALWAYS supersedes passive
                # observation, without unsubscribing its already-live topic.
                former = self._flow_only.pop(normalized, None)
                context = self._context_factory(normalized, instrument.tick_size)
                if former is not None:
                    if former.capture_book and self._ws is not None:
                        try:
                            with self._send_lock:
                                self._ws.send(json.dumps({
                                    "op": "unsubscribe",
                                    "req_id": f"flow:{normalized}:book-release",
                                    "args": [former.book_topic],
                                }))
                        except Exception:
                            pass
                    former.book_frames.clear()
                    context.impulse_observation = former.impulse_observation
                    context.trades_subscription_state = former.trades_subscription_state
                    context.trade_bootstrap_complete = former.trade_bootstrap_complete
                self._contexts[normalized] = context
                created = True
            ws = self._ws
        if created and ws is not None:
            if former is not None and former.trade_bootstrap_complete:
                # Existing publicTrade topic stays on this same connection;
                # only book ownership is missing after passive promotion.
                self._send_book_only(ws, context)
            else:
                self._send_subscribe(ws, context)
        return context

    def subscribe_flow_only(
        self, symbol: str, *, capture_book: bool = False,
    ) -> _FlowOnlyContext | SymbolContext | None:
        """Owner-approved flow observer only: one bounded passive symbol.

        Never call the full context_factory: it starts several REST/kline
        workers and creates the protected book buffer.
        This method has NO effect on protected contexts or their listeners.
        """
        normalized = self._instruments.get(symbol).symbol
        with self._lock:
            full = self._contexts.get(normalized)
            if full is not None:
                return full
            passive = self._flow_only.get(normalized)
            if passive is not None:
                # A different approved candidate may need pre-breakout L2
                # after this symbol was already warmed for publicTrade only.
                # Promote the existing passive lease without disconnecting
                # or resetting its certified trade source.
                if capture_book and not passive.capture_book and not self._stop.is_set():
                    ws = self._ws
                    if ws is not None:
                        try:
                            with self._send_lock:
                                ws.send(json.dumps({
                                    "op": "subscribe",
                                    "req_id": f"flowbook:{normalized}:capture",
                                    "args": [passive.book_topic],
                                }))
                        except Exception:
                            # No confirmed subscription: retry on the next
                            # sync, never expose partial L2 as evidence.
                            return passive
                    passive.book_frames.clear()
                    passive.capture_book = True
                return passive
            if self._stop.is_set() or self._flow_only:
                return None
            passive = _FlowOnlyContext(normalized, capture_book=capture_book)
            self._flow_only[normalized] = passive
            ws = self._ws
        if ws is not None:
            with self._lock:
                # A release/full-coverage promotion may have happened while
                # waiting for the send lock. Never subscribe an orphan lease.
                if self._flow_only.get(normalized) is passive and self._ws is ws:
                    self._send_flow_only(ws, passive)
        return passive

    def begin_protected_research_capture(
        self, symbol: str, *, owner_token: object | None = None,
    ) -> _ProtectedResearchCapture | None:
        """Attach only to an already subscribed protected SymbolContext.

        Caller must be an explicitly opted-in research observer; this method
        never creates a context, socket, topic or book snapshot.
        """
        normalized = self._instruments.get(symbol).symbol
        with self._lock:
            full = self._contexts.get(normalized)
            if full is None or self._stop.is_set():
                return None
            existing = self._protected_research
            if existing is not None:
                return existing if (existing.context is full
                                    and existing.owner_token is owner_token) else None
            witness = _ProtectedResearchCapture(full, owner_token=owner_token)
            self._protected_research = witness
            return witness

    def end_protected_research_capture(
        self, symbol: str, *, owner_token: object | None = None,
    ) -> bool:
        """Release only the caller's witness, never a protected subscription."""
        with self._lock:
            witness = self._protected_research
            if (witness is None or witness.context.symbol != symbol
                    or witness.owner_token is not owner_token):
                return False
            self._protected_research = None
            witness.close()
            return True

    def private_protected_research_snapshot(
        self, symbol: str, *, expected_witness: _ProtectedResearchCapture | None = None,
    ) -> dict[str, object] | None:
        """Private in-process read ONLY of an already-active protected witness.

        No subscriptions, capture activation or public route. A generation
        change or release while reading rejects the mixed source. Caller still
        needs an exact APPROVED host and independent completeness attestation.
        """
        with self._lock:
            witness = self._protected_research
            context = self._contexts.get(symbol)
            if (witness is None or context is None
                    or (expected_witness is not None and witness is not expected_witness)
                    or witness.context is not context or self._stop.is_set()):
                return None
            generation = context.generation
        first = witness.protected_book_tape_snapshot()
        trades = witness.impulse_observation.snapshot()
        epoch, active, count = witness.protected_book_tape_token()
        with self._lock:
            stable = (self._protected_research is witness
                      and self._contexts.get(symbol) is context
                      and context.generation == generation
                      and not self._stop.is_set())
        if (not stable or not first["active"] or not active
                or first["epoch"] != epoch or len(first["frames"]) != count):
            return None
        return {"book": first, "trades": trades}

    def release_flow_only(self, symbol: str) -> bool:
        """Release ONLY a passive topic; never unsubscribe protected books."""
        with self._lock:
            passive = self._flow_only.pop(symbol, None)
            if passive is None:
                return False
            passive.trade_bootstrap_complete = False
            passive.trades_subscription_state = "NOT_SUBSCRIBED"
            passive.impulse_observation.mark_gap()
            passive.book_frames.clear()
            # Atomically fence promotion of a protected full context until
            # this unsubscribe has been queued on the SAME socket.
            ws = self._ws
            if ws is not None:
                try:
                    with self._send_lock:
                        ws.send(json.dumps({
                            "op": "unsubscribe",
                            "req_id": f"flow:{symbol}:release",
                            "args": passive.topics(),
                        }))
                except Exception:
                    pass  # disconnect/reconnect still fences the source
            return True

    def list_flow_contexts(self) -> tuple[SymbolContext | _FlowOnlyContext, ...]:
        """All FULL plus passive contexts, solely for read-only flow audits."""
        with self._lock:
            both = {**self._flow_only, **self._contexts}
            return tuple(both[symbol] for symbol in sorted(both))

    def get(self, symbol: str) -> SymbolContext:
        normalized = self._instruments.get(symbol).symbol
        with self._lock:
            context = self._contexts.get(normalized)
        if context is None:
            raise LookupError(f"symbol context is not subscribed: {normalized}")
        return context

    def has_context(self, symbol: str) -> bool:
        normalized = self._instruments.get(symbol).symbol
        with self._lock:
            return normalized in self._contexts

    def list_contexts(self) -> tuple[SymbolContext, ...]:
        with self._lock:
            return tuple(self._contexts[symbol] for symbol in sorted(self._contexts))

    def impulse_source_diagnostics(self, *, limit: int = 32) -> dict[str, object]:
        """Read only existing hub subscriptions; NEVER discover/subscribe symbols.

        Exposes bounded source observation on the Scanner status endpoint.
        Neither healthy WebSocket state nor REST overlap proves full trade flow.
        Raw prints and any candidate/entry decision are deliberately excluded.
        """
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("diagnostic context limit must be 1..32")
        contexts = self.list_contexts()
        rows: list[dict[str, object]] = []
        for context in contexts[:limit]:
            observed = context.impulse_observation.snapshot()
            rows.append({
                "symbol": context.symbol,
                "subscription_state": context.trades_subscription_state,
                "source_generation": observed["generation"],
                "observed_prints": observed["observed_prints"],
                "invalid_frames": observed["invalid_frames"],
                "last_trade_ms": observed["last_trade_ms"],
                "last_cross_sequence": observed["last_cross_sequence"],
                "gap_or_truncation": observed["gap_or_truncation"],
                "continuity": "UNPROVEN",
                "trading_authorized": False,
            })
        return {
            "scope": "EXISTING_HUB_SUBSCRIPTIONS_ONLY",
            "subscribed_contexts": len(contexts),
            "reported_contexts": len(rows),
            "truncated": len(contexts) > limit,
            "source_complete": False,
            "trading_authorized": False,
            "contexts": rows,
        }

    def discard(self, context: SymbolContext) -> None:
        """Drop ``context`` only when no independent consumer still needs it.

        Workspace symbol switching and warm-context expiry must never sever
        Robot protection coverage (or any other active listener) for a symbol
        Workspace itself no longer needs; release is last-consumer-out.
        """
        if context.has_listeners():
            return
        with self._lock:
            if self._contexts.get(context.symbol) is not context:
                return
            del self._contexts[context.symbol]
            if (self._protected_research is not None
                    and self._protected_research.context is context):
                self._protected_research.close()
                self._protected_research = None
            ws = self._ws
        if ws is not None:
            try:
                with self._send_lock:
                    ws.send(json.dumps({"op": "unsubscribe", "args": self._topics(context)}))
            except Exception:
                pass
        context.close()

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            ws = self._ws
            self._ws = None
            contexts = tuple(self._contexts.values())
            passive = tuple(self._flow_only.values())
            self._contexts.clear()
            self._flow_only.clear()
            witness = self._protected_research
            self._protected_research = None
            if witness is not None:
                witness.close()
        for context in passive:
            context.impulse_observation.mark_gap()
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

    def _send_flow_only(self, ws, context: _FlowOnlyContext) -> None:
        context.trades_subscription_state = "SUBSCRIBING"
        context.trade_bootstrap_complete = False
        with self._send_lock:
            ws.send(json.dumps({
                "op": "subscribe", "req_id": f"flow:{context.symbol}",
                "args": context.topics(),
            }))

    def _send_book_only(self, ws, context: SymbolContext) -> None:
        context.subscription_state = "SUBSCRIBING"
        context.book_subscription_state = "SUBSCRIBING"
        with self._send_lock:
            ws.send(json.dumps({
                "op": "subscribe", "req_id": f"workspace:{context.symbol}",
                "args": [f"orderbook.{context.public_orderbook.depth}.{context.symbol}"],
            }))

    def _send_subscribe(self, ws, context: SymbolContext) -> None:
        context.subscription_state = "SUBSCRIBING"
        context.book_subscription_state = "SUBSCRIBING"
        context.trades_subscription_state = "SUBSCRIBING"
        context.trade_bootstrap_complete = False
        with self._send_lock:
            ws.send(json.dumps({
                "op": "subscribe",
                "req_id": f"workspace:{context.symbol}",
                "args": self._topics(context),
            }))

    def _run(self) -> None:
        while not self._stop.is_set():
            ws = None
            try:
                with self._lock:
                    contexts = tuple(self._contexts.values())
                    passive = tuple(self._flow_only.values())
                for flow in passive:
                    flow.trades_subscription_state = "CONNECTING"
                    flow.trade_bootstrap_complete = False
                for context in contexts:
                    context.public_orderbook.mark_connecting()
                    context.subscription_state = "CONNECTING"
                    context.book_subscription_state = "CONNECTING"
                    context.trades_subscription_state = "CONNECTING"
                    context.trade_bootstrap_complete = False
                ws = self._connection_factory(self.URL, timeout=1)
                with self._lock:
                    self._ws = ws
                    contexts = tuple(self._contexts.values())
                    passive = tuple(self._flow_only.values())
                for context in contexts:
                    self._send_subscribe(ws, context)
                for flow in passive:
                    with self._lock:
                        if self._flow_only.get(flow.symbol) is flow and self._ws is ws:
                            self._send_flow_only(ws, flow)
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
                        passive = tuple(self._flow_only.values())
                    with self._lock:
                        witness = self._protected_research
                    if witness is not None:
                        witness.reset()  # Must await a fresh vendor snapshot.
                    for flow in passive:
                        flow.trades_subscription_state = "DISCONNECTED"
                        flow.trade_bootstrap_complete = False
                        flow.impulse_observation.mark_gap()
                        flow.book_frames.clear()
                    for context in contexts:
                        context.subscription_state = "DISCONNECTED"
                        context.book_subscription_state = "DISCONNECTED"
                        context.trades_subscription_state = "DISCONNECTED"
                        context.trade_bootstrap_complete = False
                        context.reconnect_count += 1
                        context.impulse_observation.mark_gap()
                        context.last_error = type(exc).__name__
                        context.public_orderbook.mark_disconnected()
                        context._dispatch_disconnect(
                            context.reconnect_count,
                            context.last_error,
                        )
                    # Structured bounded evidence never contains raw WS exception
                    # text or credentials; reconnect and continuity fencing unchanged.
                    report_incident(
                        "WS_DISCONNECT", error_class=type(exc).__name__,
                        contexts=len(contexts),
                        symbol=contexts[0].symbol if contexts else "",
                        generation=max((c.reconnect_count for c in contexts), default=0),
                    )
                    # Existing console diagnostics, best-effort only.
                    try:
                        LOGGER.warning(
                            "Market-data WebSocket disconnected; utc=%s error_class=%s "
                            "reason=%s contexts=%d generations=%s",
                            datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                            type(exc).__name__, _safe_reason(exc), len(contexts),
                            ",".join(f"{c.symbol}:{c.reconnect_count}" for c in contexts[:20]),
                        )
                    except Exception:
                        pass
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
            self._apply_subscription_ack(message)
            return
        symbol = topic.rsplit(".", 1)[-1]
        with self._lock:
            context = self._contexts.get(symbol)
            flow = self._flow_only.get(symbol) if context is None else None
            witness = self._protected_research if context is not None else None
        if context is None:
            if flow is not None and flow.capture_book and topic == flow.book_topic:
                frame_type = message.get("type")
                if frame_type == "snapshot":
                    flow.book_frames.clear()
                elif frame_type != "delta" or not flow.book_frames:
                    return
                elif len(flow.book_frames) == flow.book_frames.maxlen:
                    flow.book_frames.clear()
                    return
                flow.book_frames.append((int(time.time() * 1000), message))
                return
            if flow is not None and topic == f"publicTrade.{flow.symbol}":
                result = flow.impulse_observation.observe(
                    message, received_at_ms=int(time.time() * 1000),
                )
                if result:
                    flow.trades_subscription_state = "SUBSCRIBED"
                    flow.trade_bootstrap_complete = True
            return
        if topic == f"orderbook.{context.public_orderbook.depth}.{symbol}":
            # Stamp the ORIGINAL frame at ingress, never invent a vendor
            # snapshot from the protected book's reconstructed state.
            received_at_ms = int(time.time() * 1000) if witness is not None else 0
            applied = context.public_orderbook.apply_message(message)
            if witness is not None and witness.context is context:
                try:
                    witness.on_book(received_at_ms, message, applied)
                except (AttributeError, TypeError, ValueError):
                    witness.reset()  # Observation must not block protection.
            component = "book"
        elif topic.startswith("publicTrade."):
            # Capture receipt at the real ingress boundary, before the existing
            # trade buffer's own processing/callback cost. This is NOT the
            # exchange event time and grants no trading authority.
            received_at_ms = int(time.time() * 1000)
            # Observe independently of the legacy aggregate buffer result:
            # IGNORED may conceal malformed/empty raw trade frames. This
            # observer remains strictly non-executing and fail-closed.
            context.impulse_observation.observe(
                message, received_at_ms=received_at_ms,
            )
            applied = context.public_trades.apply_message(message)
            component = "trades"
        else:
            return
        if applied == "APPLIED":
            context.subscription_state = "SUBSCRIBED"
            if component == "book":
                context.book_subscription_state = "SUBSCRIBED"
            else:
                context.trades_subscription_state = "SUBSCRIBED"
                context.trade_bootstrap_complete = True
            context.last_error = None

    def _apply_subscription_ack(self, message: dict) -> None:
        if message.get("op") != "subscribe":
            return
        request_id = message.get("req_id")
        if not isinstance(request_id, str):
            return
        if request_id.startswith("flowbook:") and request_id.endswith(":capture"):
            # The socket may accept send() yet reject the book subscription.
            # Keep publicTrade intact; permit the next sync to retry L2.
            symbol = request_id[len("flowbook:"):-len(":capture")]
            if message.get("success") is not True:
                with self._lock:
                    flow = self._flow_only.get(symbol)
                    if flow is not None:
                        flow.book_frames.clear()
                        flow.capture_book = False
            return
        if request_id.startswith("flow:"):
            symbol = request_id.removeprefix("flow:")
            with self._lock:
                flow = self._flow_only.get(symbol)
            if flow is None:
                return
            if message.get("success") is True:
                flow.trades_subscription_state = "SUBSCRIBED"
                flow.trade_bootstrap_complete = True
            else:
                flow.trades_subscription_state = "DEGRADED"
                flow.trade_bootstrap_complete = False
                flow.impulse_observation.mark_gap()
                flow.book_frames.clear()
            return
        if not request_id.startswith("workspace:"):
            return
        symbol = request_id.removeprefix("workspace:")
        with self._lock:
            context = self._contexts.get(symbol)
        if context is None:
            return
        if message.get("success") is True:
            context.subscription_state = "SUBSCRIBED"
            context.book_subscription_state = "SUBSCRIBED"
            context.trades_subscription_state = "SUBSCRIBED"
            context.trade_bootstrap_complete = True
            context.last_error = None
        else:
            context.subscription_state = "DEGRADED"
            context.book_subscription_state = "DEGRADED"
            context.trades_subscription_state = "DEGRADED"
            context.trade_bootstrap_complete = False
            context.last_error = str(message.get("ret_msg") or "subscription_rejected")
