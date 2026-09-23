"""Narrow coverage for geometry.l_shape (BACKLOG.md G6, owner B2USDT definition).

Pure offline detector only: no trading, Robot, Telegram, Scanner, network or
database. Synthetic candles keep every threshold explicit and ticker-neutral;
one real B2USDT 5m excerpt pins the owner's reference geometry.
"""

import dataclasses
import inspect

import pandas as pd

import geometry.l_shape as detector_module
from geometry.l_shape import (
    DEFAULT_PARAMETERS,
    DIRECTION_LONG,
    DIRECTION_SHORT,
    LShapeParameters,
    STOP_RATIO_FALLBACK,
    STOP_STRUCTURAL,
    detect_l_shape,
    find_latest_l_shape,
    l_shape_signal_plan,
)

STEP_MS = 300_000


def _frame(bars, start_ms=1_700_000_000_000):
    """bars: (high, low, close) with open == close, or (open, high, low, close)."""
    rows = []
    for index, bar in enumerate(bars):
        if len(bar) == 3:
            high, low, close = bar
            open_ = close
        else:
            open_, high, low, close = bar
        rows.append({
            "time": start_ms + index * STEP_MS,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        })
    return pd.DataFrame(rows)


def _flat(count, level, height=0.4):
    return [(level + height / 2, level - height / 2, level)] * count


def _rising(count, start, step, height=0.4):
    bars = []
    for index in range(count):
        close = start + step * (index + 1)
        bars.append((close + height / 2, close - step - height / 2, close))
    return bars


# Trough under the impulse HIGH (109.2). The second candle has the lowest low
# (106.5); its body top max(open, close) = 107.5 is the upper edge U.
_TROUGH = [
    (108.5, 108.8, 107.0, 107.5),
    (107.5, 107.8, 106.5, 107.0),
    (107.0, 107.9, 106.8, 107.6),
    (107.6, 108.4, 107.4, 108.2),
    (108.2, 108.6, 107.9, 108.4),
]
_BREAKOUT = (108.4, 110.5, 108.3, 110.2)


def _long_bars():
    """14 flat seed bars, a 6-bar rise to H from a reversal low (99.8, below
    the seed lows), a 5-bar trough, the breakout."""
    return _flat(14, 100.4) + _rising(6, 100.0, 1.5) + _TROUGH + [_BREAKOUT]


def _mirror(bars, axis=200.0):
    mirrored = []
    for bar in bars:
        if len(bar) == 3:
            high, low, close = bar
            mirrored.append((axis - low, axis - high, axis - close))
        else:
            open_, high, low, close = bar
            mirrored.append((axis - open_, axis - low, axis - high, axis - close))
    return mirrored


def _long_shape():
    return _frame(_long_bars())


def _short_shape():
    return _frame(_mirror(_long_bars()))


# Real Bybit B2USDT 5m closed candles, 09:55-12:25 MSK 2026-09-23:
# (open time ms, open, high, low, close). The owner's reference L-shape.
_B2USDT_5M = [
    (1790146500000, 0.5228, 0.5228, 0.5207, 0.521),
    (1790146800000, 0.521, 0.5216, 0.5201, 0.5206),
    (1790147100000, 0.5206, 0.522, 0.5198, 0.5198),
    (1790147400000, 0.5198, 0.5198, 0.4623, 0.4886),
    (1790147700000, 0.4886, 0.4932, 0.4843, 0.4912),
    (1790148000000, 0.4912, 0.4931, 0.4836, 0.49),
    (1790148300000, 0.49, 0.4953, 0.4836, 0.4844),
    (1790148600000, 0.4844, 0.49, 0.4816, 0.4824),
    (1790148900000, 0.4824, 0.4904, 0.478, 0.4882),
    (1790149200000, 0.4882, 0.4885, 0.4101, 0.4174),
    (1790149500000, 0.4174, 0.4284, 0.3659, 0.3882),
    (1790149800000, 0.3882, 0.4003, 0.3716, 0.3771),
    (1790150100000, 0.3771, 0.4042, 0.376, 0.378),
    (1790150400000, 0.378, 0.3951, 0.3582, 0.3639),
    (1790150700000, 0.3639, 0.3841, 0.3506, 0.3632),
    (1790151000000, 0.3632, 0.3662, 0.3456, 0.3582),
    (1790151300000, 0.3582, 0.3646, 0.353, 0.3593),
    (1790151600000, 0.3593, 0.4937, 0.3588, 0.4929),
    (1790151900000, 0.4929, 0.5054, 0.431, 0.4882),
    (1790152200000, 0.4882, 0.5168, 0.444, 0.4538),
    (1790152500000, 0.4538, 0.481, 0.4388, 0.4752),
    (1790152800000, 0.4752, 0.4772, 0.4546, 0.4723),
    (1790153100000, 0.4723, 0.4815, 0.4645, 0.478),
    (1790153400000, 0.478, 0.4838, 0.4713, 0.4795),
    (1790153700000, 0.4795, 0.4875, 0.4775, 0.4829),
    (1790154000000, 0.4829, 0.4868, 0.4784, 0.4815),
    (1790154300000, 0.4815, 0.4842, 0.4662, 0.483),
    (1790154600000, 0.483, 0.4857, 0.4784, 0.4815),
    (1790154900000, 0.4815, 0.4848, 0.478, 0.4809),
    (1790155200000, 0.4809, 0.4847, 0.4778, 0.4778),
    (1790155500000, 0.4778, 0.5203, 0.4733, 0.5048),
]


