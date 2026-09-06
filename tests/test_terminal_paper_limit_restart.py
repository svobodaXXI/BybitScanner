import tempfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.api.models import ClientActionId, CommandResultStatus, LimitCommandRequest, TimeInForce, VolumeRequest, VolumeUnit
from terminal.domain.models import Category, OrderSide, Price, Quantity, Symbol
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_runtime import PaperRuntime


class StaticBookProvider:
    def get_book(self, symbol: Symbol) -> NormalizedOrderBook:
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(Decimal("64249.5")), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(Decimal("64250.5")), Quantity(Decimal("10"))),),
            health=BookHealth.READY,
            received_at_ms=1,
            available_depth=1,
        )


def instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR, "BTCUSDT", "LinearPerpetual", "Trading",
        "BTC", "USDT", "USDT", Decimal("0.5"), Decimal("1000000"),
        Decimal("0.5"), Decimal("0.001"), Decimal("100"), Decimal("50"),
        Decimal("0.001"), Decimal("5"),
    )


def runtime(path: Path) -> PaperRuntime:
    primary = instrument()
    return PaperRuntime(
        path,
        book_provider=StaticBookProvider(),
        instrument_snapshot=primary,
        instrument_provider=lambda symbol: replace(primary, symbol=symbol),
    )


def test_active_paper_limit_survives_runtime_restart():
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "paper.sqlite3"
        first = runtime(database_path)
        try:
            created = first.create_limit(LimitCommandRequest(
                ClientActionId("restart-limit-create-1"),
                "BTCUSDT",
                OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("64000"),
                Decimal("64000"),
                TimeInForce.GTC,
            ))
            assert created.status is CommandResultStatus.COMPLETED
            before = first.paper_state("BTCUSDT")
            assert [item["order_id"] for item in before["active_limit_orders"]] == [created.order_id]
        finally:
            first.close()

        restarted = runtime(database_path)
        try:
            after = restarted.paper_state("BTCUSDT")
            assert [item["order_id"] for item in after["active_limit_orders"]] == [created.order_id]
            assert after["active_limit_orders"][0]["side"] == "Buy"
            assert after["active_limit_orders"][0]["price"] == "64000.0"
            assert after["active_limit_orders"][0]["time_in_force"] == "GTC"
        finally:
            restarted.close()
