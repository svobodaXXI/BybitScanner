"""Causally confirmed exploratory 1h trend lines and 5m correction slopes.

NO trading signals or execution permissions. Provisional pivot wing=2 is a
research parameter, not an owner-approved pivot rule. Candidate trend and
reference lines are visible only after their *right-side* candles have closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from research.historical_market_replay import Candle

PivotKind = Literal["HIGH", "LOW"]
TrendSide = Literal["BULL", "BEAR"]


@dataclass(frozen=True)
class ConfirmedPivot:
    kind: PivotKind
    index: int
    at_ms: int
    confirmed_at_ms: int
    price: Decimal

    def __post_init__(self) -> None:
        if self.confirmed_at_ms <= self.at_ms:
            raise ValueError("pivot cannot be known before its candle closes")


@dataclass(frozen=True)
class CausalLine:
    first: ConfirmedPivot
    second: ConfirmedPivot
    available_at_ms: int

    def __post_init__(self) -> None:
        if self.first.index >= self.second.index or self.first.at_ms >= self.second.at_ms:
            raise ValueError("line anchors out of order")
        if self.available_at_ms < max(self.first.confirmed_at_ms, self.second.confirmed_at_ms):
            raise ValueError("line available before anchor confirmation")
        if self.first.kind != self.second.kind:
            raise ValueError("line must connect comparable extremes")

    def value_at(self, time_ms: int) -> Decimal:
        return self.first.price + (
            (self.second.price - self.first.price)
            * Decimal(time_ms - self.first.at_ms)
            / Decimal(self.second.at_ms - self.first.at_ms)
        )


@dataclass(frozen=True)
class TrendCandidate:
    side: TrendSide
    main: CausalLine  # 1--3, yellow solid
    target: CausalLine  # 2--4, yellow dashed
    pivot_sequence: tuple[ConfirmedPivot, ConfirmedPivot, ConfirmedPivot, ConfirmedPivot]
    available_at_ms: int
    classification: str = "UNVALIDATED_GEOMETRY_ONLY"


class ConfirmedSwingStream:
    """Strict, tie-free swing detection from closed candles, never future data."""

    def __init__(self, *, timeframe_ms: int, wing: int = 2) -> None:
        if timeframe_ms <= 0 or wing < 1:
            raise ValueError("invalid swing timeframe/wing")
        self.timeframe_ms = timeframe_ms
        self.wing = wing
        self._bars: list[Candle] = []
        self._pivots: list[ConfirmedPivot] = []

    @property
    def pivots(self) -> tuple[ConfirmedPivot, ...]:
        return tuple(self._pivots)

    @property
    def bars(self) -> tuple[Candle, ...]:
        return tuple(self._bars)

    @property
    def recent_pivots(self) -> tuple[ConfirmedPivot, ...]:
        return tuple(self._pivots[-4:])

    def bars_between(self, first: ConfirmedPivot, last: ConfirmedPivot) -> tuple[Candle, ...]:
        return tuple(self._bars[first.index + 1:last.index])

    def observe_closed(self, bar: Candle) -> ConfirmedPivot | None:
        if bar.interval_ms != self.timeframe_ms:
            raise ValueError("wrong candle interval")
        if self._bars and self._bars[-1].end_ms != bar.start_ms:
            raise ValueError("missing, duplicate or unordered candle")
        self._bars.append(bar)
        i = len(self._bars) - 1 - self.wing
        if i < self.wing:
            return None
        center = self._bars[i]
        neighbors = self._bars[i - self.wing:i] + self._bars[i + 1:i + self.wing + 1]
        is_high = all(center.high > x.high for x in neighbors)
        is_low = all(center.low < x.low for x in neighbors)
        if is_high == is_low:  # Neither, or an outside candle ambiguous on both axes.
            return None
        kind: PivotKind = "HIGH" if is_high else "LOW"
        result = ConfirmedPivot(
            kind=kind,
            index=i,
            at_ms=center.start_ms,
            confirmed_at_ms=bar.end_ms,
            price=center.high if is_high else center.low,
        )
        # A sequence of same-side candidate extrema keeps the more extreme
        # confirmed pivot. No retroactive changes are sent to past callbacks.
        if self._pivots and self._pivots[-1].kind == kind:
            prior = self._pivots[-1]
            if (kind == "HIGH" and result.price <= prior.price) or (
                kind == "LOW" and result.price >= prior.price
            ):
                return None
            self._pivots[-1] = result
        else:
            self._pivots.append(result)
        return result


def recent_hourly_trend(pivots: tuple[ConfirmedPivot, ...]) -> TrendCandidate | None:
    """Last 4 alternating 1h pivots, narrowing 1--3 / 2--4 envelope."""
    if len(pivots) < 4:
        return None
    a, b, c, d = pivots[-4:]
    kinds = tuple(p.kind for p in (a, b, c, d))
    if kinds == ("LOW", "HIGH", "LOW", "HIGH"):
        if c.price <= a.price or d.price <= b.price:
            return None
        side: TrendSide = "BULL"
        main, target = (a, c), (b, d)
    elif kinds == ("HIGH", "LOW", "HIGH", "LOW"):
        if c.price >= a.price or d.price >= b.price:
            return None
        side = "BEAR"
        main, target = (a, c), (b, d)
    else:
        return None
    confirmed = max(p.confirmed_at_ms for p in (a, b, c, d))
    primary = CausalLine(*main, confirmed)
    opposing = CausalLine(*target, confirmed)
    t2, t4 = b.at_ms, d.at_ms
    if side == "BULL":
        width2 = opposing.value_at(t2) - primary.value_at(t2)
        width4 = opposing.value_at(t4) - primary.value_at(t4)
    else:
        width2 = primary.value_at(t2) - opposing.value_at(t2)
        width4 = primary.value_at(t4) - opposing.value_at(t4)
    if not (width2 > width4 > 0):
        return None
    return TrendCandidate(side, primary, opposing, (a, b, c, d), confirmed)


def last_correction_reference(
    *,
    hourly: TrendCandidate | None,
    five_minute_pivots: tuple[ConfirmedPivot, ...],
    five_minute_bars: tuple[Candle, ...],
) -> CausalLine | None:
    """Provisional counter-trend reference through last H-L-H or L-H-L.

    Rejects a line pierced by any intermediate wick; never evaluates an unseen
    candle. Does not itself detect an entry or require a prior candle close.
    """
    if hourly is None or len(five_minute_pivots) < 3:
        return None
    p, middle, q = five_minute_pivots[-3:]
    if hourly.side == "BULL":
        if (p.kind, middle.kind, q.kind) != ("HIGH", "LOW", "HIGH"):
            return None
        if q.price >= p.price:
            return None
    else:
        if (p.kind, middle.kind, q.kind) != ("LOW", "HIGH", "LOW"):
            return None
        if q.price <= p.price:
            return None
    available = max(q.confirmed_at_ms, hourly.available_at_ms)
    line = CausalLine(p, q, available)
    for bar in five_minute_bars:
        if p.at_ms < bar.start_ms < q.at_ms:
            level = line.value_at(bar.start_ms)
            if (hourly.side == "BULL" and bar.high > level) or (
                hourly.side == "BEAR" and bar.low < level
            ):
                return None
    return line


class CausalGeometryFeed:
    """Continuous research-only states at a 5m candle-close boundary."""

    def __init__(self, *, wing_1h: int = 2, wing_5m: int = 2) -> None:
        from research.historical_candle_feed import FIVE_MINUTES_MS, ONE_HOUR_MS

        self._hourly = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=wing_1h)
        self._five = ConfirmedSwingStream(timeframe_ms=FIVE_MINUTES_MS, wing=wing_5m)
        self._hourly_trend: TrendCandidate | None = None

    def observe_closed(
        self, five_minute: Candle, newly_closed_1h: Candle | None,
    ) -> tuple[TrendCandidate | None, CausalLine | None]:
        self._five.observe_closed(five_minute)
        if newly_closed_1h is not None:
            self._hourly.observe_closed(newly_closed_1h)
            proposal = recent_hourly_trend(self._hourly.recent_pivots)
            if proposal is not None:
                # Redraw only after a NEW confirmed fourth (extreme) pivot,
                # never simply to hide a trendline break.
                if self._hourly_trend is None or (
                    proposal.pivot_sequence[3].at_ms >
                    self._hourly_trend.pivot_sequence[3].at_ms
                ):
                    self._hourly_trend = proposal
        recent = self._five.recent_pivots
        # Do not copy/scan all historical 5m bars on every replay tick.
        between = self._five.bars_between(recent[-3], recent[-1]) if len(recent) >= 3 else ()
        line = last_correction_reference(
            hourly=self._hourly_trend,
            five_minute_pivots=recent,
            five_minute_bars=between,
        )
        if line is not None and line.available_at_ms > five_minute.end_ms:
            raise AssertionError("future correction slope exposed")
        if self._hourly_trend is not None and self._hourly_trend.available_at_ms > five_minute.end_ms:
            raise AssertionError("future hourly trend exposed")
        return self._hourly_trend, line
