# BybitScanner — Project Contracts

Version:

3.4

Date:

2026-08-17

Document Type:

CONTRACT_REGISTRY_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-CONTRACTS-001

purpose:

Описание архитектурных контрактов
между слоями BybitScanner
и подсистемами Project Sync Framework.

machine_readable:

true

parser_version:

1.0

---

# CONTRACT_SYSTEM

## PRINCIPLE-001

name:

Contract Based Architecture

description:

Все основные слои проекта взаимодействуют
через определённые контракты.

rules:

* contract_has_owner
* contract_has_producer
* contract_has_consumer
* contract_changes_are_tracked

---

# CONTRACT_REGISTRY

# CONTRACT-GENERAL-001

type:

DATA_CONTRACT

status:

ACTIVE

name:

Market Data Contract

owner_layer:

Market Data Layer

producer:

Bybit API Adapter

consumer:

Analyzer

purpose:

Передача рыночных данных
для дальнейшего анализа.

input:

source:

Bybit Futures API

format:

OHLCV

schema:

symbol:

string

timeframe:

string

timestamp:

integer

open:

float

high:

float

low:

float

close:

float

volume:

float

validation:

required_fields:

* symbol
* timestamp
* open
* high
* low
* close
* volume

---

# CONTRACT-GEOMETRY-001

type:

GEOMETRY_CONTRACT

status:

ACTIVE

name:

GeometryModel Contract

owner_layer:

Geometry Engine

producer:

Geometry Engine

consumer:

* Validation Engine
* Pattern Detection Layer

purpose:

Передача математического описания
рыночной структуры.

schema:

geometry_id:

string

upper_trendline:

object

lower_trendline:

object

apex:

object

slopes:

object

compression:

float

touches:

object

quality:

float

contains:

* trendlines
* apex
* compression
* touches
* geometry_quality

forbidden:

* trading_decision
* telegram_data
* execution_data

---

# CONTRACT-VALIDATION-001

type:

VALIDATION_CONTRACT

status:

ACTIVE

name:

ValidationResult Contract

owner_layer:

Validation Engine

producer:

Validation Engine

consumer:

Pattern Detection Layer

purpose:

Передача результата проверки
геометрической структуры.

schema:

validation_id:

string

geometry_id:

string

is_valid:

boolean

checks:

object

score:

float

forbidden:

* signal_logic
* trading_execution

---

# CONTRACT-PATTERN-001

type:

PATTERN_CONTRACT

status:

ACTIVE

name:

PatternResult Contract

owner_layer:

Pattern Detection Layer

producer:

Pattern Detector

consumer:

Signal Layer

purpose:

Передача найденной структуры.

schema:

pattern_id:

string

pattern_type:

string

direction:

string

quality:

float

confidence:

float

geometry_reference:

string

---

# CONTRACT-SIGNAL-001

type:

SIGNAL_CONTRACT

status:

ACTIVE

name:

Signal Object Contract

owner_layer:

Signal Layer

admission_owner:

Signal Layer

admission_result:

`approved`

approved_semantics:

`approved = true` means the signal passed the complete Signal Layer admission policy.
`approved = false` means it is rejected from normal downstream persistence and notification.

downstream_rule:

`main.py` MUST use final `approved` as the single normal persistence and notification gate.
`main.py` MUST NOT reproduce score, confirmation, quality or mode admission rules.

minimum_score_rule:

`MIN_SCORE` is an absolute lower admission threshold enforced inside Signal Layer.
If `score < MIN_SCORE`, normal admission MUST be rejected.
`score == MIN_SCORE` remains eligible for evaluation by the selected mode rules.

mode_rule:

* the selected mode comes from `config.MODE`;
* Hunter does not require `confirmed` universally; its quality and confirmation rules remain owned by Signal Layer;
* Sniper is stricter; its existing intended confirmation semantics MUST be preserved when confirmed by current code and documentation;
* mode policy MUST NOT be duplicated in `main.py`.

