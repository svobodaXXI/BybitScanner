# BybitScanner — Future Features

Version:

1.0

Date:

2026-08-11

Document Type:

FUTURE_FEATURES_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-FUTURE-FEATURES-001

purpose:

Фиксирует согласованные будущие функции BybitScanner,
которые не должны отвлекать от текущего приоритета разработки,
но должны быть сохранены для последующей реализации.

machine_readable:

true

parser_version:

1.0

---

# DEVELOPMENT_PRINCIPLE

Current priority:

Geometry
→
Wedge Detection
→
Geometry Ranking
→
Scanner Reliability

Future Features не должны перехватывать
текущий рабочий приоритет.

Они реализуются только после стабилизации
соответствующего базового слоя.

---

# FEATURE-001

name:

Pattern Measured-Move Target Visualization

status:

DEFERRED

priority:

PLANNED

applies_to:

- Falling Wedge
- Rising Wedge
- Triangle Compression
- future compatible pattern types

---

## PURPOSE

После подтверждённого пробоя структуры
Scanner должен рассчитывать
потенциальную цель движения
и отображать её непосредственно
на Telegram-графике сигнала.

---

## TARGET_MEASUREMENT_MODEL

LONG setup:

Измеряется вертикальное расстояние
между первым значимым High
и первым значимым Low структуры.

Полученное расстояние переносится вверх
от точки подтверждённого пробоя.

SHORT setup:

Используется зеркальная логика.

Измеренное расстояние переносится вниз
от точки подтверждённого пробоя.

---

## TELEGRAM_VISUALIZATION

Telegram chart должен отображать:

- горизонтальную целевую линию;
- стрелку от области пробоя к цели;
- рассчитанный потенциал движения в процентах;
- при необходимости числовое значение target price.

Telegram chart не должен отображать:

- вспомогательную измерительную линию исходной высоты структуры;
- лишнюю техническую разметку расчёта;
- элементы, ухудшающие читаемость сигнала.

---

## VISUAL_PRINCIPLE

Пользователь должен сразу видеть:

Pattern

→

Breakout

→

Direction

→

Target

→

Potential %

без необходимости самостоятельно измерять
высоту структуры на графике.

---

## REFERENCE_VISUAL

approved_visual_concept:

Telegram Target Overlay

visual_elements:

- breakout origin marker;
- directional target arrow;
- target horizontal line;
- percentage potential label.

status:

CONCEPT APPROVED

---

## IMPLEMENTATION_STAGE

implementation_after:

- Wedge Geometry stabilization;
- Geometry Ranking stabilization;
- Wedge Detection reliability;
- Breakout confirmation reliability.

recommended_stage:

Signal Visualization / Target Projection Layer

---

# FEATURE-002

name:

Geometry Review Bridge / Web Geometry Reviewer

status:

DEFERRED / ARCHITECTURE DIRECTION APPROVED

---

## PURPOSE

Создать интерактивный контур проверки
и коррекции геометрии, найденной BybitScanner.

Основной workflow:

Scanner

↓

Geometry / Overlay Payload

↓

Web Geometry Reviewer

↓

Human Review / Geometry Correction

↓

Annotation

↓

Training Dataset

↓

Geometry Calibration

---

## EXISTING_INFRASTRUCTURE

reuse_existing_components:

- tradingview_bridge.py;
- tradingview/importer.py;
- training/storage.py;
- contracts/annotation_contract.py;
- TRADINGVIEW_JSON_CONTRACT.md.

principle:

Существующая инфраструктура TradingView Bridge
не должна заменяться новой реализацией с нуля.

Она должна эволюционировать в более общий
Geometry Review Bridge.

TradingView остаётся внешним инструментом
просмотра графика и ручной проверки,
но не является обязательным ядром
Geometry Reviewer.

---

## GEOMETRY_REVIEW_MODEL

review_input:

- symbol;
- timeframe;
- candles;
- upper_line;
- lower_line;
- anchor points;
- apex;
- compression;
- touches;
- validation;
- scanner score.

