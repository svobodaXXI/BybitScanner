"""Read-only Trading Diary D1 service over existing Terminal persistence."""

from __future__ import annotations

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore

from .models import DiaryEnvironment, TradeEpisode
from .reconstruction import TradeEpisodeReconstructor


class TradeEpisodeReadService:
    """Reconstruct one account's episodes from Terminal-persisted executions."""

    def __init__(
        self,
        store: SQLiteStore,
        *,
        trading_account_id: TradingAccountId,
        environment: DiaryEnvironment,
    ):
        if not isinstance(store, SQLiteStore):
            raise TypeError("store must be SQLiteStore")
        if not isinstance(trading_account_id, TradingAccountId):
            raise TypeError("trading_account_id must be TradingAccountId")
        self._store = store
        self._trading_account_id = trading_account_id
        self._environment = DiaryEnvironment(environment)
        self._reconstructor = TradeEpisodeReconstructor()

    def list_episodes(self, *, symbol: Symbol | None = None) -> tuple[TradeEpisode, ...]:
        executions = tuple(
            item
            for item in self._store.load_executions()
            if item.dedup_key.trading_account_id == self._trading_account_id
            and (symbol is None or item.symbol == symbol)
        )
        return self._reconstructor.reconstruct(executions, environment=self._environment)