quality_label_rule:

* `"Elite Setup"` is the canonical current label;
* `"A+ Setup"` may be accepted only as a legacy-compatible alias;
* new results MUST NOT introduce a parallel canonical label.

diagnostic_rule:

* diagnostic / `TELEGRAM_TEST_MODE` may display rejected signals explicitly as rejected;
* diagnostic display MUST NOT change `approved`;
* diagnostic bypass is not normal admission;
* rejected signals MUST NOT enter normal signal persistence/history;
* rejected signals MUST NOT enter normal Telegram delivery.

historical_state_rule:

Existing historically persisted unapproved records MUST NOT be deleted or migrated automatically.
Their effect on `NEW` / `STRENGTHENING` MUST be verified after admission restoration.

implementation_status:

APPROVED_NOT_IMPLEMENTED

purpose:

Единый формат торгового решения.

forbidden:

* geometry_calculation
* pattern_detection

---

# PROJECT_SYNC_CONTRACTS

# CONTRACT-ARCHITECTURE-001

type:

ARCHITECTURE_CONTRACT

status:

ACTIVE

name:

Architecture Registry Contract

owner_layer:

Project Sync Architecture Layer

producer:

Architecture Analyzer

consumer:

* Architecture Validator
* Documentation System

purpose:

Передача архитектурного представления
проекта.

schema:

component_id:

string

module_name:

string

layer:

string

responsibility:

string

dependencies:

array

status:

string

forbidden:

* business_logic_execution
* trading_decisions

---

# CONTRACT-VALIDATION-SYNC-001

type:

VALIDATION_REPORT_CONTRACT

status:

ACTIVE

name:

Architecture Validation Report Contract

owner_layer:

Project Sync Validation Layer

producer:

Architecture Validator

consumer:

* Documentation System
* Project State
* Changelog

purpose:

Передача результата
архитектурной проверки.

schema:

validation_id:

string

rules_checked:

array

issues:

array

status:

string

timestamp:

string

validation_result:

SUCCESS

or

FAILED

---

# CONTRACT-SYNC-001

type:

SYSTEM_PIPELINE_CONTRACT

status:

ACTIVE

name:

Project Sync Pipeline Contract

owner_layer:

Project Sync Framework

producer:

Project Sync Pipeline Engine

consumer:

* Document Registry
* Validation Layer
* Dependency Analysis Layer
* Impact Analysis Layer
* Snapshot Compare Layer
* Health Monitoring Layer
* Synchronization Planning Layer
* State Intelligence Layer
* State Synchronization Planning Layer
* State Synchronization Layer
* Migration Layer
* Post Migration Validation Layer
* Reporting Layer

purpose:

Определение последовательности
и взаимодействия компонентов
канонического Project Sync Pipeline.

pipeline:

Document Registry

↓

Validation

↓

Dependency Analysis

↓

Impact Analysis

↓

Snapshot Compare

↓

Health Check

↓

Synchronization Planning

↓

State Intelligence

↓

State Synchronization Planning

↓

State Synchronization

↓

Migration

↓

Post Migration Validation

↓

Pipeline Report

execution:

Pipeline Engine

registry:

PipelineRegistry

executor:

PipelineExecutor

canonical_stage_count:

12

status:

HEALTHY

validated:

true

single_source_of_truth:

true

Important:

Migration Planning,
Migration Decision,
Approval Control,
Document Update
и Snapshot Creation
являются операциями
Migration Lifecycle
и не являются
отдельными registered Pipeline stages.

---

# CONTRACT-SYNC-DEPENDENCY-001

type:

ANALYSIS_CONTRACT

status:

ACTIVE

name:

Document Dependency Analysis Contract

owner_layer:

Project Sync Dependency Analysis Layer

producer:

Document Dependency Analyzer

consumer:

* Impact Analysis Layer
* Synchronization Planning Layer
* Reporting Layer

