"""Proof of the new internal once-only Wedge PAPER reduction through the real owner.

No automatic producer calls this method. It is not authorization to run a
Wedge/BE strategy on VPS. All executions are local in-memory market evidence.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import time
import unittest

from terminal.api.models import CommandResultStatus
from terminal.domain.models import (
    Category, OrderId, PositionKey, Symbol, TradingAccountId,
)
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_terminal_paper_runtime import (
    _runtime, _crossing_book, _open_robot_position_with_confirmed_protection,
    _set_admission,
)


class RobotBePartialOwnerPaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "be.sqlite3"
        self.runtime = _runtime(self.db)
        self.addCleanup(self.runtime.close)
        self.account = TradingAccountId("paper")
        self.symbol = Symbol("BTCUSDT")
        self.candidate_id = "wedge-be-owner"
        self.trade_id = "robot-trade-wedge-be-owner"
        now_ms = int(time.time() * 1000)
        self.minute = (now_ms // 60000 - 2) * 60000
        # Entry fill is a past, immutable source-time execution; the later
        # closed M1 bar is available before the current fresh execution book.
        self.runtime._limit_executor.clock_ms = lambda: self.minute + 30000
        _open_robot_position_with_confirmed_protection(
            self.runtime, symbol=self.symbol.value,
            entry_price=Decimal("64250.5"), stop_price=Decimal("64000"),
            take_price=Decimal("65300"), trade_id=self.trade_id,
            candidate_id=self.candidate_id,
        )
        candidate = self.runtime.store.get_robot_candidate(self.candidate_id)
        fills = self.runtime.store.load_executions_for_symbol(self.account, self.symbol)
        self.assertEqual(len(fills), 1)
        execution = {"limit_order_id": fills[0].order_id.value}
        self.runtime.store.save_robot_candidate_state(
            self.candidate_id, status="OPEN",
            robot_state={"phase": "OPEN", "direction": "LONG", "execution": execution},
            expected_revision=candidate.state_revision,
            updated_at_ms=int(time.time() * 1000),
        )
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        self.key = PositionKey(self.account, Category.LINEAR, self.symbol, 0)
        self.initial = self.runtime.store.get_position_projection(self.key).quantity.value
        self.book = _crossing_book(self.symbol.value, bid="64800", ask="64800.5")

    def run_partial(self, **overrides):
        kwargs = dict(
            candle_open_ms=self.minute + 60000,
            candle_end_ms=self.minute + 120000,
            candle_high=Decimal("64800"), candle_low=Decimal("64600"),
            book=self.book,
        )
        kwargs.update(overrides)
        return self.runtime._robot_wedge_be_partial_once(self.candidate_id, **kwargs)

    def _fade_receipt(self, *, direction="LONG"):
        """Bound original OPEN trade and two fully AFTER-entry M1 windows."""
        from robot_entry_flow_evidence import CandidateBoundFlowEvidence, FlowTransition

        candidate = self.runtime.store.get_robot_candidate(self.candidate_id)
        close_ms = self.minute + 180_000
        impact = FlowTransition(
            known_at_ms=close_ms + 2_000,
            current_delta_fraction=Decimal("0.24" if direction == "LONG" else "-0.24"),
            current_price_change_bps=Decimal("3" if direction == "LONG" else "-3"),
            buy_wave_accelerating=False, sell_wave_accelerating=False,
            buy_impact_fading=direction == "LONG",
            sell_impact_fading=direction == "SHORT",
            bid_refill_observed=None, ask_refill_observed=None,
            buy_absorption_candidate=None, sell_absorption_candidate=None,
        )
        return CandidateBoundFlowEvidence(
            candidate_id=self.candidate_id, state_revision=candidate.state_revision,
            symbol=self.symbol.value, direction=direction,
            source_kind="BYBIT_TRIPLE_CLOSED_M1_CERTIFIED",
            closed_at_ms=close_ms, decision_ms=close_ms + 2_000,
            print_facts_sha256="b" * 64,
            source_complete=True, receipt_cutoff_proven=True,
            transport_generation_proven=True, transition=impact,
        )

    def test_dynamic_fade_uses_same_reduce_only_owner_and_tightens_stop_after_fill(self):
        from unittest.mock import patch

        receipt = self._fade_receipt()
        clock_ms = receipt.closed_at_ms + 5_000
        self.runtime._impulse_fade_paper_enabled = True
        self.runtime._wedge_be_auto_paper_enabled = True
        before = len(self.runtime.store.load_executions())
        with patch("time.time", return_value=clock_ms / 1000):
            book = _crossing_book(self.symbol.value, bid="64700", ask="64700.5")
            result = self.runtime._robot_wedge_be_auto_step(
                self.candidate_id, symbol=self.symbol.value, candle=None,
                book=book, fade_receipt=receipt,
            )
            self.assertEqual(result.status, CommandResultStatus.COMPLETED)
            self.assertEqual(len(self.runtime.store.load_executions()), before + 1)
            candidate = self.runtime.store.get_robot_candidate(self.candidate_id)
            execution = candidate.robot_state["execution"]
            self.assertTrue(execution["wedge_be_partial_intent"]["reduce_only_required"])
            self.assertEqual(
                execution["wedge_be_fade_source"]["source_sha256"],
                receipt.print_facts_sha256,
            )
            self.assertLess(book.bids[0].price.value, Decimal("64751.5"))
            remaining = self.runtime.store.get_position_projection(self.key)
            self.assertGreater(remaining.quantity.value, Decimal(0))
            self.assertLess(remaining.quantity.value, self.initial)
            self.assertEqual(
                self.runtime.store.get_protection_projection(self.key).stop_loss,
                Decimal("64000"),
            )
            recovered = self.runtime._robot_wedge_be_auto_step(
                self.candidate_id, symbol=self.symbol.value, candle=None, book=book,
            )
            self.assertEqual(recovered.status, CommandResultStatus.COMPLETED)
            protected = self.runtime.store.get_protection_projection(self.key)
            self.assertGreater(protected.stop_loss, Decimal("64000"))
            self.assertLess(protected.stop_loss, book.bids[0].price.value)
            self.assertEqual(protected.take_profit, Decimal("65300"))
            self.assertEqual(len(self.runtime.store.load_executions()), before + 1)
            repeated = self.runtime._robot_wedge_be_auto_step(
                self.candidate_id, symbol=self.symbol.value, candle=None,
                book=book, fade_receipt=receipt,
            )
            self.assertEqual(repeated.status, CommandResultStatus.COMPLETED)
            self.assertEqual(len(self.runtime.store.load_executions()), before + 1)

    def test_dynamic_fade_rejects_unprofitable_or_insufficient_depth_before_intent(self):
        from dataclasses import replace
        from unittest.mock import patch
        from terminal.domain.models import Price, Quantity
        from terminal.market_data.models import PriceLevel

        receipt = self._fade_receipt()
        clock_ms = receipt.closed_at_ms + 5_000
        self.runtime._impulse_fade_paper_enabled = True
        self.runtime._wedge_be_auto_paper_enabled = True
        before = len(self.runtime.store.load_executions())
        step = self.runtime._instrument_provider(self.symbol.value).quantity_step
        partial = (
            self.initial * Decimal("0.25") / step
        ).to_integral_value(rounding="ROUND_FLOOR") * step
        tiny_best = PriceLevel(Price(Decimal("64700")), Quantity(partial / 10))
        loss_level = PriceLevel(Price(Decimal("64100")), Quantity(partial))
        with patch("time.time", return_value=clock_ms / 1000):
            book = _crossing_book(self.symbol.value, bid="64700", ask="64700.5")
            for bids in ((tiny_best,), (tiny_best, loss_level)):
                with self.subTest(depth=len(bids)):
                    thin = replace(book, bids=bids, available_depth=len(bids))
                    result = self.runtime._robot_wedge_be_auto_step(
                        self.candidate_id, symbol=self.symbol.value, candle=None,
                        book=thin, fade_receipt=receipt,
                    )
                    self.assertEqual(result.status, CommandResultStatus.BLOCKED)
                    self.assertEqual(result.reason_code, "be_fade_unproven")
                    self.assertEqual(len(self.runtime.store.load_executions()), before)
                    candidate = self.runtime.store.get_robot_candidate(self.candidate_id)
                    self.assertNotIn("wedge_be_partial_intent", candidate.robot_state["execution"])
                    protection = self.runtime.store.get_protection_projection(self.key)
                    self.assertEqual(protection.stop_loss, Decimal("64000"))
                    self.assertEqual(protection.take_profit, Decimal("65300"))

    def test_monitor_routes_fade_to_real_owner_without_old_m1_trigger(self):
        from unittest.mock import patch

        receipt = self._fade_receipt()
        clock_ms = receipt.closed_at_ms + 5_000
        self.runtime._impulse_fade_paper_enabled = True
        monitor = self._enable_auto()
        monitor._impulse_fade_paper_enabled = True
        monitor._get_pattern_flow_evidence = lambda _record: receipt
        monitor._get_closed_candle = lambda _symbol: (_ for _ in ()).throw(
            AssertionError("dynamic fade must not need old +2R candle")
        )
        original_execs = len(self.runtime.store.load_executions())
        with patch("time.time", return_value=clock_ms / 1000):
            with patch.object(self.runtime, "_streamed_book", side_effect=lambda _s:
                              _crossing_book(self.symbol.value, bid="64700", ask="64700.5")):
                self.assertEqual(monitor.tick(), (self.candidate_id,))
                self.assertEqual(
                    len(self.runtime.store.load_executions()), original_execs + 1,
                )
                self.assertEqual(
                    self.runtime.store.get_protection_projection(self.key).stop_loss,
                    Decimal("64000"),
                )
                self.assertEqual(monitor.tick(), (self.candidate_id,))
                stop = self.runtime.store.get_protection_projection(self.key).stop_loss
                self.assertGreater(stop, Decimal("64000"))
                self.assertLess(stop, Decimal("64700"))
                self.assertEqual(monitor.tick(), (self.candidate_id,))
        self.assertEqual(len(self.runtime.store.load_executions()), original_execs + 1)

    def test_unqualified_fade_does_not_mask_original_plus_two_r(self):
        from dataclasses import replace
        from unittest.mock import patch

        receipt = self._fade_receipt()
        receipt = replace(receipt, transition=replace(
            receipt.transition, buy_impact_fading=False,
        ))
        now_ms = receipt.closed_at_ms + 5_000
        self.runtime._impulse_fade_paper_enabled = True
        monitor = self._enable_auto()
        monitor._impulse_fade_paper_enabled = True
        monitor._get_pattern_flow_evidence = lambda _record: receipt
        before = len(self.runtime.store.load_executions())
        with patch("time.time", return_value=now_ms / 1000):
            with patch.object(self.runtime, "_streamed_book", side_effect=lambda _s:
                              _crossing_book(self.symbol.value, bid="64800", ask="64800.5")):
                self.assertEqual(monitor.tick(), (self.candidate_id,))
                self.assertEqual(len(self.runtime.store.load_executions()), before + 1)
                execution = self.runtime.store.get_robot_candidate(
                    self.candidate_id,
                ).robot_state["execution"]
                self.assertIn("wedge_be_partial_intent", execution)
                self.assertNotIn("wedge_be_fade_source", execution)

    def test_invalid_fade_without_legacy_bar_never_forces_partial(self):
        from dataclasses import replace
        from unittest.mock import patch

        receipt = self._fade_receipt()
        receipt = replace(receipt, source_complete=False)
        self.runtime._impulse_fade_paper_enabled = True
        monitor = self._enable_auto()
        monitor._impulse_fade_paper_enabled = True
        monitor._get_pattern_flow_evidence = lambda _record: receipt
        monitor._get_closed_candle = lambda _symbol: None
        before = len(self.runtime.store.load_executions())
        with patch("time.time", return_value=(receipt.closed_at_ms + 5_000) / 1000):
            with patch.object(self.runtime, "_streamed_book", side_effect=lambda _s:
                              _crossing_book(self.symbol.value, bid="64800", ask="64800.5")):
                self.assertEqual(monitor.tick(), ())
        self.assertEqual(len(self.runtime.store.load_executions()), before)
        execution = self.runtime.store.get_robot_candidate(
            self.candidate_id,
        ).robot_state["execution"]
        self.assertNotIn("wedge_be_partial_intent", execution)

    def test_dynamic_fade_invalid_source_cannot_dispatch_or_disarm_stop(self):
        from dataclasses import replace
        from unittest.mock import patch

        self.runtime._impulse_fade_paper_enabled = True
        self.runtime._wedge_be_auto_paper_enabled = True
        receipt = self._fade_receipt()
        before = len(self.runtime.store.load_executions())
        with patch("time.time", return_value=(receipt.closed_at_ms + 5_000) / 1000):
            book = _crossing_book(self.symbol.value, bid="64700", ask="64700.5")
            for bad in (
                replace(receipt, source_complete=False),
                replace(receipt, candidate_id="foreign"),
                replace(receipt, state_revision=receipt.state_revision + 1),
                replace(receipt, transition=replace(
                    receipt.transition, buy_impact_fading=False,
                )),
            ):
                with self.subTest(candidate=bad.candidate_id, rev=bad.state_revision):
                    outcome = self.runtime._robot_wedge_be_auto_step(
                        self.candidate_id, symbol=self.symbol.value, candle=None,
                        book=book, fade_receipt=bad,
                    )
                    self.assertEqual(outcome.status, CommandResultStatus.BLOCKED)
                    self.assertEqual(len(self.runtime.store.load_executions()), before)
                    record = self.runtime.store.get_robot_candidate(self.candidate_id)
                    self.assertNotIn(
                        "wedge_be_partial_intent", record.robot_state["execution"],
                    )
                    projection = self.runtime.store.get_protection_projection(self.key)
                    self.assertEqual(projection.stop_loss, Decimal("64000"))

    def test_exact_reduce_only_partial_preserves_stop_take_and_trade(self):
        initial = len(self.runtime.store.load_executions())
        result = self.run_partial()
        self.assertEqual(result.status, CommandResultStatus.COMPLETED)
        after = self.runtime.store.get_position_projection(self.key)
        instrument = self.runtime._instrument_provider(self.symbol.value)
        partial = (
            self.initial * Decimal("0.25") / instrument.quantity_step
        ).to_integral_value(rounding="ROUND_FLOOR") * instrument.quantity_step
        self.assertEqual(after.quantity.value, self.initial - partial)
        self.assertEqual(len(self.runtime.store.load_executions()), initial + 1)
        protection = self.runtime.store.get_protection_projection(self.key)
        self.assertEqual(protection.stop_loss, Decimal("64000"))
        self.assertEqual(protection.take_profit, Decimal("65300"))
        self.assertIsNone(self.runtime.store.get_robot_trade(self.trade_id).exit_time_ms)
        record = self.runtime.store.get_robot_candidate(self.candidate_id)
        intent = record.robot_state["execution"]["wedge_be_partial_intent"]
        self.assertTrue(intent["reduce_only_required"])
        self.assertEqual(intent["partial_quantity"], str(partial))
        # The same candidate can never dispatch a second partial, even if a
        # caller replays a different quote/source event.
        second = self.run_partial()
        self.assertEqual(second.status, CommandResultStatus.UNKNOWN)
        self.assertEqual(len(self.runtime.store.load_executions()), initial + 1)

    def test_unconfirmed_m1_or_protection_collision_does_not_latch_or_execute(self):
        before = len(self.runtime.store.load_executions())
        result = self.run_partial(candle_high=Decimal("64700"))
        self.assertEqual(result.status, CommandResultStatus.BLOCKED)
        self.assertEqual(len(self.runtime.store.load_executions()), before)
        record = self.runtime.store.get_robot_candidate(self.candidate_id)
        self.assertNotIn("wedge_be_partial_intent", record.robot_state["execution"])
        result = self.run_partial(candle_high=Decimal("65400"))
        self.assertEqual(result.status, CommandResultStatus.BLOCKED)
        self.assertEqual(len(self.runtime.store.load_executions()), before)

    def test_invalid_future_m1_rejected_before_any_intent(self):
        before = len(self.runtime.store.load_executions())
        with self.assertRaises(Exception):
            self.run_partial(
                candle_open_ms=self.minute + 120000,
                candle_end_ms=self.minute + 180000,
            )
        self.assertEqual(len(self.runtime.store.load_executions()), before)
        self.assertNotIn(
            "wedge_be_partial_intent",
            self.runtime.store.get_robot_candidate(self.candidate_id).robot_state["execution"],
        )


    def test_partial_then_native_stop_closes_full_trade_with_all_fills_and_fees(self):
        """Authoritative STOP after a reduce-only partial must close only remaining lot.

        Campaign risk/Diary must receive the sum of BOTH exits, not just the
        last STOP event. Repeat event/restart must not double-book economics.
        """
        from tests.test_robot_paper_acceptance import _event_book

        before = len(self.runtime.store.load_executions())
        self.assertEqual(self.run_partial().status, CommandResultStatus.COMPLETED)
        reconcile = self.runtime._robot_wedge_be_reconcile_partial(
            self.candidate_id,
            book=_crossing_book(self.symbol.value, bid="64800", ask="64800.5"),
            worst_case_slippage_ticks=2,
        )
        self.assertEqual(reconcile.status, CommandResultStatus.COMPLETED)
        protection = self.runtime.store.get_protection_projection(self.key)
        self.assertGreater(protection.stop_loss, Decimal("64000"))
        stop_bid = protection.stop_loss - Decimal("0.5")
        crossing = _event_book(
            self.symbol.value, bid=stop_bid, ask=protection.stop_loss,
        )
        result = self.runtime.evaluate_robot_protection_crossing(
            self.symbol.value, crossing,
            event_id="partial-then-native-stop",
            received_at_ms=crossing.received_at_ms,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "RESOLVED")
        trade = self.runtime.store.get_robot_trade(self.trade_id)
        self.assertEqual(trade.exit_reason, "STOP")
        self.assertIsNotNone(trade.exit_time_ms)
        position = self.runtime.store.get_position_projection(self.key)
        self.assertEqual(position.quantity.value, Decimal("0"))
        self.assertEqual(position.side.value, "Flat")
        fills = self.runtime.store.load_executions_for_symbol(
            self.account, self.symbol,
        )
        self.assertEqual(len(fills), before + 2)
        self.assertEqual(
            sum((f.quantity.value for f in fills[1:]), Decimal("0")),
            self.initial,
        )
        expected_gross = sum(
            (fill.quantity.value * (fill.price.value - trade.average_entry)
             for fill in fills[1:]), Decimal("0"),
        )
        expected_fees = sum((fill.fee for fill in fills), Decimal("0"))
        self.assertEqual(trade.realized_pnl_usdt, expected_gross)
        self.assertEqual(trade.fees_costs_usdt, expected_fees)
        self.assertEqual(
            trade.realized_pnl_pct,
            (expected_gross - expected_fees)
            / (trade.entry_quantity * trade.average_entry) * Decimal("100"),
        )
        repeated = self.runtime.evaluate_robot_protection_crossing(
            self.symbol.value, crossing,
            event_id="partial-then-native-stop",
            received_at_ms=crossing.received_at_ms,
        )
        self.assertIsNone(repeated)
        self.assertEqual(
            len(self.runtime.store.load_executions_for_symbol(
                self.account, self.symbol,
            )),
            before + 2,
        )

    def test_partial_unproven_stops_at_existing_protection_obligation(self):
        """An unknown/foreign partial cannot authorize remainder STOP dispatch."""
        from unittest.mock import patch
        from tests.test_robot_paper_acceptance import _event_book

        self.assertEqual(self.run_partial().status, CommandResultStatus.COMPLETED)
        protection = self.runtime.store.get_protection_projection(self.key)
        crossing = _event_book(
            self.symbol.value, bid=protection.stop_loss - Decimal("0.5"),
            ask=protection.stop_loss,
        )
        actual = self.runtime.store.get_command
        def contradict(command_id):
            command = actual(command_id)
            if command is not None and command.command_kind == "create_market":
                return None
            return command
        before = len(self.runtime.store.load_executions())
        with patch.object(self.runtime.store, "get_command", side_effect=contradict):
            result = self.runtime.evaluate_robot_protection_crossing(
                self.symbol.value, crossing,
                event_id="unproven-partial-stop",
                received_at_ms=crossing.received_at_ms,
            )
        self.assertIsNotNone(result)
        self.assertNotEqual(result.status, "RESOLVED")
        self.assertEqual(len(self.runtime.store.load_executions()), before)
        self.assertIsNone(self.runtime.store.get_robot_trade(self.trade_id).exit_time_ms)
        self.assertGreater(
            self.runtime.store.get_position_projection(self.key).quantity.value,
            Decimal("0"),
        )
        # Restoring the original command proves that SAME durable STOP may
        # dispatch exactly once; no fresh trading intent is introduced.
        retry = self.runtime.evaluate_robot_protection_crossing(
            self.symbol.value, crossing,
            event_id="unproven-partial-stop",
            received_at_ms=crossing.received_at_ms,
        )
        self.assertIsNotNone(retry)
        self.assertEqual(retry.status, "RESOLVED")
        self.assertEqual(len(self.runtime.store.load_executions()), before + 1)

    def test_verified_partial_tightens_stop_once_using_actual_execution_fees(self):
        initial_executions = len(self.runtime.store.load_executions())
        self.assertEqual(self.run_partial().status, CommandResultStatus.COMPLETED)
        book_after_fill = _crossing_book(
            self.symbol.value, bid="64800", ask="64800.5",
        )
        response = self.runtime._robot_wedge_be_reconcile_partial(
            self.candidate_id, book=book_after_fill,
            worst_case_slippage_ticks=2,
        )
        self.assertEqual(response.status, CommandResultStatus.COMPLETED)
        protection = self.runtime.store.get_protection_projection(self.key)
        self.assertGreater(protection.stop_loss, Decimal("64000"))
        self.assertLess(protection.stop_loss, Decimal("64800"))
        self.assertEqual(protection.take_profit, Decimal("65300"))
        self.assertIsNone(self.runtime.store.get_robot_trade(self.trade_id).exit_time_ms)
        persisted = self.runtime.store.get_robot_candidate(self.candidate_id)
        stop_intent = persisted.robot_state["execution"]["wedge_be_stop_intent"]
        self.assertEqual(str(protection.stop_loss), stop_intent["stop_price"])
        # Reconciliation is a durable projection read, not another STOP
        # command and absolutely not another partial market execution.
        repeated = self.runtime._robot_wedge_be_reconcile_partial(
            self.candidate_id,
            book=_crossing_book(self.symbol.value, bid="64801", ask="64801.5"),
            worst_case_slippage_ticks=2,
        )
        self.assertEqual(repeated.status, CommandResultStatus.COMPLETED)
        self.assertEqual(
            self.runtime.store.get_protection_projection(self.key).stop_loss,
            protection.stop_loss,
        )
        self.assertEqual(
            len(self.runtime.store.load_executions()), initial_executions + 1,
        )

    def test_unknown_stop_result_does_not_replay_amendment(self):
        from unittest.mock import patch

        self.assertEqual(self.run_partial().status, CommandResultStatus.COMPLETED)
        from terminal.api.models import PaperStopMutationResult
        fake_unknown = PaperStopMutationResult(
            "fake-be-stop", CommandResultStatus.UNKNOWN, "unknown",
        )
        with patch.object(self.runtime, "_robot_amend_stop", return_value=fake_unknown) as amend:
            result = self.runtime._robot_wedge_be_reconcile_partial(
                self.candidate_id,
                book=_crossing_book(self.symbol.value, bid="64800", ask="64800.5"),
                worst_case_slippage_ticks=2,
            )
            self.assertEqual(result.status, CommandResultStatus.UNKNOWN)
            self.assertEqual(amend.call_count, 1)
            result = self.runtime._robot_wedge_be_reconcile_partial(
                self.candidate_id,
                book=_crossing_book(self.symbol.value, bid="64800", ask="64800.5"),
                worst_case_slippage_ticks=2,
            )
            self.assertEqual(result.status, CommandResultStatus.UNKNOWN)
            self.assertEqual(amend.call_count, 1)
        protection = self.runtime.store.get_protection_projection(self.key)
        self.assertEqual(protection.stop_loss, Decimal("64000"))
        self.assertEqual(protection.take_profit, Decimal("65300"))

    def _enable_auto(self):
        self.runtime._wedge_be_auto_paper_enabled = True
        monitor = self.runtime._robot_breakout_monitor
        monitor._wedge_be_auto_paper_enabled = True
        monitor._get_closed_candle = lambda symbol: {
            "time_ms": self.minute + 60000,
            "high": 64800, "low": 64600, "close": 64800,
        } if symbol == self.symbol.value else None
        return monitor

    def test_wedge_auto_default_off_prevents_any_market_or_stop_command(self):
        from unittest.mock import patch

        monitor = self.runtime._robot_breakout_monitor
        original = len(self.runtime.store.load_executions())
        with patch.object(monitor, "_get_closed_candle", side_effect=AssertionError("auto disabled")):
            self.assertEqual(monitor.tick(), ())
        self.assertEqual(len(self.runtime.store.load_executions()), original)
        self.assertNotIn(
            "wedge_be_partial_intent",
            self.runtime.store.get_robot_candidate(self.candidate_id).robot_state["execution"],
        )

    def test_automatic_closed_m1_then_next_tick_reconciles_stop_once(self):
        from unittest.mock import patch

        monitor = self._enable_auto()
        initial_executions = len(self.runtime.store.load_executions())
        with patch.object(self.runtime, "_streamed_book", side_effect=lambda symbol:
                          _crossing_book(self.symbol.value, bid="64800", ask="64800.5")):
            self.assertEqual(monitor.tick(), (self.candidate_id,))
            self.assertEqual(len(self.runtime.store.load_executions()), initial_executions + 1)
            after_partial = self.runtime.store.get_protection_projection(self.key)
            self.assertEqual(after_partial.stop_loss, Decimal("64000"))
            self.assertEqual(monitor.tick(), (self.candidate_id,))
            protected = self.runtime.store.get_protection_projection(self.key)
            self.assertGreater(protected.stop_loss, Decimal("64000"))
            self.assertEqual(protected.take_profit, Decimal("65300"))
            self.assertEqual(monitor.tick(), (self.candidate_id,))
        self.assertEqual(len(self.runtime.store.load_executions()), initial_executions + 1)
        self.assertEqual(
            self.runtime.store.get_protection_projection(self.key).stop_loss,
            protected.stop_loss,
        )

    def test_auto_rejects_unclosed_or_stale_m1_without_dispatch(self):
        from unittest.mock import patch

        monitor = self._enable_auto()
        initial_executions = len(self.runtime.store.load_executions())
        with patch.object(self.runtime, "_streamed_book", side_effect=lambda symbol:
                          _crossing_book(self.symbol.value, bid="64800", ask="64800.5")):
            monitor._get_closed_candle = lambda _: {
                "time_ms": self.minute + 120000, "high": 64800,
                "low": 64600, "close": 64800,
            }
            self.assertEqual(monitor.tick(), ())
            monitor._get_closed_candle = lambda _: {
                "time_ms": self.minute - 300000, "high": 64800,
                "low": 64600, "close": 64800,
            }
            self.assertEqual(monitor.tick(), ())
        self.assertEqual(len(self.runtime.store.load_executions()), initial_executions)

    def test_auto_recovery_never_resubmits_unknown_partial(self):
        from unittest.mock import patch
        from terminal.api.models import CommandResult

        monitor = self._enable_auto()
        original = len(self.runtime.store.load_executions())
        unknown = CommandResult(
            "unknown-be", CommandResultStatus.UNKNOWN, "unknown", "owner outcome unknown",
            None, True,
        )
        with patch.object(self.runtime, "_streamed_book", side_effect=lambda symbol:
                          _crossing_book(self.symbol.value, bid="64800", ask="64800.5")):
            with patch.object(self.runtime._robot_api, "full_close", return_value=unknown) as send:
                self.assertEqual(monitor.tick(), ())
                self.assertEqual(send.call_count, 1)
                self.assertEqual(monitor.tick(), ())
                self.assertEqual(send.call_count, 1)
        self.assertEqual(len(self.runtime.store.load_executions()), original)
        self.assertIn(
            "wedge_be_partial_intent",
            self.runtime.store.get_robot_candidate(self.candidate_id).robot_state["execution"],
        )

    def test_reopened_runtime_never_resubmits_unknown_latched_partial(self):
        """Crash after durable intent but before command receipt: no retry."""
        from unittest.mock import patch
        from terminal.api.models import CommandResult

        monitor = self._enable_auto()
        unknown = CommandResult(
            "unknown-be", CommandResultStatus.UNKNOWN,
            "mutation_unknown", "partial command not proven", None, True,
        )
        with patch.object(
            self.runtime, "_streamed_book",
            side_effect=lambda symbol: _crossing_book(
                self.symbol.value, bid="64800", ask="64800.5",
            ),
        ), patch.object(
            self.runtime._robot_api, "full_close", return_value=unknown,
        ) as dispatch:
            self.assertEqual(monitor.tick(), ())
            self.assertEqual(dispatch.call_count, 1)
        immutable = dict(
            self.runtime.store.get_robot_candidate(self.candidate_id)
            .robot_state["execution"]["wedge_be_partial_intent"]
        )
        self.runtime.close()
        reopened = _runtime(self.db)
        self.addCleanup(reopened.close)
        reopened._wedge_be_auto_paper_enabled = True
        with patch.object(
            reopened._robot_api, "full_close",
            side_effect=AssertionError("durable BE intent must not resubmit"),
        ):
            state = reopened._robot_wedge_be_auto_step(
                self.candidate_id, symbol=self.symbol.value, candle=None,
                book=_crossing_book(self.symbol.value, bid="64801", ask="64801.5"),
            )
        self.assertEqual(state.status, CommandResultStatus.UNKNOWN)
        self.assertEqual(
            reopened.store.get_robot_candidate(self.candidate_id)
            .robot_state["execution"]["wedge_be_partial_intent"],
            immutable,
        )
        self.assertEqual(
            reopened.store.get_protection_projection(self.key).stop_loss,
            Decimal("64000"),
        )
        self.assertEqual(
            len(reopened.store.load_executions_for_symbol(self.account, self.symbol)),
            1,
        )

    def test_restart_after_partial_rejects_unproven_intent(self):
        from terminal.application.robot_recovery import RobotRecoveryCoordinator

        self.assertEqual(self.run_partial().status, CommandResultStatus.COMPLETED)
        record = self.runtime.store.get_robot_candidate(self.candidate_id)
        state = dict(record.robot_state)
        execution = dict(state["execution"])
        intent = dict(execution["wedge_be_partial_intent"])
        intent["partial_quantity"] = str(self.initial)
        execution["wedge_be_partial_intent"] = intent
        state["execution"] = execution
        self.runtime.store.save_robot_candidate_state(
            self.candidate_id, status="OPEN", robot_state=state,
            expected_revision=record.state_revision, updated_at_ms=int(time.time() * 1000),
        )
        before = len(self.runtime.store.load_executions())
        result = RobotRecoveryCoordinator(
            self.runtime.store, self.account, clock_ms=lambda: int(time.time() * 1000),
        ).recover()
        self.assertFalse(result.admission_ready)
        self.assertEqual(result.runtime_state.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertEqual(len(self.runtime.store.load_executions()), before)
        self.assertEqual(self.runtime.store.get_protection_projection(self.key).stop_loss,
                         Decimal("64000"))

    def test_reopened_runtime_resumes_filled_partial_to_tighter_stop_once(self):
        """Recovered filled partial gets STOP after independent READY proof."""
        from unittest.mock import patch

        self.assertEqual(self.run_partial().status, CommandResultStatus.COMPLETED)
        before = len(self.runtime.store.load_executions_for_symbol(
            self.account, self.symbol,
        ))
        self.assertEqual(
            self.runtime.store.get_protection_projection(self.key).stop_loss,
            Decimal("64000"),
        )
        self.runtime.close()
        reopened = _runtime(self.db)
        self.addCleanup(reopened.close)
        from terminal.application.robot_recovery import RobotRecoveryCoordinator
        recovered = RobotRecoveryCoordinator(
            reopened.store, self.account, clock_ms=lambda: int(time.time() * 1000),
        ).recover()
        self.assertTrue(recovered.admission_ready, recovered.runtime_state.reason)
        reopened._wedge_be_auto_paper_enabled = True
        with patch.object(
            reopened._robot_api, "full_close",
            side_effect=AssertionError("filled BE must not issue a new partial"),
        ):
            result = reopened._robot_wedge_be_auto_step(
                self.candidate_id, symbol=self.symbol.value, candle=None,
                book=_crossing_book(self.symbol.value, bid="64800", ask="64800.5"),
            )
        self.assertEqual(result.status, CommandResultStatus.COMPLETED)
        protection = reopened.store.get_protection_projection(self.key)
        self.assertGreater(protection.stop_loss, Decimal("64000"))
        self.assertEqual(protection.take_profit, Decimal("65300"))
        self.assertEqual(
            len(reopened.store.load_executions_for_symbol(self.account, self.symbol)),
            before,
        )
        again = reopened._robot_wedge_be_auto_step(
            self.candidate_id, symbol=self.symbol.value, candle=None,
            book=_crossing_book(self.symbol.value, bid="64800", ask="64800.5"),
        )
        self.assertEqual(again.status, CommandResultStatus.COMPLETED)
        self.assertEqual(
            reopened.store.get_protection_projection(self.key).stop_loss,
            protection.stop_loss,
        )



class RobotBeShortOwnerPaperTests(unittest.TestCase):
    """SHORT mirror of the real PAPER owner path, not only math helpers."""

    def setUp(self):
        from terminal.api.models import (
            ClientActionId, CommandResultStatus, LimitCommandRequest,
            PaperStopMutationRequest, TimeInForce, VolumeRequest, VolumeUnit,
        )
        from terminal.domain.models import OrderSide
        from terminal.runtime.paper_runtime import RobotPaperActionExecutor

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "be-short.sqlite3"
        self.runtime = _runtime(self.db)
        self.addCleanup(self.runtime.close)
        self.account = TradingAccountId("paper")
        self.symbol = Symbol("BTCUSDT")
        self.candidate_id = "wedge-be-short-owner"
        self.trade_id = "robot-trade-wedge-be-short-owner"
        now_ms = int(time.time() * 1000)
        self.minute = (now_ms // 60000 - 2) * 60000
        self.runtime._limit_executor.clock_ms = lambda: self.minute + 30000
        self.runtime._robot_command_dispatcher = lambda operation: operation(self.runtime)
        executor = RobotPaperActionExecutor(self.runtime)
        price = Decimal("64249.5")
        submitted = self.runtime._create_limit(
            LimitCommandRequest(
                ClientActionId(self.trade_id + "-limit"), self.symbol.value,
                OrderSide.SELL, VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                price, price, TimeInForce.GTC,
            ), self.runtime._robot_context,
        )
        self.assertEqual(submitted.status, CommandResultStatus.COMPLETED)
        self.assertEqual(self.runtime.robot_match_symbol(self.symbol.value), 1)
        executor.create_stop(PaperStopMutationRequest(
            ClientActionId(self.trade_id + "-stop"), self.symbol.value, Decimal("64500"),
        ))
        executor.create_take(PaperStopMutationRequest(
            ClientActionId(self.trade_id + "-take"), self.symbol.value, Decimal("63400"),
        ))
        self.runtime.store.create_robot_candidate(
            candidate_id=self.candidate_id, trading_account_id=self.account,
            symbol=self.symbol, status="APPROVED",
            signal_snapshot={"symbol": self.symbol.value, "pattern": "Rising Wedge"},
            approved_at_ms=1000, updated_at_ms=1000,
        )
        self.key = PositionKey(self.account, Category.LINEAR, self.symbol, 0)
        projection = self.runtime.store.get_position_projection(self.key)
        self.initial_quantity = projection.quantity.value
        self.runtime.store.create_robot_trade(
            trade_id=self.trade_id, trading_account_id=self.account,
            candidate_id=self.candidate_id, symbol=self.symbol, direction="SHORT",
            pattern="Rising Wedge", source_timeframe="1", signal_time_ms=900,
            entry_time_ms=1500, entry_path="LIMIT", actual_wv=Decimal("0.8"),
            average_entry=price, stop_price=Decimal("64500"),
            take_price=Decimal("63400"), entry_quantity=self.initial_quantity,
            entry_position_version=projection.version, created_at_ms=1500,
        )
        candidate = self.runtime.store.get_robot_candidate(self.candidate_id)
        fills = self.runtime.store.load_executions_for_symbol(self.account, self.symbol)
        self.assertEqual(len(fills), 1)
        self.runtime.store.save_robot_candidate_state(
            self.candidate_id, status="OPEN",
            robot_state={
                "phase": "OPEN", "direction": "SHORT",
                "execution": {"limit_order_id": fills[0].order_id.value},
            },
            expected_revision=candidate.state_revision,
            updated_at_ms=int(time.time() * 1000),
        )
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")

    def _book(self, *, bid="63700", ask="63700.5"):
        return _crossing_book(self.symbol.value, bid=bid, ask=ask)

    def _partial(self, *, book=None):
        return self.runtime._robot_wedge_be_partial_once(
            self.candidate_id, candle_open_ms=self.minute + 60000,
            candle_end_ms=self.minute + 120000,
            candle_high=Decimal("64000"), candle_low=Decimal("63650"),
            book=self._book() if book is None else book,
        )

    def _enable_auto(self):
        self.runtime._wedge_be_auto_paper_enabled = True
        monitor = self.runtime._robot_breakout_monitor
        monitor._wedge_be_auto_paper_enabled = True
        monitor._get_closed_candle = lambda symbol: {
            "time_ms": self.minute + 60000, "high": 64000,
            "low": 63650, "close": 63700,
        } if symbol == self.symbol.value else None
        return monitor

    def test_short_closed_m1_partial_then_fee_aware_stop_once(self):
        from unittest.mock import patch
        from terminal.domain.models import PositionSide

        monitor = self._enable_auto()
        count_before = len(self.runtime.store.load_executions())
        with patch.object(self.runtime, "_streamed_book", side_effect=lambda _: self._book()):
            self.assertEqual(monitor.tick(), (self.candidate_id,))
            after_partial = self.runtime.store.get_position_projection(self.key)
            self.assertIs(after_partial.side, PositionSide.SHORT)
            self.assertLess(after_partial.quantity.value, self.initial_quantity)
            self.assertGreater(after_partial.quantity.value, Decimal(0))
            self.assertEqual(len(self.runtime.store.load_executions()), count_before + 1)
            self.assertEqual(
                self.runtime.store.get_protection_projection(self.key).stop_loss,
                Decimal("64500"),
            )
            self.assertEqual(monitor.tick(), (self.candidate_id,))
            tightened = self.runtime.store.get_protection_projection(self.key)
            self.assertLess(tightened.stop_loss, Decimal("64500"))
            self.assertGreater(tightened.stop_loss, Decimal("63700.5"))
            self.assertEqual(tightened.take_profit, Decimal("63400"))
            self.assertEqual(monitor.tick(), (self.candidate_id,))
        self.assertEqual(len(self.runtime.store.load_executions()), count_before + 1)
        self.assertEqual(
            self.runtime.store.get_protection_projection(self.key).stop_loss,
            tightened.stop_loss,
        )
        self.assertIsNone(self.runtime.store.get_robot_trade(self.trade_id).exit_time_ms)
        intent = self.runtime.store.get_robot_candidate(
            self.candidate_id,
        ).robot_state["execution"]["wedge_be_partial_intent"]
        self.assertTrue(intent["reduce_only_required"])

    def test_short_partial_then_native_stop_accounts_all_fills_once(self):
        """Synthetic SHORT partial -> fee-aware STOP -> FLAT, canonical Diary PnL."""
        from tests.test_robot_paper_acceptance import _event_book

        before = len(self.runtime.store.load_executions_for_symbol(
            self.account, self.symbol,
        ))
        self.assertEqual(self._partial().status, CommandResultStatus.COMPLETED)
        reconciled = self.runtime._robot_wedge_be_reconcile_partial(
            self.candidate_id, book=self._book(), worst_case_slippage_ticks=2,
        )
        self.assertEqual(reconciled.status, CommandResultStatus.COMPLETED)
        protection = self.runtime.store.get_protection_projection(self.key)
        self.assertLess(protection.stop_loss, Decimal("64500"))
        self.assertGreater(protection.stop_loss, Decimal("63700.5"))
        self.assertEqual(protection.take_profit, Decimal("63400"))

        # The next book crosses the amended SHORT STOP; only the remainder
        # closes. A repeated source event must not double-book fills or fees.
        crossing = _event_book(
            self.symbol.value, bid=protection.stop_loss,
            ask=protection.stop_loss + Decimal("0.5"),
        )
        event_id = "short-partial-then-native-stop"
        outcome = self.runtime.evaluate_robot_protection_crossing(
            self.symbol.value, crossing, event_id=event_id,
            received_at_ms=crossing.received_at_ms,
        )
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.status, "RESOLVED")
        trade = self.runtime.store.get_robot_trade(self.trade_id)
        self.assertEqual(trade.exit_reason, "STOP")
        self.assertIsNotNone(trade.exit_time_ms)
        position = self.runtime.store.get_position_projection(self.key)
        self.assertEqual(position.quantity.value, Decimal("0"))
        self.assertEqual(position.side.value, "Flat")
        fills = self.runtime.store.load_executions_for_symbol(
            self.account, self.symbol,
        )
        self.assertEqual(len(fills), before + 2)
        self.assertEqual(
            sum((fill.quantity.value for fill in fills[1:]), Decimal("0")),
            self.initial_quantity,
        )
        expected_gross = sum(
            ((trade.average_entry - fill.price.value) * fill.quantity.value
             for fill in fills[1:]), Decimal("0"),
        )
        expected_fees = sum((fill.fee for fill in fills), Decimal("0"))
        self.assertEqual(trade.realized_pnl_usdt, expected_gross)
        self.assertEqual(trade.fees_costs_usdt, expected_fees)
        self.assertEqual(
            trade.realized_pnl_pct,
            (expected_gross - expected_fees)
            / (trade.entry_quantity * trade.average_entry) * Decimal("100"),
        )
        repeated = self.runtime.evaluate_robot_protection_crossing(
            self.symbol.value, crossing, event_id=event_id,
            received_at_ms=crossing.received_at_ms,
        )
        self.assertIsNone(repeated)
        self.assertEqual(
            len(self.runtime.store.load_executions_for_symbol(
                self.account, self.symbol,
            )),
            before + 2,
        )

    def test_short_retraced_quote_does_not_latch_or_execute(self):
        # Closed M1 low crossed +2R, but the current executable ask did not.
        before = len(self.runtime.store.load_executions())
        result = self._partial(book=self._book(bid="63800", ask="63800.5"))
        self.assertEqual(result.status, CommandResultStatus.BLOCKED)
        self.assertEqual(result.reason_code, "be_quote_retraced")
        self.assertEqual(len(self.runtime.store.load_executions()), before)
        self.assertNotIn(
            "wedge_be_partial_intent",
            self.runtime.store.get_robot_candidate(self.candidate_id)
            .robot_state["execution"],
        )

    def test_short_filled_partial_restart_tightens_without_reorder(self):
        from unittest.mock import patch

        self.assertEqual(self._partial().status, CommandResultStatus.COMPLETED)
        count_before = len(self.runtime.store.load_executions())
        self.assertEqual(self.runtime.store.get_protection_projection(self.key).stop_loss,
                         Decimal("64500"))
        self.runtime.close()
        reopened = _runtime(self.db)
        self.addCleanup(reopened.close)
        from terminal.application.robot_recovery import RobotRecoveryCoordinator
        recovered = RobotRecoveryCoordinator(
            reopened.store, self.account, clock_ms=lambda: int(time.time() * 1000),
        ).recover()
        self.assertTrue(recovered.admission_ready, recovered.runtime_state.reason)
        reopened._wedge_be_auto_paper_enabled = True
        with patch.object(
            reopened._robot_api, "full_close",
            side_effect=AssertionError("filled SHORT partial must never resubmit"),
        ):
            outcome = reopened._robot_wedge_be_auto_step(
                self.candidate_id, symbol=self.symbol.value, candle=None,
                book=self._book(),
            )
        self.assertEqual(outcome.status, CommandResultStatus.COMPLETED)
        stop = reopened.store.get_protection_projection(self.key).stop_loss
        self.assertLess(stop, Decimal("64500"))
        self.assertGreater(stop, Decimal("63700.5"))
        self.assertEqual(len(reopened.store.load_executions()), count_before)
        again = reopened._robot_wedge_be_auto_step(
            self.candidate_id, symbol=self.symbol.value, candle=None, book=self._book(),
        )
        self.assertEqual(again.status, CommandResultStatus.COMPLETED)
        self.assertEqual(reopened.store.get_protection_projection(self.key).stop_loss, stop)
        self.assertEqual(len(reopened.store.load_executions()), count_before)

if __name__ == "__main__":
    unittest.main()
