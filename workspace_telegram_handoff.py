"""Owner-only Telegram Editor handoff when the bot listener runs on Linux VPS.

Never claims to open a Windows PC process from VPS. Only emits a deep link
when authenticated HTTPS ingress is freshly proven; the link conveys view
context only, never trading authority or access secrets.
"""
from __future__ import annotations

import os

import telegram_gateway_client
from workspace_gateway_probe import verify_workspace_gateway
from workspace_ready_link import workspace_link


class WorkspaceHandoffUnavailable(RuntimeError):
    pass


def deliver_workspace_link(chat_id: str, *, mode: str, symbol: str,
                           timeframe: str) -> dict:
    base = os.environ.get("BYBITSCANNER_TERMINAL_HTTPS_URL", "").strip()
    client_id = os.environ.get("BYBITSCANNER_ACCESS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("BYBITSCANNER_ACCESS_CLIENT_SECRET", "").strip()
    owner = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not owner or str(chat_id) != owner:
        raise WorkspaceHandoffUnavailable("owner_mismatch")
    if not base or not client_id or not client_secret:
        raise WorkspaceHandoffUnavailable("protected_terminal_ingress_unconfigured")
    # Validate the complete URL and mode/symbol/timeframe before probing.
    try:
        link = workspace_link(base, mode, symbol, timeframe)
    except ValueError as exc:
        raise WorkspaceHandoffUnavailable("invalid_workspace_link") from exc
    if not verify_workspace_gateway(base, client_id=client_id, client_secret=client_secret):
        raise WorkspaceHandoffUnavailable("protected_terminal_ingress_unverified")
    title = "редактор" if mode == "EDITOR" else "терминал"
    markup = {"inline_keyboard": [[{"text": f"✏️ Открыть {title}" if mode == "EDITOR"
                                      else "🖥 Открыть терминал", "url": link}]]}
    # The Gateway is the existing sole VPS transport. Do not attempt direct
    # Bot API or silently fall back on a failed delivery.
    if not telegram_gateway_client.configured():
        raise WorkspaceHandoffUnavailable("telegram_gateway_unconfigured")
    try:
        result = telegram_gateway_client.send_text(
            owner, f"{symbol} · {timeframe} · {title.capitalize()}\n"
                   "Ссылка открывает соответствующий режим Terminal после входа.",
            reply_markup=markup,
        )
    except telegram_gateway_client.TelegramGatewayError as exc:
        raise WorkspaceHandoffUnavailable("telegram_delivery_unconfirmed") from exc
    if result.get("ok") is not True:
        raise WorkspaceHandoffUnavailable("telegram_delivery_unconfirmed")
    return result
