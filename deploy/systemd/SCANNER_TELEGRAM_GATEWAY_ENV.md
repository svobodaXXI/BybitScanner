# Scanner → Telegram Gateway: shared systemd environment

**Confirmed 2026-10-30:** the running PAPER backend/Scanner had neither `BYBITSCANNER_TELEGRAM_GATEWAY_URL` nor `BYBITSCANNER_TELEGRAM_GATEWAY_SECRET`, while the Telegram service had both. Scanner fell back to direct Telegram SOCKS and failed with connection refused. The running backend and PAPER_AUTO must **not** be restarted to fix notifications.

Both systemd unit source files now include optional `EnvironmentFile=-/etc/bybitscanner/telegram-gateway.env`. This is a **configuration contract for the next separately authorized canonical PAPER start**, not a hot reload or a claim that delivery is already fixed.

The VPS operator must reuse the already working Telegram Gateway URL/secret from the existing secured Telegram service configuration without printing them, and provision a **single protected** shared environment file readable by service user `bybitscanner` (directory permissions must also allow access). The existing `TELEGRAM_CHAT_ID` must be the same authorized recipient. Do not copy credentials into GitHub, terminal output or process arguments. Avoid leaving conflicting overrides from other systemd drop-ins and verify the actual effective environment safely before the next start. The optional file does not replace validation; if absent, Gateway won't be enabled for Scanner.

**Deployment gate:** systemd `daemon-reload` alone does not update an already-running process environment. Do not run `systemctl restart bybitscanner-paper-backend`, kill the process, restart Scanner independently, or change PAPER_AUTO/DB. Enable new environment only on the next owner-approved **canonical safe stop/start** after protection and positions permit it. No automatic trading runtime restart. After that, verify one **real** Scanner signal through Gateway to the owner's Telegram; do not inject artificial trading signals.

No LIVE. No change to trading logic, admission, STOP/TAKE or ledger.
