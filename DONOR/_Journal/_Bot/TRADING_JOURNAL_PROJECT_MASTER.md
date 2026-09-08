# TRADING JOURNAL — PROJECT MASTER / HANDOFF

**Repository:** `pvachaik/trading-journal`  
**Visibility:** Private  
**Default branch:** `main`  
**Local project path:** `D:\Trading\_Journal\_Bot`  
**Last verified local state:** `feature/exit-quality-v5` working tree clean after PostgreSQL-enabled verification
**Last verified test baseline:** `519 passed, 2 warnings`
**Handoff date:** 2026-09-07

---

## 1. Purpose of this document

This file is the main handoff point for continuing Trading Journal development in a new ChatGPT/Codex session.

A new session should treat the GitHub repository as the source of truth for code and current implementation state.

Recommended start sequence for a new chat:

1. Open repository `pvachaik/trading-journal`.
2. Read this file first.
3. Inspect latest commits on `main`.
4. Inspect repository structure and current tests.
5. Check open Issues / Pull Requests / CI status if present.
6. Continue from the "Next work" section below.
7. Do not ask the user to re-upload the whole project unless GitHub access is unavailable.

---

# 2. Product direction

Trading Journal is evolving from a Telegram-first journal into a broader trading platform component.

## Current product direction

### Website
The Website is the primary full application.

It should contain:
- full journal;
- trade details;
- statistics;
- configuration;
- automatic data;
- account/exchange settings;
- attention/incomplete workflows;
- later integration with Trading System.

### Telegram Bot
Telegram Bot is a companion interface.

Primary responsibilities:
- notifications;
- Attention Center alerts;
- quick completion/editing of selected trade fields;
- risk alerts;
- screener/setup alerts;
- morning briefing;
- compact KPI / statistics summaries.

### Telegram Mini App
Mini App is no longer a mandatory core dependency.

Existing Mini App frontend should be reused as the basis of a standalone responsive Web App where practical.

---

# 3. Core product principles

## Minimal manual input

A new mandatory manual field is added only when it answers a concrete statistical question.

If a value can be obtained or calculated automatically, the trader should not enter it manually.

## Historical integrity

Dynamic/custom field history must remain valid.

Rules:
- disabling a field stops collection for new trades;
- historical values remain;
- semantic meaning must not silently change;
- label rename may be allowed without changing the internal identity;
- internal technical identifiers are not user-facing.

## Multi-account / multi-exchange

Architecture is intended to support:
- multiple accounts;
- multiple exchanges;
- multiple simultaneous open trades;
- independent monitoring sessions.

There is no single global "current trade".

## Security

Never commit:
- `.env`;
- exchange API secrets;
- Telegram bot tokens;
- DB passwords;
- OpenAI keys;
- any other production secret.

`.env.example` contains only placeholders/default examples.

Backend/source repository remains private.

Frontend code must never contain secrets or trusted authorization logic.

Authentication/authorization and tenant/account isolation belong on the server.

---

# 4. Current implementation architecture

The repository is organized around layered architecture.

Major areas:

```text
app/
├── core/
├── application/
├── infrastructure/
├── miniapp/
└── telegram/

test/
├── application/
├── core/
├── infrastructure/
├── integration/
├── miniapp/
└── telegram/

alembic/
└── versions/
```

## Core
Contains domain entities, value objects, statistics concepts, trade logic, monitoring concepts, automatic-data contracts and related domain rules.

## Application
Contains:
- use cases;
- DTOs;
- ports;
- statistics engine;
- attention logic;
- automatic-data orchestration.

## Infrastructure
Contains:
- SQLAlchemy persistence;
- repositories;
- mappers;
- Bybit adapters;
- import/discovery functionality;
- maintenance utilities.

## Mini App / Web frontend base
Contains FastAPI Mini App server/API and current static frontend that can be evolved into the responsive Website.

## Telegram
Contains bot runtime, handlers, formatting, keyboards, attention/reminder flows and companion UI logic.

---

# 5. Implemented development phases

The project has already progressed through the following major areas.

## Phase 1 — Trade Core V1
Implemented account/instrument/trade identity and core Trade entity.

## Phase 2 — Execution Domain V1
Implemented Execution domain and normalized execution facts.

## Phase 3 — Trade Aggregation
Implemented aggregation of exchange executions into trades.