purpose:

Передача графа зависимостей
между официальными документами проекта.

schema:

document:

string

dependencies:

array

dependents:

array

status:

string

---

# CONTRACT-SYNC-IMPACT-001

type:

ANALYSIS_CONTRACT

status:

ACTIVE

name:

Document Impact Analysis Contract

owner_layer:

Project Sync Impact Analysis Layer

producer:

Document Impact Analyzer

consumer:

* Synchronization Planning Layer
* Reporting Layer

purpose:

Передача результатов анализа
влияния изменений документов
на связанные документы.

schema:

document:

string

impact_level:

string

affected_documents:

array

affected_count:

integer

---

# CONTRACT-SYNC-CHANGE-001

type:

CHANGE_DETECTION_CONTRACT

status:

ACTIVE

name:

Document Change Detection Contract

owner_layer:

Project Sync Change Detection Layer

producer:

Snapshot Compare Engine

consumer:

* Impact Analysis Layer
* Synchronization Planning Layer
* Reporting Layer

purpose:

Передача результатов сравнения
текущего состояния документации
с предыдущим snapshot.

schema:

document:

string

change_type:

string

allowed_change_types:

* ADDED
* MODIFIED
* REMOVED

---

# CONTRACT-SYNC-HEALTH-001

type:

HEALTH_REPORT_CONTRACT

status:

ACTIVE

name:

Project Health Report Contract

owner_layer:

Project Sync Health Layer

producer:

Project Health Report

consumer:

* Synchronization Planning Layer
* Pipeline Engine
* Reporting Layer

purpose:

Передача текущего состояния
инфраструктуры Project Sync
и обязательных отчётов.

schema:

status:

string

required_reports:

integer

existing_reports:

integer

missing_reports:

array

---

# CONTRACT-SYNC-PLANNING-001

type:

SYNCHRONIZATION_CONTRACT

status:

ACTIVE

name:

Synchronization Planning Contract

owner_layer:

Project Sync Synchronization Layer

producer:

Synchronization Planner

consumer:

* Documentation System
* State Intelligence Layer
* Migration Control Layer

purpose:

Формирование списка документов,
которые требуют проверки
или синхронизации после анализа
состояния проекта.

schema:

documents_to_review:

array

count:

integer

status:

string

approval_required:

boolean

migration_required:

boolean

---

# CONTRACT-SYNC-STATE-INTELLIGENCE-001

type:

STATE_INTELLIGENCE_CONTRACT

status:

ACTIVE

name:

State Intelligence Contract

owner_layer:

Project Sync State Intelligence Layer

producer:

State Intelligence Engine

consumer:

* State Synchronization Planning Layer
* Synchronization Planning Layer
* Migration Control Layer
* Reporting Layer

purpose:

Передача агрегированного состояния
официальных State-документов проекта.

schema:

state_documents:

array

documents_analyzed:

integer

missing_documents:

array

invalid_documents:

array

state_health:

string

synchronization_required:

boolean

---

# CONTRACT-SYNC-STATE-PLANNING-001

type:

STATE_SYNCHRONIZATION_PLANNING_CONTRACT

status:

ACTIVE

name:

State Synchronization Planning Contract

owner_layer:

Project Sync State Synchronization Planning Layer

producer:

State Synchronization Planner

consumer:

* State Synchronization Layer
* Synchronization Planning Layer
* Migration Control Layer
* Reporting Layer

purpose:

Определение необходимости
и набора действий
для синхронизации State-документов.

schema:

documents:

array

actions:

integer

synchronization_required:

boolean

status:

string

migration_required:

boolean

---

# CONTRACT-SYNC-STATE-SYNCHRONIZATION-001

type:

STATE_SYNCHRONIZATION_CONTRACT

status:

ACTIVE

name:

State Synchronization Contract

owner_layer:

Project Sync State Synchronization Layer

producer:

State Synchronizer