review_actions:

- ACCEPT;
- CORRECT;
- REJECT.

correction_capabilities:

- перемещение anchor points;
- коррекция upper trendline;
- коррекция lower trendline;
- сохранение исправленной геометрии.

review_output:

Human-validated Annotation Contract.

---

## ANCHOR_GEOMETRY_INTEGRATION

principle:

Текущая anchor-based geometry должна стать
основным форматом интерактивной коррекции линий.

Relevant line properties:

- anchor_index;
- anchor_price;
- second_index;
- second_price;
- slope;
- intercept.

Две anchor points определяют линию
и позволяют человеку визуально корректировать
геометрию непосредственно на графике.

---

## TRAINING_FEEDBACK_LOOP

target_workflow:

Scanner Prediction

↓

Human Reference

↓

Actual Market Outcome

↓

Training Dataset

↓

Geometry Calibration

purpose:

Создать накопительную базу примеров,
позволяющую сравнивать геометрию сканера
с человеческой разметкой и фактической
рыночной отработкой структуры.

---

## IMPLEMENTATION_STAGE

implementation_after:

- Anchor Geometry stabilization;
- Wedge Geometry stabilization;
- Geometry Ranking stabilization;
- Wedge Detection reliability.

recommended_stage:

Geometry Intelligence / Human Feedback Layer

---

# FEATURE-003

name:

Signal Report Archive / GitHub Sync

status:

PLANNED / ARCHITECTURE DIRECTION APPROVED

priority:

HIGH

---

## PURPOSE

Создать автоматический архив структурированных
отчётов по сигналам BybitScanner,
доступный для последующего анализа
непосредственно через GitHub.

Цель:

минимизировать необходимость ручной передачи
консольного вывода, отчётов и графиков
между пользователем и ассистентом.

---

## SIGNAL_REPORT_MODEL

Для каждого реально сформированного
и отправленного торгового сигнала
Scanner должен сохранять структурированный
машиночитаемый JSON-отчёт.

Отчёт должен включать по возможности:

- timestamp;
- symbol;
- timeframe;
- pattern;
- direction;
- score;
- geometry score;
- upper anchor;
- lower anchor;
- START;
- slopes;
- apex;
- compression;
- touches;
- geometry_mode;
- canonical downgrade reason;
- containment diagnostics;
- pre_pattern_impulse;
- breakout / confirmation data;
- calculated potential / target;
- ссылку или идентификатор соответствующего
  Telegram Review / annotation.

Формат должен допускать расширение
по мере развития Geometry Engine.

---

## STORAGE_MODEL

recommended_structure:

signal_reports/
    YYYY-MM-DD/
        SYMBOL_TIMEFRAME_TIMESTAMP.json

Принцип:

обычные автоматически создаваемые PNG-графики
не должны массово сохраняться в GitHub.

Причина:

- быстрое увеличение размера репозитория;
- бинарные файлы плохо подходят
  для истории Git;
- большинство обычных графиков
  не требуется для последующего анализа.

---

## REFERENCE_CHART_POLICY

Ценные графические примеры,
отобранные человеком или системой,
могут сохраняться отдельно в:

training/reference_patterns/

К таким материалам относятся:

- подтверждённые хорошие паттерны;
- geometry errors;
- anchor / START errors;
- необычные структуры;
- фактические outcomes;
- эталонные обучающие примеры.

---

## TELEGRAM_REVIEW_INTEGRATION

Signal Report Archive должен быть связан
с Telegram Review Queue.

target_relationship:

Scanner Signal

↓

Signal JSON

↓

Telegram Review

↓

Human Labels

↓

Outcome

↓

Training / Geometry Calibration

Один рыночный пример должен иметь возможность
накапливать несколько human-review labels,
например:

- good;
- geometry_error;
- anchor_error;
- queue / needs_review.

---

## GITHUB_SYNC

Новые отчёты должны синхронизироваться
с GitHub пакетно.

