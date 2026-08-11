# BybitScanner — Roadmap

Version:

4.3

Date:

2026-08-01

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

Pipeline Architecture Consolidation

current_state:

Project Sync Framework способен:

* анализировать структуру проекта;
* создавать Registry модели;
* выполнять Architecture Validation;
* выполнять Document Validation;
* выполнять Dependency Analysis;
* выполнять Impact Analysis;
* выполнять Change Detection;
* выполнять Health Monitoring;
* выполнять State Analysis;
* создавать Synchronization Plans;
* управлять Migration Workflow;
* контролировать Approval State;
* выполнять Pipeline Workflow;
* выполнять Migration Execution;
* выполнять Document Update операции.

current_transition:

От:

Pipeline Stabilization

К:

Unified Pipeline Architecture

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

0.

Pipeline Architecture Consolidation

1.

Pipeline Executor Integration

2.

Registry Single Source Of Truth

3.

Documentation Automation Stability

4.

Project Sync Intelligence

5.

Architecture Rule Engine Expansion

6.

State Intelligence Expansion

7.

Geometry Accuracy

8.

Human Annotation

9.

Dataset Creation

10.

Geometry Calibration

11.

Validation Calibration

12.

Pattern Detection

13.

Confirmation Engine

14.

Signal Layer

15.

Trading Automation

---

# CURRENT_OBJECTIVE

Текущий приоритет:

Pipeline Architecture Consolidation

активные задачи:

* устранение дублирования Runner/Pipeline;
* перевод Runner на PipelineExecutor;
* Registry как Single Source Of Truth;
* завершение PipelineContext Integration;
* завершение PipelineResult Contract;
* унификация Stage Contract;
* стандартизация Pipeline Report.

следующий этап:

Unified Pipeline Engine

долгосрочная цель:

Self Maintained Project System

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

ROADMAP v4.2

to:

ROADMAP v4.3

reason:

* отражён переход к Pipeline Architecture Consolidation;
* Pipeline Registry закреплён как Single Source Of Truth;
* выделена задача устранения дублирования Runner и ProjectSyncPipeline;
* добавлен этап интеграции PipelineExecutor;
* добавлена стандартизация Pipeline Report;
* актуализированы архитектурные правила Pipeline Engine.

---

# END_OF_DOCUMENT
