"""CloseManualTrade application use case."""

from app.application.dtos import CloseManualTradeCommand, TradeResult
from app.application.errors import TradeAlreadyClosedError
from app.application.automatic_market_data import AutomaticTradeDataCapture
from app.application.ports.repositories import TradeRepository
from app.application.use_cases._common import as_price, require_trade
from app.core.trades.enums import TradeStatus


class CloseManualTrade:
    def __init__(self, trade_repository: TradeRepository, automatic_observation_repository=None, automatic_capture=None) -> None:
        self._trades = trade_repository
        self._automatic_observations = automatic_observation_repository
        self._automatic_capture = automatic_capture or AutomaticTradeDataCapture()

    async def execute(self, command: CloseManualTradeCommand) -> TradeResult:
        if not isinstance(command, CloseManualTradeCommand):
            raise TypeError("command must be CloseManualTradeCommand")
        trade = require_trade(await self._trades.get_by_id(command.trade_id), command.trade_id)
        if trade.status is not TradeStatus.OPEN:
            raise TradeAlreadyClosedError(f"trade is not OPEN: {command.trade_id}")
        trade.close(as_price(command.exit_price), command.closed_at)
        await self._trades.save(trade)
        if self._automatic_observations is not None:
            await self._automatic_capture.capture(trade, self._automatic_observations)
        return TradeResult.from_trade(trade)