## Phase 4 — Dynamic Statistics Domain
Implemented dynamic/custom field definitions, options, scope and trade values.

## Phase 4.1 — Historical Integrity
Implemented historical-integrity rules for dynamic statistics.

## Phase 5 — Custom Field Resolver
Implemented field applicability resolution by context such as exchange/market/strategy/setup.

## Phase 6 — Derived Values
Implemented derived metric calculation service.

## Phase 7 — Trade Enrichment
Implemented enrichment pipeline for dynamic/derived context.

## Phase 8 — Repository Ports
Implemented repository protocols for core persistence boundaries.

## Phase 9A — SQLAlchemy Schema
Implemented SQLAlchemy models and DB schema base.

## Phase 9A.1 — Persistence Historical Integrity
Implemented DB-level historical integrity policy.

## Phase 9B — SQLAlchemy Repositories
Implemented repositories for trades, executions, custom fields, values, accounts and later supporting entities.

## Phase 9C — Alembic
Alembic migration system bootstrapped.

Current migration chain includes at least:

```text
0001 ...
0002 instruments / auto-data related base
0003_data_quality.py
0004_reminder_settings.py
0005_automatic_data_and_statistics_layout.py
0006_trade_take_profit.py
0007_history_import_and_journal_state.py
0008_trade_pnl_provenance.py
0009_reminder_delivery_state.py
```

## Phase 10 — Application Use Cases
Manual trade creation/closure, fees, expenses, custom values, enrichment, details and trade lists.

## Phase 11 — Telegram Production UI
Production-oriented Telegram workflows and separation of dev-only functionality.

## Phase 12 — Instruments
Instrument domain/repository/search and trade attachment.

## Phase 13 — Execution Fact Pipeline
Normalized exchange execution fact processing.

## Phase 14 — Bybit Adapter V1
Bybit client/config/execution source and mapping support.

## Phase 15 — Unit of Work + Orchestration
Transaction boundaries and execution-to-trade orchestration.

## Phase 15.1 — Market Data Enrichment
Market-data context/provider boundary and enrichment.

## Phase 15.2 — Statistics Engine
Statistics query/model/engine with grouped performance and coverage.

## Phase 16 — Mini App V1
FastAPI Mini App, Telegram WebApp authorization and initial UI.

## Phase 16.1+
UI improvements, PostgreSQL bootstrap hardening and subsequent functionality.

---

# 6. Major functionality added after the earlier Phase 16 baseline

The current repository contains additional substantial work beyond the old 16.1 baseline.

## Data quality / readiness

Trade readiness concepts exist.

Important statistical inclusion policy:

```text
OPEN
INCOMPLETE
READY
```

Statistics should include only:

```text
CLOSED + READY
```

Rules:
- `Net PnL = 0` is a valid breakeven result;
- missing/null data must never be silently converted to zero;
- `CLOSED + INCOMPLETE` is excluded from statistics until required data is completed.

## Attention Center

Attention functionality has been added for:
- open trades requiring attention;
- closed but incomplete trades;
- counters / attention summaries;
- reminder-related flows.

## Automatic Data

Generic automatic-data architecture is present.

Conceptual architecture:

```text
FactorDefinition
    ↓
AutomaticFactorRegistry
    ↓
Provider / Calculator
    ↓
FactorObservation
    ↓
Statistics
```

Technical names such as `MARKET_DATA`, `DERIVED`, `AT_ENTRY`, etc. must remain hidden from ordinary users.

### Automatic market-data snapshot V1 (Issue #10)

Bybit trades now receive a generic `AutomaticFactorObservation` snapshot from
the execution/import lifecycle. The snapshot is queried using the trade's
`opened_at`, persists no exploratory columns on `trades`, and uses the existing
Bybit V5 client and public kline endpoint. A complete close also persists
`holding_duration_seconds` as the exact UTC elapsed duration, including
fractional seconds, under DECIMAL definition/calculation version `2/2`.

V1 factors are:

```text
holding_duration_seconds
entry_hour
entry_day_of_week
volume_1d_at_entry
turnover_1d_at_entry
previous_day_volume
previous_day_turnover
avg_volume_prev_5d
avg_turnover_prev_5d
rvol_at_entry
```

