"""Owner-only Telegram delivery of an already verified workspace URL and QR.

The caller must provide a fresh readiness attestation from its authenticated
HTTPS gateway probe. This adapter neither starts processes nor proves readiness.
"""
from pathlib import Path
import uuid
from telegram_bot import send_photo
from workspace_ready_link import workspace_link, write_workspace_qr
from workspace_gateway_probe import verify_workspace_gateway


def send_ready_workspace(token: str, owner_chat_id: str, *,
                         base_url: str, mode: str, symbol: str,
                         timeframe: str, signal_id: str | None,
                         gateway_ready: bool, access_policy_verified: bool,
                         qr_directory: Path) -> dict:
    if gateway_ready is not True or access_policy_verified is not True:
        raise RuntimeError("Workspace HTTPS or authentication is not verified: no READY message")
    if not token or not owner_chat_id:
        raise ValueError("Owner Telegram identity and bot token are required")
    url = workspace_link(base_url, mode, symbol, timeframe, signal_id)
    qr_path = write_workspace_qr(url, Path(qr_directory) / f"workspace-{uuid.uuid4().hex}.png")
    label = "Редактор" if mode == "EDITOR" else "Терминал"
    markup = {"inline_keyboard": [[{"text": f"📱 Открыть {label.lower()}", "url": url}]]}
    result = send_photo(token, owner_chat_id, qr_path,
                        caption=f"✅ {label} готов — {symbol} · {timeframe}\nQR-код и ссылка открывают тот же сигнал.",
                        reply_markup=markup)
    # A transport-level `ok` without Telegram's durable message receipt
    # does not prove that the owner received a QR. Never report READY on an
    # ambiguous Gateway response (same contract as other Telegram cards).
    receipt = result.get("result") if isinstance(result, dict) else None
    message_id = receipt.get("message_id") if isinstance(receipt, dict) else None
    if (not isinstance(result, dict) or result.get("ok") is not True
            or type(message_id) is not int or message_id <= 0):
        raise RuntimeError("Telegram QR delivery not confirmed by message_id")
    return result


def send_ready_workspace_checked(token: str, owner_chat_id: str, *,
                                 access_client_id: str, access_client_secret: str,
                                 base_url: str, mode: str, symbol: str,
                                 timeframe: str, signal_id: str | None,
                                 qr_directory: Path) -> dict:
    """Only public entrypoint for a verified gateway READY delivery."""
    if not verify_workspace_gateway(
        base_url, client_id=access_client_id, client_secret=access_client_secret
    ):
        raise RuntimeError("HTTPS gateway readiness or Access protection not verified")
    return send_ready_workspace(
        token, owner_chat_id, base_url=base_url, mode=mode, symbol=symbol,
        timeframe=timeframe, signal_id=signal_id, gateway_ready=True,
        access_policy_verified=True, qr_directory=qr_directory,
    )
