"""AddExpense application use case."""

from app.application.dtos import AddExpenseCommand, TradeResult
from app.application.errors import TradeAlreadyClosedError
from app.application.ports.repositories import TradeRepository
from app.application.use_cases._common import require_trade
from app.core.trades.enums import TradeStatus


class AddExpense:
    def __init__(self, trade_repository: TradeRepository) -> None:
        self._trades = trade_repository

    async def execute(self, command: AddExpenseCommand) -> TradeResult:
        if not isinstance(command, AddExpenseCommand):
            raise TypeError("command must be AddExpenseCommand")
        trade = require_trade(await self._trades.get_by_id(command.trade_id), command.trade_id)
        if trade.status is not TradeStatus.OPEN:
            raise TradeAlreadyClosedError(f"trade is not OPEN: {command.trade_id}")
        trade.add_expense(command.expense)
        await self._trades.save(trade)
        return TradeResult.from_trade(trade)
