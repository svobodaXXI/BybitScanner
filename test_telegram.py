"""
test_telegram.py

Диагностический тест Telegram для BybitScanner.

Проверяет:
- доступность Telegram Bot API;
- правильность TELEGRAM_TOKEN;
- правильность TELEGRAM_CHAT_ID;
- отправку текстового сообщения;
- отправку тестового изображения.

Не участвует в работе сканера.
Используется только для диагностики.
"""


import os

from config import (
    TELEGRAM_ENABLED,
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID
)

from telegram_bot import (
    send_message,
    send_photo
)


def main():

    print("=" * 60)
    print("Telegram diagnostic test")
    print("=" * 60)

    print()

    print(
        f"Telegram enabled: {TELEGRAM_ENABLED}"
    )

    print(
        f"Token present: {bool(TELEGRAM_TOKEN)}"
    )

    print(
        f"Chat ID present: {bool(TELEGRAM_CHAT_ID)}"
    )

    print()


    if not TELEGRAM_ENABLED:

        print(
            "Telegram disabled in config.py"
        )

        return


    print("-" * 60)
    print("Sending test message...")
    print("-" * 60)


    try:

        result = send_message(
            TELEGRAM_TOKEN,
            TELEGRAM_CHAT_ID,
            "✅ BybitScanner Telegram connection OK"
        )

        print(
            "Message response:"
        )

        print(result)


    except Exception as e:

        print(
            "Message error:"
        )

        print(e)



    print()

    print("-" * 60)
    print("Sending test photo...")
    print("-" * 60)


    image_file = (
        "BTCUSDT_analysis.png"
    )


    if not os.path.exists(image_file):

        print(
            f"Image not found: {image_file}"
        )

        print(
            "Run scanner first to create analysis image."
        )

        return



    try:

        result = send_photo(
            TELEGRAM_TOKEN,
            TELEGRAM_CHAT_ID,
            image_file,
            "📊 BybitScanner test chart"
        )

        print(
            "Photo response:"
        )

        print(result)


    except Exception as e:

        print(
            "Photo error:"
        )

        print(e)



    print()

    print("=" * 60)
    print("TEST FINISHED")
    print("=" * 60)



if __name__ == "__main__":

    main()