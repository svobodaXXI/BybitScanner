"""#613 M1-M3: universal mirror levels, swing zones, breakout evidence, FVG lifecycle.

Synthetic contracts plus three real #608-day cases (public Bybit candles, frozen
in tests/fixtures/mirror_levels): HORN KNCUSDT 5m, HORN AVAUSDT 1m and the
DRIFTUSDT 1m Falling Wedge Robot candidate.
"""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from geometry.naked_retest import Boundary, naked_breakout_direction
from mirror_levels.breakout import (
    KIND_CLOSE_ONLY, KIND_FULL_BODY, KIND_WICK_ONLY, classify_crossing,
)
from mirror_levels.imbalance import (
    BEARISH, BULLISH, PHASE_EDGE, PHASE_FULL, PHASE_PARTIAL, PHASE_UNTOUCHED,
    advance, cluster_fvgs, detect_fvgs, initial_state, replay,
)
from mirror_levels.levels import (
    SOURCE_PATTERN_BOUNDARY, SOURCE_SWING_ZONE, LevelRegistry, MirrorLevel, MirrorLevelError,
    horizontal_level, level_identity, levels_from_geometry, levels_from_horn_event,
    levels_from_ikigai_box, levels_from_l_shape, levels_from_wedge_candidate, line_level,
)
from mirror_levels.swing import confirmed_pivots, swing_levels
from mirror_levels.tracker import (
    STATUS_RETESTED, STATUS_UNTESTED, STATUS_WAITING, track,
)
from mirror_retest_observer import boundaries_from_candidate_snapshot
from retest_calibration import causal_atr_series

M = 60_000
FIXTURES = Path(__file__).parent / "fixtures" / "mirror_levels"


def bar(i, o, h, l, c, step=M):
    return {"open_time_ms": i * step, "close_time_ms": (i + 1) * step,
            "open": o, "high": h, "low": l, "close": c}


def flat(level, i):
    return horizontal_level(symbol="TESTUSDT", timeframe="1", source=SOURCE_SWING_ZONE,
                            pattern=None, side="upper", price=level, anchor_time_ms=0,
                            confirmed_at_ms=i * M)


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


# --- M1: identity, adapters, registry ------------------------------------------------------------

def test_level_identity_is_deterministic_and_anchor_sensitive():
    kwargs = dict(symbol="X", timeframe="5", source=SOURCE_PATTERN_BOUNDARY, pattern="Broadening",
                  side="upper", anchors=((1000, 1.5), (2000, 1.6)))
    assert level_identity(**kwargs) == level_identity(**kwargs)
    assert level_identity(**kwargs) != level_identity(**{**kwargs, "anchors": ((1000, 1.5), (3000, 1.6))})
    assert level_identity(**kwargs) != level_identity(**{**kwargs, "side": "lower"})


def test_line_level_reproduces_both_anchors_and_is_not_usable_before_confirmation():
    level = line_level(symbol="X", timeframe="1", pattern="Triangle", side="lower",
                       first=(10 * M, 2.0), second=(20 * M, 3.0), confirmed_at_ms=25 * M)
    assert level.price_at(10 * M) == 2.0 and level.price_at(20 * M) == pytest.approx(3.0)
    assert level.boundary.as_of_time_ms == 25 * M
    with pytest.raises(MirrorLevelError):
        line_level(symbol="X", timeframe="1", pattern="Triangle", side="lower",
                   first=(10 * M, 2.0), second=(20 * M, 3.0), confirmed_at_ms=15 * M)
    with pytest.raises(MirrorLevelError):
        line_level(symbol="X", timeframe="1", pattern="Triangle", side="lower",
                   first=(20 * M, 2.0), second=(10 * M, 3.0), confirmed_at_ms=25 * M)


def test_level_round_trips_through_persistence():
    level = line_level(symbol="X", timeframe="5", pattern="Broadening", side="upper",
                       first=(0, 1.0), second=(600_000, 1.2), confirmed_at_ms=900_000,
                       provenance={"identity": "horn:X"})
    again = MirrorLevel.from_dict(json.loads(json.dumps(level.to_dict())))
    assert again == level


