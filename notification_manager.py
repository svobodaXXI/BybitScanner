"""
notification_manager.py

Определение событий уведомлений.

Отвечает только за определение того,
что произошло с сигналом.

Не занимается:
- отправкой Telegram;
- форматированием сообщений;
- сохранением сигналов.
"""

from signal_memory import get_signal


EVENT_NEW = "NEW"
EVENT_STRENGTHENING = "STRENGTHENING"
EVENT_WEAKENING = "WEAKENING"
EVENT_CONFIRMED = "CONFIRMED"
EVENT_LOST = "LOST"
EVENT_STABLE = "STABLE"


def analyze_notification(signal):
    """
    Анализирует изменение сигнала.

    Возвращает словарь:

    {
        "event": "...",
        "old_score": ...,
        "new_score": ...,
        "difference": ...
    }
    """

    previous = get_signal(
        signal["symbol"]
    )

    current_score = signal.get(
        "score",
        0
    )

    if previous is None:

        return {

            "event": EVENT_NEW,

            "old_score": 0,

            "new_score": current_score,

            "difference": current_score

        }

    previous_score = previous.get(
        "current_score",
        0
    )

    difference = (
        current_score -
        previous_score
    )

    if difference >= 5:

        event = EVENT_STRENGTHENING

    elif difference <= -5:

        event = EVENT_WEAKENING

    else:

        event = EVENT_STABLE

    return {

        "event": event,

        "old_score": previous_score,

        "new_score": current_score,

        "difference": difference

    }


def should_notify(event):
    """
    Нужно ли отправлять уведомление.
    """

    return event in {

        EVENT_NEW,

        EVENT_STRENGTHENING,

        EVENT_WEAKENING,

        EVENT_CONFIRMED,

        EVENT_LOST

    }


def build_event_title(event):
    """
    Заголовок события.
    """

    titles = {

        EVENT_NEW:
            "🚨 NEW SIGNAL",

        EVENT_STRENGTHENING:
            "📈 SIGNAL IMPROVED",

        EVENT_WEAKENING:
            "⚠ SIGNAL WEAKENING",

        EVENT_CONFIRMED:
            "🔥 BREAKOUT CONFIRMED",

        EVENT_LOST:
            "❌ SIGNAL LOST",

        EVENT_STABLE:
            "📊 SIGNAL UPDATE"

    }

    return titles.get(
        event,
        "📊 SIGNAL UPDATE"
    )