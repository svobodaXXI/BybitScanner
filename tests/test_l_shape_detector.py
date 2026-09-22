"""Narrow coverage for geometry.l_shape (BACKLOG.md G6, first version).

Pure offline detector only: no trading, Robot, Telegram, Scanner, network or
database. Synthetic candles keep every threshold explicit and ticker-neutral.
"""

from decimal import Decimal

import pandas as pd

from geometry.l_shape import (
    DEFAULT_PARAMETERS,
    DIRECTION_LONG,
    DIRECTION_SHORT,
    LShapeParameters,
    detect_l_shape,
)

STEP_MS = 300_000


def _frame(bars):
    """bars: list of (high, low, close); open is irrelevant to the detector."""
    return pd.DataFrame([
        {
            "time": 1_700_000_000_000 + index * STEP_MS,
            "open": close,
            "high": high,
            "low": low,
            "close": close,
        }
        for index, (high, low, close) in enumerate(bars)
    ])


def _flat(count, level, height=0.4):
    return [(level + height / 2, level - height / 2, level)] * count


def _rising(count, start, step, height=0.4):
    bars = []
    for index in range(count):
        close = start + step * (index + 1)
        bars.append((close + height / 2, close - step - height / 2, close))
    return bars


def _falling(count, start, step, height=0.4):
    bars = []
    for index in range(count):
        close = start - step * (index + 1)
        bars.append((close + step + height / 2, close - height / 2, close))
    return bars


def _long_shape():
    """14 flat seed bars, a 6-bar rise, then a 5-bar shelf under the high."""
    seed = _flat(14, 100.0)
    impulse = _rising(6, 100.0, 1.5)
    top = impulse[-1][0]
    shelf = _flat(5, top - 0.5, height=0.5)
    return _frame(seed + impulse + shelf)


def _short_shape():
    seed = _flat(14, 100.0)
    impulse = _falling(6, 100.0, 1.5)
    bottom = impulse[-1][1]
    shelf = _flat(5, bottom + 0.5, height=0.5)
    return _frame(seed + impulse + shelf)


def test_long_impulse_with_shelf_near_the_high_is_detected():
    formation = detect_l_shape(_long_shape())

    assert formation is not None
    assert formation.direction == DIRECTION_LONG
    # the figure starts at the impulse, never at the first shelf bar
    assert formation.start_index == formation.impulse_start_index == 14
    assert formation.impulse_end_index == 19
    assert formation.shelf_start_index == 20
    assert formation.shelf_end_index == 24
    assert formation.shelf_low < formation.shelf_high
    assert formation.shelf_high <= formation.impulse_high + formation.atr
    assert formation.impulse_atr_multiple >= DEFAULT_PARAMETERS.impulse_min_atr_multiple
    assert formation.shelf_retrace_fraction <= DEFAULT_PARAMETERS.shelf_max_retrace_fraction


def test_short_impulse_with_shelf_near_the_low_is_detected():
    formation = detect_l_shape(_short_shape())

    assert formation is not None
    assert formation.direction == DIRECTION_SHORT
    assert formation.start_index == formation.impulse_start_index == 14
    assert formation.impulse_end_index == 19
    assert formation.shelf_start_index == 20
    assert formation.shelf_end_index == 24
    assert formation.impulse_low <= formation.shelf_low
    assert formation.shelf_retrace_fraction <= DEFAULT_PARAMETERS.shelf_max_retrace_fraction


def test_plain_range_without_an_impulse_is_not_an_l_shape():
    """A quiet box is not a formation just because it is narrow."""
    formation = detect_l_shape(_frame(_flat(40, 100.0)))

    assert formation is None


def test_deep_retracement_from_the_extreme_is_not_a_long_l_shape():
    """The same rising impulse, but the shelf sits far below its high.

    The bullish figure must not be reported. A detector that later reads this
    same drop as its own SHORT leg is a different, explicitly directional claim,
    so only the LONG interpretation is asserted here.
    """
    seed = _flat(14, 100.0)
    impulse = _rising(6, 100.0, 1.5)
    top = impulse[-1][0]
    deep = _flat(5, top - 0.65 * (top - 100.0), height=0.5)

    formation = detect_l_shape(_frame(seed + impulse + deep))

    assert formation is None or formation.direction != DIRECTION_LONG


def test_detection_never_reads_future_candles():
    base = _long_shape()
    at_shape_end = detect_l_shape(base)

    # Same frame, later bars appended: the earlier as_of verdict is unchanged.
    extended = pd.concat(
        [base, _frame(_rising(8, float(base["close"].iloc[-1]), 2.0))],
        ignore_index=True,
    )
    replayed = detect_l_shape(extended, as_of_index=len(base) - 1)
    prefix_only = detect_l_shape(base.iloc[: len(base)].copy())

    assert at_shape_end is not None
    assert replayed == at_shape_end
    assert prefix_only == at_shape_end


def test_thresholds_are_named_parameters_not_hidden_constants():
    """Raising the impulse requirement rejects the very same candles."""
    strict = LShapeParameters(impulse_min_atr_multiple=25.0)

    assert detect_l_shape(_long_shape()) is not None
    assert detect_l_shape(_long_shape(), parameters=strict) is None