def test_engine_geometry_adapter_uses_index_lines_and_refuses_future_anchors():
    times = [i * M for i in range(50)]
    geometry = {"upper_line": {"slope": -0.01, "intercept": 5.0, "anchor_index": 10, "second_index": 30},
                "lower_line": {"slope": 0.02, "intercept": 3.0, "anchor_index": 12, "second_index": 35}}
    upper, lower = levels_from_geometry(symbol="X", timeframe="1", pattern="Triangle",
                                        geometry=geometry, candle_times_ms=times, decision_index=40)
    assert upper.price_at(30 * M) == pytest.approx(5.0 - 0.3)
    assert lower.price_at(12 * M) == pytest.approx(3.24)
    assert upper.confirmed_at_ms == 41 * M
    assert levels_from_geometry(symbol="X", timeframe="1", pattern="Triangle", geometry=geometry,
                                candle_times_ms=times, decision_index=32) == ()
    assert levels_from_geometry(symbol="X", timeframe="1", pattern="Triangle",
                                geometry={"upper_line": geometry["upper_line"]},
                                candle_times_ms=times, decision_index=40) == ()


def test_box_and_l_shape_adapters_are_horizontal_and_known_at_their_decision_candle():
    times = [i * M for i in range(30)]
    box = SimpleNamespace(direction="LONG", as_of_index=20, box_start_index=8, box_end_index=15,
                          box_high=1.25, box_low=1.10)
    high, low = levels_from_ikigai_box(symbol="X", timeframe="1", formation=box, candle_times_ms=times)
    assert (high.side, high.boundary.anchor_price, high.is_horizontal) == ("upper", 1.25, True)
    assert low.boundary.anchor_price == 1.10 and low.confirmed_at_ms == 21 * M
    shape = SimpleNamespace(direction="SHORT", as_of_index=25, breakout_index=25, extreme_index=12,
                            breakout_level=0.9)
    (level,) = levels_from_l_shape(symbol="X", timeframe="1", formation=shape, candle_times_ms=times)
    assert (level.side, level.boundary.anchor_price, level.confirmed_at_ms) == ("lower", 0.9, 26 * M)
    assert levels_from_ikigai_box(symbol="X", timeframe="1", formation=object(), candle_times_ms=times) == ()


def test_registry_is_idempotent_merges_same_price_sources_and_persists():
    registry = LevelRegistry()
    early = horizontal_level(symbol="X", timeframe="1", source=SOURCE_SWING_ZONE, pattern=None,
                             side="upper", price=1.000, anchor_time_ms=0, confirmed_at_ms=5 * M)
    late = horizontal_level(symbol="X", timeframe="1", source=SOURCE_PATTERN_BOUNDARY,
                            pattern="IKIGAI_BOX", side="upper", price=1.001, anchor_time_ms=M,
                            confirmed_at_ms=9 * M)
    other = horizontal_level(symbol="X", timeframe="1", source=SOURCE_SWING_ZONE, pattern=None,
                             side="lower", price=1.000, anchor_time_ms=0, confirmed_at_ms=5 * M)
    assert registry.add(late, merge_tolerance=0.002) is late
    assert registry.add(early, merge_tolerance=0.002) is early        # earliest confirmed wins
    assert registry.add(early, merge_tolerance=0.002) is early        # idempotent
    registry.add(other, merge_tolerance=0.002)                         # other side: separate level
    assert set(registry.levels) == {early.level_id, other.level_id}
    assert registry.aliases == {early.level_id: [late.level_id]}
    assert registry.get(late.level_id) is early
    assert registry.known_at(4 * M) == ()
    restored = LevelRegistry.from_dict(json.loads(json.dumps(registry.to_dict())))
    assert restored.to_dict() == registry.to_dict()


# --- M2: swing zones without a pattern ------------------------------------------------------------

def _two_tops():
    rows = []
    prices = [1.0, 1.01, 1.02, 1.03, 1.10, 1.03, 1.02, 1.01, 1.00, 1.01, 1.02, 1.03, 1.1005,
              1.03, 1.02, 1.01, 1.00, 1.0, 1.0, 1.0]
    for i, p in enumerate(prices):
        rows.append(bar(i, p - 0.002, p, p - 0.01, p - 0.001))
    return rows


