"""Shared, deliberately small helpers for manual use cases."""

from datetime import datetime, timezone

from app.application.dtos import TradeView
from app.application.errors import TradeNotFoundError
from app.core.statistics.derived_value_context import DerivedValueContext
from app.core.statistics.enums import CustomFieldPhase
from app.core.statistics.resolution_context import CustomFieldResolutionContext
from app.core.trades.enums import TradeStatus
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


def require_trade(trade: Trade | None, trade_id: TradeId) -> Trade:
    if trade is None:
        raise TradeNotFoundError(f"trade not found: {trade_id}")
    return trade


def as_price(value):
    from app.core.common.price import Price

    return value if isinstance(value, Price) else Price(value)


def default_resolution_context(trade: Trade) -> CustomFieldResolutionContext:
    phase = CustomFieldPhase.POST_TRADE if trade.status is TradeStatus.CLOSED else CustomFieldPhase.OPEN
    return CustomFieldResolutionContext(phase=phase)


def derived_context_from_trade(trade: Trade) -> DerivedValueContext:
    return DerivedValueContext(
        opened_at=trade.opened_at,
        quantity=trade.quantity,
        closed_at=trade.closed_at,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        stop_price=trade.stop_price,
        risk=trade.risk,
        gross_pnl=trade.gross_pnl,
        net_pnl=trade.net_pnl,
        currency=trade.fees.currency,
    )


def recorded_at_or_now(value: datetime | None) -> datetime:
    return value if value is not None else datetime.now(timezone.utc)


def view(trade: Trade) -> TradeView:
    return TradeView.from_trade(trade)
