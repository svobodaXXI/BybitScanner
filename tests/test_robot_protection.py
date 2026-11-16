from decimal import Decimal
import os
import unittest
from unittest.mock import patch

from robot_protection import (
    MAX_STOP_DISTANCE,
    PROTECTION_DEADLINE_MS,
    RECOVERY_CLOSED,
    RECOVERY_EMERGENCY_CLOSE,
    RECOVERY_EMERGENCY_CLOSE_PENDING,
    RECOVERY_PROTECTED,
    RECOVERY_TAKE_ONLY,
    RECOVERY_WAIT,
    build_protection_plan,
    box_stop_for_actual_entry,
    build_box_stop_only_plan,
    submit_box_stop_only,
    prepare_box_stop_terms,
    RobotProtectionError,
    frozen_take_90,
    protection_recovery,
    structural_stop,
    submit_emergency_close,
    submit_initial_protection,
    limited_stop,
    stop_within_limit,
    tighten_stop,
    fee_aware_break_even_stop,
    summarize_attested_robot_partial,
    plan_wedge_partial_at_two_r,
)
from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT
from terminal.domain.models import (
    Category, Execution, ExecutionDedupKey, ExecutionId,
    OrderId, OrderSide, Price, Quantity, Symbol, TradingAccountId,
)


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
    def test_box_stop_only_never_submits_aggregate_take(self):
        snapshot = {
            "pattern": "IKIGAI_BOX",
            "identity": {"symbol": "TESTUSDT"},
            "plan": {
                "direction": "LONG",
                "limit_prices": ["94", "93.2", "92.4", "91.6"],
                "limit_quantities": ["2"] * 4,
                "take_price": "99.2",
                "stop_price": "89.6",
            },
            "inputs": {
                "tick_size": "0.01",
                "entry_fee_rate": "0",
                "target_fee_rate": "0",
                "stop_fee_rate": "0",
            },
        }
        plan = build_box_stop_only_plan(
            {
                "candidate_id": "candidate-box",
                "status": "APPROVED",
                "signal_snapshot": snapshot,
            },
            {"direction": "LONG"},
            average_entry=Decimal("94"),
            confirmed_position_quantity=Decimal("2"),
        )
        submitter = _Submitter()
        self.assertEqual(submit_box_stop_only(submitter, plan), "stop")
        self.assertEqual([name for name, _ in submitter.calls], ["create_stop"])
        self.assertEqual(plan.take_price, Decimal("99.2"))

    def test_box_actual_fill_stop_keeps_or_minimally_tightens_for_net_rr(self):
        frozen = {
            "pattern": "IKIGAI_BOX",
            "plan": {
                "direction": "LONG",
                "limit_prices": ["94", "93.2", "92.4", "91.6"],
                "take_price": "99.2",
                "stop_price": "89.6",
            },
            "inputs": {
                "tick_size": "0.01",
                "entry_fee_rate": "0",
                "target_fee_rate": "0",
                "stop_fee_rate": "0",
            },
        }
        self.assertEqual(
            box_stop_for_actual_entry(
                frozen, average_entry=Decimal("92.8"),
            ),
            Decimal("89.6"),
        )
        self.assertEqual(
            box_stop_for_actual_entry(
                frozen, average_entry=Decimal("93.5"),
            ),
            Decimal("90.65"),
        )
        self.assertEqual(
            box_stop_for_actual_entry(
                frozen,
                average_entry=Decimal("93.5"),
                existing_stop=Decimal("90.80"),
            ),
            Decimal("90.80"),
        )
        with self.assertRaisesRegex(RobotProtectionError, "no tick-aligned"):
            box_stop_for_actual_entry(
                frozen, average_entry=Decimal("98.9"),
            )

    def test_box_stop_is_excluded_from_non_box_limit(self):
        # Ikigai Box keeps its own P4/RR policy: a 3.4% STOP stays accepted.
        frozen = {
            "pattern": "IKIGAI_BOX",
            "plan": {
                "direction": "LONG",
                "limit_prices": ["94", "93.2", "92.4", "91.6"],
                "take_price": "99.2",
                "stop_price": "89.6",
            },
            "inputs": {
                "tick_size": "0.01",
                "entry_fee_rate": "0",
                "target_fee_rate": "0",
                "stop_fee_rate": "0",
            },
        }
        stop = box_stop_for_actual_entry(frozen, average_entry=Decimal("92.8"))
        self.assertEqual(stop, Decimal("89.6"))
        self.assertGreater((Decimal("92.8") - stop) / Decimal("92.8"), MAX_STOP_DISTANCE)
        self.assertFalse(stop_within_limit(
            DIRECTION_LONG, entry_price=Decimal("92.8"), stop_price=stop,
        ))

    def test_box_actual_fill_stop_mirrors_short_and_never_widens(self):
        frozen = {
            "pattern": "IKIGAI_BOX",
            "plan": {
                "direction": "SHORT",
                "limit_prices": ["106", "106.8", "107.6", "108.4"],
                "take_price": "100.8",
                "stop_price": "110.4",
            },
            "inputs": {
                "tick_size": "0.01",
                "entry_fee_rate": "0",
                "target_fee_rate": "0",
                "stop_fee_rate": "0",
            },
        }
        self.assertEqual(
            box_stop_for_actual_entry(
                frozen, average_entry=Decimal("107.2"),
            ),
            Decimal("110.4"),
        )
        self.assertEqual(
            box_stop_for_actual_entry(
                frozen, average_entry=Decimal("106.5"),
            ),
            Decimal("109.35"),
        )
        with self.assertRaisesRegex(RobotProtectionError, "widens frozen risk"):
            box_stop_for_actual_entry(
                frozen,
                average_entry=Decimal("106.5"),
                existing_stop=Decimal("110.5"),
            )

    def test_box_stop_terms_are_fixed_and_follow_confirmed_exposure(self):
        def snapshot(direction):
            prices = (("94", "93", "92", "91") if direction == "LONG"
                      else ("106", "107", "108", "109"))
            stop = "90" if direction == "LONG" else "110"
            return {
                "pattern": "IKIGAI_BOX", "environment": "PAPER",
                "execution_authorized": False, "attempt": 1,
                "plan": {"direction": direction, "limit_prices": prices,
                         "limit_quantities": ["2"] * 4, "stop_price": stop},
            }

        for direction, entry in (("LONG", "94"), ("SHORT", "106")):
            frozen = snapshot(direction)
            first = prepare_box_stop_terms(
                frozen, confirmed_position_quantity=Decimal("2"),
                confirmed_average_entry=Decimal(entry),
            )
            fourth = prepare_box_stop_terms(
                frozen, confirmed_position_quantity=Decimal("8"),
                confirmed_average_entry=Decimal(entry),
            )
            self.assertEqual(first.price, fourth.price)
            self.assertEqual(first.quantity, Decimal("2"))
            self.assertEqual(fourth.quantity, Decimal("8"))
            with self.assertRaises(RobotProtectionError):
                prepare_box_stop_terms(
                    frozen, confirmed_position_quantity=Decimal("9"),
                    confirmed_average_entry=Decimal(entry),
                )
            with self.assertRaises(RobotProtectionError):
                prepare_box_stop_terms(
                    frozen, confirmed_position_quantity=Decimal("2"),
                    confirmed_average_entry=Decimal(frozen["plan"]["stop_price"]),
                )
            frozen["execution_authorized"] = True
            with self.assertRaises(RobotProtectionError):
                prepare_box_stop_terms(
                    frozen, confirmed_position_quantity=Decimal("2"),
                    confirmed_average_entry=Decimal(entry),
                )

    def test_long_structural_stop_one_tick_and_one_and_half_percent_fallback(self):
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
        self.assertEqual(far, Decimal("98.500"))

    def test_non_box_limit_is_one_and_half_percent_both_directions(self):
        self.assertEqual(MAX_STOP_DISTANCE, Decimal("0.015"))
        cases = (
            # direction, extreme, structural STOP exactly at 1.5%, beyond -> fallback
            (DIRECTION_LONG, Decimal("98.6"), Decimal("98.5"), Decimal("98.5"), Decimal("98.500")),
            (DIRECTION_SHORT, Decimal("101.4"), Decimal("101.5"), Decimal("101.5"), Decimal("101.500")),
        )
        for direction, at_extreme, at_stop, beyond_extreme, fallback in cases:
            with self.subTest(direction=direction):
                self.assertEqual(
                    structural_stop(
                        direction, average_entry=Decimal("100"),
                        structural_extreme=at_extreme, tick_size=Decimal("0.1"),
                    ),
                    at_stop,
                )
                self.assertEqual(
                    structural_stop(
                        direction, average_entry=Decimal("100"),
                        structural_extreme=beyond_extreme, tick_size=Decimal("0.1"),
                    ),
                    fallback,
                )

    def test_limited_stop_keeps_preferred_or_falls_back_to_one_and_half_percent(self):
        cases = (
            (DIRECTION_LONG, Decimal("98.5"), Decimal("98.5")),     # exactly 1.5%: kept
            (DIRECTION_LONG, Decimal("96"), Decimal("98.500")),     # 4%: fallback
            (DIRECTION_LONG, Decimal("100.1"), Decimal("98.500")),  # wrong side: fallback
            (DIRECTION_SHORT, Decimal("101.5"), Decimal("101.5")),
            (DIRECTION_SHORT, Decimal("104"), Decimal("101.500")),
            (DIRECTION_SHORT, Decimal("99.9"), Decimal("101.500")),
        )
        for direction, preferred, expected in cases:
            with self.subTest(direction=direction, preferred=preferred):
                self.assertEqual(
                    limited_stop(direction, entry_price=Decimal("100"), preferred_stop=preferred),
                    expected,
                )

    def test_stop_within_limit_boundaries(self):
        self.assertTrue(stop_within_limit(
            DIRECTION_LONG, entry_price=Decimal("100"), stop_price=Decimal("98.5"),
        ))
        self.assertFalse(stop_within_limit(
            DIRECTION_LONG, entry_price=Decimal("100"), stop_price=Decimal("98.49"),
        ))
        self.assertFalse(stop_within_limit(
            DIRECTION_LONG, entry_price=Decimal("100"), stop_price=Decimal("100"),
        ))
        self.assertTrue(stop_within_limit(
            DIRECTION_SHORT, entry_price=Decimal("100"), stop_price=Decimal("101.5"),
        ))
        self.assertFalse(stop_within_limit(
            DIRECTION_SHORT, entry_price=Decimal("100"), stop_price=Decimal("101.51"),
        ))
        self.assertFalse(stop_within_limit(
            DIRECTION_SHORT, entry_price=Decimal("100"), stop_price=Decimal("100"),
        ))

    def test_deepusdt_wrong_side_extreme_uses_one_and_half_percent_fallback(self):
        # RM-STRUCT-1 control case: frozen counted lower-touch min 0.02107 is
        # above the actual LIMIT fill, so the Wedge LONG fallback applies.
        stop = structural_stop(
            DIRECTION_LONG,
            average_entry=Decimal("0.0209372"), structural_extreme=Decimal("0.02107"),
            tick_size=Decimal("0.00001"),
        )
        self.assertEqual(stop, Decimal("0.0209372") * Decimal("0.985"))
        self.assertLess(stop, Decimal("0.0209372"))

    def test_short_structural_stop_one_tick_and_one_and_half_percent_fallback(self):
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
        self.assertEqual(far, Decimal("101.500"))

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

    def test_long_structural_at_or_above_entry_falls_back_to_one_and_half_percent(self):
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
        self.assertEqual(at_entry, Decimal("98.500"))
        self.assertEqual(above_entry, Decimal("98.500"))
        self.assertEqual(non_positive, Decimal("98.500"))
        self.assertLess(above_entry, Decimal("100"))

    def test_short_structural_at_or_below_entry_falls_back_to_one_and_half_percent(self):
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
        self.assertEqual(at_entry, Decimal("101.500"))
        self.assertEqual(below_entry, Decimal("101.500"))
        self.assertGreater(below_entry, Decimal("100"))



