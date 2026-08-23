import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.models import ReconciliationResult, TrustState
from terminal.application.pretrade_guard import (
    IntentClassification,
    MutationGate,
    NotionalIntent,
    OrderKind,
    PreTradeContext,
    PreTradeGuard,
    PreTradeIntent,
    SlippageMetadata,
    SlippageToleranceType,
)
from terminal.application.trading_application import TradingApplication
from terminal.domain.models import (
    Category,
    ExecutionId,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.domain.states import CommandState, ConnectivityState
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.executor import PaperMarketExecutor
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("BTCUSDT")
POSITION_KEY = PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0)


class AdapterMustNotRun:
    def __init__(self):
        self.calls = 0

    def _fail(self):
        self.calls += 1
        raise AssertionError("live/Bybit adapter must not run for PAPER Market execution")

    def create_market_order(self, **kwargs):
        self._fail()

    def create_limit_order(self, **kwargs):
        self._fail()

    def amend_order(self, **kwargs):
        self._fail()

    def cancel_order(self, **kwargs):
        self._fail()

    def set_trading_stop(self, **kwargs):
        self._fail()


class BookProvider:
    def __init__(self, book):
        self.book = book

    def get_book(self, symbol):
        return self.book if self.book.symbol == symbol else None


def instrument():
    return InstrumentSnapshot(
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
    )


def reconciliation():
    return ReconciliationResult(
        trust_state=TrustState.CONVERGED,
        position_key=POSITION_KEY,
        active_orders=(),
        unresolved_command_ids=(),
        applied_execution_count=0,
        duplicate_execution_count=0,
        checkpoint=None,
        flat_transition=None,
        reasons=(),
    )


def test_real_guard_caps_paper_market_sell_at_flat_and_never_reverses():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
        try:
            engine = ExecutionEngine(store)

            entry_book = NormalizedOrderBook(
                symbol=SYMBOL,
                bids=(
                    PriceLevel(Price(Decimal("99")), Quantity(Decimal("5"))),
                ),
                asks=(
                    PriceLevel(Price(Decimal("100")), Quantity(Decimal("2"))),
                ),
                health=BookHealth.READY,
                received_at_ms=1000,
                available_depth=1,
            )

            provider = BookProvider(entry_book)
            paper_executor = PaperMarketExecutor(
                provider,
                engine,
                max_book_age_ms=1000,
                fee_rate=Decimal("0.001"),
                clock_ms=lambda: 1500,
            )

            paper_executor.execute(
                trading_account_id=ACCOUNT,
                symbol=SYMBOL,
                side=OrderSide.BUY,
                quantity=Quantity(Decimal("2")),
                order_link_id="entry-link",
                order_id=OrderId("entry-order"),
                exec_id=ExecutionId("entry-exec"),
            )

            exit_book = NormalizedOrderBook(
                symbol=SYMBOL,
                bids=(
                    PriceLevel(Price(Decimal("110")), Quantity(Decimal("5"))),
                ),
                asks=(
                    PriceLevel(Price(Decimal("111")), Quantity(Decimal("5"))),
                ),
                health=BookHealth.READY,
                received_at_ms=3000,
                available_depth=1,
            )
            provider.book = exit_book
            paper_executor.clock_ms = lambda: 3500

            guard = PreTradeGuard(
                gate=MutationGate(mutations_enabled=True),
                identity_factory=CommandIdentityFactory(lambda: uuid.UUID(int=2)),
            )
            adapter = AdapterMustNotRun()

            app = TradingApplication(
                guard,
                store,
                adapter,
                engine,
                mutations_enabled=True,
                clock_ms=lambda: 3500,
                paper_market_executor=paper_executor,
            )

            intent = PreTradeIntent(
                symbol="BTCUSDT",
                side=OrderSide.SELL,
                order_kind=OrderKind.MARKET,
                volume=NotionalIntent(Decimal("500")),
                sizing_reference_price=Decimal("100"),
                slippage=SlippageMetadata(
                    SlippageToleranceType.PERCENT,
                    Decimal("0.5"),
                ),
            )

            context = PreTradeContext(
                selected_account_id=ACCOUNT,
                category=Category.LINEAR,
                position_key=POSITION_KEY,
                reported_position_idx=0,
                position_side=PositionSide.LONG,
                confirmed_position_quantity=Decimal("2"),
                account_trusted=True,
                position_trusted=True,
                connectivity=ConnectivityState.ONLINE,
                reconciliation=reconciliation(),
                conflicting_unresolved_command=False,
                instrument=instrument(),
            )

            result = app.submit(intent, context)

            assert result.decision is not None
            assert result.decision.admitted is True
            assert result.decision.request is not None
            assert result.decision.request.classification is IntentClassification.CLOSE
            assert result.decision.request.reduce_only is True
            assert result.decision.request.capped_at_flat is True
            assert result.decision.request.normalized_quantity == Decimal("5")
            assert result.decision.request.final_quantity == Decimal("2")

            assert result.command is not None
            assert result.command.current_state is CommandState.FILLED
            assert adapter.calls == 0

            projection = store.get_position_projection(POSITION_KEY)

            assert projection is not None
            assert projection.side is PositionSide.FLAT
            assert projection.quantity.value == Decimal("0")
            assert projection.average_entry is None
            assert projection.realized_pnl == Decimal("20")
            assert projection.accumulated_fee == Decimal("0.420")
            assert projection.engaged_notional.value == Decimal("0")
            assert len(store.load_executions()) == 2
        finally:
            store.close()
