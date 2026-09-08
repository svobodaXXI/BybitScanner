"""ListOpenTrades application use case."""

from app.application.dtos import ListOpenTradesCommand, ListOpenTradesResult
from app.application.ports.repositories import TradeRepository
from app.application.use_cases._common import view


class ListOpenTrades:
    def __init__(self, trade_repository: TradeRepository) -> None:
        self._trades = trade_repository

    async def execute(self, command: ListOpenTradesCommand | None = None) -> ListOpenTradesResult:
        if command is None:
            command = ListOpenTradesCommand()
        if not isinstance(command, ListOpenTradesCommand):
            raise TypeError("command must be ListOpenTradesCommand")
        trades = await self._trades.list_open(
            account_id=command.account_id,
            instrument_id=command.instrument_id,
        )
        ordered = sorted(trades, key=lambda item: (item.opened_at, str(item.trade_id)))
        return ListOpenTradesResult(tuple(view(trade) for trade in ordered))
