"""Boundary tests for independent manual MAIN account inventory (#930)."""
import unittest
import tempfile
from pathlib import Path
from terminal.persistence.mode_account_preference import ModeAccountPreferenceStore
from decimal import Decimal
from terminal.domain.models import TradingAccountId, Category, OrderSide, ExecutionId
from types import SimpleNamespace
from unittest.mock import patch

from terminal.application.manual_main_accounts import ManualMainAccounts, ManualMainAccountError
from terminal.persistence.credential_store import StoredBybitAccount


class FakeCredentials:
    def __init__(self, accounts=()):
        self.accounts = tuple(accounts)
        self.saves = []

    def load(self):
        return self.accounts

    def save(self, accounts):
        self.saves.append(accounts)
        self.accounts = tuple(accounts)


class FakeSnapshots:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeValidator:
    def __init__(self, environment="MAINNET", read_only=False):
        self.environment = environment
        self.read_only = read_only
        self.calls = 0

    def validate(self, credentials):
        self.calls += 1
        return SimpleNamespace(environment=self.environment, read_only=self.read_only)


class FakeReconciler:
    def __init__(self, manager, lookup, validator, store, **kwargs):
        self.manager = manager
        self.lookup = lookup
        self.calls = []

    def refresh(self, account_id):
        self.calls.append(account_id)
        # An authenticated Bybit read adapter is selected by the real
        # LiveAccountReconciler, not by this boundary unit test.
        return {"account_id": self.lookup(account_id).id, "positions": [], "orders": []}

    def summary(self, account_id):
        return {"account_id": self.lookup(account_id).id, "positions": []}


