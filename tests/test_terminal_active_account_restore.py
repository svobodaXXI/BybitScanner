import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.application.trading_accounts import (
    TradingAccount, TradingAccountEnvironment, TradingAccountProvider,
    TradingAccountStatus, paper_account_manager,
)
from terminal.domain.models import TradingAccountId
from terminal.domain.models import Category, Price, Quantity, Symbol
from terminal.exchange.events import InstrumentSnapshot
from terminal.exchange.bybit_account_validation import ValidatedBybitAccount
from terminal.exchange.bybit_v5_adapter import BybitWalletSnapshot
from terminal.persistence.active_account_preference import ActiveAccountPreferenceStore
from terminal.persistence.credential_store import StoredBybitAccount
from terminal.persistence.live_account_store import LiveAccountProjectionStore, LiveAccountSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_http_server import (
    SerializedPaperRuntime, create_configured_paper_runtime,
)


class CredentialStore:
    def __init__(self, account=None): self.account = account
    def load(self): return (self.account,) if self.account is not None else ()


class Validator:
    def __init__(self, *, read_only=False, fail=False):
        self.read_only, self.fail = read_only, fail
    def validate(self, _credentials):
        if self.fail: raise RuntimeError("reconnect failed")
        return ValidatedBybitAccount("MAINNET", self.read_only)


class ReadAdapter:
    def __init__(self, account_id, _credentials, *, testnet):
        assert account_id == TradingAccountId("bybit-one") and testnet is False
    def get_wallet_snapshot(self):
        return BybitWalletSnapshot(
            Decimal("332.3"), Decimal("80.37"), Decimal("61.25"), 1234,
            {
                "account.totalWalletBalance": "332.3",
                "account.totalEquity": "80.37",
                "account.totalAvailableBalance": "61.25",
            },
        )
    def list_open_positions(self): return ()
    def list_all_active_orders(self): return ()


def stored_account():
    return StoredBybitAccount("bybit-one", "Main", "MAINNET", "key", "secret", False)


def manager_with_ready_bybit():
    manager = paper_account_manager()
    manager.register_inactive(TradingAccount(
        TradingAccountId("bybit-one"), "Main", TradingAccountProvider.BYBIT,
        TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
    ))
    return manager


def activate_current(runtime, account_id):
    return runtime.call(lambda owner: owner.activate_account(
        account_id,
        owner._account_manager.session_token.active_account_id.value,
        owner._account_manager.session_token.generation,
    ))


class StaticBookProvider:
    def get_book(self, symbol: Symbol) -> NormalizedOrderBook:
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(Decimal("64249.5")), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(Decimal("64250.5")), Quantity(Decimal("10"))),),
            health=BookHealth.READY, received_at_ms=1, available_depth=1,
        )

    def get_current_book_update(self, symbol: Symbol):
        return "BTCUSDT:1:1", self.get_book(symbol)


def runtime_owner(
    path: Path, *, credential_store=None, account_validator=None,
    active_account_preference_store=None, live_adapter_factory=None,
    account_manager=None, **_kwargs,
) -> SerializedPaperRuntime:
    instrument = InstrumentSnapshot(
        Category.LINEAR, "BTCUSDT", "LinearPerpetual", "Trading",
        "BTC", "USDT", "USDT", Decimal("0.5"), Decimal("1000000"),
        Decimal("0.5"), Decimal("0.001"), Decimal("100"), Decimal("50"),
        Decimal("0.001"), Decimal("5"),
    )
    return SerializedPaperRuntime(lambda: create_configured_paper_runtime(
        path, book_provider=StaticBookProvider(), instrument_snapshot=instrument,
        instrument_provider=lambda symbol: replace(instrument, symbol=symbol),
        credential_store_factory=lambda _path: credential_store or CredentialStore(),
        account_validator_factory=lambda: account_validator or Validator(),
        active_account_preference_store_factory=lambda preference_path:
            active_account_preference_store or ActiveAccountPreferenceStore(preference_path),
        live_adapter_factory=live_adapter_factory,
        account_manager=account_manager,
    ))


