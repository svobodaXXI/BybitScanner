# TRADING JOURNAL PROJECT PLAN — DYNAMIC STATS & AUTO ENRICHMENT

**Version:** V2.0  
**Date:** 2026-09-02  
**Project:** Trading Journal — программная часть дневника сделок для единой Trading System  
**Status:** Updated implementation plan  
**Source inputs:** `TRADING_JOURNAL_CHANGE_TASK_DYNAMIC_STATS_AUTO_V0_1.md`, `TRADING_SYSTEM_PROJECT_MASTER_V1_1.md`

---

# 0. Назначение

Trading Journal является фактическим и статистическим ядром единой торговой системы.

Его задача:

1. фиксировать то, что реально произошло со сделкой;
2. автоматически получать всё, что может дать биржа, брокер, система или Market Data;
3. запрашивать у трейдера только неизвестный контекст;
4. хранить контекст отдельно от фактического Trade Core;
5. давать Statistics Engine качественные и исторически корректные данные;
6. позволять добавлять новые статистические вопросы без изменения таблицы `trade` и без переделки Trade Core.

Главный поток:

```text
TRADING SYSTEM / EXCHANGE / MANUAL INPUT
                  ↓
              TRADE FACT
                  ↓
        AUTO FACTUAL ENRICHMENT
                  ↓
           DERIVED VALUES
                  ↓
              TELEGRAM
                  ↓
       MANUAL CONTEXT ENRICHMENT
                  ↓
        CUSTOM STATISTICS VALUES
                  ↓
              DATABASE
                  ↓
          STATISTICS ENGINE
                  ↓
               REVIEW
                  ↓
        TRADING SYSTEM REVISION
```

---

# 1. Главный архитектурный принцип

Дневник разделяется на два слоя.

## 1.1 Stable Trade Core

Маленькое стабильное ядро хранит факты сделки и финансовые инварианты.

Пример логического Core:

```text
trade_id
account_id
instrument
exchange
direction
opened_at
closed_at
entry_price
exit_price
stop_price
quantity
strategy_code
setup_code
strategy_version
risk_money
risk_pct
fees
expenses
gross_pnl
net_pnl
result_r
status
```

Core не означает MANUAL.

Если данные доступны автоматически, они заполняются автоматически.

## 1.2 Dynamic Statistical Layer

Исследовательские и контекстные параметры не должны бесконечно добавляться колонками в `Trade`.

Они живут через:

```text
CustomFieldDefinition
CustomFieldOption
CustomFieldScope
TradeCustomValue
```

Добавление нового статистического параметра не требует:

- новой колонки `trade`;
- миграции Trade Core;
- изменения Telegram-кода под каждое новое поле;
- изменения Domain Trade Entity.

---

# 2. Важное уточнение к Protected Core

`strategy_code` и `setup_code` нужны системе как фундаментальные классификаторы сделки, но они не являются биржевым фактом.

Поэтому архитектурно нужно различать:

```text
FACTUAL CORE
CLASSIFICATION CORE
DYNAMIC RESEARCH FIELDS
```

### FACTUAL CORE

То, что реально произошло:

```text
account
instrument
direction
entry
exit
quantity
executions
fees
opened_at
closed_at
gross_pnl
net_pnl
```

### CLASSIFICATION CORE

Главные измерения торговой системы:

```text
strategy_code
setup_code
strategy_version
```

Они стабильны как понятия, но могут быть заполнены вручную.

### DYNAMIC RESEARCH FIELDS

Например:

```text
Breakout Quality
Market Condition
Tape Quality
Psychology
News Catalyst
Compression Grade
Range Width Category
Order Flow Confirmation
```

Эти поля не должны входить в `Trade` как отдельные колонки.

---

# 3. Источники данных

Для каждого статистического значения должен быть известен источник:

```text
MANUAL
EXCHANGE
SYSTEM
MARKET_DATA
DERIVED
```

## MANUAL

Только то, чего система достоверно не знает.

Пример:

```text
strategy
setup
psychology
discretionary market condition
trade quality
research observation
```

## EXCHANGE

Получаем от биржи/брокера:

```text
instrument
side
executions
entry
exit
quantity
fees
opened_at
closed_at
realized pnl
exchange identifiers
```

## SYSTEM

Создаёт наше приложение:

```text
trade_id
account reference
strategy version
timestamps
internal state
```

## MARKET_DATA

Получаем из Market Data Service:

