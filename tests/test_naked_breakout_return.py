"""#415 offline naked-breakout reversal evidence; no exchange or Robot imports."""

from dataclasses import replace

import pytest

from geometry.naked_breakout_return import observe_naked_breakout_return


STEP = 300_000
SOURCE = {"source_id": "triangle:formation-7", "frozen_at_index": 0,
          "anchor_index": 0, "anchor_price": 100.0, "slope_per_bar": 0.0}


def bar(i, opening, high, low, close, *, closed=True):
    return {"open_time_ms": i * STEP, "close_time_ms": (i + 1) * STEP,
            "open": opening, "high": high, "low": low, "close": close,
            "closed": closed}


DOWN = [
    bar(0, 102, 103, 100, 101),
    bar(1, 101, 102, 98, 98.5),
    bar(2, 98.5, 99, 94, 95),
    bar(3, 95, 96, 91, 92),
    bar(4, 92, 98, 91.5, 97),
]


def run(bars, *, boundary=SOURCE, cutoff=4, minimum=0.05, count=3):
    return observe_naked_breakout_return(
        bars, boundary=boundary, breakout_index=1, as_of_index=cutoff,
        min_excursion_fraction=minimum, min_impulse_bars=count,
    )


def mirror(bars):
    return [{**c, "open": 200-c["open"], "high": 200-c["low"],
             "low": 200-c["high"], "close": 200-c["close"]} for c in bars]


@pytest.mark.parametrize("reflected", [False, True])
def test_body_breakout_continuation_and_first_reversal_both_directions(reflected):
    bars = mirror(DOWN) if reflected else DOWN
    result = run(bars)
    assert result is not None
    assert result.stage == "OFFLINE_OBSERVATION"
    assert result.breakout_side == ("UP" if reflected else "DOWN")
    assert result.observed_return_side == ("SHORT" if reflected else "LONG")
    assert result.breakout_index == 1
    assert result.impulse_extreme_index == 3
    assert result.reversal_close_index == 4
    assert result.reversal_close_time_ms == 5 * STEP
    assert result.excursion_fraction == pytest.approx(.09)
    assert result.source_identity[0] == SOURCE["source_id"]
    assert not result.strategy_confirmed
    assert not {"order", "entry", "stop", "take", "predicted_exit_time"} & vars(result).keys()


def test_moving_boundary_reference_is_frozen_and_source_bound():
    frozen = {**SOURCE, "slope_per_bar": .1}
    result = run(DOWN, boundary=frozen)
    assert result is not None
    assert result.boundary_at_breakout == pytest.approx(100.1)
    assert result.boundary_at_reversal_close == pytest.approx(100.4)
    assert result.source_identity == ("triangle:formation-7", 0, 0, 100.0, .1)
    assert run(DOWN, boundary={**frozen, "frozen_at_index": 1}) is None
    assert run(DOWN, boundary={**frozen, "source_id": ""}) is None
    assert run(DOWN, boundary={**frozen, "slope_per_bar": float("nan")}) is None


@pytest.mark.parametrize("changed", [
    # Wick crosses level but both open and close remain on its old side.
    (1, {"close": 100.2}),
    # A gap outside without a BODY crossing is not a naked body breakout.
    (1, {"open": 99.0}),
    # A body retests the level during the alleged impulse.
    (2, {"open": 98.5, "high": 101.5, "close": 100.5}),
    # Choppy impulse with a close no longer extending downside.
    (3, {"close": 96.0}),
    # No real-body bullish reversal confirmation.
    (4, {"close": 94.0}),
    # Wick-only upside without a bullish body reversal.
    (4, {"open": 92, "high": 98, "close": 92}),
    # No decision-time closed confirmation.
    (4, {"closed": False}),
    # Historical candle is invalid; not silently repaired.
    (2, {"low": 99.0}),
    # Missing candle / unequal bar duration.
    (2, {"open_time_ms": 3 * STEP, "close_time_ms": 4 * STEP}),
])
def test_fail_closed_on_wick_only_gap_chop_retest_unclosed_and_invalid(changed):
    index, update = changed
    bars = [dict(x) for x in DOWN]
    bars[index].update(update)
    assert run(bars) is None


def test_configured_excursion_required_not_invented_and_future_ignored():
    assert run(DOWN, minimum=.10) is None
    assert run(DOWN, count=4) is None
    assert run(DOWN, minimum=0) is None
    assert run(DOWN, minimum=float("nan")) is None
    assert run(DOWN, count=True) is None
    assert run(DOWN, cutoff=True) is None
    assert run(DOWN, cutoff=3) is None
    assert run(DOWN, cutoff=7) is None
    assert run(DOWN) == run(DOWN + [bar(5, 500, 500, 1, 1, closed=False)])
    altered = [*DOWN, bar(5, 500, 501, 1, 2, closed=False)]
    assert run(altered) == run(DOWN)


def test_last_reversal_must_be_the_decision_close_not_a_future_guess():
    # Even if future candle data is present, as_of=3 cannot use next bar 4.
    assert run(DOWN, cutoff=3, count=2) is None
    # Source projected from *old frozen* geometry only, never a better line
    # fitted after seeing the breakout.
    assert run(DOWN, boundary={**SOURCE, "frozen_at_index": 4}) is None