def _b2usdt():
    return pd.DataFrame(
        _B2USDT_5M, columns=["time", "open", "high", "low", "close"]
    )


def test_long_high_trough_breakout_is_detected_with_owner_target():
    formation = detect_l_shape(_long_shape())

    assert formation is not None
    assert formation.direction == DIRECTION_LONG
    assert formation.start_index == formation.impulse_start_index == 14
    assert formation.extreme_index == 19
    assert (formation.trough_start_index, formation.trough_end_index) == (20, 24)
    assert formation.trough_index == 21
    assert formation.breakout_index == formation.as_of_index == 25
    assert formation.breakout_level == 109.2
    assert formation.trough_edge == 107.5
    assert abs(formation.depth - 1.7) < 1e-9
    assert abs(formation.target_level - 110.9) < 1e-9
    assert abs(formation.potential_percent - 100 * (110.9 / 109.2 - 1)) < 1e-9


def test_short_is_the_exact_mirror_around_a_local_low():
    formation = detect_l_shape(_short_shape())

    assert formation is not None
    assert formation.direction == DIRECTION_SHORT
    assert formation.extreme_index == 19
    assert formation.trough_index == 21
    assert formation.breakout_index == 25
    assert abs(formation.breakout_level - 90.8) < 1e-9
    assert abs(formation.trough_edge - 92.5) < 1e-9
    assert abs(formation.target_level - 89.1) < 1e-9
    assert formation.potential_percent < 0


def test_b2usdt_5m_owner_reference_geometry():
    """HIGH 11:30 (0.5168), trough 11:35-12:20, breakout 12:25; U is the body
    top of the lowest-low trough candle (11:35), T = H + (H - U)."""
    candles = _b2usdt()
    formation = find_latest_l_shape(candles)

    assert formation is not None
    assert formation.direction == DIRECTION_LONG
    time = candles["time"]
    assert int(time[formation.start_index]) == 1790151000000        # 11:10
    assert int(time[formation.extreme_index]) == 1790152200000      # 11:30
    assert int(time[formation.trough_index]) == 1790152500000       # 11:35
    assert int(time[formation.breakout_index]) == 1790155500000     # 12:25
    assert formation.breakout_level == 0.5168
    assert formation.trough_edge == 0.4752
    assert abs(formation.target_level - 0.5584) < 1e-9
    assert round(formation.potential_percent, 2) == 8.05


