# Cloudflare direct Gateway — migration pending (09.11.2026)

**Goal:** keep the existing VPS HTTPS URL and Telegram single-consumer unchanged,
but replace the current Cloudflare → Vercel → Telegram proxy with
Cloudflare Workers → Telegram. Existing Vercel 402 quota rejection is a proven
transport blocker. This is an operator-controlled migration, not a Telegram,
Backend, Scanner, Robot, or PAPER DB redeployment.

- Source: `cloudflare_proxy_worker.mjs` re-exports the existing tested
  `worker.mjs` API handler; Wrangler bundles the local module. The deployed
  Cloudflare version must be attested separately. No Vercel fetch or env is
  required.
- Existing Worker name: `bybitscanner-gateway`. Existing VPS URL is unchanged.
  Do **not** create a second bot/Worker/getUpdates consumer.
- **Source and host are separate authorities.** Upload a staged Cloudflare version
  from an exact reviewed GitHub checkout of `stable/adfb50b-forward` on the
  authorized workstation/CI, not the VPS installation. The installed VPS
  Backend SHA can legitimately lag GitHub stable and is not a condition for
  `wrangler versions upload`. In particular, `STABLE_SHA_UNAVAILABLE_ON_VPS`
  must not block **Cloudflare staging**; diagnose a real SSH/host routing issue
  only when a VPS-dependent action is explicitly authorized. Do not transfer
  or install GitHub source onto VPS just to stage the Worker.
  Cloudflare version ID and **active deployment** are separate facts:
  uploaded != production; verify both independently and never infer cutover
  from `/health=200`.
- **Before any deploy**, create three Cloudflare Worker **Secrets** (not plain
  variables) under the existing Worker: `GATEWAY_SHARED_SECRET` (exactly the
  current VPS gateway secret), `TELEGRAM_BOT_TOKEN` (existing bot token),
  `TELEGRAM_CHAT_ID` (fixed existing owner destination). Use owner-controlled
  secret storage; never paste values into PRs, chats, CI logs, or repo files.
  `wrangler.toml` declares these bindings required: absent secrets block the
  deployment. Setting secrets may create a new Worker version; coordinate
  any such rollout with separate owner authorization.
- CI always runs the focused direct-routing/auth/single-consumer-safe tests.
  **Merging a PR does not deploy.** After a separate owner deploy authorization,
  dispatch the existing `Cloudflare Telegram Gateway deploy` workflow on
  `stable/adfb50b-forward` with its protected Cloudflare environment; it
  publishes the existing Worker, not a new worker. Cloudflare credentials for
  the GitHub environment must be configured; the workflow never reads private
  Telegram secret values. The Worker deploy must preserve dashboard vars and
  existing secrets.
- Verify existing VPS Telegram health `127.0.0.1:8766/health` reaches HTTP
  200 `status=ready` and matching DB identity **without a restart**, then
  confirm real authorized Telegram delivery/menu/callback under owner control.
  A public `/health` HTTP 200 only proves Worker transport availability;
  it is not Telegram delivery or EDITOR_ONLY readiness.
- On any unknown, remain BLOCKED with original VPS release, Backend, PAPER DB,
  receipts, Scanner STOPPED, Autopilot OFF and LIVE gates unchanged. Do not
  re-run STOP, launch a second poller, delete Vercel before validated cutover,
  or fall back directly from VPS to Telegram API. Cloudflare Workers Free has
  resource limits; real polling and photo delivery remain runtime acceptance
  gates.

---

# Telegram Gateway — минимальный маршрут (#684)

**Историческая спецификация MVP #684.** По состоянию на 2026-10-30 проверены VPS → Cloudflare → Vercel → Telegram (реально получены текст и PNG); кнопки/callback и полный PAPER E2E пока не приняты. Актуальная схема, адреса, восстановление и подтверждённые факты: [TELEGRAM_CLOUDFLARE_VPS_PROVEN_ROUTE_20261030.md](../../DOCUMENTS/TELEGRAM_CLOUDFLARE_VPS_PROVEN_ROUTE_20261030.md). Этот файл сохраняет проектный контракт, не является текущим отчётом о развертывании.