Day boundaries are UTC. The historical `entry_hour` factor keeps its original local-user-time semantics and identity `1/1`.
Capture uses an explicit configured timezone for `entry_hour`, or the opening timestamp's timezone when none is configured; it is not relabeled as UTC.
`entry_day_of_week` is ISO weekday (`Monday=1`, `Sunday=7`) in UTC. Bybit linear
volume is stored in base-coin units; turnover is stored in USDT. Previous-day
and five-day aggregates use only complete UTC daily candles. RVOL uses the
current day's cumulative volume through the last fully closed one-minute
candle before the entry minute, divided by the average cumulative volume
through that same elapsed UTC-day minute across the five previous complete
days. Market-data source timestamps point to the actual last contributing
closed kline (or the latest daily candle for a five-day average), and
provenance records the RVOL cutoff/comparison window and daily contributing
candle bounds. Insufficient source data remains an explicit missing
observation.

Observation identity is versioned by trade, factor, definition version,
calculation version and capture semantics. Replayed imports/syncs do not add
duplicates; a previously missing observation may be repaired when a later
source lookup succeeds. No Alembic migration was needed for V1 because the
generic observation table already exists; the migration head remains
`0011_telegram_viewer_grants`.

### Automatic market-data snapshot V2 (Issue #16)

V2 extends the same versioned automatic-observation pipeline with these
thirteen Bybit LINEAR factors:

```text
market_price_at_entry_snapshot, day_open_price, day_high_at_entry,
day_low_at_entry, day_change_pct_at_entry, day_range_pct_at_entry,
day_range_position_at_entry, atr_1d_14, atr_1d_14_pct, day_range_to_atr,
vwap_1d_at_entry, distance_to_vwap_pct, change_24h_pct_at_entry
```

All V2 values are evaluated at `trade.opened_at`. The entry minute is
excluded; only fully closed 1m candles through the prior UTC minute are used,
and the same fetched intraday rows are reused for price, day range, VWAP and
the exact 24-hour comparison. `change_24h_pct_at_entry` requires the close of
the candle at exactly `cutoff - 24h`, so a nearby or future candle is never
substituted. Provenance records the cutoff, contributing intraday window,
and exact reference candle.

`atr_1d_14` is the arithmetic mean of 14 True Range values from the latest 14
fully closed UTC daily candles before the trade day. The one additional prior
closed daily candle supplies the previous close for the first True Range.
This is deliberately the Issue #16 ATR definition, not Wilder/RMA. ATR
provenance records all 15 required/contributing daily candle timestamps.
Bybit LINEAR VWAP is cumulative turnover divided by cumulative volume through
the cutoff. Missing source data or invalid denominators remain missing and are
never converted to zero. A full V2 snapshot uses the existing six bounded 1m
window requests and one bounded daily request; no request is made per factor.

V2 is storage-only and does not add Telegram Trade Details rows or manual
fields. No Alembic migration was needed because the generic observation schema
already supports the versioned decimal factors; the migration head remains
`0011_telegram_viewer_grants`.

### Automatic derivatives snapshot V3 (Issue #18)

V3 adds thirteen Bybit LINEAR derivatives factors through the same automatic
observation and lifecycle pipeline:

```text
open_interest_base_at_entry, open_interest_notional_usdt_at_entry,
open_interest_change_1h_pct_at_entry, open_interest_change_4h_pct_at_entry,
open_interest_change_24h_pct_at_entry, last_settled_funding_rate_at_entry,
avg_last_3_settled_funding_rate_at_entry, funding_interval_minutes_inferred_at_entry,
minutes_since_last_funding_at_entry, minutes_to_next_funding_inferred_at_entry,
mark_price_at_entry_snapshot, index_price_at_entry_snapshot,
mark_index_basis_pct_at_entry
```

Open Interest uses `opened_at` floored to a UTC five-minute bucket and the
exact cutoff one bucket earlier. Current, 1h, 4h and 24h references are exact
5m timestamps; nearest records are never substituted. A 24-hour OI window is
fetched backwards with deterministic pagination using the endpoint maximum of
200 records, normally requiring two requests for the 289 timestamps in the
inclusive 24h window. OI provenance records the cutoff and exact references.

Funding uses only historical `/v5/market/funding/history` settlements with
`fundingRateTimestamp <= opened_at`; predicted/current ticker funding is not
used. The latest three settled rates are averaged arithmetically, and the
historical funding interval is inferred from the two latest settlement
timestamps. Since/next-funding values use that inferred interval and preserve
fractional minutes where present.

