"""
geometry.l_shape

Autonomous offline detector for the L-shaped continuation formation
(BACKLOG.md G6): a pronounced directional impulse followed by a short, narrow
consolidation -- the "shelf" -- that holds near the extreme of that impulse.

LONG  : rising impulse, shelf near the impulse high.
SHORT : falling impulse, shelf near the impulse low.

The formation starts at the beginning of the impulse, not at the first shelf
bar, so ``start_index`` is deliberately the impulse start.

Responsibility:
- read already loaded closed candles and report one formation or nothing.

Not responsible for:
- trading decisions, Robot admission, STOP/TAKE, Telegram, Scanner wiring;
- a generic pattern engine, ranking or scoring.

Only candles up to ``as_of_index`` are read, so a later bar can never change an
earlier verdict and a confirmed historical anchor is never re-derived from
future data.
"""

from __future__ import annotations

from dataclasses import dataclass

from confirmation import calculate_atr

DIRECTION_LONG = "LONG"
DIRECTION_SHORT = "SHORT"


@dataclass(frozen=True)
class LShapeParameters:
    """Named, tunable thresholds. Deliberately coarse: no per-ticker fitting.

    atr_period
        Period of the existing project ATR (``confirmation.calculate_atr``).
    impulse_min_bars / impulse_max_bars
        Bounded search window for the impulse leg.
    impulse_min_atr_multiple
        The impulse high-low range must be at least this many ATR.
    impulse_min_directional_ratio
        Net close-to-close move divided by the impulse range: separates a real
        directional leg from a wide but aimless swing.
    impulse_peak_last_fraction
        The impulse extreme must print in this trailing fraction of the leg, so
        the move actually ends at its extreme.
    impulse_min_bar_progress_atr
        Average net progress per impulse bar, in ATR units. This is what stops a
        long flat prelude from being absorbed into the impulse: adding dead bars
        lowers the pace below the floor.
    shelf_min_bars / shelf_max_bars
        Bounded search window for the consolidation.
    shelf_max_height_atr_multiple
        Shelf height ceiling in ATR units.
    shelf_max_height_impulse_fraction
        Shelf height ceiling as a fraction of the impulse range.
    shelf_max_retrace_fraction
        How far the shelf may pull back from the impulse extreme, as a fraction
        of the impulse range. This is what rejects a deep retracement.
    """

    atr_period: int = 14
    impulse_min_bars: int = 3
    impulse_max_bars: int = 30
    impulse_min_atr_multiple: float = 3.0
    impulse_min_directional_ratio: float = 0.6
    impulse_peak_last_fraction: float = 0.5
    impulse_min_bar_progress_atr: float = 0.5
    shelf_min_bars: int = 4
    shelf_max_bars: int = 20
    shelf_max_height_atr_multiple: float = 1.2
    shelf_max_height_impulse_fraction: float = 0.35
    shelf_max_retrace_fraction: float = 0.35


DEFAULT_PARAMETERS = LShapeParameters()


@dataclass(frozen=True)
class LShapeFormation:
    """One detected formation, in source candle indices."""

    direction: str
    start_index: int              # the impulse start: the figure starts here
    impulse_start_index: int
    impulse_end_index: int
    shelf_start_index: int
    shelf_end_index: int
    shelf_high: float
    shelf_low: float
    shelf_height: float
    impulse_low: float
    impulse_high: float
    impulse_range: float
    impulse_extreme_index: int
    atr: float
    impulse_atr_multiple: float
    impulse_directional_ratio: float
    impulse_bar_progress_atr_multiple: float
    shelf_height_atr_multiple: float
    shelf_height_impulse_fraction: float
    shelf_retrace_fraction: float
    as_of_index: int


def _series(candles):
    """Accept a DataFrame or any sequence of OHLC mappings, read-only."""
    if candles is None:
        return None
    if hasattr(candles, "to_dict"):
        rows = candles.to_dict("records")
    else:
        rows = list(candles)
    if not rows:
        return None
    try:
        return [
            (
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
            )
            for row in rows
        ]
    except (KeyError, TypeError, ValueError):
        return None


def _atr_at(candles, index, period):
    """Reuse the project ATR; None when it is not seeded at ``index``."""
    try:
        frame = candles.iloc[: index + 1] if hasattr(candles, "iloc") else candles
        values = calculate_atr(frame, period=period)
        value = float(values.iloc[index])
    except Exception:
        return None
    if value != value or value <= 0:       # NaN or non-positive
        return None
    return value


