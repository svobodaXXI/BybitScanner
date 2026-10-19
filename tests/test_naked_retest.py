import pytest

from geometry.naked_retest import (
    BREAKOUT_DOWN,
    BREAKOUT_UP,
    CAMPAIGN_LONG,
    CAMPAIGN_SHORT,
    EVENT_BEFORE_AS_OF,
    EVENT_IGNORED_STALE,
    EVENT_LEVEL_INVALIDATED,
    EVENT_NAKED_BREAKOUT,
    EVENT_NO_TRANSITION,
    EVENT_RETEST_PROVEN,
    EVENT_RETEST_UNPROVEN,
    EVENT_TERMINAL,
    PHASE_CAMPAIGN_ACTIVE,
    PHASE_LEVEL_INVALIDATED,
    PHASE_RETEST_PROVEN,
    PHASE_RETEST_UNPROVEN,
    PHASE_WAITING_BREAKOUT,
    Boundary,
    NakedRetestError,
    atr_tolerance,
    initialize_state,
    mark_level_invalidated,
    naked_breakout_direction,
    process_closed_candle,
    replay_closed_candles,
    retest_contact,
)


MINUTE = 60_000
PIVOT = 100.0


def bar(i, o, h, l, c):
    return {"open_time_ms": i * MINUTE, "close_time_ms": (i + 1) * MINUTE,
            "open": o, "high": h, "low": l, "close": c, "closed": True}


def mirror_bar(candle):
    """Reflect prices around PIVOT: an UP scenario becomes its DOWN twin."""
    return candle | {"open": 2 * PIVOT - candle["open"], "close": 2 * PIVOT - candle["close"],
                     "high": 2 * PIVOT - candle["low"], "low": 2 * PIVOT - candle["high"]}


def mirror_boundary(boundary):
    return Boundary(boundary.boundary_id, boundary.anchor_time_ms, 2 * PIVOT - boundary.anchor_price,
                    -boundary.slope_per_ms, boundary.as_of_time_ms)


def run(boundary, candles):
    state, _ = initialize_state(boundary)
    return replay_closed_candles(boundary, state, candles)


LEVEL = Boundary.horizontal("lvl", PIVOT, as_of_time_ms=0)
# Rising line: 100 at t=0, +1 per minute.
RISING = Boundary("rise", 0, PIVOT, 1.0 / MINUTE, 0)

