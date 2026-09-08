"""Safely edit optional stop/take levels on a journal trade."""

from app.application.dtos import UpdateTradeProtectionCommand, TradeResult
from app.application.ports.repositories import TradeRepository
from app.application.use_cases._common import require_trade


class UpdateTradeProtection:
    def __init__(self, trade_repository: TradeRepository) -> None:
        self._trades = trade_repository

    async def execute(self, command: UpdateTradeProtectionCommand) -> TradeResult:
        if not isinstance(command, UpdateTradeProtectionCommand):
            raise TypeError("command must be UpdateTradeProtectionCommand")
        trade = require_trade(await self._trades.get_by_id(command.trade_id), command.trade_id)
        if command.stop_price is not None:
            trade.set_stop_price(command.stop_price)
        if command.take_profit is not None:
            trade.set_take_profit(command.take_profit)
        await self._trades.save(trade)
        return TradeResult.from_trade(trade)
