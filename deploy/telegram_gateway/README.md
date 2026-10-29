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

## Current integration slice
- `telegram_bot.send_message` opts into the gateway only when `BYBITSCANNER_TELEGRAM_GATEWAY_URL` is set; otherwise original direct Bot API transport remains unchanged.
- Set `BYBITSCANNER_TELEGRAM_GATEWAY_SECRET` (same bearer key as Worker) and `TELEGRAM_CHAT_ID` in the Telegram service's protected environment. No secrets in repository. The client excludes inherited system SOCKS proxies for the Gateway HTTPS hop.
- Text messages now support a constrained subset of inline keyboards (`callback_data`, HTTPS `url` and HTTPS `web_app`); photo, menu configuration, and `getUpdates` calls still use direct Telegram API and remain blocked on this VPS. **Do not deploy this slice as an operational fix.**
- Existing owner commands and monitoring require an authenticated inbound relay and expanded Bot API coverage before this can replace current Telegram transport.

## Inbound relay slice (unverified)
- Worker exposes authenticated `POST /v1/get-updates`; it proxies Telegram's single long-poll response and never polls autonomously. VPS `telegram_monitoring.py` stays the **sole** update consumer and continues owner checks and existing callback dispatch.
- Restricted `POST /v1/bot-method` supports only `answerCallbackQuery`, `setMyCommands`, `getChatMenuButton`, `setChatMenuButton`; it does not permit arbitrary Telegram methods or trading API operations.
- `telegram_monitoring._telegram_request` uses the gateway only when opted in; existing direct behavior remains the default.
- **Not a deployed or accepted solution:** callbacks and full workflows still depend on additional direct Telegram API uses, photos remain direct, durable delivery is absent, Worker hosting and endpoint are unverified. No production rollout.

## Expanded transport slice
- The existing Telegram Web App menu setter now uses the constrained `setChatMenuButton` Gateway method when enabled.
- `send_photo_by_file_id` now supports Gateway transport for a known Telegram file ID without uploading new media. This path rejects photo keyboards until the full supported contract is implemented.
- Uploads of local image files remain direct and cannot work through the blocked VPS network. The durable outbox/deduplication and deployment remain outstanding. No production acceptance yet.