SCENARIOS = {
    "horizontal_naked_then_retest": (LEVEL, [
        bar(0, 99.0, 99.5, 98.5, 99.2),
        bar(1, 99.4, 102.5, 99.3, 102.0),   # naked UP
        bar(2, 102.0, 103.0, 101.5, 102.8),
        bar(3, 102.6, 102.7, 100.0, 100.4),  # low == level: contact
        bar(4, 100.4, 100.5, 98.0, 98.5),
    ], (EVENT_NO_TRANSITION, EVENT_NAKED_BREAKOUT, EVENT_NO_TRANSITION, EVENT_RETEST_PROVEN),
        PHASE_RETEST_PROVEN),
    "sloped_naked_then_ambiguous_touch": (RISING, [
        bar(0, 99.5, 101.6, 99.4, 101.5),    # line 100 -> 101: naked UP
        bar(1, 104.0, 104.5, 101.5, 103.5),  # line 101 -> 102, low between: unknown time
    ], (EVENT_NAKED_BREAKOUT, EVENT_RETEST_UNPROVEN), PHASE_RETEST_UNPROVEN),
    "sloped_naked_then_close_through": (RISING, [
        bar(0, 99.5, 101.6, 99.4, 101.5),
        bar(1, 102.5, 102.6, 101.6, 101.7),  # close 101.7 < line 102 at close
    ], (EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN), PHASE_RETEST_PROVEN),
    "no_retest_yet": (LEVEL, [
        bar(0, 99.0, 103.0, 98.9, 102.5),
        bar(1, 102.5, 104.0, 100.1, 103.0),
    ], (EVENT_NAKED_BREAKOUT, EVENT_NO_TRANSITION), PHASE_CAMPAIGN_ACTIVE),
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenarios_and_their_mirror_twins(name):
    boundary, candles, events, phase = SCENARIOS[name]
    state, got = run(boundary, candles)
    assert (got, state["phase"]) == (events, phase)
    assert state["breakout"]["direction"] == BREAKOUT_UP
    assert state["breakout"]["campaign_direction"] == CAMPAIGN_SHORT

    twin, twin_events = run(mirror_boundary(boundary), [mirror_bar(c) for c in candles])
    assert (twin_events, twin["phase"]) == (events, phase)
    assert twin["breakout"]["direction"] == BREAKOUT_DOWN
    assert twin["breakout"]["campaign_direction"] == CAMPAIGN_LONG
    assert (twin["retest"] or {}).get("close_time_ms") == (state["retest"] or {}).get("close_time_ms")


@pytest.mark.parametrize("candle", [
    bar(0, 100.0, 102.0, 99.5, 101.5),  # opens exactly on the level
    bar(0, 99.0, 100.0, 98.5, 100.0),   # closes exactly on the level
    bar(0, 99.0, 101.0, 98.5, 99.5),    # wick-only crossing
    bar(0, 100.5, 102.0, 99.0, 101.5),  # opened already beyond the level
], ids=["open_equal", "close_equal", "wick_only", "opened_beyond"])
def test_non_naked_candles_never_start_a_campaign(candle):
    assert naked_breakout_direction(LEVEL, candle) is None
    assert naked_breakout_direction(mirror_boundary(LEVEL), mirror_bar(candle)) is None


def test_sloped_line_is_evaluated_at_candle_open_and_close_times():
    # Above line(open)=100 but below line(close)=101: not a full-body crossing.
    assert naked_breakout_direction(RISING, bar(0, 99.5, 100.9, 99.4, 100.8)) is None
    assert naked_breakout_direction(RISING, bar(0, 99.5, 101.3, 99.4, 101.2)) == BREAKOUT_UP


def test_horizontal_level_is_never_ambiguous():
    boundary, candles, _, _ = SCENARIOS["horizontal_naked_then_retest"]
    state, _ = run(boundary, candles[:2])
    for low in (99.9, 100.0, 100.1):
        _, event = process_closed_candle(boundary, state, bar(2, 102.0, 102.5, low, 101.0))
        assert event in {EVENT_RETEST_PROVEN, EVENT_NO_TRANSITION}


def test_first_retest_is_terminal_and_later_taps_do_not_rearm():
    boundary, candles, _, _ = SCENARIOS["horizontal_naked_then_retest"]
    state, _ = run(boundary, candles[:4])
    later = [bar(5, 98.0, 103.0, 97.0, 102.5), bar(6, 102.5, 103.0, 99.0, 99.5)]
    for candle in later:
        new_state, event = process_closed_candle(boundary, state, candle)
        assert (new_state, event) == (state, EVENT_TERMINAL)


def test_breakout_candle_own_wick_is_not_a_retest():
    state, events = run(LEVEL, [bar(0, 99.0, 103.0, 98.0, 102.5)])
    assert events == (EVENT_NAKED_BREAKOUT,)
    assert state["retest"] is None


def test_verdicts_use_only_closed_prefix_no_look_ahead():
    boundary, candles, _, _ = SCENARIOS["horizontal_naked_then_retest"]
    _, full = run(boundary, candles)
    for k in range(1, len(candles) + 1):
        _, prefix = run(boundary, candles[:k])
        assert prefix == full[:k]
    # Rewriting candles after the terminal retest cannot change history.
    altered = candles[:4] + [bar(4, 150.0, 151.0, 149.0, 150.5)]
    assert run(boundary, altered) == run(boundary, candles)


def test_candles_before_boundary_as_of_and_stale_replays_are_ignored():
    late = Boundary.horizontal("late", PIVOT, as_of_time_ms=2 * MINUTE)
    state, _ = initialize_state(late)
    state, event = process_closed_candle(late, state, bar(1, 99.0, 103.0, 98.0, 102.5))
    assert (event, state["phase"]) == (EVENT_BEFORE_AS_OF, PHASE_WAITING_BREAKOUT)
    state, event = process_closed_candle(late, state, bar(2, 99.0, 103.0, 98.0, 102.5))
    assert event == EVENT_NAKED_BREAKOUT
    same, event = process_closed_candle(late, state, bar(2, 99.0, 103.0, 98.0, 102.5))
    assert (same, event) == (state, EVENT_IGNORED_STALE)


@pytest.mark.parametrize("candle", [
    bar(0, 99.0, 103.0, 98.0, 102.5) | {"closed": False},
    bar(0, 99.0, 101.0, 99.5, 102.5),
    bar(0, 99.0, 103.0, 98.0, float("nan")),
    bar(0, 99.0, 103.0, 98.0, 102.5) | {"close_time_ms": 0},
], ids=["open_candle", "ohlc_inconsistent", "nan", "zero_duration"])
def test_untrusted_candles_fail_closed(candle):
    state, _ = initialize_state(LEVEL)
    with pytest.raises(NakedRetestError):
        process_closed_candle(LEVEL, state, candle)


def test_state_from_another_boundary_is_rejected():
    state, _ = initialize_state(LEVEL)
    with pytest.raises(NakedRetestError):
        process_closed_candle(RISING, state, bar(0, 99.0, 103.0, 98.0, 102.5))


# --- MIRROR RETEST-2: owner decisions 2026-10-19 ---------------------------

def test_prior_compression_does_not_block_a_naked_breakout():
    # Several candles hugging the level before the strict body crossing.
    hugging = [bar(i, 99.8, 100.0, 99.6, 99.9) for i in range(5)]
    state, events = run(LEVEL, hugging + [bar(5, 99.7, 101.5, 99.6, 101.2)])
    assert events[-1] == EVENT_NAKED_BREAKOUT
    assert state["phase"] == PHASE_CAMPAIGN_ACTIVE


def test_atr_tolerance_zone_counts_a_near_miss_and_mirrors():
    near_miss = bar(2, 102.0, 102.5, 100.3, 101.0)  # 0.3 above the level
    boundary, candles, _, _ = SCENARIOS["horizontal_naked_then_retest"]
    state, _ = run(boundary, candles[:2])
    tolerance = atr_tolerance(atr=0.5, multiplier=1.0)  # test values, not a policy
    _, exact = process_closed_candle(boundary, state, near_miss)
    zoned, event = process_closed_candle(boundary, state, near_miss, retest_tolerance=tolerance)
    assert (exact, event) == (EVENT_NO_TRANSITION, EVENT_RETEST_PROVEN)
    assert zoned["retest"]["tolerance"] == tolerance

    twin_boundary = mirror_boundary(boundary)
    twin_state, _ = run(twin_boundary, [mirror_bar(c) for c in candles[:2]])
    _, twin_event = process_closed_candle(
        twin_boundary, twin_state, mirror_bar(near_miss), retest_tolerance=tolerance)
    assert twin_event == EVENT_RETEST_PROVEN


def test_tolerance_never_relaxes_the_naked_breakout_itself():
    state, _ = initialize_state(LEVEL)
    _, event = process_closed_candle(
        LEVEL, state, bar(0, 100.0, 102.0, 99.5, 101.5), retest_tolerance=5.0)
    assert event == EVENT_NO_TRANSITION


def test_replay_uses_per_candle_dynamic_tolerance():
    boundary, candles, _, _ = SCENARIOS["no_retest_yet"]  # low 100.1 after breakout
    atr_by_open = {0: 1.0, MINUTE: 0.2}
    _, events = run(boundary, candles)
    assert events[-1] == EVENT_NO_TRANSITION
    state, _ = initialize_state(boundary)
    state, events = replay_closed_candles(
        boundary, state, candles,
        retest_tolerance_for=lambda c: atr_tolerance(atr_by_open[c["open_time_ms"]], 1.0))
    assert (events[-1], state["retest"]["tolerance"]) == (EVENT_RETEST_PROVEN, 0.2)


@pytest.mark.parametrize("atr,multiplier", [(-1.0, 1.0), (1.0, -0.1), (float("nan"), 1.0), (None, 1.0)])
def test_atr_tolerance_rejects_untrusted_inputs(atr, multiplier):
    with pytest.raises(NakedRetestError):
        atr_tolerance(atr, multiplier)


def test_negative_tolerance_is_rejected():
    with pytest.raises(NakedRetestError):
        retest_contact(LEVEL, BREAKOUT_UP, bar(1, 102.0, 102.5, 101.0, 102.2), -0.1)


def test_campaign_has_no_fixed_horizon():
    quiet = [bar(i, 103.0, 103.5, 102.5, 103.2) for i in range(1, 2001)]
    state, events = run(LEVEL, [bar(0, 99.0, 103.0, 98.9, 102.5)] + quiet)
    assert state["phase"] == PHASE_CAMPAIGN_ACTIVE
    assert set(events[1:]) == {EVENT_NO_TRANSITION}


def test_proven_loss_of_level_relevance_is_terminal_and_not_retroactive():
    state, _ = run(LEVEL, [bar(0, 99.0, 103.0, 98.9, 102.5), bar(1, 102.5, 104.0, 101.0, 103.0)])
    with pytest.raises(NakedRetestError):
        mark_level_invalidated(LEVEL, state, reason="x", evidence_close_time_ms=MINUTE)
    with pytest.raises(NakedRetestError):
        mark_level_invalidated(LEVEL, state, reason=" ", evidence_close_time_ms=2 * MINUTE)
    ended, event = mark_level_invalidated(
        LEVEL, state, reason="caller_proof", evidence_close_time_ms=2 * MINUTE)
    assert (event, ended["phase"]) == (EVENT_LEVEL_INVALIDATED, PHASE_LEVEL_INVALIDATED)
    assert process_closed_candle(LEVEL, ended, bar(2, 103.0, 103.0, 99.0, 99.5))[1] == EVENT_TERMINAL


def test_only_an_active_campaign_can_be_invalidated():
    waiting, _ = initialize_state(LEVEL)
    with pytest.raises(NakedRetestError):
        mark_level_invalidated(LEVEL, waiting, reason="x", evidence_close_time_ms=0)
    boundary, candles, _, _ = SCENARIOS["horizontal_naked_then_retest"]
    retested, _ = run(boundary, candles)
    assert mark_level_invalidated(
        boundary, retested, reason="x", evidence_close_time_ms=10 * MINUTE) == (retested, EVENT_TERMINAL)
