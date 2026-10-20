"""Owner-only Telegram delivery of an already verified workspace URL and QR.

The caller must provide a fresh readiness attestation from its authenticated
HTTPS gateway probe. This adapter neither starts processes nor proves readiness.
"""
from pathlib import Path
from telegram_bot import send_photo
from workspace_ready_link import workspace_link, write_workspace_qr


def send_ready_workspace(token: str, owner_chat_id: str, *,
                         base_url: str, mode: str, symbol: str,
                         timeframe: str, signal_id: str | None,
                         gateway_ready: bool, access_policy_verified: bool,
                         qr_directory: Path) -> dict:
    if not gateway_ready or not access_policy_verified:
        raise RuntimeError("Workspace HTTPS or authentication is not verified: no READY message")
    if not token or not owner_chat_id:
        raise ValueError("Owner Telegram identity and bot token are required")
    url = workspace_link(base_url, mode, symbol, timeframe, signal_id)
    qr_path = write_workspace_qr(url, Path(qr_directory) / "workspace-ready.png")
    label = "Редактор" if mode == "EDITOR" else "Терминал"
    markup = {"inline_keyboard": [[{"text": f"📱 Открыть {label.lower()}", "url": url}]]}
    result = send_photo(token, owner_chat_id, qr_path,
                        caption=f"✅ {label} готов — {symbol} · {timeframe}\nQR-код и ссылка открывают тот же сигнал.",
                        reply_markup=markup)
    if result.get("ok") is not True:
        raise RuntimeError("Telegram rejected workspace ready message")
    return result
