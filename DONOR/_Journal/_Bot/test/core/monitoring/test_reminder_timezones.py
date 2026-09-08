from datetime import date, time, timedelta, timezone, datetime

import pytest

from app.core.monitoring import (
    REMINDER_TIMEZONES,
    AttentionReminderPolicy,
    ReminderSettings,
    timezone_display_name,
    validate_timezone_name,
)


MOSCOW = "Europe/Moscow"


def test_moscow_wall_clock_is_not_interpreted_as_utc_wall_clock():
    moscow = ReminderSettings(daily_attention_digest_time=time(3), timezone_name=MOSCOW)
    utc = ReminderSettings(daily_attention_digest_time=time(3), timezone_name="UTC")
    at_0230_utc = datetime(2026, 9, 7, 2, 30, tzinfo=timezone.utc)

    assert AttentionReminderPolicy.due_for_daily_digest(at_0230_utc, moscow)
    assert not AttentionReminderPolicy.due_for_daily_digest(at_0230_utc, utc)


def test_due_check_uses_moscow_local_time_and_utc_mode_still_works():
    moscow = ReminderSettings(daily_attention_digest_time=time(3), timezone_name=MOSCOW)
    utc = ReminderSettings(daily_attention_digest_time=time(3), timezone_name="UTC")
    before_moscow_due = datetime(2026, 9, 7, 23, 59, tzinfo=timezone.utc)
    after_moscow_due = datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc)

    assert not AttentionReminderPolicy.due_for_daily_digest(before_moscow_due, moscow)
    assert AttentionReminderPolicy.due_for_daily_digest(after_moscow_due, moscow)
    assert not AttentionReminderPolicy.due_for_daily_digest(after_moscow_due, utc)
    assert AttentionReminderPolicy.due_for_daily_digest(
        datetime(2026, 9, 7, 3, 0, tzinfo=timezone.utc), utc
    )


def test_invalid_timezone_is_rejected_and_supported_labels_are_user_facing():
    with pytest.raises(ValueError, match="unknown timezone"):
        ReminderSettings(timezone_name="Not/A_Timezone")
    with pytest.raises(ValueError, match="unknown timezone"):
        validate_timezone_name("Not/A_Timezone")

    assert dict(REMINDER_TIMEZONES)["Москва (UTC+3)"] == MOSCOW
    assert timezone_display_name(MOSCOW) == "Москва (UTC+3)"
    assert timezone_display_name("UTC") == "UTC"


def test_delivery_state_is_once_per_moscow_date_and_catch_up_survives_restart():
    settings = ReminderSettings(
        timezone_name=MOSCOW,
        daily_attention_digest_time=time(3),
        last_reminder_local_date=date(2026, 9, 7),
    )
    same_moscow_day_after_restart = datetime(2026, 9, 7, 10, tzinfo=timezone.utc)
    next_moscow_day = datetime(2026, 9, 8, 0, tzinfo=timezone.utc)

    assert not AttentionReminderPolicy.due_for_daily_digest(
        same_moscow_day_after_restart,
        settings,
        last_sent_local_date=settings.last_reminder_local_date,
    )
    assert AttentionReminderPolicy.due_for_daily_digest(
        next_moscow_day,
        settings,
        last_sent_local_date=settings.last_reminder_local_date,
    )


def test_future_and_past_time_changes_follow_current_local_day_once_semantics():
    now = datetime(2026, 9, 7, 1, 30, tzinfo=timezone.utc)  # 04:30 Moscow
    future = ReminderSettings(timezone_name=MOSCOW, daily_attention_digest_time=time(5))
    past = ReminderSettings(timezone_name=MOSCOW, daily_attention_digest_time=time(4))

    assert not AttentionReminderPolicy.due_for_daily_digest(now, future)
    assert AttentionReminderPolicy.due_for_daily_digest(now, past)
