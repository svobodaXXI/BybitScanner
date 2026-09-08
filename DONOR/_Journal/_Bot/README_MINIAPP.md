# Trading Journal Mini App V1

The Mini App uses FastAPI, plain HTML/CSS/JavaScript, and the existing Application/Statistics read services. No frontend framework or public CDN is required; the only remote script is Telegram's official WebApp bridge, which supplies `initData` and theme integration.

Data quality V1 is derived in the domain/application layers. General statistics include only `CLOSED + READY`; `OPEN` and `CLOSED + INCOMPLETE` are excluded and reported in readiness counts. Reminder settings and the no-spam due policy are available as pure, testable application policy. A production scheduler/delivery worker is intentionally not enabled yet, so Telegram reminders are not sent automatically.

Statistics exposes a stable metric registry (`/api/miniapp/statistics/metrics`), cumulative PnL series, per-account Overview/Home layouts, and metric-specific coverage. Home pins are limited to six and use `7d`, `30d`, `90d`, or `all` periods; unknown persisted metric IDs are ignored safely.

Automatic Data is foundation-only in this phase. Definitions and generic observations use a registry plus typed storage (`automatic_factor_observations`), with provider/calculator ports, capability/quality statuses, generic factor settings, and factor-aware query primitives. Adding a factor does not add a Trade column or migration. The current UI exposes plain-language catalog cards and keeps routing/look-ahead metadata internal.

## Frontend platform boundary

The reusable UI in `app/miniapp/static/app.js` does not talk to the Telegram WebApp runtime directly. Platform-specific initialization and authentication headers are supplied through `window.TradingJournalPlatform`.

The current Telegram shell loads:

```text
Telegram WebApp SDK
    ↓
/static/telegram-platform.js
    ↓
/static/app.js
```

`telegram-platform.js` owns `window.Telegram.WebApp`, `ready()`, `expand()`, `initData`, and construction of the `X-Telegram-Init-Data` request header. The generic UI consumes only `prepare()`, `authHeaders()`, and the provider authentication error message.

This boundary is intentionally incremental. It preserves the existing Telegram Mini App while allowing a future standalone Website shell to provide a different production authentication/session adapter without copying journal/statistics rendering logic. There is no unauthenticated Website fallback or development authentication bypass.

For reproducible PostgreSQL, Windows, Linux, backup, restore, and port setup, see [README_SETUP.md](README_SETUP.md).

Development server:

```text
uvicorn app.miniapp.server:create_app --factory --reload
```

Configure `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, and `TELEGRAM_WEBAPP_URL`. Telegram API requests send validated WebApp `initData` in `X-Telegram-Init-Data`; server-side authentication remains authoritative.

Acceptance checklist:

- [ ] Open Mini App from the Telegram Bot button
- [ ] Owner authentication succeeds; stale/wrong users are rejected
- [ ] Dashboard loads summary values
- [ ] Journal shows OPEN and CLOSED trades with pagination
- [ ] Instrument search/filter works
- [ ] Trade Details shows historical custom fields/options
- [ ] Statistics summary and direction grouping load
- [ ] Dynamic Field grouping and applicability-aware coverage load
- [ ] Minimum sample size and explicit missing bucket work
- [ ] Narrow/mobile viewport has no primary horizontal overflow
- [ ] Telegram light/dark theme remains readable
- [ ] Dashboard hero and KPI hierarchy are readable at 320/375/430px
- [ ] Bottom navigation keeps Dashboard / Journal / Statistics reachable
- [ ] Attention Center shows OPEN and INCOMPLETE trades with missing reasons
- [ ] Loading, empty, authentication, and generic error states are concise
- [ ] Trade Details presents symbol, status, core data, financials, and context
- [ ] Dynamic statistics shows Eligible / Filled / Missing / Coverage%
- [ ] Statistics metric catalog and Overview/Home layout controls persist after reload
- [ ] Automatic Data catalog shows plain-language cards without technical source/capture metadata
- [ ] Generic `app.js` contains no direct Telegram WebApp runtime/auth transport dependency
