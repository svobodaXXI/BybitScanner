"""PAPER account-wide Close-All coordinates admission, entry LIMITs and owners.

Synthetic serialized owner only. No real DB, backend, Telegram, exchange, or LIVE.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal.api.models import (
    ClientActionId, CloseAllCommandRequest, CloseAllCommandResponse,
    CommandResult, CommandResultStatus,
)
from terminal.domain.models import OrderId, OrderSide, PositionSide, Symbol, TradingAccountId
from terminal.runtime.paper_runtime import PaperCloseAllRejected, PaperRuntime

ACCOUNT = TradingAccountId("paper")


def position(name, side=PositionSide.LONG):
    return SimpleNamespace(position_key=SimpleNamespace(symbol=Symbol(name)), side=side)


def limit(name, symbol="MANUALUSDT", side=OrderSide.BUY):
    return SimpleNamespace(order_id=OrderId(name), symbol=Symbol(symbol), side=side)


def candidate(symbol="BOTUSDT"):
    return SimpleNamespace(
        candidate_id="candidate-bot", symbol=Symbol(symbol), status="OPEN",
    )


def trade(symbol="BOTUSDT"):
    return SimpleNamespace(
        trade_id="trade-bot", candidate_id="candidate-bot", symbol=Symbol(symbol),
    )


def response(results=(), positions=()):
    return CloseAllCommandResponse("confirmed-owner-action", tuple(results), tuple(positions))


def completed(action="robot-close"):
    return CommandResult(action, CommandResultStatus.COMPLETED, "closed", "closed")


def fixture(
    *, mode="ROBOT_RUNNING", status="READY", robot=False,
    manual=True, orders=(), obligations=(),
):
    initial_positions = ([position("BOTUSDT")] if robot else []) + (
        [position("MANUALUSDT")] if manual else []
    )
    state = SimpleNamespace(
        mode=mode, recovery_status=status, version=4, updated_at_ms=0,
    )
    autopilot = SimpleNamespace(mode="PAPER_AUTO", version=3, updated_at_ms=0)
    current = {"robot": state, "trades": (trade(),) if robot else (), "limits": list(orders)}

    def update_robot(account, *, mode, recovery_status, reason, expected_version, updated_at_ms):
        assert expected_version == current["robot"].version
        new = SimpleNamespace(
            mode=mode, recovery_status=recovery_status,
            reason=reason, version=expected_version + 1, updated_at_ms=updated_at_ms,
        )
        current["robot"] = new
        return new

    candidates = (candidate(),) if robot else ()
    store = SimpleNamespace(
        get_robot_runtime_state=Mock(side_effect=lambda account: current["robot"]),
        update_robot_runtime_state=Mock(side_effect=update_robot),
        get_robot_autopilot_state=Mock(return_value=autopilot),
        update_robot_autopilot_state=Mock(),
        load_robot_candidates_by_status=Mock(return_value=candidates),
        load_open_robot_trades=Mock(side_effect=lambda account: current["trades"]),
        load_active_robot_candidate_states=Mock(return_value=candidates),
        load_active_robot_entry_orders=Mock(return_value={}),
        load_unresolved_paper_protection_obligations=Mock(return_value=tuple(obligations)),
        load_open_position_projections=Mock(side_effect=lambda account: (
            tuple(initial_positions) if current["trades"] or not robot else (
                (position("MANUALUSDT"),) if manual else ()
            )
        )),
        load_active_paper_limits_for_account=Mock(
            side_effect=lambda account: tuple(current["limits"]),
        ),
    )
    # A successful Robot close removes that one durable owner before manual
    # close, as the production close_robot_trade transaction does.
    def close_robot(request, **kwargs):
        current["trades"] = ()
        return response((completed(),))
    runtime = SimpleNamespace(
        _paper_account_id=ACCOUNT, store=store,
        require_paper_mutations=Mock(),
        robot_synchronize_pending_entries=Mock(return_value=SimpleNamespace(
            unresolved_candidate_ids=(), still_pending_protection=(),
        )),
        robot_close_all=Mock(side_effect=close_robot),
        robot_reconcile=Mock(return_value=SimpleNamespace(success=False)),
        close_all=Mock(return_value=response(
            (completed("manual-close"),) if manual else (),
        )),
        _robot_cancel_limit=Mock(side_effect=lambda request: (
            current["limits"].__setitem__(
                slice(None), [item for item in current["limits"]
                              if item.order_id.value != request.order_id],
            )
            or SimpleNamespace(status=CommandResultStatus.COMPLETED)
        )),
        open_positions=Mock(return_value=SimpleNamespace(positions=())),
    )
    # The production runtime owns this read-only formatter; the synthetic
    # SimpleNamespace owner must expose the same method for integration tests.
    runtime._paper_close_all_symbol_reports = (
        lambda request, before, trades: PaperRuntime._paper_close_all_symbol_reports(
            runtime, request, before, trades,
        )
    )
    runtime._robot_linked_entry_limits = Mock(return_value={})
    runtime._cancel_robot_entries_for_account_flatten = (
        lambda action_id: PaperRuntime._cancel_robot_entries_for_account_flatten(
            runtime, action_id,
        )
    )
    return runtime, current


def run(runtime):
    return PaperRuntime.coordinated_paper_close_all(
        runtime, CloseAllCommandRequest(ClientActionId("confirmed-owner-action")),
    )


class CoordinatedPaperCloseAllTests(unittest.TestCase):
    def test_ready_robot_is_paused_and_autopilot_off_before_market_dispatch(self):
        runtime, state = fixture(robot=True, manual=True)
        def close_robot(request, **kwargs):
            self.assertEqual(state["robot"].recovery_status, "PAUSED")
            runtime.store.update_robot_autopilot_state.assert_called_once()
            state["trades"] = ()
            return response((completed(),))
        runtime.robot_close_all.side_effect = close_robot
        result = run(runtime)
        self.assertEqual(len(result.results), 2)
        self.assertEqual(result.positions, ())
        runtime.robot_close_all.assert_called_once()
        runtime.close_all.assert_called_once()
        self.assertEqual(runtime.store.update_robot_runtime_state.call_args.kwargs["recovery_status"], "PAUSED")

    def test_robot_box_close_receives_off_owner_execution_evidence(self):
        runtime, state = fixture(robot=True, manual=False)
        book = object()
        run_request = CloseAllCommandRequest(ClientActionId("confirmed-owner-action"))
        PaperRuntime.coordinated_paper_close_all(
            runtime, run_request, evidence={"BOTUSDT": book},
        )
        self.assertIs(runtime.robot_close_all.call_args.kwargs["evidence"]["BOTUSDT"], book)

    def test_box_missing_fresh_book_preserves_exit_before_market_dispatch(self):
        runtime = SimpleNamespace(
            _paper_account_id=ACCOUNT,
            store=SimpleNamespace(
                get_open_robot_trade_for_symbol=Mock(return_value=SimpleNamespace(
                    candidate_id="box-child",
                )),
                get_robot_candidate=Mock(return_value=SimpleNamespace(
                    status="BOX_PLAN_ONLY", candidate_id="box-source",
                )),
                prove_box_owned_position=Mock(return_value=SimpleNamespace(
                    remaining_quantity=Decimal("519.2"),
                )),
                reserve_box_order_identity=Mock(),
                cancel_paper_limit=Mock(),
            ),
            _fresh_box_close_book=Mock(return_value=None),
            _robot_api=SimpleNamespace(market=Mock()),
        )
        box = SimpleNamespace(
            candidate_id="box-child", symbol=Symbol("BOTUSDT"),
            signal_snapshot={"source_box_candidate_id": "box-source"},
        )
        result = PaperRuntime._robot_close_box_candidate(runtime, box)
        self.assertEqual(result.status, CommandResultStatus.UNAVAILABLE)
        self.assertEqual(result.reason_code, "box_close_fresh_book_unavailable")
        runtime.store.reserve_box_order_identity.assert_not_called()
        runtime.store.cancel_paper_limit.assert_not_called()
        runtime._robot_api.market.assert_not_called()

    def test_box_prefers_fresh_handler_evidence_over_stale_stream(self):
        symbol = Symbol("BOTUSDT")
        stale = SimpleNamespace(symbol=symbol, received_at_ms=5000)
        fresh = SimpleNamespace(symbol=symbol, received_at_ms=9900)
        def validate(request_symbol, book):
            if book is None or book.symbol != request_symbol:
                raise RuntimeError("unavailable")
            if not 0 <= 10000 - book.received_at_ms <= 1000:
                raise RuntimeError("stale")
        runtime = SimpleNamespace(
            _streamed_book=Mock(return_value=stale),
            _market_executor=SimpleNamespace(validate_book=Mock(side_effect=validate)),
        )
        selected = PaperRuntime._fresh_box_close_book(runtime, symbol, fresh)
        self.assertIs(selected, fresh)
        self.assertIsNone(PaperRuntime._fresh_box_close_book(runtime, symbol))

    def test_stop_mode_manual_only_uses_original_paper_path(self):
        runtime, _ = fixture(mode="ROBOT_STOPPED", status="ROBOT_STOPPED")
        result = run(runtime)
        self.assertEqual(len(result.results), 1)
        runtime.robot_close_all.assert_not_called()
        runtime.robot_synchronize_pending_entries.assert_not_called()
        runtime.close_all.assert_called_once()

    def test_preexisting_reconciliation_fence_blocks_market_dispatch(self):
        runtime, _ = fixture(status="RECONCILIATION_REQUIRED", robot=True)
        with self.assertRaisesRegex(PaperCloseAllRejected, "robot_reconciliation_required"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()

    def test_reconcile_failure_fences_autopilot_before_attempt(self):
        runtime, _ = fixture(status="RECONCILIATION_REQUIRED", robot=True)
        def reconcile():
            runtime.store.update_robot_autopilot_state.assert_called_once()
            return SimpleNamespace(success=False)
        runtime.robot_reconcile.side_effect = reconcile
        with self.assertRaisesRegex(PaperCloseAllRejected, "robot_reconciliation_required"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()

    def test_reconciliation_success_allows_canonical_close(self):
        runtime, state = fixture(status="RECONCILIATION_REQUIRED", robot=True)
        def reconcile():
            current = state["robot"]
            state["robot"] = SimpleNamespace(
                mode="ROBOT_RUNNING", recovery_status="PAUSED",
                version=current.version + 1, updated_at_ms=1,
            )
            return SimpleNamespace(success=True)
        runtime.robot_reconcile.side_effect = reconcile
        result = run(runtime)
        self.assertEqual(len(result.results), 2)
        runtime.robot_reconcile.assert_called_once()
        runtime.robot_close_all.assert_called_once()

    def test_reconcile_claim_without_paused_state_cannot_dispatch(self):
        runtime, _ = fixture(status="RECONCILIATION_REQUIRED", robot=True)
        runtime.robot_reconcile.return_value = SimpleNamespace(success=True)
        with self.assertRaisesRegex(PaperCloseAllRejected, "robot_reconciliation_required"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()

    def test_reconcile_stopped_mode_cannot_dispatch(self):
        runtime, state = fixture(status="RECONCILIATION_REQUIRED", robot=True)
        def reconcile():
            state["robot"] = SimpleNamespace(
                mode="ROBOT_STOPPED", recovery_status="PAUSED",
                version=5, updated_at_ms=1,
            )
            return SimpleNamespace(success=True)
        runtime.robot_reconcile.side_effect = reconcile
        with self.assertRaisesRegex(PaperCloseAllRejected, "robot_reconciliation_required"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()

    def test_malformed_reconcile_reply_cannot_dispatch(self):
        runtime, _ = fixture(status="RECONCILIATION_REQUIRED", robot=True)
        runtime.robot_reconcile.return_value = SimpleNamespace()
        with self.assertRaisesRegex(PaperCloseAllRejected, "robot_reconciliation_required"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()

    def test_reconcile_exception_preserves_fence_and_protection(self):
        runtime, _ = fixture(status="RECONCILIATION_REQUIRED", robot=True)
        runtime.robot_reconcile.side_effect = RuntimeError("unexpected recovery failure")
        with self.assertRaisesRegex(PaperCloseAllRejected, "robot_reconciliation_required"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()
        runtime.store.update_robot_runtime_state.assert_not_called()

    def test_orphan_trade_fails_closed_before_any_market_order(self):
        runtime, _ = fixture()
        runtime.store.load_open_robot_trades.return_value = (trade(),)
        # A side-effect is used for other tests; here replace it explicitly.
        runtime.store.load_open_robot_trades.side_effect = lambda account: (trade(),)
        with self.assertRaisesRegex(PaperCloseAllRejected, "robot_trade_ledger_unproven"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()
        self.assertEqual(runtime.store.get_robot_runtime_state(ACCOUNT).recovery_status,
                         "RECONCILIATION_REQUIRED")

    def _open_box_with_remaining_entries(self, *, status="READY"):
        entry = limit("box-entry", symbol="BOTUSDT", side=OrderSide.BUY)
        take = limit("box-exit", symbol="BOTUSDT", side=OrderSide.SELL)
        runtime, state = fixture(
            robot=True, manual=False, status=status, orders=(entry, take),
        )
        orders = {"box-entry": "open", "box-exit": "open"}
        runtime._robot_linked_entry_limits.return_value = {"box-entry": 4}
        runtime.store.load_active_robot_entry_orders.side_effect = lambda account: (
            {"box-entry": (Symbol("BOTUSDT"), 4)}
            if orders["box-entry"] == "open" else {}
        )
        runtime.store.get_paper_limit = Mock(side_effect=lambda order_id, account: (
            SimpleNamespace(symbol=Symbol("BOTUSDT"), status=orders[order_id])
            if order_id in orders else None
        ))
        def cancel(request):
            orders[request.order_id] = "cancelled"
            state["limits"] = [
                item for item in state["limits"]
                if item.order_id.value != request.order_id
            ]
            return SimpleNamespace(status=CommandResultStatus.COMPLETED)
        runtime._robot_cancel_limit.side_effect = cancel
        return runtime, state, orders

    def test_open_box_remaining_entry_is_cancelled_before_market_and_exit_survives_until_flat(self):
        runtime, state, orders = self._open_box_with_remaining_entries()
        def close_robot(request):
            self.assertEqual(orders["box-entry"], "cancelled")
            self.assertEqual(orders["box-exit"], "open")
            state["trades"] = ()
            return response((completed(),))
        runtime.robot_close_all.side_effect = close_robot
        result = run(runtime)
        self.assertFalse(result.positions)
        self.assertEqual(orders["box-exit"], "cancelled")
        self.assertEqual(
            [x.args[0].order_id for x in runtime._robot_cancel_limit.call_args_list],
            ["box-entry", "box-exit"],
        )

    def test_reconciliation_required_cancels_open_box_entry_before_reconcile(self):
        runtime, state, orders = self._open_box_with_remaining_entries(
            status="RECONCILIATION_REQUIRED",
        )
        def reconcile():
            self.assertEqual(orders["box-entry"], "cancelled")
            previous = state["robot"]
            state["robot"] = SimpleNamespace(
                mode="ROBOT_RUNNING", recovery_status="PAUSED",
                version=previous.version + 1, updated_at_ms=1,
            )
            return SimpleNamespace(success=True)
        runtime.robot_reconcile.side_effect = reconcile
        result = run(runtime)
        self.assertFalse(result.positions)
        runtime.robot_reconcile.assert_called_once()
        runtime.robot_close_all.assert_called_once()

    def test_unconfirmed_open_box_entry_cancel_never_dispatches_market(self):
        runtime, state, orders = self._open_box_with_remaining_entries()
        runtime._robot_cancel_limit.return_value = SimpleNamespace(
            status=CommandResultStatus.UNKNOWN,
        )
        runtime._robot_cancel_limit.side_effect = None
        with self.assertRaisesRegex(
            PaperCloseAllRejected, "robot_entry_limit_cancel_unconfirmed",
        ):
            run(runtime)
        self.assertEqual(orders["box-entry"], "open")
        self.assertEqual(orders["box-exit"], "open")
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()
        self.assertEqual(state["robot"].recovery_status, "RECONCILIATION_REQUIRED")

    def test_unresolved_protection_never_dispatches_market_close(self):
        runtime, _ = fixture(robot=True, obligations=(
            SimpleNamespace(trade_id="trade-bot"),
        ))
        with self.assertRaisesRegex(PaperCloseAllRejected, "robot_protection_obligation_unresolved"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()

    def test_failed_pending_robot_entry_sync_fences_and_stops(self):
        runtime, _ = fixture(robot=True)
        runtime.robot_synchronize_pending_entries.return_value = SimpleNamespace(
            unresolved_candidate_ids=("candidate-bot",), still_pending_protection=(),
        )
        with self.assertRaisesRegex(PaperCloseAllRejected, "pending_robot_entry_unresolved"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()

    def test_opening_limits_cancel_before_any_market_and_exit_limits_after_flat(self):
        entry = limit("entry", side=OrderSide.BUY)
        take = limit("take", side=OrderSide.SELL)
        runtime, _ = fixture(orders=(entry, take))
        def manual_close(request, **kwargs):
            requests = [x.args[0].order_id for x in runtime._robot_cancel_limit.call_args_list]
            self.assertIn("entry", requests)
            self.assertNotIn("take", requests)
            return response((completed("manual"),))
        runtime.close_all.side_effect = manual_close
        result = run(runtime)
        self.assertFalse(result.positions)
        requests = [x.args[0].order_id for x in runtime._robot_cancel_limit.call_args_list]
        self.assertEqual(requests, ["entry", "take"])
        self.assertEqual(runtime.store.load_active_paper_limits_for_account(ACCOUNT), ())

    def test_residual_position_preserves_exit_limit_and_non_success(self):
        take = limit("take", side=OrderSide.SELL)
        runtime, _ = fixture(orders=(take,))
        runtime.close_all.return_value = response(
            (CommandResult("manual", CommandResultStatus.UNKNOWN, "stale", "unconfirmed"),),
            (SimpleNamespace(symbol="MANUALUSDT", position_quantity=Decimal("1")),),
        )
        result = run(runtime)
        self.assertTrue(result.positions)
        runtime._robot_cancel_limit.assert_not_called()
        runtime.open_positions.assert_not_called()

    def test_failed_robot_close_blocks_manual_market_dispatch(self):
        runtime, state = fixture(robot=True)
        runtime.robot_close_all.side_effect = lambda request: response((
            CommandResult("robot", CommandResultStatus.UNKNOWN, "stale", "unconfirmed"),
        ))
        with self.assertRaisesRegex(PaperCloseAllRejected, "robot_owned_close_unconfirmed"):
            run(runtime)
        runtime.close_all.assert_not_called()

    def test_cannot_close_robot_owner_when_stopped(self):
        runtime, _ = fixture(mode="ROBOT_STOPPED", status="ROBOT_STOPPED", robot=True)
        with self.assertRaisesRegex(PaperCloseAllRejected, "stopped_robot_has_open_exposure"):
            run(runtime)
        runtime.robot_close_all.assert_not_called()
        runtime.close_all.assert_not_called()

    def test_paper_only_account_gate_is_mandatory(self):
        runtime, _ = fixture()
        runtime.require_paper_mutations.side_effect = RuntimeError("live_mutations_disabled")
        with self.assertRaisesRegex(RuntimeError, "live_mutations_disabled"):
            run(runtime)
        runtime.store.update_robot_runtime_state.assert_not_called()
        runtime.close_all.assert_not_called()

    def test_no_positions_or_limits_is_clean_idempotent_noop(self):
        runtime, _ = fixture(manual=False)
        runtime.close_all.return_value = response()
        result = run(runtime)
        self.assertEqual(result.results, ())
        self.assertEqual(result.positions, ())


if __name__ == "__main__":
    unittest.main()