def test_swing_zone_needs_two_confirmed_touches_and_is_known_only_after_confirmation():
    candles = _two_tops()
    highs, _ = confirmed_pivots(candles)
    assert [(p["index"], p["confirmed_at_ms"]) for p in highs] == [(4, 8 * M), (12, 16 * M)]
    (level,) = [lvl for lvl in swing_levels(candles, symbol="X", timeframe="1", tolerance_atr=1.0,
                                             atr_period=3) if lvl.side == "upper"]
    assert (level.boundary.anchor_price, level.touches, level.confirmed_at_ms) == (1.10, 2, 16 * M)
    assert level.source == SOURCE_SWING_ZONE and level.pattern is None


def test_swing_levels_have_prefix_parity_on_every_cut():
    candles = fixture("horn_KNCUSDT_5_1792842000000.json")["candles"]
    full = swing_levels(candles, symbol="KNCUSDT", timeframe="5")
    assert full, "real KNCUSDT window must contain swing zones"
    for cut in range(20, len(candles), 7):
        horizon = candles[cut - 1]["close_time_ms"]
        expected = [lvl.to_dict() for lvl in full if lvl.confirmed_at_ms <= horizon]
        got = [lvl.to_dict() for lvl in swing_levels(candles[:cut], symbol="KNCUSDT", timeframe="5")]
        assert got == expected, cut


# --- M3: breakout evidence -----------------------------------------------------------------------

@pytest.mark.parametrize("candle,expected", [
    (bar(5, 0.99, 1.02, 0.98, 1.01), (KIND_FULL_BODY, "UP")),
    (bar(5, 1.01, 1.02, 0.98, 0.99), (KIND_FULL_BODY, "DOWN")),
    (bar(5, 0.98, 1.02, 0.97, 0.99), (KIND_WICK_ONLY, "UP")),
    (bar(5, 1.02, 1.03, 0.98, 1.01), (KIND_WICK_ONLY, "DOWN")),
    (bar(5, 1.00, 1.02, 0.99, 1.01), (KIND_CLOSE_ONLY, "UP")),
    (bar(5, 0.97, 0.99, 0.96, 0.98), None),
])
def test_crossing_classes(candle, expected):
    level = flat(1.0, 0)
    evidence = classify_crossing(level.boundary, candle, atr=0.01)
    if expected is None:
        assert evidence is None
        return
    assert (evidence.kind, evidence.direction) == expected
    assert evidence.is_naked == (naked_breakout_direction(level.boundary, dict(candle, closed=True)) is not None)


def test_gap_over_the_level_is_close_only_not_naked():
    level = flat(1.0, 0)
    gap_up = bar(5, 1.02, 1.04, 1.015, 1.03)
    assert classify_crossing(level.boundary, gap_up) is None
    evidence = classify_crossing(level.boundary, gap_up, previous_close=0.99)
    assert (evidence.kind, evidence.direction) == (KIND_CLOSE_ONLY, "UP")
    gap_down = bar(5, 0.98, 0.985, 0.96, 0.97)
    evidence = classify_crossing(level.boundary, gap_down, previous_close=1.01)
    assert (evidence.kind, evidence.direction) == (KIND_CLOSE_ONLY, "DOWN")


def test_sloped_level_is_evaluated_at_the_candle_own_times():
    rising = Boundary("b", 0, 1.0, 0.01 / M, 0)
    candle = bar(10, 1.095, 1.12, 1.09, 1.115)   # level 1.10 at open, 1.11 at close
    evidence = classify_crossing(rising, candle)
    assert (evidence.kind, evidence.level_at_open, evidence.level_at_close) == (KIND_FULL_BODY, 1.10, pytest.approx(1.11))


# --- M3: FVG / IFVG --------------------------------------------------------------------------------

def _bull_gap():
    return [bar(0, 1.00, 1.01, 0.99, 1.005), bar(1, 1.005, 1.08, 1.0, 1.075),
            bar(2, 1.075, 1.09, 1.03, 1.085)]


