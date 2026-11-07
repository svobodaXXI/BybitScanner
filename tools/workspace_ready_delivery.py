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
    """Get one complete, owner-only Telegram identity; never log credentials.

    A dedicated bot/owner pair wins. If either dedicated environment variable
    is set, both must be set: never mix credentials from different identities.
    Otherwise reuse only the existing Scanner owner's single chat from config,
    not the broadcast TELEGRAM_CHAT_IDS list.
    """
    token = (os.environ.get("BYBITSCANNER_TELEGRAM_BOT_TOKEN") or "").strip()
    owner = (os.environ.get("BYBITSCANNER_TELEGRAM_OWNER_ID") or "").strip()
    if token or owner:
        return (token, owner) if token and owner else ("", "")
    try:
        import config
        fallback_token = getattr(config, "TELEGRAM_TOKEN", None)
        fallback_owner = getattr(config, "TELEGRAM_CHAT_ID", None)
    except (ImportError, AttributeError, ValueError, TypeError):
        return "", ""
    if not isinstance(fallback_token, str):
        return "", ""
    if not isinstance(fallback_owner, (str, int)) or isinstance(fallback_owner, bool):
        return "", ""
    return fallback_token.strip(), str(fallback_owner).strip()


def deliver_if_verified(mode: str, symbol: str, timeframe: str,
                        local_url: str = "http://127.0.0.1:4173/",
                        signal_id: str | None = None) -> bool:
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
        mode=mode, symbol=symbol, timeframe=timeframe, signal_id=signal_id,
        qr_directory=Path(os.environ.get("TEMP", ".")) / "BybitScanner-workspace-qr",
    )
    url = workspace_link(
        os.environ["BYBITSCANNER_TERMINAL_HTTPS_URL"], mode, symbol, timeframe,
        signal_id=signal_id,
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
    parser.add_argument("--signal-id", default=None)
    args = parser.parse_args()
    if deliver_if_verified(args.mode, args.symbol, args.timeframe, signal_id=args.signal_id):
        print("Mobile QR delivered to owner after authenticated HTTPS verification.")
    else:
        print("Mobile QR not sent: gateway configuration or local readiness unavailable.")


if __name__ == "__main__":
    main()
