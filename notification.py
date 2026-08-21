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


def get_telegram_chat_ids():
    """Return configured Telegram recipients in stable, deduplicated order."""

    configured = getattr(
        config,
        "TELEGRAM_CHAT_IDS",
        None
    )

    if isinstance(configured, (str, int)):
        configured = (configured,)

    recipients = []
    seen = set()

    for value in configured or ():
        if value is None:
            continue

        chat_id = str(value).strip()

        if not chat_id or chat_id in seen:
            continue

        seen.add(chat_id)
        recipients.append(chat_id)

    if recipients:
        return tuple(recipients)

    legacy_chat_id = str(
        getattr(config, "TELEGRAM_CHAT_ID", "")
    ).strip()

    if legacy_chat_id:
        return (legacy_chat_id,)

    return ()


def _telegram_delivery_ok(response):
    return bool(
        isinstance(response, dict)
        and response.get("ok", False)
    )


def send_message_to_recipients(text, reply_markup=None):
    """Send one message to every configured recipient without fail-fast."""

    recipients = get_telegram_chat_ids()

    if not recipients:
        print("[TELEGRAM ERROR] No recipients configured")
        return False

    all_delivered = True

    for chat_id in recipients:
        try:
            response = send_message(
                config.TELEGRAM_TOKEN,
                chat_id,
                text,
                reply_markup=reply_markup
            )

            if not _telegram_delivery_ok(response):
                all_delivered = False
                print(
                    f"[TELEGRAM MESSAGE ERROR] "
                    f"chat_id={chat_id} response={response}"
                )

        except Exception as error:
            all_delivered = False
            print(
                f"[TELEGRAM MESSAGE ERROR] "
                f"chat_id={chat_id} error={error}"
            )

    return all_delivered


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

    all_delivered = send_message_to_recipients(
        message
    )

    symbol = result.get(
        "symbol"
    )

    if not symbol:
        return all_delivered

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
        return all_delivered

    reply_markup = (
        build_tradingview_keyboard(
            symbol,
            timeframe
        )
    )

    for chat_id in get_telegram_chat_ids():
        try:
            response = send_photo(
                config.TELEGRAM_TOKEN,
                chat_id,
                chart_path,
                reply_markup=reply_markup
            )

            if not _telegram_delivery_ok(response):
                all_delivered = False
                print(
                    f"[TELEGRAM PHOTO ERROR] "
                    f"chat_id={chat_id} response={response}"
                )

        except Exception as error:
            all_delivered = False
            print(
                f"[TELEGRAM PHOTO ERROR] "
                f"chat_id={chat_id} error={error}"
            )

    return all_delivered