consumer:

* Project State
* State Documents
* Migration Control Layer
* Reporting Layer

purpose:

Контролируемое обновление
State-документов на основании
подтверждённого плана синхронизации.

schema:

documents:

array

actions:

array

status:

string

synchronization_required:

boolean

updated_documents:

array

errors:

array

---

# CONTRACT-SYNC-MIGRATION-PLANNING-001

type:

MIGRATION_PLANNING_CONTRACT

status:

ACTIVE

name:

Migration Planning Contract

owner_layer:

Project Sync Migration Control Layer

producer:

Migration Planner

consumer:

* Migration Decision Layer
* Approval Control Layer
* Migration Execution Layer
* Reporting Layer

purpose:

Формирование контролируемого
плана изменения документов.

schema:

documents:

array

actions:

array

updates:

integer

migration_required:

boolean

approval_required:

boolean

validity:

string

risk:

string

---

# CONTRACT-SYNC-MIGRATION-DECISION-001

type:

MIGRATION_DECISION_CONTRACT

status:

ACTIVE

name:

Migration Decision Contract

owner_layer:

Project Sync Migration Control Layer

producer:

Migration Decision Handler

consumer:

* Approval Control Layer
* Migration Execution Layer
* Reporting Layer

purpose:

Формирование контролируемого
решения о готовности migration
к прохождению Approval Gate.

schema:

status:

string

decision:

string

plan_valid:

boolean

migration_required:

boolean

approval_required:

boolean

automatic_approval:

boolean

allowed_decisions:

* PENDING
* APPROVED
* REJECTED

Important:

Migration Decision
не является Approval.

Decision и Approval
являются отдельными
контрольными состояниями.

---

# CONTRACT-SYNC-APPROVAL-001

type:

APPROVAL_CONTRACT

status:

ACTIVE

name:

Migration Approval Contract

owner_layer:

Project Sync Approval Control Layer

producer:

Approval Controller

consumer:

* Document Update Layer
* Migration Execution Layer
* Reporting Layer

purpose:

Передача явно подтверждённого
разрешения на выполнение
утверждённого migration workflow.

schema:

approval:

boolean

explicit_approval:

boolean

automatic_approval:

boolean

plan_valid:

boolean

migration_required:

boolean

status:

string

approval_artifact:

string

Important:

Automatic approval:

false

Approval Control
не может самостоятельно
переводить Migration Decision
из PENDING в APPROVED.

Наличие approval artifact
не заменяет отдельное состояние
Migration Decision.

---

# CONTRACT-SYNC-DOCUMENT-UPDATE-001

type:

DOCUMENT_UPDATE_CONTRACT

status:

ACTIVE

name:

Document Update Contract

owner_layer:

Project Sync Document Update Layer

producer:

Document Update Engine

consumer:

Migration Execution Layer

purpose:

Контролируемое применение
явно подготовленных обновлений
к разрешённым документам.

schema:

documents:

array

updates:

array

backups:

array

approval:

object

status:

string

report:

string

rules:

* approval_required
* explicit_updates_only
* backup_before_update
* no_unspecified_documents
* machine_readable_report

forbidden:

* autonomous_document_generation
* approval_bypass
* unspecified_document_modification

---

# CONTRACT-SYNC-MIGRATION-EXECUTION-001

type:

MIGRATION_EXECUTION_CONTRACT

status:

ACTIVE

name:

Migration Execution Contract

owner_layer:

Project Sync Migration Execution Layer

producer:

Migration Executor

consumer:

* Post Migration Validation Layer
* Snapshot Layer
* Reporting Layer

purpose:

Передача фактического результата
контролируемого выполнения migration.

schema:

status:

string

updated_documents:

array

backups:

array

errors:

array

execution_report:

string

approval:

object

execution_gate:

string

rules:

* valid_approval_required
* backup_required
* execution_report_required
* approval_bypass_prohibited

---

