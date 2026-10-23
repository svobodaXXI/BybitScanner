"""Send owner a workspace mobile link + QR only after local and protected HTTPS checks.

Called by the owner PC launcher, never by a public HTTP endpoint. Unconfigured
remote access is an ordinary skip, not an opportunity to announce READY.
"""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from urllib.request import urlopen

from workspace_ready_telegram import send_ready_workspace_checked
from workspace_ready_link import workspace_link, write_workspace_qr


def _telegram_identity() -> tuple[str, str]:
    """Owner bot token and chat id; never logged.

    The dedicated BYBITSCANNER_TELEGRAM_* variables win. Otherwise the already
    configured Scanner/Robot Telegram identity is reused (config.TELEGRAM_TOKEN
    and the single owner chat config.TELEGRAM_CHAT_ID, same as
    notification.get_telegram_owner_chat_id); the broadcast list
    TELEGRAM_CHAT_IDS is deliberately not used. Missing config means no
    delivery, never a guess. Each value falls back independently.
    """
    token = (os.environ.get("BYBITSCANNER_TELEGRAM_BOT_TOKEN") or "").strip()
    owner = (os.environ.get("BYBITSCANNER_TELEGRAM_OWNER_ID") or "").strip()
    if token and owner:
        return token, owner
    try:
        import config
    except Exception:
        return token, owner
    if not token:
        token = str(getattr(config, "TELEGRAM_TOKEN", "") or "").strip()
    if not owner:
        owner = str(getattr(config, "TELEGRAM_CHAT_ID", "") or "").strip()
    return token, owner


def deliver_if_verified(mode: str, symbol: str, timeframe: str,
                        local_url: str = "http://127.0.0.1:4173/") -> bool:
    required = (
        "BYBITSCANNER_TERMINAL_HTTPS_URL",
        "BYBITSCANNER_ACCESS_CLIENT_ID",
        "BYBITSCANNER_ACCESS_CLIENT_SECRET",
    )
    if any(not os.environ.get(key) for key in required):
        return False
    bot_token, owner_chat_id = _telegram_identity()
    if not bot_token or not owner_chat_id:
        return False
    # The already-running UI must respond locally, even if the tunnel is healthy.
    try:
        with urlopen(local_url, timeout=3) as response:
            if response.status != 200:
                return False
    except (OSError, ValueError):
        return False
    # A Vite preview HTML 200 does not guarantee a working terminal backend.
    # Do not announce a usable signal view while the proxied API is unavailable.
    try:
        with urlopen("http://127.0.0.1:4173/api/health", timeout=3) as api_response:
            if api_response.status != 200:
                return False
            health = json.load(api_response)
            if not isinstance(health, dict) or health.get("ok") is not True:
                return False
    except (OSError, ValueError):
        return False
    send_ready_workspace_checked(
        bot_token,
        owner_chat_id,
        access_client_id=os.environ["BYBITSCANNER_ACCESS_CLIENT_ID"],
        access_client_secret=os.environ["BYBITSCANNER_ACCESS_CLIENT_SECRET"],
        base_url=os.environ["BYBITSCANNER_TERMINAL_HTTPS_URL"],
        mode=mode, symbol=symbol, timeframe=timeframe, signal_id=None,
        qr_directory=Path(os.environ.get("TEMP", ".")) / "BybitScanner-workspace-qr",
    )
    url = workspace_link(
        os.environ["BYBITSCANNER_TERMINAL_HTTPS_URL"], mode, symbol, timeframe
    )
    qr_path = Path(os.environ.get("TEMP", ".")) / "BybitScanner-workspace-qr" / (
        f"owner-{mode}-{symbol}-{timeframe}.png"
    )
    write_workspace_qr(url, qr_path)
    print("QR_FILE=" + str(qr_path))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("EDITOR", "TERMINAL"), required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    args = parser.parse_args()
    if deliver_if_verified(args.mode, args.symbol, args.timeframe):
        print("Mobile QR delivered to owner after authenticated HTTPS verification.")
    else:
        print("Mobile QR not sent: gateway configuration or local readiness unavailable.")


if __name__ == "__main__":
    main()
