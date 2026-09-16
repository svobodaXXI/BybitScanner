import unittest

import robot_state_machine


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


def _candidate(snapshot):
    return {
        "candidate_id": "candidate-1",
        "status": "APPROVED",
        "timeframe": "1",
        "symbol": snapshot["symbol"],
        "signal_snapshot": snapshot,
    }


def _candle(index, *, high, low, close):
    return {
        "closed": True,
        "timeframe": "1",
        "geometry_index": index,
        "high": high,
        "low": low,
        "close": close,
    }


class RobotAdmissionCatchupReplayTests(unittest.TestCase):
    def _initial(self, *, apex_index=130):
        snapshot = _snapshot(apex_index=apex_index)
        state, _ = robot_state_machine.initialize_state(_candidate(snapshot))
        return snapshot, state

    def test_replay_without_breakout_remains_waiting_breakout(self):
        snapshot, state = self._initial()

        replayed, events = robot_state_machine.replay_closed_candles(
            snapshot,
            state,
            (
                _candle(101, high=96, low=94, close=95),
                _candle(102, high=97, low=95, close=96),
            ),
        )

        self.assertEqual(replayed["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)
        self.assertEqual(replayed["geometry_cursor"], 102)
        self.assertIsNone(replayed["breakout_index"])
        self.assertEqual(
            events,
            (robot_state_machine.EVENT_NO_TRANSITION, robot_state_machine.EVENT_NO_TRANSITION),
        )

    def test_replay_restores_waiting_retest_after_missed_breakout(self):
        snapshot, state = self._initial()

        replayed, events = robot_state_machine.replay_closed_candles(
            snapshot,
            state,
            (
                _candle(101, high=96, low=94, close=95),
                _candle(102, high=106, low=97, close=105),
                _candle(103, high=108, low=100, close=104),
            ),
        )

        self.assertEqual(replayed["phase"], robot_state_machine.PHASE_WAITING_RETEST)
        self.assertEqual(replayed["breakout_index"], 102)
        self.assertIsNone(replayed["retest_index"])
        self.assertEqual(replayed["geometry_cursor"], 103)
        self.assertEqual(events[-2:], (robot_state_machine.EVENT_BREAKOUT, robot_state_machine.EVENT_NO_TRANSITION))

    def test_replay_restores_retest_detected_without_waiting_for_second_retest(self):
        snapshot, state = self._initial()

        replayed, events = robot_state_machine.replay_closed_candles(
            snapshot,
            state,
            (
                _candle(101, high=96, low=94, close=95),
                _candle(102, high=106, low=97, close=105),
                _candle(103, high=101, low=95, close=98),
                # Must not be evaluated after RETEST_DETECTED becomes terminal.
                {"closed": False},
            ),
        )

        self.assertEqual(replayed["phase"], robot_state_machine.PHASE_RETEST_DETECTED)
        self.assertEqual(replayed["breakout_index"], 102)
        self.assertEqual(replayed["retest_index"], 103)
        self.assertEqual(replayed["geometry_cursor"], 103)
        self.assertEqual(events[-2:], (robot_state_machine.EVENT_BREAKOUT, robot_state_machine.EVENT_RETEST))
        self.assertEqual(len(events), 3)

    def test_replay_expires_at_apex_and_stops(self):
        snapshot, state = self._initial(apex_index=104)

        replayed, events = robot_state_machine.replay_closed_candles(
            snapshot,
            state,
            (
                _candle(104, high=99, low=97, close=98),
                {"closed": False},
            ),
        )

        self.assertEqual(replayed["phase"], robot_state_machine.PHASE_EXPIRED_AT_APEX)
        self.assertEqual(replayed["geometry_cursor"], 104)
        self.assertEqual(events, (robot_state_machine.EVENT_EXPIRED_AT_APEX,))

    def test_replaying_same_evidence_is_idempotent(self):
        snapshot, state = self._initial()
        candles = (
            _candle(101, high=96, low=94, close=95),
            _candle(102, high=106, low=97, close=105),
            _candle(103, high=101, low=95, close=98),
        )

        first, _ = robot_state_machine.replay_closed_candles(snapshot, state, candles)
        second, events = robot_state_machine.replay_closed_candles(snapshot, first, candles)

        self.assertEqual(second, first)
        self.assertEqual(events, (robot_state_machine.EVENT_TERMINAL,))


if __name__ == "__main__":
    unittest.main()
