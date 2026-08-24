import ast
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from terminal.api.models import (
    AmendCommandRequest, CancelCommandRequest, ClientActionId, CommandResultStatus,
    LimitCommandRequest, MarketCommandRequest, ProtectionCommandRequest,
    VolumeRequest, VolumeUnit,
)
from terminal.api.rest import ServerCommandContext, TerminalCommandApi
from terminal.application.models import ProtectionState
from terminal.application.pretrade_guard import (
    PreTradeDecision, RejectionCode, WorkingVolumeIntent,
)
from terminal.application.trading_application import ApplicationResult
from terminal.domain.models import CommandId, OrderSide
from terminal.domain.states import CommandState
from terminal.exchange.bybit_v5_mutation_adapter import (
    MutationDisposition, MutationKind, MutationOutcome,
)
from terminal.persistence.sqlite_store import PersistenceError
from tests.test_terminal_pretrade_guard import context, instrument
from tests.test_terminal_reconciliation import position_event
from tests.test_terminal_trading_application import order


ACTION = ClientActionId("gesture-1")


class Provider:
    def __init__(self):
        self.context = ServerCommandContext(
            context(), instrument(), position_event(), Decimal("50"), OrderSide.BUY,
        )
        self.lookups = []

    def context_for(self, symbol):
        self.lookups.append(("context", symbol))
        return self.context

    def order_for(self, symbol, order_id, order_link_id):
        self.lookups.append(("order", symbol, order_id, order_link_id))
        return order()


class FakeTradingApplication:
    def __init__(self):
        self.calls = []
        self.next_result = None
        self.error = None

    def _call(self, name, value, *extra):
        self.calls.append((name, value, *extra))
        if self.error:
            raise self.error
        if self.next_result is not None:
            return self.next_result
        command = SimpleNamespace(command_id=CommandId("command-1"), current_state=CommandState.ACKNOWLEDGED)
        outcome = MutationOutcome(MutationKind.CREATE, MutationDisposition.ACKNOWLEDGED)
        return ApplicationResult(None, command, outcome)

    def submit(self, intent, ctx): return self._call("submit", intent, ctx)
    def amend(self, intent): return self._call("amend", intent)
    def cancel(self, intent): return self._call("cancel", intent)

    def set_protection(self, intent):
        self.calls.append(("protection", intent))
        if self.error:
            raise self.error
        if self.next_result is not None:
            return self.next_result
        return SimpleNamespace(command_id="command-1", state=ProtectionState.PENDING_CONFIRMATION)


def market():
    return MarketCommandRequest(
        ACTION, "btcusdt", OrderSide.BUY,
        VolumeRequest(VolumeUnit.USDT, Decimal("100")), Decimal("100"),
        "Percent", Decimal("0.5"),
    )


class TerminalCommandApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FakeTradingApplication()
        self.provider = Provider()
        self.api = TerminalCommandApi(self.app, self.provider)

    def test_market_and_limit_map_only_to_trading_application(self):
        market_result = self.api.market(replace(
            market(),
            volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, Decimal("1")),
        ))
        limit_result = self.api.limit(LimitCommandRequest(
            ACTION, "BTCUSDT", OrderSide.SELL,
            VolumeRequest(VolumeUnit.WORKING_VOLUME, Decimal("2")),
            Decimal("100"), Decimal("101"),
        ))
        self.assertEqual([call[0] for call in self.app.calls], ["submit", "submit"])
        self.assertEqual(self.provider.lookups[0], ("context", "BTCUSDT"))
        self.assertEqual(market_result.status, CommandResultStatus.ACCEPTED_PENDING)
        self.assertEqual(limit_result.client_action_id, ACTION.value)
        self.assertIsInstance(self.app.calls[0][1].volume, WorkingVolumeIntent)
        self.assertEqual(self.app.calls[0][1].volume.wv_count, Decimal("1"))
        self.assertEqual(self.app.calls[0][1].volume.configured_one_wv_usdt, Decimal("50"))
        self.assertEqual(self.app.calls[1][1].volume.configured_one_wv_usdt, Decimal("50"))

    def test_amend_cancel_and_protection_use_server_owned_facts(self):
        self.api.amend(AmendCommandRequest(
            ACTION, "BTCUSDT", order_id="active", changed_price=Decimal("101"),
        ))
        self.api.cancel(CancelCommandRequest(ACTION, "BTCUSDT", order_id="active"))
        self.api.protection(ProtectionCommandRequest(
            ACTION, "BTCUSDT", Decimal("120"), Decimal("80"),
        ))
        self.assertEqual([call[0] for call in self.app.calls], ["amend", "cancel", "protection"])
        self.assertEqual(self.app.calls[0][1].trading_account_id, context().selected_account_id)
        self.assertEqual(self.app.calls[2][1].position, self.provider.context.position)

        cancelled = self.api.protection(ProtectionCommandRequest(
            ClientActionId("gesture-cancel-protection"), "BTCUSDT", None, None,
        ))
        self.assertEqual(cancelled.status, CommandResultStatus.ACCEPTED_PENDING)
        self.assertIsNone(self.app.calls[-1][1].take_profit)
        self.assertIsNone(self.app.calls[-1][1].stop_loss)

    def test_blocked_rejected_unknown_and_safe_errors(self):
        self.app.next_result = ApplicationResult(
            PreTradeDecision(False, RejectionCode.OFFLINE, "offline", None), None, None,
        )
        self.assertEqual(self.api.market(market()).status, CommandResultStatus.BLOCKED)

        command = SimpleNamespace(command_id=CommandId("command-2"), current_state=CommandState.REJECTED)
        self.app.next_result = ApplicationResult(
            None, command, MutationOutcome(MutationKind.CREATE, MutationDisposition.REJECTED,
                                           reason="raw exchange detail"),
        )
        rejected = self.api.market(market())
        self.assertEqual(rejected.status, CommandResultStatus.REJECTED)
        self.assertNotIn("raw exchange", rejected.message)

        self.app.next_result = ApplicationResult(
            None, command, MutationOutcome(MutationKind.CREATE, MutationDisposition.UNKNOWN,
                                           reason="secret signed payload"),
        )
        unknown = self.api.market(market())
        self.assertEqual(unknown.status, CommandResultStatus.UNKNOWN)
        self.assertTrue(unknown.reconciliation_required)
        self.assertNotIn("secret", unknown.message)

        self.app.next_result = None
        self.app.error = PersistenceError("database path and internal detail")
        failed = self.api.market(market())
        self.assertEqual(failed.status, CommandResultStatus.PERSISTENCE_FAILURE)
        self.assertNotIn("database path", failed.message)

        self.app.error = RuntimeError("trace credentials signed request")
        unavailable = self.api.market(market())
        self.assertEqual(unavailable.status, CommandResultStatus.UNAVAILABLE)
        self.assertNotIn("credentials", unavailable.message)

        invalid = self.api.market(replace(market(), symbol=""))
        self.assertEqual(invalid.status, CommandResultStatus.VALIDATION_ERROR)

    def test_api_source_has_no_adapter_engine_network_or_credentials_boundary(self):
        api_root = Path(__file__).parents[1] / "terminal" / "api"
        forbidden_imports = {
            "terminal.exchange.bybit_v5_adapter",
            "terminal.exchange.bybit_v5_mutation_adapter",
            "terminal.application.execution_engine",
            "requests", "websocket", "fastapi", "starlette", "flask", "aiohttp",
        }
        for path in api_root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            self.assertTrue(forbidden_imports.isdisjoint(imported), (path, imported & forbidden_imports))
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("api_secret", text)
            self.assertNotIn("api_key", text)


if __name__ == "__main__":
    unittest.main()
