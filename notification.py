"""
notification.py

Формирование и отправка
торговых уведомлений.

Не содержит:

- анализа;
- расчётов;
- работы с Bybit.

Только:

- принимает результат;
- форматирует сообщение;
- отправляет текст и график в Telegram.
"""

import os

from telegram_bot import (
    send_message,
    send_photo
)

import config


CHARTS_DIR = "charts"


def format_signal(result, test_mode=False):
    """
    Преобразует результат анализа
    в сообщение для Telegram.
    """

    if not result:
        return None

    pattern = result.get(
        "pattern",
        "Unknown"
    )

    direction = (
        result.get("confirmation", {})
        .get("direction", "WAIT")
    )

    score = result.get(
        "final_score",
        result.get("score", 0)
    )

    symbol = result.get(
        "symbol",
        "UNKNOWN"
    )

    confirmed = (
        result.get("confirmation", {})
        .get("confirmed", False)
    )

    status = (
        "✅ CONFIRMED"
        if confirmed
        else
        "⚡ EARLY SIGNAL"
    )

    test_marker = (
        "\n🧪 TEST MODE\n"
        if test_mode
        else ""
    )

    message = f"""
🤖 BybitCleanScanner
{test_marker}
{status}

📌 Symbol:
{symbol}

📐 Pattern:
{pattern}

📈 Direction:
{direction}

⭐ Score:
{score}/100
"""

    return message.strip()


def send_signal(result, test_mode=False):
    """
    Отправляет сигнал в Telegram.

    Если для символа существует сохранённый
    график, он отправляется после текста.
    """

    if not config.TELEGRAM_ENABLED:
        return False

    message = format_signal(
        result,
        test_mode=test_mode
    )

    if not message:
        return False

    send_message(
        config.TELEGRAM_TOKEN,
        config.TELEGRAM_CHAT_ID,
        message
    )

    symbol = result.get(
        "symbol"
    )

    if not symbol:
        return True

    chart_path = os.path.join(
        CHARTS_DIR,
        f"{symbol}_analysis.png"
    )

    if not os.path.exists(chart_path):
        print(
            f"[TELEGRAM] Chart not found: {chart_path}"
        )
        return True

    try:
        response = send_photo(
            config.TELEGRAM_TOKEN,
            config.TELEGRAM_CHAT_ID,
            chart_path
        )

        if not response.get("ok", False):
            print(
                f"[TELEGRAM PHOTO ERROR] {response}"
            )
            return False

        return True

    except Exception as error:
        print(
            f"[TELEGRAM PHOTO ERROR] {error}"
        )
        return False