Предпочтительная точка синхронизации:

после успешного завершения полного Scan.

Не создавать отдельный Git commit
для каждого сигнала.

Один Scan должен по возможности создавать
не более одного автоматического
Signal Report Sync commit.

---

## ASSISTANT_ACCESS

После синхронизации ассистент должен иметь
возможность читать Signal Reports
непосредственно из GitHub
при диагностике и разработке.

Это должно позволить:

- сравнивать группы сигналов;
- анализировать good / bad geometry;
- искать систематические ошибки anchors / START;
- исследовать pre-pattern context;
- оценивать качество новых фильтров;
- анализировать outcomes;
- уменьшить необходимость ручного
  копирования диагностического вывода.

---

## SAFETY_AND_REPOSITORY_RULES

Signal Reports не должны содержать:

- Telegram bot token;
- API secrets;
- passwords;
- другие приватные credentials.

config.py остаётся вне GitHub.

Автоматическая GitHub-синхронизация
не должна отправлять:

- config.py;
- временные .bak файлы;
- обычные массовые charts;
- другие исключённые рабочие артефакты.

---

## IMPLEMENTATION_STAGE

recommended_stage:

Scanner Diagnostics / Training Feedback Infrastructure

implementation_direction:

Signal Report

→

Review Queue

→

Outcome

→

GitHub Archive

→

Comparative Analysis

→

Geometry Calibration

---

## STATUS

architecture_direction:

APPROVED

implementation:

PLANNED



# FEATURE-004

name:

Hierarchical Multi-Account Robot / Capacity-Aware Candidate Delegation

status:

DEFERRED / ARCHITECTURE DIRECTION APPROVED

priority:

FUTURE

---

## PURPOSE

Позволить нескольким Robot runtime работать на разных торговых счетах и,
при необходимости, на разных серверах, не конкурируя за один и тот же сигнал.

Основной сценарий:

- Senior Robot работает на более крупном счёте;
- Junior Robot работает на отдельном меньшем счёте;
- Senior получает первичное право на подходящий durable candidate;
- если Senior не может безопасно/эффективно исполнить candidate из-за
  ограничений капитала, ликвидности, лимита открытых позиций или
  приоритетов портфеля, candidate может быть атомарно делегирован Junior;
- после делегирования только один Robot остаётся execution owner этого
  candidate.

Эта функция не является способом обойти risk limits. Она должна распределять
кандидаты между независимыми счетами, сохраняя исходные торговые и защитные
инварианты каждого счёта.

---

## EXTERNAL_REFERENCE_RESEARCH — 2026-09-29

Точного готового retail-bot паттерна
"Senior account rejects -> Junior account inherits exact candidate"
в рассмотренных проектах не обнаружено. Ближайшие зрелые идеи:

### Freqtrade

Freqtrade поддерживает Producer/Consumer mode: один bot instance публикует
analyzed data/signals, другие instances могут их использовать, не пересчитывая
источник независимо.

Полезная идея для BybitScanner:

- один canonical signal/candidate source;
- consumers не должны заново изобретать исходную геометрию;
- межпроцессная передача должна быть аутентифицирована и иметь bounded message
  contract.

Также Freqtrade отдельно рекомендует независимые DB/ports/config для нескольких
bot instances.

References:
- https://www.freqtrade.io/en/stable/producer-consumer/
- https://www.freqtrade.io/en/stable/advanced-setup/

### Hummingbot

Hummingbot API имеет portfolio/account-level endpoints и умеет агрегировать
состояние нескольких accounts/connectors.

Полезная идея:

- allocator должен видеть account-level balances/capacity отдельно от
  execution runtime;
- решение о маршрутизации должно учитывать доступный капитал и ограничения
  конкретного счёта, а не только качество сигнала.

Reference:
- https://hummingbot.org/hummingbot-api/routers/

### QuantConnect / LEAN

