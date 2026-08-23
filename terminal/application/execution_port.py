"""Transport-neutral mutation boundary for trading execution."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from terminal.exchange.bybit_v5_mutation_adapter import MutationOutcome


class ExecutionPort(Protocol):
    """Mutation interface shared by live and paper execution adapters."""

    def create_market_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: Decimal,
        order_link_id: str,
        reduce_only: bool,
        slippage_tolerance_type: str,
        slippage_tolerance: Decimal,
    ) -> MutationOutcome: ...

    def create_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        order_link_id: str,
        reduce_only: bool = False,
    ) -> MutationOutcome: ...

    def amend_order(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
        qty: Decimal | None = None,
        price: Decimal | None = None,
    ) -> MutationOutcome: ...

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
    ) -> MutationOutcome: ...

    def set_trading_stop(
        self,
        *,
        symbol: str,
        take_profit: Decimal | None,
        stop_loss: Decimal | None,
        tp_trigger_by: str,
        sl_trigger_by: str,
    ) -> MutationOutcome: ...
