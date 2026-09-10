# BybitScanner — Project Map

Version:

3.4

Date:

2026-09-10

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

Canonical authority:

DOCUMENTS/ARCHITECTURE.md → TRADING_INTELLIGENCE / TRADING_LAYERS

Verified pipeline, layer responsibilities, restrictions and module lists
are owned there and are not repeated here to avoid drift between two
descriptions of the same verified content.

---

# TRADING_COMPONENT_MAP

Directory location of each Trading Intelligence component. Responsibility,
restrictions and verified module lists belong to ARCHITECTURE.md; only
locations and facts not already recorded there are kept in this map.

DATA_LAYER:

contracts/

ANALYZER COMPONENT:

analyzer/

GEOMETRY_LAYER:

geometry/

geometry/validation/

PATTERN_LAYER:

wedge/

structures/

current_pattern:

Wedge

future_extensions (not recorded in ARCHITECTURE.md):

* Triangle;

* Channel;

* Breakout;

* Complex Structures.

CONFIRMATION_LAYER:

analyzer/ (confirmation components; no separate directory)

SIGNAL_LAYER:

signal/

signals/

NOTIFICATION_LAYER:

reports/

charts/

tradingview/

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

Source of truth:

DOCUMENTS/PROJECT_STATE.md

PROJECT_MAP.md is a logical/topology map and does not track current
priority, phase or active-development status. That state changes
frequently and is owned exclusively by PROJECT_STATE.md; a copy here
would drift and eventually contradict it.

---

# MAP_UPDATE_REASON

from:

PROJECT_MAP v3.3

to:

PROJECT_MAP v3.4

changes:

* removed TRADING_INTELLIGENCE_MAP/TRADING_COMPONENT_MAP content that
  duplicated verified ARCHITECTURE.md content (pipeline, layer
  responsibility, restrictions, module lists);
* kept only directory-location facts and forward-looking notes not
  already recorded in ARCHITECTURE.md;
* replaced the stale CURRENT_PROJECT_STATE snapshot (referencing
  Architecture Rule Intelligence Transition, no longer current) with a
  pointer to PROJECT_STATE.md as the single source of truth for
  priority/phase/active-development state;
* PROJECT_SYNC_COMPONENT_MAP and the rest of the document are unchanged.

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
