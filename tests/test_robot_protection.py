from decimal import Decimal
import os
import unittest
from unittest.mock import patch

from robot_protection import (
    PROTECTION_DEADLINE_MS,
    RECOVERY_CLOSED,
    RECOVERY_EMERGENCY_CLOSE,
    RECOVERY_EMERGENCY_CLOSE_PENDING,
    RECOVERY_PROTECTED,
    RECOVERY_TAKE_ONLY,
    RECOVERY_WAIT,
    build_protection_plan,
    frozen_take_90,
    protection_recovery,
    structural_stop,
    submit_emergency_close,
    submit_initial_protection,
    tighten_stop,
)
from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT


def _candidate(pattern="Falling Wedge"):
    return {
        "candidate_id": "candidate-1",
        "status": "APPROVED",
        "timeframe": "1",
        "signal_snapshot": {"symbol": "TESTUSDT", "pattern": pattern},
    }


class _Submitter:
    def __init__(self):
        self.calls = []

    def create_stop(self, request):
        self.calls.append(("create_stop", request))
        return "stop"

    def amend_stop(self, request):
        self.calls.append(("amend_stop", request))
        return "stop-amend"

    def create_take(self, request):
        self.calls.append(("create_take", request))
        return "take"

    def amend_take(self, request):
        self.calls.append(("amend_take", request))
        return "take-amend"

    def full_close(self, request):
        self.calls.append(("full_close", request))
        return "closed"


