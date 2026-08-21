# BybitScanner — Roadmap

Version:

4.35

Date:

2026-08-21

Document Type:

PROJECT_ROADMAP_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-ROADMAP-001

purpose:

Определяет стратегию развития
проекта BybitScanner,
архитектурные этапы,
приоритеты разработки,
развитие Trading Intelligence,
Project Sync Framework,
Architecture Intelligence,
State Intelligence
и автоматизацию сопровождения документации.

machine_readable:

true

parser_version:

1.0

---

# ROADMAP_IDENTITY

project:

BybitScanner

roadmap_type:

Architecture Driven Development Roadmap

roadmap_state:

Pipeline Architecture Consolidation

principle:

Architecture First

---

# MAIN_GOAL

Создание профессиональной
самоописывающейся инженерной системы.

Trading Intelligence:

Market Data

↓

Analyzer

↓

Geometry Understanding

↓

Geometry Calibration

↓

Validation

↓

Pattern Detection

↓

Confirmation

↓

Signal

↓

Reporting

↓

Automation

Project Intelligence:

Code

↓

Architecture

↓

Project Sync Framework

↓

Documentation Intelligence

↓

State Intelligence

↓

Knowledge System

---

# CURRENT_ARCHITECTURE_DIRECTION

current_focus:

Scanner Geometry / Targeted Runtime Reliability

current_state:

Performance Architecture Audit completed.

Architecture verdict:

HEALTHY_WITH_TARGETED_BOTTLENECKS

current_transition:

От:

Structural audit findings

К:

Measured, minimal and regression-tested improvements

---

# PROJECT_SYNC_DEVELOPMENT

## STAGE-13

id:

SYNC-STAGE-001

name:

Project Synchronization Automation

status:

COMPLETED

implemented:

* registry_generation;
* validation_pipeline;
* dependency_analysis;
* impact_analysis;
* synchronization_planning;
* report_generation.

result:

Project Sync Framework создан
как управляющий слой проекта.

---

## STAGE-16

id:

SYNC-INTELLIGENCE-STAGE-001

name:

Documentation Intelligence Layer

status:

ACTIVE

implemented:

* Document Dependency Intelligence;
* Documentation Impact Analysis;
* Synchronization Recommendations;
* Change Detection Engine;
* Migration Planning;
* Migration Reporting;
* Migration Decision Control.

current:

Integration of controlled
documentation synchronization.

---

## STAGE-17

id:

STATE-INTELLIGENCE-STAGE-001

name:

State Intelligence Layer

status:

ACTIVE

implemented:

* State Analyzer;
* State Package Analysis;
* State Synchronization Monitoring.

purpose:

Контроль согласованности:

PROJECT_STATE

↓

STATE_* Documents

↓

Project Components

---

## STAGE-18

id:

DOC-AUTOMATION-STAGE-001

name:

Documentation Automation Engine

status:

ACTIVE DEVELOPMENT

implemented:

* Migration Planner;
* Migration Report;
* Migration Decision Handler;
* Approval Controller;
* Document Update Engine;
* Migration Executor.

current:

Интеграция полного
цикла автоматического
обновления документации.

remaining:

* Post Migration Validation;
* State Package Synchronization;
* Extended Document Intelligence.

---

## STAGE-19

id:

PIPELINE-ENGINE-STAGE-001

name:

Project Sync Pipeline Engine

status:

ACTIVE DEVELOPMENT

implemented:

* Pipeline Registry;
* Pipeline Stage;
* Pipeline Executor;
* Pipeline Context;
* Pipeline Result;
* Project Sync Runner;
* Migration Stage;
* Stage Adapter;
* Migration Integration;
* Approval Integration;
* Document Update Integration.

current:

Консолидация исполнительной архитектуры
Pipeline Engine.

---

# PIPELINE_ENGINE_STATE

status:

ACTIVE DEVELOPMENT

architecture_state:

TRANSITION

current_state:

Сформировано ядро Pipeline Engine.

Выявлено архитектурное
дублирование между:

* ProjectSyncPipeline;
* Project Sync Runner;
* PipelineRegistry;
* PIPELINE_STEPS.

architectural_goal:

Registry становится
единственным источником истины
для состава Pipeline.

target_execution_flow:

PipelineRegistry

↓

PipelineExecutor

↓

PipelineContext

↓

PipelineResult

↓

PipelineReport

---

## PIPELINE-001

name:

Pipeline Consolidation

status:

ACTIVE

goal:

Удаление дублирования
исполнительной логики.

tasks:

* отказаться от PIPELINE_STEPS;
* перевести Runner на PipelineRegistry;
* выполнять стадии через PipelineExecutor;
* исключить двойную регистрацию Stage.

---

## PIPELINE-002

name:

Registry Standardization

status:

ACTIVE

tasks:

* единый Stage Contract;
* единый механизм регистрации;
* единый механизм создания Stage;
* единый источник списка Pipeline Stage.

---

## PIPELINE-003

name:

Execution Flow Refactoring

status:

PLANNED

tasks:

* отказаться от смешанной модели выполнения;
* минимизировать использование subprocess;
* передавать состояние через PipelineContext;
* унифицировать PipelineResult.

---

## PIPELINE-004

name:

Pipeline Reporting

status:

PLANNED

tasks:

* единый Pipeline Report;
* единый формат ошибок;
* единый формат Stage Result;
* единый механизм агрегации результатов.

---

# MIGRATION_CONTROL_SYSTEM

status:

ACTIVE

components:

* Migration Planner;
* Migration Report;
* Migration Decision Handler;
* Approval Controller;
* Document Update Engine;
* Migration Executor.

current_state:

System способен:

* определить необходимость миграции;
* сформировать Migration Plan;
* создать Migration Report;
* контролировать Approval State;
* создать резервные копии;
* выполнить подтверждённые операции;
* создать Execution Report.

---

# TRADING_INTELLIGENCE_DEVELOPMENT

Pipeline:

Market Data

↓

Analyzer

↓

Geometry Engine

↓

Validation Engine

↓

Pattern Detection

↓

Confirmation Engine

↓

Signal Layer

↓

Reporting Layer

↓

Automation Layer

---

# DEVELOPMENT_PRIORITY

priority_order:

1.

Restore explicit Signal admission

2.

Gate chart/report side effects and isolate failures

3.

Correct Telegram delivery-state semantics

4.

Instrument Geometry performance before optimization

5.

Harden signal-history persistence

6.

Harden startup market-data failure handling

7.

Evaluate bounded market-data concurrency