def test_fvg_is_known_only_when_the_third_candle_closed():
    candles = _bull_gap()
    assert detect_fvgs(candles[:2], symbol="X", timeframe="1") == ()
    (gap,) = detect_fvgs(candles, symbol="X", timeframe="1")
    assert (gap.direction, gap.bottom, gap.top, gap.formed_at_ms) == (BULLISH, 1.01, 1.03, 3 * M)
    bear = [bar(0, 1.0, 1.01, 0.99, 0.995), bar(1, 0.995, 1.0, 0.92, 0.925), bar(2, 0.925, 0.98, 0.91, 0.915)]
    (gap,) = detect_fvgs(bear, symbol="X", timeframe="1")
    assert (gap.direction, gap.bottom, gap.top) == (BEARISH, 0.98, 0.99)


def test_fvg_fill_depth_inversion_and_ifvg_retest():
    (gap,) = detect_fvgs(_bull_gap(), symbol="X", timeframe="1")
    state = initial_state(gap)
    assert state["phase"] == PHASE_UNTOUCHED
    state = advance(gap, state, bar(3, 1.08, 1.09, 1.03, 1.06))          # edge
    assert (state["phase"], state["first_touch_ms"]) == (PHASE_EDGE, 3 * M)
    state = advance(gap, state, bar(4, 1.06, 1.07, 1.02, 1.05))          # 50 %
    assert state["phase"] == PHASE_PARTIAL and state["midpoint_touch_ms"] == 4 * M
    assert state["max_wick_depth"] == pytest.approx(0.5)
    assert state["unfilled_top"] == pytest.approx(1.02)
    assert advance(gap, state, bar(4, 1.0, 1.0, 1.0, 1.0)) == state     # stale candle ignored
    state = advance(gap, state, bar(5, 1.05, 1.05, 1.00, 1.005))         # full fill + closed through
    assert state["phase"] == PHASE_FULL and state["inverted_ms"] == 5 * M
    assert state["ifvg_retest_ms"] is None
    state = advance(gap, state, bar(6, 1.0, 1.012, 0.99, 1.0))           # back up into the zone
    assert state["ifvg_retest_ms"] == 6 * M


def test_fvg_state_blocks_on_a_missing_candle():
    (gap,) = detect_fvgs(_bull_gap(), symbol="X", timeframe="1")
    state = advance(gap, initial_state(gap), bar(5, 1.08, 1.09, 1.0, 1.0))
    assert state["data_blocked"] and state["phase"] == PHASE_UNTOUCHED


def test_consecutive_gaps_cluster_but_keep_components():
    candles = _bull_gap() + [bar(3, 1.085, 1.15, 1.095, 1.14), bar(4, 1.14, 1.2, 1.12, 1.19)]
    gaps = detect_fvgs(candles, symbol="X", timeframe="1")
    assert len(gaps) == 3
    (cluster,) = cluster_fvgs(gaps, timeframe_ms=M)
    assert cluster["components"] == [g.fvg_id for g in gaps]
    assert (cluster["bottom"], cluster["top"]) == (1.01, 1.12)


# --- tracker: fresh untested level, first retest, FVG only as a factor ---------------------------

def test_level_without_any_gap_is_tracked_to_its_first_retest():
    level = flat(1.0, 0)
    candles = [bar(1, 0.98, 0.99, 0.97, 0.985), bar(2, 0.99, 1.02, 0.985, 1.015),
               bar(3, 1.015, 1.03, 1.01, 1.025), bar(4, 1.025, 1.03, 0.999, 1.02)]
    record = track(level, candles[:3])
    assert record["status"] == STATUS_UNTESTED and record["imbalance"] == []
    assert record["breakout_evidence"]["kind"] == KIND_FULL_BODY
    record = track(level, candles[3:], record=json.loads(json.dumps(record)))
    assert record["status"] == STATUS_RETESTED
    assert track(level, candles[:1])["status"] == STATUS_WAITING


