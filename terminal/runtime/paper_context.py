"""PAPER command-context provider backed by durable local projections."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from terminal.api.rest import ServerCommandContext
from terminal.application.models import ReconciliationResult, TrustState
from terminal.application.pretrade_guard import PreTradeContext
from terminal.domain.models import (
    Category,
    PositionKey,
    PositionSide,
    Symbol,
    TradingAccountId,
)
from terminal.domain.states import ConnectivityState
from terminal.exchange.events import (
    InstrumentSnapshot,
    NormalizedPositionStatus,
    PositionEvent,
)
from terminal.persistence.sqlite_store import SQLiteStore


def working_volume_usdt(equity_usdt: Decimal) -> Decimal:
    one_wv = (
        equity_usdt * Decimal("0.05") / Decimal("10")
    ).to_integral_value(rounding=ROUND_DOWN) * Decimal("10")
    if one_wv <= 0:
        raise ValueError("paper equity is too small for working-volume sizing")
    return one_wv


@dataclass(slots=True)
class PaperCommandContextProvider:
    store: SQLiteStore
    account_id: TradingAccountId
    instrument: InstrumentSnapshot

    def context_for(self, symbol: str) -> ServerCommandContext:
        normalized_symbol = symbol.strip().upper()
        if normalized_symbol != self.instrument.symbol:
            raise ValueError("paper context symbol is unsupported")

        key = PositionKey(
            self.account_id,
            Category.LINEAR,
            Symbol(normalized_symbol),
            0,
        )
        projection = self.store.get_position_projection(key)
        account = self.store.get_paper_account(self.account_id)
        if account is None:
            raise ValueError("paper account is not initialized")

        one_wv_usdt = working_volume_usdt(account.equity_usdt)

        if projection is None:
            side = PositionSide.FLAT
            quantity = Decimal("0")
            average_entry = None
            realized_pnl = Decimal("0")
        else:
            side = projection.side
            quantity = projection.quantity.value
            average_entry = (
                projection.average_entry.value
                if projection.average_entry is not None
                else None
            )
            realized_pnl = projection.realized_pnl

        reconciliation = ReconciliationResult(
            trust_state=TrustState.CONVERGED,
            position_key=key,
            active_orders=(),
            unresolved_command_ids=(),
            applied_execution_count=0,
            duplicate_execution_count=0,
            checkpoint=None,
            flat_transition=None,
            reasons=(),
        )

        pretrade = PreTradeContext(
            selected_account_id=self.account_id,
            category=Category.LINEAR,
            position_key=key,
            reported_position_idx=0,
            position_side=side,
            confirmed_position_quantity=quantity,
            account_trusted=True,
            position_trusted=True,
            connectivity=ConnectivityState.ONLINE,
            reconciliation=reconciliation,
            conflicting_unresolved_command=False,
            instrument=self.instrument,
        )

        position = PositionEvent(
            position_key=key,
            side=side,
            size=quantity,
            average_entry=average_entry,
            mark_price=None,
            position_value=None,
            unrealized_pnl=None,
            current_realized_pnl=realized_pnl,
            cumulative_realized_pnl=realized_pnl,
            status=NormalizedPositionStatus.NORMAL,
            raw_status="PAPER",
            take_profit=None,
            stop_loss=None,
            trailing_stop=None,
            sequence=None,
            updated_at_ms=projection.updated_at_ms if projection is not None else 0,
        )

        return ServerCommandContext(
            pretrade=pretrade,
            instrument=self.instrument,
            position=position,
            one_wv_usdt=one_wv_usdt,
            protection_command_side=None,
        )

    def order_for(
        self,
        symbol: str,
        order_id: str | None,
        order_link_id: str | None,
    ):
        raise ValueError("paper runtime does not support amend/cancel yet")