class RobotProtectionTests(unittest.TestCase):
    def test_long_structural_stop_one_tick_and_two_percent_fallback(self):
        near = structural_stop(
            DIRECTION_LONG,
            average_entry=Decimal("100"), structural_extreme=Decimal("99"),
            tick_size=Decimal("0.1"),
        )
        far = structural_stop(
            DIRECTION_LONG,
            average_entry=Decimal("100"), structural_extreme=Decimal("95"),
            tick_size=Decimal("0.1"),
        )
        self.assertEqual(near, Decimal("98.9"))
        self.assertEqual(far, Decimal("98.00"))

    def test_short_structural_stop_one_tick_and_two_percent_fallback(self):
        near = structural_stop(
            DIRECTION_SHORT,
            average_entry=Decimal("100"), structural_extreme=Decimal("101"),
            tick_size=Decimal("0.1"),
        )
        far = structural_stop(
            DIRECTION_SHORT,
            average_entry=Decimal("100"), structural_extreme=Decimal("105"),
            tick_size=Decimal("0.1"),
        )
        self.assertEqual(near, Decimal("101.1"))
        self.assertEqual(far, Decimal("102.00"))

    def test_topup_stop_can_only_tighten(self):
        self.assertEqual(
            tighten_stop(DIRECTION_LONG, existing_stop=Decimal("98"), proposed_stop=Decimal("97")),
            Decimal("98"),
        )
        self.assertEqual(
            tighten_stop(DIRECTION_LONG, existing_stop=Decimal("98"), proposed_stop=Decimal("99")),
            Decimal("99"),
        )
        self.assertEqual(
            tighten_stop(DIRECTION_SHORT, existing_stop=Decimal("102"), proposed_stop=Decimal("103")),
            Decimal("102"),
        )
        self.assertEqual(
            tighten_stop(DIRECTION_SHORT, existing_stop=Decimal("102"), proposed_stop=Decimal("101")),
            Decimal("101"),
        )

    def test_take_is_ninety_percent_of_frozen_scanner_potential(self):
        self.assertEqual(
            frozen_take_90(
                DIRECTION_LONG,
                frozen_signal_reference_price=Decimal("100"),
                frozen_scanner_target_price=Decimal("110"),
            ),
            Decimal("109.00"),
        )
        self.assertEqual(
            frozen_take_90(
                DIRECTION_SHORT,
                frozen_signal_reference_price=Decimal("100"),
                frozen_scanner_target_price=Decimal("90"),
            ),
            Decimal("91.00"),
        )

    def test_plan_has_stable_stop_take_requests(self):
        kwargs = dict(
            average_entry=Decimal("100"), structural_extreme=Decimal("99"),
            tick_size=Decimal("0.1"), frozen_signal_reference_price=Decimal("100"),
            frozen_scanner_target_price=Decimal("110"),
        )
        first = build_protection_plan(_candidate(), {"direction": DIRECTION_LONG}, **kwargs)
        second = build_protection_plan(_candidate(), {"direction": DIRECTION_LONG}, **kwargs)
        self.assertEqual(first.stop_price, Decimal("98.9"))
        self.assertEqual(first.take_price, Decimal("109.00"))
        self.assertEqual(first.stop_request.client_action_id, second.stop_request.client_action_id)
        self.assertEqual(first.take_request.client_action_id, second.take_request.client_action_id)

    def test_initial_submission_is_stop_first_and_once_each(self):
        plan = build_protection_plan(
            _candidate(), {"direction": DIRECTION_LONG},
            average_entry=Decimal("100"), structural_extreme=Decimal("99"),
            tick_size=Decimal("0.1"), frozen_signal_reference_price=Decimal("100"),
            frozen_scanner_target_price=Decimal("110"),
        )
        submitter = _Submitter()
        self.assertEqual(submit_initial_protection(submitter, plan), ("stop", "take"))
        self.assertEqual([name for name, _ in submitter.calls], ["create_stop", "create_take"])

    def test_stop_proven_allows_take_recovery_without_emergency_close(self):
        decision = protection_recovery(
            "candidate-1", "TESTUSDT", position_open=True,
            stop_proven=True, take_proven=False,
            protection_started_at_ms=1_000, now_ms=20_000,
            market_data_authoritative=False, intended_stop_crossed=True,
        )
        self.assertEqual(decision.action, RECOVERY_TAKE_ONLY)
        self.assertIsNone(decision.emergency_close_request)

    def test_unproven_stop_waits_only_until_five_second_deadline(self):
        waiting = protection_recovery(
            "candidate-1", "TESTUSDT", position_open=True,
            stop_proven=False, take_proven=True,
            protection_started_at_ms=1_000, now_ms=5_999,
            market_data_authoritative=True, intended_stop_crossed=False,
        )
        closing = protection_recovery(
            "candidate-1", "TESTUSDT", position_open=True,
            stop_proven=False, take_proven=True,
            protection_started_at_ms=1_000, now_ms=1_000 + PROTECTION_DEADLINE_MS,
            market_data_authoritative=True, intended_stop_crossed=False,
        )
        self.assertEqual(waiting.action, RECOVERY_WAIT)
        self.assertEqual(closing.action, RECOVERY_EMERGENCY_CLOSE)

    def test_unknown_market_or_crossed_intended_stop_closes_immediately(self):
        unknown = protection_recovery(
            "candidate-1", "TESTUSDT", position_open=True,
            stop_proven=False, take_proven=False,
            protection_started_at_ms=1_000, now_ms=1_001,
            market_data_authoritative=False, intended_stop_crossed=False,
        )
        crossed = protection_recovery(
            "candidate-1", "TESTUSDT", position_open=True,
            stop_proven=False, take_proven=False,
            protection_started_at_ms=1_000, now_ms=1_001,
            market_data_authoritative=True, intended_stop_crossed=True,
        )
        self.assertEqual(unknown.action, RECOVERY_EMERGENCY_CLOSE)
        self.assertEqual(crossed.action, RECOVERY_EMERGENCY_CLOSE)

    def test_emergency_close_has_stable_identity_and_no_resend_while_in_flight(self):
        first = protection_recovery(
            "candidate-1", "TESTUSDT", position_open=True,
            stop_proven=False, take_proven=False,
            protection_started_at_ms=1_000, now_ms=6_000,
            market_data_authoritative=True, intended_stop_crossed=False,
        )
        second = protection_recovery(
            "candidate-1", "TESTUSDT", position_open=True,
            stop_proven=False, take_proven=False,
            protection_started_at_ms=1_000, now_ms=7_000,
            market_data_authoritative=True, intended_stop_crossed=False,
            emergency_close_in_flight=True,
        )
        self.assertEqual(first.action, RECOVERY_EMERGENCY_CLOSE)
        self.assertEqual(second.action, RECOVERY_EMERGENCY_CLOSE_PENDING)
        submitter = _Submitter()
        submit_emergency_close(submitter, first)
        self.assertEqual([name for name, _ in submitter.calls], ["full_close"])

    def test_authoritative_flat_is_terminal_emergency_failure_close(self):
        decision = protection_recovery(
            "candidate-1", "TESTUSDT", position_open=False,
            stop_proven=False, take_proven=False,
            protection_started_at_ms=1_000, now_ms=2_000,
            market_data_authoritative=True, intended_stop_crossed=False,
            authoritative_flat=True,
        )
        self.assertEqual(decision.action, RECOVERY_CLOSED)

    def test_both_legs_proven_is_protected(self):
        decision = protection_recovery(
            "candidate-1", "TESTUSDT", position_open=True,
            stop_proven=True, take_proven=True,
            protection_started_at_ms=1_000, now_ms=1_100,
            market_data_authoritative=True, intended_stop_crossed=False,
        )
        self.assertEqual(decision.action, RECOVERY_PROTECTED)

    def test_long_structural_at_or_above_entry_falls_back_to_two_percent(self):
        # Post-BATUSDT-defect fix: a structural candidate on the wrong side of
        # (or equal to) the actual authoritative entry must never leave a
        # filled position with no computable STOP at all.
        at_entry = structural_stop(
            DIRECTION_LONG,
            average_entry=Decimal("100"), structural_extreme=Decimal("100.1"),
            tick_size=Decimal("0.1"),
        )
        above_entry = structural_stop(
            DIRECTION_LONG,
            average_entry=Decimal("100"), structural_extreme=Decimal("101"),
            tick_size=Decimal("0.1"),
        )
        non_positive = structural_stop(
            DIRECTION_LONG,
            average_entry=Decimal("100"), structural_extreme=Decimal("0.05"),
            tick_size=Decimal("0.1"),
        )
        self.assertEqual(at_entry, Decimal("98.00"))
        self.assertEqual(above_entry, Decimal("98.00"))
        self.assertEqual(non_positive, Decimal("98.00"))
        self.assertLess(above_entry, Decimal("100"))

    def test_short_structural_at_or_below_entry_falls_back_to_two_percent(self):
        at_entry = structural_stop(
            DIRECTION_SHORT,
            average_entry=Decimal("100"), structural_extreme=Decimal("99.9"),
            tick_size=Decimal("0.1"),
        )
        below_entry = structural_stop(
            DIRECTION_SHORT,
            average_entry=Decimal("100"), structural_extreme=Decimal("99"),
            tick_size=Decimal("0.1"),
        )
        self.assertEqual(at_entry, Decimal("102.00"))
        self.assertEqual(below_entry, Decimal("102.00"))
        self.assertGreater(below_entry, Decimal("100"))


