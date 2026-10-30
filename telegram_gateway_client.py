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
    if reply_markup is not None and not isinstance(reply_markup, dict):
        raise TelegramGatewayError("Invalid Gateway keyboard")
    event_id = secrets.token_urlsafe(24)
    last_error = None
    for attempt in range(2):
        try:
            session = requests.Session()
            session.trust_env = False
            response = session.post(
                url.rstrip("/") if parsed.path.rstrip("/") == "/v1/send" else url.rstrip("/") + "/v1/send",
                json={"event_id": event_id, "text": text, **({"reply_markup": reply_markup} if reply_markup is not None else {})},
                headers={"Authorization": "Bearer " + key},
                timeout=12, allow_redirects=False,
            )
            result = response.json()
            if (isinstance(result, dict) and response.status_code == 200 and
                    result.get("ok") is True and result.get("event_id") == event_id and
                    result.get("stage") == "accepted_by_telegram_api"):
                return {"ok": True, "result": {"message_id": result.get("telegram_message_id")},
                        "delivery_stage": "accepted_by_telegram_api"}
            last_error = "gateway_rejected"
            # Never retry a definite validation/authentication failure.
            if response.status_code < 500:
                break
        except (requests.RequestException, ValueError):
            last_error = "transport_unavailable"
    raise TelegramGatewayError("Gateway delivery not confirmed: " + str(last_error))

def get_updates(**params):
    """Relay polling through Gateway; VPS remains sole update consumer."""
    url = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_URL", "").strip()
    key = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_SECRET", "").strip()
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or
            parsed.password or parsed.query or parsed.fragment or
            parsed.path.rstrip("/") not in ("", "/v1/send") or len(key) < 32):
        raise TelegramGatewayError("invalid Gateway polling configuration")
    allowed = {"offset", "timeout", "allowed_updates"}
    if set(params) - allowed:
        raise TelegramGatewayError("unsupported Gateway polling parameters")
    if "allowed_updates" in params and isinstance(params["allowed_updates"], str):
        import json
        params["allowed_updates"] = json.loads(params["allowed_updates"])
    endpoint = url.rstrip("/")
    if endpoint.endswith("/v1/send"):
        endpoint = endpoint[:-len("/v1/send")]
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.post(endpoint + "/v1/get-updates", json=params,
                                headers={"Authorization": "Bearer " + key},
                                timeout=42, allow_redirects=False)
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise TelegramGatewayError("Gateway poll unavailable") from exc
    if response.status_code != 200 or not isinstance(result, dict):
        raise TelegramGatewayError("Gateway poll rejected")
    return result

def bot_method(method, **params):
    """Pass only monitoring menu/callback methods via authorized Gateway."""
    permitted = {"answerCallbackQuery", "setMyCommands",
                 "getChatMenuButton", "setChatMenuButton"}
    if method not in permitted:
        raise TelegramGatewayError("unsupported Gateway method")
    url = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_URL", "").strip()
    key = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_SECRET", "").strip()
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or
            parsed.password or parsed.query or parsed.fragment or
            parsed.path.rstrip("/") not in ("", "/v1/send") or len(key) < 32):
        raise TelegramGatewayError("invalid Gateway method configuration")
    endpoint = url.rstrip("/")
    if endpoint.endswith("/v1/send"):
        endpoint = endpoint[:-len("/v1/send")]
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.post(endpoint + "/v1/bot-method",
                                json={"method": method, "params": params},
                                headers={"Authorization": "Bearer " + key},
                                timeout=15, allow_redirects=False)
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise TelegramGatewayError("Gateway method unavailable") from exc
    if response.status_code != 200 or not isinstance(result, dict):
        raise TelegramGatewayError("Gateway method rejected")
    return result

