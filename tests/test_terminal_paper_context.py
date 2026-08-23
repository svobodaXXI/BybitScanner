import tempfile
from decimal import Decimal
from pathlib import Path

from terminal.domain.models import Category, PositionSide, TradingAccountId
from terminal.domain.states import ConnectivityState
from terminal.exchange.events import InstrumentSnapshot
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_context import PaperCommandContextProvider


def test_paper_context_provider_builds_trusted_flat_context():
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
            )

            result = provider.context_for("BTCUSDT")

            assert result.pretrade.position_side is PositionSide.FLAT
            assert result.pretrade.confirmed_position_quantity == Decimal("0")
            assert result.pretrade.account_trusted is True
            assert result.pretrade.position_trusted is True
            assert result.pretrade.connectivity is ConnectivityState.ONLINE
            assert result.one_wv_usdt == Decimal("250")
            assert result.position.size == Decimal("0")
        finally:
            store.close()
