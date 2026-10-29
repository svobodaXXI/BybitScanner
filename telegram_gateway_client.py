"""Opt-in Telegram send-only Gateway client; never silently falls back to direct Bot API."""
from __future__ import annotations

import os
import secrets
from urllib.parse import urlsplit

import requests


class TelegramGatewayError(RuntimeError):
    """Gateway transport unavailable or rejected; no automatic duplicate send."""


def configured() -> bool:
    return bool(os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_URL", "").strip())


def send_text(chat_id, text, *, reply_markup=None):
    """Preserve Telegram send_message response shape for plain text only.

    Gateway has a fixed authorized destination; interactive keyboards and photos
    are deliberately unsupported until their complete transport contract exists.
    """
    url = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_URL", "").strip()
    key = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_SECRET", "").strip()
    owner = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or
            parsed.password or parsed.query or parsed.fragment or
            parsed.path.rstrip("/") not in ("", "/v1/send")):
        raise TelegramGatewayError("invalid Gateway HTTPS URL")
    if len(key) < 32 or not owner or str(chat_id) != owner:
        raise TelegramGatewayError("Gateway owner/configuration mismatch")
    if reply_markup is not None:
        raise TelegramGatewayError("Gateway keyboard transport not implemented")
    event_id = secrets.token_urlsafe(24)
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            url.rstrip("/") if parsed.path.rstrip("/") == "/v1/send" else url.rstrip("/") + "/v1/send",
            json={"event_id": event_id, "text": text},
            headers={"Authorization": "Bearer " + key},
            timeout=12,
            allow_redirects=False,
        )
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise TelegramGatewayError("Gateway transport failed; delivery unknown") from exc
    if not isinstance(result, dict) or response.status_code != 200 or result.get("ok") is not True:
        raise TelegramGatewayError("Gateway rejected message; delivery unknown")
    if result.get("event_id") != event_id or result.get("stage") != "accepted_by_telegram_api":
        raise TelegramGatewayError("Gateway acknowledgement invalid")
    return {"ok": True, "result": {"message_id": result.get("telegram_message_id")},
            "delivery_stage": "accepted_by_telegram_api"}
