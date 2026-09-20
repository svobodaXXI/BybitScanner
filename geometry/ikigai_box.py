"""Read-only, detection-time Ikigai Box geometry; no orders or Robot admission.

See DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md. Supply CLOSED OHLC candles only.
An explicit as_of_index is inclusive; later rows are never inspected.
Detection thresholds below are initial, tunable hypotheses, NOT a validated
trading signal or an executable limit-grid placement policy.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class IkigaiBoxParameters:
    first_min_bars: int = 4
    first_max_bars: int = 16
    box_min_bars: int = 4
    box_max_bars: int = 14
    second_min_bars: int = 2
    second_max_bars: int = 15
    min_impulse_atr: float = 3.0
    min_impulse_fraction: float = 0.01
    max_box_width_fraction: float = 0.55
    max_box_retrace_fraction: float = 0.60
    # Alternative path for a first impulse ending in a rejection wick.
    # Never relax the ordinary body-driven impulse path globally.
    max_wick_box_retrace_fraction: float = 0.70
    min_terminal_rejection_fraction: float = 0.35
    min_wick_close_progress_fraction: float = 0.30
    min_second_progress: float = 0.30
    max_second_progress: float = 1.90


@dataclass(frozen=True)
class IkigaiBoxFormation:
    direction: str  # SHORT on two UP impulses; LONG on two DOWN impulses.
    impulse_start_index: int
    impulse_end_index: int
    box_start_index: int
    box_end_index: int
    second_start_index: int
    as_of_index: int
    anchor_start_index: int
    anchor_end_index: int
    anchor_start_price: float  # F(0), origin of first impulse.
    anchor_end_price: float  # F(1), terminal wick of first impulse.
    box_low: float
    box_high: float
    second_extreme: float
    fibonacci_1_0: float
    fibonacci_1_618: float
    fibonacci_2_618: float

    def fibonacci_price(self, level: float) -> float:
        """Price extension measured from the frozen FIRST impulse, never leg two."""
        return self.anchor_start_price + level * (
            self.anchor_end_price - self.anchor_start_price
        )



@dataclass(frozen=True)
class IkigaiBoxWatch:
    """Early observational candidate. NOT a confirmed reversal or order signal.

    One identity per (direction, A, B); the box is provisional until the
    caller freezes it. No chart/Telegram/Robot integration in this slice.
    """
    direction: str
    phase: str  # BOX_READY or BOX_BREAK_OBSERVED (not confirmed leg two)
    as_of_index: int
    anchor_start_index: int
    anchor_end_index: int
    anchor_start_price: float
    anchor_end_price: float
    box_start_index: int
    box_end_index: int
    box_low: float
    box_high: float
    first_box_exit_index: Optional[int]
    fibonacci_1_0: float
    fibonacci_1_618: float
    fibonacci_2_618: float

    @property
    def anchor_identity(self):
        return self.direction, self.anchor_start_index, self.anchor_end_index

    def fibonacci_price(self, level: float) -> float:
        return self.anchor_start_price + level * (
            self.anchor_end_price - self.anchor_start_price
        )

def _valid_ohlc(row):
    op, hi, lo, cl = row
    return (
        all(isfinite(v) and v > 0 for v in row)
        and lo <= op <= hi
        and lo <= cl <= hi
    )


def _pre_impulse_atr(rows, start):
    """Volatility sampled strictly BEFORE the selected first impulse."""
    if start < 14:
        return None
    ranges = []
    for i in range(start - 14, start):
        prev_close = rows[i - 1][3] if i > 0 else rows[i][3]
        op, hi, lo, cl = rows[i]
        ranges.append(max(hi - lo, abs(hi - prev_close), abs(lo - prev_close)))
    return sum(ranges) / len(ranges)




def _validate_parameters(p):
    if any(
        getattr(p, start) < 1 or getattr(p, end) < getattr(p, start)
        for start, end in (
            ("first_min_bars", "first_max_bars"),
            ("box_min_bars", "box_max_bars"),
            ("second_min_bars", "second_max_bars"),
        )
    ):
        raise ValueError("Invalid Ikigai Box segment lengths")
    if not (
        p.min_impulse_atr > 0
        and p.min_impulse_fraction > 0
        and 0 < p.max_box_width_fraction < 1
        and 0 < p.max_box_retrace_fraction <= p.max_wick_box_retrace_fraction < 1
        and 0 < p.min_terminal_rejection_fraction < 1
        and 0 < p.min_wick_close_progress_fraction < 0.60
        and 0 < p.min_second_progress < p.max_second_progress
    ):
        raise ValueError("Invalid Ikigai Box geometry thresholds")

def _qualified_first_impulse_and_box(
    rows, first_start, first_end, box_low, box_high, sign, p,
):
    """Shared frozen-A/B and consolidation gates for WATCH and confirmation."""
    first_n = first_end - first_start + 1
    first_rows = rows[first_start : first_end + 1]
    a = rows[first_start][2 if sign == 1 else 1]
    b = rows[first_end][1 if sign == 1 else 2]
    span = sign * (b - a)
    if span <= 0 or a <= 0:
        return None
    atr = _pre_impulse_atr(rows, first_start)
    if not atr or span < max(
        p.min_impulse_atr * atr, p.min_impulse_fraction * a
    ):
        return None
    # The origin is the earliest valid first-impulse extreme, and terminal B
    # its FIRST unique extremum, not an equal wick inside the following shelf.
    if (
        (sign == 1 and (
            min(row[2] for row in first_rows) < a
            or max(row[1] for row in first_rows[:-1]) >= b
        ))
        or (sign == -1 and (
            max(row[1] for row in first_rows) > a
            or min(row[2] for row in first_rows[:-1]) <= b
        ))
    ):
        return None
    close_move = sign * (rows[first_end][3] - rows[first_start][0])
    forward_bars = sum(
        sign * (row[3] - row[0]) > 0 for row in first_rows
    )
    ordinary_impulse = (
        close_move >= 0.60 * span
        and forward_bars * 5 >= first_n * 3
    )
    terminal_rejection = sign * (b - rows[first_end][3])
    wick_impulse = (
        terminal_rejection >= p.min_terminal_rejection_fraction * span
        and close_move >= p.min_wick_close_progress_fraction * span
        and forward_bars * 2 >= first_n
    )
    if not (ordinary_impulse or wick_impulse):
        return None
    if box_high - box_low > p.max_box_width_fraction * span:
        return None
    retrace = (b - box_low) if sign == 1 else (box_high - b)
    extension = (box_high - b) if sign == 1 else (b - box_low)
    allowed_retrace = (
        p.max_wick_box_retrace_fraction
        if wick_impulse
        else p.max_box_retrace_fraction
    )
    if not (
        0 <= retrace <= allowed_retrace * span
        and extension <= 0.12 * span
    ):
        return None
    return a, b, span, atr

def detect_ikigai_box(
    candles,
    *,
    as_of_index: Optional[int] = None,
    parameters: Optional[IkigaiBoxParameters] = None,
) -> Optional[IkigaiBoxFormation]:
    """Find a recent two-impulse / box / same-direction leg approaching extension.

    A false/ambiguous setup returns None. Offline observation only, not entry
    permission. There is no caller-supplied default distance for a LIMIT grid.
    """
    p = parameters or IkigaiBoxParameters()
    _validate_parameters(p)

    if candles is None or not all(
        column in candles.columns for column in ("open", "high", "low", "close")
    ):
        return None
    count = len(candles)
    end = count - 1 if as_of_index is None else as_of_index
    if type(end) is not int or not (0 <= end < count):
        return None
    minimum = 14 + p.first_min_bars + p.box_min_bars + p.second_min_bars
    if end + 1 < minimum:
        return None
    # Read ONLY the requested closed prefix: no future peeking via ATR, extrema,
    # anchoring, orientation, scores or candidate selection.
    try:
        rows = [
            tuple(map(float, row))
            for row in candles.iloc[: end + 1][
                ["open", "high", "low", "close"]
            ].itertuples(index=False, name=None)
        ]
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(_valid_ohlc(row) for row in rows):
        return None

    best = None
    best_rank = None
    for sign, direction in ((1, "SHORT"), (-1, "LONG")):
        for second_n in range(p.second_min_bars, p.second_max_bars + 1):
            second_start = end - second_n + 1
            for box_n in range(p.box_min_bars, p.box_max_bars + 1):
                box_end = second_start - 1
                box_start = box_end - box_n + 1
                if box_start < 14 + p.first_min_bars:
                    continue
                box_rows = rows[box_start : box_end + 1]
                box_low = min(row[2] for row in box_rows)
                box_high = max(row[1] for row in box_rows)
                second_rows = rows[second_start : end + 1]
                second_extreme = (
                    max(row[1] for row in second_rows)
                    if sign == 1
                    else min(row[2] for row in second_rows)
                )
                for first_n in range(p.first_min_bars, p.first_max_bars + 1):
                    first_end = box_start - 1
                    first_start = first_end - first_n + 1
                    if first_start < 14:
                        continue
                    qualified = _qualified_first_impulse_and_box(
                        rows, first_start, first_end,
                        box_low, box_high, sign, p,
                    )
                    if qualified is None:
                        continue
                    a, b, span, atr = qualified
                    progress = sign * (second_extreme - b) / span
                    if not (
                        p.min_second_progress
                        <= progress
                        <= p.max_second_progress
                    ):
                        continue
                    if sign * (
                        rows[end][3] - rows[box_end][3]
                    ) < 0.22 * span:
                        continue
                    # Choose a candidate near the 1.618/2.618 extension,
                    # with a compact box, reproducibly and without hindsight.
                    nearest_zone = min(
                        abs(progress - 0.618), abs(progress - 1.618)
                    )
                    rank = (
                        -nearest_zone,
                        -(box_high - box_low) / span,
                        span / atr,
                        -first_start,
                        -first_end,
                    )
                    if best_rank is not None and rank <= best_rank:
                        continue
                    best_rank = rank
                    best = IkigaiBoxFormation(
                        direction=direction,
                        impulse_start_index=first_start,
                        impulse_end_index=first_end,
                        box_start_index=box_start,
                        box_end_index=box_end,
                        second_start_index=second_start,
                        as_of_index=end,
                        anchor_start_index=first_start,
                        anchor_end_index=first_end,
                        anchor_start_price=a,
                        anchor_end_price=b,
                        box_low=box_low,
                        box_high=box_high,
                        second_extreme=second_extreme,
                        fibonacci_1_0=b,
                        fibonacci_1_618=a + 1.618 * (b - a),
                        fibonacci_2_618=a + 2.618 * (b - a),
                    )
    return best


def detect_ikigai_box_watches(
    candles,
    *,
    as_of_index: Optional[int] = None,
    parameters: Optional[IkigaiBoxParameters] = None,
):
    """Return distinct early WATCH candidates by FIRST-impulse anchor pair.

    BOX_READY needs only the first impulse and the following consolidation;
    BOX_BREAK_OBSERVED means at least one subsequent CLOSE broke the frozen
    box in the impulse direction, but does NOT confirm a sustained second leg.
    The first extension must not have been touched in the known prefix. This
    is pure offline discovery: no Scanner/Telegram/Robot emission or orders.
    A and B are not re-anchored to any later candle or other WATCH identity.
    """
    p = parameters or IkigaiBoxParameters()
    _validate_parameters(p)
    if candles is None or not all(
        col in candles.columns for col in ("open", "high", "low", "close")
    ):
        return ()
    count = len(candles)
    end = count - 1 if as_of_index is None else as_of_index
    if type(end) is not int or not 0 <= end < count:
        return ()
    if end + 1 < 14 + p.first_min_bars + p.box_min_bars:
        return ()
    # The source may include future rows; never read outside the closed prefix.
    try:
        rows = [
            tuple(map(float, row))
            for row in candles.iloc[: end + 1][
                ["open", "high", "low", "close"]
            ].itertuples(index=False, name=None)
        ]
    except (TypeError, ValueError, OverflowError):
        return ()
    if not all(_valid_ohlc(row) for row in rows):
        return ()

    selected = {}  # Stable independent identities: (direction, A-index, B-index).
    for sign, direction in ((1, "SHORT"), (-1, "LONG")):
        # A WATCH may persist during the early box break, without requiring
        # a second-impulse progress/close threshold or an apex.
        earliest_end = max(
            0, end - p.second_max_bars,
        )
        for box_end in range(end, earliest_end - 1, -1):
            followed = rows[box_end + 1 : end + 1]
            for box_n in range(p.box_min_bars, p.box_max_bars + 1):
                box_start = box_end - box_n + 1
                first_end = box_start - 1
                if first_end - p.first_min_bars + 1 < 14:
                    continue
                box_rows = rows[box_start : box_end + 1]
                box_low = min(row[2] for row in box_rows)
                box_high = max(row[1] for row in box_rows)
                # A CLOSE beyond the preceding shelf boundary marks a
                # possible breakout candle, not a newly enlarged shelf.
                # Without this, adding the breakout bar to the box hides
                # the first breakout until much later.
                if box_end == end and len(box_rows) > 1:
                    before_last = box_rows[:-1]
                    if (
                        rows[end][3] > max(row[1] for row in before_last)
                        if sign == 1
                        else rows[end][3] < min(row[2] for row in before_last)
                    ):
                        continue
                # A previous box can only persist if the subsequent candles
                # exhibit a real close outside its frozen boundary. Otherwise
                # the latest known candle must still belong to the shelf.
                first_exit = next((
                    box_end + 1 + i for i, row in enumerate(followed)
                    if (row[3] > box_high if sign == 1 else row[3] < box_low)
                ), None)
                if box_end != end and first_exit is None:
                    continue
                phase = (
                    "BOX_BREAK_OBSERVED" if first_exit is not None
                    else "BOX_READY"
                )
                for first_n in range(p.first_min_bars, p.first_max_bars + 1):
                    first_start = first_end - first_n + 1
                    if first_start < 14:
                        continue
                    qualified = _qualified_first_impulse_and_box(
                        rows, first_start, first_end,
                        box_low, box_high, sign, p,
                    )
                    if qualified is None:
                        continue
                    a, b, span, atr = qualified
                    extension = a + 1.618 * (b - a)
                    # An observation created AFTER the proposed entry zone
                    # was already reached is stale, not an advance WATCH.
                    # Also reject previously touched zones since box closure.
                    if any(
                        row[1] >= extension if sign == 1
                        else row[2] <= extension
                        for row in followed
                    ):
                        continue
                    watch = IkigaiBoxWatch(
                        direction=direction,
                        phase=phase,
                        as_of_index=end,
                        anchor_start_index=first_start,
                        anchor_end_index=first_end,
                        anchor_start_price=a,
                        anchor_end_price=b,
                        box_start_index=box_start,
                        box_end_index=box_end,
                        box_low=box_low,
                        box_high=box_high,
                        first_box_exit_index=first_exit,
                        fibonacci_1_0=b,
                        fibonacci_1_618=extension,
                        fibonacci_2_618=a + 2.618 * (b - a),
                    )
                    identity = watch.anchor_identity
                    # Keep each independent A/B candidate. Within that pair,
                    # preserve an already-observed EARLIER box exit rather
                    # than extending the box through its breakout candle.
                    rank = (
                        # Prefer the latest completed shelf when no current
                        # close has actually broken its preceding boundary.
                        # A short-lived excursion inside a later wider box
                        # must not be promoted into a confirmed second leg.
                        box_end,
                        box_n,
                        int(first_exit is not None),
                    )
                    previous = selected.get(identity)
                    if previous is None or rank > previous[0]:
                        selected[identity] = rank, watch
    # Do not rank away a newer A/B just because an older setup is closer
    # to 1.618. Consumers must track by anchor_identity, not by symbol only.
    return tuple(
        item[1] for _, item in sorted(
            selected.items(), key=lambda record: record[0], reverse=True,
        )
    )
