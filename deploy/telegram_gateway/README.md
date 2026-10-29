# Telegram Gateway — send-only prototype (#684)

This is an isolated **prototype**, not a production-ready Telegram integration and not a deployment instruction. It does not modify the running VPS, Backend, Robot, PAPER_AUTO, SQLite, or Telegram monitoring.

## Contract
- `GET /health`: process availability only; explicitly reports `delivery_verified:false`.
- `POST /v1/send`: HTTPS JSON `{"event_id":"unique_identifier_123","text":"message"}`; header `Authorization: Bearer <GATEWAY_SHARED_SECRET>`.
- Server-side secrets: `GATEWAY_SHARED_SECRET` (minimum 32 characters), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Do not put them in code, commits, requests logged by proxies, or examples containing real values.
- Telegram chat is **fixed by configuration**; client cannot choose the destination or Bot API method. The response distinguishes Telegram API acceptance from owner-observed receipt.
- No `getUpdates` consumer; existing `telegram_monitoring.py` remains the only listener until an explicitly reviewed inbound design is available.

## Mandatory before production
1. Choose an authorized external hosting location and verify **VPS → exact gateway HTTPS URL** and **gateway → Telegram API**. General TLS access to GitHub/Cloudflare is insufficient.
2. Add durable outbox/retry/deduplication across network crashes and response-loss windows; `event_id` is currently only validated and echoed, **not** persisted or deduplicated. Do not enable automatic retries that may create duplicate user notifications.
3. Integrate gateway transport into existing `telegram_bot.py` and other Telegram request paths without changing trading logic; test protected single-owner polling and, if needed, design authenticated inbound commands separately.
4. Add rate limiting, abuse controls, bounded logs, request-size enforcement by bytes, integration tests, secret rotation and revocation procedure.
5. Verify a real owner-visible Telegram message and PAPER identity, prove trading contour unchanged; only then permit `TELEGRAM_DELIVERY_READY`.
6. Obtain separate owner approval for resource provisioning, deployment, and runtime changes. LIVE remains prohibited.

This prototype intentionally does not declare Telegram READY and does not solve the existing `getUpdates` outage.
