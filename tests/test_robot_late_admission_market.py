from decimal import Decimal
import unittest

import robot_state_machine
from terminal.api.models import VolumeUnit
from terminal.application.robot_admission_catchup import LATE_ADMISSION_MARKET
from terminal.application.robot_late_admission_market import (
    LATE_ADMISSION_MARKET_WV,
    LATE_ADMISSION_SLIPPAGE_PERCENT,
    LATE_ADMISSION_SLIPPAGE_TYPE,
    RobotLateAdmissionMarketError,
    build_late_admission_market_plan,
    durable_late_admission_market_intent,
    restore_late_admission_market_plan,
)
from terminal.domain.models import OrderSide, Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel


SYMBOL = "TESTUSDT"


def _candidate(pattern="Falling Wedge"):
    return {
        "candidate_id": "candidate-1",
        "status": "APPROVED",
        "timeframe": "1",
        "signal_snapshot": {
            "symbol": SYMBOL,
            "pattern": pattern,
        },
    }


def _state(direction=robot_state_machine.DIRECTION_LONG):
    return {
        "phase": robot_state_machine.PHASE_RETEST_DETECTED,
        "direction": direction,
        "execution": {"entry_mode": LATE_ADMISSION_MARKET},
    }


def _book(*, health=BookHealth.READY, symbol=SYMBOL):
    return NormalizedOrderBook(
        symbol=Symbol(symbol),
        bids=(
            PriceLevel(Price(Decimal("99")), Quantity(Decimal("10"))),
            PriceLevel(Price(Decimal("98")), Quantity(Decimal("10"))),
        ),
        asks=(
            PriceLevel(Price(Decimal("101")), Quantity(Decimal("10"))),
            PriceLevel(Price(Decimal("102")), Quantity(Decimal("10"))),
        ),
        health=health,
        received_at_ms=1000,
        available_depth=2,
    )


def _durable_intent(plan):
    return durable_late_admission_market_intent(
        plan,
        normalized_quantity=Decimal("2.4"),
        current_geometry_index=105,
        projected_vwap=Decimal("101.25"),
        stop_price=Decimal("99"),
        take_price=Decimal("106"),
        expected_reward=Decimal("0.0469"),
        rr=Decimal("2.1"),
        adverse_slippage=Decimal("0.0025"),
        persisted_at_ms=1234,
    )


class RobotLateAdmissionMarketPlanTests(unittest.TestCase):
    def test_long_plan_uses_one_wv_best_ask_and_bybit_half_percent_slippage(self):
        plan = build_late_admission_market_plan(_candidate(), _state(), _book())

        self.assertEqual(plan.request.side, OrderSide.BUY)
        self.assertEqual(plan.best_price, Decimal("101"))
        self.assertEqual(plan.request.sizing_reference_price, Decimal("101"))
        self.assertEqual(plan.request.volume.unit, VolumeUnit.WORKING_VOLUME)
        self.assertEqual(plan.request.volume.amount, LATE_ADMISSION_MARKET_WV)
        self.assertEqual(plan.request.slippage_type, LATE_ADMISSION_SLIPPAGE_TYPE)
        self.assertEqual(plan.request.slippage_value, LATE_ADMISSION_SLIPPAGE_PERCENT)
        self.assertEqual(LATE_ADMISSION_MARKET_WV, Decimal("1"))
        self.assertEqual(LATE_ADMISSION_SLIPPAGE_TYPE, "Percent")
        self.assertEqual(LATE_ADMISSION_SLIPPAGE_PERCENT, Decimal("0.5"))

    def test_short_plan_uses_best_bid(self):
        plan = build_late_admission_market_plan(
            _candidate("Rising Wedge"),
            _state(robot_state_machine.DIRECTION_SHORT),
            _book(),
        )

        self.assertEqual(plan.request.side, OrderSide.SELL)
        self.assertEqual(plan.best_price, Decimal("99"))
        self.assertEqual(plan.request.sizing_reference_price, Decimal("99"))

    def test_same_candidate_has_stable_action_command_and_order_link_identity(self):
        first = build_late_admission_market_plan(_candidate(), _state(), _book())
        second = build_late_admission_market_plan(_candidate(), _state(), _book())

        self.assertEqual(first.request.client_action_id, second.request.client_action_id)
        self.assertEqual(first.identity, second.identity)
        self.assertEqual(first.identity.command_id.value, second.identity.command_id.value)
        self.assertEqual(first.identity.order_link_id, second.identity.order_link_id)
        self.assertEqual(len(first.identity.order_link_id), 36)
        self.assertTrue(first.identity.order_link_id.startswith("tw_"))

    def test_identity_stays_stable_when_best_price_changes(self):
        first = build_late_admission_market_plan(_candidate(), _state(), _book())
        changed = NormalizedOrderBook(
            symbol=Symbol(SYMBOL),
            bids=(PriceLevel(Price(Decimal("100")), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(Decimal("103")), Quantity(Decimal("10"))),),
            health=BookHealth.READY,
            received_at_ms=2000,
            available_depth=1,
        )
        second = build_late_admission_market_plan(_candidate(), _state(), changed)

        self.assertNotEqual(first.request.sizing_reference_price, second.request.sizing_reference_price)
        self.assertEqual(first.request.client_action_id, second.request.client_action_id)
        self.assertEqual(first.identity, second.identity)

    def test_durable_intent_restores_exact_request_and_identity(self):
        plan = build_late_admission_market_plan(_candidate(), _state(), _book())
        intent = _durable_intent(plan)
        restored = restore_late_admission_market_plan(intent)

        self.assertEqual(restored, plan)
        self.assertEqual(intent["normalized_quantity"], "2.4")
        self.assertEqual(intent["geometry_index"], 105)
        self.assertEqual(intent["projected_vwap"], "101.25")
        self.assertEqual(intent["persisted_at_ms"], 1234)

    def test_durable_intent_rejects_changed_stable_identity(self):
        plan = build_late_admission_market_plan(_candidate(), _state(), _book())
        intent = _durable_intent(plan)
        intent["order_link_id"] = "tw_changed"

        with self.assertRaisesRegex(RobotLateAdmissionMarketError, "order_link_id changed"):
            restore_late_admission_market_plan(intent)

    def test_rejects_non_late_state_and_non_ready_or_mismatched_book(self):
        ordinary = _state()
        ordinary["execution"] = {}
        with self.assertRaisesRegex(RobotLateAdmissionMarketError, "marker"):
            build_late_admission_market_plan(_candidate(), ordinary, _book())

        with self.assertRaisesRegex(RobotLateAdmissionMarketError, "READY"):
            build_late_admission_market_plan(
                _candidate(), _state(), _book(health=BookHealth.STALE),
            )

        with self.assertRaisesRegex(RobotLateAdmissionMarketError, "READY"):
            build_late_admission_market_plan(
                _candidate(), _state(), _book(symbol="OTHERUSDT"),
            )


if __name__ == "__main__":
    unittest.main()