def detect_l_shape(
    candles,
    *,
    as_of_index=None,
    parameters: LShapeParameters = DEFAULT_PARAMETERS,
):
    """Return the L-shaped formation ending at ``as_of_index``, or None.

    ``as_of_index`` defaults to the last supplied candle. Nothing after it is
    read, so calling this on a longer frame with the same ``as_of_index``
    produces the same answer as calling it on the truncated prefix.

    Search order is deterministic and structural, not a score: the longest
    qualifying shelf wins, so every consolidation bar belongs to the shelf, and
    the impulse is then anchored at the most recent origin of the move (the last
    bar printing the lowest low for LONG, the highest high for SHORT) inside the
    bounded lookback. A flat prelude is therefore never absorbed into the leg.
    """
    rows = _series(candles)
    if rows is None:
        return None

    last = len(rows) - 1 if as_of_index is None else int(as_of_index)
    if last < 0 or last >= len(rows):
        return None

    atr = _atr_at(candles, last, parameters.atr_period)
    if atr is None:
        return None

    highs = [row[0] for row in rows]
    lows = [row[1] for row in rows]
    closes = [row[2] for row in rows]

    for shelf_bars in range(parameters.shelf_max_bars, parameters.shelf_min_bars - 1, -1):
        shelf_start = last - shelf_bars + 1
        if shelf_start <= 0:
            continue

        shelf_high = max(highs[shelf_start:last + 1])
        shelf_low = min(lows[shelf_start:last + 1])
        shelf_height = shelf_high - shelf_low
        if shelf_height > parameters.shelf_max_height_atr_multiple * atr:
            continue

        impulse_end = shelf_start - 1
        window_start = max(0, impulse_end - parameters.impulse_max_bars + 1)

        for direction in (DIRECTION_LONG, DIRECTION_SHORT):
            origin = (
                _last_index_of_min(lows, window_start, impulse_end)
                if direction == DIRECTION_LONG
                else _last_index_of_max(highs, window_start, impulse_end)
            )
            impulse_bars = impulse_end - origin + 1
            if impulse_bars < parameters.impulse_min_bars:
                continue

            formation = _qualify(
                highs, lows, closes, atr, parameters, direction,
                origin, impulse_end, shelf_start, last,
                shelf_high, shelf_low, shelf_height,
            )
            if formation is not None:
                return formation
    return None


def _qualify(
    highs, lows, closes, atr, parameters, direction,
    impulse_start, impulse_end, shelf_start, shelf_end,
    shelf_high, shelf_low, shelf_height,
):
    impulse_high = max(highs[impulse_start:impulse_end + 1])
    impulse_low = min(lows[impulse_start:impulse_end + 1])
    impulse_range = impulse_high - impulse_low
    if impulse_range <= 0:
        return None
    if impulse_range < parameters.impulse_min_atr_multiple * atr:
        return None
    if shelf_height > parameters.shelf_max_height_impulse_fraction * impulse_range:
        return None

    net_move = closes[impulse_end] - closes[impulse_start]
    if direction == DIRECTION_LONG and net_move <= 0:
        return None
    if direction == DIRECTION_SHORT and net_move >= 0:
        return None

    directional_ratio = abs(net_move) / impulse_range
    if directional_ratio < parameters.impulse_min_directional_ratio:
        return None

    impulse_bars = impulse_end - impulse_start + 1
    bar_progress = abs(net_move) / impulse_bars
    if bar_progress < parameters.impulse_min_bar_progress_atr * atr:
        return None

    peak_window_start = impulse_start + int(
        impulse_bars * (1.0 - parameters.impulse_peak_last_fraction)
    )
    if direction == DIRECTION_LONG:
        extreme_index = _last_index_of_max(highs, impulse_start, impulse_end)
        retrace = impulse_high - shelf_low
        runaway = shelf_high - impulse_high
    else:
        extreme_index = _last_index_of_min(lows, impulse_start, impulse_end)
        retrace = shelf_high - impulse_low
        runaway = impulse_low - shelf_low

    if extreme_index < peak_window_start:
        return None
    if retrace > parameters.shelf_max_retrace_fraction * impulse_range:
        return None
    if runaway > parameters.shelf_max_height_atr_multiple * atr:
        return None

    return LShapeFormation(
        direction=direction,
        start_index=impulse_start,
        impulse_start_index=impulse_start,
        impulse_end_index=impulse_end,
        shelf_start_index=shelf_start,
        shelf_end_index=shelf_end,
        shelf_high=shelf_high,
        shelf_low=shelf_low,
        shelf_height=shelf_height,
        impulse_low=impulse_low,
        impulse_high=impulse_high,
        impulse_range=impulse_range,
        impulse_extreme_index=extreme_index,
        atr=atr,
        impulse_atr_multiple=impulse_range / atr,
        impulse_directional_ratio=directional_ratio,
        impulse_bar_progress_atr_multiple=bar_progress / atr,
        shelf_height_atr_multiple=shelf_height / atr,
        shelf_height_impulse_fraction=shelf_height / impulse_range,
        shelf_retrace_fraction=retrace / impulse_range,
        as_of_index=shelf_end,
    )


def _last_index_of_min(values, start, end):
    """Most recent bar printing the window minimum: the origin of a rise."""
    best_index = start
    best_value = values[start]
    for index in range(start, end + 1):
        if values[index] <= best_value:
            best_value = values[index]
            best_index = index
    return best_index


def _last_index_of_max(values, start, end):
    """Most recent bar printing the window maximum: the origin of a drop."""
    best_index = start
    best_value = values[start]
    for index in range(start, end + 1):
        if values[index] >= best_value:
            best_value = values[index]
            best_index = index
    return best_index
