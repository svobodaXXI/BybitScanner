# BybitScanner — Subsystem Registry

Version:

1.0

Date:

2026-07-27

Document Type:

PROJECT_SUBSYSTEM_REGISTRY

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-SUBSYSTEMS-001

purpose:

Единый реестр архитектурных подсистем
проекта BybitScanner.

machine_readable:

true

parser_version:

1.0

---

# REGISTRY_POLICY

## POLICY-001

name:

Subsystem Registration

description:

Каждая крупная подсистема проекта
должна быть зарегистрирована
в данном документе.

required:

* subsystem_id
* name
* status
* purpose
* owner_layers
* related_documents
* related_modules

---

# SUBSYSTEM_REGISTRY

## SUBSYSTEM-001

subsystem_id:

SUBSYSTEM-MARKET-001

name:

Market Intelligence System

status:

ACTIVE

purpose:

Анализ рыночных данных
и поиск графических структур.

owner_layers:

* Market Data
* Analyzer
* Geometry Engine
* Validation Engine
* Pattern Detection
* Signal Layer
* Notification

related_documents:

* ARCHITECTURE.md
* LAYER_REGISTRY.md
* PROJECT_CONTRACTS.md

---

## SUBSYSTEM-002

subsystem_id:

SUBSYSTEM-LEARNING-001

name:

Learning Intelligence System

status:

PLANNED

purpose:

Обучение системы
на основе человеческой разметки.

owner_layers:

* Human Annotation
* Dataset
* Geometry Calibration

related_documents:

* ROADMAP.md
* PROJECT_CONTRACTS.md

---

## SUBSYSTEM-003

subsystem_id:

SUBSYSTEM-PROJECT-001

name:

Project Intelligence System

status:

PLANNED

purpose:

Автоматическое сопровождение проекта,
контроль архитектуры
и синхронизация документации.

owner_layers:

* Project Sync Framework
* Documentation Subsystem
* Governance System

related_documents:

* PROJECT_SYNC.md
* PROJECT_RULES.md
* PROJECT_TREE.md
* PROJECT_STATE.md
* CHANGELOG.md
* SNAPSHOT.md
* DECISION_LOG.md
* PROJECT_STANDARDS.md

---

## SUBSYSTEM-004

subsystem_id:

SUBSYSTEM-DOCUMENTATION-001

name:

Documentation Subsystem

status:

ACTIVE

purpose:

Хранение
и сопровождение
официциальной документации проекта.

owner_layers:

* Documentation

related_documents:

* PROJECT_RULES.md
* ARCHITECTURE.md
* PROJECT_TREE.md
* PROJECT_MAP.md
* PROJECT_STATE.md
* PROJECT_SYNC.md

---

# SUBSYSTEM_RELATIONSHIPS

Market Intelligence System

↓

Learning Intelligence System

↓

Project Intelligence System

Project Intelligence System

↓

Documentation Subsystem

---

# SUBSYSTEM_STATUS

allowed_values:

* PLANNED
* ACTIVE
* DEPRECATED
* REMOVED

---

# PROJECT_SYNC_USAGE

Project Sync Framework
использует данный документ
для контроля состава
архитектурных подсистем проекта.

Проверяется:

* регистрация подсистем;
* соответствие архитектуре;
* полнота документации;
* наличие связанных документов.

---

# FINAL_PRINCIPLE

BybitScanner состоит
из независимых подсистем,
каждая из которых
имеет собственную ответственность,
архитектуру
и жизненный цикл.

Подсистема является
архитектурной единицей
более высокого уровня,
чем отдельный слой
или программный модуль.

---

# END_OF_DOCUMENT
