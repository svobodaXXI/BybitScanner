"""AddFee application use case."""

from app.application.dtos import AddFeeCommand, TradeResult
from app.application.errors import TradeAlreadyClosedError
from app.application.ports.repositories import TradeRepository
from app.application.use_cases._common import require_trade
from app.core.trades.enums import TradeStatus


class AddFee:
    def __init__(self, trade_repository: TradeRepository) -> None:
        self._trades = trade_repository

    async def execute(self, command: AddFeeCommand) -> TradeResult:
        if not isinstance(command, AddFeeCommand):
            raise TypeError("command must be AddFeeCommand")
        trade = require_trade(await self._trades.get_by_id(command.trade_id), command.trade_id)
        if trade.status is not TradeStatus.OPEN:
            raise TradeAlreadyClosedError(f"trade is not OPEN: {command.trade_id}")
        trade.add_fee(command.fee)
        await self._trades.save(trade)
        return TradeResult.from_trade(trade)
