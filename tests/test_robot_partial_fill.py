from decimal import Decimal
import unittest

from robot_partial_fill import (
    DECISION_APEX_REACHED,
    DECISION_BLOCKED_AMBIGUOUS,
    DECISION_BLOCKED_POOR_RR,
    DECISION_FULL,
    DECISION_KEEP_PARTIAL,
    DECISION_MARKET_COMPLETE,
    DECISION_WAIT,
    PartialFillSnapshot,
    RobotPartialFillError,
    adverse_move_ratio,
    build_topup_limit,
    evaluate_partial_completion,
    missing_wv,
    topup_due,
)
from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT
from terminal.api.models import VolumeUnit
from terminal.domain.models import OrderSide


def _candidate(pattern="Falling Wedge"):
    return {
        "candidate_id": "candidate-1",
        "status": "APPROVED",
        "signal_snapshot": {
            "symbol": "TESTUSDT",
            "pattern": pattern,
            "geometry": {
                "upper_line": {"slope": -1.0, "intercept": 200.0},
                "lower_line": {"slope": -0.5, "intercept": 145.0},
                "apex": {"index": 110, "price": 90.0, "valid_intersection": True},
                "current_index": 100,
            },
        },
    }


def _state(direction=DIRECTION_LONG, apex_index=110):
    return {"direction": direction, "apex_index": apex_index}


