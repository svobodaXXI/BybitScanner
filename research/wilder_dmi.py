"""Causal Wilder DMI (+DI, -DI, ADX) over completed OHLC candles only.

Research-only implementation of TradingView/Pine-style ta.dmi: TR RMA is
seeded from the first bar, directional movement RMA from the first 14 actual
changes, ADX RMA from the first 14 DX samples. No volume or order data.
Comparison with a TradingView reference fixture is still required before
claiming numeric equivalence to any particular published chart settings.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from research.historical_market_replay import Candle

Side = Literal["PLUS", "MINUS"]
Direction = Literal["UP", "DOWN"]
Comparator = Literal["OPPOSITE_DI", "ADX", "LEVEL_20"]


@dataclass(frozen=True)
class DmiCrossing:
    side: Side
    direction: Direction
    comparator: Comparator
    time_ms: int


@dataclass(frozen=True)
class DmiSnapshot:
    time_ms: int
    plus_di: Decimal | None
    minus_di: Decimal | None
    adx: Decimal | None
    crossings: tuple[DmiCrossing, ...]
    di_length: int
    adx_smoothing: int

    @property
    def ready(self) -> bool:
        return self.plus_di is not None and self.minus_di is not None and self.adx is not None


class WilderDmi:
    """Time-ordered indicator stream. One instance per symbol/timeframe."""

    def __init__(
        self, *, timeframe_ms: int, di_length: int = 14,
        adx_smoothing: int = 14, threshold: Decimal = Decimal("20"),
    ) -> None:
        if timeframe_ms <= 0 or di_length < 2 or adx_smoothing < 2:
            raise ValueError("invalid DMI timeframe or smoothing")
        self.timeframe_ms = timeframe_ms
        self.di_length = di_length
        self.adx_smoothing = adx_smoothing
        self.threshold = Decimal(str(threshold))
        if not self.threshold.is_finite() or not Decimal(0) < self.threshold < Decimal(100):
            raise ValueError("invalid DI crossing threshold")
        self._previous: Candle | None = None
        self._previous_snapshot: DmiSnapshot | None = None
        self._tr_count = 0
        self._tr_total = Decimal(0)
        self._atr: Decimal | None = None
        self._dm_count = 0
        self._plus_total = Decimal(0)
        self._minus_total = Decimal(0)
        self._plus_rma: Decimal | None = None
        self._minus_rma: Decimal | None = None
        self._dx_count = 0
        self._dx_total = Decimal(0)
        self._adx: Decimal | None = None

    @staticmethod
    def _cross(
        before: Decimal, after: Decimal,
        before_reference: Decimal, after_reference: Decimal,
    ) -> Direction | None:
        if before <= before_reference and after > after_reference:
            return "UP"
        if before >= before_reference and after < after_reference:
            return "DOWN"
        return None

    def _crossings(
        self, now: DmiSnapshot,
    ) -> tuple[DmiCrossing, ...]:
        prev = self._previous_snapshot
        if prev is None:
            return ()
        out: list[DmiCrossing] = []
        for side in ("PLUS", "MINUS"):
            current = now.plus_di if side == "PLUS" else now.minus_di
            earlier = prev.plus_di if side == "PLUS" else prev.minus_di
            opposite_now = now.minus_di if side == "PLUS" else now.plus_di
            opposite_before = prev.minus_di if side == "PLUS" else prev.plus_di
            if current is None or earlier is None:
                continue
            comparators: tuple[tuple[Comparator, Decimal | None, Decimal | None], ...] = (
                ("OPPOSITE_DI", opposite_before, opposite_now),
                ("LEVEL_20", self.threshold, self.threshold),
                ("ADX", prev.adx, now.adx),
            )
            for name, before_ref, after_ref in comparators:
                if before_ref is None or after_ref is None:
                    continue  # Do not invent a crossover during indicator warmup.
                direction = self._cross(earlier, current, before_ref, after_ref)
                if direction is not None:
                    out.append(DmiCrossing(side, direction, name, now.time_ms))
        return tuple(out)

    def observe_closed(self, bar: Candle) -> DmiSnapshot:
        if not isinstance(bar, Candle) or bar.interval_ms != self.timeframe_ms:
            raise ValueError("DMI requires completed candles of a single timeframe")
        prev = self._previous
        if prev is not None and bar.start_ms != prev.end_ms:
            raise ValueError("DMI history has a missing, overlapping or duplicate candle")
        if prev is None:
            tr = bar.high - bar.low
            positive_dm = negative_dm = Decimal(0)
        else:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - prev.close),
                abs(bar.low - prev.close),
            )
            up_move = bar.high - prev.high
            down_move = prev.low - bar.low
            positive_dm = up_move if up_move > 0 and up_move > down_move else Decimal(0)
            negative_dm = down_move if down_move > 0 and down_move > up_move else Decimal(0)

        n = Decimal(self.di_length)
        if self._atr is None:
            self._tr_total += tr
            self._tr_count += 1
            if self._tr_count == self.di_length:
                self._atr = self._tr_total / n
        else:
            self._atr = (self._atr * (n - 1) + tr) / n

        if prev is not None:
            if self._plus_rma is None:
                self._dm_count += 1
                self._plus_total += positive_dm
                self._minus_total += negative_dm
                if self._dm_count == self.di_length:
                    self._plus_rma = self._plus_total / n
                    self._minus_rma = self._minus_total / n
            else:
                self._plus_rma = (self._plus_rma * (n - 1) + positive_dm) / n
                assert self._minus_rma is not None
                self._minus_rma = (self._minus_rma * (n - 1) + negative_dm) / n

        plus_di: Decimal | None = None
        minus_di: Decimal | None = None
        if self._atr is not None and self._plus_rma is not None:
            assert self._minus_rma is not None
            if self._atr == 0:
                plus_di = minus_di = Decimal(0)
            else:
                plus_di = Decimal(100) * self._plus_rma / self._atr
                minus_di = Decimal(100) * self._minus_rma / self._atr

            combined = plus_di + minus_di
            dx = Decimal(0) if combined == 0 else Decimal(100) * abs(plus_di - minus_di) / combined
            k = Decimal(self.adx_smoothing)
            if self._adx is None:
                self._dx_count += 1
                self._dx_total += dx
                if self._dx_count == self.adx_smoothing:
                    self._adx = self._dx_total / k
            else:
                self._adx = (self._adx * (k - 1) + dx) / k

        now = DmiSnapshot(
            time_ms=bar.end_ms,
            plus_di=plus_di,
            minus_di=minus_di,
            adx=self._adx,
            crossings=(),
            di_length=self.di_length,
            adx_smoothing=self.adx_smoothing,
        )
        now = DmiSnapshot(
            time_ms=now.time_ms,
            plus_di=now.plus_di,
            minus_di=now.minus_di,
            adx=now.adx,
            crossings=self._crossings(now),
            di_length=now.di_length,
            adx_smoothing=now.adx_smoothing,
        )
        self._previous = bar
        self._previous_snapshot = now
        return now
