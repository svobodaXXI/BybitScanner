"""
telegram_formatter.py

Формирование сообщений Telegram.

Отвечает только за внешний вид уведомлений.

Не содержит:
- анализа сигналов;
- работы с API;
- отправки сообщений.
"""

from notification_manager import build_event_title


def format_signal_message(signal, event):
    """
    Формирует текст уведомления Telegram.
    """

    title = build_event_title(event)

    symbol = signal.get(
        "symbol",
        "UNKNOWN"
    )

    pattern = signal.get(
        "pattern",
        "UNKNOWN"
    )

    direction = signal.get(
        "direction",
        "WAIT"
    )

    score = signal.get(
        "score",
        0
    )

    geometry = signal.get(
        "geometry",
        {}
    )

    compression = (
        geometry.get(
            "compression",
            {}
        ).get(
            "compression_percent",
            0
        )
    )

    touches = (
        geometry.get(
            "touches",
            {}
        ).get(
            "total_touches",
            0
        )
    )

    tradingview = (
        signal.get(
            "tradingview",
            {}
        ).get(
            "url"
        )
    )

    message = f"""
{title}

📌 Symbol:
{symbol}

📐 Pattern:
{pattern}

📈 Direction:
{direction}

⭐ Score:
{score}/100

📉 Compression:
{compression:.1f}%

🎯 Touches:
{touches}
""".strip()

    if tradingview:

        message += f"""

🔗 TradingView:
{tradingview}
"""

    return message