"""Original Robot Wedge STOP/TAKE/RR gates reused for risk-only SIMULATION previews."""
import os
import unittest
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch

from robot_entry_limit import build_initial_retest_limit
from robot_state_machine import PHASE_RETEST_DETECTED
from research.simulator_v2.wedge_risk_preflight import (
    FrozenWedgeRiskEvidence, SimWedgeRiskSettings,
    WedgePreflightBlocked, preview_protected_wedge_limit,
)


def original_plan(pattern="Falling Wedge"):
    short = pattern == "Rising Wedge"
    candidate = {
        "candidate_id": "original-cid",
        "status": "APPROVED",
        "timeframe": "1",
        "signal_snapshot": {
            "symbol": "BTCUSDT", "pattern": pattern,
            "geometry": {
                "upper_line": {"slope": 0, "intercept": 105 if short else 100},
                "lower_line": {"slope": 0, "intercept": 100 if short else 95},
                "apex": {"index": 150, "valid_intersection": True},
                "current_index": 50,
            },
        },
    }
    state = {
        "direction": "SHORT" if short else "LONG",
        "phase": PHASE_RETEST_DETECTED,
        "breakout_index": 51,
        "retest_index": 52,
    }
    return build_initial_retest_limit(candidate, state, tick_size=D("0.01"))


def original_evidence(pattern="Falling Wedge"):
    short = pattern == "Rising Wedge"
    return FrozenWedgeRiskEvidence(
        candidate_id="original-cid", symbol="BTCUSDT", pattern=pattern,
        observed_at_ms=60_000, structural_extreme=D("100.40") if short else D("99.50"),
        frozen_signal_reference_price=D("100"),
        frozen_scanner_target_price=D("95") if short else D("105"),
    )


def config():
    return SimWedgeRiskSettings(
        tick_size=D("0.01"),
        contracts_per_working_volume=D("1.0"),
        quantity_step=D("0.01"), minimum_quantity=D("0.01"),
        max_notional_usdt=D("200"), max_risk_usdt=D("5"),
        entry_fee_rate=D("0.0006"), exit_fee_rate=D("0.0006"),
    )


class NativeWedgeRiskPreflightTests(unittest.TestCase):
    def test_long_and_short_use_original_robot_stop_take_and_fee_aware_rr(self):
        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": "1.5"}):
            for pattern, side, entry, stop, take in (
                ("Falling Wedge", "BUY", D("100.02"), D("99.49"), D("104.50")),
                ("Rising Wedge", "SELL", D("99.98"), D("100.41"), D("95.50")),
            ):
                with self.subTest(pattern=pattern):
                    preview = preview_protected_wedge_limit(
                        original_plan(pattern), evidence=original_evidence(pattern),
                        settings=config(), retest_closed_at_ms=120_000,
                    )
                    self.assertEqual(preview.status, "PREVIEW_ONLY")
                    self.assertEqual(preview.request.namespace, "SIMULATION")
                    self.assertEqual(preview.request.side, side)
                    self.assertEqual(preview.request.limit_price, entry)
                    self.assertEqual(preview.request.quantity, D("1.0"))
                    self.assertEqual(preview.stop_price, stop)
                    self.assertEqual(preview.take_price, take)
                    self.assertGreater(preview.projected_net_rr, D("1.5"))
                    self.assertLess(preview.worst_case_loss_usdt, D("5"))
                    self.assertEqual(preview.minimum_rr, D("1.5"))

    def test_owner_1point5_policy_is_shared_not_invented_for_simulation(self):
        from robot_protection import WEDGE_MIN_ENTRY_RR, wedge_min_entry_rr
        from terminal.application.robot_late_admission import MIN_LATE_ADMISSION_RR
        self.assertEqual(WEDGE_MIN_ENTRY_RR, D("1.5"))
        self.assertEqual(MIN_LATE_ADMISSION_RR, D("1.5"))
        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": "10"}):
            self.assertEqual(wedge_min_entry_rr(), D("10"))
            with self.assertRaisesRegex(WedgePreflightBlocked, "below current"):
                preview_protected_wedge_limit(
                    original_plan(), evidence=original_evidence(),
                    settings=config(), retest_closed_at_ms=120_000,
                )

    def test_requires_frozen_scanner_target_not_made_up_from_future_candles(self):
        plan = original_plan()
        with self.assertRaisesRegex(WedgePreflightBlocked, "frozen Scanner"):
            preview_protected_wedge_limit(
                plan, evidence=None, settings=config(), retest_closed_at_ms=120_000,
            )
        with self.assertRaisesRegex(WedgePreflightBlocked, "settings"):
            preview_protected_wedge_limit(
                plan, evidence=original_evidence(), settings=None,
                retest_closed_at_ms=120_000,
            )
        with self.assertRaisesRegex(WedgePreflightBlocked, "after retest"):
            preview_protected_wedge_limit(
                plan, evidence=original_evidence(), settings=config(),
                retest_closed_at_ms=59_999,
            )
        with self.assertRaisesRegex(WedgePreflightBlocked, "identity"):
            preview_protected_wedge_limit(
                plan, evidence=replace(original_evidence(), candidate_id="other"),
                settings=config(), retest_closed_at_ms=120_000,
            )
        with self.assertRaisesRegex(WedgePreflightBlocked, "direction differs"):
            preview_protected_wedge_limit(
                plan, evidence=replace(original_evidence(), pattern="Rising Wedge"),
                settings=config(), retest_closed_at_ms=120_000,
            )

    def test_risk_budget_and_quantity_normalization_are_fail_closed(self):
        with self.assertRaisesRegex(WedgePreflightBlocked, "risk budget"):
            preview_protected_wedge_limit(
                original_plan(), evidence=original_evidence(),
                settings=replace(config(), max_risk_usdt=D("0.1")),
                retest_closed_at_ms=120_000,
            )
        with self.assertRaisesRegex(WedgePreflightBlocked, "notional"):
            preview_protected_wedge_limit(
                original_plan(), evidence=original_evidence(),
                settings=replace(config(), max_notional_usdt=D("90")),
                retest_closed_at_ms=120_000,
            )
        with self.assertRaisesRegex(WedgePreflightBlocked, "contract quantity"):
            preview_protected_wedge_limit(
                original_plan(), evidence=original_evidence(),
                settings=replace(config(), contracts_per_working_volume=D("0.155")),
                retest_closed_at_ms=120_000,
            )
        with self.assertRaisesRegex(WedgePreflightBlocked, "positive"):
            replace(config(), contracts_per_working_volume=D("NaN"))

    def test_insufficient_reward_is_not_a_trade_even_with_valid_structure(self):
        evidence = replace(original_evidence(), frozen_scanner_target_price=D("100.5"))
        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": "1.5"}):
            with self.assertRaisesRegex(WedgePreflightBlocked, "below current"):
                preview_protected_wedge_limit(
                    original_plan(), evidence=evidence, settings=config(),
                    retest_closed_at_ms=120_000,
                )


if __name__ == "__main__":
    unittest.main()