class ActiveAccountRestoreTests(unittest.TestCase):
    def test_successful_activation_persists_only_canonical_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database_path = root / "paper.sqlite3"
            live = LiveAccountProjectionStore(database_path.with_suffix(".live_accounts.sqlite3"))
            live.publish(LiveAccountSnapshot(
                "bybit-one", "MAINNET", False, 1, Decimal("80.37"), Decimal("81.25"),
                Decimal("332.3"), 1, (), (), 2,
            ))
            live.close()
            preference_path = database_path.with_suffix(".active_account.json")
            runtime = runtime_owner(
                database_path, account_manager=manager_with_ready_bybit(),
            )
            try:
                result = activate_current(runtime, "bybit-one")
                self.assertEqual(result["session_generation"], 2)
                self.assertEqual(json.loads(preference_path.read_text()), {
                    "version": 1, "preferred_account_id": "bybit-one",
                })
            finally:
                runtime.close()

    def test_restart_reconnects_before_ready_or_read_only_activation_once(self):
        for read_only, expected in ((False, "READY"), (True, "READ_ONLY")):
            with self.subTest(read_only=read_only), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                database_path = root / "paper.sqlite3"
                preference = ActiveAccountPreferenceStore(database_path.with_suffix(".active_account.json"))
                preference.save(TradingAccountId("bybit-one"))
                stale_store = LiveAccountProjectionStore(database_path.with_suffix(".live_accounts.sqlite3"))
                stale_store.publish(LiveAccountSnapshot(
                    "bybit-one", "MAINNET", read_only, 7, Decimal("1"), Decimal("2"),
                    Decimal("3"), 100, (), (), 200,
                ))
                stale_store.close()
                runtime = runtime_owner(
                    database_path, credential_store=CredentialStore(stored_account()),
                    account_validator=Validator(read_only=read_only),
                    live_adapter_factory=ReadAdapter,
                )
                try:
                    catalog = runtime.call(lambda owner: owner.account_catalog())
                    projection = runtime.call(lambda owner: owner.workspace_account_projection("BTCUSDT"))
                    self.assertEqual(catalog["active_account_id"], "bybit-one")
                    self.assertEqual(catalog["session_generation"], 2)
                    self.assertEqual(catalog["accounts"][0]["status"], expected)
                    self.assertEqual(projection["wallet_balance_usdt"], "332.3")
                    self.assertEqual(projection["total_equity_usdt"], "80.37")
                    self.assertEqual(projection["available_balance_usdt"], "61.25")
                    self.assertEqual(len({
                        projection["wallet_balance_usdt"],
                        projection["total_equity_usdt"],
                        projection["available_balance_usdt"],
                    }), 3)
                    self.assertEqual(projection["projection_generation"], 8)
                    self.assertEqual(projection["balance_source_fields"]["account_type"], "UNIFIED")
                    self.assertEqual(
                        projection["balance_source_fields"]["available_balance_usdt"],
                        "result.list[0].totalAvailableBalance",
                    )
                    self.assertEqual(
                        projection["balance_provenance"]["account.totalAvailableBalance"],
                        "61.25",
                    )
                finally:
                    runtime.close()

    def test_failed_or_unknown_restore_stays_paper_without_generation_change(self):
        for preferred, validator in (
            ("bybit-one", Validator(fail=True)), ("deleted-account", Validator()),
        ):
            with self.subTest(preferred=preferred), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                database_path = root / "paper.sqlite3"
                preference = ActiveAccountPreferenceStore(database_path.with_suffix(".active_account.json"))
                preference.save(TradingAccountId(preferred))
                runtime = runtime_owner(
                    database_path, credential_store=CredentialStore(stored_account()),
                    account_validator=validator,
                    live_adapter_factory=ReadAdapter,
                )
                try:
                    catalog = runtime.call(lambda owner: owner.account_catalog())
                    self.assertEqual(catalog["active_account_id"], "paper")
                    self.assertEqual(catalog["session_generation"], 1)
                finally:
                    runtime.close()

    def test_ineligible_switch_does_not_replace_persisted_preference(self):
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "paper.sqlite3"
            preference_path = database_path.with_suffix(".active_account.json")
            preference = ActiveAccountPreferenceStore(preference_path)
            preference.save(TradingAccountId("paper"))
            manager = paper_account_manager()
            manager.register_inactive(TradingAccount(
                TradingAccountId("bybit-one"), "Main", TradingAccountProvider.BYBIT,
                TradingAccountEnvironment.MAINNET, TradingAccountStatus.ERROR,
            ))
            runtime = runtime_owner(database_path, account_manager=manager)
            try:
                with self.assertRaisesRegex(RuntimeError, "account_activation_not_ready"):
                    activate_current(runtime, "bybit-one")
                self.assertEqual(preference.load(), TradingAccountId("paper"))
                self.assertEqual(manager.session_token.generation, 1)
                self.assertEqual(manager.active_account_id, TradingAccountId("paper"))
            finally:
                runtime.close()

    def test_persisted_paper_restores_without_reconnect_or_generation_increment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database_path = root / "paper.sqlite3"
            preference = ActiveAccountPreferenceStore(database_path.with_suffix(".active_account.json"))
            preference.save(TradingAccountId("paper"))
            runtime = runtime_owner(
                database_path,
            )
            try:
                catalog = runtime.call(lambda owner: owner.account_catalog())
                self.assertEqual((catalog["active_account_id"], catalog["session_generation"]), ("paper", 1))
            finally:
                runtime.close()
