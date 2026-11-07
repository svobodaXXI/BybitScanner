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


def test_closed_engulfing_keeps_decimal_boundary_precision():
    from geometry.reversal_patterns import observe_closed_engulfing
    prior = candle(0, "10", "11", "8", "9")
    # Float conversion rounds this open down to 9 and would falsely
    # claim it engulfs the previous bearish real body.
    near_miss = candle(1, "9.0000000000000000000000000001",
                       "11.5", "8.5", "10.5")
    assert observe_closed_engulfing(prior, near_miss, "LONG") is None
    valid = {**near_miss, "open": "9"}
    result = observe_closed_engulfing(prior, valid, "LONG")
    assert result is not None
    assert result["confirmed"] is False

    # A genuine large-magnitude engulfing must not be lost because float
    # converts finite Decimal OHLC to inf.
    large = candle(0, "1e400", "1.1e400", "8e399", "9e399")
    after = candle(1, "8.9e399", "1.2e400", "8.7e399", "1.05e400")
    assert observe_closed_engulfing(large, after, "LONG") is not None


@pytest.mark.parametrize("invalid", [None, [], "not-a-candle", 42, False])
def test_closed_engulfing_rejects_non_mapping_rows_without_exception(invalid):
    from geometry.reversal_patterns import observe_closed_engulfing
    first = candle(0, 10, 11, 8.8, 9)
    second = candle(1, 8.9, 10.4, 8.5, 10.1)
    assert observe_closed_engulfing(invalid, second, "LONG") is None
    assert observe_closed_engulfing(first, invalid, "LONG") is None


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
    # Float truncation, booleans and numeric strings must never be accepted
    # as authoritative candle IDs, even when int(value) would appear adjacent.
    for invalid in (0.5, True, "0", 0.0):
        assert observe_closed_engulfing(
            {**first, "open_time_ms": invalid}, second, "LONG",
        ) is None
    for invalid in (STEP + 0.5, str(STEP), float(STEP)):
        assert observe_closed_engulfing(
            first, {**second, "open_time_ms": invalid}, "LONG",
        ) is None


# Classical Nison-style patterns: tests are closed-only, observation-only.
# Qualitative body-size/trend criteria are explicit engineering heuristics.
_DOWN = [
    candle(0, 13, 13.5, 12.5, 13),
    candle(1, 12, 12.5, 11.5, 12),
    candle(2, 11, 11.5, 10.5, 11),
]
_UP = [
    candle(0, 10, 10.5, 9.5, 10),
    candle(1, 11, 11.5, 10.5, 11),
    candle(2, 12, 12.5, 11.5, 12),
]