8.

Decouple notification latency if measurements justify it

---

# CURRENT_OBJECTIVE

Текущий приоритет:

SCANNER_GEOMETRY

активные задачи:

* сохранить качество Geometry/Wedge;
* восстановить явный Signal admission;
* устранить доказанные runtime bottlenecks
  минимальными целевыми изменениями;
* измерить Geometry до её оптимизации.

следующий этап:

Signal admission contract verification

долгосрочная цель:

Acceptable Scanner Operation

---

# TARGETED_PERFORMANCE_IMPLEMENTATION_PLAN

Status:

APPROVED / NOT_STARTED

Source:

Performance Architecture Audit 2026-08-17

Audit conclusion:

* CRITICAL findings: NONE;
* unbounded in-process scanner memory leak: NOT_DEMONSTRATED;
* architecture: HEALTHY_WITH_TARGETED_BOTTLENECKS;
* major redesign: NOT_REQUIRED;
* full scanner asyncio conversion: NOT_JUSTIFIED.

## PRIORITY_1_SIGNAL_ADMISSION

Status:

IMPLEMENTED_VERIFIED

Objective:

Восстановить одно явное production-решение
о допуске Signal.

Contract authority:

DOCUMENTS/PROJECT_CONTRACTS.md / CONTRACT-SIGNAL-001

Current mismatch authority:

DOCUMENTS/PROJECT_STATE.md / PERFORMANCE_ARCHITECTURE_AUDIT_STATE

Approved implementation scope:

* `signal/filter.py`;
* `analyzer/core.py`;
* `main.py`;
* focused isolated Signal admission regression tests.

Scope rule:

NO_EXPANSION_WITHOUT_NEW_EVIDENCE

Acceptance / regression requirements:

* canonical `Elite Setup` admission;
* legacy-compatible `A+ Setup` admission;
* A / B / Watch / Invalid boundaries under the current Signal contract;
* `score == MIN_SCORE` boundary;
* `score < MIN_SCORE` rejection;
* Hunter mode;
* Sniper mode;
* confirmation boundary;
* approved signal reaches normal persistence and notification;
* rejected signal is suppressed from normal persistence;
* rejected signal is suppressed from normal Telegram;
* diagnostic mode, when used, does not change `approved` and does not persist a rejected signal;
* existing Signal/event tests do not regress.

Acceptance status:

FOCUSED_VERIFICATION_SATISFIED_WITH_NON_BLOCKING_FOLLOW_UPS

Verification evidence:

* 9 focused Signal admission tests — OK;
* artifact-free compile — PASS;
* scoped diff-check — PASS.
* legacy script-style Signal/event files — compile PASS, execution deferred because of persistence/Telegram side effects.

Follow-up verification:

* do not automatically delete or migrate historical unapproved persistence;
* after admission restoration, verify its effect on `NEW` / `STRENGTHENING`.
* replace unsafe script-style Signal/event tests with isolated regression tests;
* improve rejected diagnostic visibility in Telegram formatter;
* consider neutral Hunter approval reason wording — LOW.

## PRIORITY_2_CHART_REPORT_SIDE_EFFECTS

Objective:

Не создавать production chart/report
для результатов, которые будут отброшены.

Planned result:

* diagnostic output только по явной configuration;
* chart/report failures изолированы
  от успешного analytical result;
* Matplotlib figures закрываются
  также на exception paths;
* Geometry/Wedge detection behavior не меняется.

## PRIORITY_3_TELEGRAM_DELIVERY_STATE

Objective:

Исправить notification delivery semantics.

Planned result:

* analytical/history state отделён
  от notification delivery state;
* HTTP и Telegram success проверяются явно;
* delivered state устанавливается
  только после успешной доставки;
* failed/pending delivery сохраняется
  для безопасного retry;
* duplicate notifications предотвращаются.

Classification:

RELIABILITY_CORRECTION / NOT_ASYNC_REFACTOR

## PRIORITY_4_GEOMETRY_INSTRUMENTATION

Rule:

DO_NOT_OPTIMIZE_GEOMETRY_BLINDLY

Required measurements:

* raw upper candidate count;
* raw lower candidate count;
* filtered upper candidate count;
* filtered lower candidate count;
* candidate pair count;
* rejection counts by important gate;
* expensive envelope/candle evaluation count;
* candidate generation elapsed time;
* pair evaluation elapsed time;
* Geometry elapsed time per symbol.

Optimization gate:

Только после измерений разрешается
оценивать cheap pair preconditions,
early gates и row-access optimization.

Protected boundaries:

* Geometry detection quality;
* GeometryModel;
* Geometry → Wedge contract.

## PRIORITY_5_SIGNAL_HISTORY_PERSISTENCE

Planned result:

* сокращены лишние full reload/rewrite cycles,
  где это практически оправдано;
* persistence crash-safe и atomic;
* known-corrupt history не заменяется
  молча пустым history;
* текущая signal-history semantics сохраняется,
  если отдельно не утверждено иное.

## PRIORITY_6_STARTUP_MARKET_DATA_FAILURES

Planned result:

* symbol-discovery failure отделён
  от legitimate empty result;
* transient startup failure не выдаётся
  как успешный zero-symbol scan;
* retry/backoff ограничен и контролируем.

## PRIORITY_7_BOUNDED_MARKET_DATA_CONCURRENCY

Status:

DEFERRED_UNTIL_MEASURED

Evaluation scope:

* candle fetching only;
* conservative worker limit;
* Bybit rate-limit and retry compliance;
* deterministic per-symbol analysis
  сохраняется там, где это полезно;
* сначала оценивается small thread pool
  или narrowly asynchronous HTTP layer.

Forbidden:

END_TO_END_ASYNCIO_CONVERSION

## PRIORITY_8_NOTIFICATION_LATENCY

Status:

DEFERRED_UNTIL_DELIVERY_CORRECTNESS_AND_MEASUREMENT

Evaluation scope:

* small bounded notification worker/queue;
* limited concurrency;
* explicit backpressure;
* Telegram rate-limit handling.

Forbidden:

UNBOUNDED_FIRE_AND_FORGET_TASKS

# PERFORMANCE_NON_GOALS

Не входят в утверждённый performance refactor:

* GeometryModel rewrite;
* Geometry → Wedge contract rewrite;
* pivot detection architecture rewrite;
* Wedge classification/scoring architecture rewrite;
* confirmation architecture rewrite;
* pandas candle representation replacement
  для текущих bounded 200-row frames;