def send_photo_file_id(chat_id, file_id, caption="", reply_markup=None):
    """Relay an already-uploaded Telegram image; no direct fallback."""
    if reply_markup is not None and not isinstance(reply_markup, dict):
        raise TelegramGatewayError("invalid photo keyboard")
    if not isinstance(file_id, str) or not file_id or len(file_id) > 1024:
        raise TelegramGatewayError("invalid photo file ID")
    if not isinstance(caption, str) or len(caption) > 1024:
        raise TelegramGatewayError("invalid photo caption")
    owner = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not owner or str(chat_id) != owner:
        raise TelegramGatewayError("Gateway photo recipient mismatch")
    url = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_URL", "").strip()
    secret = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_SECRET", "").strip()
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or
            parsed.password or parsed.query or parsed.fragment or
            parsed.path.rstrip("/") not in ("", "/v1/send") or len(secret) < 32):
        raise TelegramGatewayError("invalid Gateway photo configuration")
    endpoint = url.rstrip("/")
    if endpoint.endswith("/v1/send"):
        endpoint = endpoint[:-len("/v1/send")]
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            endpoint + "/v1/photo-file-id",
            json={"file_id": file_id, "caption": caption},
            headers={"Authorization": "Bearer " + secret},
            timeout=20, allow_redirects=False,
        )
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise TelegramGatewayError("Gateway photo transport unavailable") from exc
    if response.status_code != 200 or not isinstance(result, dict) or result.get("ok") is not True:
        raise TelegramGatewayError("Gateway photo rejected")
    if reply_markup is not None:
        try:
            menu = send_text(chat_id, "📎 Действия к графику выше", reply_markup=reply_markup)
        except TelegramGatewayError as exc:
            print(f"[TELEGRAM GATEWAY PHOTO MENU ERROR] {type(exc).__name__}: {exc}", flush=True)
            return {**result, "keyboard_delivered": False}
        return {**result, "keyboard_delivered": bool(menu.get("ok"))}
    return result

def send_photo_upload(chat_id, photo_path, caption="", reply_markup=None):
    """Upload a bounded PNG/JPEG through the fixed-owner Gateway."""
    from pathlib import Path
    if reply_markup is not None and not isinstance(reply_markup, dict):
        raise TelegramGatewayError("invalid photo keyboard")
    if str(chat_id) != os.getenv("TELEGRAM_CHAT_ID", "").strip():
        raise TelegramGatewayError("Gateway photo recipient mismatch")
    path = Path(photo_path)
    suffix = path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise TelegramGatewayError("unsupported image format")
    if not isinstance(caption, str) or len(caption) > 1024:
        raise TelegramGatewayError("invalid caption")
    url = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_URL", "").strip()
    key = os.getenv("BYBITSCANNER_TELEGRAM_GATEWAY_SECRET", "").strip()
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or
            parsed.password or parsed.query or parsed.fragment or
            parsed.path.rstrip("/") not in ("", "/v1/send") or len(key) < 32):
        raise TelegramGatewayError("invalid Gateway configuration")
    endpoint = url.rstrip("/")
    if endpoint.endswith("/v1/send"):
        endpoint = endpoint[:-len("/v1/send")]
    try:
        if path.stat().st_size > 2000000:
            raise TelegramGatewayError("photo too large for Gateway")
        photo = path.read_bytes()
        if not photo or len(photo) > 2000000:
            raise TelegramGatewayError("invalid photo size")
        media_type = "image/png" if suffix == ".png" else "image/jpeg"
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            endpoint + "/v1/photo-upload",
            data=photo,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": media_type,
                     "X-Telegram-Caption": caption},
            timeout=25, allow_redirects=False,
        )
        result = response.json()
    except (OSError, requests.RequestException, ValueError) as exc:
        raise TelegramGatewayError("Gateway photo upload unavailable") from exc
    if response.status_code != 200 or not isinstance(result, dict) or result.get("ok") is not True:
        raise TelegramGatewayError("Gateway photo upload rejected")
    if reply_markup is not None:
        # The deployed Gateway photo endpoint does not accept inline keyboards.
        # Send a *separate owner menu* through the supported text route only
        # after a confirmed photo upload; never silently drop the image.
        # This is an explicit compatibility mode until photo markup is supported
        # server-side. No direct Telegram fallback or invented message IDs.
        try:
            menu = send_text(chat_id, "📎 Действия к графику выше", reply_markup=reply_markup)
        except TelegramGatewayError as exc:
            # Do not trigger automatic photo retry after an accepted image:
            # reupload would create duplicate chart messages.
            print(f"[TELEGRAM GATEWAY PHOTO MENU ERROR] {type(exc).__name__}: {exc}", flush=True)
            return {**result, "keyboard_delivered": False}
        return {**result, "keyboard_delivered": bool(menu.get("ok"))}
    return result