class MinEntryRrTests(unittest.TestCase):
    def _threshold(self, value):
        import robot_protection

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROBOT_MIN_ENTRY_RR", None)
            if value is not None:
                os.environ["ROBOT_MIN_ENTRY_RR"] = value
            return robot_protection.min_entry_rr()

    def test_default_is_one_and_a_half(self):
        import robot_protection

        self.assertEqual(robot_protection.MIN_ENTRY_RR, Decimal("1.5"))
        self.assertEqual(self._threshold(None), Decimal("1.5"))

    def test_environment_value_in_bounds_is_used(self):
        for raw, expected in (("2", "2"), (" 1.25 ", "1.25"), ("0", "0"), ("10", "10")):
            with self.subTest(raw=raw):
                self.assertEqual(self._threshold(raw), Decimal(expected))

    def test_invalid_or_out_of_bounds_value_falls_back_to_default(self):
        for raw in ("", "  ", "abc", "-0.1", "10.01", "NaN", "Infinity", "1,5"):
            with self.subTest(raw=raw):
                self.assertEqual(self._threshold(raw), Decimal("1.5"))

    def test_late_admission_keeps_its_own_constant_with_the_same_default(self):
        from terminal.application.robot_late_admission import MIN_LATE_ADMISSION_RR

        self.assertEqual(MIN_LATE_ADMISSION_RR, Decimal("1.5"))
        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": "5"}):
            self.assertEqual(MIN_LATE_ADMISSION_RR, Decimal("1.5"))  # env applies to the LIMIT path only


if __name__ == "__main__":
    unittest.main()