# CONTRACT-SYNC-POST-MIGRATION-VALIDATION-001

type:

POST_MIGRATION_VALIDATION_CONTRACT

status:

ACTIVE

name:

Post Migration Validation Contract

owner_layer:

Project Sync Post Migration Validation Layer

producer:

Post Migration Validator

consumer:

* Snapshot Layer
* Project State
* Reporting Layer

purpose:

Передача результата проверки
фактического состояния проекта
после Migration Execution.

schema:

execution_status:

string

documents_status:

string

backups_status:

string

execution_errors:

array

validation_status:

string

execution_report:

string

allowed_states:

* NOT_EXECUTED
* VALIDATED
* FAILED

rule:

VALIDATED допускается только
после успешного Migration Execution.

---

# CONTRACT-SYNC-SNAPSHOT-001

type:

SNAPSHOT_CONTRACT

status:

ACTIVE

name:

Project Snapshot Contract

owner_layer:

Project Sync Snapshot Layer

producer:

Snapshot Creator

consumer:

* Snapshot Compare Layer
* State Intelligence Layer
* Reporting Layer

purpose:

Формирование контрольной точки
состояния проекта после успешного
migration lifecycle.

schema:

snapshot_id:

string

created:

string

registry:

object

documents:

array

status:

string

baseline:

string

rules:

* snapshot_after_successful_migration
* snapshot_after_successful_validation
* snapshot_is_historical_state
* snapshot_does_not_replace_governance_documents

---

# CONTRACT-PIPELINE-REPORT-001

type:

PIPELINE_REPORT_CONTRACT

status:

ACTIVE

name:

Pipeline Report Contract

owner_layer:

Project Sync Reporting Layer

producer:

PipelineReport

consumer:

* Project State
* Documentation System
* Changelog
* Health Monitoring
* Synchronization Planning

purpose:

Каноническая передача итогового
результата выполнения Project Sync Pipeline.

schema:

pipeline:

string

version:

string

status:

string

created:

string

stages:

array

results:

array

errors:

array

canonical_model:

PipelineReport

report_artifact:

pipeline_report.json

rules:

* single_canonical_report_model
* machine_readable
* stage_results_preserved
* errors_preserved

---

# CONTRACT-DOCUMENTATION-001

type:

SYSTEM_CONTRACT

status:

ACTIVE

name:

Documentation Sync Contract

owner_layer:

Project Sync Framework

producer:

Project Sync Framework

consumer:

* PROJECT_STATE
* PROJECT_MAP
* SNAPSHOT
* CHANGELOG
* ROADMAP

purpose:

Обмен информацией между кодом
и документацией проекта.

schema:

project_version:

string

architecture_version:

string

changed_files:

array

changed_components:

array

sync_status:

string

---

# CONTRACT-DEPENDENCY_RULES

## RULE-CONTRACT-001

name:

Contract Ownership

description:

Каждый контракт принадлежит одному
архитектурному слою.

---

## RULE-CONTRACT-002

name:

No Hidden Changes

description:

Изменение контракта требует:

required:

* dependency_analysis
* documentation_update
* changelog_entry

---

## RULE-CONTRACT-003

name:

Backward Compatibility

description:

Старые поля и интеграции должны сохраняться,
если нет согласованного изменения версии.

---

## RULE-CONTRACT-004

name:

Pipeline Contract Synchronization

description:

Изменение состава или порядка
Project Sync Pipeline должно
отражаться в Project Sync Pipeline Contract.

required:

* pipeline_validation
* project_sync_state_update
* changelog_entry

---

## RULE-CONTRACT-005

name:

Migration Control Synchronization

description:

Изменение Migration Lifecycle,
Approval Gate,
Document Update,
Migration Execution
или Post Migration Validation
должно отражаться
в соответствующих архитектурных контрактах.

required:

* migration_validation
* project_state_update
* changelog_entry

---

## RULE-CONTRACT-006