* complete scanner asyncio conversion;
* Project Sync / migration architecture changes;
* объединение charting, Telegram,
  Signal и Geometry в одну subsystem;
* broad parallelization всего
  `analyze_symbol()` при наличии
  Matplotlib и shared persistence.

# PERFORMANCE_DEFERRED_OPTIONAL

Deferred findings:

* explicit requests.Session reuse for Telegram;
* production Geometry debug-output reduction,
  если profiling не покажет material impact;
* review-queue retention policy.

Review queue rule:

Training/reference data сохраняются.
Automatic deletion запрещено
без отдельно утверждённой retention policy.

# PERFORMANCE_IMPLEMENTATION_PRINCIPLES

1. Correctness before throughput.
2. Measure before optimizing Geometry.
3. Minimal targeted fixes before architectural rewrites.
4. Preserve working analytical contracts.
5. Separate I/O concurrency from CPU-bound analysis.
6. Regression-test scanner behavior and Geometry quality.
7. Do not change pattern-detection thresholds for speed.
8. Do not sacrifice candidate quality or known valid Geometry examples without explicit evidence and approval.

---

# CR-DOC-AI-CONTEXT-001

Title:

Documentation and AI Context Workflow Modernization

Lifecycle state:

MISSION_CLOSED / MISSION_CLOSE_COMPLETED

Implementation status:

IMPLEMENTED_VERIFIED / CLOSED

Objective:

Introduce `TASK -> SPEC -> CONTEXT -> IMPLEMENT -> VERIFY -> RECORD` with compact task-scoped recovery,
durable ChangeRequests for substantial work, disposable ContextDumps and enforceable LegacyWarnings.

Approved scope:

* authoritative documentation and compact tracked `AGENTS.md`;
* ChangeRequest, ContextDump and LegacyWarning contracts/infrastructure;
* narrow read-only context generation and validation;
* staged recovery, authority reconciliation and Codex CLI workflow integration;
* focused tests and measured context-budget verification.

Non-goals:

* production scanner or analytical behavior changes;
* redesign of the complete Project Sync pipeline;
* permanent ChangeRequests for trivial work;
* ContextDump as authority or permanent history;
* automatic deletion of legacy artifacts;
* GitHub templates before the local workflow is stable;
* broad documentation rewrite or PROJECT_TREE redesign in Phase 0.

Migration phases:

0. Recovery checkpoint — COMPLETED.
1. Canonical agent entry and authority reconciliation — IMPLEMENTED_VERIFIED.
2. ChangeRequest and LegacyWarning schema/storage/validation — IMPLEMENTED_VERIFIED.
3. Minimal ContextDump generator targeting ignored `runtime/context/` — IMPLEMENTED_VERIFIED.
4. Staleness and scoped LegacyWarning enforcement — IMPLEMENTED_VERIFIED.
5. Codex workflow integration — IMPLEMENTED_VERIFIED.
6. Measured context-cost reduction and safe documentation deduplication — IMPLEMENTED_VERIFIED.

Acceptance criteria:

* tracked compact `AGENTS.md` becomes the routine entry point;
* local checkout precedence and Git/GitHub responsibilities are deterministic;
* substantial and lightweight task tiers are supported without unnecessary bureaucracy;
* ContextDump is reproducible, scoped, non-authoritative, ignored by default and stale-detectable;
* blocking LegacyWarnings fail machine validation and block agent workflow;
* routine ContextDump generation does not run the full Project Sync migration pipeline;
* interruption recovery works from repository state alone at every lifecycle stage;
* Git owns detailed implementation history without parallel duplication;
* approved initial context-budget targets are demonstrated while deep recovery remains available;
* production scanner behavior and existing analytical contracts remain unchanged.

Rollback and commit boundary:

Each phase requires scoped verification and a separate revertible commit.
Phase 0 is documentation-only and does not authorize later implementation.

Current next phase:

NONE

Post-mission routing:

SCANNER_GEOMETRY_TASK_SELECTION — NOT_STARTED / NOT_AUTHORIZED

Phase 0 through Phase 6 and mission close are complete. Final outcome is owned by ChangeRequest revision 1.9.
Detailed implementation history is owned by Git.

---

# CR-SCANNER-GEOMETRY-001

Title:

Consolidate Directional Envelope Ownership in Wedge Layer

Status:

MISSION_CLOSED / MISSION_CLOSE_COMPLETED / IMPLEMENTED_VERIFIED

Planned scope:

* keep Geometry raw metrics and ranking direction-neutral;
* remove premature opposite-side directional interpretation from `geometry/evaluation.py`;
* apply STRICT/EXCURSION semantics in Wedge after operational pattern determination;
* reuse existing envelope metrics and add focused directional regression coverage.

Acceptance and risks:

Owned by `DOCUMENTS/CHANGE_REQUESTS/CR-SCANNER-GEOMETRY-001.md` revision 1.4.

Next action:

SCANNER_GEOMETRY_TASK_SELECTION. No next implementation task is selected or authorized.

---

# CR-TRADING-INTELLIGENCE-001

Title:

Trading Intelligence and Paper Trader Roadmap Research

Governance type:

DURABLE_PLANNING_RESEARCH_CHANGE_REQUEST

Status:

IN_PROGRESS / CONTEXT / RESEARCH_ACTIVE

Implementation status:

IMPLEMENTATION_NOT_STARTED_NOT_AUTHORIZED

Roadmap status:

HYPOTHESIS_NOT_FINAL / ADDITIONAL_RESEARCH_REQUIRED

Objective:

Prepare an evidence-based, dependency-aware proposed roadmap from the current Scanner to broader
Trading Intelligence and an event-driven Paper Trader while preserving approved human decisions,
open questions, performance constraints and the normalized boundary between analytics and execution.

Planning tracks:

* Track A — Scanner / Trading Intelligence: Wedge refinement, Flag, HS/IHS, Double Top/Bottom,
  Candlestick Formation Evidence, common PatternObservation and pre-breakout corridor setups;
* Track B — Trading Foundation: normalized contracts, instrument precision, clock/time semantics,
  strategy/risk, order/fill/position/account, ExecutionPort, PaperExecution, fees/PnL/margin and recovery;
* Track C — Market Microstructure / Simulation: Bybit public trades, full L2 incremental local book,
  selective active-symbol subscriptions, LiquidityObservation, liquidity-aware management and later replay.

Approved product boundaries:

