"""ListAllTrades application use case."""

from app.application.dtos import ListAllTradesCommand, ListAllTradesResult
from app.application.ports.repositories import TradeRepository
from app.application.use_cases._common import view


class ListAllTrades:
    def __init__(self, trade_repository: TradeRepository) -> None:
        self._trades = trade_repository

    async def execute(self, command: ListAllTradesCommand | None = None) -> ListAllTradesResult:
        if command is None:
            command = ListAllTradesCommand()
        if not isinstance(command, ListAllTradesCommand):
            raise TypeError("command must be ListAllTradesCommand")
        trades = await self._trades.list_all(
            account_id=command.account_id,
            instrument_id=command.instrument_id,
            limit=command.limit,
            offset=command.offset,
        )
        ordered = sorted(trades, key=lambda item: (item.opened_at, str(item.trade_id)), reverse=True)
        return ListAllTradesResult(tuple(view(trade) for trade in ordered))
