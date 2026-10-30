"""Synthetic PAPER Box close safety: no VPS, exchange, or production DB."""
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from terminal.api.models import CommandResult, CommandResultStatus
from terminal.domain.models import OrderId, OrderSide, Symbol, TradingAccountId
from terminal.paper.executor import PaperBookStale
from terminal.runtime.paper_runtime import PaperRuntime


def fixture():
    symbol = Symbol("API3USDT")
    candidate = SimpleNamespace(
        candidate_id="robot-box", symbol=symbol, status="OPEN",
        signal_snapshot={"pattern": "IKIGAI_BOX", "source_box_candidate_id": "box-source"},
        robot_state={"execution": {"box_manual_close_intent": {"existing": True}}},
    )
    source = SimpleNamespace(candidate_id="box-source", status="BOX_PLAN_ONLY")
    proof = SimpleNamespace(remaining_quantity=Decimal("519.2"))
    flat = SimpleNamespace(
        remaining_quantity=Decimal("0"), average_exit=Decimal("0.2405"),
        last_execution_at_ms=100, entry_notional=Decimal("124"),
        realized_pnl=Decimal("0"), accumulated_fee=Decimal("0.1"),
    )
    trade = SimpleNamespace(trade_id="trade-box", candidate_id="robot-box", direction="SHORT")
    request = SimpleNamespace(
        symbol="API3USDT", side=OrderSide.BUY, quantity=Decimal("519.2"),
        client_action_id=SimpleNamespace(value="box-market-close"),
    )
    plan = SimpleNamespace(
        slot=0, quantity=Decimal("519.2"), request=request,
        identity="stable-identity", order_id=OrderId("close-slot-0"),
    )
    store = SimpleNamespace(
        get_open_robot_trade_for_symbol=Mock(return_value=trade),
        get_robot_candidate=Mock(return_value=source),
        prove_box_owned_position=Mock(side_effect=[proof, flat]),
        reserve_box_order_identity=Mock(),
        load_box_order_ownership=Mock(return_value=(
            SimpleNamespace(order_id=OrderId("protective-exit"), role="EXIT"),
        )),
        get_paper_limit=Mock(return_value=SimpleNamespace(status="open")),
        cancel_paper_limit=Mock(),
        close_robot_trade=Mock(),
        clear_paper_protection_for_flat=Mock(),
    )
    runtime = SimpleNamespace(
        _paper_account_id=TradingAccountId("paper"), store=store,
        _robot_execution_book=Mock(return_value=SimpleNamespace(symbol=symbol)),
        _market_executor=SimpleNamespace(validate_book=Mock()),
        _robot_api=SimpleNamespace(market=Mock(return_value=CommandResult(
            "box-market-close", CommandResultStatus.COMPLETED,
            "completed", "completed",
        ))),
    )
    return runtime, candidate, plan


class BoxCloseEvidenceBeforeExitCancel(unittest.TestCase):
    def test_stale_book_preserves_exit_and_reports_reason(self):
        runtime, candidate, plan = fixture()
        runtime._market_executor.validate_book.side_effect = PaperBookStale(
            "normalized book is stale: age=2000ms max=1000ms"
        )
        with patch("terminal.runtime.paper_runtime.restore_box_market_plan", return_value=plan):
            result = PaperRuntime._robot_close_box_candidate(runtime, candidate)
        self.assertEqual(result.status, CommandResultStatus.UNAVAILABLE)
        self.assertEqual(result.reason_code, "paper_market_book_stale")
        runtime.store.reserve_box_order_identity.assert_not_called()
        runtime.store.cancel_paper_limit.assert_not_called()
        runtime._robot_api.market.assert_not_called()

    def test_prepared_off_owner_book_replaces_stale_stream_and_reaches_market(self):
        runtime, candidate, plan = fixture()
        prepared = SimpleNamespace(symbol=candidate.symbol, received_at_ms=100)
        def validate(symbol, book):
            if book is not prepared:
                raise PaperBookStale("normalized book is stale")
        runtime._market_executor.validate_book.side_effect = validate
        with patch("terminal.runtime.paper_runtime.restore_box_market_plan", return_value=plan):
            result = PaperRuntime._robot_close_box_candidate(
                runtime, candidate, evidence=prepared,
            )
        self.assertEqual(result.status, CommandResultStatus.COMPLETED)
        self.assertIs(runtime._robot_api.market.call_args.kwargs["market_book"], prepared)

    def test_market_unavailable_after_validation_preserves_exit(self):
        runtime, candidate, plan = fixture()
        runtime._robot_api.market.return_value = CommandResult(
            "box-market-close", CommandResultStatus.UNAVAILABLE,
            "service_unavailable", "command service is unavailable",
        )
        with patch("terminal.runtime.paper_runtime.restore_box_market_plan", return_value=plan):
            result = PaperRuntime._robot_close_box_candidate(runtime, candidate)
        self.assertEqual(result.reason_code, "service_unavailable")
        runtime.store.cancel_paper_limit.assert_not_called()
        runtime.store.close_robot_trade.assert_not_called()

    def test_proven_flat_retires_exit_after_market(self):
        runtime, candidate, plan = fixture()
        def market(*args, **kwargs):
            runtime.store.cancel_paper_limit.assert_not_called()
            return CommandResult(
                "box-market-close", CommandResultStatus.COMPLETED, "completed", "completed",
            )
        runtime._robot_api.market.side_effect = market
        with patch("terminal.runtime.paper_runtime.restore_box_market_plan", return_value=plan):
            result = PaperRuntime._robot_close_box_candidate(runtime, candidate)
        self.assertEqual(result.status, CommandResultStatus.COMPLETED)
        runtime.store.cancel_paper_limit.assert_called_once()
        runtime.store.close_robot_trade.assert_called_once()
        runtime.store.clear_paper_protection_for_flat.assert_called_once()

    def test_unproven_flat_preserves_exit(self):
        runtime, candidate, plan = fixture()
        runtime.store.prove_box_owned_position.side_effect = [
            SimpleNamespace(remaining_quantity=Decimal("519.2")),
            SimpleNamespace(remaining_quantity=Decimal("1")),
        ]
        with patch("terminal.runtime.paper_runtime.restore_box_market_plan", return_value=plan):
            result = PaperRuntime._robot_close_box_candidate(runtime, candidate)
        self.assertEqual(result.status, CommandResultStatus.UNKNOWN)
        runtime.store.cancel_paper_limit.assert_not_called()
        runtime.store.close_robot_trade.assert_not_called()


if __name__ == "__main__":
    unittest.main()
