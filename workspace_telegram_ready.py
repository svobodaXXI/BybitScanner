"""Owner-only ready notification for the existing browser workspace.

The caller must prove that the authenticated HTTPS gateway is configured and
the workspace has reached READY before invoking this module. No service starts.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from workspace_ready_link import workspace_link, write_workspace_qr


def send_workspace_ready(*, bot_token, owner_chat_id, https_origin, mode,
                         symbol, timeframe, signal_id=None,
                         ready_verified=False, access_policy_verified=False,
                         send_photo_func=None):
    """Send one QR image and the same navigable HTTPS URL, fail closed otherwise.

    ready_verified must come from an actual frontend readiness/health check.
    access_policy_verified must come from an authenticated gateway check.
    Caller owns these checks; do not substitute a public HTTP 200 or login HTML.
    """
    if not ready_verified or not access_policy_verified:
        raise ValueError("Verified readiness and authenticated HTTPS access required")
    if not bot_token or not str(owner_chat_id).strip():
        raise ValueError("Owner Telegram delivery is not configured")
    if send_photo_func is None:
        from telegram_bot import send_photo as send_photo_func

    url = workspace_link(https_origin, mode, symbol, timeframe, signal_id)
    # This identifier belongs to the owner only: caller must never use group or
    # broadcast chat ids for workspace link delivery.
    title = "Редактор" if mode == "EDITOR" else "Терминал"
    caption = f"✅ {title} готов — {symbol} · {timeframe}\n📱 {url}"
    with TemporaryDirectory(prefix="bybitscanner_workspace_qr_") as tmp:
        qr_path = write_workspace_qr(url, Path(tmp) / "workspace.png")
        result = send_photo_func(bot_token, owner_chat_id, str(qr_path),
                                 caption=caption,
                                 reply_markup={"inline_keyboard": [[
                                     {"text": f"📱 Открыть {title.lower()}", "url": url}
                                 ]]})
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError("Telegram workspace ready notification failed")
    return url
