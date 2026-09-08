"""In-memory state for the Telegram development harness."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import ExecutionSide
from app.core.trades.execution import Execution
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.trade_aggregate import TradeAggregate
from app.core.trades.trade_aggregation_service import TradeAggregationService
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


@dataclass(slots=True)
class InMemoryTradeStore:
    """Keep multiple trades in memory for the development harness."""

    trades: dict[TradeId, Trade] = field(default_factory=dict)
    instrument_symbols: dict[TradeId, str] = field(default_factory=dict)

    def add(self, trade: Trade, instrument_symbol: str) -> None:
        self.trades[trade.trade_id] = trade
        self.instrument_symbols[trade.trade_id] = instrument_symbol

    def get(self, trade_id: TradeId) -> Trade | None:
        return self.trades.get(trade_id)

    def get_by_string(self, value: str) -> Trade | None:
        try:
            trade_id = TradeId.parse(value)
        except (TypeError, ValueError):
            return None
        return self.get(trade_id)

    def open(self) -> list[Trade]:
        return sorted(
            (trade for trade in self.trades.values() if trade.status.value == "OPEN"),
            key=lambda trade: (trade.opened_at, str(trade.trade_id)),
        )

    def all(self) -> list[Trade]:
        return sorted(self.trades.values(), key=lambda trade: (trade.opened_at, str(trade.trade_id)))

    def symbol_for(self, trade: Trade) -> str:
        return self.instrument_symbols.get(trade.trade_id, str(trade.instrument_id))


@dataclass(slots=True)
class ExecutionLabState:
    """Instance-scoped TEST/USDT context for manual execution acceptance tests."""

    account_id: AccountId = field(
        default_factory=lambda: AccountId.parse("00000000-0000-0000-0000-000000000001")
    )
    instrument_id: InstrumentId = field(default_factory=InstrumentId.generate)
    instrument_symbol: str = "TEST"
    currency: str = "USDT"
    service: TradeAggregationService = field(default_factory=TradeAggregationService)

    def make_fact(
        self,
        side: ExecutionSide,
        price: Price,
        quantity: Quantity,
        fee: Money,
        external_execution_id: str | None,
    ) -> ExecutionFact:
        if external_execution_id is None:
            external_execution_id = f"dev-{uuid4()}"
        return ExecutionFact(
            exchange="TEST",
            account_id=self.account_id,
            instrument_id=self.instrument_id,
            side=side,
            quantity=quantity,
            price=price,
            fee=fee,
            executed_at=datetime.now(timezone.utc),
            external_execution_id=external_execution_id,
        )

    def apply_fact(self, fact: ExecutionFact) -> tuple[Execution, TradeAggregate, bool]:
        """Apply through the real domain conversion and return duplicate status."""
        execution = Execution.from_fact(fact)
        duplicate = self.service.is_duplicate(execution)
        aggregate = self.service.apply(execution)
        return execution, aggregate, duplicate

    def aggregate(self) -> TradeAggregate | None:
        return self.service.get(self.account_id, self.instrument_id)

    def reset(self) -> None:
        self.service.reset()