```text
ATR
relative volume
VWAP
daily change
turnover
volume
MAE
MFE
market measurements
```

## DERIVED

Вычисляем из уже имеющихся данных:

```text
day_of_week
entry_hour
trading_session
holding_time
position_value
stop_distance
risk_pct
result_r
R multiple
```

---

# 4. Правило MVP

AUTO и DERIVED не откладываются на поздние этапы.

MVP должен сразу уметь:

```text
получить факт
→ сохранить факт
→ вычислить доступные DERIVED данные
→ определить отсутствующие MANUAL данные
→ спросить только их
```

Если сначала реализовать полностью ручной дневник, а AUTO добавить потом, придётся переделывать:

- lifecycle сделки;
- Telegram workflow;
- storage;
- validation;
- statistics coverage;
- domain/application services.

Поэтому AUTO-ready architecture делается до Telegram UI.

---

# 5. Custom Statistics

## 5.1 CustomFieldDefinition

Минимальная модель:

```text
id
code
name
value_type
source
status
required
phase
description
created_at
updated_at
```

`phase` рекомендуется добавить сразу:

```text
OPEN
POST_TRADE
ANY
```

Это позволит отделить вопросы при открытии сделки от post-trade review.

## 5.2 CustomFieldOption

Для `CHOICE`:

```text
id
field_id
code
label
sort_order
active
```

## 5.3 CustomFieldScope

Область применимости:

```text
field_id
market optional
exchange optional
strategy_code optional
setup_code optional
```

В будущем можно расширить:

```text
account_id
instrument_category
trading_type
```

Но general-purpose rules engine в MVP не нужен.

## 5.4 TradeCustomValue

```text
trade_id
field_id
value
recorded_at
source
definition_version
```

`definition_version` рекомендуется предусмотреть, чтобы статистика не смешивала значения после существенного изменения смысла поля.

---

# 6. Типы Custom Fields V1

MVP:

```text
CHOICE
NUMBER
YES_NO
TEXT
```

Позже без изменения архитектуры:

```text
MULTI_CHOICE
INTEGER
DECIMAL
PERCENTAGE
DURATION
DATETIME
RATING
```

---

# 7. Lifecycle Custom Fields

Статусы:

```text
ACTIVE
INACTIVE
```

Правила:

- ACTIVE участвует в новых сделках;
- INACTIVE не собирается для новых сделок;
- старые значения сохраняются;
- поле может быть реактивировано;
- hard delete запрещён при наличии исторических значений.

Если смысл поля существенно изменился:

```text
не переопределяем историю
→ создаём новую версию / новое поле
```

---

# 8. Statistics Coverage

Отсутствие значения и значение `UNKNOWN` — разные состояния.

Пример:

```text
BREAKOUT trades = 100
Trading Session collected = 57
coverage = 57%
```

Статистика по Trading Session строится на 57 наблюдениях.

Оставшиеся 43 не должны автоматически становиться:

```text
UNKNOWN
```

если трейдер реально не выбирал категорию UNKNOWN.

Statistics API позже должен возвращать:

```text
sample_size
coverage_count
coverage_pct
missing_count
```

---

# 9. Trade Lifecycle

Основное правило:

```text
ORDER != TRADE FACT
```

Создание заявки само по себе не создаёт завершённый факт сделки.

## Open

```text
EXECUTION / POSITION OPENED
        ↓
find or create logical Trade
        ↓
attach execution
        ↓
calculate weighted entry
        ↓
save exchange facts
        ↓
run derived enrichment
        ↓
calculate missing manual context
        ↓
Telegram notification
```

## Add / partial fills

Новые исполнения той же позиции:

```text
same logical trade
→ add execution
→ recalculate quantity
→ recalculate weighted entry
→ update fees
```

Они не создают независимые Telegram-сделки.

## Partial close

```text
closing execution
→ reduce open quantity
→ update realized pnl
→ trade remains OPEN if quantity != 0
```

## Full close

```text
remaining quantity == 0
→ CLOSED
→ closed_at
→ exit calculation
→ fees
→ pnl
→ holding duration
→ Result R
→ MAE/MFE finalization
→ post-trade enrichment
```

---

# 10. Trade Aggregation — обязательный отдельный компонент

Нельзя помещать правила агрегации исполнений прямо в Bybit/Finam adapter или Trade entity.

Нужен application/domain service:

```text
TradeAggregationService
```

или:

```text
PositionTradeAssembler
```

Он отвечает за:

- partial fills;
- weighted average entry;
- scale-in;
- partial exit;
- full close;
- linking exchange executions to logical Journal Trade.

Adapter должен только преобразовывать внешний API в единый внутренний контракт.

---

# 11. Exchange Adapter Contract

Нужно определить единый формат события.

Пример:

```text
ExecutionFact
- exchange
- account_id
- external_execution_id
- external_order_id
- instrument
- side
- quantity
- price
- fee
- fee_currency
- executed_at
- position_id optional
- raw_reference optional
```

Для изменения позиции:

```text
PositionSnapshot
- exchange
- account_id
- instrument
- side
- quantity
- average_entry
- realized_pnl
- unrealized_pnl optional
- updated_at
```

Bybit, Binance, MOEX/Finam и будущие брокеры адаптируются к этим внутренним контрактам.

Trade Core не должен знать API Bybit.

---

# 12. Idempotency — обязательное добавление к плану

Биржи могут присылать одно событие повторно после reconnect.

Поэтому:

```text
external_execution_id
+
exchange
+
account
```

должны позволять определить дубликат.

Повторное событие не должно:

- повторно увеличить position quantity;
- дважды начислить fee;
- создать вторую сделку;
- повторно изменить PnL.

Idempotency должна быть частью MVP exchange ingestion.

---

# 13. Enrichment Status

Trade lifecycle и заполненность статистики разделяются.

Trade может быть OPEN/CLOSED независимо от заполненности анкеты.

Отдельный статус:

```text
NOT_REQUIRED
PENDING
COMPLETE
```

Это позволяет:

```text
реальная сделка сохранена
+
контекст можно заполнить позже
```

и исключает потерю фактических сделок из-за незаполненного Telegram-опроса.

---

# 14. Enrichment Engine

Рекомендуется отдельный application service:

```text
TradeEnrichmentService
```

Он получает Trade и выполняет:

```text
1. SYSTEM values
2. EXCHANGE values
3. MARKET_DATA values
4. DERIVED values
5. resolve active scopes
6. determine missing MANUAL fields
7. calculate enrichment status
```

Telegram не должен сам решать, какие поля показывать.

Telegram вызывает:

```text
get_missing_manual_fields(trade_id)
```

---

# 15. Telegram Dynamic Form

Telegram становится renderer динамической схемы, а не местом бизнес-логики.

### AUTO-created trade

```text
NEW TRADE

BTCUSDT LONG
Entry: ...
Quantity: ...
Opened: ...

Missing context:
Strategy
Setup
Market Condition

[Fill now]
[Later]
```

### Fill now

Flow:

```text
Strategy
   ↓
filter Setup
   ↓
resolve CustomFieldScope
   ↓
ask only relevant ACTIVE MANUAL fields
```

### Important

Telegram никогда не спрашивает:

- EXCHANGE значения;
- SYSTEM значения;
- MARKET_DATA значения, если они уже доступны;
- DERIVED значения.

---

# 16. Strategy / Setup

Текущие словари:

## Strategy

```text
LONG_CONTINUATION — WORKING
CONSOLIDATION_SHORT — RESEARCH
```

Будущие:

```text
SHORT_CONTINUATION
LONG_REVERSAL
SHORT_REVERSAL
```

## LONG_CONTINUATION setups

```text
COMPRESSION
BREAKOUT
RETEST
```

## CONSOLIDATION_SHORT setups

```text
REJECTION
FAILED_BREAKOUT
LOCAL_BREAKDOWN
```

Strategy и Setup должны быть расширяемыми справочниками.

Нельзя зашивать их Python Enum таким образом, чтобы добавление стратегии требовало изменения Core-кода и миграции.

Допускается Domain Value Object для `StrategyCode`, но конкретный список кодов должен храниться в конфигурации/БД.

---

# 17. Trading System Data Contract

Journal должен поддерживать архитектуру:

```text
Dominant Market Context
Local Market Context
Market Phase
Strategy
Setup
Direction
Entry Type
Execution / Order Flow
Risk
Psychology
Rule Compliance
Result
MAE
MFE
```

Но эти параметры не обязаны быть фиксированными колонками Trade.

Разделение:

### Core classification

```text
Strategy
Setup
Direction
```

### Dynamic statistics / context

Например:

```text
Dominant Context
Local Context
Market Phase
Entry Type
Order Flow Grade
Psychology
Trade Quality A/B/C
```

