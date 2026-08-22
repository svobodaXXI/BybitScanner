"""Point the existing Telegram bot's owner menu button at a temporary HTTPS Workspace URL."""
import argparse

import config
from notification import get_telegram_owner_chat_id
from telegram_bot import set_workspace_menu_button


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Temporary HTTPS URL printed by cloudflared")
    parser.add_argument("--chat-id", default=None, help="Optional private chat ID override")
    args = parser.parse_args()
    chat_id = args.chat_id or get_telegram_owner_chat_id()
    if not chat_id:
        raise SystemExit("No owner Telegram chat ID is configured")
    response = set_workspace_menu_button(config.TELEGRAM_TOKEN, chat_id, args.url)
    if not response.get("ok"):
        raise SystemExit(f"Telegram rejected the menu button: {response.get('description', 'unknown error')}")
    print("Telegram Workspace menu button configured for the owner chat.")


if __name__ == "__main__":
    main()
