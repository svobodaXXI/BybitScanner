import unittest

import robot_state_machine
from terminal.application.robot_admission_catchup import (
    LATE_ADMISSION_MARKET,
    replay_admission_catchup,
)


def _snapshot(*, apex_index=130):
    return {
        "symbol": "TESTUSDT",
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": apex_index, "price": 90.0, "valid_intersection": True},
            "current_index": 100,
        },
    }


def _initial_state(snapshot):
    state, _event = robot_state_machine.initialize_state({
        "candidate_id": "candidate-1",
        "status": "APPROVED",
        "timeframe": "1",
        "symbol": "TESTUSDT",
        "signal_snapshot": snapshot,
    })
    return state


def _candle(index, *, high, low, close):
    return {
        "closed": True,
        "timeframe": "1",
        "geometry_index": index,
        "high": high,
        "low": low,
        "close": close,
    }


class RobotAdmissionCatchupTests(unittest.TestCase):
    def test_no_retest_keeps_existing_entry_path_unmarked(self):
        snapshot = _snapshot()
        state, events = replay_admission_catchup(
            snapshot,
            _initial_state(snapshot),
            (
                _candle(101, high=100, low=98, close=99),
                _candle(102, high=105, low=102, close=104),
            ),
        )

        self.assertEqual(state["phase"], robot_state_machine.PHASE_WAITING_RETEST)
        self.assertIn(robot_state_machine.EVENT_BREAKOUT, events)
        self.assertNotIn("execution", state)

    def test_replay_discovered_retest_marks_late_admission_market(self):
        snapshot = _snapshot()
        state, events = replay_admission_catchup(
            snapshot,
            _initial_state(snapshot),
            (
                _candle(101, high=100, low=98, close=99),
                _candle(102, high=105, low=102, close=104),
                _candle(103, high=101, low=95, close=98),
            ),
        )

        self.assertEqual(state["phase"], robot_state_machine.PHASE_RETEST_DETECTED)
        self.assertEqual(state["breakout_index"], 102)
        self.assertEqual(state["retest_index"], 103)
        self.assertIn(robot_state_machine.EVENT_RETEST, events)
        self.assertEqual(state["execution"]["entry_mode"], LATE_ADMISSION_MARKET)

    def test_apex_expiry_is_not_marked_as_late_admission_entry(self):
        snapshot = _snapshot(apex_index=102)
        state, events = replay_admission_catchup(
            snapshot,
            _initial_state(snapshot),
            (_candle(102, high=105, low=95, close=104),),
        )

        self.assertEqual(state["phase"], robot_state_machine.PHASE_EXPIRED_AT_APEX)
        self.assertEqual(events, (robot_state_machine.EVENT_EXPIRED_AT_APEX,))
        self.assertNotIn("execution", state)

    def test_existing_execution_diagnostics_are_preserved_when_marker_is_added(self):
        snapshot = _snapshot()
        initial = _initial_state(snapshot)
        initial["execution"] = {"attempt_count": 2, "last_execution_error": "old"}

        state, _events = replay_admission_catchup(
            snapshot,
            initial,
            (
                _candle(102, high=105, low=102, close=104),
                _candle(103, high=101, low=95, close=98),
            ),
        )

        self.assertEqual(state["execution"]["attempt_count"], 2)
        self.assertEqual(state["execution"]["last_execution_error"], "old")
        self.assertEqual(state["execution"]["entry_mode"], LATE_ADMISSION_MARKET)


if __name__ == "__main__":
    unittest.main()