# Real Bybit METISUSDT 5m closed candles, 10:50-13:45 MSK 2026-09-23 (the
# last closed candle of the scan that delivered the METISUSDT Ikigai Box).
_METISUSDT_5M = [
    (1790149800000, 3.583, 3.589, 3.578, 3.578),
    (1790150100000, 3.578, 3.581, 3.577, 3.581),
    (1790150400000, 3.581, 3.597, 3.578, 3.585),
    (1790150700000, 3.585, 3.587, 3.562, 3.587),
    (1790151000000, 3.587, 3.594, 3.584, 3.591),
    (1790151300000, 3.591, 3.624, 3.591, 3.619),
    (1790151600000, 3.619, 3.623, 3.605, 3.607),
    (1790151900000, 3.607, 3.612, 3.605, 3.607),
    (1790152200000, 3.607, 3.621, 3.601, 3.621),
    (1790152500000, 3.621, 3.625, 3.621, 3.625),
    (1790152800000, 3.625, 3.625, 3.616, 3.616),
    (1790153100000, 3.616, 3.616, 3.579, 3.579),
    (1790153400000, 3.579, 3.579, 3.558, 3.563),
    (1790153700000, 3.563, 3.579, 3.561, 3.575),
    (1790154000000, 3.575, 3.588, 3.575, 3.588),
    (1790154300000, 3.588, 3.591, 3.576, 3.591),
    (1790154600000, 3.591, 3.598, 3.59, 3.59),
    (1790154900000, 3.59, 3.599, 3.59, 3.591),
    (1790155200000, 3.591, 3.602, 3.591, 3.602),
    (1790155500000, 3.602, 3.613, 3.602, 3.603),
    (1790155800000, 3.603, 3.607, 3.603, 3.607),
    (1790156100000, 3.607, 3.607, 3.607, 3.607),
    (1790156400000, 3.607, 3.611, 3.593, 3.611),
    (1790156700000, 3.611, 3.611, 3.599, 3.607),
    (1790157000000, 3.607, 3.612, 3.603, 3.609),
    (1790157300000, 3.609, 3.616, 3.609, 3.613),
    (1790157600000, 3.613, 3.643, 3.607, 3.643),
    (1790157900000, 3.643, 3.647, 3.634, 3.638),
    (1790158200000, 3.638, 3.638, 3.617, 3.617),
    (1790158500000, 3.617, 3.63, 3.617, 3.63),
    (1790158800000, 3.63, 3.63, 3.608, 3.613),
    (1790159100000, 3.613, 3.625, 3.611, 3.625),
    (1790159400000, 3.625, 3.629, 3.621, 3.621),
    (1790159700000, 3.621, 3.638, 3.621, 3.638),
    (1790160000000, 3.638, 3.652, 3.638, 3.641),
    (1790160300000, 3.641, 3.646, 3.633, 3.641),
]


def _metisusdt():
    return pd.DataFrame(
        _METISUSDT_5M, columns=["time", "open", "high", "low", "close"]
    )


def test_metisusdt_5m_impulse_starts_at_the_nearest_reversal_low():
    """12:40 reversal LOW -> 13:05 HIGH -> trough 13:10-13:35 -> 13:40 breakout.
    The 11:50 window minimum is not the origin of this impulse."""
    candles = _metisusdt()
    formation = find_latest_l_shape(candles)

    assert formation is not None
    assert formation.direction == DIRECTION_LONG
    time = candles["time"]
    assert int(time[formation.start_index]) == 1790156400000        # 12:40
    assert int(time[formation.extreme_index]) == 1790157900000      # 13:05
    assert int(time[formation.trough_index]) == 1790158800000       # 13:20
    assert int(time[formation.breakout_index]) == 1790160000000     # 13:40
    assert formation.breakout_level == 3.647
    assert formation.trough_edge == 3.63
    assert abs(formation.target_level - 3.664) < 1e-9
    assert formation.impulse_atr_multiple >= DEFAULT_PARAMETERS.impulse_min_atr_multiple
    assert (formation.impulse_bar_progress_atr_multiple
            >= DEFAULT_PARAMETERS.impulse_min_bar_progress_atr)


def test_metisusdt_5m_earlier_structure_still_qualifies_independently():
    """11:50 reversal LOW -> 12:25 HIGH -> trough 12:30-12:50 -> 12:55."""
    candles = _metisusdt()
    breakout = int(candles.index[candles["time"] == 1790157300000][0])
    formation = detect_l_shape(candles, as_of_index=breakout)

    assert formation is not None
    time = candles["time"]
    assert int(time[formation.start_index]) == 1790153400000        # 11:50
    assert int(time[formation.extreme_index]) == 1790155500000      # 12:25
    assert formation.breakout_level == 3.613
    assert formation.trough_edge == 3.611


def test_no_reversal_low_means_no_impulse_origin():
    """A rise out of a flat, equal-low base has no strictly lower pivot."""
    bars = _flat(14, 100.0) + [(101.7, 99.8, 101.5)] + _long_bars()[15:]

    assert detect_l_shape(_frame(bars)) is None


def test_plain_range_without_an_impulse_is_not_an_l_shape():
    assert find_latest_l_shape(_frame(_flat(40, 100.0))) is None


