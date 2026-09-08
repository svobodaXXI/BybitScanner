"""CreateManualTrade application use case."""

from app.application.dtos import CreateManualTradeCommand, TradeResult
from app.application.errors import AccountNotFoundError
from app.application.automatic_market_data import AutomaticTradeDataCapture
from app.application.ports.repositories import AccountRepository, TradeRepository
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.trades.trade import Trade


class CreateManualTrade:
    def __init__(self, account_repository: AccountRepository, trade_repository: TradeRepository, automatic_observation_repository=None, automatic_capture=None) -> None:
        self._accounts = account_repository
        self._trades = trade_repository
        self._automatic_observations = automatic_observation_repository
        self._automatic_capture = automatic_capture or AutomaticTradeDataCapture()

    async def execute(self, command: CreateManualTradeCommand) -> TradeResult:
        if not isinstance(command, CreateManualTradeCommand):
            raise TypeError("command must be CreateManualTradeCommand")
        if not await self._accounts.exists(command.account_id):
            raise AccountNotFoundError(f"account not found: {command.account_id}")

        trade = Trade.open(
            account_id=command.account_id,
            instrument_id=command.instrument_id,
            direction=command.direction,
            entry_price=command.entry_price if isinstance(command.entry_price, Price) else Price(command.entry_price),
            quantity=command.quantity if isinstance(command.quantity, Quantity) else Quantity(command.quantity),
            opened_at=command.opened_at,
            currency=command.currency,
            trade_id=command.trade_id,
            stop_price=command.stop_price,
            take_profit=command.take_profit,
            risk=command.risk,
            fees=command.fees,
            expenses=command.expenses,
        )
        await self._trades.save(trade)
        if self._automatic_observations is not None:
            await self._automatic_capture.capture(trade, self._automatic_observations)
        return TradeResult.from_trade(trade)