class RobotPartialFillTests(unittest.TestCase):
    def test_missing_wv_is_capped_at_one(self):
        self.assertEqual(missing_wv(Decimal("0.35")), Decimal("0.65"))
        self.assertEqual(missing_wv(Decimal("1")), Decimal("0"))
        with self.assertRaisesRegex(RobotPartialFillError, "exceeds 1 WV"):
            missing_wv(Decimal("1.01"))

    def test_adverse_direction_is_higher_for_long_lower_for_short(self):
        self.assertEqual(
            adverse_move_ratio(
                DIRECTION_LONG,
                reference_price=Decimal("100"),
                current_price=Decimal("100.5"),
            ),
            Decimal("0.005"),
        )
        self.assertEqual(
            adverse_move_ratio(
                DIRECTION_SHORT,
                reference_price=Decimal("100"),
                current_price=Decimal("99.5"),
            ),
            Decimal("0.005"),
        )
        self.assertEqual(
            adverse_move_ratio(
                DIRECTION_LONG,
                reference_price=Decimal("100"),
                current_price=Decimal("99"),
            ),
            Decimal("0"),
        )

    def test_waits_full_ten_seconds_before_market_completion(self):
        snapshot = PartialFillSnapshot(
            DIRECTION_LONG, Decimal("0.4"), 1_000, Decimal("100"), True,
        )
        decision = evaluate_partial_completion(
            snapshot,
            now_ms=10_999,
            current_price=Decimal("100.4"),
            rr=Decimal("1.2"),
            before_apex=True,
        )
        self.assertEqual(decision.action, DECISION_WAIT)

        decision = evaluate_partial_completion(
            snapshot,
            now_ms=11_000,
            current_price=Decimal("100.5"),
            rr=Decimal("1.2"),
            before_apex=True,
        )
        self.assertEqual(decision.action, DECISION_MARKET_COMPLETE)
        self.assertEqual(decision.missing_wv, Decimal("0.6"))

    def test_more_than_half_percent_adverse_move_does_not_chase(self):
        snapshot = PartialFillSnapshot(
            DIRECTION_LONG, Decimal("0.4"), 1_000, Decimal("100"), True,
        )
        decision = evaluate_partial_completion(
            snapshot,
            now_ms=20_000,
            current_price=Decimal("100.5001"),
            rr=Decimal("1.5"),
            before_apex=True,
        )
        self.assertEqual(decision.action, DECISION_KEEP_PARTIAL)

    def test_ambiguous_active_order_blocks_market_completion(self):
        snapshot = PartialFillSnapshot(
            DIRECTION_SHORT, Decimal("0.25"), 1_000, Decimal("100"), False,
        )
        decision = evaluate_partial_completion(
            snapshot,
            now_ms=20_000,
            current_price=Decimal("99.8"),
            rr=Decimal("1.5"),
            before_apex=True,
        )
        self.assertEqual(decision.action, DECISION_BLOCKED_AMBIGUOUS)

    def test_rr_and_apex_fail_closed(self):
        snapshot = PartialFillSnapshot(
            DIRECTION_LONG, Decimal("0.5"), 1_000, Decimal("100"), True,
        )
        self.assertEqual(
            evaluate_partial_completion(
                snapshot,
                now_ms=20_000,
                current_price=Decimal("100"),
                rr=Decimal("0.99"),
                before_apex=True,
            ).action,
            DECISION_BLOCKED_POOR_RR,
        )
        self.assertEqual(
            evaluate_partial_completion(
                snapshot,
                now_ms=20_000,
                current_price=Decimal("100"),
                rr=Decimal("2"),
                before_apex=False,
            ).action,
            DECISION_APEX_REACHED,
        )

    def test_full_position_never_requests_more_exposure(self):
        snapshot = PartialFillSnapshot(
            DIRECTION_LONG, Decimal("1"), 1_000, Decimal("100"), False,
        )
        decision = evaluate_partial_completion(
            snapshot,
            now_ms=20_000,
            current_price=Decimal("200"),
            rr=Decimal("0"),
            before_apex=False,
        )
        self.assertEqual(decision.action, DECISION_FULL)
        self.assertEqual(decision.missing_wv, Decimal("0"))

    def test_topup_reprice_is_due_every_five_new_closed_candles(self):
        self.assertFalse(topup_due(last_limit_index=104, current_index=108))
        self.assertTrue(topup_due(last_limit_index=104, current_index=109))

    def test_long_topup_uses_missing_wv_and_upper_plus_two_ticks(self):
        plan = build_topup_limit(
            _candidate(),
            _state(),
            geometry_index=105,
            filled_wv=Decimal("0.4"),
            tick_size=Decimal("0.01"),
            rr=Decimal("1.1"),
        )
        self.assertEqual(plan.missing_wv, Decimal("0.6"))
        self.assertEqual(plan.request.volume.unit, VolumeUnit.WORKING_VOLUME)
        self.assertEqual(plan.request.volume.amount, Decimal("0.6"))
        self.assertEqual(plan.request.side, OrderSide.BUY)
        self.assertEqual(plan.boundary_price, Decimal("95.0"))
        self.assertEqual(plan.request.limit_price, Decimal("95.02"))

    def test_short_topup_uses_lower_minus_two_ticks(self):
        plan = build_topup_limit(
            _candidate("Rising Wedge"),
            _state(DIRECTION_SHORT),
            geometry_index=105,
            filled_wv=Decimal("0.7"),
            tick_size=Decimal("0.01"),
            rr=Decimal("1"),
        )
        self.assertEqual(plan.request.side, OrderSide.SELL)
        self.assertEqual(plan.request.limit_price, Decimal("92.48"))
        self.assertEqual(plan.request.volume.amount, Decimal("0.3"))

    def test_topup_is_forbidden_at_apex_or_poor_rr(self):
        with self.assertRaisesRegex(RobotPartialFillError, "at or after apex"):
            build_topup_limit(
                _candidate(), _state(), geometry_index=110,
                filled_wv=Decimal("0.5"), tick_size=Decimal("0.01"), rr=Decimal("2"),
            )
        with self.assertRaisesRegex(RobotPartialFillError, "RR >= 1"):
            build_topup_limit(
                _candidate(), _state(), geometry_index=105,
                filled_wv=Decimal("0.5"), tick_size=Decimal("0.01"), rr=Decimal("0.9"),
            )

    def test_topup_action_id_is_stable_and_changes_with_reprice_slot(self):
        first = build_topup_limit(
            _candidate(), _state(), geometry_index=105,
            filled_wv=Decimal("0.5"), tick_size=Decimal("0.01"), rr=Decimal("1"),
        )
        second = build_topup_limit(
            _candidate(), _state(), geometry_index=105,
            filled_wv=Decimal("0.5"), tick_size=Decimal("0.01"), rr=Decimal("1"),
        )
        later = build_topup_limit(
            _candidate(), _state(), geometry_index=110 - 1,
            filled_wv=Decimal("0.5"), tick_size=Decimal("0.01"), rr=Decimal("1"),
        )
        self.assertEqual(first.request.client_action_id, second.request.client_action_id)
        self.assertNotEqual(first.request.client_action_id, later.request.client_action_id)


if __name__ == "__main__":
    unittest.main()
