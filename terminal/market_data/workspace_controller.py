"""Atomic Workspace symbol authority, readiness barrier and warm-context lifecycle."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from terminal.market_data.hub import MarketDataHub, SymbolContext


@dataclass(frozen=True, slots=True)
class WorkspaceState:
    requested_symbol: str
    active_symbol: str
    active_generation: int
    switch_state: str
    pending_candidate: str | None
    last_switch_error: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceReadiness:
    ready: bool
    book_ready: bool
    trades_ready: bool
    candle_history_ready: bool
    live_candle_ready: bool


class WorkspaceController:
    """Publish a new active context only after one composite readiness barrier."""

    def __init__(
        self,
        hub: MarketDataHub,
        initial: SymbolContext,
        on_activate: Callable[[SymbolContext, SymbolContext], None],
        *,
        required_candle_interval: str = "5",
        warm_context_limit: int = 1,
        warm_grace_seconds: float = 30.0,
        poll_interval: float = 0.02,
    ) -> None:
        if warm_context_limit < 0 or warm_grace_seconds < 0 or poll_interval <= 0:
            raise ValueError("invalid WorkspaceController lifecycle settings")
        self._hub = hub
        self._active = initial
        self._active_generation = 1
        self._active.generation = 1
        self._requested_symbol = initial.symbol
        self._switch_state = "SYNCING"
        self._pending: SymbolContext | None = None
        self._last_switch_error: str | None = None
        self._on_activate = on_activate
        self._required_candle_interval = required_candle_interval
        self._warm_context_limit = warm_context_limit
        self._warm_grace_seconds = warm_grace_seconds
        self._poll_interval = poll_interval
        self._warm: dict[str, tuple[SymbolContext, float]] = {}
        self._warm_timers: dict[str, threading.Timer] = {}
        self._lock = threading.RLock()
        self._switch_lock = threading.Lock()

    def state(self) -> WorkspaceState:
        with self._lock:
            return WorkspaceState(
                self._requested_symbol,
                self._active.symbol,
                self._active_generation,
                self._switch_state,
                self._pending.symbol if self._pending is not None else None,
                self._last_switch_error,
            )

    def ensure_initial_ready(self, timeout: float) -> SymbolContext:
        readiness = self._wait_until_ready(self._active, timeout)
        with self._lock:
            if not readiness.ready:
                self._fail_locked("initial_workspace_not_ready")
                raise TimeoutError("Initial Workspace did not reach composite readiness")
            self._switch_state = "READY"
            self._last_switch_error = None
            return self._active

    def switch(self, symbol: str, timeout: float) -> SymbolContext:
        if not isinstance(symbol, str) or not symbol.strip():
            raise LookupError("unsupported Workspace symbol")
        normalized = symbol.strip().upper()
        with self._switch_lock:
            self._expire_warm()
            with self._lock:
                self._requested_symbol = normalized
                self._last_switch_error = None
                self._pending = None
                if normalized == self._active.symbol:
                    self._switch_state = "READY"
                    return self._active
                self._switch_state = "SYNCING"
            try:
                existed = self._hub.has_context(normalized)
                candidate = self._hub.subscribe(normalized)
            except Exception as exc:
                self._fail(type(exc).__name__)
                raise
            with self._lock:
                was_warm = self._warm.get(candidate.symbol, (None, 0))[0] is candidate
                if was_warm:
                    self._remove_warm_locked(candidate.symbol)
                self._pending = candidate
            readiness = self._wait_until_ready(candidate, timeout)
            if not readiness.ready:
                with self._lock:
                    self._pending = None
                    if was_warm:
                        self._retain_warm_locked(candidate)
                if not existed:
                    self._hub.discard(candidate)
                self._fail("workspace_candidate_not_ready")
                raise TimeoutError("Workspace candidate did not reach composite readiness")
            with self._lock:
                previous = self._active
                try:
                    self._on_activate(previous, candidate)
                except Exception as exc:
                    self._pending = None
                    self._fail_locked(type(exc).__name__)
                    if was_warm:
                        self._retain_warm_locked(candidate)
                    if not existed:
                        self._hub.discard(candidate)
                    raise
                self._active_generation += 1
                candidate.generation = self._active_generation
                self._active = candidate
                self._pending = None
                self._switch_state = "READY"
                self._last_switch_error = None
                self._retain_warm_locked(previous)
            self._enforce_warm_limit()
            return candidate

    def readiness(self, context: SymbolContext) -> WorkspaceReadiness:
        book = context.public_orderbook.snapshot()
        book_ready = (
            book.get("state") == "READY"
            and bool(book.get("bids"))
            and bool(book.get("asks"))
            and self._positive_int(book.get("version"))
            and self._positive_int(book.get("updateId"))
            and self._positive_int(book.get("sequence"))
        )
        trades_ready = (
            context.trades_subscription_state == "SUBSCRIBED"
            and context.trade_bootstrap_complete
        )
        candle = context.public_klines.get(self._required_candle_interval)
        candle_snapshot = candle.snapshot() if candle is not None else {}
        candle_history_ready = (
            candle_snapshot.get("state") == "READY"
            and bool(candle_snapshot.get("candles"))
        )
        live_candle_ready = candle_snapshot.get("state") == "READY"
        return WorkspaceReadiness(
            book_ready and trades_ready and candle_history_ready and live_candle_ready,
            book_ready, trades_ready, candle_history_ready, live_candle_ready,
        )

    @staticmethod
    def _positive_int(value: object) -> bool:
        if isinstance(value, bool):
            return False
        try:
            return int(value) > 0
        except (TypeError, ValueError):
            return False

    def get_active(self, symbol: str) -> tuple[SymbolContext, int]:
        normalized = symbol.strip().upper()
        with self._lock:
            if normalized != self._active.symbol:
                raise LookupError("inactive Workspace symbol")
            return self._active, self._active_generation

    def is_current(self, context: SymbolContext, generation: int) -> bool:
        with self._lock:
            return self._active is context and self._active_generation == generation

    def close(self) -> None:
        with self._lock:
            timers = tuple(self._warm_timers.values())
            self._warm_timers.clear()
            self._warm.clear()
        for timer in timers:
            timer.cancel()

    def _wait_until_ready(self, context: SymbolContext, timeout: float) -> WorkspaceReadiness:
        deadline = time.monotonic() + timeout
        while True:
            readiness = self.readiness(context)
            if readiness.ready or time.monotonic() >= deadline:
                return readiness
            time.sleep(min(self._poll_interval, max(0, deadline - time.monotonic())))

    def _fail(self, error: str) -> None:
        with self._lock:
            self._fail_locked(error)

    def _fail_locked(self, error: str) -> None:
        self._switch_state = "FAILED"
        self._last_switch_error = error

    def _retain_warm_locked(self, context: SymbolContext) -> None:
        if self._warm_context_limit == 0 or self._warm_grace_seconds == 0:
            return
        expires_at = time.monotonic() + self._warm_grace_seconds
        self._remove_warm_locked(context.symbol)
        self._warm[context.symbol] = (context, expires_at)
        timer = threading.Timer(
            self._warm_grace_seconds,
            self._expire_specific_warm,
            args=(context.symbol, context, expires_at),
        )
        timer.daemon = True
        self._warm_timers[context.symbol] = timer
        timer.start()

    def _remove_warm_locked(self, symbol: str) -> None:
        self._warm.pop(symbol, None)
        timer = self._warm_timers.pop(symbol, None)
        if timer is not None:
            timer.cancel()

    def _expire_specific_warm(
        self, symbol: str, context: SymbolContext, expires_at: float,
    ) -> None:
        with self._lock:
            current = self._warm.get(symbol)
            if current != (context, expires_at) or self._active is context:
                return
            self._warm.pop(symbol, None)
            self._warm_timers.pop(symbol, None)
        self._hub.discard(context)

    def _expire_warm(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [
                context for context, expires_at in self._warm.values()
                if expires_at <= now
            ]
            for context in expired:
                self._remove_warm_locked(context.symbol)
        for context in expired:
            self._hub.discard(context)

    def _enforce_warm_limit(self) -> None:
        with self._lock:
            ordered = sorted(self._warm.values(), key=lambda item: item[1])
            evicted = [item[0] for item in ordered[:-self._warm_context_limit]] if (
                len(ordered) > self._warm_context_limit
            ) else []
            for context in evicted:
                self._remove_warm_locked(context.symbol)
        for context in evicted:
            self._hub.discard(context)