def test_gap_around_the_breakout_is_linked_only_after_its_third_candle_closed():
    level = flat(1.02, 0)
    candles = _bull_gap() + [bar(3, 1.085, 1.09, 1.06, 1.07)]
    gaps = detect_fvgs(candles, symbol="X", timeframe="1")
    after_breakout = track(level, candles[:2], gaps=gaps)      # breakout = displacement candle
    assert after_breakout["status"] == STATUS_UNTESTED and after_breakout["imbalance"] == []
    after_third = track(level, candles[2:3], record=after_breakout, gaps=gaps)
    assert [item["position"] for item in after_third["imbalance"]] == ["inside"]


# --- real #608-day cases ---------------------------------------------------------------------------

def _real_track(data, level):
    candles = data["candles"]
    atr = dict(zip((c["close_time_ms"] for c in candles), causal_atr_series(candles, 14)))
    gaps = detect_fvgs(candles, symbol=level.symbol, timeframe=level.timeframe)
    later = [c for c in candles if c["open_time_ms"] >= level.confirmed_at_ms]
    full = track(level, later, atr_at=atr.get, gaps=gaps)
    half = len(later) // 2
    resumed = track(level, later[half:], atr_at=atr.get, gaps=gaps,
                    record=json.loads(json.dumps(track(level, later[:half], atr_at=atr.get, gaps=gaps))))
    assert resumed == json.loads(json.dumps(full))          # restart equivalence
    return full


def test_real_horn_levels_match_event_anchors_and_track():
    knc = fixture("horn_KNCUSDT_5_1792842000000.json")
    upper, lower = levels_from_horn_event(knc["event"])
    for level, side in ((upper, "upper"), (lower, "lower")):
        line = knc["event"][f"{side}_line"]
        assert level.price_at(line["anchor_time_ms"]) == pytest.approx(line["anchor_price"], rel=1e-12)
        assert level.price_at(line["second_time_ms"]) == pytest.approx(line["second_price"], rel=1e-12)
    record = _real_track(knc, lower)
    assert record["status"] == STATUS_UNTESTED
    assert record["breakout_evidence"]["kind"] == KIND_FULL_BODY
    assert len(record["imbalance"]) == 3
    assert _real_track(knc, upper)["status"] == STATUS_WAITING

    ava = fixture("horn_AVAUSDT_1_1792840500000.json")
    upper, _ = levels_from_horn_event(ava["event"])
    record = _real_track(ava, upper)
    assert record["status"] == STATUS_RETESTED
    assert record["naked_retest"]["breakout"]["direction"] == "UP"


def test_real_wedge_adapter_equals_the_existing_mirror_transform():
    drift = fixture("wedge_DRIFTUSDT_d954e71a03.json")
    levels = levels_from_wedge_candidate(candidate_id=drift["candidate_id"], symbol="DRIFTUSDT",
                                         created_at_ms=drift["approved_at_ms"],
                                         signal_snapshot=drift["signal_snapshot"])
    reference = boundaries_from_candidate_snapshot(candidate_id=drift["candidate_id"],
                                                   created_at_ms=drift["approved_at_ms"],
                                                   signal_snapshot=drift["signal_snapshot"])
    for level, boundary in zip(levels, reference):
        assert level.boundary.as_of_time_ms == boundary.as_of_time_ms
        for t in (boundary.anchor_time_ms, boundary.as_of_time_ms, boundary.as_of_time_ms + 3_600_000):
            assert level.price_at(t) == pytest.approx(boundary.price_at(t), rel=1e-12)
    upper, lower = levels
    assert _real_track(drift, upper)["status"] == STATUS_RETESTED
    assert _real_track(drift, lower)["status"] == STATUS_UNTESTED


def test_real_fvg_detection_has_prefix_parity():
    candles = fixture("wedge_DRIFTUSDT_d954e71a03.json")["candles"]
    full = detect_fvgs(candles, symbol="DRIFTUSDT", timeframe="1")
    assert full
    for cut in range(3, len(candles), 37):
        horizon = candles[cut - 1]["close_time_ms"]
        assert detect_fvgs(candles[:cut], symbol="DRIFTUSDT", timeframe="1") == tuple(
            gap for gap in full if gap.formed_at_ms <= horizon)
    assert replay(full[0], candles)["phase"] in {PHASE_UNTOUCHED, PHASE_EDGE, PHASE_PARTIAL, PHASE_FULL}