name:

Canonical Pipeline Registry

description:

Registered Pipeline stages
должны определяться
через PipelineRegistry.

Запрещено создавать
второй независимый список
canonical stages.

---

## RULE-CONTRACT-007

name:

Canonical Pipeline Report

description:

PipelineReport является
единственной canonical model
итогового Pipeline Report.

Вторичная независимая модель
итогового pipeline JSON
не допускается.

---

## RULE-CONTRACT-008

name:

Approval Separation

description:

Migration Decision
и Approval Control
являются раздельными
контрольными состояниями.

Наличие approval artifact
не должно автоматически
изменять Migration Decision.

---

## RULE-CONTRACT-009

name:

Post Migration Validation Gate

description:

Post Migration Validation
не может перейти в VALIDATED
до успешного Migration Execution.

---

# CONTRACT_VERSIONING

format:

CONTRACT_NAME-MAJOR-MINOR

rules:

major_change:

requires_migration:

true

minor_change:

compatible:

true

---

# PROJECT_PIPELINE_CONTRACT_MAP

## Trading Pipeline

MarketDataContract

↓

GeometryModelContract

↓

ValidationResultContract

↓

PatternResultContract

↓

SignalObjectContract

---

## Project Sync Pipeline

Filesystem

↓

Document Registry Contract

↓

Validation Report Contract

↓

Document Dependency Analysis Contract

↓

Document Impact Analysis Contract

↓

Document Change Detection Contract

↓

Project Health Report Contract

↓

Synchronization Planning Contract

↓

State Intelligence Contract

↓

State Synchronization Planning Contract

↓

State Synchronization Contract

↓

Snapshot Compare Contract

↓

Migration Contract

↓

Post Migration Validation Contract

↓

Pipeline Report Contract

Important:

Migration Planning,
Migration Decision,
Approval Control,
Document Update
и Snapshot Creation
являются связанными
Migration Lifecycle contracts,
но не являются
отдельными registered
Pipeline stages.

Migration Execution
также является операцией
Migration Lifecycle
и не является
отдельным registered
Pipeline stage.

Canonical registered
Pipeline stages:

1. Document Registry
2. Validation
3. Dependency Analysis
4. Impact Analysis
5. Snapshot Compare
6. Health Check
7. Synchronization Planning
8. State Intelligence
9. State Synchronization Planning
10. State Synchronization
11. Migration
12. Post Migration Validation

Pipeline Report является
каноническим результатом
выполнения Pipeline
и не является отдельным
registered Pipeline stage.

---

# PROJECT_SYNC_USAGE

Project Sync Framework должен проверять:

* наличие контрактов;
* владельца контракта;
* производителя контракта;
* потребителя контракта;
* совместимость версий;
* изменение схем;
* зависимые компоненты;
* соответствие Pipeline Contract
  фактическому canonical pipeline;
* соответствие stage registration
  PipelineRegistry;
* соответствие PipelineReport
  canonical report model;
* разделение Migration Decision
  и Approval Control;
* наличие обязательной документации изменений;
* соблюдение Post Migration Validation gate.

---

# CURRENT_CONTRACT_STATE

contract_registry:

ACTIVE

project_sync_pipeline_contract:

ACTIVE

canonical_pipeline_stages:

12

pipeline_registry:

ACTIVE

pipeline_executor:

ACTIVE

pipeline_report_contract:

ACTIVE

state_intelligence_contract:

ACTIVE

state_synchronization_planning_contract:

ACTIVE

state_synchronization_contract:

ACTIVE

dependency_analysis_contract:

ACTIVE

impact_analysis_contract:

ACTIVE

change_detection_contract:

ACTIVE

health_report_contract:

ACTIVE

synchronization_planning_contract:

ACTIVE

migration_planning_contract:

ACTIVE

migration_decision_contract:

ACTIVE

approval_contract:

ACTIVE

document_update_contract:

