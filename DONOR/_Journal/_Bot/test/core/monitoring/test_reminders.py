from datetime import datetime, timedelta, timezone

from app.core.monitoring import AttentionReminderPolicy, ReminderKind, ReminderSettings
from app.core.trades.trade import Trade
from app.core.accounts.account_id import AccountId
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeDirection
from app.core.trades.readiness import TradeReadiness, TradeReadinessStatus


NOW = datetime(2026, 9, 4, 20, tzinfo=timezone.utc)


def trade(status="OPEN"):
    item = Trade.open(AccountId.generate(), InstrumentId.generate(), TradeDirection.LONG, Price(100), Quantity(1), NOW - timedelta(hours=25), "USDT")
    if status == "CLOSED":
        item.close(Price(110), NOW - timedelta(hours=2))
    return item


def test_defaults_and_trade_thresholds():
    settings = ReminderSettings()
    assert settings.incomplete_reminder_delay == timedelta(hours=1)
    assert settings.open_trade_reminder_threshold == timedelta(hours=24)
    assert AttentionReminderPolicy.due_for_trade(trade(), NOW, settings) is ReminderKind.OPEN_TRADE
    assert AttentionReminderPolicy.due_for_trade(trade("CLOSED"), NOW, settings, readiness=TradeReadiness(TradeReadinessStatus.INCOMPLETE, ("EXIT_PRICE",))) is ReminderKind.INCOMPLETE_TRADE


def test_reminders_are_not_repeated_within_the_configured_window_and_digest_is_daily():
    settings = ReminderSettings()
    assert AttentionReminderPolicy.due_for_trade(trade(), NOW, settings, last_reminded_at=NOW - timedelta(hours=1)) is None
    assert not AttentionReminderPolicy.due_for_daily_digest(NOW.replace(hour=19), settings)
    assert AttentionReminderPolicy.due_for_daily_digest(NOW, settings)
    assert not AttentionReminderPolicy.due_for_daily_digest(NOW, settings, last_sent_at=NOW - timedelta(hours=1))
