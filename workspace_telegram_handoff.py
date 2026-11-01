"""Owner-only Telegram Editor handoff when the bot listener runs on Linux VPS.

Never claims to open a Windows PC process from VPS. Only emits a deep link
when authenticated HTTPS ingress is freshly proven; the link conveys view
context only, never trading authority or access secrets.
"""
from __future__ import annotations

import os

import telegram_gateway_client
from urllib.parse import urlsplit, urlunsplit

import requests
from workspace_ready_link import workspace_link


class WorkspaceHandoffUnavailable(RuntimeError):
    pass


def deliver_workspace_link(chat_id: str, *, mode: str, symbol: str,
                           timeframe: str) -> dict:
    # Use the same approved Mini App address as the Telegram /terminal button.
    # Keep the explicit HTTPS-origin override for existing installations.
    base = os.environ.get("BYBITSCANNER_TERMINAL_HTTPS_URL", "").strip()
    if not base:
        base = os.environ.get("BYBITSCANNER_WORKSPACE_URL", "").strip()
    owner = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not owner or str(chat_id) != owner:
        raise WorkspaceHandoffUnavailable("owner_mismatch")
    if not base:
        raise WorkspaceHandoffUnavailable("protected_terminal_ingress_unconfigured")
    # Validate the complete URL and mode/symbol/timeframe before probing.
    try:
        parts = urlsplit(base)
        if parts.path not in ("", "/", "/login") or parts.query or parts.fragment:
            raise ValueError("Expected a protected HTTPS origin or /login path without parameters")
        link = workspace_link(urlunsplit((parts.scheme, parts.netloc, "/login", "", "")), mode, symbol, timeframe)
    except ValueError as exc:
        raise WorkspaceHandoffUnavailable("invalid_workspace_link") from exc
    # Direct HTTPS ingress from #687: real TLS and anonymous read denial.
    try:
        origin = f"{parts.scheme}://{parts.netloc}"
        login = requests.get(origin + "/login", timeout=5, allow_redirects=False)
        private = requests.get(origin + "/", timeout=5, allow_redirects=False)
        if login.status_code != 200 or private.status_code not in (401, 403):
            raise WorkspaceHandoffUnavailable("protected_terminal_ingress_unverified")
    except requests.RequestException as exc:
        raise WorkspaceHandoffUnavailable("protected_terminal_ingress_unverified") from exc
    title = "редактор" if mode == "EDITOR" else "терминал"
    markup = {"inline_keyboard": [[{"text": f"✏️ Открыть {title}" if mode == "EDITOR"
                                      else "🖥 Открыть терминал", "web_app": {"url": link}}]]}
    # The Gateway is the existing sole VPS transport. Do not attempt direct
    # Bot API or silently fall back on a failed delivery.
    if not telegram_gateway_client.configured():
        raise WorkspaceHandoffUnavailable("telegram_gateway_unconfigured")
    try:
        result = telegram_gateway_client.send_text(
            owner, f"{symbol} · {timeframe} · {title.capitalize()}\n"
                   "Открыть защищённый Terminal через Telegram.",
            reply_markup=markup,
        )
    except telegram_gateway_client.TelegramGatewayError as exc:
        raise WorkspaceHandoffUnavailable("telegram_delivery_unconfirmed") from exc
    if result.get("ok") is not True:
        raise WorkspaceHandoffUnavailable("telegram_delivery_unconfirmed")
    return result