### MARKET_DATA / DERIVED

Например:

```text
MAE
MFE
ATR
relative volume
daily change
holding duration
session
```

Конкретный источник каждого параметра задаётся отдельно.

---

# 18. MAE / MFE

MAE/MFE лучше не просить у трейдера вручную.

Источник:

```text
MARKET_DATA
```

Алгоритм:

```text
trade opened_at → closed_at
+
market candles/ticks
+
direction
→ MAE
→ MFE
```

Если Market Data недоступен:

```text
value absent
coverage < 100%
```

а не ручной обязательный вопрос.

---

# 19. Financial Core сохраняется

Ранее принятые правила остаются.

## Multiple trades

Одновременно допускается:

```text
many OPEN trades
many ACTIVE monitoring sessions
```

Каждая сделка независима.

## Expense sign

```text
net_pnl = gross_pnl - fees + expenses
```

```text
+25 expense adjustment → Net PnL +25
-25 expense adjustment → Net PnL -25
```

## Monitoring

Monitoring session не является самой сделкой.

Истечение monitoring TTL не закрывает Trade.

---

# 20. Рекомендуемые Domain / Application компоненты

## Existing / Core

```text
Money
Price
Quantity
Percentage
Risk
Expense
Trade
TradeLeg
Order
Execution
PnL
Account
Instrument
```

## New Value Objects / Enums

```text
FieldCode
FieldValueType
FieldSource
FieldStatus
EnrichmentStatus
FieldPhase
StrategyCode
SetupCode
```

## New Domain Models

```text
CustomFieldDefinition
CustomFieldOption
CustomFieldScope
TradeCustomValue
```

## Application Services

```text
TradeAggregationService
TradeEnrichmentService
CustomFieldService
CustomFieldResolver
DerivedValueService
StatisticsCoverageService
```

## Integration Contracts

```text
ExecutionFact
PositionSnapshot
MarketDataSnapshot
```

---

# 21. Обновлённый порядок разработки

Старый линейный план необходимо заменить.

## PHASE 0 — Freeze current domain invariants

Проверить уже сделанные:

```text
Money
Price
Quantity
Percentage
Risk
Expense
_decimal
```

Зафиксировать финансовые правила и не ломать их.

Результат:

```text
stable value-object foundation
```

---

## PHASE 1 — Trade Core V1

Реализовать минимальный Trade Core.

Нужно:

```text
TradeId
TradeStatus
Direction
Account reference
Instrument reference
opened_at
closed_at
entry/exit
quantity
stop
risk
PnL
fees
expenses
```

Не добавлять исследовательские поля в Trade.

Тесты:

- open;
- update;
- partial quantity;
- close;
- invalid states;
- PnL invariants.

---

## PHASE 2 — Execution / Trade Aggregation

Реализовать:

```text
Execution
ExecutionFact
TradeAggregationService
```

Поддержать:

```text
partial fills
weighted entry
scale-in
partial close
full close
duplicate event protection
```

Это нужно сделать раньше биржевого адаптера.

---

## PHASE 3 — Dynamic Statistics Domain

Реализовать:

```text
CustomFieldDefinition
CustomFieldOption
CustomFieldScope
TradeCustomValue
```

Поддержать:

```text
ACTIVE
INACTIVE
CHOICE
NUMBER
YES_NO
TEXT
MANUAL
EXCHANGE
SYSTEM
MARKET_DATA
DERIVED
```

Добавить validation и domain tests.

---

## PHASE 4 — Scope Resolver

Реализовать:

```text
CustomFieldResolver
```

Запрос:

```text
trade/account/market/strategy/setup
```

Результат:

```text
relevant active fields
```

Проверить:

```text
global
market-specific
exchange-specific
strategy-specific
setup-specific
```

---

## PHASE 5 — Derived Data Engine

Реализовать минимальные DERIVED значения:

```text
day_of_week
entry_hour
trading_session
position_value
holding_duration
stop_distance
result_r
```

Bucket configuration хранить вне Trade Core.

---

## PHASE 6 — Enrichment Engine

Реализовать:

```text
TradeEnrichmentService
```

Он должен:

```text
resolve fields
fill available AUTO
calculate DERIVED
find missing MANUAL
set enrichment status
```

---

## PHASE 7 — Persistence / PostgreSQL

Только после стабилизации domain model.

Таблицы:

```text
users
accounts
account_rules
instruments
trades
trade_legs
orders
executions
expenses
trade_events
custom_field_definitions
custom_field_options
custom_field_scopes
trade_custom_values
monitoring_sessions
reminder_settings
daily_settlements
```

Важные DB rules:

```text
unique exchange execution identity
historical custom values preserved
no cascade delete of statistical history
indexes for strategy/setup/statistics queries
```

---

## PHASE 8 — Repository Layer

Интерфейсы:

```text
TradeRepository
ExecutionRepository
CustomFieldRepository
TradeCustomValueRepository
AccountRepository
```

Infrastructure implementation через PostgreSQL/SQLAlchemy.

---

## PHASE 9 — Manual Trade Application Flow

Сделать сначала минимальный working path:

```text
Telegram/manual command
→ create trade
→ save fact
→ run enrichment
→ ask missing MANUAL context
```

Таким образом можно начать реальное накопление данных ещё до подключения биржи.

---

## PHASE 10 — Telegram Dynamic UI

Реализовать:

```text
dynamic field renderer
choice buttons
number input
yes/no
text
strategy → setup dependency
Fill now
Later
Complete review
```

Telegram не содержит списка статистических полей в коде.

---

## PHASE 11 — Exchange Adapter Contract

Создать общий port:

```text
ExchangeTradeAdapter
```

который публикует внутренние:

```text
ExecutionFact
PositionSnapshot
```

---

## PHASE 12 — First Crypto Adapter

Для первого MVP рекомендуется Bybit.

Причина:

- удобный API;
- executions;
- position data;
- fees;
- realtime updates;
- пользователь в будущем планирует crypto integration.

Но сам Journal не должен зависеть от Bybit.

Flow:

```text
Bybit
→ adapter
→ ExecutionFact
→ TradeAggregationService
→ Trade
→ Enrichment
→ Telegram
```

---

## PHASE 13 — Automatic Close / Update

Поддержать:

```text
partial close
full close
fees update
exit
realized pnl
closed_at
holding duration
result_r
post-trade fields
```

---

## PHASE 14 — Market Data Enrichment

После базового trade flow подключить:

```text
ATR
relative volume
daily change
VWAP
MAE
MFE
```

Поля идут через общий enrichment pipeline.

---

## PHASE 15 — Statistics Engine V1

Сначала базовые метрики:

```text
Trades
Win Rate
Average Win
Average Loss
Expectancy R
Total R
Profit Factor
Average R
Max Drawdown
```

Разрезы строятся динамически по:

```text
Strategy
Setup
Custom Statistics
```

Обязательно показывать coverage.

---

## PHASE 16 — Reports

```text
Daily
Weekly
Monthly
Strategy
Setup
Risk
Psychology
Execution
System Health
```

---

# 22. Что поменялось относительно старого плана

## Было

```text
Journal Data Contract
→ Database
→ Telegram
→ Statistics
→ Automation later
```

## Стало

```text
Stable Core
→ Execution model
→ Dynamic Statistics
→ AUTO/DERIVED architecture
→ Enrichment Engine
→ Database
→ Telegram
→ Manual real usage
→ Exchange adapter
→ Market Data
→ Statistics
```

Причина:

AUTO влияет не только на integration layer.

Он влияет на:

- Trade lifecycle;
- ownership данных;
- storage;
- Telegram UX;
- missing fields;
- statistics coverage;
- idempotency;
- post-trade workflow.

---

# 23. Что НЕ надо делать сейчас

Не нужно:

- строить универсальный rules engine;
- зашивать все поля Trading System в Trade;
- делать scanner;
- делать AI setup recognition;
- автоматизировать выбор стратегии;
- автоматизировать вход/выход;
- строить сложный Research Engine;
- делать все биржи одновременно;
- делать полноценный Market Data Analytics до рабочего Journal Core;
- заставлять трейдера вручную вводить данные, которые можно вычислить.

---

# 24. Первый практический этап программирования

Текущий проект уже находится на этапе Python Domain Interfaces.

Следующая рекомендуемая последовательность кода:

```text
STEP 1
закончить / проверить Value Objects

STEP 2
Direction / TradeStatus / TradeId

STEP 3
Trade Entity V1

STEP 4
Execution Entity + ExecutionFact

STEP 5
TradeAggregationService

STEP 6
Custom Statistics Value Objects

STEP 7
CustomFieldDefinition

STEP 8
CustomFieldOption

STEP 9
CustomFieldScope

STEP 10
TradeCustomValue

STEP 11
CustomFieldResolver

STEP 12
DerivedValueService

STEP 13
TradeEnrichmentService

STEP 14
Persistence mappings
```

