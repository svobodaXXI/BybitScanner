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
- отправляет текст и график в Telegram;
- добавляет ссылку TradingView.
"""

import os

from telegram_bot import (
    send_message,
    send_photo
)

from tradingview_bridge import (
    create_tradingview_url
)

import config


CHARTS_DIR = "charts"


def format_signal(
    result,
    test_mode=False
):
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
        result.get(
            "confirmation",
            {}
        )
        .get(
            "direction",
            "WAIT"
        )
    )

    score = result.get(
        "final_score",
        result.get(
            "score",
            0
        )
    )

    symbol = result.get(
        "symbol",
        "UNKNOWN"
    )

    confirmed = (
        result.get(
            "confirmation",
            {}
        )
        .get(
            "confirmed",
            False
        )
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


def build_tradingview_keyboard(
    symbol,
    timeframe
):
    """
    Telegram inline keyboard:
    TradingView + Review Queue.
    """

    tradingview_url = (
        create_tradingview_url(
            symbol,
            timeframe
        )
    )

    symbol = str(symbol)
    timeframe = str(timeframe)

    return {
        "inline_keyboard": [
            [
                {
                    "text":
                        "\U0001F4C8 Open TradingView",

                    "url":
                        tradingview_url
                }
            ],
            [
                {
                    "text":
                        "\U0001F4CC \u0412 \u0440\u0430\u0437\u0431\u043e\u0440",

                    "callback_data":
                        f"review:queue:{symbol}:{timeframe}"
                },
                {
                    "text":
                        "\u2705 \u0425\u043e\u0440\u043e\u0448\u0438\u0439",

                    "callback_data":
                        f"review:good:{symbol}:{timeframe}"
                }
            ],
            [
                {
                    "text":
                        "\u274C \u0413\u0435\u043e\u043c\u0435\u0442\u0440\u0438\u044f",

                    "callback_data":
                        f"review:geometry:{symbol}:{timeframe}"
                },
                {
                    "text":
                        "\u2693 Anchor/START",

                    "callback_data":
                        f"review:anchor:{symbol}:{timeframe}"
                }
            ]
        ]
    }


def send_signal(
    result,
    test_mode=False
):
    """
    Отправляет сигнал в Telegram.

    Если для символа существует сохранённый
    график, он отправляется после текста.

    Под графиком добавляется кнопка
    открытия текущего символа в TradingView.
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

    timeframe = str(
        result.get(
            "timeframe",
            getattr(
                config,
                "TIMEFRAME",
                "5"
            )
        )
    )

    chart_path = os.path.join(
        CHARTS_DIR,
        f"{symbol}_analysis.png"
    )

    if not os.path.exists(
        chart_path
    ):
        print(
            f"[TELEGRAM] Chart not found: "
            f"{chart_path}"
        )
        return True

    reply_markup = (
        build_tradingview_keyboard(
            symbol,
            timeframe
        )
    )

    try:

        response = send_photo(
            config.TELEGRAM_TOKEN,
            config.TELEGRAM_CHAT_ID,
            chart_path,
            reply_markup=reply_markup
        )

        if not response.get(
            "ok",
            False
        ):
            print(
                f"[TELEGRAM PHOTO ERROR] "
                f"{response}"
            )
            return False

        return True

    except Exception as error:

        print(
            f"[TELEGRAM PHOTO ERROR] "
            f"{error}"
        )

        return False