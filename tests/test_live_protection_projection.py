from decimal import Decimal

from terminal.application.live_account_reconciliation import _position_projection
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.exchange.events import NormalizedPositionStatus, PositionEvent


def test_live_position_projection_preserves_protection_evidence():
    account_id = TradingAccountId("bybit-main")
    position = PositionEvent(
        position_key=PositionKey(account_id, Category.LINEAR, Symbol("BTCUSDT"), 0),
        side=PositionSide.LONG,
        size=Decimal("0.01"),
        average_entry=Decimal("64000"),
        mark_price=Decimal("64500"),
        position_value=Decimal("645"),
        unrealized_pnl=Decimal("5"),
        current_realized_pnl=Decimal("0"),
        cumulative_realized_pnl=Decimal("0"),
        status=NormalizedPositionStatus.NORMAL,
        raw_status="Normal",
        take_profit=Decimal("68000"),
        stop_loss=Decimal("62000"),
        trailing_stop=Decimal("0"),
        sequence=None,
        updated_at_ms=123,
    )

    projected = _position_projection(account_id.value, position)

    assert projected["take_profit"] == "68000"
    assert projected["stop_loss"] == "62000"
    assert projected["trailing_stop"] == "0"
