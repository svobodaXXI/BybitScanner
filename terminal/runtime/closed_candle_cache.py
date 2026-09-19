"""Closed-candle cache that keeps Robot network reads off the PAPER owner thread.

The Robot closed-candle provider (``latest_scanner_closed_candle``) is a
blocking REST call. The background RobotBreakoutMonitor calls it on its own
thread every tick for every APPROVED candidate, which keeps this cache warm.
One-shot monitors that run ON the owner thread (entry finalization on fill,
continuity-loss recovery, pause/stop/reconcile synchronization) then read the
cached candle instead of going to the network.

Owner thread semantics:
- fresh entry (age <= max_age_s): returned without a network call;
- missing or stale entry: the previous behaviour -- fetch in place -- plus a
  rate-limited WARNING; a ``None`` fetch result is returned as before.
Any other thread always fetches and stores a non-``None`` result.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from scanner_geometry_cursor import latest_scanner_closed_candle


LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_AGE_S = 90.0
MISS_WARNING_INTERVAL_S = 60.0
WARM_MAX_WORKERS = 8

Candle = Mapping[str, object]


class CachedClosedCandleProvider:
    def __init__(
        self,
        fetch: Callable[[str], Candle | None] = latest_scanner_closed_candle,
        *,
        max_age_s: float = DEFAULT_MAX_AGE_S,
        clock: Callable[[], float] = time.monotonic,
        is_owner_thread: Callable[[], bool] | None = None,
    ) -> None:
        self._fetch = fetch
        self._max_age_s = max_age_s
        self._clock = clock
        self._is_owner_thread = is_owner_thread
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, Candle]] = {}
        self._last_miss_warning: dict[str, float] = {}
        self._hits = 0
        self._owner_misses = 0

    @property
    def fetch(self) -> Callable[[str], Candle | None]:
        return self._fetch

    def bind_owner_thread(self, is_owner_thread: Callable[[], bool]) -> None:
        """Use the runtime's existing owner-thread identity (its SQLiteStore owner)."""
        self._is_owner_thread = is_owner_thread

    def __call__(self, symbol: str) -> Candle | None:
        if self._on_owner_thread():
            now = self._clock()
            with self._lock:
                entry = self._entries.get(symbol)
                if entry is not None and now - entry[0] <= self._max_age_s:
                    self._hits += 1
                    return entry[1]
                self._owner_misses += 1
                last_warning = self._last_miss_warning.get(symbol)
                warn = last_warning is None or now - last_warning >= MISS_WARNING_INTERVAL_S
                if warn:
                    self._last_miss_warning[symbol] = now
            if warn:
                LOGGER.warning("candle cache miss on owner thread symbol=%s", symbol)
        return self._fetch_and_store(symbol)

    def warm(self, symbols: Iterable[str], *, max_workers: int = WARM_MAX_WORKERS) -> None:
        """Fetch ``symbols`` in parallel on the calling (non-owner) thread's pool.

        Errors are ignored: a later owner-thread miss falls back to fetching.
        """
        unique = sorted(set(symbols))
        if not unique:
            return
        with ThreadPoolExecutor(
            max_workers=min(max_workers, len(unique)), thread_name_prefix="robot-candle-warm",
        ) as pool:
            for future in [pool.submit(self._fetch_and_store, symbol) for symbol in unique]:
                try:
                    future.result()
                except Exception:
                    LOGGER.debug("candle cache warm-up failed", exc_info=True)

    def metrics(self) -> dict[str, int]:
        with self._lock:
            return {
                "candle_cache_hits": self._hits,
                "candle_cache_misses_owner": self._owner_misses,
            }

    def _on_owner_thread(self) -> bool:
        return self._is_owner_thread is not None and self._is_owner_thread()

    def _fetch_and_store(self, symbol: str) -> Candle | None:
        candle = self._fetch(symbol)
        if candle is not None:
            fetched_at = self._clock()
            with self._lock:
                self._entries[symbol] = (fetched_at, candle)
        return candle
