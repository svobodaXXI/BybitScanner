"""Account-wide PAPER Close-All reuses stable execution identity on HTTP retry.

Synthetic owner/store only: no exchange, PAPER database, backend, Telegram
or LIVE runtime. Ordinary standalone manual FullClose remains unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal.api.models import ClientActionId, CloseAllCommandRequest, CommandResult, CommandResultStatus
from terminal.application.command_identity import CommandIdentityCandidate
from terminal.domain.models import Symbol, TradingAccountId
from terminal.runtime.paper_runtime import PaperRuntime

PAPER = TradingAccountId("paper")


def fake_runtime(*symbols):
    items = tuple(SimpleNamespace(
        position_key=SimpleNamespace(symbol=Symbol(symbol)),
    ) for symbol in symbols)
    close = Mock(side_effect=lambda request, **kwargs: CommandResult(
        request.client_action_id.value,
        CommandResultStatus.COMPLETED, "closed", "closed",
    ))
    runtime = SimpleNamespace(
        _account_id=PAPER,
        require_paper_mutations=Mock(),
        store=SimpleNamespace(
            load_open_position_projections=Mock(return_value=items),
        ),
        api=SimpleNamespace(full_close=close),
        _robot_execution_book=Mock(return_value=None),
        open_positions=Mock(return_value=SimpleNamespace(positions=())),
    )
    return runtime, close


def run(runtime, action="request-1"):
    return PaperRuntime.close_all(
        runtime, CloseAllCommandRequest(ClientActionId(action)),
    )


class PaperCloseAllStableIdentityTests(unittest.TestCase):
    def test_identical_action_is_replay_stable_even_with_original_open_inventory(self):
        first, a = fake_runtime("BOTUSDT")
        second, b = fake_runtime("BOTUSDT")
        run(first, "confirm-tap")
        run(second, "confirm-tap")
        request_a, request_b = a.call_args.args[0], b.call_args.args[0]
        self.assertEqual(request_a, request_b)
        identity = a.call_args.kwargs["identity"]
        self.assertIsInstance(identity, CommandIdentityCandidate)
        self.assertEqual(identity, b.call_args.kwargs["identity"])
        self.assertTrue(identity.command_id.value.startswith("cmd_"))
        self.assertEqual(len(identity.order_link_id), 36)
        self.assertTrue(identity.order_link_id.startswith("tw_"))
        self.assertIsNone(a.call_args.kwargs["market_book"])

    def test_different_action_and_symbol_never_share_identity(self):
        first, close = fake_runtime("BOTUSDT", "OTHERUSDT")
        run(first, "command")
        a, b = [item.kwargs["identity"] for item in close.call_args_list]
        self.assertNotEqual(a, b)
        second, another = fake_runtime("BOTUSDT")
        run(second, "other-command")
        self.assertNotEqual(a, another.call_args.kwargs["identity"])

    def test_account_close_identity_cannot_collide_with_robot_close_identity(self):
        # Robot Close-All #653 hashes action + symbol without this route's
        # domain prefix; even identical opaque action IDs cannot collide.
        import hashlib
        action, symbol = "shared-action", "BOTUSDT"
        robot_digest = hashlib.sha256(
            (action + chr(0) + symbol).encode("utf-8")
        ).hexdigest()[:32]
        runtime, close = fake_runtime(symbol)
        run(runtime, action)
        identity = close.call_args.kwargs["identity"]
        self.assertNotEqual(identity.command_id.value, "cmd_" + robot_digest)

    def test_existing_client_action_id_and_response_contract_remain_intact(self):
        runtime, close = fake_runtime("BOTUSDT", "OTHERUSDT")
        response = run(runtime, "existing-wire-id")
        self.assertEqual(response.client_action_id, "existing-wire-id")
        self.assertEqual(len(response.results), 2)
        self.assertEqual(response.positions, ())
        self.assertTrue(all(result.status is CommandResultStatus.COMPLETED
                            for result in response.results))
        for item in close.call_args_list:
            self.assertTrue(item.args[0].client_action_id.value.startswith("paper-close-all-"))
        runtime.require_paper_mutations.assert_called_once()
        runtime.open_positions.assert_called_once()

    def test_no_open_paper_positions_dispatches_no_order(self):
        runtime, close = fake_runtime()
        response = run(runtime)
        self.assertEqual(response.results, ())
        close.assert_not_called()
        runtime.open_positions.assert_called_once()


if __name__ == "__main__":
    unittest.main()
