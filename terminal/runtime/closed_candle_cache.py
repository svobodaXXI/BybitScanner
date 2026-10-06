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

import hashlib
import json
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

    def peek(self, symbol: str) -> Candle | None:
        """Fresh cached candle or None. Never fetches, on any thread."""
        with self._lock:
            entry = self._entries.get(symbol)
            if entry is not None and self._clock() - entry[0] <= self._max_age_s:
                self._hits += 1
                return entry[1]
            self._owner_misses += 1
        return None

    def require_cached(self, symbol: str) -> Candle:
        """Recovery evidence only: never fall back to network on the owner.

        Missing/stale evidence keeps canonical recovery fail-closed. The HTTP
        command boundary warms this same cache before submitting owner work.
        """
        with self._lock:
            entry = self._entries.get(symbol)
            if entry is not None and self._clock() - entry[0] <= self._max_age_s:
                self._hits += 1
                return entry[1]
            self._owner_misses += 1
        raise RuntimeError(f"Robot recovery closed candle cache unavailable: {symbol}")

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


def _snapshot_key(symbol: str, signal_snapshot: Mapping[str, object]) -> tuple[str, str]:
    canonical = json.dumps(
        signal_snapshot, sort_keys=True, separators=(",", ":"), default=str,
    )
    return symbol, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PreparedCatchupEvidence:
    """Admission catch-up candles prepared OFF the owner thread.

    ``load_scanner_catchup_closed_candles`` is a blocking Bybit kline request.
    Owner-thread one-shot monitors (pause/stop/reconcile synchronization) get
    this object as their ``get_admission_catchup_candles``: it only returns
    evidence that ``prepare`` already fetched on a non-owner thread for that
    exact (symbol, signal snapshot), consumes it once, and raises -- never
    fetches -- when nothing fresh was prepared. The monitor then leaves the
    candidate uninitialized (no state, no order, no exposure), exactly as a
    failed fetch always has.
    """

    def __init__(
        self,
        fetch: Callable[[str, Mapping[str, object]], tuple],
        *,
        max_age_s: float = DEFAULT_MAX_AGE_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._max_age_s = max_age_s
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], tuple[float, tuple]] = {}

    @property
    def fetch(self) -> Callable[[str, Mapping[str, object]], tuple]:
        return self._fetch

    def prepare(self, targets: Iterable[tuple[str, Mapping[str, object]]]) -> None:
        """Fetch on the calling (non-owner) thread. Errors leave no evidence."""
        for symbol, signal_snapshot in targets:
            try:
                candles = tuple(self._fetch(symbol, signal_snapshot))
            except Exception:
                LOGGER.warning(
                    "Robot catch-up evidence unavailable symbol=%s", symbol, exc_info=True,
                )
                continue
            fetched_at = self._clock()
            with self._lock:
                self._entries[_snapshot_key(symbol, signal_snapshot)] = (fetched_at, candles)

    def __call__(self, symbol: str, signal_snapshot: Mapping[str, object]) -> tuple:
        key = _snapshot_key(symbol, signal_snapshot)
        with self._lock:
            entry = self._entries.pop(key, None)
        if entry is None or self._clock() - entry[0] > self._max_age_s:
            raise RuntimeError(
                f"Robot catch-up evidence was not prepared off the owner thread: {symbol}"
            )
        return entry[1]
