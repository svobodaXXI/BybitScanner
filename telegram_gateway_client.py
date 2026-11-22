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


def _send_outbound(post):
    """Bounded notice retry, sanitized classification, no trading side effects."""
    import time

    for attempt in range(2):
        try:
            response = post()
        except requests.RequestException as exc:
            if attempt == 0:
                time.sleep(0.25)
                continue
            raise TelegramGatewayError(
                "Gateway delivery not confirmed: class=TRANSIENT_TRANSPORT, "
                "status=unavailable, exception=" + type(exc).__name__
            ) from None

        status = response.status_code
        if status == 200:
            return response
        if status in (401, 403):
            code = "PERMANENT_AUTH"
        elif status in (400, 404, 405, 413, 422):
            code = "PERMANENT_CONFIG"
        elif status == 429:
            code = "RATE_LIMIT"
            value = response.headers.get("Retry-After") if hasattr(response.headers, "get") else None
            delay = int(value) if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 4 else None
            if attempt == 0 and delay is not None and delay <= 2:
                time.sleep(delay)
                continue
        elif isinstance(status, int) and status >= 500:
            code = "TRANSIENT_HTTP"
            if attempt == 0:
                time.sleep(0.25)
                continue
        else:
            code = "PERMANENT_REJECTION"
        raise TelegramGatewayError(
            f"Gateway delivery not confirmed: class={code}, status={status}"
            + (f", retry_after={delay}s" if code == "RATE_LIMIT" and delay is not None else "")
        )
    raise TelegramGatewayError("Gateway delivery not confirmed: class=UNKNOWN_DELIVERY")


def _gateway_json(response):
    try:
        value = response.json()
    except ValueError:
        value = None
    if not isinstance(value, dict):
        raise TelegramGatewayError(
            "Gateway delivery not confirmed: class=UNKNOWN_DELIVERY, status=200"
        )
    return value


def send_text(chat_id, text, *, reply_markup=None, retry=True):
    """Preserve the Telegram response shape; no direct fallback."""
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
    endpoint = url.rstrip("/") if parsed.path.rstrip("/") == "/v1/send" else url.rstrip("/") + "/v1/send"

    def post():
        session = requests.Session()
        session.trust_env = False
        return session.post(
            endpoint,
            json={"event_id": event_id, "text": text,
                  **({"reply_markup": reply_markup} if reply_markup is not None else {})},
            headers={"Authorization": "Bearer " + key},
            timeout=12, allow_redirects=False,
        )

    # Owner-release approval prompts must never be duplicated after an
    # ambiguous network response. Ordinary monitoring notices retain retry.
    response = _send_outbound(post) if retry else post()
    if response.status_code != 200:
        raise TelegramGatewayError("Gateway text outcome unproven")
    result = _gateway_json(response)
    if (result.get("ok") is not True or result.get("event_id") != event_id
            or result.get("stage") != "accepted_by_telegram_api"):
        raise TelegramGatewayError(
            "Gateway delivery not confirmed: class=UNKNOWN_DELIVERY, status=200"
        )
    return {"ok": True, "result": {"message_id": result.get("telegram_message_id")},
            "delivery_stage": "accepted_by_telegram_api"}

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
    except requests.RequestException as exc:
        raise TelegramGatewayError(
            "Gateway poll unavailable: exception=" + type(exc).__name__ +
            ", status=unavailable, content_type=unavailable"
        ) from exc
    content_type = str(response.headers.get("content-type", "")).split(";", 1)[0].strip().lower()
    if not content_type:
        content_type = "missing"
    elif (len(content_type) > 127 or
          not all(char.isascii() and (char.isalnum() or char in "/.+-_")
                  for char in content_type)):
        content_type = "invalid"
    try:
        result = response.json()
    except ValueError as exc:
        raise TelegramGatewayError(
            "Gateway poll unavailable: exception=" + type(exc).__name__ +
            f", status={response.status_code}, content_type={content_type}"
        ) from exc
    if response.status_code != 200 or not isinstance(result, dict):
        raise TelegramGatewayError(
            "Gateway poll rejected: exception=none, " +
            f"status={response.status_code}, content_type={content_type}"
        )
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
    """Send an archived photo and keyboard in one Telegram message."""
    if reply_markup is not None and not isinstance(reply_markup, dict):
        raise TelegramGatewayError("invalid photo keyboard")
    if not isinstance(file_id, str) or not file_id or len(file_id) > 1024:
        raise TelegramGatewayError("invalid photo file ID")
    if not isinstance(caption, str) or len(caption) > 1024:
        raise TelegramGatewayError("invalid photo caption")
    if str(chat_id) != os.getenv("TELEGRAM_CHAT_ID", "").strip():
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
    def post():
        session = requests.Session()
        session.trust_env = False
        return session.post(
            endpoint + "/v1/photo-card",
            json={"file_id": file_id, "caption": caption,
                  **({"reply_markup": reply_markup} if reply_markup is not None else {})},
            headers={"Authorization": "Bearer " + secret},
            timeout=25, allow_redirects=False,
        )

    result = _gateway_json(_send_outbound(post))
    if result.get("ok") is not True:
        raise TelegramGatewayError(
            "Gateway delivery not confirmed: class=UNKNOWN_DELIVERY, status=200"
        )
    return result


def send_photo_upload(chat_id, photo_path, caption="", reply_markup=None):
    """Upload PNG/JPEG with its UTF-8 caption and keyboard as ONE Telegram card.

    Requires the v2 photo-card endpoint deployed through the Cloudflare
    allowlist and the Gateway origin before the VPS client is updated.
    A failed request never falls back to text-only or to a second photo send.
    """
    from pathlib import Path
    import json
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
    except OSError:
        raise TelegramGatewayError("Gateway photo: class=CHART_NOT_READY") from None
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    data = {"caption": caption,
            **({"reply_markup": json.dumps(reply_markup, ensure_ascii=False)}
               if reply_markup is not None else {})}

    def post():
        session = requests.Session()
        session.trust_env = False
        return session.post(
            endpoint + "/v1/photo-card",
            files={"photo": ("chart.png", photo, media_type)},
            data=data,
            headers={"Authorization": "Bearer " + key},
            timeout=25, allow_redirects=False,
        )

    result = _gateway_json(_send_outbound(post))
    if result.get("ok") is not True:
        raise TelegramGatewayError(
            "Gateway delivery not confirmed: class=UNKNOWN_DELIVERY, status=200"
        )
    return result