LEAN явно разделяет Alpha/Insight -> Portfolio Construction -> Risk Management
-> Execution. Это полезный архитектурный precedent для отдельного слоя
allocation между candidate и execution.

Interactive Brokers Financial Advisor integration также показывает group/account
routing как отдельную concern от генерации сигнала.

При этом QuantConnect отмечает, что обычные pre-trade buying-power/risk checks
привязаны к одному portfolio и не являются готовым multi-account risk engine.
Это подтверждает, что BybitScanner должен иметь собственный cross-account
allocator, а не пытаться спрятать эту функцию внутри одного Robot state machine.

References:
- https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/portfolio-construction/key-concepts
- https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/key-concepts
- https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/financial-advisors
- https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/pre-trade-risk-control

---

## ARCHITECTURE DIRECTION

Target flow:

Scanner / canonical durable candidate

↓

Candidate Allocator

↓

Senior account eligibility + capacity gate

├─ ACCEPT -> Senior Robot becomes execution owner

└─ DELEGATE -> atomic ownership transfer -> Junior Robot eligibility gate

    ├─ ACCEPT -> Junior Robot becomes execution owner

    └─ REJECT -> candidate remains unexecuted / terminalized by policy

The allocator owns routing only.

It MUST NOT:

- place exchange orders directly;
- own protection;
- mutate pattern geometry;
- recalculate the immutable trade plan differently per Robot;
- silently weaken strategy/risk gates to force utilisation of idle capital.

Each Robot keeps its existing per-account:

- execution;
- reconciliation;
- protection;
- position lifecycle;
- emergency handling;
- runtime health.

---

## ACCOUNT MODEL

Each Robot instance must have a stable account identity.

minimum identity:

- trading_account_id;
- robot_instance_id;
- runtime/server identity;
- PAPER/LIVE mode;
- supported venue/account;
- capital/risk budget.

Senior and Junior must use different trading accounts.

A candidate assignment must therefore identify at minimum:

- candidate_id;
- source signal/plan identity;
- assigned_trading_account_id;
- assigned_robot_instance_id;
- assignment_version;
- assignment_reason;
- assigned_at;
- prior_assignment if delegated.

---

## OWNERSHIP INVARIANTS

Hard invariant:

ONE candidate -> ONE current execution owner.

Required properties:

1. assignment/delegation is durable;
2. delegation is atomic from the allocator's point of view;
3. Senior loses order authority before Junior gains it;
4. Junior must acknowledge the exact assignment/version before placing any
   order;
5. stale assignment versions are rejected;
6. restart/recovery reconstructs ownership from durable state;
7. network partition cannot legitimately create two owners;
8. if ownership is uncertain, both sides fail closed for new mutation until
   reconciliation establishes the current owner;
9. an already-open position is not migrated between accounts by this mechanism;
10. manual operator actions remain explicit and account-scoped.

Recommended state shape:

UNASSIGNED
-> OFFERED_SENIOR
-> OWNED_SENIOR

or

OFFERED_SENIOR
-> DELEGATION_PENDING
-> OWNED_JUNIOR

Any ambiguous transition:

-> RECONCILIATION_REQUIRED

No execution is allowed from an ambiguous assignment state.

---

## DELEGATION REASONS

Initial safe category:

### CAPACITY_REJECTION

Examples:

- insufficient free capital under that account's risk budget;
- max open positions reached;
- symbol/account exposure limit reached;
- required notional is too large relative to executable liquidity;
- expected market impact/slippage exceeds policy;
- account-specific exchange/min-order constraint.

This category should be implemented first because the strategy itself still
accepts the candidate; only the account cannot execute it appropriately.

Later category:

### PORTFOLIO_PRIORITY_REJECTION

Examples:

- Senior capital is reserved for stronger simultaneously active candidates;
- candidate ranks below other accepted opportunities;
- portfolio diversification/correlation policy makes Senior skip it.

This MUST NOT be implemented until ranking/edge statistics are mature enough to
justify the comparison. A heuristic "less promising" label is insufficient.

---

