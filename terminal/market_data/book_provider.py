"""Read boundary for normalized order books."""

from __future__ import annotations

from typing import Protocol

from terminal.domain.models import Symbol
from terminal.market_data.models import NormalizedOrderBook


class MarketBookProvider(Protocol):
    """Provides the latest normalized book for one symbol."""

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None: ...
