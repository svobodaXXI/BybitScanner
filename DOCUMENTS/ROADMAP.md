# BybitScanner — Roadmap

Version:

4.13

Date:

2026-08-18

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

SPEC_APPROVED / PHASE_5_COMPLETED

Implementation status:

PHASE_5_IMPLEMENTED_VERIFIED

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
6. Measured context-cost reduction and safe documentation deduplication.

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

PHASE_5_CODEX_WORKFLOW_INTEGRATION

Phase 5 authorization state:

COMPLETED / IMPLEMENTED_VERIFIED

Phase 5 implementation evidence is owned by ChangeRequest revision 1.6.
Phase 6 remains separately unauthorized and has not started.

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

ROADMAP v4.12

to:

ROADMAP v4.13

reason:

Current checkpoint — CR-DOC-AI-CONTEXT-001 Phase 5 implementation (v4.12 to v4.13):

* recorded Codex workflow integration as IMPLEMENTED_VERIFIED;
* recorded focused orchestration and governance verification;
* preserved Phase 6 as separately unauthorized.

Previous checkpoint preserved — CR-DOC-AI-CONTEXT-001 Phase 5 authorization (v4.11 to v4.12):

* recorded Phase 5 as human-authorized at PRE_IMPLEMENTATION_CHECKPOINT;
* routed bounded scope and acceptance to ChangeRequest revision 1.5 without duplication;
* recorded implementation as NOT_STARTED and Phase 6 as unauthorized.

Previous checkpoint preserved — CR-DOC-AI-CONTEXT-001 Phase 4 implementation (v4.10 to v4.11):

* recorded Phase 4 staleness validation and scoped warning enforcement as IMPLEMENTED_VERIFIED;
* recorded focused regression and standalone validation completion;
* preserved Phase 5 as separately unauthorized.

Previous checkpoint preserved — CR-DOC-AI-CONTEXT-001 Phase 4 authorization (v4.9 to v4.10):

* recorded bounded Phase 4 scope, acceptance and rollback ownership in ChangeRequest revision 1.3;
* recorded Phase 4 as authorized but not implemented;
* preserved Phase 5 as separately unauthorized.

Previous checkpoint preserved — CR-DOC-AI-CONTEXT-001 Phase 3 (v4.8 to v4.9):

* recorded the minimal ContextDump generator as IMPLEMENTED_VERIFIED;
* preserved Phase 4 staleness/LegacyWarning enforcement as separately unauthorized;
* retained the approved phase boundaries and context-budget acceptance.

Previous checkpoint preserved — CR-DOC-AI-CONTEXT-001 Phase 2 (v4.7 to v4.8):

* recorded Phase 1 and Phase 2 as IMPLEMENTED_VERIFIED;
* recorded durable ChangeRequest and LegacyWarning infrastructure completion;
* set Phase 3 as the next separately authorized phase.

Previous checkpoint preserved — CR-DOC-AI-CONTEXT-001 Phase 0 (v4.6 to v4.7):

* recorded the approved phased modernization plan, scope, non-goals and acceptance;
* recorded SPEC_APPROVED / PRE_IMPLEMENTATION_CHECKPOINT with implementation NOT_STARTED;
* set Phase 1 as the next separately authorized action.

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