## Цель
Вместо старого Windows SOCKS/SSH-туннеля использовать один HTTPS Gateway на внешней площадке, которая имеет доступ к Telegram API. Торговая логика остаётся на VPS. Telegram не блокирует открытие/закрытие PAPER-сделок и защиту STOP/TAKE.

## Текущий прототип
- Gateway Worker: аутентифицированная отправка текста с inline-кнопками, фото PNG/JPEG с ограничением размера, повторное использование Telegram photo file_id; relay для getUpdates и разрешённых методов меню/ответа на callback.
- Python: opt-in клиент в существующих telegram_bot.py и telegram_monitoring.py. Один существующий getUpdates consumer на VPS; Worker самостоятельно не опрашивает Telegram.
- Секреты только в защищённой конфигурации: GATEWAY_SHARED_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID; на VPS BYBITSCANNER_TELEGRAM_GATEWAY_URL и BYBITSCANNER_TELEGRAM_GATEWAY_SECRET. Секреты не помещать в GitHub или журналы.
- При настройке Gateway попытка отправки текста выполняется ограниченно (не более двух запросов с одним event_id). Возможны дубли при потере подтверждения — это допустимо для обычных уведомлений, **не для торговых команд**.
- Необязательные Durable Objects и отдельная SQLite-outbox исключены из MVP. Нет обязательного ручного разбора UNKNOWN.

## Атомарная Telegram-карточка (ожидает deployment / реальную приёмку)

Причина жалобы владельца 31.10.2026: старый Gateway передавал PNG без Unicode caption/keyboard, а потом отдельным сообщением подпись/навигацию. Сообщение другого символа могло вклиниться между ними (на скриншоте ALCHUSDT / WOOUSDT). Это проблема транспорта, а не доказательство неверного сигнала.

Новый `POST /v1/photo-card` принимает multipart `photo` PNG/JPEG (до 2 МБ), `caption` UTF-8 (до 1024 символов) и `reply_markup` JSON с существующей allowlist inline-кнопок; также принимает JSON `file_id`, `caption`, `reply_markup` для репоста архива. Gateway делает **ровно один** вызов Telegram `sendPhoto`; нет отдельного сообщения «Навигация», нет потери связи фото/подпись/кнопки. Только фиксированный авторизованный chat_id. Не добавлять торговые команды, прямой Telegram fallback, новый consumer или перезапись исходного архива.

**Порядок развёртывания обязателен:** сначала обновить Vercel Gateway на новый endpoint и Cloudflare Worker allowlist, подтвердить доступность нового маршрута без отправки реальных сигналов; **только потом** включать новый VPS Python-клиент при безопасном операционном переходе. До обновления обоих внешних компонентов VPS остаётся на старом коде, не следует переключать клиент отдельно: он fail-closed по HTTP 404. Старый /v1/photo-upload сохранён для обратной совместимости на время перехода. Не перезапускать Scanner/Robot с открытыми PAPER-позициями без защиты и согласованного переключения. Нельзя считать GitHub CI доказательством доставки в Telegram. После deployment проверить одно реальное фото с подписью и кнопками в **одном message_id**, затем карточку MIRROR/Robot с точным campaign lineage; до этого acceptance открыта.

## Границы и критерии приёмки
1. Выбран и разрешён реальный хостинг. Проверены VPS → конкретный HTTPS endpoint и Gateway → Telegram API. Общий NETWORK_READY с GitHub/Google не заменяет эту проверку.
2. Подтверждена успешная отправка и фактическое получение сообщения владельцем; кнопки и одна безопасная команда работают через авторизованный канал. Не выдавать /health или Telegram API 200 за прочтение владельцем.
3. При временном сбое Telegram выдаёт отдельное NOT_READY и возобновляет работу без перезапуска торговли; не вызывает дополнительного торгового действия.
4. Проверены ограничения получателя, auth, отсутствие прямого fallback при настроенном Gateway, короткие целевые тесты и логирование без токена.
5. Только после успешной приёмки и разрешения владельца менять работающий Telegram service. Backend, Robot, Scanner и PAPER_AUTO не трогать. LIVE запрещён.

Это транспортное решение без гарантий exactly-once доставки; не добавлять сложную state-machine без доказанной необходимости.
