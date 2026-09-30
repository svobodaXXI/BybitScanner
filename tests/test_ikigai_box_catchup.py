from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from terminal.application.ikigai_box_catchup import (
    BoxCatchupStopRejected,
    build_box_exit_specs,
    build_box_market_plans,
    classify_box_catchup_slots,
    durable_box_market_intent,
    plan_box_catchup,
    restore_box_market_plan,
    ready_box_exit_slots,
    translate_box_catchup_stop,
)
from terminal.application.ikigai_box_first_grid import build_box_first_grid_specs
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


def _short_snapshot():
    data = snapshot()
    data["identity"]["direction"] = "SHORT"
    data["anchors"] = {"a_price": "90", "b_price": "100"}
    data["fibonacci"] = {"f1": "100", "f1618": "108", "f2618": "120"}
    data["plan"]["direction"] = "SHORT"
    data["plan"]["frozen_f1618"] = "108"
    data["plan"]["limit_prices"] = ["106", "106.8", "107.6", "108.4"]
    data["plan"]["take_price"] = "100.8"
    data["plan"]["stop_price"] = "110.4"
    data["plan"]["full_position"]["average_entry"] = "107.2"
    return data


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
        short, _ = self.store.save_box_plan_only(snapshot=_short_snapshot(), created_at_ms=3002)

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

    def test_paired_exit_waits_for_full_slot_fill_and_is_idempotent_after_exit(self):
        class Proof:
            entry_by_slot = (
                Decimal("2"), Decimal("1"), Decimal("2"), Decimal("0"),
            )
            exit_by_slot = (
                Decimal("0"), Decimal("0"), Decimal("2"), Decimal("0"),
            )

        self.assertEqual(
            ready_box_exit_slots(self.source, Proof()),
            (1,),
        )

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


