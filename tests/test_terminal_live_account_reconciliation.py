import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from terminal.application.live_account_reconciliation import LiveAccountReconciliationError, LiveAccountReconciler
from terminal.application.trading_accounts import (
    TradingAccount, TradingAccountEnvironment, TradingAccountProvider,
    TradingAccountStatus, paper_account_manager,
)
from terminal.domain.models import TradingAccountId
from terminal.exchange.bybit_account_validation import ValidatedBybitAccount
from terminal.exchange.bybit_v5_adapter import BybitWalletSnapshot
from terminal.persistence.credential_store import StoredBybitAccount
from terminal.persistence.live_account_store import (
    LiveAccountProjectionStore, LiveAccountSnapshot, LiveAccountStoreError,
)


def _manager():
    manager = paper_account_manager()
    manager.register_inactive(TradingAccount(
        TradingAccountId("bybit-one"), "Main", TradingAccountProvider.BYBIT,
        TradingAccountEnvironment.MAINNET, TradingAccountStatus.DISCONNECTED,
    ))
    return manager


class Validator:
    def __init__(self, read_only=False, environment="MAINNET"):
        self.read_only = read_only
        self.environment = environment

    def validate(self, credentials):
        return ValidatedBybitAccount(self.environment, self.read_only)


class ReadAdapter:
    mutation_calls = 0

    def __init__(self, account_id, credentials, *, testnet):
        assert account_id == TradingAccountId("bybit-one")
        assert testnet is False

    def get_wallet_snapshot(self):
        return BybitWalletSnapshot(Decimal("90"), Decimal("100"), Decimal("70"), 1234)

    def list_open_positions(self):
        return (SimpleNamespace(
            position_key=SimpleNamespace(
                trading_account_id=TradingAccountId("bybit-one"),
                symbol=SimpleNamespace(value="BTCUSDT"),
            ),
            side=SimpleNamespace(value="Long"), size=Decimal("0.01"),
            average_entry=Decimal("60000"), mark_price=Decimal("61000"),
            unrealized_pnl=Decimal("10"), updated_at_ms=1200,
        ),)

    def list_all_active_orders(self):
        return (SimpleNamespace(
            trading_account_id=TradingAccountId("bybit-one"),
            symbol="ETHUSDT", order_id=SimpleNamespace(value="order-1"),
            side=SimpleNamespace(value="Sell"), order_type=SimpleNamespace(value="Limit"),
            price=Decimal("4000"), quantity=Decimal("1"),
            status=SimpleNamespace(value="Open"), updated_at_ms=1201,
        ),)

    def create_order(self, **kwargs):
        type(self).mutation_calls += 1


def _stored():
    return StoredBybitAccount("bybit-one", "Main", "MAINNET", "key", "secret", False)


class LiveAccountReconciliationTests(unittest.TestCase):
    def test_fresh_account_wide_refresh_sets_safe_status_and_preserves_paper(self):
        for read_only, expected in (
            (False, TradingAccountStatus.READY), (True, TradingAccountStatus.READ_ONLY),
        ):
            with self.subTest(read_only=read_only), tempfile.TemporaryDirectory() as temp:
                manager = _manager()
                token = manager.session_token
                store = LiveAccountProjectionStore(Path(temp) / "live.sqlite3")
                reconciler = LiveAccountReconciler(
                    manager, lambda account_id: _stored(), Validator(read_only), store,
                    adapter_factory=ReadAdapter, clock_ms=lambda: 2000,
                )
                result = reconciler.refresh("bybit-one")
                self.assertIs(manager.account(TradingAccountId("bybit-one")).status, expected)
                self.assertEqual(manager.active_account_id, TradingAccountId("paper"))
                self.assertEqual(manager.session_token, token)
                self.assertEqual(result["status"], expected.value)
                self.assertEqual((result["position_count"], result["order_count"]), (1, 1))
                self.assertEqual(result["positions"][0]["account_id"], "bybit-one")
                self.assertEqual(result["orders"][0]["account_id"], "bybit-one")
                self.assertEqual(ReadAdapter.mutation_calls, 0)
                self.assertNotIn("secret", json.dumps(result).lower())
                store.close()

    def test_environment_mismatched_refresh_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = _manager()
            store = LiveAccountProjectionStore(Path(temp) / "live.sqlite3")
            reconciler = LiveAccountReconciler(
                manager, lambda account_id: _stored(), Validator(environment="TESTNET"), store,
                adapter_factory=ReadAdapter,
            )
            with self.assertRaisesRegex(LiveAccountReconciliationError, "account_environment_mismatch"):
                reconciler.refresh("bybit-one")
            self.assertIs(manager.account(TradingAccountId("bybit-one")).status, TradingAccountStatus.ERROR)
            self.assertEqual(manager.active_account_id, TradingAccountId("paper"))
            store.close()

    def test_cross_account_normalized_evidence_is_rejected_without_publish(self):
        class ContaminatedAdapter(ReadAdapter):
            def list_open_positions(self):
                position = super().list_open_positions()[0]
                return (SimpleNamespace(
                    **{**vars(position), "position_key": SimpleNamespace(
                        trading_account_id=TradingAccountId("bybit-other"),
                        symbol=SimpleNamespace(value="BTCUSDT"),
                    )},
                ),)

        with tempfile.TemporaryDirectory() as temp:
            manager = _manager()
            store = LiveAccountProjectionStore(Path(temp) / "live.sqlite3")
            reconciler = LiveAccountReconciler(
                manager, lambda account_id: _stored(), Validator(), store,
                adapter_factory=ContaminatedAdapter,
            )
            with self.assertRaisesRegex(LiveAccountReconciliationError, "cross_account_live_evidence"):
                reconciler.refresh("bybit-one")
            self.assertIsNone(store.get("bybit-one"))
            self.assertIs(manager.account(TradingAccountId("bybit-one")).status, TradingAccountStatus.ERROR)
            store.close()

    def test_persisted_snapshot_is_disconnected_and_stale_write_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "live.sqlite3"
            snapshot = LiveAccountSnapshot(
                "bybit-one", "MAINNET", False, 2, Decimal("1"), Decimal("2"), Decimal("1"),
                100, (), (), 200,
            )
            first = LiveAccountProjectionStore(path)
            first.publish(snapshot)
            first.close()
            manager = _manager()
            restarted = LiveAccountProjectionStore(path)
            reconciler = LiveAccountReconciler(
                manager, lambda account_id: _stored(), Validator(), restarted,
                adapter_factory=ReadAdapter,
            )
            summary = reconciler.summary("bybit-one")
            self.assertEqual(summary["status"], "DISCONNECTED")
            self.assertEqual(manager.active_account_id, TradingAccountId("paper"))
            with self.assertRaisesRegex(LiveAccountStoreError, "stale_live_account_snapshot"):
                restarted.publish(snapshot)
            restarted.close()