ACTIVE

migration_execution_contract:

ACTIVE

post_migration_validation_contract:

ACTIVE

snapshot_contract:

ACTIVE

documentation_sync_contract:

ACTIVE

overall:

STABLE

---

# CURRENT_PIPELINE_STATE

status:

HEALTHY

pipeline_engine:

OPERATIONAL

pipeline_engine_version:

3.2

canonical_stage_count:

12

registered_documents:

41

validated_documents:

41

critical_errors:

0

registry:

PipelineRegistry

execution:

PipelineExecutor

report_model:

PipelineReport

report_status:

HEALTHY

---

# CURRENT_MIGRATION_CONTROL_STATE

migration_planning:

READY

migration_decision:

WAITING_APPROVAL

migration_decision_value:

PENDING

approval_control:

ACTIVE

approval_artifact:

APPROVED

automatic_approval:

DISABLED

document_update:

NOT_EXECUTED

migration_execution:

NOT_PERFORMED

post_migration_validation:

NOT_EXECUTED

snapshot_creation:

LIFECYCLE_CONTROLLED

Important:

Approval artifact сохраняется
как явно созданное состояние approval,
однако Migration Decision остаётся
WAITING_APPROVAL / PENDING.

Migration Execution
не выполняется до прохождения
валидного Approval Gate.

---

# FINAL_PRINCIPLE

Контракты являются границами ответственности
между архитектурными слоями.

Изменение контракта является
архитектурным изменением проекта.

Project Sync Pipeline Contract является
единым контрактом фактического
исполнительного workflow Project Sync.

PipelineRegistry является
единственным источником истины
для зарегистрированных Pipeline stages.

PipelineReport является
единственной canonical model
итогового Pipeline Report.

Migration Decision,
Approval Control,
Document Update,
Migration Execution
и Post Migration Validation
образуют контролируемый
Migration Lifecycle.

# VERSION_UPDATE_REASON

from:

PROJECT_CONTRACTS v3.3

to:

PROJECT_CONTRACTS v3.4

reason:

Current checkpoint — Signal Admission Recovery (v3.3 to v3.4):

* activated and defined CONTRACT-SIGNAL-001 admission ownership and downstream gate;
* established `MIN_SCORE`, mode, canonical quality-label, diagnostic and persistence rules;
* recorded implementation status as APPROVED_NOT_IMPLEMENTED;

Previous version reason preserved — PROJECT_CONTRACTS v3.3:

* синхронизирован Project Sync Pipeline Contract с актуальным canonical 12-stage Pipeline;
* исправлена карта Project Sync Pipeline Contract Map;
* Snapshot Compare Contract возвращён в соответствующую позицию canonical Pipeline;
* Migration Execution явно зафиксирован как операция Migration Lifecycle, а не отдельный registered Pipeline stage;
* добавлены State Intelligence, State Synchronization Planning и State Synchronization contracts;
* добавлены Migration Planning и Migration Decision contracts;
* добавлен отдельный Approval Contract;
* добавлен Document Update Contract;
* добавлен Migration Execution Contract;
* добавлен Post Migration Validation Contract;
* добавлен Project Snapshot Contract;
* добавлен canonical Pipeline Report Contract;
* зафиксировано, что Migration Planning, Migration Decision, Approval Control, Document Update, Migration Execution и Snapshot Creation являются операциями Migration Lifecycle, а не registered Pipeline stages;
* зафиксирован PipelineRegistry как Single Source Of Truth для registered stages;
* зафиксирован PipelineReport как единственная canonical report model;
* зафиксировано разделение Migration Decision и Approval Control;
* зафиксировано требование Post Migration Validation после Migration Execution;
* обновлено текущее состояние контрактов Project Sync;
* обновлено состояние canonical Pipeline до 12 stages;
* сохранена backward compatibility для существующих контрактов;
* версия документа обновлена до 3.3.

# END_OF_DOCUMENT
