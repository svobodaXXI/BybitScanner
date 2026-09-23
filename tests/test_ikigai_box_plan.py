"""Focused planner arithmetic/rejections; no runtime, network or order fixtures."""

from dataclasses import FrozenInstanceError
from decimal import Decimal as D
import unittest

from terminal.paper.ikigai_box_plan import plan_ikigai_box, plan_approved_first_ikigai_box


def inputs(direction="LONG"):
    return dict(
        direction=direction,
        limit_prices=tuple(map(D, ("94", "93", "92", "91") if direction == "LONG"
                              else ("106", "107", "108", "109"))),
        limit_quantities=(D("2"),) * 4, working_quantity=D("8"),
        frozen_f1=D("100"), frozen_f1618=D("92" if direction == "LONG" else "108"),
        tick_size=D("0.01"), entry_fee_rate=D("0"),
        target_fee_rate=D("0"), stop_fee_rate=D("0"),
    )


class IkigaiBoxPaperPlanTests(unittest.TestCase):
    def test_approved_first_grid_equal_spacing_and_common_take_risk(self):
        for direction, levels, take, stop in (
            ("LONG", ("94", "93.2", "92.4", "91.6"), "99.2", "89.6"),
            ("SHORT", ("106", "106.8", "107.6", "108.4"), "100.8", "110.4"),
        ):
            with self.subTest(direction=direction):
                args = inputs(direction)
                args.pop("limit_prices")
                args.pop("limit_quantities")
                plan = plan_approved_first_ikigai_box(**args)
                self.assertEqual(plan.limit_prices, tuple(map(D, levels)))
                self.assertEqual(plan.take_price, D(take))
                self.assertEqual(plan.grid_spacing, D("0.8"))
                self.assertEqual(plan.stop_price, D(stop))
                self.assertEqual(plan.full_position.reward_risk, D("2"))
                self.assertEqual(plan.limit_quantities, (D("2"),) * 4)
                self.assertFalse(plan.execution_authorized)
                self.assertEqual(
                    (plan.limit_prices[2] + plan.limit_prices[3]) / 2,
                    args["frozen_f1618"],
                )

    def test_approved_first_grid_fails_closed_if_tick_breaks_spacing(self):
        args = inputs()
        args.pop("limit_prices")
        args.pop("limit_quantities")
        args["tick_size"] = D("1")
        with self.assertRaisesRegex(ValueError, "tick-aligned"):
            plan_approved_first_ikigai_box(**args)

    def test_mirrored_full_grid_average_and_exact_two_to_one_stop(self):
        for direction, average, stop in (("LONG", "92.5", "88.75"),
                                         ("SHORT", "107.5", "111.25")):
            with self.subTest(direction=direction):
                args = inputs(direction)
                plan = plan_ikigai_box(**args)
                self.assertEqual(plan.full_position.average_entry, D(average))
                self.assertEqual(plan.full_position.quantity, D("8"))
                self.assertEqual(plan.full_position.net_target_profit, D("60"))
                self.assertEqual(plan.full_position.net_stop_loss, D("30"))
                self.assertEqual(plan.full_position.reward_risk, D("2"))
                self.assertEqual(plan.stop_price, D(stop))
                self.assertEqual(plan.grid_spacing, D("1"))
                self.assertEqual(plan.frozen_f1, D("100"))
                self.assertEqual(plan.limit_prices, args["limit_prices"])
                self.assertEqual(plan.environment, "PAPER")
                self.assertFalse(plan.execution_authorized)

    def test_distinct_fees_and_inward_tick_rounding(self):
        for direction, stop, reward, loss in (
            ("LONG", "89.26", "57.66", "28.80224"),
            ("SHORT", "110.65", "57.54", "28.71560"),
        ):
            with self.subTest(direction=direction):
                args = inputs(direction)
                args.update(entry_fee_rate=D("0.001"), target_fee_rate=D("0.002"),
                            stop_fee_rate=D("0.003"))
                plan = plan_ikigai_box(**args)
                self.assertEqual(plan.stop_price, D(stop))
                self.assertEqual(plan.full_position.net_target_profit, D(reward))
                self.assertEqual(plan.full_position.net_stop_loss, D(loss))
                self.assertGreaterEqual(plan.full_position.reward_risk, D("2"))
                # One more adverse tick exceeds the independently stated budget.
                sign = D(1 if direction == "LONG" else -1)
                farther = plan.stop_price - sign * args["tick_size"]
                e = plan.full_position.average_entry
                farther_loss = D(8) * (sign * (e - farther) + e * D("0.001")
                                      + farther * D("0.003"))
                self.assertGreater(farther_loss * 2, D(reward))

    def test_structural_stop_is_preferred_only_when_valid(self):
        for direction, valid, outside, inside in (("LONG", "90", "87", "92"),
                                                  ("SHORT", "110", "113", "108")):
            with self.subTest(direction=direction):
                args = inputs(direction)
                preferred = plan_ikigai_box(**args, structural_stop=D(valid))
                self.assertEqual(preferred.stop_price, D(valid))
                self.assertEqual(preferred.stop_basis, "STRUCTURAL")
                default = plan_ikigai_box(**args)
                for invalid in (outside, inside, "90.001"):
                    fallback = plan_ikigai_box(**args, structural_stop=D(invalid))
                    self.assertEqual(fallback.stop_price, default.stop_price)
                    self.assertEqual(fallback.stop_basis, "FULL_GRID_RR_CAP")

    def test_fixed_price_partial_risk_is_not_full_grid_rr(self):
        plan = plan_ikigai_box(**inputs())
        self.assertEqual(plan.slices[0].net_stop_loss, D("10.50"))
        self.assertLess(plan.minimum_partial_fill_rr, D("2"))
        self.assertEqual(plan.minimum_partial_fill_rr, plan.slices[0].reward_risk)
        self.assertEqual(plan.partial_fill_loss_upper_bound, D("30"))
        self.assertEqual(sum(s.net_target_profit for s in plan.slices), D("60"))
        with self.assertRaises(FrozenInstanceError):
            plan.stop_price = D("90")

    def test_rejects_no_affordable_tick_strictly_beyond_fourth(self):
        for direction, prices in (("LONG", ("94", "90", "86", "82")),
                                  ("SHORT", ("106", "110", "114", "118"))):
            with self.subTest(direction=direction):
                args = inputs(direction)
                args["limit_prices"] = tuple(map(D, prices))
                # The exact 2:1 boundary equals P4, which is not beyond it.
                with self.assertRaisesRegex(ValueError, "beyond P4"):
                    plan_ikigai_box(**args)
        args = inputs()
        args.update(tick_size=D("1"), entry_fee_rate=D("0.01"),
                    target_fee_rate=D("0.01"), stop_fee_rate=D("0.005"))
        with self.assertRaisesRegex(ValueError, "beyond P4"):
            plan_ikigai_box(**args)

    def test_tick_normalized_first_anchor_preserves_proposed_grid(self):
        for direction, level, prices in (
            ("LONG", "92.01", ("94", "93", "92", "91")),
            ("SHORT", "107.99", ("106", "107", "108", "109")),
        ):
            with self.subTest(direction=direction):
                args = inputs(direction)
                args.update(frozen_f1618=D(level), tick_size=D("1"))
                plan = plan_ikigai_box(**args)
                self.assertEqual(plan.limit_prices, tuple(map(D, prices)))
                self.assertGreaterEqual(plan.full_position.reward_risk, D("2"))

    def test_rejects_invalid_or_unspecified_grid_inputs(self):
        cases = (
            {"direction": "LIVE"},
            {"limit_prices": (D("94"),) * 3},
            {"limit_quantities": (D("2"),) * 3},
            {"limit_prices": tuple(map(D, ("94", "93", "92", "90")))},
            {"limit_prices": tuple(map(D, ("94", "95", "96", "97")))},
            {"limit_prices": tuple(map(D, ("94", "94", "94", "94")))},
            {"limit_prices": tuple(map(D, ("95", "94", "93", "92")))},
            {"limit_prices": tuple(map(D, ("94", "93.5", "93", "92.5")))},
            {"limit_prices": tuple(map(D, ("94", "93.333", "92.666", "91.999")))},
            {"limit_quantities": tuple(map(D, ("1", "2", "2", "3")))},
            {"working_quantity": D("4")},
            {"frozen_f1618": D("108")},
            {"entry_fee_rate": D("0.1")},
        )
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                plan_ikigai_box(**(inputs() | change))
        for name in ("tick_size", "working_quantity", "frozen_f1", "frozen_f1618",
                     "structural_stop"):
            for value in (None, D("NaN"), D("Infinity"), D("0"), D("-1"), True, 1.0):
                if name == "structural_stop" and value is None:
                    continue
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    plan_ikigai_box(**(inputs() | {name: value}))
        for name in ("limit_prices", "limit_quantities"):
            for value in (D("NaN"), D("Infinity"), D("0"), D("-1"), True, 1.0):
                args = inputs()
                args[name] = (value,) + args[name][1:]
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    plan_ikigai_box(**args)
        for name in ("entry_fee_rate", "target_fee_rate", "stop_fee_rate"):
            for value in (None, D("NaN"), D("Infinity"), D("-0.001"), D("1"), 0.0):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    plan_ikigai_box(**(inputs() | {name: value}))
        for name in ("limit_prices", "limit_quantities", "working_quantity", "frozen_f1",
                     "frozen_f1618", "tick_size", "entry_fee_rate", "target_fee_rate",
                     "stop_fee_rate"):
            missing = inputs()
            del missing[name]
            with self.subTest(name=name), self.assertRaises(TypeError):
                plan_ikigai_box(**missing)


if __name__ == "__main__":
    unittest.main()
