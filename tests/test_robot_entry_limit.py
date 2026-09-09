from decimal import Decimal
import unittest

from robot_entry_limit import (
    RobotEntryLimitError,
    build_initial_retest_limit,
    submit_initial_retest_limit,
)
from robot_state_machine import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    PHASE_RETEST_DETECTED,
)
from terminal.api.models import CommandResultStatus, PaperLimitMutationResult, VolumeUnit
from terminal.domain.models import OrderSide


def _snapshot(pattern="Falling Wedge"):
    return {
        "symbol": "TESTUSDT",
        "pattern": pattern,
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {
                "index": 110,
                "price": 90.0,
                "valid_intersection": True,
            },
            "current_index": 100,
        },
    }


def _candidate(pattern="Falling Wedge"):
    return {
        "candidate_id": "candidate-1",
        "status": "APPROVED",
        "timeframe": "1",
        "signal_snapshot": _snapshot(pattern),
    }


def _state(direction=DIRECTION_LONG, *, breakout_index=102, retest_index=104):
    return {
        "phase": PHASE_RETEST_DETECTED,
        "direction": direction,
        "breakout_index": breakout_index,
        "retest_index": retest_index,
    }


class _RecordingSubmitter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create_limit(self, request):
        self.calls.append(request)
        return self.result


class RobotInitialRetestLimitTests(unittest.TestCase):
    def test_long_uses_frozen_upper_plus_two_ticks_and_one_wv(self):
        plan = build_initial_retest_limit(
            _candidate(),
            _state(),
            tick_size=Decimal("0.01"),
        )

        self.assertEqual(plan.direction, DIRECTION_LONG)
        self.assertEqual(plan.retest_index, 104)
        self.assertEqual(plan.boundary_price, Decimal("96.0"))
        self.assertEqual(plan.request.side, OrderSide.BUY)
        self.assertEqual(plan.request.limit_price, Decimal("96.02"))
        self.assertEqual(plan.request.sizing_reference_price, Decimal("96.02"))
        self.assertEqual(plan.request.volume.unit, VolumeUnit.WORKING_VOLUME)
        self.assertEqual(plan.request.volume.amount, Decimal("1"))

    def test_short_uses_frozen_lower_minus_two_ticks(self):
        plan = build_initial_retest_limit(
            _candidate("Rising Wedge"),
            _state(DIRECTION_SHORT, breakout_index=102, retest_index=103),
            tick_size=Decimal("0.01"),
        )

        self.assertEqual(plan.direction, DIRECTION_SHORT)
        self.assertEqual(plan.boundary_price, Decimal("93.5"))
        self.assertEqual(plan.request.side, OrderSide.SELL)
        self.assertEqual(plan.request.limit_price, Decimal("93.48"))

    def test_shared_normalizer_is_applied_after_two_tick_offset(self):
        candidate = _candidate()
        candidate["signal_snapshot"]["geometry"]["upper_line"] = {
            "slope": Decimal("-0.333"),
            "intercept": Decimal("130.777"),
        }
        plan = build_initial_retest_limit(
            candidate,
            _state(retest_index=104),
            tick_size=Decimal("0.05"),
        )

        self.assertEqual(plan.request.limit_price % Decimal("0.05"), Decimal("0.00"))
        self.assertLessEqual(plan.request.limit_price, plan.boundary_price + Decimal("0.10"))

    def test_client_action_id_is_stable_for_same_candidate_and_retest(self):
        first = build_initial_retest_limit(
            _candidate(), _state(), tick_size=Decimal("0.01")
        )
        second = build_initial_retest_limit(
            _candidate(), _state(), tick_size=Decimal("0.01")
        )

        self.assertEqual(
            first.request.client_action_id.value,
            second.request.client_action_id.value,
        )

    def test_different_retest_index_gets_different_action_identity(self):
        first = build_initial_retest_limit(
            _candidate(), _state(retest_index=104), tick_size=Decimal("0.01")
        )
        second = build_initial_retest_limit(
            _candidate(), _state(retest_index=105), tick_size=Decimal("0.01")
        )

        self.assertNotEqual(
            first.request.client_action_id.value,
            second.request.client_action_id.value,
        )

    def test_submission_calls_shared_create_limit_exactly_once_even_for_unknown(self):
        plan = build_initial_retest_limit(
            _candidate(), _state(), tick_size=Decimal("0.01")
        )
        expected = PaperLimitMutationResult(
            plan.request.client_action_id.value,
            CommandResultStatus.UNKNOWN,
            "ambiguous_transport",
            None,
        )
        submitter = _RecordingSubmitter(expected)

        result = submit_initial_retest_limit(submitter, plan)

        self.assertIs(result, expected)
        self.assertEqual(submitter.calls, [plan.request])

    def test_fails_closed_before_retest(self):
        state = _state()
        state["phase"] = "WAITING_RETEST"
        with self.assertRaisesRegex(RobotEntryLimitError, "RETEST_DETECTED"):
            build_initial_retest_limit(
                _candidate(), state, tick_size=Decimal("0.01")
            )

    def test_fails_closed_on_direction_pattern_mismatch(self):
        with self.assertRaisesRegex(RobotEntryLimitError, "differs from frozen pattern"):
            build_initial_retest_limit(
                _candidate("Rising Wedge"),
                _state(DIRECTION_LONG),
                tick_size=Decimal("0.01"),
            )

    def test_fails_closed_on_bad_tick_or_retest_order(self):
        with self.assertRaisesRegex(RobotEntryLimitError, "tick_size"):
            build_initial_retest_limit(
                _candidate(), _state(), tick_size=Decimal("0")
            )
        with self.assertRaisesRegex(RobotEntryLimitError, "after breakout"):
            build_initial_retest_limit(
                _candidate(),
                _state(breakout_index=104, retest_index=104),
                tick_size=Decimal("0.01"),
            )


if __name__ == "__main__":
    unittest.main()
