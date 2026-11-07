"""Shared reversal-candle evidence: exact old MIRROR parity, no trade gating."""
from copy import deepcopy

import pytest
import mirror_scanner as mirror
from geometry.reversal_patterns import (
    directional_engulfing, closed_candle_numbers, is_nison_lower_wick,
    confirms_next_body_close, is_bullish_engulfing,
)


STEP = 300_000


def candle(index, o, h, lo, c, *, closed=True):
    return {
        "open_time_ms": index * STEP,
        "close_time_ms": (index + 1) * STEP,
        "open": o, "high": h, "low": lo, "close": c, "closed": closed,
    }


@pytest.mark.parametrize("direction,first,second,matched", [
    ("LONG", candle(0, 10, 11, 8.8, 9), candle(1, 8.9, 10.4, 8.5, 10.1), True),
    ("SHORT", candle(0, 9, 11, 8.8, 10), candle(1, 10.1, 10.4, 8.5, 8.9), True),
    ("LONG", candle(0, 10, 11, 8.8, 9), candle(1, 9.1, 10.4, 8.5, 10.1), False),
    ("SHORT", candle(0, 9, 11, 8.8, 10), candle(1, 9.9, 10.4, 8.5, 8.9), False),
])
def test_engulfing_parity(direction, first, second, matched):
    before = deepcopy((first, second))
    assert directional_engulfing(first, second, direction) is matched
    assert mirror._engulfing(first, second, direction) is matched
    assert (first, second) == before


def test_reject_incomplete_or_invalid_closed_candles():
    row = candle(0, 10, 11, 8.5, 10.1)
    assert closed_candle_numbers(row) is not None
    for changed in ({"closed": False}, {"high": 10}, {"open": float("nan")},
                    {"low": -1}, {"high": float("inf")}):
        assert closed_candle_numbers({**row, **changed}) is None
    assert mirror._candle_numbers(row) == closed_candle_numbers(row)


@pytest.mark.parametrize("direction,prior,formation,expected", [
    ("LONG", (candle(0, 10.9, 11, 10.4, 10.5),
              candle(1, 10.3, 10.4, 9.8, 9.9)),
     candle(2, 10, 10.11, 9.5, 10.1), True),
    ("SHORT", (candle(0, 9.9, 10.1, 9.8, 10),
               candle(1, 10.2, 10.5, 10.1, 10.4)),
     candle(2, 10.5, 10.61, 9.9, 10.6), True),
    ("LONG", (candle(0, 10.9, 11, 10.4, 10.5),
              candle(1, 10.3, 10.4, 9.8, 9.9)),
     candle(2, 10, 10.2, 9.5, 10), False),  # Doji: neutral, no entry.
])
def test_nison_parity(direction, prior, formation, expected):
    assert is_nison_lower_wick(formation, direction, prior, upper_to_body="0.50") is expected
    assert mirror._nison_hammer(formation, direction, prior) is expected
    delayed = {**formation, "open_time_ms": formation["open_time_ms"] + STEP}
    assert not is_nison_lower_wick(delayed, direction, prior, upper_to_body="0.50")
    assert not is_nison_lower_wick({**formation, "closed": False}, direction, prior, upper_to_body="0.50")


def test_body_confirmation_parity_and_no_lookahead():
    long = candle(0, 9, 10.2, 8.5, 10)
    first = candle(1, 10, 10.4, 9.8, 9.9)  # Wick past body, close does NOT confirm.
    confirmed = candle(1, 10, 10.5, 9.9, 10.3)
    assert not confirms_next_body_close([long], first, "LONG", STEP)
    assert confirms_next_body_close([long], confirmed, "LONG", STEP)
    assert mirror._next_close_confirms([long], confirmed, "LONG", STEP)
    assert not confirms_next_body_close([long], {**confirmed, "closed": False}, "LONG", STEP)
    assert not confirms_next_body_close([long], {**confirmed, "open_time_ms": 2*STEP}, "LONG", STEP)
    assert not confirms_next_body_close([long], confirmed, "LONG", STEP//5)

    short = candle(0, 10, 10.3, 9.8, 9.9)
    short_done = candle(1, 9.9, 10.05, 9.5, 9.7)
    assert confirms_next_body_close([short], short_done, "SHORT", STEP)
    assert mirror._next_close_confirms([short], short_done, "SHORT", STEP)
    assert not confirms_next_body_close([short], {**short_done, "close": 9.9}, "SHORT", STEP)


def test_legacy_wedge_bullish_engulfing_remains_unchanged():
    import pandas as pd
    frame = pd.DataFrame([
        {"open": 10, "high": 11, "low": 8, "close": 9},
        {"open": 8.9, "high": 10.4, "low": 8.5, "close": 10.1},
    ])
    assert is_bullish_engulfing(frame, 1)
    assert not is_bullish_engulfing(frame, 0)


@pytest.mark.parametrize("direction,first,second", [
    ("LONG", candle(0, 10, 11, 8.8, 9), candle(1, 8.9, 10.4, 8.5, 10.1)),
    ("SHORT", candle(0, 9, 11, 8.8, 10), candle(1, 10.1, 10.4, 8.5, 8.9)),
])
def test_closed_engulfing_observation_has_no_trade_confirmation(direction, first, second):
    from geometry.reversal_patterns import observe_closed_engulfing
    result = observe_closed_engulfing(first, second, direction)
    assert result == {
        "formation_type": "ENGULFING", "direction": direction,
        "formation_candle_ids": (0, STEP),
        "confirmation_close_time": None, "confirmed": False,
        "evidence": {"formation_close_time_ms": 2 * STEP},
    }


def test_closed_engulfing_rejects_unfinished_gaps_bad_ohlc_and_wrong_direction():
    from geometry.reversal_patterns import observe_closed_engulfing
    first = candle(0, 10, 11, 8.8, 9)
    second = candle(1, 8.9, 10.4, 8.5, 10.1)
    assert observe_closed_engulfing(first, second, "SHORT") is None
    assert observe_closed_engulfing(first, second, "UNKNOWN") is None
    for changed in (
        {"closed": False},
        {"high": 9},
        {"open": float("nan")},
        {"open_time_ms": 2 * STEP, "close_time_ms": 3 * STEP},
        {"close_time_ms": 3 * STEP},
        {"open_time_ms": "invalid"},
    ):
        assert observe_closed_engulfing(first, {**second, **changed}, "LONG") is None
    assert observe_closed_engulfing({**first, "closed": False}, second, "LONG") is None
    assert observe_closed_engulfing({**first, "open_time_ms": -STEP}, second, "LONG") is None