После этого уже идти к Telegram и Bybit adapter.

---

# 25. Главный acceptance scenario MVP

```text
1. Пользователь открывает BTCUSDT LONG на Bybit.

2. Bybit сообщает execution.

3. Adapter создаёт ExecutionFact.

4. Journal проверяет idempotency.

5. TradeAggregationService создаёт logical Trade.

6. EXCHANGE данные сохраняются автоматически.

7. SYSTEM данные создаются автоматически.

8. DERIVED engine рассчитывает доступные значения.

9. CustomFieldResolver определяет релевантные поля.

10. Telegram показывает факт сделки.

11. Telegram спрашивает только:
    Strategy
    Setup
    и остальные ACTIVE MANUAL поля.

12. Пользователь может нажать Later.

13. Trade остаётся валидным и сохранённым.

14. При закрытии Bybit присылает executions.

15. Journal агрегирует закрытие.

16. Trade становится CLOSED.

17. Рассчитываются:
    Net PnL
    Result R
    Holding Duration
    доступные MAE/MFE.

18. Telegram предлагает post-trade review.

19. Statistics Engine учитывает сделку и показывает coverage каждого статистического поля.
```

Если этот сценарий работает, основная архитектура Journal MVP доказана.

---

# 26. Граница ответственности

## Trading Journal

Отвечает за:

```text
что реально произошло
какие данные были получены
какие значения вычислены
какой контекст добавил трейдер
историческую целостность
```

## Trading System

Отвечает за:

```text
какие стратегии существуют
какие setups исследуются
какие правила действуют
какие гипотезы проверяются
```

## Statistics Engine

Отвечает за:

```text
что статистически работает
где достаточно данных
какое покрытие выборки
какой expectancy
```

---

# 27. Итоговая архитектура

```text
                  TRADING SYSTEM
                        │
            Strategy / Setup Catalog
                        │
                        ▼
                 TRADING JOURNAL
                        │
          ┌─────────────┴─────────────┐
          │                           │
     FACTUAL CORE              STATISTICAL LAYER
          │                           │
 Execution / Trade             Custom Fields
 Account / Instrument          Scope / Source
 PnL / Risk / Fees             Historical Values
          │                           │
          └─────────────┬─────────────┘
                        ▼
                 ENRICHMENT ENGINE
              ┌─────────┼─────────┐
              ▼         ▼         ▼
          EXCHANGE   DERIVED   MARKET DATA
              │         │         │
              └─────────┼─────────┘
                        ▼
                    TELEGRAM
                        │
                   MANUAL ONLY
                        │
                        ▼
                    DATABASE
                        │
                        ▼
                STATISTICS ENGINE
                        │
                        ▼
                     REVIEW
                        │
                        ▼
                 SYSTEM EVOLUTION
```

---

# 28. Финальное решение V2.0

Фиксируем:

1. `Trade` остаётся маленьким и стабильным.
2. Статистические исследования не расширяют `Trade` бесконечно.
3. Custom Statistics являются отдельным полноценным domain layer.
4. `AUTO/DERIVED` входят в MVP.
5. Exchange integration работает через внутренний adapter contract.
6. Partial fills агрегируются в logical Trade.
7. Exchange events обрабатываются идемпотентно.
8. Telegram спрашивает только отсутствующие MANUAL данные.
9. Факт сделки не зависит от заполнения статистической анкеты.
10. Strategy/Setup остаются расширяемыми.
11. Historical values никогда не исчезают при деактивации поля.
12. Statistics обязана показывать coverage.
13. MAE/MFE в идеале собираются автоматически через Market Data.
14. Manual и Auto trade flows заканчиваются одной и той же моделью `Trade`.
15. Journal программируется как независимое ядро, но его Data Contract согласован с единой Trading System.

---

# 29. Следующий шаг

Продолжить текущий этап `Python Domain Interfaces V1`.

Первый следующий объект:

```text
Trade Entity V1
```

но перед написанием кода зафиксировать точный минимальный интерфейс:

```text
TradeId
TradeStatus
Direction
Trade
Execution
ExecutionFact
```

После этого перейти к `TradeAggregationService`, а затем к Dynamic Statistics Domain.