class WedgePartialCausalPlanTests(unittest.TestCase):
    def _case(self, direction="LONG", **overrides):
        params = dict(
            pattern="Falling Wedge",
            average_entry=Decimal("100"),
            initial_stop=Decimal("98") if direction == "LONG" else Decimal("102"),
            active_stop=Decimal("98") if direction == "LONG" else Decimal("102"),
            active_take=Decimal("110") if direction == "LONG" else Decimal("90"),
            original_quantity=Decimal("10"),
            remaining_quantity=Decimal("10"),
            quantity_step=Decimal("0.1"),
            entry_fill_ms=59000,
            candle_open_ms=60000,
            candle_end_ms=120000,
            candle_high=Decimal("104") if direction == "LONG" else Decimal("100"),
            candle_low=Decimal("100") if direction == "LONG" else Decimal("96"),
            available_at_ms=120000,
        )
        params.update(overrides)
        return plan_wedge_partial_at_two_r(direction, **params)

    def test_exact_two_r_and_step_floor_for_both_directions(self):
        self.assertEqual(self._case(), Decimal("2.5"))
        self.assertEqual(self._case("SHORT", pattern="Rising Wedge"), Decimal("2.5"))
        self.assertEqual(self._case(original_quantity=Decimal("9.9"),
                                    remaining_quantity=Decimal("9.9")),
                         Decimal("2.4"))

    def test_unreached_trigger_and_ambiguous_stop_take_bar_do_not_partial(self):
        self.assertIsNone(self._case(candle_high=Decimal("103.99")))
        self.assertIsNone(self._case("SHORT", candle_low=Decimal("96.01")))
        self.assertIsNone(self._case(candle_low=Decimal("98")))
        self.assertIsNone(self._case(candle_high=Decimal("110")))
        self.assertIsNone(self._case("SHORT", candle_high=Decimal("102")))
        self.assertIsNone(self._case("SHORT", candle_low=Decimal("90")))

    def test_unfilled_or_not_yet_closed_bar_is_rejected_not_replayed(self):
        cases = [
            {"entry_fill_ms": 60001}, {"available_at_ms": 119999},
            {"candle_open_ms": 60001},
            {"candle_end_ms": 120001}, {"entry_fill_ms": True},
            {"available_at_ms": -1},
        ]
        for updates in cases:
            with self.subTest(updates=updates):
                with self.assertRaises(RobotProtectionError):
                    self._case(**updates)

    def test_unknown_protection_or_duplicate_partial_is_rejected(self):
        cases = [
            {"remaining_quantity": Decimal("7.5")},
            {"initial_stop": Decimal("100")},
            {"active_stop": Decimal("102")},
            {"active_take": Decimal("99")},
            {"quantity_step": Decimal("0")},
            {"candle_high": Decimal("NaN")},
            {"pattern": "IKIGAI_BOX"},
        ]
        for updates in cases:
            with self.subTest(updates=updates):
                with self.assertRaises(RobotProtectionError):
                    self._case(**updates)
        with self.assertRaises(RobotProtectionError):
            self._case("INVALID")

    def test_non_executable_round_down_returns_none(self):
        self.assertIsNone(self._case(
            original_quantity=Decimal("0.3"),
            remaining_quantity=Decimal("0.3"),
        ))



