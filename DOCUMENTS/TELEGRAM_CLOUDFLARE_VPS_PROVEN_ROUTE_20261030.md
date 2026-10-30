# Telegram на VPS: проверенный маршрут через Cloudflare → Vercel

**Дата фактической проверки:** 2026-10-30. **Область:** Telegram transport в PAPER, без изменения торговли.  
**Статус:** GET `/health` с VPS, отправка текста и PNG **фактически подтверждены владельцем**. Inline-кнопки/callback, polling, автоматический запуск Telegram service и полный Scanner/PAPER E2E **ещё не проверены**.

## Схема и доказательства

```text
VPS /opt/BybitScanner
  telegram_gateway_client.py (configured; HTTPS, no direct Telegram fallback)
    → https://bybitscanner-gateway.svoboda21vekaru.workers.dev
      Cloudflare Worker (allowlist paths; passes Authorization and body)
        → https://bybitscanner-telegram-gateway.vercel.app
          Vercel Telegram Gateway (fixed owner; shared-secret authorization)
            → api.telegram.org
```

Факты из отчёта владельца и наблюдаемых результатов 2026-10-30:

- VPS (после owner-approved close/stop/deploy): код `d1329214ad2efe8d862114d39eca2077b6df467f`; PAPER DB integrity OK, FLAT/synced, pending/obligations 0; backend, Scanner, Robot, Telegram inactive; LIVE off.
- Прямой доступ VPS → Vercel давал TLS timeout, старый SOCKS/proxy давал Connection refused. Это причина смены **маршрута**, а не торгового кода.
- Worker `bybitscanner-gateway` активная deployment version `2181d8b3`, 100% traffic; в браузере и **на VPS с `curl --noproxy '*'`** путь `/health` вернул `component=bybitscanner-telegram-gateway`, `status=up`, `delivery_verified=false`. Health доказывает только доступность.
- В `/etc/bybitscanner/paper.env` заменён только `BYBITSCANNER_TELEGRAM_GATEWAY_URL` на URL Cloudflare Worker; результат `grep` подтверждён. Gateway secret оставлен прежним.
- В текущем VPS Python окружении вызов `telegram_gateway_client.send_text(..., "Gateway test")` привёл к **фактическому получению** сообщения владельцем в Telegram.
- В текущем VPS Python окружении вызов `telegram_gateway_client.send_photo_upload(..., "charts/0GUSDT_1_analysis.png", "Gateway PNG test")` привёл к **фактическому получению** PNG владельцем.
- Никакого подтверждения кнопок, чтения/обработки callback и полноценного полного прохода Scanner пока нет; не утверждать FULL PASS или end-to-end READY на основании этих двух отправок.

## Каноническая настройка при восстановлении

1. Использовать **существующий** проект Vercel `bybitscanner-telegram-gateway` и **существующий** Worker `bybitscanner-gateway`; не создавать второй бот, worker или poller.
2. Worker — простой HTTPS proxy **только** разрешённых `GET /health`, `POST /v1/send`, `POST /v1/photo-upload`, `POST /v1/photo-file-id`, `POST /v1/get-updates`, `POST /v1/bot-method`. Для остального 404; `Authorization`/body forwards unchanged; redirects must not be followed automatically. HTTPS upstream: `https://bybitscanner-telegram-gateway.vercel.app`. Worker does **not** contain Telegram bot token, Vercel credentials, or shared secret. Public Worker endpoint is *not* authorization: Vercel Gateway validates the shared secret, allowed methods, owner recipient and payload.
3. VPS machine-local `/etc/bybitscanner/paper.env`: `BYBITSCANNER_TELEGRAM_GATEWAY_URL=https://bybitscanner-gateway.svoboda21vekaru.workers.dev`. `BYBITSCANNER_TELEGRAM_GATEWAY_SECRET` remains private in the existing machine config; **never print/copy/upload/commit secret values or screenshots of the env file**. Backend and Telegram services read `paper.env` when started; inactive services do not hot reload.
4. Do not rely on broken old SOCKS proxy `127.0.0.1:10809`. Existing `telegram_gateway_client.py` creates `requests.Session` with `trust_env=False`; curl checks should be explicit `--noproxy '*'` when diagnosing that route. The proxy configuration itself is not a reason to mutate unrelated files.
5. For an operational acceptance check, use a **single bounded helper / agent operation** that reads environment without printing secrets, checks `/health`, sends one safe text and one existing PNG, optionally tests a non-trading inline keyboard, and reports per-stage outcome. **Do not manually walk the owner through dozens of Python REPL commands.** Do not use synthetic orders, runtime mutations or SQL edits to test Telegram.
6. Start/restart `bybitscanner-paper-start.service` **only on explicit owner authorization after current protected runtime state is checked**; it starts backend and optionally Telegram **and** requests runtime intent ALL (Scanner/Robot) plus PAPER_AUTO opt-in, i.e. it is **not** a Telegram-only test command. Scanner manual launch ownership remains governed by `DOCUMENTS/ASSISTANT_PROTOCOL.md`; do not quietly launch Scanner or autonomous trading as a transport check.
7. Telegram Gateway is *not* a trading authority: failures must not cause bypass of Admission/protection/STOP/TAKE. No automatic fallback direct to Telegram when Gateway configured; never turn a health check into a trading entrypoint.

## Recovery / failures

| Symptom | Narrow diagnosis / response |
| --- | --- |
| Worker `/health` from VPS returns timeout | Check worker deployment and **VPS→Cloudflare** path, not the robot or DB |
| Worker health reports up but send fails | Check Vercel upstream reachability, auth/config and actual Telegram response; health alone is insufficient |
| `Gateway delivery not confirmed: transport_unavailable` | Preserve honest NOT_READY; avoid endless synchronous MIRROR retries. In code `d1329214`, MIRROR sends are throttled with failure cooldown |
| `photo keyboard not supported` | In code `d1329214`, photo upload can succeed and the inline action keyboard is sent in a separate text message. Do not claim buttons are attached to the photo. Verify keyboard/callback independently |
| Photo succeeds but menu fails | Do not automatically resend an already accepted photo: it may duplicate. `keyboard_delivered=false` is partial-delivery evidence |
| Owner cannot paste long shell commands in browser terminal | Avoid long commands and repetitive prompt-by-prompt REPL. Use a narrowly scoped existing tool, prepared tracked helper, or one owner-approved action |
| Credentials suspected exposed | Rotate Gateway shared secret and any actually exposed credentials through their owners, without printing them. Owner **declined rotation on 2026-10-30**; this is an **open security risk**, not a cleared finding |

## Future completion boundary (not yet achieved)

Before claiming Telegram service/PAPER E2E operational: confirm one real callback/button operation in Telegram; one ordinary Scanner signal with correct pattern/timeframe/PNG and expected action menu; normal scan coverage and no unchecked MIRROR backlog blocking the loop. Scanner/Robot autonomous runtime must be separately authorized and verified; a completed GitHub PR or health result does not substitute for VPS evidence.

**Source ownership:** `deploy/telegram_gateway/worker.mjs` owns Vercel Gateway behavior, `telegram_gateway_client.py` owns VPS client, `deploy/systemd/bybitscanner-telegram.service` / `deploy/systemd/bybitscanner-paper-start.service` own systemd topology. The Cloudflare Worker shown here was configured manually in Cloudflare dashboard; its deployed version is not automatically managed by GitHub. Do not imply that the Vercel Worker source is the actual Cloudflare deployment.
