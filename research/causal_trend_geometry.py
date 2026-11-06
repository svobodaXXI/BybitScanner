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


def confirmed_four_pivot_side(
    pivots: tuple[ConfirmedPivot, ...],
) -> TrendSide | None:
    """One closed-candle, four-swing structure shared by H1 and M5.

    The fourth pivot is a real confirmed swing, not the most recent
    still-forming wick. Significance calibration is separate research.
    """
    if len(pivots) < 4:
        return None
    a, b, c, d = pivots[-4:]
    kinds = tuple(p.kind for p in (a, b, c, d))
    if kinds == ("LOW", "HIGH", "LOW", "HIGH") and (
        c.price > a.price and d.price > b.price
    ):
        return "BULL"
    if kinds == ("HIGH", "LOW", "HIGH", "LOW") and (
        c.price < a.price and d.price < b.price
    ):
        return "BEAR"
    return None


def recent_hourly_trend(pivots: tuple[ConfirmedPivot, ...]) -> TrendCandidate | None:
    """Four confirmed H1 pivots, narrowing 1--3 / 2--4 envelope."""
    side = confirmed_four_pivot_side(pivots)
    if side is None:
        return None
    a, b, c, d = pivots[-4:]
    main, target = (a, c), (b, d)
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


def wick_tight_hourly_line(
    first: ConfirmedPivot, second: ConfirmedPivot,
    bars: tuple[Candle, ...], *, boundary: Literal["UPPER", "LOWER"],
    available_at_ms: int,
) -> CausalLine | None:
    """Keep the first wick fixed; fit the worst known protrusion by slope.

    Only CLOSED bars between the two anchors count. This is a candidate
    geometry revision, never a retroactive edit to an emitted version.
    """
    if first.index >= second.index or first.kind != second.kind:
        return None
    chosen = second
    slope = (second.price - first.price) / Decimal(second.at_ms - first.at_ms)
    for index in range(first.index + 1, second.index + 1):
        if index >= len(bars):
            return None
        bar = bars[index]
        if bar.end_ms > available_at_ms:
            return None
        price = bar.high if boundary == "UPPER" else bar.low
        trial = (price - first.price) / Decimal(bar.start_ms - first.at_ms)
        if (trial > slope if boundary == "UPPER" else trial < slope):
            slope = trial
            chosen = ConfirmedPivot(
                first.kind, index, bar.start_ms, bar.end_ms, price,
            )
    line = CausalLine(first, chosen, available_at_ms)
    for index in range(first.index + 1, second.index + 1):
        bar = bars[index]
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
    """Fit candidate H1 boundaries while retaining the movement's first pair."""
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
        side, main, target, (a, b, main.second, target.second),
        proposal.available_at_ms,
    )


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
    # Keep the first known correction extreme fixed. For a descending upper
    # bound choose the candle with the greatest slope from that anchor;
    # for a rising lower bound choose the smallest slope. A mere absolute
    # max/min wick is not enough to keep every intervening candle inside.
    # No future data: only already closed candles through pivot q are used.
    selected = q
    slope = (q.price - p.price) / Decimal(q.at_ms - p.at_ms)
    for bar in five_minute_bars:
        if not (p.at_ms < bar.start_ms <= q.at_ms):
            continue
        price = bar.high if hourly.side == "BULL" else bar.low
        trial = (price - p.price) / Decimal(bar.start_ms - p.at_ms)
        tighter = trial > slope if hourly.side == "BULL" else trial < slope
        if tighter:
            slope = trial
            # A closed candle's wick is known at its close, not a pivot
            # inferred from future bars. It is still a geometry-only anchor.
            selected = ConfirmedPivot(
                kind=p.kind,
                index=p.index + (bar.start_ms - p.at_ms) // bar.interval_ms,
                at_ms=bar.start_ms,
                confirmed_at_ms=bar.end_ms,
                price=price,
            )
    if not (slope < 0 if hourly.side == "BULL" else slope > 0):
        return None
    available = max(q.confirmed_at_ms, selected.confirmed_at_ms,
                    hourly.available_at_ms)
    line = CausalLine(p, selected, available)
    # Verify the whole known segment, including wicks after the chosen
    # second anchor. Do not hide a later breakout by retroactively moving
    # this frozen candidate once emitted.
    for bar in five_minute_bars:
        if p.at_ms < bar.start_ms <= q.at_ms:
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

    def __init__(self, *, wing_1h: int = 2, wing_5m: int = 2) -> None:
        from research.historical_candle_feed import FIVE_MINUTES_MS, ONE_HOUR_MS

        self._hourly = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=wing_1h)
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
        touch = line.second.at_ms
        if self._last_prior_candidate_touch_ms is None or touch > self._last_prior_candidate_touch_ms:
            self._last_prior_candidate_touch_ms = touch
            if self._prior_price is not None and (
                (trend.side == "BULL" and line.second.price > self._prior_price) or
                (trend.side == "BEAR" and line.second.price < self._prior_price)
            ):
                # The original first wick remains fixed; the old trend
                # extreme is known from H1 bars strictly BEFORE this touch.
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
                        touch, line.second.price, extreme, trend.side, line.available_at_ms,
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

    def _install_opposite_if_confirmed(self, at_ms: int) -> None:
        if self._waiting_for_side is None:
            return
        proposal = recent_hourly_trend(self._hourly.recent_pivots)
        if proposal is None or proposal.side != self._waiting_for_side:
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
                proposal = recent_hourly_trend(self._hourly.recent_pivots)
                if proposal is not None:
                    if self._hourly_trend is None:
                        fitted = wick_tight_hourly_trend(proposal, self._hourly.bars)
                        if fitted is not None:
                            self._hourly_trend = fitted
                    elif (proposal.side == self._hourly_trend.side and
                          proposal.pivot_sequence[3].at_ms >
                          self._hourly_trend.pivot_sequence[3].at_ms):
                        # The original 1/2 anchors belong to this movement.
                        # New extrema may revise points 3/4, never shift the
                        # first pair forward by taking the last four pivots.
                        previous = self._hourly_trend
                        fitted = wick_tight_hourly_trend(
                            proposal, self._hourly.bars,
                            first_main=previous.main.first,
                            first_target=previous.target.first,
                        )
                        if fitted is not None:
                            self._hourly_trend = fitted
        self._install_opposite_if_confirmed(five_minute.end_ms)
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
            # Do NOT publish a blue reference from a partial H-L-H / L-H-L
            # setup. The opposite M5 correction requires its own confirmed
            # fourth structural pivot (lower LOW / higher HIGH).
            opposite_side: TrendSide = "BEAR" if trend.side == "BULL" else "BULL"
            if (len(recent) >= 4 and
                confirmed_four_pivot_side(recent) == opposite_side and
                (self._blue_broken_at_ms is None or
                 recent[-4].at_ms > self._blue_broken_at_ms)):
                first, middle, third, fourth = recent[-4:]
                between = self._five.bars_between(first, third)
                candidate = last_correction_reference(
                    hourly=trend,
                    five_minute_pivots=(first, middle, third),
                    five_minute_bars=between,
                )
                if candidate is not None:
                    # A valid line shape does not grant publication until
                    # point 4 is confirmed on the M5 stream.
                    available = max(candidate.available_at_ms, fourth.confirmed_at_ms)
                    self._active_blue = CausalLine(
                        candidate.first, candidate.second, available,
                    )
                    self._active_blue_hourly_first_ms = origin
                    self._active_blue_correction_extreme = middle.price
                    self._active_blue_checked_q_ms = third.confirmed_at_ms
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