class AttestedPartialEconomicsTests(unittest.TestCase):
    def _fill(self, tag, oid, side, qty, price, fee, ms,
              account="PAPER", symbol="TESTUSDT"):
        return Execution(
            dedup_key=ExecutionDedupKey(
                TradingAccountId(account), Category.LINEAR, ExecutionId(tag),
            ),
            order_id=OrderId(oid), symbol=Symbol(symbol),
            side=side, quantity=Quantity(Decimal(qty)),
            price=Price(Decimal(price)), fee=Decimal(fee),
            exchange_timestamp_ms=ms,
        )

    def _source(self, direction="LONG", **overrides):
        own_side = OrderSide.BUY if direction == "LONG" else OrderSide.SELL
        exit_side = OrderSide.SELL if direction == "LONG" else OrderSide.BUY
        inputs = dict(
            trading_account_id=TradingAccountId("PAPER"),
            symbol=Symbol("TESTUSDT"),
            entry_order_ids=("entry-a", "entry-b"),
            partial_order_id="partial-1",
            entry_executions=(
                self._fill("entry-exec-a", "entry-a", own_side, "6", "99", "0.36", 1000),
                self._fill("entry-exec-b", "entry-b", own_side, "4", "101.5", "0.24", 1001),
            ),
            partial_executions=(
                self._fill("partial-exec-a", "partial-1", exit_side, "1", "104", "0.0624", 2000),
                self._fill("partial-exec-b", "partial-1", exit_side, "1.5", "105", "0.0945", 2001),
            ),
            actual_remaining_quantity=Decimal("7.5"),
        )
        inputs.update(overrides)
        return summarize_attested_robot_partial(direction, **inputs)

    def test_long_exact_two_entry_and_two_partial_fills(self):
        facts = self._source()
        self.assertEqual(facts.original_quantity, Decimal("10"))
        self.assertEqual(facts.closed_quantity, Decimal("2.5"))
        self.assertEqual(facts.remaining_quantity, Decimal("7.5"))
        self.assertEqual(facts.average_entry, Decimal("100"))
        self.assertEqual(facts.realized_gross_pnl, Decimal("11.5"))
        self.assertEqual(facts.total_entry_fees, Decimal("0.60"))
        self.assertEqual(facts.realized_exit_fees, Decimal("0.1569"))
        stop = fee_aware_break_even_stop(
            "LONG", average_entry=facts.average_entry,
            original_quantity=facts.original_quantity,
            closed_quantity=facts.closed_quantity,
            remaining_quantity=facts.remaining_quantity,
            realized_gross_pnl=facts.realized_gross_pnl,
            total_entry_fees=facts.total_entry_fees,
            realized_exit_fees=facts.realized_exit_fees,
            stop_exit_fee_rate=Decimal("0.001"),
            tick_size=Decimal("0.01"), current_stop=Decimal("98"),
            executable_price=Decimal("105"),
            worst_case_slippage_ticks=2,
        )
        self.assertGreater(stop, Decimal("98"))

    def test_short_exact_partial_has_short_gross_sign(self):
        entry_side = OrderSide.SELL
        exit_side = OrderSide.BUY
        entries = (
            self._fill("short-in-1", "entry-a", entry_side, "6", "99", "0.36", 1000),
            self._fill("short-in-2", "entry-b", entry_side, "4", "101.5", "0.24", 1001),
        )
        exits = (
            self._fill("short-out-1", "partial-1", exit_side, "2.5", "96", "0.144", 2000),
        )
        facts = self._source(
            "SHORT", entry_executions=entries, partial_executions=exits,
        )
        self.assertEqual(facts.realized_gross_pnl, Decimal("10"))
        self.assertEqual(facts.latest_partial_fill_ms, 2000)

    def test_foreign_ambiguous_duplicate_or_incomplete_evidence_fails_closed(self):
        own = self._fill(
            "partial-exec-a", "partial-1", OrderSide.SELL,
            "1", "104", "0.0624", 2000,
        )
        cases = (
            {"partial_executions": (own, own)},
            {"partial_executions": (self._fill(
                "foreign-account", "partial-1", OrderSide.SELL,
                "2.5", "104", "0.1", 2000, account="OTHER",
            ),)},
            {"partial_executions": (self._fill(
                "wrong-side", "partial-1", OrderSide.BUY, "2.5", "104", "0.1", 2000,
            ),)},
            {"partial_executions": (self._fill(
                "wrong-symbol", "partial-1", OrderSide.SELL, "2.5",
                "104", "0.1", 2000, symbol="OTHERUSDT",
            ),)},
            {"partial_executions": (self._fill(
                "wrong-order", "foreign-exit", OrderSide.SELL,
                "2.5", "104", "0.1", 2000,
            ),)},
            {"partial_executions": (self._fill(
                "out-of-order", "partial-1", OrderSide.SELL,
                "2.5", "104", "0.1", 999,
            ),)},
            {"entry_order_ids": ("entry-a", "entry-b", "unfilled-order")},
            {"entry_order_ids": ("entry-a", "entry-a")},
            {"partial_order_id": "entry-b"},
            {"actual_remaining_quantity": Decimal("7.6")},
            {"actual_remaining_quantity": Decimal("0")},
            {"partial_executions": ()},
        )
        for updates in cases:
            with self.subTest(updates=updates):
                with self.assertRaises(RobotProtectionError):
                    self._source(**updates)