class BoxCatchupPlanAndStopTranslationTests(unittest.TestCase):
    """OFR-5 Slice A: frozen shared TAKE and actual-average STOP translation."""

    CASES = {
        # direction: (frozen P1..P4, TAKE, executable prices for 0..4 crossed)
        "LONG": (
            ["94", "93.2", "92.4", "91.6"], "99.2",
            ["95", "93.5", "92.8", "92.0", "91.0"],
        ),
        "SHORT": (
            ["106", "106.8", "107.6", "108.4"], "100.8",
            ["105", "106.4", "107.0", "108.0", "109.0"],
        ),
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SQLiteStore.open(Path(self.tmp.name) / "paper.sqlite3")
        self.addCleanup(self.store.close)
        self.sources = {
            "LONG": self.store.save_box_plan_only(snapshot=snapshot(), created_at_ms=3001)[0],
            "SHORT": self.store.save_box_plan_only(
                snapshot=_short_snapshot(), created_at_ms=3002,
            )[0],
        }

    def test_zero_to_four_crossed_slots_keep_identity_frozen_limits_and_shared_take(self):
        for direction, (prices, take, executables) in self.CASES.items():
            source = self.sources[direction]
            frozen = [Decimal(value) for value in prices]
            limit_specs = {
                spec.slot: spec
                for spec in build_box_first_grid_specs(source, created_at_ms=5000)
            }
            for crossed, executable in enumerate(executables):
                with self.subTest(direction=direction, crossed=crossed):
                    plan = plan_box_catchup(source, _book(executable))
                    self.assertEqual(plan.direction, direction)
                    self.assertEqual([item.slot for item in plan.slots], [1, 2, 3, 4])
                    self.assertEqual([item.quantity for item in plan.slots], [Decimal("2")] * 4)
                    self.assertEqual([item.planned_price for item in plan.slots], frozen)
                    self.assertEqual(plan.market_slots, tuple(range(1, crossed + 1)))
                    self.assertEqual(plan.limit_slots, tuple(range(crossed + 1, 5)))
                    self.assertEqual(plan.take_price, Decimal(take))
                    self.assertEqual(plan.stop_offset, Decimal("3.2"))

                    market = build_box_market_plans(
                        source, _book(executable), slots=plan.market_slots,
                    )
                    self.assertEqual([item.slot for item in market], list(plan.market_slots))
                    self.assertEqual([item.quantity for item in market], [Decimal("2")] * crossed)

                    exits = build_box_exit_specs(
                        source, slots=plan.market_slots, created_at_ms=5000,
                    )
                    self.assertEqual([item.price for item in exits], [Decimal(take)] * crossed)

                    for slot in plan.limit_slots:
                        self.assertEqual(limit_specs[slot].price, frozen[slot - 1])
                        self.assertEqual(limit_specs[slot].quantity, Decimal("2"))

    def _source_with_partial_floor(self, direction, floor):
        # The floor is read from the frozen plan, never invented at runtime;
        # this fixture only raises it so it binds inside the valid P4 range.
        data = snapshot() if direction == "LONG" else _short_snapshot()
        data["plan"]["minimum_partial_fill_rr"] = floor
        data["identity"]["a_time_ms"] = 1100  # distinct setup identity
        return self.store.save_box_plan_only(snapshot=data, created_at_ms=3100)[0]

    def test_stop_translates_frozen_offset_to_actual_average_and_rounds_outward(self):
        cases = [
            # direction, full-grid VWAP, raw translated STOP, tick-normalized STOP
            ("LONG", "92.8", "89.6", "89.6"),      # planned average -> frozen STOP
            ("LONG", "91.0", "87.8", "87.8"),      # all four caught at 91.0
            ("LONG", "92.555", "89.355", "89.35"),  # outward = down one tick
            ("SHORT", "107.2", "110.4", "110.4"),
            ("SHORT", "109.0", "112.2", "112.2"),
            ("SHORT", "107.445", "110.645", "110.65"),  # outward = up one tick
        ]
        for direction, average, raw, stop in cases:
            with self.subTest(direction=direction, average=average):
                result = translate_box_catchup_stop(
                    self.sources[direction],
                    actual_average_entry=Decimal(average),
                    filled_quantity=Decimal("8"),
                )
                self.assertEqual(result.stop_offset, Decimal("3.2"))
                self.assertEqual(result.raw_stop_price, Decimal(raw))
                self.assertEqual(result.stop_price, Decimal(stop))
                self.assertEqual(result.stop_price % Decimal("0.01"), 0)
                self.assertEqual(result.take_price, Decimal(self.CASES[direction][1]))
                self.assertEqual(result.minimum_rr, Decimal("2"))
                sign = Decimal(1 if direction == "LONG" else -1)
                displacement = sign * (result.raw_stop_price - result.stop_price)
                self.assertGreaterEqual(displacement, Decimal(0))
                self.assertLess(displacement, Decimal("0.01"))

    def test_full_fill_accepts_raw_rr_before_sub_tick_outward_rounding(self):
        cases = {
            "LONG": (("93.99", "93.2", "92.4", "91.6"), "89.5975", "89.59"),
            "SHORT": (("106.01", "106.8", "107.6", "108.4"), "110.4025", "110.41"),
        }
        for direction, (fills, raw_stop, normalized_stop) in cases.items():
            with self.subTest(direction=direction):
                vwap = sum(map(Decimal, fills), Decimal(0)) / Decimal(len(fills))
                result = translate_box_catchup_stop(
                    self.sources[direction],
                    actual_average_entry=vwap,
                    filled_quantity=Decimal("8"),
                )
                expected_vwap = "92.7975" if direction == "LONG" else "107.2025"
                self.assertEqual(vwap, Decimal(expected_vwap))
                self.assertEqual(result.raw_stop_price, Decimal(raw_stop))
                self.assertEqual(result.stop_price, Decimal(normalized_stop))
                self.assertEqual(result.minimum_rr, Decimal("2"))

                sign = Decimal(1 if direction == "LONG" else -1)
                executable_rr = (
                    sign * (result.take_price - result.actual_average_entry)
                    / (sign * (result.actual_average_entry - result.stop_price))
                )
                self.assertLess(executable_rr, Decimal("2"))
                self.assertEqual(
                    executable_rr.quantize(Decimal("0.0001")), Decimal("1.9961")
                )
                displacement = sign * (result.raw_stop_price - result.stop_price)
                self.assertGreaterEqual(displacement, Decimal(0))
                self.assertLess(displacement, Decimal("0.01"))

    def test_partial_fill_uses_frozen_partial_rr_floor_without_tightening(self):
        # P1 alone has net RR 5.2/3.2 = 1.625: below 2 but above the frozen
        # minimum_partial_fill_rr (1.1818...), so the translated STOP stands.
        cases = {"LONG": ("94", "90.8"), "SHORT": ("106", "109.2")}
        for direction, (vwap, stop) in cases.items():
            with self.subTest(direction=direction):
                result = translate_box_catchup_stop(
                    self.sources[direction],
                    actual_average_entry=Decimal(vwap),
                    filled_quantity=Decimal("2"),
                )
                self.assertEqual(result.stop_price, Decimal(stop))
                self.assertEqual(
                    result.minimum_rr, Decimal("1.181818181818181818181818182"),
                )

    def test_later_fill_retranslates_from_filled_vwap_and_may_widen_stop(self):
        # Two slots caught by MARKET, then the far P4 LIMIT fills. VWAP covers
        # only the filled owned exposure; unfilled P3 never contributes.
        cases = {
            "LONG": (["92.0", "92.0"], "91.6", "88.8", "88.66"),
            "SHORT": (["108.0", "108.0"], "108.4", "111.2", "111.34"),
        }
        for direction, (market_fills, p4_fill, first_stop, second_stop) in cases.items():
            with self.subTest(direction=direction):
                source = self.sources[direction]
                filled = [Decimal(price) for price in market_fills]
                first = translate_box_catchup_stop(
                    source,
                    actual_average_entry=sum(filled) / len(filled),
                    filled_quantity=Decimal("2") * len(filled),
                )
                filled.append(Decimal(p4_fill))
                second = translate_box_catchup_stop(
                    source,
                    actual_average_entry=sum(filled) / len(filled),
                    filled_quantity=Decimal("2") * len(filled),
                )
                self.assertEqual(first.stop_price, Decimal(first_stop))
                self.assertEqual(second.stop_price, Decimal(second_stop))
                self.assertEqual(second.stop_offset, first.stop_offset)
                self.assertEqual(second.take_price, first.take_price)
                sign = 1 if direction == "LONG" else -1
                # Absolute STOP moved farther from market: intentional widening.
                self.assertGreater(sign * (first.stop_price - second.stop_price), 0)

    def test_invalid_translated_stop_fails_closed(self):
        cases = [
            # Full four-slot quantity keeps net RR >= 2: 5.2/3.2 fails.
            (self.sources["LONG"], "94", "8", "RR >= 2"),
            (self.sources["SHORT"], "106", "8", "RR >= 2"),
            # Partial exposure below the frozen partial-fill floor (1.625 < 1.7).
            (self._source_with_partial_floor("LONG", "1.7"), "94", "2", "RR >= 1.7"),
            (self._source_with_partial_floor("SHORT", "1.7"), "106", "2", "RR >= 1.7"),
            # Translated STOP no longer strictly beyond P4.
            (self.sources["LONG"], "95", "2", "P4"),
            (self.sources["SHORT"], "105", "2", "P4"),
            # Average on the profit side of the frozen TAKE.
            (self.sources["LONG"], "99.2", "2", "TAKE"),
            (self.sources["SHORT"], "100.8", "2", "TAKE"),
        ]
        for source, average, quantity, reason in cases:
            with self.subTest(direction=source.signal_snapshot["plan"]["direction"],
                              average=average, quantity=quantity):
                with self.assertRaisesRegex(BoxCatchupStopRejected, reason):
                    translate_box_catchup_stop(
                        source,
                        actual_average_entry=Decimal(average),
                        filled_quantity=Decimal(quantity),
                    )
        with self.assertRaisesRegex(ValueError, "exceeds the frozen grid"):
            translate_box_catchup_stop(
                self.sources["LONG"],
                actual_average_entry=Decimal("92.8"),
                filled_quantity=Decimal("10"),
            )
        with self.assertRaisesRegex(BoxCatchupStopRejected, "not positive"):
            translate_box_catchup_stop(
                self.sources["LONG"],
                actual_average_entry=Decimal("3.2"),
                filled_quantity=Decimal("2"),
            )


if __name__ == "__main__":
    unittest.main()
