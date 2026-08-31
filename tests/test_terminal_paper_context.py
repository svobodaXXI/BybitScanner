import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.domain.models import Category, PositionSide, TradingAccountId
from terminal.domain.states import ConnectivityState
from terminal.exchange.events import InstrumentSnapshot
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_context import PaperCommandContextProvider


class PaperCommandContextProviderTests(unittest.TestCase):
    def test_builds_trusted_flat_context_and_rejects_non_active_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
            try:
                store.initialize_paper_account(
                    TradingAccountId("paper"),
                    Decimal("5000"),
                    updated_at_ms=1000,
                )
                provider = PaperCommandContextProvider(
                    store=store,
                    account_id=TradingAccountId("paper"),
                    instrument=InstrumentSnapshot(
                        Category.LINEAR,
                        "BTCUSDT",
                        "LinearPerpetual",
                        "Trading",
                        "BTC",
                        "USDT",
                        "USDT",
                        Decimal("1"),
                        Decimal("1000000"),
                        Decimal("0.5"),
                        Decimal("0.001"),
                        Decimal("100"),
                        Decimal("50"),
                        Decimal("0.001"),
                        Decimal("5"),
                    ),
                    active_account_id_provider=lambda: TradingAccountId("paper"),
                )

                result = provider.context_for("BTCUSDT")

                self.assertIs(result.pretrade.position_side, PositionSide.FLAT)
                self.assertEqual(result.pretrade.confirmed_position_quantity, Decimal("0"))
                self.assertTrue(result.pretrade.account_trusted)
                self.assertTrue(result.pretrade.position_trusted)
                self.assertIs(result.pretrade.connectivity, ConnectivityState.ONLINE)
                self.assertEqual(result.one_wv_usdt, Decimal("250"))
                self.assertEqual(result.position.size, Decimal("0"))

                provider.account_id = TradingAccountId("other")
                with self.assertRaisesRegex(
                    RuntimeError, "not the active trading account"
                ):
                    provider.context_for("BTCUSDT")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
