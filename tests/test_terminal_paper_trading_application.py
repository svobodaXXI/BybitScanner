import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.pretrade_guard import (
    AdmittedPreTradeRequest,
    IntentClassification,
    OrderKind,
    PreTradeDecision,
    SlippageMetadata,
    SlippageToleranceType,
)
from terminal.application.trading_application import TradingApplication
from terminal.domain.models import (
    Category,
    OrderSide,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.executor import PaperMarketExecutor
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT = TradingAccountId("paper")


class Guard:
    def __init__(self, decision):
        self.decision = decision

    def evaluate(self, intent, context):
        return self.decision


class AdapterMustNotRun:
    def __init__(self):
        self.calls = 0

    def create_market_order(self, **kwargs):
        self.calls += 1
        raise AssertionError("Bybit/live adapter must not run for PAPER Market execution")

    def create_limit_order(self, **kwargs):
        self.calls += 1
        raise AssertionError("unexpected live adapter call")

    def amend_order(self, **kwargs):
        self.calls += 1
        raise AssertionError("unexpected live adapter call")

    def cancel_order(self, **kwargs):
        self.calls += 1
        raise AssertionError("unexpected live adapter call")

    def set_trading_stop(self, **kwargs):
        self.calls += 1
        raise AssertionError("unexpected live adapter call")


class BookProvider:
    def __init__(self, book):
        self.book = book

    def get_book(self, symbol):
        return self.book if self.book.symbol == symbol else None


def admitted():
    identity = CommandIdentityFactory(lambda: uuid.UUID(int=1)).create()
    request = AdmittedPreTradeRequest(
        identity=identity,
        trading_account_id=ACCOUNT,
        category=Category.LINEAR,
        symbol="BTCUSDT",
        position_idx=0,
        side=OrderSide.BUY,
        order_kind=OrderKind.MARKET,
        requested_notional=Decimal("202"),
        sizing_reference_price=Decimal("101"),
        raw_quantity=Decimal("2"),
        normalized_quantity=Decimal("2"),
        final_quantity=Decimal("2"),
        normalized_limit_price=None,
        classification=IntentClassification.ENTRY,
        reduce_only=False,
        capped_at_flat=False,
        slippage=SlippageMetadata(
            SlippageToleranceType.PERCENT,
            Decimal("0.5"),
        ),
    )
    return PreTradeDecision(True, None, "admitted", request)


def test_trading_application_paper_market_finishes_filled_without_live_adapter():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
        try:
            engine = ExecutionEngine(store)
            adapter = AdapterMustNotRun()

            book = NormalizedOrderBook(
                symbol=Symbol("BTCUSDT"),
                bids=(
                    PriceLevel(Price(Decimal("99")), Quantity(Decimal("5"))),
                ),
                asks=(
                    PriceLevel(Price(Decimal("100")), Quantity(Decimal("1"))),
                    PriceLevel(Price(Decimal("102")), Quantity(Decimal("1"))),
                ),
                health=BookHealth.READY,
                received_at_ms=1000,
                available_depth=2,
            )

            paper_executor = PaperMarketExecutor(
                BookProvider(book),
                engine,
                max_book_age_ms=1000,
                fee_rate=Decimal("0.001"),
                clock_ms=lambda: 1500,
            )

            app = TradingApplication(
                Guard(admitted()),
                store,
                adapter,
                engine,
                mutations_enabled=True,
                clock_ms=lambda: 1500,
                paper_market_executor=paper_executor,
            )

            result = app.submit(object(), object())

            assert result.command is not None
            assert result.command.current_state is CommandState.FILLED
            assert adapter.calls == 0

            projection = store.get_position_projection(
                PositionKey(
                    ACCOUNT,
                    Category.LINEAR,
                    Symbol("BTCUSDT"),
                    0,
                )
            )

            assert projection is not None
            assert projection.side is PositionSide.LONG
            assert projection.quantity.value == Decimal("2")
            assert projection.average_entry.value == Decimal("101")
            assert projection.engaged_notional.value == Decimal("202")
            assert projection.accumulated_fee == Decimal("0.202")
            assert len(store.load_executions()) == 1
        finally:
            store.close()
