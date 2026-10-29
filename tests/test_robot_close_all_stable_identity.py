"""Same Robot Close-All action must yield the same durable PAPER Market identity.

No network, exchange, live runtime or persistent PAPER database.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal.api.models import (
    ClientActionId, CloseAllCommandRequest, CommandResult,
    CommandResultStatus, FullCloseCommandRequest,
)
from terminal.api.rest import TerminalCommandApi
from terminal.application.command_identity import CommandIdentityCandidate
from terminal.application.trading_application import ApplicationResult
from terminal.domain.models import Symbol, TradingAccountId
from terminal.runtime.paper_runtime import PaperRuntime


def _runtime_for_symbols(*symbols):
    candidates = [
        SimpleNamespace(
            candidate_id=f"candidate-{i}-{symbol}",
            symbol=Symbol(symbol),
            status="OPEN",
            robot_state={},
            signal_snapshot={"pattern": "Falling Wedge"},
        )
        for i, symbol in enumerate(symbols)
    ]
    store = SimpleNamespace(
        load_robot_candidates_by_status=Mock(return_value=candidates),
        load_open_robot_trades=Mock(return_value=tuple(
            SimpleNamespace(
                trade_id=f"trade-{candidate.candidate_id}",
                candidate_id=candidate.candidate_id,
                symbol=candidate.symbol,
            )
            for candidate in candidates
        )),
        load_active_robot_candidate_states=Mock(return_value=candidates),
        load_active_robot_entry_orders=Mock(return_value={}),
        load_unresolved_paper_protection_obligations=Mock(return_value=()),
        load_active_paper_limits=Mock(return_value=()),
        get_robot_runtime_state=Mock(),
        update_robot_runtime_state=Mock(),
        # CR-ROBOT-CLOSE-ALL-MAX-QTY-001: robot_close_all() re-reads the
        # position after a COMPLETED chunk; already flat here, so these
        # tests see exactly the one chunk they expect.
        get_position_projection=Mock(return_value=SimpleNamespace(
            quantity=SimpleNamespace(value=Decimal(0)),
        )),
    )
    close = Mock(side_effect=lambda request, *, identity: CommandResult(
        request.client_action_id.value, CommandResultStatus.COMPLETED,
        "completed", "completed",
    ))
    runtime = SimpleNamespace(
        _account_id=TradingAccountId("paper"), store=store,
        _robot_full_close=close,
        _robot_prepare_manual_close=Mock(side_effect=lambda candidate, request, identity, chunk_index=0: (
            request, identity,
        )),
        _instrument_provider=Mock(return_value=SimpleNamespace(
            max_market_order_quantity=Decimal("999999"), quantity_step=Decimal("0.0001"),
        )),
        _robot_finalize_manual_close=Mock(side_effect=lambda candidate: (
            close.call_count > next(
                i for i, item in enumerate(candidates)
                if item.candidate_id == candidate.candidate_id
            )
        )),
        _robot_linked_entry_limits=Mock(return_value={}),
        _robot_close_box_candidate=Mock(),
        open_positions=Mock(return_value=SimpleNamespace(positions=())),
    )
    return runtime, close


def _run(runtime, action):
    return PaperRuntime.robot_close_all(
        runtime, CloseAllCommandRequest(ClientActionId(action)),
    )


class CloseAllStableIdentityTests(unittest.TestCase):
    def test_same_action_has_same_market_identity_across_retries(self):
        a, a_close = _runtime_for_symbols("BOTUSDT")
        b, b_close = _runtime_for_symbols("BOTUSDT")
        _run(a, "operator-command")
        _run(b, "operator-command")
        args_a = a_close.call_args
        args_b = b_close.call_args
        identity = args_a.kwargs["identity"]
        self.assertIsInstance(identity, CommandIdentityCandidate)
        self.assertEqual(identity, args_b.kwargs["identity"])
        self.assertEqual(args_a.args[0], args_b.args[0])
        self.assertEqual(len(identity.order_link_id), 36)
        self.assertEqual(identity.order_link_id[:3], "tw_")
        self.assertEqual(identity.command_id.value[:4], "cmd_")

    def test_different_symbols_and_commands_do_not_share_identity(self):
        a, close = _runtime_for_symbols("BOTUSDT", "OTHERUSDT")
        _run(a, "operator-command")
        first, second = [call.kwargs["identity"] for call in close.call_args_list]
        self.assertNotEqual(first, second)
        b, another = _runtime_for_symbols("BOTUSDT")
        _run(b, "different-command")
        self.assertNotEqual(first, another.call_args.kwargs["identity"])

    def test_existing_full_close_api_passes_optional_identity_to_engine(self):
        position = SimpleNamespace(
            mark_price=Decimal("100"), average_entry=Decimal("100"),
        )
        pretrade = SimpleNamespace(
            position_side=SimpleNamespace(value="Long"),
            confirmed_position_quantity=Decimal("2"),
        )
        context = SimpleNamespace(
            context_for=Mock(return_value=SimpleNamespace(
                pretrade=pretrade, position=position,
            )),
        )
        app = SimpleNamespace(submit=Mock(return_value=ApplicationResult(None, None, None)))
        api = TerminalCommandApi(app, context)
        runtime, close = _runtime_for_symbols("BOTUSDT")
        _run(runtime, "operator-command")
        identity = close.call_args.kwargs["identity"]
        request = FullCloseCommandRequest(ClientActionId("close-symbol"), "BOTUSDT")
        result = api.full_close(request, identity=identity, market_book=None)
        self.assertEqual(result.status, CommandResultStatus.ACCEPTED_PENDING)
        self.assertIs(app.submit.call_args.kwargs["identity"], identity)
        self.assertIsNone(app.submit.call_args.kwargs["market_book"])

    def test_original_manual_full_close_has_no_stable_identity(self):
        position = SimpleNamespace(
            mark_price=Decimal("100"), average_entry=Decimal("100"),
        )
        pretrade = SimpleNamespace(
            position_side=SimpleNamespace(value="Short"),
            confirmed_position_quantity=Decimal("2"),
        )
        context = SimpleNamespace(
            context_for=Mock(return_value=SimpleNamespace(
                pretrade=pretrade, position=position,
            )),
        )
        app = SimpleNamespace(submit=Mock(return_value=ApplicationResult(None, None, None)))
        api = TerminalCommandApi(app, context)
        api.full_close(FullCloseCommandRequest(ClientActionId("manual"), "BOTUSDT"))
        self.assertNotIn("identity", app.submit.call_args.kwargs)

    def test_robot_wrapper_preserves_identity(self):
        identity = CommandIdentityCandidate(
            SimpleNamespace(value="cmd_abc"), "tw_" + "a" * 33,
        )
        api = SimpleNamespace(full_close=Mock(return_value="ok"))
        runtime = SimpleNamespace(
            _robot_api=api, _robot_execution_book=Mock(return_value=None),
        )
        request = FullCloseCommandRequest(ClientActionId("action"), "BOTUSDT")
        result = PaperRuntime._robot_full_close(runtime, request, identity=identity)
        self.assertEqual(result, "ok")
        api.full_close.assert_called_once_with(
            request, market_book=None, identity=identity,
        )


if __name__ == "__main__":
    unittest.main()