* new pattern families are not automatically placed in wedge/;
* candlestick formations initially provide evidence/confirmation/context rather than a primary engine;
* mild LONG preference belongs to later Strategy/Decision policy and does not alter detector validity or Geometry score;
* PRE_BREAKOUT_CORRIDOR_SETUP and BREAKOUT_SETUP remain distinct setup types;
* Paper Trader v1 uses ONE_WAY, ISOLATED, USDT_ONLY, one open position per symbol and NO_SCALE_IN policies;
* new entries use CLOSED candles and preserve distinct source, signal, order and fill times;
* realtime execution and position management are event-driven over public trades and full L2 order-book data;
* PaperExecution and later LiveBybitExecution share normalized Strategy/Risk and ExecutionPort contracts;
* hot/cold path separation and measured CPU/RAM/network budgets protect Scanner throughput.

Research required before roadmap approval:

* detector-family and PatternObservation contracts;
* corridor maturity, confidence, entry, target, SL, invalidation, risk and apex limits;
* exact LONG bias measurement and candlestick taxonomy, including canonical meaning of «Восходящая звезда»;
* order/fill/account/risk/persistence/reconciliation and replay semantics;
* dynamic target-corridor book depth and selective subscription strategy;
* tape-aware liquidity-barrier evidence and position-management policy;
* comparison of high-quality open-source architectures without blind copying;
* performance budgets, profiling and benchmark gates.

Microstructure research checkpoint:

SUFFICIENT_FOR_ROADMAP_LEVEL_DESIGN / IMPLEMENTATION_SPEC_NOT_READY.

Recorded roadmap-level findings:

* Paper Trader remains event-driven over separate, correlatable public-trade and public-L2 streams;
* public L2 is the v1 baseline for aggregated price-level liquidity, not L3/MBO identity or exact queue reconstruction;
* LocalOrderBook follows snapshot plus validated incremental delta and explicit resnapshot/recovery semantics;
* adaptive depth follows `MINIMUM_DEPTH_THAT_COVERS_TRADE_HORIZON` rather than a universal fixed level count;
* deep processing is lifecycle-activated for `SYMBOL_IN_PLAY`, approved setups and open positions, then cooled down and downgraded;
* hot-path delta application and cheap aggregates remain separate from coalesced LiquidityObservation and heavy analysis;
* initial evidence families are clustered/relative liquidity, multi-window imbalance, persistence, consumption,
  pull/migration, replenishment/absorption and price response relative to aggressive flow;
* LiquidityEngine publishes observations but does not directly execute position changes;
* v1 market simulation walks executable L2 levels into fills/VWAP while retaining explicit latency and concurrency limitations;
* realistic limit-order fills remain later work pending an explicitly documented queue approximation;
* performance budgets are required before broad deep-monitoring activation.

Microstructure items remaining open:

* exact schemas, formulas, thresholds, buckets, windows and lifecycle transitions;
* Bybit gap detection, resnapshot and recovery details;
* SYMBOL_IN_PLAY activation/cooldown policy and adaptive-depth algorithm;
* market-fill latency, concurrency haircut and insufficient-liquidity policy;
* future limit queue approximation;
* measurable network, message-rate, CPU, RAM and latency budgets.

HS / IHS research checkpoint:

COMPLETED / SUFFICIENT_FOR_ROADMAP_LEVEL_DESIGN / IMPLEMENTATION_NOT_STARTED_NOT_AUTHORIZED.
The family uses mirrored five-pivot `LS — N1 — HEAD — N2 — RS` geometry and an N1/N2 neckline that
may be horizontal, rising or falling. Hard geometry is separated from quality, context, confirmation
and admission; perfect shoulder symmetry, prior trend and volume are not hard pivot-geometry gates.
The conceptual lifecycle supports FORMING before Right Shoulder or breakout confirmation, then
STRUCTURALLY_VALID, CONFIRMED or INVALIDATED. Thresholds remain open for Bybit perpetual calibration;
profitability requires later historical and Paper Trader evidence.

Geometry research observation:

GRVTUSDT suggests future validation of robust wick-aware Wedge boundary fitting. Candidate objectives
include meaningful touches/near-touches, distance and violation magnitude, limited outliers, and
structure-scale or volatility-normalized tolerance for upper high-wicks and mirrored lower low-wicks.
This is an unproven research hypothesis, not an algorithm change or implementation authorization.

## FUTURE_MISSION_ANCHOR_QUALITY_LEARNING

Mission ID:

ANCHOR_QUALITY_LEARNING

Working title:

Historical Anchor Quality Learning

Domain:

Scanner / Geometry Engine

Status:

FUTURE_RESEARCH_MISSION_RECORDED / NOT_SELECTED / NOT_STARTED / NOT_AUTHORIZED

Authority classification:

ROADMAP_BACKLOG_RESEARCH_DIRECTION / NO_IMPLEMENTATION_CONTRACT

Problem:

One pattern episode may admit several formally serious geometric variants with different historical
Anchor/START pivots. Current geometry may not have enough evidence to rank which plausible historical
pivot is the best structural start. Choosing an earlier or later anchor changes base height, structural
duration, geometry and expected potential even when several candidates appear visually and formally valid.

Goal:

Research a future historical self-calibration and ranking mechanism that learns from completed pattern
episodes and gives better Anchor/START candidates a measured prior during later live detection. This is
not authorization for ML, a model, a dataset schema or any Geometry Engine production change.

Live-time evidence invariant:

* live detection uses only candles and evidence available at the detection timestamp;
* several serious Anchor Candidates may be retained with their immutable detection-time geometry,
  features and scores;
* the candidate selected by the historical live decision is retained explicitly;
* future candles and outcome fields never enter the live feature set;
* hindsight evaluation never rewrites or relabels the historical live decision as if future information
  had been available then.

Post-outcome research direction:

After a pattern episode is resolved, a separately defined Pattern Outcome may describe what the structure
actually did. Historical candidates from that same episode may then be compared and assigned hindsight
Anchor Quality evidence. That evidence may train or calibrate ranking only for future pattern episodes.
Outcome evaluation and training evidence must remain reproducible, versioned and separated from immutable
features-at-detection-time.

Look-ahead leakage prohibition:

LOOK_AHEAD_LEAKAGE_FORBIDDEN. Future candles, realized outcome and hindsight labels must never change a
historical live decision retroactively and must never be included in the feature set presented to live
detection. Dataset construction, feature provenance and evaluation splits must demonstrate this boundary.

Potential / pattern-height hypothesis:

The realized magnitude of a completed pattern may be one important hindsight feature for judging whether
the assumed base height or start scale of an Anchor Candidate corresponded to the structure that actually
resolved. A research metric may examine a relation conceptually similar to:

```text
potential_error = abs(expected_potential - realized_move) / realized_move
```

This formula is not approved. Realized potential must not be the sole criterion, edge cases such as zero
or ambiguous realized move require methodology, and definitions, normalization, windows and thresholds
must be researched before any implementation decision.

Anchor Quality versus trade result:

Geometric or structural Anchor correctness is distinct from trade usefulness and realized trading outcome.
A structurally sound pattern need not reach its full target. An unfavorable trade result alone does not
prove that its anchor was geometrically wrong, and a favorable result alone does not prove that an anchor
was structurally best.

Possible hindsight features:

The following are research candidates, not an approved formula:

* correspondence between pattern height / expected potential and realized move;
* quality and number of boundary touches;
* boundary violations and their magnitude;
* compression quality;
* pivot significance;
* structural duration;
* geometry stability as new candles became available;
* symmetry or asymmetry where applicable;
* start location relative to a meaningful impulse or extreme;
* other existing Scanner geometry features whose live-time provenance can be demonstrated.

Candidate-ranking direction:

The future evidence design must not retain only the winner. It should support several candidates from one
episode and comparable evaluations, conceptually for example `Anchor A = 0.91`, `Anchor B = 0.66` and
`Anchor C = 0.38`. A later live-ranking hypothesis may combine:

```text
base_geometry_score + learned_anchor_prior
```

No formula or weight is approved. A learned prior must not override hard geometry validity constraints
without control, and disabling the prior must reproduce baseline geometry behavior.

Conceptual durable entities:

Future architecture research may evaluate entities equivalent to:

* `AnchorCandidateSnapshot`;
* `PatternOutcome`;
* `AnchorEvaluation`;
* `AnchorPreferenceModel`.

These names are conceptual and are not implementation contracts. Research must define immutable
detection-time fields, outcome fields, versioning, retention, reproducibility, leakage prevention,
dataset-quality controls, and the relationship between manual labels and automatically derived labels.

Existing manual Anchor/START review:

The existing Scanner Anchor/START review workflow may later provide high-quality supervision or evaluation
evidence. A manual click is not automatically absolute ground truth; reviewer identity, context, agreement,
label intent and methodology require separate treatment before labels are used for training or scoring.

Reference cases:

The user provided two visual examples of alternative Anchor/START markup for one class of wedge/converging
structure. The recorded meaning is limited to the following: several anchors may look visually and formally
plausible; an earlier anchor changes base height, duration and expected potential; a later anchor produces
a different geometry and scale; and historical outcome should eventually support comparison of those
candidates. No additional image content is inferred.

If separately authorized after symbol and case identity are verified, the existing durable reference layout
should be used rather than a new store:

```text
training/reference_patterns/<SYMBOL>/<CASE_ID>/
```

A candidate stable case ID may follow `anchor-quality-<timeframe>-<date>-<sequence>`, with exact original
source images preserved under manifest control and an `annotation.json` describing candidate relationships.
No image is copied, generated or registered by this roadmap record.

Future acceptance direction:

Any later approved mission must demonstrate at minimum:

* no look-ahead information in live detection or its feature set;
* reproducible historical outcome evaluation;
* deterministic candidate snapshots;
* comparison of multiple anchors from the same pattern episode;
* measurable anchor-ranking improvement on holdout history;
* no degradation of hard geometry validity;
* focused and regression tests;
* an off switch that reproduces baseline geometry behavior without the learned prior.

Unresolved research questions:

* What defines one pattern episode and its candidate-comparison set?
* When and by which deterministic rules is a Pattern Outcome considered resolved?
* How are expected potential, realized move, censoring and ambiguous outcomes defined?
* Which Anchor Quality components measure structural correctness versus trade usefulness?
* How are candidate snapshots versioned when geometry algorithms evolve?
* What dataset retention, class balance, split, holdout and leakage controls are required?
* How are manual review labels weighted, audited and reconciled with automatic evidence?
* Which model family, calibration method or non-ML ranking method is justified by evidence?
* How large must improvement be, and on which metrics, before a learned prior may affect live ranking?

Scope separation and routing:

`ANCHOR_QUALITY_LEARNING` is a separate future Scanner / Geometry mission. It is not part of Manual Live
Trading Terminal, Trading Workspace, Robot execution or the Bybit trading backend. Recording it does not
select the mission, create an implementation-authorized ChangeRequest, start CONTEXT or IMPLEMENT, or alter
any Geometry production behavior. Current primary work remains `TRADING WORKSPACE v1 — CONTEXT / RESEARCH`
with `CR-TRADING-WORKSPACE-001` still IN_PROGRESS and IMPLEMENT not started or authorized.

Deferred detector research:

Double Top/Bottom, Candlestick Formation Evidence and PRE_BREAKOUT_CORRIDOR_SETUP.

Track D — Trading Workspace / Telegram Mini App:

Normalized operator-control surface for Scanner, Paper, later Demo/Live, manual control, robot
observability, chart layers, positions and history. It consumes normalized state and never detector
internals. Before a UI MVP, Track B defines trade-domain identity/lifecycle, ExecutionPort, persistent
journal, idempotent commands, manual override, re-entry locks and reconciliation/restart safety.

Dependency hypothesis:

Tracks A, B and C may develop in parallel but join only through normalized contracts. Paper Trader
starts behind PatternObservation and normalized TradingSignal; execution simulation follows domain
order/fill contracts and does not depend directly on Wedge, Telegram or scanner signal-memory formats.

Track D sequence is requirements/gap checkpoint; domain contracts; Paper plus journal;
reconciliation/recovery; chart-engine comparison/prototype; Telegram Paper MVP; verified Demo; then
separately authorized Live. This supersedes hypotheses that place safety foundations after UI work.

Chart-engine decision checkpoint:

RESEARCH_IN_PROGRESS / PREFERRED_DIRECTION_IDENTIFIED / IMPLEMENTATION_DECISION_NOT_FINALIZED.
Repository-reconciled Trading Workspace CONTEXT research identifies KLineChart as the preferred v1
interactive renderer behind a shared renderer-neutral Chart Contract/Adapter. Static Matplotlib/mplfinance
remains the Scanner report path. Dependency approval, version choice and implementation remain open and
require later feasibility/prototype and implementation-plan review.

Acceptance, risks, approved decisions and unresolved decisions:

Owned by `DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-INTELLIGENCE-001.md` revision 1.5.

Active development focus:

TRADING_TERMINAL / TRADING_WORKSPACE.

Current action:

DEFINE_SEPARATE_DURABLE_TRADING_TERMINAL_CHANGE_REQUEST. Future scope may include Workspace, Paper
Trader, real Bybit market data, order/position lifecycle, virtual balance/equity, fees/slippage, TP/SL,
chart trading and overlays, persistence/journal, Telegram Mini App access and preparation for robot
execution. No terminal implementation is started or authorized by this checkpoint.

Implementation authorization:

NONE. No production or test implementation may begin from this planning entry.

---

# CR-TRADING-WORKSPACE-001

Title:

Trading Workspace v1 / Manual Live Trading

Status:

IN_PROGRESS / MANUAL_EXECUTION_PROTECTION_IMPLEMENT_PLAN_RECORDED

Implementation status:

NOT_STARTED_NOT_AUTHORIZED

Current checkpoint:

MANUAL_EXECUTION_PROTECTION_IMPLEMENT_PLAN_RECORDED

First implementation priority:

Usable manual live trading on the user's real Bybit account. Terminal is independent from Scanner and
Robot, works while Scanner is stopped, starts locally and preserves a deployment-neutral path to VPS.
Paper-first and autonomous Robot implementation are not the v1 priority.

Specification boundary:

* durable Telegram signal deep links and SignalSnapshot history;
* shared Terminal/Signal Editor chart engine;
* explicit historical signal versus current market presentation;
* Working Volume equal to 5% of own equity before leverage;
* leverage-independent WV sizing and one-decimal display-only engaged-WV indicator;
* exchange-confirmed market, Limit, SL/TP, fill, cancel, modification and full-close cleanup lifecycles;
* Bybit reconciliation before active/closed success presentation;
* chart overlays, fill markers and confirmed-event feedback;
* future MANUAL/ROBOT ownership compatibility without robot implementation.
* exclusive MANUAL/ROBOT controller authority, future AUTOPILOT handoff and reconciled human takeover;
* independent MANUAL and AUTOPILOT active-position groups and ownership-scoped Close All operations.
* interactive Working Volume details without using rounded display as accounting truth;
* AUTOPILOT DAY/WEEK/MONTH/YEAR results with realized PnL, account and open-exposure metrics;
* interactive pattern plus entry-reason profitable/losing breakdowns;
* restart-durable closed-trade analytics with immutable provenance and ownership history.
* unified Scanner bot Menu routing to Terminal, Trading Results, AUTOPILOT and Run Scanner;
* independent Manual Terminal entry without SignalSnapshot while retaining signal deep links;
* authorization-aware Scanner Control with duplicate-run prevention and lifecycle feedback.
* named Bybit trading-account profiles, active-account display, isolated account state and reconciled switching;
* account-scoped leverage-independent WV calculated as five percent and rounded down to the nearest 10 USDT;
* future Robot aggregate exposure capped at 19 WV per account without including MANUAL exposure;
* account-aware DAY/WEEK/MONTH/YEAR realized PnL in USDT and percentage with cash-flow semantics deferred;
* Terminal-backend credential custody with API Secret excluded from frontend, Scanner, chart and Telegram state.

Owning record:

`DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md` revision 1.13.

Current action:

MANUAL_EXECUTION_PROTECTION_IMPLEMENT_PLAN_COMPLETE_IMPLEMENT_NOT_AUTHORIZED_REVISION_1_13.

Approved intermediate CONTEXT architecture directions from revision 1.5:

* Bybit V5 authenticated REST plus private order/execution/position/wallet events, with reconciliation
  for startup, reconnect, uncertain commands and full-close invariants;
* backend-validated Telegram Mini App initData, freshness and numeric-user allowlist;
* immutable versioned SignalSnapshot separated from trading state and detector runtime;
* KLineChart behind a shared chart adapter, with Matplotlib/mplfinance retained for static reports;
* Python/FastAPI REST plus backend WebSocket boundary and SQLite/WAL journal plus projections;
* reconciliation-gated trading, account-isolated state and replaceable CredentialStore;
* cash-flow-adjusted return direction, single-flight Scanner Control and deployment-neutral HTTPS ingress.

Human-approved intermediate revision 1.6 refinements, superseded where revision 1.8 binds a later decision:

* position-mode-aware USDT Linear Perpetual scope with preferred Hedge Mode and explicit side/positionIdx;
* ACK-to-pending-to-event/reconciliation confirmation and execId-deduplicated fills;
* account/symbol/side position projections, reconciled close workflow and REST recovery sources;
* durable TradingCommand/orderLinkId correlation and no blind retry after uncertain exposure commands;
* preferred WV base of active-account USDT walletBalance without leverage or unrealized-PnL expansion;
* downward instrument qty normalization, pre-submit insufficient-volume rejection and visible tickSize price normalization;
* actual fractional WV derived from confirmed execution and reconciled position state.

Human-approved intermediate revision 1.7 execution/reconciliation model:

* acknowledgements are acceptance evidence, while immutable executions deduplicated by account/category/execId
  are the only fill evidence and cannot apply quantity, PnL, fee or WV effects twice;
* TradingCommand and unique orderLinkId are durable before submission, uncertain outcomes prohibit blind retry,
  and normalized order/position evidence never regresses stronger confirmed state;
* PositionKey is account/category/symbol/position_idx, position events are operational state rather than fills,
  and external origin is never silently claimed as Terminal origin or conflated with current controller;
* L1 command/order, L2 symbol/leg, L3 account and L4 startup/reconnect reconciliation converge through one
  execution-state owner with scope-appropriate new-exposure locks and a separate reduce-risk gate;
* crash/replay-safe atomic ingestion covers journal, execution deduplication, immutable execution, projections
  and reconciliation state, while Full Close converges only at zero plus required cleanup and final reconciliation;
* revision 1.8 resolves the previously open WV authority, binding position mode, external interaction, Manual
  takeover, emergency-close, negative-correlation, automatic mode-switching and external-order cleanup policies.

Human-approved intermediate revision 1.8 execution/risk decisions:

* active-account USDT walletBalance is the binding leverage-independent WV base, with existing five-percent
  calculation and downward tens-of-USDT rounding; totalAvailableBalance, totalEquity and non-USDT value are excluded;
* Manual v1 requires One-Way Mode and positionIdx zero, prohibits simultaneous opposite exposure and hidden
  reversal, and never switches Bybit position mode automatically;
* external exchange state is displayed, included in risk and reconciled/adopted without rewriting origin or
  sending compensating orders; OWNER takeover changes controller only after reconciliation;