def test_trough_erasing_the_impulse_is_a_reversal_not_an_l_shape():
    bars = _long_bars()
    bars[21] = (107.5, 107.8, 99.0, 107.0)      # undercuts the impulse origin

    formation = detect_l_shape(_frame(bars))

    assert formation is None or formation.direction != DIRECTION_LONG


def test_trough_trading_above_the_high_voids_that_high():
    bars = _long_bars()
    bars[22] = (107.0, 109.5, 106.8, 107.6)     # a trough wick above H

    formation = detect_l_shape(_frame(bars))

    assert formation is None or formation.extreme_index != 19


def test_detection_never_reads_future_candles():
    base = _long_shape()
    at_breakout = detect_l_shape(base)
    extended = pd.concat(
        [base, _frame(_rising(8, float(base["close"].iloc[-1]), 2.0),
                      start_ms=int(base["time"].iloc[-1]) + STEP_MS)],
        ignore_index=True,
    )

    assert at_breakout is not None
    assert detect_l_shape(extended, as_of_index=len(base) - 1) == at_breakout


def test_latest_breakout_a_few_candles_before_the_scan_is_found():
    base = _long_shape()
    after = _frame([(110.6, 109.9, 110.3)] * 3,
                   start_ms=int(base["time"].iloc[-1]) + STEP_MS)
    candles = pd.concat([base, after], ignore_index=True)

    assert detect_l_shape(candles) is None
    assert find_latest_l_shape(candles) == detect_l_shape(base)


def test_thresholds_are_named_parameters_not_hidden_constants():
    strict = LShapeParameters(impulse_min_atr_multiple=25.0)

    assert DEFAULT_PARAMETERS.impulse_min_atr_multiple < 25.0
    assert detect_l_shape(_long_shape()) is not None
    assert detect_l_shape(_long_shape(), parameters=strict) is None


def test_no_shelf_condition_or_terminology_remains():
    assert "shelf" not in inspect.getsource(detector_module).lower()


# --- Scanner signal eligibility (owner decision 2026-09-23) -----------------


def test_b2usdt_is_eligible_with_the_half_target_fallback_stop():
    formation = find_latest_l_shape(_b2usdt())
    plan = l_shape_signal_plan(formation)

    assert plan.eligible and plan.rejection is None
    assert plan.reference == formation.breakout_level == 0.5168
    assert plan.target == formation.target_level
    # Structural STOP at the trough low 0.4388 is 0.078 away, more than half
    # the 0.0416 target distance, so the ratio-based STOP applies.
    assert plan.structural_stop == 0.4388
    assert plan.stop_kind == STOP_RATIO_FALLBACK
    assert abs(plan.stop - (0.5168 - 0.0416 / 2)) < 1e-9
    assert plan.reward_risk == 2.0
    assert round(formation.potential_percent, 2) == 8.05


def test_metisusdt_structures_stay_valid_but_are_not_signals():
    candles = _metisusdt()
    breakout_1255 = int(candles.index[candles["time"] == 1790157300000][0])
    for formation in (
        find_latest_l_shape(candles),                                  # +0.47%
        detect_l_shape(candles, as_of_index=breakout_1255),            # +0.06%
    ):
        plan = l_shape_signal_plan(formation)
        assert formation is not None
        assert formation.potential_percent < 0.8
        assert not plan.eligible
        assert plan.rejection == "potential_below_minimum"


def test_structural_stop_is_preferred_when_within_half_the_target():
    formation = dataclasses.replace(detect_l_shape(_long_shape()), trough_extreme=108.8)
    plan = l_shape_signal_plan(formation)

    assert plan.stop_kind == STOP_STRUCTURAL
    assert plan.stop == 108.8
    assert plan.reward_risk >= 2.0 and plan.eligible


def test_short_stop_is_on_the_adverse_side_of_the_breakout():
    formation = detect_l_shape(_short_shape())
    plan = l_shape_signal_plan(formation)

    assert plan.eligible
    assert plan.stop > plan.reference > plan.target
    assert plan.reward_risk == 2.0


def test_signal_plan_never_changes_the_formation():
    formation = detect_l_shape(_long_shape())
    before = dataclasses.asdict(formation)

    l_shape_signal_plan(dataclasses.replace(formation, potential_percent=0.1))
    l_shape_signal_plan(formation)

    assert dataclasses.asdict(formation) == before