class FeeAwareBreakEvenPlannerTests(unittest.TestCase):
    def _case(self, direction="LONG", **overrides):
        data = dict(
            average_entry=Decimal("100"),
            original_quantity=Decimal("10"),
            closed_quantity=Decimal("2.5"),
            remaining_quantity=Decimal("7.5"),
            realized_gross_pnl=Decimal("5"),
            total_entry_fees=Decimal("1"),
            realized_exit_fees=Decimal("0.15"),
            stop_exit_fee_rate=Decimal("0.001"),
            tick_size=Decimal("0.01"),
            current_stop=Decimal("98") if direction == "LONG" else Decimal("102"),
            executable_price=Decimal("104") if direction == "LONG" else Decimal("96"),
            worst_case_slippage_ticks=1,
        )
        data.update(overrides)
        return fee_aware_break_even_stop(direction, **data)

    def test_long_stop_covers_all_fees_and_one_tick_adverse_slippage(self):
        stop = self._case()
        self.assertGreater(stop, Decimal("98"))
        self.assertLess(stop, Decimal("104"))
        fill = stop - Decimal("0.01")
        net = (
            Decimal("5") + (fill - Decimal("100")) * Decimal("7.5")
            - Decimal("1.15") - fill * Decimal("7.5") * Decimal("0.001")
        )
        self.assertGreaterEqual(net, 0)

    def test_short_stop_covers_all_fees_and_one_tick_adverse_slippage(self):
        stop = self._case("SHORT")
        self.assertLess(stop, Decimal("102"))
        self.assertGreater(stop, Decimal("96"))
        fill = stop + Decimal("0.01")
        net = (
            Decimal("5") + (Decimal("100") - fill) * Decimal("7.5")
            - Decimal("1.15") - fill * Decimal("7.5") * Decimal("0.001")
        )
        self.assertGreaterEqual(net, 0)

    def test_repeated_proposal_never_loosens_existing_stop(self):
        long_stop = self._case()
        short_stop = self._case("SHORT")
        self.assertEqual(self._case(current_stop=long_stop + Decimal("0.01")),
                         long_stop + Decimal("0.01"))
        self.assertEqual(self._case("SHORT", current_stop=short_stop - Decimal("0.01")),
                         short_stop - Decimal("0.01"))

    def test_partial_must_be_proven_and_exactly_match_remaining_position(self):
        for updates in (
            {"closed_quantity": Decimal("0")},
            {"remaining_quantity": Decimal("0")},
            {"remaining_quantity": Decimal("8")},
            {"original_quantity": Decimal("0")},
            {"total_entry_fees": Decimal("-1")},
            {"realized_exit_fees": Decimal("-0.1")},
            {"stop_exit_fee_rate": Decimal("1")},
            {"tick_size": Decimal("0")},
            {"realized_gross_pnl": Decimal("NaN")},
            {"worst_case_slippage_ticks": -1},
            {"worst_case_slippage_ticks": True},
        ):
            with self.subTest(updates=updates):
                with self.assertRaises(RobotProtectionError):
                    self._case(**updates)

    def test_gapped_or_unexecutable_stop_never_replaces_armed_protection(self):
        for direction, updates in (
            ("LONG", {"executable_price": Decimal("98")}),
            ("SHORT", {"executable_price": Decimal("102")}),
            ("LONG", {"executable_price": Decimal("99")}),
            ("SHORT", {"executable_price": Decimal("101")}),
        ):
            with self.subTest(direction=direction, updates=updates):
                with self.assertRaises(RobotProtectionError):
                    self._case(direction, **updates)

    def test_refuses_unsupported_direction_and_nonfinite_price(self):
        with self.assertRaises(RobotProtectionError):
            self._case("SIDEWAYS")
        with self.assertRaises(RobotProtectionError):
            self._case(average_entry=Decimal("Infinity"))


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

    def test_late_admission_shares_owner_approved_one_and_half_wedge_floor(self):
        import robot_protection
        from terminal.application.robot_late_admission import MIN_LATE_ADMISSION_RR

        self.assertEqual(MIN_LATE_ADMISSION_RR, Decimal("1.5"))
        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": "0"}):
            self.assertEqual(robot_protection.wedge_min_entry_rr(), Decimal("1.5"))
        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": "1.54"}):
            self.assertEqual(robot_protection.wedge_min_entry_rr(), Decimal("1.54"))
        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": "5"}):
            self.assertEqual(robot_protection.wedge_min_entry_rr(), Decimal("5"))


if __name__ == "__main__":
    unittest.main()
