import tempfile
import unittest
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from decimal import Decimal
from pathlib import Path

from terminal.application.trading_accounts import (
    TradingAccount, TradingAccountEnvironment, TradingAccountProvider,
    TradingAccountStatus, paper_account_manager,
)
from terminal.domain.models import TradingAccountId
from terminal.domain.models import Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.persistence.live_account_store import LiveAccountProjectionStore, LiveAccountSnapshot
from tests.test_terminal_paper_http import _runtime_owner
from terminal.runtime.paper_http_server import PaperHttpHandler


def manager_with_bybit(status=TradingAccountStatus.READY):
    manager = paper_account_manager()
    manager.register_inactive(TradingAccount(
        TradingAccountId("bybit-one"), "Main", TradingAccountProvider.BYBIT,
        TradingAccountEnvironment.MAINNET, status,
    ))
    return manager


def publish_live(store):
    store.publish(LiveAccountSnapshot(
        "bybit-one", "MAINNET", False, 1, Decimal("90"), Decimal("100"), Decimal("70"),
        1000,
        ({"account_id": "bybit-one", "symbol": "BTCUSDT", "side": "Long", "size": "1"},),
        ({"account_id": "bybit-one", "symbol": "ETHUSDT", "order_id": "o1", "side": "Buy"},),
        1100,
    ))


