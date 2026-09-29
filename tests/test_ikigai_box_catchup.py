from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from terminal.application.ikigai_box_catchup import (
    build_box_exit_specs,
    build_box_market_plans,
    classify_box_catchup_slots,
    durable_box_market_intent,
    restore_box_market_plan,
)
from terminal.domain.models import Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_box_plan_persistence import snapshot


def _book(price: str) -> NormalizedOrderBook:
    value = Decimal(price)
    return NormalizedOrderBook(
        symbol=Symbol("BTCUSDT"),
        bids=(PriceLevel(Price(value), Quantity(Decimal("100"))),),
        asks=(PriceLevel(Price(value), Quantity(Decimal("100"))),),
        health=BookHealth.READY,
        received_at_ms=1,
        available_depth=1,
    )


class BoxCatchupPlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SQLiteStore.open(Path(self.tmp.name) / "paper.sqlite3")
        self.addCleanup(self.store.close)
        self.source, _ = self.store.save_box_plan_only(
            snapshot=snapshot(), created_at_ms=3001,
        )

    def test_long_classifies_zero_to_four_crossed_slots(self):
        expected = {
            "95": 0,
            "93.5": 1,
            "92.8": 2,
            "92.0": 3,
            "91.0": 4,
        }
        for executable, market_count in expected.items():
            with self.subTest(executable=executable):
                slots = classify_box_catchup_slots(self.source, _book(executable))
                self.assertEqual(
                    sum(slot.entry_mode == "MARKET" for slot in slots),
                    market_count,
                )
                self.assertEqual(
                    [slot.slot for slot in slots],
                    [1, 2, 3, 4],
                )
                self.assertEqual(
                    [slot.quantity for slot in slots],
                    [Decimal("2")] * 4,
                )

    def test_short_mirrors_crossed_slot_classification(self):
        data = snapshot()
        data["identity"]["direction"] = "SHORT"
        data["anchors"] = {"a_price": "90", "b_price": "100"}
        data["fibonacci"] = {"f1": "100", "f1618": "108", "f2618": "120"}
        data["plan"]["direction"] = "SHORT"
        data["plan"]["limit_prices"] = ["106", "106.8", "107.6", "108.4"]
        data["plan"]["take_price"] = "100.8"
        data["plan"]["stop_price"] = "110.4"
        data["plan"]["full_position"]["average_entry"] = "107.2"
        short, _ = self.store.save_box_plan_only(snapshot=data, created_at_ms=3002)

        expected = {
            "105": 0,
            "106.4": 1,
            "107.0": 2,
            "108.0": 3,
            "109.0": 4,
        }
        for executable, market_count in expected.items():
            with self.subTest(executable=executable):
                slots = classify_box_catchup_slots(short, _book(executable))
                self.assertEqual(
                    sum(slot.entry_mode == "MARKET" for slot in slots),
                    market_count,
                )

    def test_market_plans_preserve_slot_quantity_by_notional_identity(self):
        plans = build_box_market_plans(
            self.source, _book("92.8"), slots=(1, 2),
        )
        self.assertEqual([plan.slot for plan in plans], [1, 2])
        self.assertEqual([plan.quantity for plan in plans], [Decimal("2")] * 2)
        self.assertEqual([plan.best_price for plan in plans], [Decimal("92.8")] * 2)
        self.assertEqual(
            [plan.request.volume.amount for plan in plans],
            [Decimal("185.6")] * 2,
        )
        self.assertEqual(
            [plan.request.volume.unit.value for plan in plans],
            ["usdt", "usdt"],
        )
        self.assertEqual([plan.request.side.value for plan in plans], ["Buy", "Buy"])
        self.assertEqual(len({plan.request.client_action_id.value for plan in plans}), 2)
        self.assertEqual(len({plan.identity.command_id.value for plan in plans}), 2)

    def test_market_intent_round_trips_exact_request_identity(self):
        plan = build_box_market_plans(
            self.source, _book("92.8"), slots=(1,),
        )[0]
        intent = durable_box_market_intent(plan)
        self.assertEqual(restore_box_market_plan(intent), plan)
        changed = dict(intent)
        changed["volume_amount"] = "1"
        with self.assertRaisesRegex(ValueError, "changed"):
            restore_box_market_plan(changed)

    def test_market_plan_rejects_uncrossed_slot(self):
        with self.assertRaisesRegex(ValueError, "uncrossed"):
            build_box_market_plans(self.source, _book("93.5"), slots=(2,))

    def test_exit_specs_are_per_slot_but_share_frozen_take(self):
        specs = build_box_exit_specs(
            self.source, slots=(1, 3, 4), created_at_ms=5000,
        )
        self.assertEqual([spec.slot for spec in specs], [1, 3, 4])
        self.assertEqual([spec.price for spec in specs], [Decimal("99.2")] * 3)
        self.assertEqual([spec.quantity for spec in specs], [Decimal("2")] * 3)
        self.assertEqual(len({spec.order_id.value for spec in specs}), 3)
        self.assertEqual(len({spec.client_action_id for spec in specs}), 3)
        self.assertEqual([spec.side.value for spec in specs], ["Sell"] * 3)

    def test_exit_specs_are_deterministic_and_deduplicate_requested_slots(self):
        first = build_box_exit_specs(
            self.source, slots=(4, 2, 2), created_at_ms=7000,
        )
        second = build_box_exit_specs(
            self.source, slots=(2, 4), created_at_ms=7000,
        )
        self.assertEqual(first, second)
        self.assertEqual([spec.slot for spec in first], [2, 4])


if __name__ == "__main__":
    unittest.main()
