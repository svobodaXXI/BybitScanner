"""
telegram_bot.py

Модуль отправки уведомлений Telegram.

Отвечает только за:
- отправку текстовых сообщений;
- отправку изображений;
- optional inline keyboard markup.

Не содержит:
- анализа сигналов;
- логики Score;
- торговых решений.
"""


import json

import requests


def set_workspace_menu_button(token, chat_id, web_app_url, text="Open Workspace"):
    """Configure one private chat menu button without exposing the token to the frontend."""
    if not web_app_url.startswith("https://"):
        raise ValueError("Telegram Mini App URL must use HTTPS")
    url = f"https://api.telegram.org/bot{token}/setChatMenuButton"
    data = {
        "chat_id": str(chat_id),
        "menu_button": json.dumps({
            "type": "web_app",
            "text": text,
            "web_app": {"url": web_app_url},
        }),
    }
    return requests.post(url, data=data, timeout=10).json()


def send_message(
    token,
    chat_id,
    text,
    reply_markup=None
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

    if reply_markup is not None:
        data["reply_markup"] = json.dumps(
            reply_markup
        )

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
    caption="",
    reply_markup=None
):
    """
    Отправка изображения Telegram.

    Поддерживает optional inline keyboard.
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

        if reply_markup is not None:
            data["reply_markup"] = json.dumps(
                reply_markup
            )

        response = requests.post(
            url,
            files=files,
            data=data,
            timeout=20
        )

    return response.json()