class AccountSwitchingTests(unittest.TestCase):
    def test_orderbook_paper_processing_tracks_authoritative_active_account(self):
        class MutableBookProvider:
            update_id = "BTCUSDT:1:1"

            def get_book(self, symbol):
                return NormalizedOrderBook(
                    symbol=Symbol(symbol.value),
                    bids=(PriceLevel(Price(Decimal("64249.5")), Quantity(Decimal("10"))),),
                    asks=(PriceLevel(Price(Decimal("64250.5")), Quantity(Decimal("10"))),),
                    health=BookHealth.READY,
                    received_at_ms=1,
                    available_depth=1,
                )

            def get_current_book_update(self, symbol):
                return self.update_id, self.get_book(symbol)

        for live_status in (TradingAccountStatus.READY, TradingAccountStatus.READ_ONLY):
            with self.subTest(live_status=live_status), tempfile.TemporaryDirectory() as temp:
                manager = manager_with_bybit(live_status)
                books = MutableBookProvider()
                live_path = Path(temp) / "live.sqlite3"
                live_store = LiveAccountProjectionStore(live_path)
                live_store.publish(LiveAccountSnapshot(
                    "bybit-one", "MAINNET", live_status is TradingAccountStatus.READ_ONLY,
                    1, Decimal("90"), Decimal("100"), Decimal("70"), 1000, (), (), 1100,
                ))
                live_store.close()
                runtime = _runtime_owner(
                    Path(temp) / "paper.sqlite3",
                    account_manager=manager,
                    book_provider=books,
                    live_account_store_path=live_path,
                )
                try:
                    paper_generation = manager.session_token.generation
                    class ContextSpy:
                        def __init__(self, delegate):
                            self.delegate = delegate
                            self.calls = 0

                        def context_for(self, symbol):
                            self.calls += 1
                            return self.delegate.context_for(symbol)

                    context = runtime.call(lambda owner: ContextSpy(owner._context))
                    runtime.call(lambda owner: setattr(owner, "_context", context))

                    self.assertEqual(
                        runtime.call(lambda owner: owner.process_orderbook_update(books.update_id)),
                        0,
                    )
                    self.assertEqual(context.calls, 1)

                    runtime.call(lambda owner: owner.activate_account("bybit-one"))
                    live_generation = manager.session_token.generation
                    books.update_id = "BTCUSDT:2:2"
                    execution_count = runtime.call(lambda owner: len(owner.store.load_executions()))
                    self.assertEqual(
                        runtime.call(lambda owner: owner.process_orderbook_update(books.update_id)),
                        0,
                    )
                    self.assertEqual(context.calls, 1)
                    self.assertEqual(
                        runtime.call(lambda owner: len(owner.store.load_executions())),
                        execution_count,
                    )
                    self.assertEqual(manager.session_token.generation, live_generation)

                    runtime.call(lambda owner: owner.activate_account("paper"))
                    resumed_generation = manager.session_token.generation
                    self.assertEqual(
                        runtime.call(lambda owner: owner.process_orderbook_update(books.update_id)),
                        0,
                    )
                    self.assertEqual(context.calls, 2)
                    self.assertEqual(manager.session_token.generation, resumed_generation)
                    self.assertEqual((paper_generation, live_generation, resumed_generation), (1, 2, 3))
                finally:
                    runtime.close()

    def test_every_existing_mutation_route_is_backend_blocked_for_live(self):
        class LiveRuntime:
            calls = 0

            def call(self, operation, timeout=15.0):
                return operation(self)

            def require_paper_mutations(self):
                self.calls += 1
                raise RuntimeError("live_mutations_disabled")

        runtime = LiveRuntime()
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        routes = (
            "/api/market", "/api/limit", "/api/limit/amend", "/api/limit/cancel",
            "/api/stop", "/api/stop/amend", "/api/stop/delete",
            "/api/take", "/api/take/amend", "/api/take/delete",
            "/api/full-close", "/api/close-all",
        )
        try:
            for route in routes:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}{route}",
                    data=json.dumps({}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code, 409)
                self.assertEqual(json.load(caught.exception), {
                    "ok": False, "error": "live_mutations_disabled",
                })
            self.assertEqual(runtime.calls, len(routes))
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_paper_live_paper_switch_is_atomic_and_restores_paper_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = manager_with_bybit()
            live_store = LiveAccountProjectionStore(Path(temp) / "live.sqlite3")
            publish_live(live_store)
            live_store.close()
            runtime = _runtime_owner(
                Path(temp) / "paper.sqlite3", account_manager=manager,
                live_account_store_path=Path(temp) / "live.sqlite3",
            )
            try:
                paper_before = runtime.call(lambda owner: owner.workspace_account_projection("BTCUSDT"))
                live = runtime.call(lambda owner: owner.activate_account("bybit-one"))
                live_projection = runtime.call(lambda owner: owner.workspace_account_projection("BTCUSDT"))
                with self.assertRaisesRegex(RuntimeError, "live_mutations_disabled"):
                    runtime.call(lambda owner: owner.require_paper_mutations())
                paper = runtime.call(lambda owner: owner.activate_account("paper"))
                paper_after = runtime.call(lambda owner: owner.workspace_account_projection("BTCUSDT"))
                self.assertEqual(live, {
                    "active_account_id": "bybit-one", "session_generation": 2, "status": "READY",
                })
                self.assertEqual(live_projection["positions"][0]["account_id"], "bybit-one")
                self.assertEqual(live_projection["orders"][0]["account_id"], "bybit-one")
                self.assertEqual(paper["session_generation"], 3)
                self.assertEqual(paper_before["account_id"], "paper")
                self.assertEqual(paper_after["account_id"], "paper")
                self.assertEqual(paper_before["wallet_balance_usdt"], paper_after["wallet_balance_usdt"])
                catalog = runtime.call(lambda owner: owner.account_catalog())
                self.assertEqual(catalog["accounts"][0]["id"], "paper")
                self.assertEqual(sum(item["id"] == catalog["active_account_id"] for item in catalog["accounts"]), 1)
            finally:
                runtime.close()

    def test_read_only_is_eligible_but_disconnected_and_error_preserve_authority(self):
        for status in (
            TradingAccountStatus.DISCONNECTED,
            TradingAccountStatus.RECONCILING,
            TradingAccountStatus.ERROR,
        ):
            with self.subTest(status=status):
                manager = manager_with_bybit(status)
                before = manager.session_token
                with self.assertRaisesRegex(RuntimeError, "account_activation_not_ready"):
                    manager.activate(TradingAccountId("bybit-one"))
                self.assertEqual(manager.session_token, before)
        manager = manager_with_bybit(TradingAccountStatus.READ_ONLY)
        token = manager.activate(TradingAccountId("bybit-one"))
        self.assertEqual(token.generation, 2)
        self.assertEqual(token.active_account_id, TradingAccountId("bybit-one"))

    def test_read_only_runtime_activation_requires_and_projects_read_only_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = manager_with_bybit(TradingAccountStatus.READ_ONLY)
            live_path = Path(temp) / "live.sqlite3"
            store = LiveAccountProjectionStore(live_path)
            store.publish(LiveAccountSnapshot(
                "bybit-one", "MAINNET", True, 1, Decimal("90"), Decimal("100"),
                Decimal("70"), 1000, (), (), 1100,
            ))
            store.close()
            runtime = _runtime_owner(
                Path(temp) / "paper.sqlite3", account_manager=manager,
                live_account_store_path=live_path,
            )
            try:
                switched = runtime.call(lambda owner: owner.activate_account("bybit-one"))
                projected = runtime.call(
                    lambda owner: owner.workspace_account_projection("BTCUSDT")
                )
                self.assertEqual(switched["status"], "READ_ONLY")
                self.assertTrue(projected["read_only"])
                self.assertEqual(projected["account_id"], "bybit-one")
            finally:
                runtime.close()

    def test_catalog_sorts_current_first_without_changing_status(self):
        manager = manager_with_bybit()
        manager.activate(TradingAccountId("bybit-one"))
        catalog = manager.catalog_projection()
        self.assertEqual([item["id"] for item in catalog["accounts"]], ["bybit-one", "paper"])
        self.assertEqual(catalog["accounts"][1]["status"], "READY")
        same = manager.activate(TradingAccountId("bybit-one"))
        self.assertEqual(same.generation, 2)
