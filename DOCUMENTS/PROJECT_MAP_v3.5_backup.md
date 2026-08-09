# BybitScanner — Project Map

Version:

4.0

Date:

2026-07-28

Document Type:

PROJECT_MAP_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-MAP-001

purpose:

Физическая карта компонентов проекта,
архитектурных слоёв,
зависимостей,
связей между кодом,
архитектурой,
документационной системой
и Project Sync Framework.

machine_readable:

true

parser_version:

1.0

---

# SOURCE_OF_TRUTH

primary_source:

PROJECT_TREE.md


secondary_source:

filesystem_scan


architecture_source:

PROJECT_STATE.md


documentation_source:

PROJECT_RULES.md


principle:

PROJECT_MAP описывает фактическую структуру проекта,
а не предполагаемую архитектуру.


---

# PROJECT_ROOT

location:

C:\BybitScanner

---

# ARCHITECTURE_MODEL

main_pipeline:

Market Data

↓

Analyzer / Orchestration Layer

↓

Geometry Engine

↓

Validation Engine

↓

Pattern Detection Layer

↓

Confirmation Engine

↓

Signal Layer

↓

Reporting Layer

↓

Automation Layer


project_intelligence_pipeline:

Project Files

↓

Project Sync Framework

↓

Registry Layer

↓

Architecture Intelligence

↓

Validation Intelligence

↓

Documentation Intelligence

↓

Impact Intelligence

↓

Change Intelligence

↓

Synchronization Intelligence

↓

Knowledge System

---

# ROOT_COMPONENTS

## Application Layer

components:

* main.py


responsibility:

Запуск системы анализа.

---

## Analyzer Layer

components:

* analyzer.py


responsibility:

Оркестрация аналитического pipeline.


dependencies:

* bybit_api.py

* geometry/

* wedge/

* confirmation.py

* chart.py

* report.py

---

## Market Data Layer

components:

* bybit_api.py

* symbols.py


responsibility:

Получение и нормализация
рыночных данных Bybit.

---

## Geometry Engine

location:

geometry/


responsibility:

Математическое описание
рыночных структур.


components:

* trendline

* apex

* engine

* validation


must_not_contain:

* trading_decisions

* telegram

* notifications

---

## Pattern Detection Layer

locations:

* wedge/

* structures/


legacy_components:

* wedge_legacy.py

* wedge_legacy_root.py


responsibility:

Распознавание рыночных структур
на основе GeometryModel.


current_patterns:

* Wedge


future_patterns:

* Triangle

* Channel

* Breakout

* Complex Structures

---

## Validation Layer

components:

geometry/validation/


responsibility:

Проверка геометрических моделей.

---

## Signal Layer

locations:

* signal/

* signals/


responsibility:

Работа с качеством сигналов
и торговой интерпретацией.


must_not_contain:

* geometry_generation

* pattern_detection

---

## Notification Layer

components:

* telegram_bot.py

* telegram_formatter.py

* notification.py

* notification_manager.py


responsibility:

Передача готовых сигналов пользователю.


must_not_contain:

* pattern_detection

* geometry_calculation

* trading_analysis

---

# PROJECT_SYNC_FRAMEWORK

location:

tools/project_sync/


status:

ACTIVE DEVELOPMENT


purpose:

Автоматический анализ структуры,
архитектуры,
документации
и изменений проекта.

---

# PROJECT_SYNC_COMPONENTS

## Scanner Engine

responsibility:

Сканирование файловой структуры.


output:

ProjectModel

---

## Registry Layer

responsibility:

Регистрация компонентов проекта.


artifacts:

tools/project_sync/reports/module_registry.json

tools/project_sync/reports/document_registry.json

---

## Architecture Intelligence

responsibility:

Создание архитектурного представления проекта.


artifact:

tools/project_sync/reports/architecture_registry.json

---

## Validation Intelligence

responsibility:

Проверка архитектурных
и документационных правил.


artifact:

tools/project_sync/reports/validation_report.json

---

## Impact Intelligence

responsibility:

Определение компонентов
и документов,
затронутых изменениями.


artifact:

tools/project_sync/reports/impact_report.json

---

## Change Intelligence

responsibility:

Обнаружение изменений
между состояниями проекта.


artifacts:

tools/project_sync/reports/change_report.json

tools/project_sync/snapshots/

---

## Health System

responsibility:

Проверка состояния
Project Sync Framework.


artifact:

tools/project_sync/reports/project_health_report.json

---

## Synchronization Intelligence

responsibility:

Формирование плана
синхронизации документации.


artifact:

tools/project_sync/reports/synchronization_plan.json

---

## Pipeline Runner

responsibility:

Оркестрация полного workflow
Project Sync Framework.


artifact:

tools/project_sync/reports/pipeline_report.json

---

# SUPPORTING_SYSTEMS

## TradingView Integration

location:

tradingview/


components:

* tradingview_bridge.py

* test_tradingview_bridge.py

* test_tradingview_import.py

---

## Training System

location:

training/


components:

* annotations

* examples

---

## Testing System

location:

tests/


responsibility:

Проверка компонентов проекта.

---

## Backup System

location:

Backups/


contents:

* analyzer

* geometry

* legacy

---

# DOCUMENTATION_SYSTEM

location:

DOCUMENTS/


description:

Документационная подсистема является
частью архитектуры проекта.


---

# GOVERNANCE_DOCUMENTS