## LIQUIDITY / SCALE MODEL

A large account must not assume that a strategy scales linearly.

Allocator may eventually evaluate:

- required position notional;
- top-of-book and depth within bounded slippage;
- expected slippage;
- maximum participation relative to observed market depth/volume;
- number of entry legs;
- expected time-to-fill;
- free capital after existing reservations;
- account-level margin/exposure limits.

If Senior's desired position would materially degrade execution while Junior's
smaller notional remains inside policy, the candidate may be delegated to
Junior instead of forcing Senior to trade an oversized order.

The exact liquidity estimator and thresholds require a separate future decision
and real execution evidence.

---

## FAILURE / NETWORK PARTITION POLICY

Because Robots may run on different servers:

- allocator state must be durable and versioned;
- assignment commands must be idempotent;
- Robot acknowledgements must include assignment_version;
- retries must not create duplicate ownership;
- timeout is not evidence that the other Robot did nothing;
- allocator must reconcile durable assignment + account/order state before
  reassigning after uncertain delivery;
- no "best effort" fallback that lets both Robots trade the same candidate;
- allocator outage must stop new cross-account delegation, not existing
  per-account protection.

Existing open positions continue to be protected locally by their owning Robot
even if the allocator is unavailable.

---

## PHASED IMPLEMENTATION

### Phase A — observe only

- define account identities;
- compute hypothetical Senior/Junior routing;
- persist routing decision/reason;
- no execution delegation.

Goal:
measure how often capacity delegation would actually occur.

### Phase B — PAPER multi-account

- two separate PAPER accounts/databases/runtimes;
- durable allocator ownership;
- one candidate can execute on only one PAPER account;
- inject disconnect/restart/duplicate-delivery cases;
- verify fail-closed recovery.

### Phase C — micro-LIVE

- separate real accounts/API credentials;
- minimal capital;
- capacity-only delegation;
- no portfolio-quality ranking delegation yet.

### Phase D — portfolio-aware routing

Only after enough verified outcome statistics:

- candidate ranking;
- capital reservation;
- correlation/exposure policy;
- opportunity-cost routing;
- optional N-level hierarchy beyond Senior/Junior.

---

## ACCEPTANCE PRINCIPLES

Before LIVE cross-account routing:

- zero duplicate ownership in PAPER fault scenarios;
- restart/recovery proves the same owner deterministically;
- allocator outage does not compromise local position protection;
- Senior rejection reason is explicit and durable;
- Junior receives the identical immutable candidate/trade plan, except for
  account-specific executable quantity/rounding allowed by policy;
- account balance/risk limits are checked immediately before execution;
- no LIVE authority is inferred from allocator assignment alone.

---

## IMPLEMENTATION_STAGE

implementation_after:

- single-account Robot PAPER lifecycle is stable;
- current reconciliation/self-recovery blockers are closed;
- pattern/Geometry quality is sufficiently stable;
- PAPER strategy statistics justify continuing toward LIVE;
- single-account micro-LIVE execution behavior is understood.

recommended_stage:

Portfolio / Multi-Account Orchestration Layer

This feature must not pre-empt the current Robot reliability and Geometry queue.

---

## STATUS

architecture_direction:

APPROVED FOR FUTURE DESIGN

implementation:

NOT STARTED

# FEATURE_STATUS_SUMMARY

FEATURE-001:

Pattern Measured-Move Target Visualization

Status:

DEFERRED / APPROVED FOR FUTURE IMPLEMENTATION

FEATURE-002:

Geometry Review Bridge / Web Geometry Reviewer

Status:

DEFERRED / ARCHITECTURE DIRECTION APPROVED

FEATURE-003:

Signal Report Archive / GitHub Sync

Status:

PLANNED / ARCHITECTURE DIRECTION APPROVED

FEATURE-004:

Hierarchical Multi-Account Robot / Capacity-Aware Candidate Delegation

Status:

DEFERRED / ARCHITECTURE DIRECTION APPROVED

---

# END