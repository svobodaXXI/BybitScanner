"""Closed, run-private M1/M5 source for the original MIRROR campaign replay.

The only writer is the local Simulator AFTER a successful M1 timeline commit.
No Bybit client, wall clock, network, PAPER account or DB is available here.
Missing history fails closed: a later candle must never masquerade as a
contiguous continuation of the original MIRROR boundary.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping

from research.historical_market_replay import Candle

MINUTE_MS = 60_000
FIVE_MS = 5 * MINUTE_MS
DEFAULT_MAX_MINUTES = 10_080  # bounded to seven days on a weak laptop
MAX_CANDLES_PER_READ = 64


def _closed_row(candle: Candle) -> dict[str, object]:
    return {
        "open_time_ms": candle.start_ms,
        "close_time_ms": candle.end_ms,
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
        "closed": True,
    }


class LocalMirrorClosedCandles:
    """Same closed-candle protocol the existing MirrorRobotPolicy consumes."""

    def __init__(self, symbol: str, *, max_minutes: int = DEFAULT_MAX_MINUTES):
        if not isinstance(symbol, str) or not symbol.endswith("USDT"):
            raise ValueError("exact SIMULATION symbol required")
        if (type(max_minutes) is not int or max_minutes < 10
                or max_minutes % 5 != 0):
            raise ValueError("MIRROR closed history requires a positive 5m buffer")
        self.symbol = symbol
        self._max_minutes = max_minutes
        self._m1 = deque()
        self._index: dict[int, Candle] = {}
        self._m5 = deque(maxlen=max_minutes // 5)
        self._last_close_ms: int | None = None

    def append_committed(self, candle: Candle, *, committed_time_ms: int) -> None:
        """Accept exactly the newest *committed* closed minute, never future OHLC."""
        if (not isinstance(candle, Candle) or candle.interval_ms != MINUTE_MS
                or type(committed_time_ms) is not int
                or candle.end_ms != committed_time_ms
                or candle.start_ms % MINUTE_MS != 0):
            raise ValueError("MIRROR requires a committed aligned closed M1")
        if (self._last_close_ms is not None
                and candle.start_ms != self._last_close_ms):
            raise ValueError("MIRROR source has missing, duplicate or future M1")
        if len(self._m1) == self._max_minutes:
            expired = self._m1.popleft()
            del self._index[expired.start_ms]
        self._m1.append(candle)
        self._index[candle.start_ms] = candle
        self._last_close_ms = candle.end_ms

        if committed_time_ms % FIVE_MS:
            return
        first_start = committed_time_ms - FIVE_MS
        group = tuple(self._index.get(first_start + n * MINUTE_MS)
                      for n in range(5))
        if any(item is None for item in group):
            # Initial partial 5m history cannot be presented as a complete bar.
            return
        from decimal import Decimal
        self._m5.append(Candle(
            start_ms=first_start, interval_ms=FIVE_MS,
            open=group[0].open, high=max(x.high for x in group),
            low=min(x.low for x in group), close=group[-1].close,
            volume=sum((x.volume for x in group), Decimal(0)),
        ))

    def _require_symbol(self, symbol: str) -> None:
        if symbol != self.symbol:
            raise ValueError("cross-symbol MIRROR replay is forbidden")

    def closed_candles(
        self, candidate_id: str, symbol: str, after_close_ms: int,
    ) -> tuple[dict[str, object], ...]:
        """Read a contiguous prefix AFTER the requested closed M5 cursor."""
        self._require_symbol(symbol)
        if (not isinstance(candidate_id, str) or not candidate_id
                or type(after_close_ms) is not int or after_close_ms < 0
                or after_close_ms % FIVE_MS != 0):
            raise ValueError("invalid MIRROR campaign cursor")
        if self._last_close_ms is None:
            return ()
        if after_close_ms > self._last_close_ms:
            raise ValueError("MIRROR request is beyond committed time")
        rows = [bar for bar in self._m5 if bar.end_ms > after_close_ms]
        if rows and rows[0].start_ms != after_close_ms:
            raise ValueError("MIRROR history prefix missing or expired")
        if (not rows and self._m5 and after_close_ms < self._m5[0].start_ms):
            raise ValueError("MIRROR history prefix expired")
        return tuple(_closed_row(bar) for bar in rows[:MAX_CANDLES_PER_READ])

    def fine_candles(
        self, symbol: str, coarse: Mapping[str, object],
    ) -> tuple[dict[str, object], ...]:
        """The exact five committed M1 belonging to this already closed M5."""
        self._require_symbol(symbol)
        if not isinstance(coarse, Mapping):
            raise ValueError("invalid MIRROR M5 candle")
        start, end = coarse.get("open_time_ms"), coarse.get("close_time_ms")
        if (type(start) is not int or type(end) is not int
                or start < 0 or start % FIVE_MS != 0
                or end != start + FIVE_MS or self._last_close_ms is None
                or end > self._last_close_ms):
            raise ValueError("MIRROR fine replay cannot read future M1")
        group = tuple(self._index.get(start + i * MINUTE_MS) for i in range(5))
        if any(bar is None for bar in group):
            raise ValueError("MIRROR fine M1 proof missing or expired")
        return tuple(_closed_row(bar) for bar in group)