Mark and index prices use exact fully closed 1m candles at
`floor(opened_at UTC to minute) - 1 minute`. Basis is `(mark / index - 1) *
100`. OI notional is OI multiplied by the historical mark snapshot. Source
timestamps and provenance preserve the exact source records and calculation
policies; missing values and invalid denominators remain missing.

Dependency sets overlap by source: OI-change factors require only OI, funding
factors only funding history, basis requires mark plus index, and OI notional
requires OI plus mark. A full V3 snapshot adds five bounded requests to the
V1/V2 seven-request snapshot: two OI pages, one funding request, one mark
request and one index request. Selective requests return only requested points.
V3 is storage-only, adds no manual fields or Telegram rows, and requires no
Alembic migration; the migration head remains `0011_telegram_viewer_grants`.

### Post-trade excursion analytics V4 (Issue #20)

V4 adds eight `POST_TRADE` observed-1m factors through the generic automatic
observation lifecycle:

```text
mae_observed_1m_extreme_price, mfe_observed_1m_extreme_price,
mae_observed_1m_price_distance, mfe_observed_1m_price_distance,
mae_observed_1m_pct, mfe_observed_1m_pct,
mae_observed_1m_gross_pnl_usdt, mfe_observed_1m_gross_pnl_usdt
```

Only CLOSED trades request the exchange-neutral `PostTradeMarketContext` /
`PostTradeMarketSnapshot` contract. The Bybit provider uses `/v5/market/kline`
interval `1` and includes exact entry/exit endpoints plus only candles whose
full one-minute interval is contained in `[opened_at, closed_at]`. Partial
opening/closing buckets are excluded. A sub-minute trade makes zero kline
requests and uses only its exact entry/exit facts. A normal trade with up to
1000 contained minutes uses one bounded request; longer ranges use deterministic
chunking.

The provider verifies that returned timestamps equal the complete expected
minute sequence. Any gap makes all V4 observations explicitly missing rather
than producing a partial valid path. Extreme ties choose the earliest source
timestamp. Zero MAE/MFE is valid. Gross-PnL factors are positive magnitudes of
price distance times quantity; fees, funding, expenses and `stop_price` are
excluded. R-normalized MAE/MFE is intentionally deferred because the current
stop is not versioned as initial stop-at-entry semantics.

Extreme provenance records the endpoint/candle source kind, true source
timestamp, containment window, expected/actual counts and the policy that a
kline timestamp is the candle bucket start, not the exact intraminute extreme
second. Repeated CLOSED capture is idempotent and missing observations remain
repairable. No schema or Alembic migration was needed; the migration head
remains `0011_telegram_viewer_grants`.

### Exit quality analytics V5 (Issue #22)

V5 adds eight `DERIVED` + `POST_TRADE` factors calculated from trade facts and
the current valid V4 `mfe_observed_1m_price_distance` observation:

```text
exit_directional_move_price_signed, exit_directional_move_pct_signed,
exit_efficiency_pct_of_observed_mfe, profit_capture_pct_of_observed_mfe,
mfe_giveback_price_distance, mfe_giveback_pct_of_observed_mfe,
mfe_giveback_pct_of_entry, mfe_giveback_gross_pnl_usdt
```

V5 performs zero Bybit/market-data requests. It runs after V4 persistence in
the same `AutomaticTradeDataCapture` call, so a repaired V4 dependency is
immediately available for V5 calculation. The dependency is selected by the
exact current registry identity: factor ID, definition version, calculation
version and `POST_TRADE` capture semantics; stale versions are never used.

Directional move is `X - E` for LONG and `E - X` for SHORT. MFE-dependent
factors require `D <= M`; `D > M` or a negative/corrupt M produces explicit
error observations without clamping. `M == 0` remains valid: directional move,
giveback distance, entry-relative giveback and gross giveback still calculate,
while only factors with an M denominator remain missing. Zero values are valid.
All V5 observations use `trade.closed_at` as `source_timestamp`. Provenance
contains the semantic, exact V4 dependency identity/value/source timestamp,
trade facts and the concrete factor formula. OPEN trades do not receive V5
observations. The generic observation schema is sufficient; no migration was
needed.

## Metric Registry / configurable statistics

A metric registry exists.

Product policy:
- stable `metric_id`;
- Overview metrics should be configurable;
- Main dashboard can pin selected KPIs;
- statistics must not be hard-coded to only Net PnL / Winrate / Count.