class ManualMainAccountsTests(unittest.TestCase):
    def setUp(self):
        self.c = FakeCredentials()
        self.snap = FakeSnapshots()
        self.v = FakeValidator()
        patcher = patch(
            "terminal.application.manual_main_accounts.LiveAccountReconciler",
            FakeReconciler,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def runtime(self):
        return ManualMainAccounts(self.c, self.snap, validator=self.v)

    def test_empty_start_has_no_paper_or_trading_authority(self):
        app = self.runtime()
        self.assertEqual(app.catalog(), {"accounts": []})
        self.assertFalse(hasattr(app, "place_order"))
        self.assertFalse(hasattr(app, "full_close"))
        self.assertFalse(hasattr(app, "start_robot"))
        self.assertEqual(self.c.saves, [])
        with self.assertRaises(LookupError):
            app.refresh("paper")
        app.close()
        self.assertTrue(self.snap.closed)

    def test_provision_is_validated_encrypted_store_only_then_refresh_uses_existing_reconciler(self):
        app = self.runtime()
        result = app.provision("Main subaccount", "some-key", "some-secret")
        self.assertTrue(result["created"])
        self.assertEqual(self.v.calls, 1)
        self.assertEqual(len(self.c.saves), 1)
        self.assertEqual(self.c.accounts[0].environment, "MAINNET")
        self.assertNotIn("some-secret", repr(result))
        self.assertNotIn("some-key", repr(app.catalog()))
        self.assertEqual(app.catalog()["accounts"][0]["status"], "DISCONNECTED")
        self.assertEqual(app.refresh(result["account_id"])["account_id"], result["account_id"])
        self.assertEqual(app.summary(result["account_id"])["account_id"], result["account_id"])
        self.assertEqual(app.provision("Main subaccount", "some-key", "some-secret")["created"], False)
        self.assertEqual(len(self.c.saves), 1)
        self.assertEqual(self.v.calls, 1)

    def test_provision_stage_receipts_are_sanitized_on_success_and_failure(self):
        app = self.runtime()
        logger = "terminal.application.manual_main_accounts"
        with self.assertLogs(logger, level="WARNING") as captured:
            app.provision("private-name", "private-key", "private-secret")
        messages = "\n".join(captured.output)
        stages = [entry.split("stage=")[1].split()[0] for entry in captured.output]
        self.assertEqual(stages, ["WAIT_LOCK", "LOCK_ACQUIRED", "VALIDATION_BEGIN",
                                  "VALIDATION_RETURNED", "STORAGE_BEGIN", "STORAGE_RETURNED",
                                  "REGISTERED"])
        for value in ("private-name", "private-key", "private-secret", self.c.accounts[0].id):
            self.assertNotIn(value, messages)
        with patch.object(self.v, "validate", side_effect=RuntimeError("sensitive-exception")):
            with self.assertLogs(logger, level="WARNING") as captured:
                with self.assertRaises(RuntimeError):
                    app.provision("private-name", "other-key", "other-secret")
        self.assertIn("stage=VALIDATION_FAILED", "\n".join(captured.output))
        self.assertNotIn("sensitive-exception", "\n".join(captured.output))
        self.assertEqual(len(self.c.saves), 1)
        with patch.object(self.c, "save", side_effect=RuntimeError("sensitive-storage")):
            with self.assertLogs(logger, level="WARNING") as captured:
                with self.assertRaises(RuntimeError):
                    app.provision("private-name", "other-key", "other-secret")
        self.assertIn("stage=STORAGE_FAILED", "\n".join(captured.output))
        self.assertNotIn("sensitive-storage", "\n".join(captured.output))
        self.assertNotIn("stage=REGISTERED", "\n".join(captured.output))
        self.assertEqual(len(app.catalog()["accounts"]), 1)

    def test_reject_testnet_and_duplicate_secret_change_before_persistence(self):
        self.v.environment = "TESTNET"
        app = self.runtime()
        with self.assertRaisesRegex(ManualMainAccountError, "requires_mainnet"):
            app.provision("Main", "key", "secret")
        self.assertEqual(self.c.saves, [])
        self.v.environment = "MAINNET"
        app.provision("Main", "key", "secret")
        with self.assertRaisesRegex(ManualMainAccountError, "duplicate_api_key"):
            app.provision("Main", "key", "different")
        self.assertEqual(len(self.c.saves), 1)

    def test_execution_history_is_read_only_scoped_deduplicated_and_exact(self):
        record = StoredBybitAccount("bybit-a", "Main", "MAINNET", "key", "secret", True)
        self.c = FakeCredentials((record,))
        event = SimpleNamespace(
            trading_account_id=TradingAccountId(record.id), category=Category.LINEAR,
            symbol="BTCUSDT", exec_id=ExecutionId("fill-1"), side=OrderSide.BUY,
            execution_price=Decimal("65000.125"), execution_quantity=Decimal("0.01"),
            executed_at_ms=999999999999,
        )
        calls = []
        def read(symbol, **kwargs):
            calls.append((symbol, kwargs))
            return (event, event)
        def factory(account_id, credentials, *, testnet):
            self.assertEqual(account_id, TradingAccountId(record.id))
            self.assertFalse(testnet)
            return SimpleNamespace(list_executions=read)
        app = ManualMainAccounts(self.c, self.snap, validator=self.v, adapter_factory=factory)
        with patch("terminal.application.manual_main_accounts.time.time", return_value=1000000000):
            result = app.execution_history(record.id, "BTCUSDT")
            self.assertEqual(result["end_ms"] - result["start_ms"], 7 * 86400000)
            self.assertEqual(result["executions"], [{"exec_id": "fill-1", "time_ms": event.executed_at_ms,
                                                      "price": "65000.125", "side": "Buy"}])
            self.assertEqual(result["account_id"], record.id)
            self.assertTrue(calls[0][1]["trade_only"])
            with self.assertRaises(LookupError):
                app.execution_history("paper", "BTCUSDT")
            with self.assertRaises(ValueError):
                app.execution_history(record.id, "BTC/USDT")
            event.symbol = "ETHUSDT"
            with self.assertRaises(ManualMainAccountError):
                app.execution_history(record.id, "BTCUSDT")
            event.symbol = "BTCUSDT"
            event.trading_account_id = TradingAccountId("other-account")
            with self.assertRaises(ManualMainAccountError):
                app.execution_history(record.id, "BTCUSDT")
        self.assertEqual(self.c.saves, [])
        self.assertEqual(self.v.calls, 0)

    def test_trade_only_adapter_paginates_and_rejects_nontrade(self):
        from terminal.exchange.bybit_v5_adapter import (
            BybitCredentials, BybitV5ReadAdapter, MalformedResponse, UnsupportedPayload,
        )
        from tests.test_terminal_bybit_adapter import FakeHTTP, execution_payload, response

        http = FakeHTTP()
        adapter = BybitV5ReadAdapter(TradingAccountId("bybit-a"),
                                    BybitCredentials("key", "secret"), testnet=False,
                                    http_factory=lambda **kwargs: http)
        http.responses["get_executions"] = lambda kwargs: (
            response([execution_payload(execType="Trade", execId="exec-2")])
            if kwargs.get("cursor") else
            response([execution_payload(execType="Trade")], cursor="next")
        )
        events = adapter.list_executions("BTCUSDT", start_time_ms=0,
                                         end_time_ms=3000, trade_only=True)
        self.assertEqual([item.exec_id.value for item in events], ["exec-1", "exec-2"])
        self.assertTrue(all(kwargs["execType"] == "Trade"
                            for name, kwargs in http.calls if name == "get_executions"))
        http.responses["get_executions"] = response([execution_payload(execType="Funding")])
        with self.assertRaises(UnsupportedPayload):
            adapter.list_executions("BTCUSDT", trade_only=True)
        http.calls.clear()
        http.responses["get_executions"] = lambda kwargs: response(
            [execution_payload(execType="Trade")], cursor=str(len(http.calls)))
        with self.assertRaises(MalformedResponse):
            adapter.list_executions("BTCUSDT", trade_only=True)
        self.assertEqual(len(http.calls), 20)

    def test_terminal_preference_survives_restart_without_connecting_or_activating(self):
        record = StoredBybitAccount("bybit-a", "MAIN", "MAINNET", "key", "secret", True)
        self.c = FakeCredentials((record,))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "terminal.preference.json"
            def runtime():
                return ManualMainAccounts(self.c, self.snap, validator=self.v,
                                          terminal_preferences=ModeAccountPreferenceStore(path))
            app = runtime()
            self.assertIsNone(app.terminal_preference())
            self.assertEqual(app.save_terminal_preference(record.id), record.id)
            restored = runtime()
            self.assertEqual(restored.terminal_preference(), record.id)
            self.assertEqual(restored.catalog()["accounts"][0]["status"], "DISCONNECTED")
            with self.assertRaises(LookupError):
                restored.save_terminal_preference("bybit-unknown")
            self.assertEqual(restored.terminal_preference(), record.id)
            with patch("terminal.persistence.mode_account_preference.os.replace", side_effect=OSError):
                with self.assertRaises(RuntimeError):
                    restored.save_terminal_preference("paper")
            self.assertEqual(runtime().terminal_preference(), record.id)
            restored.save_terminal_preference("paper")
            self.assertEqual(runtime().terminal_preference(), "paper")
            self.assertIsNone(ModeAccountPreferenceStore(path).load("AUTOPILOT"))
            self.assertEqual(self.v.calls, 0)
            self.assertEqual(self.c.saves, [])

    def test_existing_credentials_are_registered_without_network_or_paper(self):
        record = StoredBybitAccount(
            "bybit-preexisting", "Main", "MAINNET", "key", "secret", True,
        )
        self.c = FakeCredentials((record,))
        app = self.runtime()
        self.assertEqual(self.v.calls, 0)
        self.assertEqual(app.catalog()["accounts"][0]["id"], record.id)
        self.assertEqual(app.catalog()["accounts"][0]["status"], "DISCONNECTED")
        with self.assertRaises(LookupError):
            app.summary("paper")
        self.assertEqual(app.summary(record.id)["account_id"], record.id)
        self.assertEqual(self.c.saves, [])


if __name__ == "__main__":
    unittest.main()