* Emergency Close remains a separate auditable reduce-risk workflow with no blind retry and CLOSED_RECONCILED
  completion, while Full Close never silently cancels potentially dangerous external orders;
* negative lookup uses bounded repeated multi-source correlation, but exhausted horizon retains explicit
  unresolved state; exact refresh, timeout, interval, backoff and horizon parameters remain later work.

Human-approved intermediate revision 1.9 upper-workspace direction:

* the upper Manual Terminal workspace remains minimal with the primary live chart on the left and a narrow
  collapsible DOM plus execution-prints panel on the right; the existing trading controls remain below;
* DOM levels combine price, resting size and stable proportional depth fill, while aggressive executions use
  buyer/seller color, clamped volume sizing and bounded realtime history;
* a multi-level sweep ellipse is allowed only when sequenced L2 and trade evidence support the consumed range;
  ambiguous correlation falls back to a factual non-sweep print;
* one normalized market-data source is shared with active liquidity consumers, hidden rendering is suspended,
  and depth, scaling, batching, subscription lifecycle and mobile feasibility remain unresolved research.

Repository-confirmed boundary:

Current public OHLCV, final admission/count, outbound Telegram, signal evidence and static chart paths may
be reused behind normalized boundaries. Authenticated trading/private streams, SignalSnapshot persistence,
Terminal UI/backend, interactive charting, trading-domain state, reconciliation and journal are absent.

Next phase:

CONTEXT / RESEARCH — AUTHORIZED_IN_PROGRESS, INTERMEDIATE_CHECKPOINT_APPROVED_RECORDED, NOT_COMPLETE_OR_VERIFIED;
IMPLEMENT — NOT_STARTED_NOT_AUTHORIZED.

---

# ROADMAP_UPDATE_RULES

RULE-001:

Каждый завершённый Milestone
отражается в Roadmap.

RULE-002:

Изменение архитектуры требует
проверки связанных этапов.

RULE-003:

Новые подсистемы Project Sync
имеют отдельную запись.

RULE-004:

ROADMAP.md является частью
официальной архитектурной документации.

RULE-005:

Все изменения сохраняют
machine_readable формат.

RULE-006:

Pipeline Registry является
единственным источником
регистрации Pipeline Stage.

RULE-007:

Pipeline Executor является
единственным исполнительным
контуром Pipeline.

RULE-008:

Новые Stage не должны
дублироваться вручную
в Runner.

---

# VERSION_UPDATE_REASON

from:

ROADMAP v4.39

to:

ROADMAP v4.40

reason:

Current checkpoint — Manual execution/protection IMPLEMENT planning (v4.39 to v4.40):

* advanced `CR-TRADING-WORKSPACE-001` to revision 1.13 and checkpoint `MANUAL_EXECUTION_PROTECTION_IMPLEMENT_PLAN_RECORDED`;
* recorded modular Terminal boundaries, Bybit adapter responsibilities, explicit execution/connectivity states, persistence/recovery and DOM/chart projection contracts;
* decomposed the bounded implementation into nine reviewable stages with acceptance, rollback and a complete safety/regression test matrix;
* assessed the plan as ready for explicit human authorization after recorded pre-implementation gates, without authorizing or starting IMPLEMENT;
* preserved overall active incomplete CONTEXT, Robot out of scope and unauthorized IMPLEMENT.

Previous checkpoint preserved — Manual execution/protection CONTEXT completion (v4.38 to v4.39):

* advanced `CR-TRADING-WORKSPACE-001` to revision 1.12 and recorded checkpoint `MANUAL_EXECUTION_PROTECTION_CONTEXT_SUFFICIENT_FOR_IMPLEMENT_PLANNING`;
* completed fast-input versus uncertainty locks, degraded-state risk gates, Market/Limit reversal distinction and realtime reconciliation requirements;
* recorded origin-independent current-symbol ordinary-Limit cleanup after confirmed FLAT, without extending it to other symbols or conditional protection;
* recorded the final conceptual execution-state matrix and assessed this bounded CONTEXT block as sufficiently researched with no blocker before separately authorized IMPLEMENT planning;
* preserved overall active incomplete CONTEXT, Robot out of scope and unauthorized IMPLEMENT planning and IMPLEMENT.

Previous checkpoint preserved — Trading Workspace Manual Market / Limit / SL-TP execution and protection (v4.37 to v4.38):

* advanced `CR-TRADING-WORKSPACE-001` to revision 1.11 and recorded checkpoint `MANUAL_MARKET_LIMIT_SLTP_EXECUTION_PROTECTION_RECORDED`;
* recorded held-side fast DOM execution, quick-volume and anti-bounce semantics, fail-closed submission and distinct Market/Limit partial-fill behavior;
* recorded Market-to-FLAT behavior, the narrow Manual-Limit opposite-remainder exception, all-origin Limit visibility and confirmed DOM/chart order lifecycle;
* preserved Bybit authority, reconciliation locks, close cleanup with external-order safeguards and future-capable non-priority automatic preset SL/TP;
* preserved active incomplete CONTEXT, Robot out of scope and unauthorized IMPLEMENT.

Previous checkpoint preserved — Trading Workspace threshold-based DOM recenter policy (v4.36 to v4.37):

* advanced `CR-TRADING-WORKSPACE-001` to revision 1.10 and recorded checkpoint `MANUAL_LIVE_TRADING_V1_THRESHOLD_RECENTER_POLICY_RECORDED`;
* superseded only the approximately 23-second periodic timing with an approximately five-second configurable check that recenters only beyond a central-deviation threshold;
* preserved immediate CENTER, higher-priority STRONG-sweep follow, manual-inspection suppression and every other revision 1.9 DOM/prints decision;
* retained exact interval, deviation threshold, dead-zone, motion and inactivity behavior as prototype-tunable research;
* preserved active incomplete CONTEXT, Robot out of scope and unauthorized IMPLEMENT.

Previous checkpoint preserved — Trading Workspace upper workspace / DOM / prints direction (v4.35 to v4.36):

* advanced `CR-TRADING-WORKSPACE-001` to revision 1.9 and recorded the approved minimal upper-workspace composition;
* recorded the normalized public-market-data owner, confidence-gated sweep and resync semantics, reusable Manual book walk, compact position indication and Canvas2D-oriented bounded rendering direction;
* recorded non-binding DOM/print scaling and external license/provenance constraints without vendoring source;
* recorded a preferred 20+20 viewport over an `orderbook.50` working-depth candidate, configurable recenter, interaction-safe STRONG-sweep follow and optional deferred x10/x100 presentation compression;
* retained responsive/calculation depth, exact timing/animation, compression feasibility, gap/correlation/confidence rules, scaling windows, retention, lifecycle, vendoring, heatmap and mobile feasibility as later research;
* preserved active incomplete CONTEXT, Robot out of scope and unauthorized IMPLEMENT.