Target statistics include:
- result and risk;
- instrument breakdown;
- direction breakdown;
- dynamic-field breakdown;
- time breakdowns;
- P&L calendar;
- equity curve;
- drawdown;
- cumulative profit;
- coverage/readiness.

## Bybit historical import

Historical Bybit import functionality has been added, including areas such as:
- history discovery;
- compatibility;
- historical reconstruction/backfill;
- instrument catalog;
- safe history import;
- incremental synchronization.

Exchange execution facts should fill objective facts automatically.

The trader should later add only context not available from the exchange, such as strategy/setup/manual notes.

## Reminder delivery hardening

Reminder delivery state has been hardened.

Recent behavior includes:
- persistence failure after successful delivery is logged explicitly;
- runtime does not claim durable state if DB persistence failed;
- timezone/time/toggle updates preserve existing delivery state;
- maintenance utility exists to reset reminder delivery state for one configured account;
- tests cover this behavior.

Maintenance utility:

```text
app/infrastructure/persistence/reset_reminder_delivery_state.py
```

Related test:

```text
test/infrastructure/persistence/test_reset_reminder_delivery_state.py
```

---

# 7. Latest verified Git history

Recent verified commits:

```text
b15e597  Baseline after Phase 16.1.1 PostgreSQL bootstrap hardening
cdc5c02  Update Trading Journal to current development state
ce97325  Harden reminder delivery state persistence
e8cf24b  Add reminder delivery state reset tests
```

At the last local verification:

```text
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

---

# 8. Test baseline

Latest verified local run:

```text
510 passed, 2 warnings
```

Warnings were dependency deprecations involving FastAPI/Starlette/httpx/anyio, not test failures. This baseline was run with the PostgreSQL integration database enabled.

Before any major merge, run:

```powershell
pytest
```

Do not consider a feature complete if the existing regression suite is broken.

---

# 9. GitHub workflow from now on

GitHub should be the central project source of truth.

Avoid doing large future development directly on `main`.

Recommended workflow:

```text
GitHub Issue
    ↓
feature/fix branch
    ↓
Codex / implementation
    ↓
pytest
    ↓
commit + push
    ↓
Pull Request
    ↓
ChatGPT review
    ↓
CI / tests
    ↓
merge into main
```

Suggested branch names:

```text
feature/statistics-dashboard
feature/equity-curve
feature/pnl-calendar
feature/web-app-shell
feature/automatic-data-catalog
fix/bybit-sync-...
fix/reminder-...
```

Do not mix unrelated changes into one commit.

---

# 10. GitHub / local synchronization rule

The developer machine and GitHub must stay synchronized.

Before starting work:

```powershell
git status
git pull
```

After GitHub-side changes made by ChatGPT or another tool, the local machine must pull them:

```powershell
git pull
```

Before push:

```powershell
pytest
git status
git add ...
git commit -m "..."
git push
```

Never use `git add .` blindly when unknown files/logs/secrets are present.

---

# 11. Files that must remain excluded

Confirmed project rule:

```text
.env
runtime_logs/
```

Also exclude typical local/runtime artifacts as applicable:

```text
.venv/
__pycache__/
.pytest_cache/
*.log
```

Do not commit production credentials.

---

# 12. UI / UX product decisions already fixed

## Dynamic Custom Fields

User-facing rules:
- internal `code` hidden and autogenerated;
- Russian field type labels;
- field type explanation shown to users;
- rename label allowed without changing internal identity;
- inactive fields separated from active fields;
- actions represented with icons;
- initial install should be minimal;
- sample field can be `Комментарии`.

## Net PnL

Net PnL should not be manually entered when it can be calculated from objective trade data.

It must be derived from sufficient entry/exit/position/fee/expense information.

## Statistics

Statistics is the main product value and a top priority.

Do not reduce Statistics to three fixed numbers.

## Technical details

Internal provider/source/time-anchor identifiers should not be exposed directly to end users.

## Prototype IDs

For significant UI edits, maintain a clickable prototype / stable UI element identifier mechanism so the user can refer to elements by ID.

---

# 13. Relationship with Trading System

Trading Journal remains a separate project.

Trading System supplies strategy/risk/trading-process logic.

Trading Journal supplies:
- factual trade history;
- automatic exchange data;
- context fields;
- statistical analysis;
- performance feedback.

Long term:

```text
Trading System
    ↓
