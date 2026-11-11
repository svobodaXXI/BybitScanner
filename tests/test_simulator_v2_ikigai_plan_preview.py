"""Native Box P1–P4 preview, separately scoped M1/M5, no orders."""
import unittest
from dataclasses import replace
from unittest.mock import patch
from decimal import Decimal as D

from geometry.ikigai_box import IkigaiBoxFormation
from research.simulator_v2.ikigai_observer import IkigaiObservation
from research.simulator_v2.ikigai_plan_preview import (
    BoxSimulationRiskTerms, preview_box_plan,
)


def terms():
    return BoxSimulationRiskTerms(
        tick_size=D("0.01"), working_quantity=D("8"),
        quantity_step=D("1"), minimum_quantity=D("1"),
        maximum_notional_usdt=D("1000"), maximum_loss_usdt=D("300"),
        entry_fee_rate=D("0"), exit_fee_rate=D("0"),
        adverse_stop_slippage_per_unit=D("0"),
        additional_cost_allowance_usdt=D("0"),
    )


def signal(tf):
    formation = IkigaiBoxFormation(
        direction="LONG", impulse_start_index=1, impulse_end_index=2,
        box_start_index=3, box_end_index=7, second_start_index=8,
        as_of_index=9, anchor_start_index=1, anchor_end_index=2,
        anchor_start_price=112.94498381877023, anchor_end_price=100.,
        box_low=100., box_high=108., second_extreme=91.,
        fibonacci_1_0=100., fibonacci_1_618=92.,
        fibonacci_2_618=79.05501618122977,
    )
    return IkigaiObservation(
        "test", "BTCUSDT", tf, 900_000, f"{tf}:LONG:120000:180000",
        formation, 120_000, 180_000,
    )


class NativeBoxPreviewTests(unittest.TestCase):
    def test_four_original_limits_both_timeframes(self):
        for tf in ("1m", "5m"):
            with self.subTest(tf=tf):
                preview = preview_box_plan(signal(tf), terms=terms())
                self.assertEqual(preview.status, "PREVIEW_ONLY")
                self.assertEqual(preview.timeframe, tf)
                self.assertEqual(preview.plan.limit_prices,
                                 tuple(map(D, ("94", "93.2", "92.4", "91.6"))))
                self.assertEqual(preview.plan.take_price, D("99.2"))
                self.assertEqual(preview.plan.stop_price, D("89.6"))
                self.assertFalse(preview.plan.execution_authorized)
                self.assertTrue(preview.risk.allowed)

    def test_missing_original_robot_box_planner_never_falls_back(self):
        with patch(
            "research.simulator_v2.ikigai_plan_preview.plan_approved_first_ikigai_box",
            side_effect=RuntimeError("original Box planner unavailable"),
        ) as original:
            for tf in ("1m", "5m"):
                with self.subTest(timeframe=tf):
                    with self.assertRaisesRegex(RuntimeError, "original Box planner unavailable"):
                        preview_box_plan(signal(tf), terms=terms())
        self.assertEqual(original.call_count, 2)

    def test_risk_and_signal_provenance_fail_closed(self):
        for invalid in (
            replace(terms(), maximum_loss_usdt=D("0.01")),
            replace(terms(), maximum_notional_usdt=D("1")),
            replace(terms(), quantity_step=D("3")),
        ):
            with self.assertRaises(ValueError):
                preview_box_plan(signal("1m"), terms=invalid)
        with self.assertRaises(ValueError):
            preview_box_plan(replace(signal("1m"), timeframe="5m"),
                             terms=terms())


if __name__ == "__main__":
    unittest.main()
