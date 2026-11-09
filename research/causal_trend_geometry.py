"""Causally confirmed exploratory 1h trend lines and 5m correction slopes.

Single H-017 detector for offline replay and future Scanner pattern fan-out.
Consumes only supplied closed H1/M5 candles; owns no data fetching, Telegram,
execution, PAPER state, or other pattern logic. The default one-bar swing wing
is a research heuristic for points 1–3; point 4 is published when its own
extremum candle closes, with no later right-wing lookahead.
NO trading signals or execution permissions.
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

    def __init__(self, *, timeframe_ms: int, wing: int = 2,
                 seed_first_pivot: bool = False) -> None:
        if timeframe_ms <= 0 or wing < 1:
            raise ValueError("invalid swing timeframe/wing")
        self.timeframe_ms = timeframe_ms
        self.wing = wing
        self.seed_first_pivot = seed_first_pivot
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
        if self.seed_first_pivot and len(self._bars) == self.wing + 1:
            # The source boundary has no candles to its left. The initial H1
            # candle is a *candidate*, not an instantly confirmed extremum:
            # it qualifies only after the usual right-side wing has CLOSED.
            first = self._bars[0]
            following = self._bars[1:]
            high = all(first.high > bar.high for bar in following)
            low = all(first.low < bar.low for bar in following)
            if high != low:
                pivot = ConfirmedPivot(
                    kind="HIGH" if high else "LOW", index=0,
                    at_ms=first.start_ms, confirmed_at_ms=bar.end_ms,
                    price=first.high if high else first.low,
                )
                self._pivots.append(pivot)
                return pivot
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


def closed_fourth_pivot(
    pivots: tuple[ConfirmedPivot, ...], bars: tuple[Candle, ...], just_closed: Candle,
) -> ConfirmedPivot | None:
    """Publish point 4 on its OWN close, without an extra right-wing delay.

    Points 1..3 remain genuinely confirmed swings. The fourth is an observed
    higher high / lower low, not a future-confirmed local peak/trough. Keep the
    event time separate from the candle's anchor time for replay causality.
    """
    if len(pivots) < 3 or not bars or bars[-1] != just_closed:
        return None
    a, b, c = pivots[-3:]
    if c.index >= len(bars) - 1 or c.confirmed_at_ms > just_closed.end_ms:
        return None
    if (a.kind, b.kind, c.kind) == ("LOW", "HIGH", "LOW"):
        if c.price <= a.price or just_closed.high <= b.price:
            return None
        # An outside bar exceeding BOTH sides is not an unambiguous point 4.
        if just_closed.low < c.price:
            return None
        kind, price = "HIGH", just_closed.high
    elif (a.kind, b.kind, c.kind) == ("HIGH", "LOW", "HIGH"):
        if c.price >= a.price or just_closed.low >= b.price:
            return None
        if just_closed.high > c.price:
            return None
        kind, price = "LOW", just_closed.low
    else:
        return None
    return ConfirmedPivot(
        kind=kind, index=len(bars) - 1, at_ms=just_closed.start_ms,
        confirmed_at_ms=just_closed.end_ms, price=price,
    )


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



def trend_from_frozen_first_pair(
    pivots: tuple[ConfirmedPivot, ...],
    first: ConfirmedPivot, second: ConfirmedPivot,
) -> TrendCandidate | None:
    """Newest confirmed 3/4 against immutable movement origin 1/2."""
    if len(pivots) < 4 or first.at_ms >= second.at_ms:
        return None
    c, d = pivots[-2:]
    if c.at_ms <= second.at_ms or d.at_ms <= c.at_ms:
        return None
    return recent_hourly_trend((first, second, c, d))


def original_reversal_trend(
    pivots: tuple[ConfirmedPivot, ...],
    *, side: TrendSide, source_start_ms: int, known_at_ms: int,
) -> TrendCandidate | None:
    """Start at preceding impulse's highest/lowest *confirmed* pivot.

    The source window starts at the retired trend's first main anchor, not at
    the latest four-pivot suffix. Never backdate a pivot or invent a wick.
    """
    known = tuple(p for p in pivots if p.at_ms >= source_start_ms
                  and p.confirmed_at_ms <= known_at_ms)
    main_kind: PivotKind = "HIGH" if side == "BEAR" else "LOW"
    origins = [p for p in known if p.kind == main_kind]
    if not origins:
        return None
    first = (max(origins, key=lambda p: (p.price, -p.at_ms)) if side == "BEAR"
             else min(origins, key=lambda p: (p.price, p.at_ms)))
    second = next((p for p in known if p.at_ms > first.at_ms
                   and p.kind != main_kind), None)
    if second is None:
        return None
    return trend_from_frozen_first_pair(known, first, second)


def wick_tight_hourly_line(
    first: ConfirmedPivot, second: ConfirmedPivot,
    bars: tuple[Candle, ...], *, boundary: Literal["UPPER", "LOWER"],
    available_at_ms: int,
) -> CausalLine | None:
    """Validate the line between two ORIGINAL confirmed H1 swing pivots.

    A wick through 1--3 or 2--4 invalidates this candidate. It must never
    move point 3/4 to an arbitrary intermediate candle to make the envelope
    fit: that used to publish spurious four-point H1 trends.
    """
    if first.index >= second.index or first.kind != second.kind:
        return None
    if first.kind != ("HIGH" if boundary == "UPPER" else "LOW"):
        return None
    if second.confirmed_at_ms > available_at_ms or first.confirmed_at_ms > available_at_ms:
        return None
    if first.index < 0 or second.index >= len(bars):
        return None
    for pivot in (first, second):
        bar = bars[pivot.index]
        extreme = bar.high if boundary == "UPPER" else bar.low
        if bar.start_ms != pivot.at_ms or extreme != pivot.price:
            return None
    line = CausalLine(first, second, available_at_ms)
    for index in range(first.index + 1, second.index + 1):
        bar = bars[index]
        if bar.end_ms > available_at_ms:
            return None
        level = line.value_at(bar.start_ms)
        if ((boundary == "UPPER" and bar.high > level) or
                (boundary == "LOWER" and bar.low < level)):
            return None
    return line


def wick_tight_hourly_trend(
    proposal: TrendCandidate, bars: tuple[Candle, ...],
    *, first_main: ConfirmedPivot | None = None,
    first_target: ConfirmedPivot | None = None,
) -> TrendCandidate | None:
    """Validate true 1--3 / 2--4 H1 pivot anchors; never substitute wicks."""
    a = first_main or proposal.main.first
    b = first_target or proposal.target.first
    c, d = proposal.main.second, proposal.target.second
    side = proposal.side
    main = wick_tight_hourly_line(
        a, c, bars, boundary="LOWER" if side == "BULL" else "UPPER",
        available_at_ms=proposal.available_at_ms,
    )
    target = wick_tight_hourly_line(
        b, d, bars, boundary="UPPER" if side == "BULL" else "LOWER",
        available_at_ms=proposal.available_at_ms,
    )
    if main is None or target is None:
        return None
    # Direction belongs to the trend, not to HIGH/LOW: both yellow
    # boundaries must rise in BULL and fall in BEAR.
    if side == "BULL":
        if main.second.price <= a.price or target.second.price <= b.price:
            return None
    elif main.second.price >= a.price or target.second.price >= b.price:
        return None
    t2, t4 = b.at_ms, d.at_ms
    if side == "BULL":
        width2 = target.value_at(t2) - main.value_at(t2)
        width4 = target.value_at(t4) - main.value_at(t4)
    else:
        width2 = main.value_at(t2) - target.value_at(t2)
        width4 = main.value_at(t4) - target.value_at(t4)
    if not (width2 > width4 > 0):
        return None
    return TrendCandidate(
        side, main, target, (a, b, c, d),
        proposal.available_at_ms,
    )




def reanchor_bear_on_closed_lower_low(
    previous: TrendCandidate,
    pivots: tuple[ConfirmedPivot, ...],
    bars: tuple[Candle, ...],
    just_closed: Candle,
) -> TrendCandidate | None:
    """Move the SAME bearish H1 main line to its preceding confirmed HIGH.

    A continuation revision is not a new four-pivot trend. The initial
    four-pivot qualification remains immutable. Once an H1 candle closes
    with a new lower low after a confirmed high, the existing second support
    moves to that real high without waiting for the new LOW swing to confirm.
    """
    if previous.side != "BEAR" or not bars or just_closed != bars[-1]:
        return None
    previous_low = previous.target.second
    if just_closed.start_ms <= previous_low.at_ms or just_closed.low >= previous_low.price:
        return None
    # The old 2--4 LOW belongs to the ORIGINAL four-pivot qualification
    # and must not serve forever as the continuation threshold. A later
    # H1 candle that dips below that frozen LOW but remains ABOVE an
    # already observed lower low is NOT a new low of this movement.
    # On real GRASS 29 Aug 21:00 that stale comparison invented a
    # same-side reanchor and moved the purple prior without a new low.
    earlier_lows = [
        bar.low for bar in bars
        if previous.main.first.at_ms <= bar.start_ms < just_closed.start_ms
    ]
    if not earlier_lows or just_closed.low >= min(earlier_lows):
        return None
    highs = [
        p for p in pivots
        if p.kind == "HIGH"
        and previous.main.second.at_ms < p.at_ms < just_closed.start_ms
        and p.confirmed_at_ms <= just_closed.end_ms
        and p.price < previous.main.first.price
    ]
    if not highs:
        return None
    support = highs[-1]
    if support.at_ms <= previous_low.at_ms:
        return None
    main = wick_tight_hourly_line(
        previous.main.first, support, bars, boundary="UPPER",
        available_at_ms=just_closed.end_ms,
    )
    if main is None:
        return None
    return TrendCandidate(
        previous.side, main, previous.target,
        previous.pivot_sequence, just_closed.end_ms,
        "CONTINUATION_REANCHOR_AFTER_CLOSED_LOWER_LOW",
    )


def last_correction_reference(
    *,
    hourly: TrendCandidate | None,
    five_minute_pivots: tuple[ConfirmedPivot, ...],
    five_minute_bars: tuple[Candle, ...],
) -> CausalLine | None:
    """Validate a counter-H1 reference through ORIGINAL confirmed M5 pivots.

    This helper validates the 1--3 boundary of an H-L-H/L-H-L sequence.
    Publication is separately gated on the confirmed fourth M5 swing by
    CausalGeometryFeed. Never refit point 3 to an intermediate non-pivot wick:
    a piercing candle invalidates the candidate, not its pivot provenance.
    """
    if hourly is None or len(five_minute_pivots) < 3:
        return None
    p, middle, q = five_minute_pivots[-3:]
    if not (p.at_ms < middle.at_ms < q.at_ms and
            p.confirmed_at_ms <= middle.confirmed_at_ms <= q.confirmed_at_ms):
        return None
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
    # Validate only already closed M5 candles between true pivots 1 and 3;
    # the right-confirmation of pivot 4 remains the publication gate.
    for bar in five_minute_bars:
        if p.at_ms < bar.start_ms <= q.at_ms:
            if bar.end_ms > available:
                return None
            if bar.start_ms == q.at_ms:
                extreme = bar.high if hourly.side == "BULL" else bar.low
                if extreme != q.price:
                    return None
            level = line.value_at(bar.start_ms)
            if (hourly.side == "BULL" and bar.high > level) or (
                hourly.side == "BEAR" and bar.low < level
            ):
                return None
    return line


def main_line_contact(trend: TrendCandidate | None, bar: Candle) -> Decimal | None:
    """Closed-bar OHLC test of an ALREADY KNOWN hourly 1--3 line.

    This is research-only contact evidence, NOT an entry or a confirmed
    bounce. The entire moving line's 5m price interval must lie within the
    candle's high/low, and the close must remain on the trend side. Requiring
    the line to be known at the bar OPEN avoids backdating new H1 pivots.
    """
    if trend is None or trend.available_at_ms > bar.start_ms:
        return None
    at_open = trend.main.value_at(bar.start_ms)
    at_close = trend.main.value_at(bar.end_ms)
    if bar.low > min(at_open, at_close) or bar.high < max(at_open, at_close):
        return None
    if trend.side == "BULL" and bar.close < at_close:
        return None
    if trend.side == "BEAR" and bar.close > at_close:
        return None
    return at_close



class CausalGeometryFeed:
    """Time-causal local H1 state: trend continuation, prior break, opposite line.

    A contrary four-pivot candidate alone never reverses the active trend.
    A full H1 close beyond the confirmed second main-line pivot followed by
    the next H1 open beyond it first retires the trend. Only an already
    confirmed, directionally opposite four-pivot candidate may start the new
    yellow 1--3/2--4 geometry. No provisional future pivot is painted.
    """

    def __init__(self, *, wing_1h: int = 1, wing_5m: int = 1) -> None:
        # One right-side closed candle suffices to confirm point 3 at the
        # close of point 4; a two-bar wing delays H1/M5 beyond owner timing.
        from research.historical_candle_feed import FIVE_MINUTES_MS, ONE_HOUR_MS

        self._hourly = ConfirmedSwingStream(
            timeframe_ms=ONE_HOUR_MS, wing=wing_1h, seed_first_pivot=True,
        )
        self._five = ConfirmedSwingStream(timeframe_ms=FIVE_MINUTES_MS, wing=wing_5m)
        self._hourly_trend: TrendCandidate | None = None
        # Purple prior is confirmed from CLOSED H1 wicks; it is separate
        # from the latest yellow line's refitted second anchor.
        self._prior_movement: tuple[TrendSide, int, Decimal] | None = None
        self._prior_price: Decimal | None = None
        self._prior_touch_ms: int | None = None
        self._prior_trend_version: int | None = None
        self._last_hourly_prior_break: dict[str, object] | None = None
        self._last_prior_candidate_touch_ms: int | None = None
        # (second-touch time, wick price, prior trend extreme, side, known-at).
        self._prior_candidates: list[tuple[int, Decimal, Decimal, TrendSide, int]] = []
        # H1 close, frozen prior, side, contact, publication version.
        self._pending_break: tuple[int, Decimal, TrendSide, int, int] | None = None
        self._waiting_for_side: TrendSide | None = None
        self._reversal_known_at_ms: int | None = None
        self._reversal_source_start_ms: int | None = None
        # The M5 correction is its own stateful movement: new pivots must
        # never silently replace its first anchor or create parallel blues.
        self._active_blue: CausalLine | None = None
        self._active_blue_hourly_first_ms: int | None = None
        # Extremum of the M5 countertrend movement at the previous valid
        # three-pivot confirmation; first blue wick anchor stays immutable.
        self._active_blue_correction_extreme: Decimal | None = None
        self._active_blue_checked_q_ms: int | None = None
        self._blue_broken_at_ms: int | None = None

    @property
    def confirmed_hourly_prior(self) -> Decimal | None:
        """Latest causally confirmed purple H1 level, independent of a re-fit."""
        return self._prior_price

    @property
    def confirmed_hourly_prior_touch_ms(self) -> int | None:
        """H1 second-contact wick timestamp that licensed the current prior."""
        return self._prior_touch_ms

    @property
    def confirmed_hourly_prior_break(self) -> dict[str, object] | None:
        """Only the break confirmed by this closed M5, never a later guess."""
        return self._last_hourly_prior_break

    def _advance_hourly_prior(self, closed_at_ms: int) -> None:
        trend = self._hourly_trend
        if trend is None:
            return
        line = trend.main
        movement = (trend.side, line.first.at_ms, line.first.price)
        if self._prior_movement != movement:
            self._prior_movement = movement
            self._prior_price = line.second.price
            self._prior_touch_ms = line.second.at_ms
            self._prior_trend_version = trend.available_at_ms
            self._last_prior_candidate_touch_ms = line.second.at_ms
            self._prior_candidates = []
            return
        # Owner H1 BEAR rule: once a NEW fully confirmed LH+LL publishes a
        # descending structural version, its confirmed lower HIGH becomes
        # BOTH the yellow line's newer support and the purple prior. The
        # same-origin case was previously missed because candidate scanning
        # started strictly AFTER line.second; thus the new actual pivot was
        # never considered. Do not publish from a mere HIGH wick / lone LH.
        if (
            trend.side == "BEAR"
            and self._prior_touch_ms is not None
            and line.second.at_ms > self._prior_touch_ms
            and self._prior_price is not None
            and (line.second.price < self._prior_price or
                 trend.classification == "CONTINUATION_REANCHOR_AFTER_CLOSED_LOWER_LOW")
            and trend.available_at_ms <= closed_at_ms
            and trend.pivot_sequence[3].kind == "LOW"
            and trend.pivot_sequence[3].confirmed_at_ms <= closed_at_ms
        ):
            self._prior_price = line.second.price
            self._prior_touch_ms = line.second.at_ms
            self._prior_trend_version = trend.available_at_ms
            self._last_prior_candidate_touch_ms = line.second.at_ms
            self._prior_candidates = []
            return
        # The PURPLE prior follows new confirmed H1 touches of the already
        # frozen 1--3 line; it does not need a newly refitted yellow 1--3/2--4.
        # A wick-pierced H1 proposal must be rejected, but that rejection
        # cannot erase a legitimate later pivot touching the old line.
        for pivot in self._hourly.pivots:
            touch = pivot.at_ms
            if pivot.kind != line.first.kind or touch <= line.second.at_ms or (
                self._last_prior_candidate_touch_ms is not None and
                touch <= self._last_prior_candidate_touch_ms
            ) or pivot.confirmed_at_ms > closed_at_ms:
                continue
            # Only an actual confirmed H1 pivot at the time-evaluated line
            # level qualifies; not a near miss, a local M5 wick or a re-fit.
            if pivot.price != line.value_at(touch):
                continue
            self._last_prior_candidate_touch_ms = touch
            if self._prior_price is None or not (
                (trend.side == "BULL" and pivot.price > self._prior_price) or
                (trend.side == "BEAR" and pivot.price < self._prior_price)
            ):
                continue
            earlier = [
                bar for bar in self._hourly.bars
                if line.first.at_ms <= bar.start_ms < touch
                and bar.end_ms <= closed_at_ms
            ]
            if earlier:
                extreme = (
                    max(bar.high for bar in earlier) if trend.side == "BULL"
                    else min(bar.low for bar in earlier)
                )
                self._prior_candidates.append((
                    touch, pivot.price, extreme, trend.side, pivot.confirmed_at_ms,
                ))
        # A touch is never enough. Only a later, FULLY CLOSED H1 extreme
        # advances the prior. Pending touches remain eligible after a re-fit.
        for touch, price, extreme, side, known_at in self._prior_candidates:
            if known_at > closed_at_ms or self._prior_price is None or (
                self._prior_touch_ms is not None and touch <= self._prior_touch_ms
            ):
                continue
            qualified = any(
                bar.start_ms > touch and bar.end_ms <= closed_at_ms and
                (bar.high > extreme if side == "BULL" else bar.low < extreme)
                for bar in self._hourly.bars
            )
            if qualified and (
                (side == "BULL" and price > self._prior_price) or
                (side == "BEAR" and price < self._prior_price)
            ):
                self._prior_price = price
                self._prior_touch_ms = touch
                self._prior_trend_version = trend.available_at_ms

    def _install_opposite_if_confirmed(
        self, at_ms: int, just_closed_1h: Candle | None = None,
    ) -> None:
        if self._waiting_for_side is None:
            return
        if self._reversal_source_start_ms is None:
            return
        proposal = original_reversal_trend(
            self._hourly.pivots, side=self._waiting_for_side,
            source_start_ms=self._reversal_source_start_ms,
            known_at_ms=at_ms,
        )
        if proposal is None and just_closed_1h is not None:
            fourth = closed_fourth_pivot(
                self._hourly.pivots, self._hourly.bars, just_closed_1h,
            )
            if fourth is not None:
                candidate = recent_hourly_trend(self._hourly.pivots[-3:] + (fourth,))
                if (candidate is not None and candidate.side == self._waiting_for_side
                        and candidate.main.first.at_ms >= self._reversal_source_start_ms):
                    proposal = candidate
        if proposal is None:
            return
        if proposal.available_at_ms > at_ms:
            raise AssertionError("future opposite hourly trend exposed")
        # An older candidate cannot acquire the status of the NEW trend
        # before the prior broke. Preserve its frozen wick anchors, but
        # make the new version known no earlier than confirmation.
        available = max(proposal.available_at_ms, self._reversal_known_at_ms or at_ms)
        fitted = wick_tight_hourly_trend(proposal, self._hourly.bars)
        if fitted is None:
            return  # Unproven candidate cannot terminate the waiting state.
        self._hourly_trend = TrendCandidate(
            fitted.side,
            CausalLine(fitted.main.first, fitted.main.second, available),
            CausalLine(fitted.target.first, fitted.target.second, available),
            fitted.pivot_sequence,
            available,
        )
        self._waiting_for_side = None
        self._reversal_known_at_ms = None
        self._reversal_source_start_ms = None

    def observe_closed(
        self, five_minute: Candle, newly_closed_1h: Candle | None,
    ) -> tuple[TrendCandidate | None, CausalLine | None]:
        self._five.observe_closed(five_minute)
        self._last_hourly_prior_break = None
        if self._pending_break is not None:
            hourly_end, prior, old_side, prior_touch, prior_version = self._pending_break
            # Only the first M5 of the very next H1 can confirm its OPEN.
            self._pending_break = None
            if five_minute.start_ms == hourly_end:
                beyond = (five_minute.open < prior if old_side == "BULL" else
                          five_minute.open > prior)
                if beyond:
                    self._last_hourly_prior_break = {
                        "confirmed_at_ms": five_minute.end_ms,
                        "previous_side": old_side,
                        "new_side": "BEAR" if old_side == "BULL" else "BULL",
                        "prior_price": prior,
                        "prior_at_ms": prior_touch,
                        "trend_version": prior_version,
                        "hourly_close_ms": hourly_end,
                        "next_hour_open_ms": five_minute.start_ms,
                    }
                    self._reversal_source_start_ms = (
                        self._hourly_trend.main.first.at_ms
                        if self._hourly_trend is not None else None
                    )
                    self._hourly_trend = None
                    self._waiting_for_side = "BEAR" if old_side == "BULL" else "BULL"
                    self._reversal_known_at_ms = five_minute.end_ms
        if newly_closed_1h is not None:
            # Evaluate the PREVIOUSLY KNOWN trend, before today's H1
            # extrema can confirm a different pivot or revise the prior.
            old = self._hourly_trend
            if old is not None and old.available_at_ms <= newly_closed_1h.start_ms:
                # Freeze the level known BEFORE this H1 candle. Do not use
                # a newly revised yellow anchor or this hour's own wick.
                prior = self._prior_price
                outside = prior is not None and (
                    newly_closed_1h.close < prior if old.side == "BULL" else
                    newly_closed_1h.close > prior
                )
                if outside and self._prior_touch_ms is not None and self._prior_trend_version is not None:
                    self._pending_break = (
                        newly_closed_1h.end_ms, prior, old.side,
                        self._prior_touch_ms, self._prior_trend_version,
                    )
            self._hourly.observe_closed(newly_closed_1h)
            if self._waiting_for_side is None:
                previous = self._hourly_trend
                if previous is None:
                    proposal = recent_hourly_trend(self._hourly.recent_pivots)
                    if proposal is None:
                        fourth = closed_fourth_pivot(
                            self._hourly.pivots, self._hourly.bars, newly_closed_1h,
                        )
                        if fourth is not None:
                            proposal = recent_hourly_trend(self._hourly.pivots[-3:] + (fourth,))
                    if proposal is not None:
                        fitted = wick_tight_hourly_trend(proposal, self._hourly.bars)
                        if fitted is not None:
                            self._hourly_trend = fitted
                elif previous.side == "BEAR":
                    # One movement = ONE fixed first H1 HIGH. Later lower
                    # lows may revise ONLY the second HIGH of that same
                    # descending line, using an already confirmed pivot and
                    # a wick-clear line from the original first anchor.
                    # NEVER choose a newer first HIGH inside an unbroken
                    # bearish movement: that created a spurious BEAR->BEAR
                    # line on the owner's GRASS screenshots. A new movement
                    # requires the independently confirmed purple-prior
                    # break followed by an opposite four-pivot structure.
                    fitted = reanchor_bear_on_closed_lower_low(
                        previous, self._hourly.pivots,
                        self._hourly.bars, newly_closed_1h,
                    )
                    if fitted is not None:
                        self._hourly_trend = fitted
                else:
                    # Preserve the existing BULL lifecycle and independent
                    # prior-confirmation semantics; today's owner regression
                    # concerns only the BEAR lower-high/lower-low boundary.
                    proposal = trend_from_frozen_first_pair(
                        self._hourly.pivots,
                        previous.main.first, previous.target.first,
                    )
                    if (proposal is not None and proposal.side == previous.side and
                            proposal.pivot_sequence[3].at_ms >
                            previous.pivot_sequence[3].at_ms):
                        fitted = wick_tight_hourly_trend(proposal, self._hourly.bars)
                        if fitted is not None:
                            self._hourly_trend = fitted
        self._install_opposite_if_confirmed(five_minute.end_ms, newly_closed_1h)
        trend = self._hourly_trend
        movement = ((trend.side, trend.main.first.at_ms, trend.main.first.price)
                    if trend is not None else None)
        # A new opposite trend may be confirmed on an M5 CLOSE. Do not
        # attach the retired movement's purple prior until another H1 closes.
        if trend is not None and (newly_closed_1h is not None or
                                  movement != self._prior_movement):
            self._advance_hourly_prior(five_minute.end_ms)
        trend = self._hourly_trend
        # A structurally retired/reversed H1 trend also ends its associated M5
        # correction; a mere H1 re-fit inside the SAME movement does not.
        origin = trend.main.first.at_ms if trend is not None else None
        if (trend is None or (self._active_blue is not None and
                self._active_blue_hourly_first_ms != origin)):
            self._active_blue = None
            self._active_blue_hourly_first_ms = None
            self._active_blue_correction_extreme = None
            self._active_blue_checked_q_ms = None
        if self._active_blue is not None and trend is not None:
            line = self._active_blue
            # H-017 continuation is the NEXT M5 OPEN beyond the already
            # published blue, not a wick and not a new pivot. The record is
            # exposed at this bar's CLOSE by the causal replay cursor.
            if line.available_at_ms <= five_minute.start_ms and (
                (trend.side == "BULL" and
                 five_minute.open > line.value_at(five_minute.start_ms)) or
                (trend.side == "BEAR" and
                 five_minute.open < line.value_at(five_minute.start_ms))
            ):
                self._active_blue = None
                self._active_blue_hourly_first_ms = None
                self._active_blue_correction_extreme = None
                self._active_blue_checked_q_ms = None
                self._blue_broken_at_ms = five_minute.end_ms
        if self._active_blue is None and trend is not None:
            recent = self._five.recent_pivots
            # Point 4 is known on the closed break of the previous point 2,
            # not after an additional arbitrary right-wing confirmation.
            if len(recent) >= 3:
                fourth = closed_fourth_pivot(self._five.pivots, self._five.bars, five_minute)
                if fourth is not None:
                    recent = self._five.pivots[-3:] + (fourth,)
            # Publication requires four SIGNIFICANT, confirmed M5 swings,
            # just like the independent H1 trend. Three pivots establish
            # only a provisional slope: never export it as a blue reference.
            # BULL H1: descending HIGH-LOW-lower HIGH-lower LOW.
            # BEAR H1: rising LOW-HIGH-higher LOW-higher HIGH.
            four = len(recent) == 4 and (
                (trend.side == "BULL" and
                 tuple(p.kind for p in recent) == ("HIGH", "LOW", "HIGH", "LOW") and
                 recent[2].price < recent[0].price and
                 recent[3].price < recent[1].price)
                or
                (trend.side == "BEAR" and
                 tuple(p.kind for p in recent) == ("LOW", "HIGH", "LOW", "HIGH") and
                 recent[2].price > recent[0].price and
                 recent[3].price > recent[1].price)
            )
            if four and (
                self._blue_broken_at_ms is None or
                recent[0].at_ms > self._blue_broken_at_ms
            ):
                between = self._five.bars_between(recent[0], recent[2])
                candidate = last_correction_reference(
                    hourly=trend,
                    five_minute_pivots=recent[:3],
                    five_minute_bars=between,
                )
                if candidate is not None:
                    # The 1-3 line is published when the closed fourth
                    # extremum exceeds point 2, never before that close.
                    published = CausalLine(
                        candidate.first, candidate.second,
                        max(candidate.available_at_ms, recent[3].confirmed_at_ms),
                    )
                    self._active_blue = published
                    self._active_blue_hourly_first_ms = origin
                    self._active_blue_correction_extreme = recent[3].price
                    self._active_blue_checked_q_ms = recent[2].confirmed_at_ms
        elif self._active_blue is not None and trend is not None:
            recent = self._five.recent_pivots
            first = self._active_blue.first
            if len(recent) >= 2:
                middle, q = recent[-2:]
                old_extreme = self._active_blue_correction_extreme
                # A longer correction keeps point 1. Refitting point 2 is
                # licensed only by a NEW deepest LOW (BULL H1) / highest HIGH
                # (BEAR H1), followed by a new CONFIRMED return pivot.
                new_extreme = (old_extreme is not None and
                               (middle.price < old_extreme if trend.side == "BULL"
                                else middle.price > old_extreme))
                eligible = (
                    q.kind == first.kind and middle.kind != first.kind and
                    middle.at_ms > first.at_ms and q.at_ms > middle.at_ms and
                    (self._active_blue_checked_q_ms is None or
                     q.confirmed_at_ms > self._active_blue_checked_q_ms)
                )
                if eligible and new_extreme:
                    self._active_blue_checked_q_ms = q.confirmed_at_ms
                    # Refitting is bounded by q: no later wick can leak into
                    # this version, and previously published versions stay
                    # immutable in the exported geometry timeline.
                    bars = self._five.bars_between(first, q)
                    revised = last_correction_reference(
                        hourly=trend, five_minute_pivots=(first, middle, q),
                        five_minute_bars=bars,
                    )
                    if revised is not None:
                        self._active_blue_correction_extreme = middle.price
                        if (revised.first != self._active_blue.first or
                            revised.second != self._active_blue.second):
                            self._active_blue = revised
        line = self._active_blue
        if line is not None and line.available_at_ms > five_minute.end_ms:
            raise AssertionError("future correction slope exposed")
        if trend is not None and trend.available_at_ms > five_minute.end_ms:
            raise AssertionError("future hourly trend exposed")
        return trend, line
