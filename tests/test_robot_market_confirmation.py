from decimal import Decimal
import unittest

from robot_market_confirmation import (
    DECISION_APEX_REACHED,
    DECISION_BLOCKED_LIMIT_ACTIVE,
    DECISION_BLOCKED_LIMIT_AMBIGUOUS,
    DECISION_FULL,
    DECISION_MARKET_ENTRY,
    DECISION_SKIPPED_LOW_REWARD,
    DECISION_SKIPPED_POOR_RR,
    DECISION_WAIT_CONFIRMATION,
    RobotMarketConfirmationError,
    build_confirmation_market,
    evaluate_confirmation,
    submit_confirmation_market,
)
from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT
from terminal.api.models import CommandResultStatus, CommandResult, VolumeUnit
from terminal.domain.models import OrderSide


def _snapshot(pattern="Falling Wedge"):
    return {
        "symbol": "TESTUSDT",
        "pattern": pattern,
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": 110, "price": 90.0, "valid_intersection": True},
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


def _state(direction=DIRECTION_LONG):
    return {"direction": direction, "apex_index": 110, "retest_index": 104}


def _candle(index=105, close="96.5"):
    return {
        "closed": True,
        "timeframe": "1",
        "geometry_index": index,
        "close": Decimal(close),
    }


class _RecordingSubmitter:
    def __init__(self):
        self.calls = []

    def market(self, request):
        self.calls.append(request)
        return CommandResult(request.client_action_id.value, CommandResultStatus.COMPLETED, "filled")


class RobotMarketConfirmationTests(unittest.TestCase):
    def test_long_requires_close_back_above_frozen_upper(self):
        waiting = evaluate_confirmation(
            _snapshot(), _state(), _candle(close="94.9"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("96"),
            stop_price=Decimal("94"), take_price=Decimal("100"),
            limit_active=False, limit_state_authoritative=True,
        )
        admitted = evaluate_confirmation(
            _snapshot(), _state(), _candle(close="95.1"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("96"),
            stop_price=Decimal("94"), take_price=Decimal("100"),
            limit_active=False, limit_state_authoritative=True,
        )
        self.assertEqual(waiting.action, DECISION_WAIT_CONFIRMATION)
        self.assertEqual(admitted.action, DECISION_MARKET_ENTRY)

    def test_short_requires_close_back_below_frozen_lower(self):
        state = _state(DIRECTION_SHORT)
        waiting = evaluate_confirmation(
            _snapshot("Rising Wedge"), state, _candle(close="92.6"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("92"),
            stop_price=Decimal("94"), take_price=Decimal("88"),
            limit_active=False, limit_state_authoritative=True,
        )
        admitted = evaluate_confirmation(
            _snapshot("Rising Wedge"), state, _candle(close="92.4"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("92"),
            stop_price=Decimal("94"), take_price=Decimal("88"),
            limit_active=False, limit_state_authoritative=True,
        )
        self.assertEqual(waiting.action, DECISION_WAIT_CONFIRMATION)
        self.assertEqual(admitted.action, DECISION_MARKET_ENTRY)

    def test_limit_must_be_authoritatively_inactive(self):
        ambiguous = evaluate_confirmation(
            _snapshot(), _state(), _candle(close="95.1"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("96"),
            stop_price=Decimal("94"), take_price=Decimal("100"),
            limit_active=False, limit_state_authoritative=False,
        )
        active = evaluate_confirmation(
            _snapshot(), _state(), _candle(close="95.1"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("96"),
            stop_price=Decimal("94"), take_price=Decimal("100"),
            limit_active=True, limit_state_authoritative=True,
        )
        self.assertEqual(ambiguous.action, DECISION_BLOCKED_LIMIT_AMBIGUOUS)
        self.assertEqual(active.action, DECISION_BLOCKED_LIMIT_ACTIVE)

    def test_rr_and_one_percent_reward_are_terminal_gates(self):
        poor_rr = evaluate_confirmation(
            _snapshot(), _state(), _candle(close="95.1"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("96"),
            stop_price=Decimal("90"), take_price=Decimal("100"),
            limit_active=False, limit_state_authoritative=True,
        )
        low_reward = evaluate_confirmation(
            _snapshot(), _state(), _candle(close="95.1"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("96"),
            stop_price=Decimal("95.7"), take_price=Decimal("96.5"),
            limit_active=False, limit_state_authoritative=True,
        )
        self.assertEqual(poor_rr.action, DECISION_SKIPPED_POOR_RR)
        self.assertEqual(low_reward.action, DECISION_SKIPPED_LOW_REWARD)

    def test_apex_and_full_position_block_new_exposure(self):
        apex = evaluate_confirmation(
            _snapshot(), _state(), _candle(index=110, close="91"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("92"),
            stop_price=Decimal("90"), take_price=Decimal("96"),
            limit_active=False, limit_state_authoritative=True,
        )
        full = evaluate_confirmation(
            _snapshot(), _state(), _candle(close="95.1"),
            filled_wv=Decimal("1"), sizing_reference_price=Decimal("96"),
            stop_price=Decimal("94"), take_price=Decimal("100"),
            limit_active=False, limit_state_authoritative=True,
        )
        self.assertEqual(apex.action, DECISION_APEX_REACHED)
        self.assertEqual(full.action, DECISION_FULL)

    def test_market_plan_uses_only_missing_wv_and_stable_identity(self):
        decision = evaluate_confirmation(
            _snapshot(), _state(), _candle(close="95.1"),
            filled_wv=Decimal("0.4"), sizing_reference_price=Decimal("96"),
            stop_price=Decimal("94"), take_price=Decimal("100"),
            limit_active=False, limit_state_authoritative=True,
        )
        first = build_confirmation_market(
            _candidate(), _state(), decision, geometry_index=105,
            sizing_reference_price=Decimal("96"), slippage_type="Percent",
            slippage_value=Decimal("0.1"),
        )
        second = build_confirmation_market(
            _candidate(), _state(), decision, geometry_index=105,
            sizing_reference_price=Decimal("96"), slippage_type="Percent",
            slippage_value=Decimal("0.1"),
        )
        self.assertEqual(first.request.side, OrderSide.BUY)
        self.assertEqual(first.request.volume.unit, VolumeUnit.WORKING_VOLUME)
        self.assertEqual(first.request.volume.amount, Decimal("0.6"))
        self.assertEqual(first.request.client_action_id, second.request.client_action_id)

    def test_submission_calls_shared_market_once_even_if_result_unknown(self):
        decision = evaluate_confirmation(
            _snapshot(), _state(), _candle(close="95.1"),
            filled_wv=Decimal("0"), sizing_reference_price=Decimal("96"),
            stop_price=Decimal("94"), take_price=Decimal("100"),
            limit_active=False, limit_state_authoritative=True,
        )
        plan = build_confirmation_market(
            _candidate(), _state(), decision, geometry_index=105,
            sizing_reference_price=Decimal("96"), slippage_type="Percent",
            slippage_value=Decimal("0.1"),
        )
        submitter = _RecordingSubmitter()
        submit_confirmation_market(submitter, plan)
        self.assertEqual(submitter.calls, [plan.request])

    def test_rejects_non_authoritative_candle_and_invalid_stop(self):
        candle = _candle(close="95.1")
        candle["closed"] = False
        with self.assertRaisesRegex(RobotMarketConfirmationError, "authoritative closed"):
            evaluate_confirmation(
                _snapshot(), _state(), candle,
                filled_wv=Decimal("0"), sizing_reference_price=Decimal("96"),
                stop_price=Decimal("94"), take_price=Decimal("100"),
                limit_active=False, limit_state_authoritative=True,
            )
        with self.assertRaisesRegex(RobotMarketConfirmationError, "STOP"):
            evaluate_confirmation(
                _snapshot(), _state(), _candle(close="95.1"),
                filled_wv=Decimal("0"), sizing_reference_price=Decimal("96"),
                stop_price=Decimal("97"), take_price=Decimal("100"),
                limit_active=False, limit_state_authoritative=True,
            )


if __name__ == "__main__":
    unittest.main()