## PROJECT_RULES.md

responsibility:

Главный управляющий документ проекта.

---

## ASSISTANT_PROTOCOL.md

responsibility:

Операционный протокол
работы ассистента.

---

# ARCHITECTURE_DOCUMENTS

## ARCHITECTURE_RULES.md

responsibility:

Архитектурные ограничения,
слои,
границы ответственности.

---

## PROJECT_CONTRACTS.md

responsibility:

Контракты между
архитектурными слоями.

---

# DEVELOPMENT_DOCUMENTS

## CODE_RULES.md

responsibility:

Правила разработки,
изменения
и рефакторинга кода.


---

## WORKFLOW_RULES.md

responsibility:

Правила процессов,
состояний workflow
и последовательности операций.


---

## PROJECT_STANDARDS.md

responsibility:

Обязательные стандарты
качества проекта.

---

# STATE_DOCUMENTS

## PROJECT_STATE.md

responsibility:

Индекс текущего состояния проекта.


decomposition_model:

PROJECT_STATE.md

↓

STATE_ARCHITECTURE.md

STATE_TRADING_SYSTEM.md

STATE_PROJECT_SYNC.md

STATE_DOCUMENTATION.md

STATE_DEVELOPMENT.md

---

# STRUCTURE_DOCUMENTS

## PROJECT_TREE.md

responsibility:

Фактическая структура файлов
и каталогов проекта.


---

## PROJECT_MAP.md

responsibility:

Физическая карта компонентов
и архитектурных связей.

---

# PROJECT_SYNC_DOCUMENTS

## PROJECT_SYNC.md

responsibility:

Главный документ
Project Sync Framework.


## PROJECT_SYNC_ARCHITECTURE.md

responsibility:

Архитектура подсистемы
Project Sync.


## PROJECT_SYNC_COMPONENTS.md

responsibility:

Описание компонентов
Project Sync.


## PROJECT_SYNC_HISTORY.md

responsibility:

История развития
Project Sync Framework.


## PROJECT_SYNC_ROADMAP.md

responsibility:

План дальнейшего развития
Project Sync Framework.

---

# PLANNING_DOCUMENTS

documents:

* ROADMAP.md

* SNAPSHOT.md

* CHANGELOG.md


responsibility:

Планирование,
контрольные точки
и история изменений.

---

# DOCUMENT_RESPONSIBILITY_MODEL

PROJECT_RULES.md

↓

Governance Root


ARCHITECTURE_RULES.md

↓

Architecture Constraints


DOCUMENTATION_RULES.md

↓

Documentation Management


CODE_RULES.md

↓

Source Code Development


WORKFLOW_RULES.md

↓

Process Management


PROJECT_STANDARDS.md

↓

Quality Validation


PROJECT_CONTRACTS.md

↓

Layer Communication Contracts


PROJECT_STATE.md

↓

Current Project State


PROJECT_SYNC.md

↓

Project Synchronization System

---

# PROJECT_SYNC_SAFETY_MODEL

purpose:

Сохранение управляемости,
обратимости
и архитектурной безопасности
автоматизации.


Project Sync Framework:


CAN:

* анализировать структуру;

* создавать реестры;

* выполнять проверки;

* обнаруживать изменения;

* определять влияние изменений;

* формировать планы.


CANNOT:

* самостоятельно менять governance документы;

* изменять правила работы ассистента;

* заменять официальные источники истины;

* выполнять необратимые изменения.


principle:

Automation assists governance.

Automation does not replace governance.

---

# ARCHITECTURE_EVOLUTION

previous_state:

Filesystem Awareness


current_state:

Architecture Registry Awareness


current_state_2:

Architecture Validation Awareness


current_state_3:

Project Intelligence Pipeline


next_state:

Architecture Rule Engine


future_state:

Automatic Documentation Synchronization

---

# COMPONENT_REGISTRATION_MODEL

every_component:

name:

required


location:

required


layer:

required


responsibility:

required


status:

required


dependencies:

required


documentation:

required_future_field

---

# DOCUMENT_IMPACT_RELATIONSHIP

current:

Assisted Project Change Model


workflow:

Project Change

↓

Change Detection

↓

Dependency Analysis

↓

Impact Analysis

↓

Affected Documents Detection

↓

Synchronization Planning

↓

Documentation Update


future:

Automatic Project Change Model

↓

Changed Components

↓

Document Dependency Map

↓

DOCUMENT_IMPACT_REPORT

↓

Documentation Synchronization

---

# STRUCTURE_OBSERVATIONS

observed:

* проект разделён на архитектурные подсистемы;

* Geometry Engine вынесен отдельно;

* Project Sync Framework выделен в отдельную подсистему;

* документация является частью архитектуры;

* governance, architecture, code и workflow разделены;

* legacy-компоненты сохранены отдельно;

* присутствуют тесты и резервные копии;

* документационная система имеет единую карту ответственности;

* Project Sync Framework получил собственную архитектуру и pipeline.

---

# FINAL_PRINCIPLE

PROJECT_MAP является связующим слоем между:

Filesystem

↓

Architecture

↓

Documentation

↓

Project Sync Framework

↓

Documentation Intelligence


Главный принцип:

Каждый компонент проекта должен иметь:

* физическое расположение;

* архитектурную роль;

* ответственность;

* владельца;

* зависимости;

* документационную связь.

# END_OF_DOCUMENT