Previous checkpoint preserved — Trading Workspace human execution/risk decisions record (v4.34 to v4.35):

* advanced `CR-TRADING-WORKSPACE-001` to revision 1.8 and recorded the approved execution/risk decisions;
* bound walletBalance WV, One-Way Mode, reconcile-and-adopt external state, Manual takeover, Emergency Close, external-order-aware Full Close and conservative negative correlation;
* retained numeric refresh/cache/retry/backoff/search-horizon parameters as later configurable research/design work;
* preserved active incomplete CONTEXT, future-only Robot constraints and unauthorized IMPLEMENT.

Previous checkpoint preserved — Trading Workspace execution/reconciliation model record (v4.33 to v4.34):

* advanced `CR-TRADING-WORKSPACE-001` to revision 1.7 and recorded the formal execution/reconciliation model;
* retained REST/WS acknowledgements as non-fill evidence, immutable deduplicated executions, non-regressive order/position projections and external-origin separation;
* recorded L1-L4 reconciliation, scoped exposure gates, crash/replay atomicity and reconciled Full Close invariants;
* preserved the enumerated human decisions as unresolved, kept CONTEXT active and incomplete, and left IMPLEMENT not started or authorized.

Previous checkpoint preserved — ANCHOR_QUALITY_LEARNING future research mission record (v4.32 to v4.33):

* recorded historical multi-candidate Anchor/START quality learning as a future Scanner / Geometry mission;
* prohibited look-ahead leakage and separated immutable live evidence from hindsight outcome evaluation;
* recorded potential/height correspondence as an unapproved research feature rather than a formula;
* preserved hard geometry constraints, baseline behavior, manual-review uncertainty and holdout acceptance;
* retained Trading Workspace v1 CONTEXT / RESEARCH as current primary work without lifecycle change;
* did not authorize a ChangeRequest, CONTEXT, IMPLEMENT, ML work or production Geometry change.

Previous checkpoint preserved — CR-TRADING-INTELLIGENCE-001 microstructure research record (v4.22 to v4.23):

* recorded realtime L2/tape, incremental book, adaptive depth and selective activation conclusions;
* recorded LiquidityZone/LiquidityObservation evidence boundaries and market-execution simulation direction;
* classified microstructure research as sufficient for roadmap-level design while retaining implementation details as open;
* routed the next research focus to Trading Intelligence detector families;
* preserved the roadmap as non-final and kept ROADMAP_SPEC and IMPLEMENT unauthorized.

Previous checkpoint preserved — CR-TRADING-INTELLIGENCE-001 durable planning/research start (v4.21 to v4.22):

* added the non-final three-track roadmap hypothesis for Trading Intelligence, Trading Foundation and Market Microstructure;
* preserved approved Paper Trader v1, strategy, realtime execution, liquidity and performance directions;
* routed unresolved design choices to targeted external research;
* explicitly retained implementation as not started and not authorized.

Previous checkpoint preserved — CR-SCANNER-GEOMETRY-001 mission close (v4.20 to v4.21):

* recorded the verified implementation commit and synchronized push;
* closed revision 1.4 while preserving criterion 13 and residual non-blocking risks;
* returned planning to `SCANNER_GEOMETRY_TASK_SELECTION` without authorizing new implementation.

Previous checkpoint preserved — CR-SCANNER-GEOMETRY-001 checkpoint commit authorization (v4.19 to v4.20):

* recorded explicit authorization for the scoped implementation/record commit under revision 1.3;
* preserved verified implementation, acceptance disposition, review result and residual risks;
* retained mission close as a separate lifecycle action.

Previous checkpoint preserved — CR-SCANNER-GEOMETRY-001 implementation review record (v4.18 to v4.19):

* recorded implementation, focused verification and review as complete;
* recorded `READY_FOR_RECORD` and retained manual reference validation as a residual non-blocking risk;
* routed the next action to an explicitly authorized scoped commit.

Previous checkpoint preserved — CR-SCANNER-GEOMETRY-001 implementation authorization (v4.17 to v4.18):

* recorded revision 1.1 as human-authorized for bounded implementation;
* preserved implementation as not started and retained the approved scope and acceptance criteria.

Previous checkpoint preserved — CR-SCANNER-GEOMETRY-001 Task/Spec (v4.16 to v4.17):

* selected the next durable Scanner Geometry task and recorded its bounded scope;
* routed acceptance criteria and risks to ChangeRequest revision 1.0;
* retained implementation as not started and not authorized.

Previous checkpoint preserved — CR-DOC-AI-CONTEXT-001 mission close (v4.15 to v4.16):

* recorded MISSION_CLOSE_COMPLETED and the durable ChangeRequest as CLOSED;
* retained Phase 0–6 as implemented and verified;
* recorded the final 35.80 percent recovery-footprint reduction;
* returned planning to `SCANNER_GEOMETRY` task selection without starting or authorizing new implementation.

Previous checkpoint preserved — Signal Admission Implementation (v4.5 to v4.6):

* Priority 1 implementation and focused verification recorded as complete;
* acceptance status recorded as satisfied;
* remaining technical-debt and historical-state items retained as non-blocking follow-ups.

Previous checkpoint preserved — Signal Admission Recovery (v4.4 to v4.5):

* approved Signal admission contract and confirmed mismatches recorded;
* Priority 1 status set to APPROVED_NOT_IMPLEMENTED;
* minimal implementation scope, acceptance matrix and historical-state follow-up recorded;

Previous checkpoint preserved — Performance Architecture Audit (v4.3 to v4.4):

* зафиксирован утверждённый результат Performance Architecture Audit;
* текущий Roadmap синхронизирован с приоритетом SCANNER_GEOMETRY;
* утверждён порядок восьми targeted implementation priorities;
* Signal admission поставлен перед throughput optimization;
* chart/report и Telegram reliability выделены как отдельные целевые этапы;
* Geometry instrumentation поставлена перед Geometry optimization;
* bounded market-data concurrency и notification worker отложены до измерений;
* запрещён end-to-end asyncio conversion;
* зафиксированы performance non-goals, deferred findings и implementation principles;
* сохранены действующие analytical contracts и Project Sync architecture.

---

# END_OF_DOCUMENT