@pytest.mark.parametrize("prior,formation,pattern,direction", [
    (_DOWN, [candle(3, 10.5, 10.72, 9.4, 10.7)], "HAMMER", "LONG"),
    (_UP, [candle(3, 13.5, 13.72, 12.4, 13.7)], "HANGING_MAN", "SHORT"),
    (_DOWN, [candle(3, 10.1, 11.2, 10.08, 10.3)], "INVERTED_HAMMER", "LONG"),
    (_UP, [candle(3, 13.1, 14.2, 13.08, 13.3)], "SHOOTING_STAR", "SHORT"),
    (_DOWN, [candle(3, 11, 11.2, 9.6, 10),
             candle(4, 9.8, 11.3, 9.7, 11.1)], "ENGULFING", "LONG"),
    (_UP, [candle(3, 12, 13.3, 11.8, 13),
           candle(4, 13.1, 13.2, 11.7, 11.9)], "ENGULFING", "SHORT"),
    (_DOWN, [candle(3, 11, 11.2, 9.7, 9.8),
             candle(4, 10, 10.7, 9.7, 10.2)], "HARAMI", "LONG"),
    (_DOWN, [candle(3, 11, 11.2, 9.7, 9.8),
             candle(4, 10, 10.5, 9.7, 10.01)], "HARAMI_CROSS", "LONG"),
    (_UP, [candle(3, 12, 13.4, 11.8, 13.2),
           candle(4, 12.8, 13.3, 12.3, 12.6)], "HARAMI", "SHORT"),
    (_UP, [candle(3, 12, 13.4, 11.8, 13.2),
           candle(4, 12.8, 13.2, 12.4, 12.8)], "HARAMI_CROSS", "SHORT"),
    (_DOWN, [candle(3, 11, 11.2, 9.7, 9.8),
             candle(4, 9.5, 10.8, 9.4, 10.6)], "PIERCING", "LONG"),
    (_UP, [candle(3, 12, 13.4, 11.8, 13.2),
           candle(4, 13.5, 13.7, 12.3, 12.4)], "DARK_CLOUD_COVER", "SHORT"),
    (_DOWN, [candle(3, 11, 11.2, 9.7, 9.8),
             candle(4, 9.3, 9.4, 9.0, 9.25),
             candle(5, 9.4, 10.9, 9.3, 10.7)], "MORNING_STAR", "LONG"),
    (_UP, [candle(3, 12, 13.4, 11.8, 13.2),
           candle(4, 13.6, 13.9, 13.5, 13.7),
           candle(5, 13.5, 13.6, 12.1, 12.3)], "EVENING_STAR", "SHORT"),
    (_DOWN, [candle(3, 11, 11.2, 9.7, 9.8),
             candle(4, 9.25, 9.4, 9.0, 9.25),
             candle(5, 9.4, 10.9, 9.3, 10.7)], "MORNING_DOJI_STAR", "LONG"),
    (_UP, [candle(3, 12, 13.4, 11.8, 13.2),
           candle(4, 13.6, 13.9, 13.5, 13.6),
           candle(5, 13.5, 13.6, 12.1, 12.3)], "EVENING_DOJI_STAR", "SHORT"),
    (_DOWN, [candle(3, 10.5, 11.12, 10.44, 11.05),
             candle(4, 10.91, 11.64, 10.88, 11.58),
             candle(5, 11.45, 12.22, 11.4, 12.15)], "THREE_WHITE_SOLDIERS", "LONG"),
    (_UP, [candle(3, 12.5, 12.56, 11.87, 11.95),
           candle(4, 12.1, 12.15, 11.4, 11.46),
           candle(5, 11.6, 11.63, 10.9, 10.96)], "THREE_BLACK_CROWS", "SHORT"),
    (_DOWN, [candle(3, 10, 10.5, 9.5, 10.01)], "DOJI", "NEUTRAL"),
])
def test_nison_classic_formation(prior, formation, pattern, direction):
    from geometry.reversal_patterns import observe_nison_reversals
    original = deepcopy(prior + formation)
    result = observe_nison_reversals(prior + formation)
    matched = [item for item in result
               if item["formation_type"] == pattern and item["direction"] == direction]
    assert len(matched) == 1
    entry = matched[0]
    assert entry["formation_candle_ids"] == tuple(x["open_time_ms"] for x in formation)
    assert entry["evidence"]["formation_close_time_ms"] == formation[-1]["close_time_ms"]
    assert entry["evidence"]["prior_trend"] == ("DOWN" if direction == "LONG"
                                                  else "UP" if direction == "SHORT" else "DOWN")
    assert entry["confirmed"] is False
    assert entry["confirmation_close_time"] is None
    assert prior + formation == original  # No mutation of source data.


def test_nison_rejects_unfinished_gapped_corrupt_and_unproved_trend():
    from geometry.reversal_patterns import observe_nison_reversals as observe
    hammer = candle(3, 10.5, 10.61, 9, 10.6)
    assert observe(_DOWN + [hammer])
    for defect in (
        {"closed": False},
        {"high": 10.0},
        {"open": float("nan")},
        {"open_time_ms": 4 * STEP, "close_time_ms": 5 * STEP},
        {"close_time_ms": 5 * STEP},
        {"open_time_ms": "3"},
    ):
        assert observe(_DOWN + [{**hammer, **defect}]) == ()
    assert observe([{**_DOWN[0], "closed": False}, *_DOWN[1:], hammer]) == ()
    assert observe([_DOWN[0], _DOWN[1], {**_DOWN[2], "close": 12.5, "high": 13.0}, hammer]) == ()
    assert observe(_DOWN + [hammer], trend_lookback=2) == ()
    assert observe(_DOWN + [hammer], trend_lookback=True) == ()
    assert observe(_DOWN + [hammer], trend_lookback=9) == ()


def test_nison_preserves_classical_gaps_and_never_uses_unclosed_future():
    from geometry.reversal_patterns import observe_nison_reversals as observe
    first = candle(3, 11, 11.2, 9.7, 9.8)
    star = candle(4, 9.3, 9.4, 9.0, 9.25)
    third = candle(5, 9.4, 10.9, 9.3, 10.7)
    valid = _DOWN + [first, star, third]
    assert any(x["formation_type"] == "MORNING_STAR" for x in observe(valid))
    # A gapless crypto-like construction must NOT be mislabelled a classic star.
    no_gap = _DOWN + [first, {**star, "open": 9.85, "close": 9.83, "high": 9.95}, third]
    assert not any("MORNING" in x["formation_type"] for x in observe(no_gap))
    # The in-progress third candle is not available as decision-time evidence.
    assert not any("MORNING" in x["formation_type"]
                   for x in observe(_DOWN + [first, star, {**third, "closed": False}]))
    # No trigger from an unclosed extra candle, even after a valid formation.
    future = {**candle(6, 10.5, 10.6, 10.0, 10.1), "closed": False}
    assert observe(valid + [future]) == ()


