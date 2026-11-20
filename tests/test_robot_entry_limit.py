from decimal import Decimal
import unittest

from robot_entry_limit import (
    RobotEntryLimitError,
    build_initial_retest_limit,
    build_retest_limit_reprice,
    reprice_due,
    submit_initial_retest_limit,
    submit_retest_limit_reprice,
)
from robot_state_machine import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    PHASE_RETEST_DETECTED,
)
from terminal.api.models import CommandResultStatus, PaperLimitMutationResult, VolumeUnit
from terminal.domain.models import OrderSide


def _snapshot(pattern="Falling Wedge"):
    return {
        "symbol": "TESTUSDT",
        "pattern": pattern,
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {
                "index": 110,
                "price": 90.0,
                "valid_intersection": True,
            },
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


def _state(direction=DIRECTION_LONG, *, breakout_index=102, retest_index=104):
    return {
        "phase": PHASE_RETEST_DETECTED,
        "direction": direction,
        "breakout_index": breakout_index,
        "retest_index": retest_index,
    }


class _RecordingSubmitter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create_limit(self, request):
        self.calls.append(request)
        return self.result

    def amend_limit(self, request):
        self.calls.append(request)
        return self.result


class RobotInitialRetestLimitTests(unittest.TestCase):
    def test_long_uses_frozen_upper_plus_two_ticks_and_one_wv(self):
        plan = build_initial_retest_limit(
            _candidate(),
            _state(),
            tick_size=Decimal("0.01"),
        )

        self.assertEqual(plan.direction, DIRECTION_LONG)
        self.assertEqual(plan.retest_index, 104)
        self.assertEqual(plan.boundary_price, Decimal("96.0"))
        self.assertEqual(plan.request.side, OrderSide.BUY)
        self.assertEqual(plan.request.limit_price, Decimal("96.02"))
        self.assertEqual(plan.request.sizing_reference_price, Decimal("96.02"))
        self.assertEqual(plan.request.volume.unit, VolumeUnit.WORKING_VOLUME)
        self.assertEqual(plan.request.volume.amount, Decimal("1"))

    def test_short_uses_frozen_lower_minus_two_ticks(self):
        plan = build_initial_retest_limit(
            _candidate("Rising Wedge"),
            _state(DIRECTION_SHORT, breakout_index=102, retest_index=103),
            tick_size=Decimal("0.01"),
        )

        self.assertEqual(plan.direction, DIRECTION_SHORT)
        self.assertEqual(plan.boundary_price, Decimal("93.5"))
        self.assertEqual(plan.request.side, OrderSide.SELL)
        self.assertEqual(plan.request.limit_price, Decimal("93.48"))

    def test_shared_normalizer_is_applied_after_two_tick_offset(self):
        candidate = _candidate()
        candidate["signal_snapshot"]["geometry"]["upper_line"] = {
            "slope": Decimal("-0.333"),
            "intercept": Decimal("130.777"),
        }
        plan = build_initial_retest_limit(
            candidate,
            _state(retest_index=104),
            tick_size=Decimal("0.05"),
        )

        self.assertEqual(plan.request.limit_price % Decimal("0.05"), Decimal("0.00"))
        self.assertLessEqual(plan.request.limit_price, plan.boundary_price + Decimal("0.10"))

    def test_client_action_id_is_stable_for_same_candidate_and_retest(self):
        first = build_initial_retest_limit(
            _candidate(), _state(), tick_size=Decimal("0.01")
        )
        second = build_initial_retest_limit(
            _candidate(), _state(), tick_size=Decimal("0.01")
        )

        self.assertEqual(
            first.request.client_action_id.value,
            second.request.client_action_id.value,
        )

    def test_different_retest_index_gets_different_action_identity(self):
        first = build_initial_retest_limit(
            _candidate(), _state(retest_index=104), tick_size=Decimal("0.01")
        )
        second = build_initial_retest_limit(
            _candidate(), _state(retest_index=105), tick_size=Decimal("0.01")
        )

        self.assertNotEqual(
            first.request.client_action_id.value,
            second.request.client_action_id.value,
        )

    def test_submission_calls_shared_create_limit_exactly_once_even_for_unknown(self):
        plan = build_initial_retest_limit(
            _candidate(), _state(), tick_size=Decimal("0.01")
        )
        expected = PaperLimitMutationResult(
            plan.request.client_action_id.value,
            CommandResultStatus.UNKNOWN,
            "ambiguous_transport",
            None,
        )
        submitter = _RecordingSubmitter(expected)

        result = submit_initial_retest_limit(submitter, plan)

        self.assertIs(result, expected)
        self.assertEqual(submitter.calls, [plan.request])

    def test_reprice_due_every_five_closed_candles(self):
        self.assertFalse(reprice_due(last_limit_index=104, current_index=108))
        self.assertTrue(reprice_due(last_limit_index=104, current_index=109))
        with self.assertRaisesRegex(RobotEntryLimitError, "precedes"):
            reprice_due(last_limit_index=104, current_index=103)

    def test_long_reprice_amends_same_order_at_current_boundary(self):
        plan = build_retest_limit_reprice(
            _candidate(),
            _state(),
            geometry_index=109,
            tick_size=Decimal("0.01"),
            order_id="paper-order-1",
        )

        self.assertEqual(plan.geometry_index, 109)
        self.assertEqual(plan.boundary_price, Decimal("91.0"))
        self.assertEqual(plan.request.order_id, "paper-order-1")
        self.assertEqual(plan.request.limit_price, Decimal("91.02"))

    def test_short_reprice_uses_lower_boundary_minus_two_ticks(self):
        plan = build_retest_limit_reprice(
            _candidate("Rising Wedge"),
            _state(DIRECTION_SHORT, retest_index=103),
            geometry_index=109,
            tick_size=Decimal("0.01"),
            order_id="paper-order-short",
        )

        self.assertEqual(plan.boundary_price, Decimal("90.5"))
        self.assertEqual(plan.request.order_id, "paper-order-short")
        self.assertEqual(plan.request.limit_price, Decimal("90.48"))

    def test_reprice_action_identity_is_stable_and_bound_to_order_and_index(self):
        first = build_retest_limit_reprice(
            _candidate(), _state(), geometry_index=109,
            tick_size=Decimal("0.01"), order_id="paper-order-1",
        )
        repeated = build_retest_limit_reprice(
            _candidate(), _state(), geometry_index=109,
            tick_size=Decimal("0.01"), order_id="paper-order-1",
        )
        later = build_retest_limit_reprice(
            _candidate(), _state(), geometry_index=108,
            tick_size=Decimal("0.01"), order_id="paper-order-2",
        )

        self.assertEqual(
            first.request.client_action_id,
            repeated.request.client_action_id,
        )
        self.assertNotEqual(
            first.request.client_action_id,
            later.request.client_action_id,
        )

    def test_reprice_rejects_apex_and_submit_uses_amend_once(self):
        with self.assertRaisesRegex(RobotEntryLimitError, "at or after apex"):
            build_retest_limit_reprice(
                _candidate(), _state(), geometry_index=110,
                tick_size=Decimal("0.01"), order_id="paper-order-1",
            )

        plan = build_retest_limit_reprice(
            _candidate(), _state(), geometry_index=109,
            tick_size=Decimal("0.01"), order_id="paper-order-1",
        )
        expected = PaperLimitMutationResult(
            plan.request.client_action_id.value,
            CommandResultStatus.COMPLETED,
            "amended",
            "paper-order-1",
        )
        submitter = _RecordingSubmitter(expected)
        result = submit_retest_limit_reprice(submitter, plan)

        self.assertIs(result, expected)
        self.assertEqual(submitter.calls, [plan.request])

    def test_fails_closed_before_retest(self):
        state = _state()
        state["phase"] = "WAITING_RETEST"
        with self.assertRaisesRegex(RobotEntryLimitError, "RETEST_DETECTED"):
            build_initial_retest_limit(
                _candidate(), state, tick_size=Decimal("0.01")
            )

    def test_fails_closed_on_direction_pattern_mismatch(self):
        with self.assertRaisesRegex(RobotEntryLimitError, "differs from frozen pattern"):
            build_initial_retest_limit(
                _candidate("Rising Wedge"),
                _state(DIRECTION_LONG),
                tick_size=Decimal("0.01"),
            )

    def test_fails_closed_on_bad_tick_or_retest_order(self):
        with self.assertRaisesRegex(RobotEntryLimitError, "tick_size"):
            build_initial_retest_limit(
                _candidate(), _state(), tick_size=Decimal("0")
            )
        with self.assertRaisesRegex(RobotEntryLimitError, "after breakout"):
            build_initial_retest_limit(
                _candidate(),
                _state(breakout_index=104, retest_index=104),
                tick_size=Decimal("0.01"),
            )




class PostBreakoutWedgeImpulseQuoteTests(unittest.TestCase):
    """First executable-quote boundary only; still no Robot order authority."""

    @staticmethod
    def host(direction="LONG"):
        from types import SimpleNamespace

        pattern = "Falling Wedge" if direction == "LONG" else "Rising Wedge"
        snapshot = {
            "symbol": "TESTUSDT", "pattern": pattern,
            "geometry": {
                "upper_line": {"slope": -1.0, "intercept": 200.0},
                "lower_line": {"slope": -0.5, "intercept": 145.0},
                "apex": {"index": 110, "valid_intersection": True},
                "current_index": 100,
                "pair_metrics": {
                    "reference_price": "100" if direction == "LONG" else "95",
                    "start_width": "10",
                },
                "touches": {
                    "lower_touch_points": [{"counted": True, "price": "98"}],
                    "upper_touch_points": [{"counted": True, "price": "97"}],
                },
            },
            "scanner_geometry_cursor": {
                "version": "1.0", "timeframe": "1",
                "geometry_index": 100, "source_candle_time_ms": 60_000,
            },
        }
        state = {
            "state_version": "1.0", "pattern": pattern,
            "phase": "WAITING_RETEST", "direction": direction,
            "geometry_cursor": 101, "breakout_index": 101,
            "retest_index": None,
        }
        return SimpleNamespace(
            candidate_id="original-wedge-1", state_revision=4,
            symbol=SimpleNamespace(value="TESTUSDT"),
            status="APPROVED", signal_snapshot=snapshot, robot_state=state,
        )

    @staticmethod
    def receipt(direction="LONG"):
        from robot_entry_flow_evidence import CandidateBoundFlowEvidence, FlowTransition

        return CandidateBoundFlowEvidence(
            candidate_id="original-wedge-1", state_revision=4,
            symbol="TESTUSDT", direction=direction,
            source_kind="BYBIT_TRIPLE_CLOSED_M1_CERTIFIED",
            closed_at_ms=180_000, decision_ms=180_010,
            print_facts_sha256="a" * 64, source_complete=True,
            receipt_cutoff_proven=True, transport_generation_proven=True,
            transition=FlowTransition(
                known_at_ms=180_010,
                current_delta_fraction=Decimal(
                    "0.45" if direction == "LONG" else "-0.45"
                ),
                current_price_change_bps=Decimal(
                    "11" if direction == "LONG" else "-11"
                ),
                buy_wave_accelerating=(direction == "LONG"),
                sell_wave_accelerating=(direction == "SHORT"),
                sell_impact_fading=False, buy_impact_fading=False,
                bid_refill_observed=None, ask_refill_observed=None,
                sell_absorption_candidate=None, buy_absorption_candidate=None,
            ),
        )

    @staticmethod
    def book(direction="LONG", *, received=180_050, health=None):
        from terminal.domain.models import Price, Quantity, Symbol
        from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel

        bid = Decimal("100.20" if direction == "LONG" else "93.90")
        ask = Decimal("100.25" if direction == "LONG" else "94.00")
        return NormalizedOrderBook(
            symbol=Symbol("TESTUSDT"),
            bids=(PriceLevel(Price(bid), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(ask), Quantity(Decimal("10"))),),
            health=BookHealth.READY if health is None else health,
            received_at_ms=received, available_depth=1,
        )

    @staticmethod
    def plan(host=None, receipt=None, book=None, *, now=180_100):
        from robot_entry_limit import build_post_breakout_wedge_impulse_limit_research

        return build_post_breakout_wedge_impulse_limit_research(
            host if host is not None else PostBreakoutWedgeImpulseQuoteTests.host(),
            receipt if receipt is not None else PostBreakoutWedgeImpulseQuoteTests.receipt(),
            book if book is not None else PostBreakoutWedgeImpulseQuoteTests.book(),
            tick_size=Decimal("0.01"), now_ms=now,
        )

    def test_long_proposes_current_best_ask_with_native_protection_and_costs(self):
        p = self.plan()
        self.assertFalse(p.trading_authorized)
        self.assertEqual(p.candidate_id, "original-wedge-1")
        self.assertEqual(p.breakout_known_at_ms, 180_000)
        self.assertEqual(p.quoted_price, Decimal("100.25"))
        self.assertEqual(p.request.limit_price, Decimal("100.25"))
        self.assertEqual(p.request.side, OrderSide.BUY)
        self.assertEqual(p.request.volume.unit, VolumeUnit.WORKING_VOLUME)
        self.assertEqual(p.request.volume.amount, Decimal("1"))
        self.assertEqual(p.take_price, Decimal("109.0"))
        self.assertLess(p.stop_price, p.quoted_price)
        self.assertGreater(p.planned_net_rr, Decimal("1.5"))
        self.assertGreater(p.worst_loss_per_base_usdt, Decimal("0"))
        self.assertEqual(p.request.client_action_id, self.plan().request.client_action_id)

    def test_short_proposes_best_bid_without_retest(self):
        p = self.plan(
            host=self.host("SHORT"),
            receipt=self.receipt("SHORT"),
            book=self.book("SHORT"),
        )
        self.assertEqual(p.request.side, OrderSide.SELL)
        self.assertEqual(p.quoted_price, Decimal("93.90"))
        self.assertGreater(p.stop_price, p.quoted_price)
        self.assertLess(p.take_price, p.quoted_price)
        self.assertGreater(p.planned_net_rr, Decimal("1.5"))
        self.assertFalse(p.trading_authorized)

    def test_retest_or_existing_execution_never_creates_an_early_plan(self):
        host = self.host()
        host.robot_state["phase"] = "RETEST_DETECTED"
        with self.assertRaises(RobotEntryLimitError):
            self.plan(host=host)
        host = self.host()
        host.robot_state["execution"] = {"limit_order_id": "already-owned"}
        with self.assertRaises(RobotEntryLimitError):
            self.plan(host=host)

    def test_rejects_unknown_stale_revised_or_opposite_flow(self):
        from dataclasses import replace

        for proof in (
            replace(self.receipt(), source_complete=False),
            replace(self.receipt(), state_revision=5),
            replace(self.receipt(), direction="SHORT"),
            replace(self.receipt(), closed_at_ms=120_000),
            replace(self.receipt(), transition=replace(
                self.receipt().transition, buy_wave_accelerating=False,
            )),
        ):
            with self.subTest(proof=proof):
                with self.assertRaises(RobotEntryLimitError):
                    self.plan(receipt=proof)

    def test_book_must_be_fresh_ready_and_outside_frozen_pattern(self):
        from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
        from terminal.domain.models import Price, Quantity, Symbol

        with self.assertRaises(RobotEntryLimitError):
            self.plan(book=self.book(received=177_000))
        with self.assertRaises(RobotEntryLimitError):
            self.plan(book=self.book(health=BookHealth.DEGRADED))
        b = self.book()
        inside = NormalizedOrderBook(
            symbol=Symbol("TESTUSDT"),
            bids=(PriceLevel(Price(Decimal("98.9")), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(Decimal("99.0")), Quantity(Decimal("10"))),),
            health=BookHealth.READY, received_at_ms=180_050,
            available_depth=1,
        )
        with self.assertRaises(RobotEntryLimitError):
            self.plan(book=inside)
        future = replace(b, source_event_at_ms=180_200)
        with self.assertRaises(RobotEntryLimitError):
            self.plan(book=future)
        wrong_symbol = replace(b, symbol=Symbol("OTHERUSDT"))
        with self.assertRaises(RobotEntryLimitError):
            self.plan(book=wrong_symbol)

    def test_rejects_unproven_geometry_and_poor_net_reward(self):
        host = self.host()
        host.signal_snapshot["geometry"]["touches"] = {}
        with self.assertRaises(Exception):
            self.plan(host=host)
        host = self.host()
        host.signal_snapshot["geometry"]["pair_metrics"]["start_width"] = "0.1"
        with self.assertRaises(Exception):
            self.plan(host=host)

    def test_original_retest_policy_still_requires_retest_detected(self):
        with self.assertRaises(RobotEntryLimitError):
            build_initial_retest_limit(
                _candidate(),
                {"phase": "WAITING_RETEST", "direction": "LONG",
                 "breakout_index": 102, "retest_index": None},
                tick_size=Decimal("0.01"),
            )


if __name__ == "__main__":
    unittest.main()
