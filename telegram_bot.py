"""
telegram_bot.py

Модуль отправки уведомлений Telegram.

Отвечает только за:
- отправку текстовых сообщений;
- отправку изображений.

Не содержит:
- анализа сигналов;
- логики Score;
- торговых решений.
"""


import requests


def send_message(
    token,
    chat_id,
    text
):
    """
    Отправка текстового сообщения Telegram.
    """

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    data = {
        "chat_id": chat_id,
        "text": text
    }

    response = requests.post(
        url,
        data=data,
        timeout=10
    )

    return response.json()



def send_photo(
    token,
    chat_id,
    photo_path,
    caption=""
):
    """
    Отправка изображения Telegram.
    """

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendPhoto"
    )

    with open(
        photo_path,
        "rb"
    ) as photo:

        files = {
            "photo": photo
        }

        data = {
            "chat_id": chat_id,
            "caption": caption
        }

        response = requests.post(
            url,
            files=files,
            data=data,
            timeout=20
        )

    return response.json()