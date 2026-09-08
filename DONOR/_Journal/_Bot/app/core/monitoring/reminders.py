"""Pure reminder settings and due-time policy for Attention Center V1."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.trades.enums import TradeStatus
from app.core.trades.readiness import TradeReadiness, TradeReadinessStatus, evaluate_trade_readiness
from app.core.accounts.account_id import AccountId


class ReminderKind(StrEnum):
    INCOMPLETE_TRADE = "INCOMPLETE_TRADE"
    OPEN_TRADE = "OPEN_TRADE"
    DAILY_DIGEST = "DAILY_DIGEST"


# V1 deliberately exposes a small, reviewed list instead of accepting
# arbitrary user input. Values are persisted as canonical IANA identifiers.
REMINDER_TIMEZONES: tuple[tuple[str, str], ...] = (
    ("Москва (UTC+3)", "Europe/Moscow"),
    ("UTC", "UTC"),
)


@dataclass(frozen=True, slots=True)
class ReminderSettings:
    account_id: AccountId | None = field(default=None, kw_only=True)
    incomplete_reminder_delay: timedelta = timedelta(hours=1)
    open_trade_reminder_threshold: timedelta = timedelta(hours=24)
    daily_attention_digest_enabled: bool = True
    daily_attention_digest_time: time = time(20, 0)
    timezone_name: str = "UTC"
    last_reminder_local_date: date | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if self.account_id is not None and not isinstance(self.account_id, AccountId):
            object.__setattr__(self, "account_id", AccountId(self.account_id))
        for value, name in (
            (self.incomplete_reminder_delay, "incomplete_reminder_delay"),
            (self.open_trade_reminder_threshold, "open_trade_reminder_threshold"),
        ):
            if not isinstance(value, timedelta) or value < timedelta(0):
                raise ValueError(f"{name} must be a non-negative timedelta")
        if type(self.daily_attention_digest_enabled) is not bool:
            raise TypeError("daily_attention_digest_enabled must be bool")
        if not isinstance(self.daily_attention_digest_time, time):
            raise TypeError("daily_attention_digest_time must be time")
        validate_timezone_name(self.timezone_name)
        if self.last_reminder_local_date is not None and not isinstance(self.last_reminder_local_date, date):
            raise TypeError("last_reminder_local_date must be date or None")


class AttentionReminderPolicy:
    """Decide whether one notification is due; it never sends messages."""

    @staticmethod
    def due_for_trade(
        trade,
        now: datetime,
        settings: ReminderSettings,
        *,
        readiness: TradeReadiness | None = None,
        last_reminded_at: datetime | None = None,
    ) -> ReminderKind | None:
        if not isinstance(settings, ReminderSettings):
            raise TypeError("settings must be ReminderSettings")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if last_reminded_at is not None and now - last_reminded_at < AttentionReminderPolicy._threshold(trade, settings):
            return None
        readiness = readiness or evaluate_trade_readiness(trade)
        if readiness.status is TradeReadinessStatus.OPEN:
            age = now.astimezone(timezone.utc) - trade.opened_at.astimezone(timezone.utc)
            return ReminderKind.OPEN_TRADE if age >= settings.open_trade_reminder_threshold else None
        if readiness.status is TradeReadinessStatus.INCOMPLETE:
            closed_at = getattr(trade, "closed_at", None)
            if closed_at is None:
                return None
            age = now.astimezone(timezone.utc) - closed_at.astimezone(timezone.utc)
            return ReminderKind.INCOMPLETE_TRADE if age >= settings.incomplete_reminder_delay else None
        return None

    @staticmethod
    def due_for_daily_digest(
        now: datetime,
        settings: ReminderSettings,
        *,
        last_sent_at: datetime | None = None,
        last_sent_local_date: date | None = None,
    ) -> bool:
        if not settings.daily_attention_digest_enabled:
            return False
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        local = now.astimezone(_zone(settings.timezone_name))
        if local.time() < settings.daily_attention_digest_time:
            return False
        if last_sent_local_date is not None and last_sent_local_date >= local.date():
            return False
        if last_sent_at is not None and last_sent_at.astimezone(_zone(settings.timezone_name)).date() >= local.date():
            return False
        return True

    @staticmethod
    def _threshold(trade, settings):
        return settings.open_trade_reminder_threshold if trade.status is TradeStatus.OPEN else settings.incomplete_reminder_delay


def validate_timezone_name(name: str) -> str:
    """Validate and return a canonical IANA timezone identifier."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("timezone_name must not be empty")
    try:
        ZoneInfo(name)
    except (TypeError, ZoneInfoNotFoundError) as error:
        raise ValueError(f"unknown timezone: {name!r}") from error
    return name


def _zone(name: str):
    return ZoneInfo(validate_timezone_name(name))


def timezone_display_name(name: str) -> str:
    """Return a user-facing label for a supported V1 zone."""
    validate_timezone_name(name)
    for label, identifier in REMINDER_TIMEZONES:
        if identifier == name:
            return label
    # Keep other already-valid persisted IANA zones usable without exposing
    # them in the deliberately small V1 selection menu.
    return name
