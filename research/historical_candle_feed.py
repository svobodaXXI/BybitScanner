"""Historical 5m candles and strictly CLOSED 1h/4h context for offline replay.

The downloader receives an injected read-only candle fetch function; this module
never imports Bybit HTTP, PAPER runtime, credentials, or trading endpoints.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from research.historical_market_replay import (
    Candle, ClosedBarView, EntryIntent, ReplayResult, replay_candles,
)
from research.wilder_dmi import DmiSnapshot, WilderDmi

FIVE_MINUTES_MS = 300_000
ONE_HOUR_MS = 3_600_000
FOUR_HOURS_MS = 14_400_000


def load_closed_five_minute_history(
    *,
    symbol: str,
    start_ms: int,
    end_ms: int,
    fetch_candles: Callable[..., object],
    page_limit: int = 1000,
) -> tuple[Candle, ...]:
    """Fetch an exact UTC-aligned [start_ms, end_ms) historical 5m range.

    The injected fetch function has the existing bybit_api.get_candles signature
    (symbol, interval, limit, *, end_ms). Results may be pandas DataFrames or
    row mappings, newest-first or oldest-first. A missing/inconsistent candle
    fails closed instead of silently manufacturing a backtest result.
    """
    if not symbol or not symbol.strip():
        raise ValueError("symbol is required")
    if (
        start_ms < 0 or end_ms <= start_ms
        or start_ms % FIVE_MINUTES_MS or end_ms % FIVE_MINUTES_MS
    ):
        raise ValueError("history bounds must be ascending UTC 5m boundaries")
    if not 1 <= page_limit <= 1000:
        raise ValueError("invalid Bybit page limit")

    required_count = (end_ms - start_ms) // FIVE_MINUTES_MS
    candles: dict[int, Candle] = {}
    cursor = end_ms - 1
    # Even a broken endpoint giving one bar per page cannot loop forever.
    for _ in range(required_count + 2):
        raw = fetch_candles(symbol, "5", page_limit, end_ms=cursor)
        if hasattr(raw, "to_dict"):
            records = raw.to_dict(orient="records")
        else:
            records = raw
        if not isinstance(records, (list, tuple)) or not records:
            raise ValueError("Bybit history ended before required range was complete")

        oldest: int | None = None
        for row in records:
            if not isinstance(row, Mapping):
                raise ValueError("invalid candle row")
            timestamp = int(row["time"])
            if timestamp > cursor:
                # Some backends may return the newest forming candle despite
                # the end cursor. Ignore it, but still require page progress.
                continue
            if timestamp % FIVE_MINUTES_MS:
                raise ValueError("unaligned Bybit candle timestamp")
            oldest = timestamp if oldest is None else min(oldest, timestamp)
            if start_ms <= timestamp < end_ms:
                item = Candle(
                    start_ms=timestamp, interval_ms=FIVE_MINUTES_MS,
                    open=row["open"], high=row["high"], low=row["low"],
                    close=row["close"], volume=row["volume"],
                )
                if timestamp in candles and candles[timestamp] != item:
                    raise ValueError("conflicting duplicate historical candle")
                candles[timestamp] = item

        if oldest is None or oldest >= cursor:
            raise ValueError("Bybit historical pagination did not advance")
        if oldest <= start_ms:
            break
        cursor = oldest - 1
    else:
        raise ValueError("Bybit pagination exceeded strict history bound")

    expected = range(start_ms, end_ms, FIVE_MINUTES_MS)
    if any(t not in candles for t in expected):
        raise ValueError("missing historical 5m candles; refusing incomplete replay")
    return tuple(candles[t] for t in expected)


@dataclass(frozen=True)
class ClosedMultiTimeframeView:
    five_minute: ClosedBarView
    last_closed_1h: Candle | None
    last_closed_4h: Candle | None
    newly_closed_1h: Candle | None
    newly_closed_4h: Candle | None
    dmi_5m: DmiSnapshot | None = None
    last_closed_dmi_1h: DmiSnapshot | None = None
    last_closed_dmi_4h: DmiSnapshot | None = None


class ClosedHigherTimeframeFeed:
    """Aggregate exactly consecutive completed UTC 5m bars; never publish partials."""

    def __init__(self) -> None:
        self._last_end_ms: int | None = None
        self._building_1h: list[Candle] = []
        self._building_4h: list[Candle] = []
        self._closed_1h: Candle | None = None
        self._closed_4h: Candle | None = None

    @staticmethod
    def _aggregate(bars: Sequence[Candle], interval_ms: int) -> Candle | None:
        if not bars:
            return None
        bucket_start = (bars[0].start_ms // interval_ms) * interval_ms
        expected = interval_ms // FIVE_MINUTES_MS
        if (
            len(bars) != expected
            or bars[0].start_ms != bucket_start
            or bars[-1].end_ms != bucket_start + interval_ms
            or any(bar.start_ms != bucket_start + i * FIVE_MINUTES_MS
                   for i, bar in enumerate(bars))
        ):
            return None
        return Candle(
            start_ms=bucket_start, interval_ms=interval_ms,
            open=bars[0].open, high=max(b.high for b in bars),
            low=min(b.low for b in bars), close=bars[-1].close,
            volume=sum((b.volume for b in bars), start=bars[0].volume * 0),
        )

    @staticmethod
    def _push(bars: list[Candle], bar: Candle, span: int) -> tuple[list[Candle], Candle | None]:
        bucket = bar.start_ms // span
        if bars and bars[0].start_ms // span != bucket:
            bars = []
        bars.append(bar)
        if bar.end_ms == (bucket + 1) * span:
            result = ClosedHigherTimeframeFeed._aggregate(bars, span)
            return [], result
        return bars, None

    def observe_closed_five_minute(self, bar: Candle) -> tuple[Candle | None, Candle | None, Candle | None, Candle | None]:
        """Call at a confirmed 5m close; return (last H1, last H4, new H1, new H4)."""
        if bar.interval_ms != FIVE_MINUTES_MS or bar.start_ms % FIVE_MINUTES_MS:
            raise ValueError("context input must be UTC-aligned 5m")
        if self._last_end_ms is not None and bar.start_ms < self._last_end_ms:
            raise ValueError("context received overlapping/out-of-order candle")
        self._last_end_ms = bar.end_ms
        self._building_1h, new_1h = self._push(self._building_1h, bar, ONE_HOUR_MS)
        self._building_4h, new_4h = self._push(self._building_4h, bar, FOUR_HOURS_MS)
        if new_1h is not None:
            self._closed_1h = new_1h
        if new_4h is not None:
            self._closed_4h = new_4h
        return self._closed_1h, self._closed_4h, new_1h, new_4h


def replay_with_closed_context(
    *,
    simulation_run_id: str,
    candles: Sequence[Candle],
    on_closed_context: Callable[[ClosedMultiTimeframeView], EntryIntent | None],
    **replay_options: object,
) -> ReplayResult:
    """Wrap the existing offline executor with causal 1h/4h context."""
    context = ClosedHigherTimeframeFeed()
    dmi_5m = WilderDmi(timeframe_ms=FIVE_MINUTES_MS)
    dmi_1h = WilderDmi(timeframe_ms=ONE_HOUR_MS)
    dmi_4h = WilderDmi(timeframe_ms=FOUR_HOURS_MS)
    last_dmi_1h: DmiSnapshot | None = None
    last_dmi_4h: DmiSnapshot | None = None

    def on_close(view: ClosedBarView) -> EntryIntent | None:
        nonlocal last_dmi_1h, last_dmi_4h
        h1, h4, new_h1, new_h4 = context.observe_closed_five_minute(view.bar)
        dmi5 = dmi_5m.observe_closed(view.bar)
        if new_h1 is not None:
            last_dmi_1h = dmi_1h.observe_closed(new_h1)
        if new_h4 is not None:
            last_dmi_4h = dmi_4h.observe_closed(new_h4)
        assert h1 is None or h1.end_ms <= view.signal_time_ms
        assert h4 is None or h4.end_ms <= view.signal_time_ms
        assert last_dmi_1h is None or last_dmi_1h.time_ms <= view.signal_time_ms
        assert last_dmi_4h is None or last_dmi_4h.time_ms <= view.signal_time_ms
        return on_closed_context(
            ClosedMultiTimeframeView(
                view, h1, h4, new_h1, new_h4,
                dmi5, last_dmi_1h, last_dmi_4h,
            )
        )

    return replay_candles(
        simulation_run_id=simulation_run_id,
        candles=candles,
        on_closed_bar=on_close,
        **replay_options,
    )