@pytest.mark.parametrize("prior,candidate", [
    (_DOWN, candle(3, 10.5, 10.51, 9.0, 10.505)),
    (_UP, candle(3, 13.5, 13.51, 12.0, 13.505)),
    (_DOWN, candle(3, 10.1, 11.7, 10.095, 10.105)),
    (_UP, candle(3, 13.1, 14.7, 13.095, 13.105)),
])
def test_nison_long_wick_doji_is_never_also_directional_hammer(prior, candidate):
    from geometry.reversal_patterns import observe_nison_reversals
    signals = observe_nison_reversals(prior + [candidate])
    single_candle = [item for item in signals
                     if item["formation_candle_ids"] == (3 * STEP,)]
    assert [item["formation_type"] for item in single_candle] == ["DOJI"]
    assert all(item["direction"] == "NEUTRAL" and not item["confirmed"]
               for item in single_candle)


def test_nison_doji_is_neutral_and_mirror_existing_contracts_remain_unchanged():
    from geometry.reversal_patterns import observe_nison_reversals as observe
    doji = candle(3, 10, 10.5, 9.5, 10.01)
    result = observe(_DOWN + [doji])
    assert {x["direction"] for x in result} == {"NEUTRAL"}
    assert all(x["confirmed"] is False for x in result)
    # New recognizer must not change existing MIRROR evidence or Wedge exception.
    first = candle(0, 10, 11, 8.8, 9)
    second = candle(1, 8.9, 10.4, 8.5, 10.1)
    assert mirror._engulfing(first, second, "LONG")
    assert directional_engulfing(first, second, "LONG")


def test_nison_soldiers_crows_reject_outside_opens_weak_closes_and_fake_wicks():
    from geometry.reversal_patterns import observe_nison_reversals as observe

    soldiers = [
        candle(3, 10.5, 11.12, 10.44, 11.05),
        candle(4, 10.91, 11.64, 10.88, 11.58),
        candle(5, 11.45, 12.22, 11.4, 12.15),
    ]
    crows = [
        candle(3, 12.5, 12.56, 11.87, 11.95),
        candle(4, 12.1, 12.15, 11.4, 11.46),
        candle(5, 11.6, 11.63, 10.9, 10.96),
    ]

    def has_pattern(rows, name):
        return any(item["formation_type"] == name for item in observe(rows))

    assert has_pattern(_DOWN + soldiers, "THREE_WHITE_SOLDIERS")
    assert has_pattern(_UP + crows, "THREE_BLACK_CROWS")

    for modified in (
        # Open above the previous real body, even though all bodies are long.
        [soldiers[0], {**soldiers[1], "open": 11.10}, soldiers[2]],
        # A long upper shadow means the second close is not near its high.
        [soldiers[0], {**soldiers[1], "high": 12.50}, soldiers[2]],
        # Third close fails to advance while still showing a large white body.
        [soldiers[0], soldiers[1], {**soldiers[2],
                                   "open": 11.05, "high": 11.57,
                                   "low": 11.0, "close": 11.50}],
        [soldiers[0], soldiers[1], {**soldiers[2], "closed": False}],
    ):
        assert not has_pattern(_DOWN + modified, "THREE_WHITE_SOLDIERS")
    for modified in (
        [crows[0], {**crows[1], "open": 11.93}, crows[2]],
        [crows[0], crows[1], {**crows[2], "low": 9.50}],
        [crows[0], crows[1], {**crows[2],
                              "open": 12.0, "high": 12.04,
                              "low": 11.50, "close": 11.55}],
        [crows[0], crows[1], {**crows[2], "closed": False}],
    ):
        assert not has_pattern(_UP + modified, "THREE_BLACK_CROWS")

    # A bullish rise during an established uptrend is not silently reported as
    # a trend-reversal pattern; confirmation and position decisions remain out.
    assert not has_pattern(_UP + soldiers, "THREE_WHITE_SOLDIERS")
    assert not has_pattern(_DOWN + crows, "THREE_BLACK_CROWS")
