from copy import deepcopy

import pytest

from robot_candidate_store import (
    RobotCandidateStateConflict,
    approve_candidate,
    create_signal_snapshot,
    load_candidate,
    save_robot_state,
)
from robot_state_machine import (
    EVENT_BREAKOUT,
    EVENT_EXPIRED_AT_APEX,
    EVENT_IGNORED_STALE,
    EVENT_NO_TRANSITION,
    EVENT_RESUMED_WITHOUT_REPLAY,
    EVENT_RETEST,
    PHASE_EXPIRED_AT_APEX,
    PHASE_RETEST_DETECTED,
    PHASE_WAITING_BREAKOUT,
    PHASE_WAITING_RETEST,
    RobotStateMachineError,
    boundary_price,
    initialize_state,
    process_closed_candle,
    resume_without_replay,
)


def _snapshot(pattern="Falling Wedge", *, current_index=100, apex_index=110):
    return {
        "symbol": "TESTUSDT",
        "pattern": pattern,
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {
                "index": apex_index,
                "price": 90.0,
                "valid_intersection": True,
            },
            "current_index": current_index,
        },
    }


def _candidate(pattern="Falling Wedge", *, current_index=100, apex_index=110):
    return {
        "status": "APPROVED",
        "timeframe": "1",
        "signal_snapshot": _snapshot(
            pattern,
            current_index=current_index,
            apex_index=apex_index,
        ),
    }


def _candle(index, *, high, low, close):
    return {
        "timeframe": "1",
        "closed": True,
        "geometry_index": index,
        "high": high,
        "low": low,
        "close": close,
    }


def test_falling_wedge_requires_close_above_frozen_upper_then_later_retest():
    candidate = _candidate()
    snapshot = candidate["signal_snapshot"]
    state, _ = initialize_state(candidate)

    assert state["phase"] == PHASE_WAITING_BREAKOUT
    assert boundary_price(snapshot, side="upper", geometry_index=101) == 99.0

    wick_only = _candle(101, high=101.0, low=97.0, close=98.5)
    state, event = process_closed_candle(snapshot, state, wick_only)
    assert event == EVENT_NO_TRANSITION
    assert state["phase"] == PHASE_WAITING_BREAKOUT

    breakout = _candle(102, high=100.0, low=98.0, close=99.0)
    state, event = process_closed_candle(snapshot, state, breakout)
    assert event == EVENT_BREAKOUT
    assert state["phase"] == PHASE_WAITING_RETEST
    assert state["breakout_index"] == 102

    no_retest = _candle(103, high=99.0, low=97.5, close=98.0)
    state, event = process_closed_candle(snapshot, state, no_retest)
    assert event == EVENT_NO_TRANSITION

    deep_retest = _candle(104, high=98.0, low=94.0, close=95.0)
    state, event = process_closed_candle(snapshot, state, deep_retest)
    assert event == EVENT_RETEST
    assert state["phase"] == PHASE_RETEST_DETECTED
    assert state["retest_index"] == 104


def test_rising_wedge_requires_close_below_lower_and_retests_from_below():
    candidate = _candidate("Rising Wedge")
    snapshot = candidate["signal_snapshot"]
    state, _ = initialize_state(candidate)

    # lower(101) = 94.5; a wick below is not a breakout.
    state, event = process_closed_candle(
        snapshot,
        state,
        _candle(101, high=96.0, low=93.0, close=95.0),
    )
    assert event == EVENT_NO_TRANSITION

    state, event = process_closed_candle(
        snapshot,
        state,
        _candle(102, high=95.0, low=92.0, close=93.0),
    )
    assert event == EVENT_BREAKOUT
    assert state["phase"] == PHASE_WAITING_RETEST

    # lower(103) = 93.5. Touching/up-crossing the boundary is a valid retest.
    state, event = process_closed_candle(
        snapshot,
        state,
        _candle(103, high=94.0, low=92.5, close=93.0),
    )
    assert event == EVENT_RETEST
    assert state["phase"] == PHASE_RETEST_DETECTED


def test_breakout_candle_cannot_also_become_retest():
    candidate = _candidate()
    snapshot = candidate["signal_snapshot"]
    state, _ = initialize_state(candidate)

    state, event = process_closed_candle(
        snapshot,
        state,
        _candle(101, high=102.0, low=95.0, close=100.0),
    )

    assert event == EVENT_BREAKOUT
    assert state["phase"] == PHASE_WAITING_RETEST
    assert state["retest_index"] is None


