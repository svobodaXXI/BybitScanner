# BybitScanner — Project Map

Version:

3.3

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

Определяет логическую карту проекта
BybitScanner, связи между подсистемами,
архитектурными слоями,
компонентами,
документами
и Project Sync Framework.

machine_readable:

true

parser_version:

1.0

---

# PROJECT_IDENTITY

system:

BybitScanner

architecture_model:

Architecture Driven Development

main_principle:

Architecture First

---

# GLOBAL_SYSTEM_MAP

BybitScanner

│

├── Trading Intelligence System

│

└── Project Intelligence System

---

# TRADING_INTELLIGENCE_MAP

## Market Data Flow

Market Data

↓

Analyzer / Orchestration

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

Notification Layer

---

# TRADING_COMPONENT_MAP

## DATA_LAYER

location:

contracts/

responsibility:

Получение и передача
рыночных данных
через определённые контракты.

---

## ANALYZER COMPONENT

location:

analyzer/

type:

Orchestration Component

responsibility:

* запуск pipeline;

* передача данных между слоями;

* координация результатов.

restrictions:

Не содержит:

* собственную геометрию;

* торговые решения;

* уведомления.

---

## GEOMETRY_LAYER

location:

geometry/

responsibility:

Математическое описание
рыночной структуры.

components:

geometry/

├── Trendline Engine

├── Apex Engine

├── Compression Analysis

├── Touch Analysis

├── Validation Support

output:

GeometryModel Contract

---

## VALIDATION_LAYER

location:

geometry/validation/

responsibility:

Проверка качества
геометрической структуры.

input:

GeometryModel

output:

ValidationResult Contract

---

## PATTERN_LAYER

locations:

wedge/

structures/

responsibility:

Распознавание рыночных структур.

current_pattern:

Wedge

future_extensions:

* Triangle;

* Channel;

* Breakout;

* Complex Structures.

---

## CONFIRMATION_LAYER

location:

analyzer/

confirmation components

responsibility:

Дополнительная проверка
качества структуры.

functions:

* breakout confirmation;

* volume confirmation;

* volatility confirmation.

---

## SIGNAL_LAYER

locations:

signal/

signals/

responsibility:

Формирование торговой интерпретации.

output:

Signal Object Contract

---

## NOTIFICATION_LAYER

locations:

reports/

charts/

tradingview/

responsibility:

Представление результата
пользователю.

supports:

* reports;

* chart images;

* external presentation.

---

# PROJECT_INTELLIGENCE_MAP

Project Sync Framework

location:

tools/project_sync/

pipeline:

Project Files

↓

Scanner

↓

ProjectModel

↓

Registry System

↓

Architecture Intelligence

↓

Rule Engine

↓

Validation Intelligence

↓

Impact Intelligence

↓

Change Intelligence

↓

Documentation Intelligence

↓

Synchronization Intelligence

↓

Reports

---

# PROJECT_SYNC_COMPONENT_MAP

## Scanner Layer

location:

tools/project_sync/analysis/

responsibility:

Создание ProjectModel
на основе файловой структуры.

---

## Registry Layer

location:

tools/project_sync/registry/

components:

Module Registry

Document Registry

Architecture Registry

---

## Architecture Intelligence

location:

tools/project_sync/registry/architecture/

responsibility:

Построение архитектурного
представления проекта.

---

## Architecture Rule Engine

location:

tools/project_sync/rules/

components:

* Rule Registry;

* Rule Loader;

* Rule Executor;

* Rule Handlers.

purpose:

Проверка соответствия
архитектурным правилам.

---

## Validation Intelligence

locations:

tools/project_sync/validation/

tools/project_sync/validators/

responsibility:

Проверка:

* архитектуры;

* документов;

* контрактов.

---

## Dependency Intelligence

location:

tools/project_sync/analysis/

responsibility:

Анализ связей
между компонентами.

---

## Impact Intelligence

location:

tools/project_sync/impact/

responsibility:

Определение влияния изменений.

---

## Change Intelligence

location:

tools/project_sync/change_detection/

responsibility:

Сравнение состояний проекта.

---

## Health Monitoring

location:

tools/project_sync/health/

responsibility:

Контроль состояния системы.

---

## Synchronization Intelligence

location:

tools/project_sync/synchronization/

responsibility:

Формирование планов
синхронизации.

---

## Pipeline Engine

location:

tools/project_sync/pipeline/

responsibility:

Оркестрация процессов
Project Sync Framework.

---

# DOCUMENTATION_MAP

DOCUMENTS/

│

├── PROJECT_RULES.md

├── ASSISTANT_PROTOCOL.md

├── ARCHITECTURE.md

├── ARCHITECTURE_RULES.md

├── STATE_ARCHITECTURE.md

├── STATE_PROJECT_SYNC.md

├── PROJECT_STATE.md

├── PROJECT_CONTRACTS.md

├── PROJECT_STANDARDS.md

├── PROJECT_TREE.md

├── PROJECT_MAP.md

├── ROADMAP.md

├── SNAPSHOT.md

└── CHANGELOG.md

---

# CONTRACT_FLOW_MAP

Market Data Contract

↓

GeometryModel Contract

↓

ValidationResult Contract

↓

PatternResult Contract

↓

Signal Object Contract

↓

Notification Contract

---

# ARCHITECTURE_RELATION_MAP

Architecture Rules

↓

Architecture Model

↓

Project Structure

↓

Component Registry

↓

Validation Engine

↓

Documentation Synchronization

---

# CURRENT_PROJECT_STATE

architecture_state:

Architecture Rule Intelligence Transition

implemented:

* Project Registry;

* Architecture Registry;

* Validation Pipeline;

* Impact Analysis;

* Change Detection;

* Rule Engine Foundation;

* Synchronization Planning.

active_development:

* Architecture Rule Engine Pipeline;

* Documentation Intelligence;

* State Intelligence.

---

# MAP_UPDATE_REASON

from:

PROJECT_MAP v3.2

to:

PROJECT_MAP v3.3

changes:

* синхронизирована карта с новым PROJECT_TREE;

* добавлен полный Project Sync Framework;

* добавлена Architecture Rule Engine карта;

* добавлена связь между архитектурными слоями и каталогами;

* обновлены контракты взаимодействия;

* устранены расхождения между архитектурой и файловой структурой.

---

# FINAL_NOTE

PROJECT_MAP является логической
картой системы.

PROJECT_TREE отвечает за:

Filesystem Structure

PROJECT_MAP отвечает за:

Component Relationships

ARCHITECTURE отвечает за:

System Design

PROJECT_SYNC отвечает за:

State Control

Все четыре уровня формируют
единое представление проекта:

Files

↓

Components

↓

Architecture

↓

Intelligence

# END_OF_DOCUMENT
