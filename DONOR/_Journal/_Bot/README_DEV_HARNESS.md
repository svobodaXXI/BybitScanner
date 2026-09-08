# Trading Journal — Development Harness

This is a small Telegram acceptance harness for the Phase 1 Trade Core. It is not the production Journal UI.

Current scope: single entry + full close only. Partial fills and partial closes are not implemented yet.

## Setup

From `D:\Trading\_Journal\_Bot`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Create a bot with [BotFather](https://t.me/BotFather) and put its token in `.env`:

```text
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_ALLOWED_USER_ID=
```

Set `TELEGRAM_ALLOWED_USER_ID` to your numeric Telegram user ID. If it is empty, every user is denied and their sender ID is logged to the console:

```text
Unauthorized Telegram user attempted access: 123456789
```

The harness never auto-authorizes unknown users. Do not put real tokens in `.env.example` or documentation.

## Start

```powershell
.\.venv\Scripts\python.exe -m app.dev_harness.bot
```

After `/start`, use the menu to open LONG/SHORT trades, inspect multiple in-memory trades, add fees and signed expenses, and close a trade. Restarting the process clears the in-memory store.

All PnL calculations remain in the Domain `Trade` API. Telegram only parses input, calls Domain methods, and formats Domain values.