Watchlist / Strategy / Setup / Risk / Alerts
    ↓
Trade
    ↓
Trading Journal
    ↓
Statistics / Feedback
    ↓
Trading System improvement
```

Do not merge both codebases prematurely.

---

# 14. Current technical stack

Main known stack:

```text
Python 3.12
FastAPI
aiogram
SQLAlchemy 2.x
asyncpg
Alembic
PostgreSQL
pytest
Docker / docker-compose
Bybit integration
Telegram Bot / WebApp auth
```

Local PostgreSQL has previously been run with Docker.

Mini App / Web server factory pattern:

```text
app.miniapp.server:create_app --factory
```

---

# 15. What should happen next

The next session should not restart architecture discussions from zero.

Recommended next work order:

## A. Establish GitHub development discipline
1. Add/verify GitHub Actions for `pytest`.
2. Add root `README.md`.
3. Add `.gitattributes` for consistent line endings.
4. Consider branch protection after CI is stable.
5. Move feature work to branches + PRs.

## B. Website transition
1. Audit current `app/miniapp/static`.
2. Separate Telegram-WebApp-specific assumptions from generic Web UI.
3. Reuse current responsive frontend as standalone Website base.
4. Keep backend/API boundaries server-authoritative.

## C. Statistics — highest product priority
1. Audit metric registry.
2. Confirm stable `metric_id` set.
3. Implement configurable Overview layout.
4. Implement pinning of up to six main KPIs.
5. Add P&L calendar.
6. Add equity curve.
7. Add drawdown.
8. Add cumulative profit.
9. Add breakdowns by instrument/direction/custom fields/time.
10. Preserve readiness/coverage rules.

## D. Automatic Data
1. Formalize automatic-data catalog.
2. Map each factor to source/provider/calculator.
3. Define applicability.
4. Make technical fields invisible in UI.
5. Integrate observations generically into statistics.

## E. Bybit / journal automation
1. Validate historical import against real account data.
2. Validate incremental sync.
3. Confirm duplicate/idempotency handling.
4. Ensure imported execution facts reconstruct trades correctly.
5. Ask user only for unavailable trading context.

## F. Telegram companion
1. Keep Attention/reminders reliable.
2. Add compact statistics where useful.
3. Preserve no-spam reminder policy.
4. Keep Telegram as companion rather than full primary product.

---

# 16. Critical rules for the next ChatGPT/Codex session

1. Read this Master before proposing architectural changes.
2. Use GitHub as the source of truth.
3. Do not ask the user to manually copy the whole repository when GitHub is available.
4. Do not change established historical-integrity rules casually.
5. Do not expose internal technical codes in UI.
6. Do not add manual fields that can be automatically obtained.
7. Do not hard-code the statistics UI around a tiny fixed metric set.
8. Keep Trading Journal and Trading System as separate projects.
9. Use branches/PRs for substantial future work.
10. Run regression tests before merge.
11. Never commit secrets.
12. Record major product/architecture decisions back into this Master when they become authoritative.

---

# 17. Immediate handoff prompt for a new chat

Use this message in a new ChatGPT session:

```text
Продолжаем проект Trading Journal.

GitHub repository:
pvachaik/trading-journal

Сначала открой репозиторий и прочитай:
TRADING_JOURNAL_PROJECT_MASTER.md

GitHub является source of truth.
Проверь текущий main, последние commits, структуру проекта, тесты, Issues/PR/CI.
Не начинай проектирование заново и не проси меня пересылать весь код вручную.

Текущий подтверждённый baseline перед handoff:
- private repository
- main synchronized
- 473 tests passed
- migrations through 0009
- Automatic Data / Attention / readiness / statistics metric registry / Bybit historical import present
- reminder delivery state hardening completed

После проверки Master и repository предложи конкретный следующий технический шаг и, если нужна реализация, подготовь работу через Issue → branch → Codex → PR → review.
```

---

# 18. Master maintenance policy

This file is living documentation.

Update it when:
- a major phase is completed;
- architecture direction changes;
- new product-level rules are approved;
- a major subsystem is introduced;
- the next handoff point changes.

Do not update it for every tiny code edit.

Git commits, Pull Requests and Issues should carry low-level development history.

---

**Current handoff status:** READY FOR NEW CHAT.