def test_apex_is_fail_closed_before_new_breakout_or_retest():
    candidate = _candidate(apex_index=103)
    snapshot = candidate["signal_snapshot"]
    state, _ = initialize_state(candidate)

    state, event = process_closed_candle(
        snapshot,
        state,
        _candle(103, high=110.0, low=80.0, close=105.0),
    )

    assert event == EVENT_EXPIRED_AT_APEX
    assert state["phase"] == PHASE_EXPIRED_AT_APEX
    assert state["breakout_index"] is None


def test_replayed_or_older_closed_candles_are_idempotently_ignored():
    candidate = _candidate()
    snapshot = candidate["signal_snapshot"]
    state, _ = initialize_state(candidate)

    state, event = process_closed_candle(
        snapshot,
        state,
        _candle(101, high=100.0, low=97.0, close=99.5),
    )
    assert event == EVENT_BREAKOUT

    replayed = deepcopy(state)
    result, event = process_closed_candle(
        snapshot,
        state,
        _candle(101, high=200.0, low=1.0, close=1.0),
    )
    assert event == EVENT_IGNORED_STALE
    assert result == replayed


def test_resume_advances_cursor_without_replaying_missed_breakout():
    candidate = _candidate(apex_index=120)
    snapshot = candidate["signal_snapshot"]
    state, _ = initialize_state(candidate)

    state, event = resume_without_replay(
        snapshot,
        state,
        latest_geometry_index=105,
    )
    assert event == EVENT_RESUMED_WITHOUT_REPLAY
    assert state["phase"] == PHASE_WAITING_BREAKOUT
    assert state["geometry_cursor"] == 105

    state, event = process_closed_candle(
        snapshot,
        state,
        _candle(106, high=96.0, low=92.0, close=95.0),
    )
    assert event == EVENT_BREAKOUT
    assert state["breakout_index"] == 106


def test_resume_past_apex_expires_without_replay():
    candidate = _candidate(apex_index=105)
    snapshot = candidate["signal_snapshot"]
    state, _ = initialize_state(candidate)

    state, event = resume_without_replay(
        snapshot,
        state,
        latest_geometry_index=105,
    )
    assert event == EVENT_EXPIRED_AT_APEX
    assert state["phase"] == PHASE_EXPIRED_AT_APEX


def test_state_machine_fails_closed_on_wrong_timeframe_or_bad_geometry():
    candidate = _candidate()
    candidate["timeframe"] = "5"
    with pytest.raises(RobotStateMachineError, match="requires 1m"):
        initialize_state(candidate)

    candidate = _candidate()
    candidate["signal_snapshot"]["geometry"]["upper_line"].pop("slope")
    with pytest.raises(RobotStateMachineError, match="upper_line.slope"):
        initialize_state(candidate)


def test_only_authoritative_closed_1m_candles_are_accepted():
    candidate = _candidate()
    snapshot = candidate["signal_snapshot"]
    state, _ = initialize_state(candidate)

    with pytest.raises(RobotStateMachineError, match="closed candles"):
        process_closed_candle(
            snapshot,
            state,
            {
                "timeframe": "1",
                "closed": False,
                "geometry_index": 101,
                "high": 101,
                "low": 98,
                "close": 100,
            },
        )


def test_robot_state_persistence_preserves_snapshot_and_rejects_stale_writer(tmp_path):
    original = _snapshot()
    create_signal_snapshot(
        original,
        timeframe="1",
        store_dir=tmp_path,
        candidate_id="candidate-1",
        created_at="2026-09-09T00:00:00+00:00",
    )
    approved, changed = approve_candidate(
        "candidate-1",
        store_dir=tmp_path,
        approved_at="2026-09-09T00:01:00+00:00",
        approval={"source": "telegram"},
    )
    assert changed is True

    state, _ = initialize_state(approved)
    persisted = save_robot_state(
        "candidate-1",
        state,
        expected_revision=0,
        store_dir=tmp_path,
    )
    assert persisted["robot_state"]["revision"] == 1
    assert persisted["signal_snapshot"] == original
    assert persisted["approval"] == {"source": "telegram"}

    with pytest.raises(RobotCandidateStateConflict, match="revision mismatch"):
        save_robot_state(
            "candidate-1",
            state,
            expected_revision=0,
            store_dir=tmp_path,
        )

    reloaded = load_candidate("candidate-1", store_dir=tmp_path)
    assert reloaded["signal_snapshot"] == original
    assert reloaded["robot_state"]["revision"] == 1
