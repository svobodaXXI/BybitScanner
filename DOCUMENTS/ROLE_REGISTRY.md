# BybitScanner — Role Registry

Version:

1.0

Date:

2026-07-27

Document Type:

PROJECT_ROLE_REGISTRY

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-ROLES-001

purpose:

Единый реестр инженерных ролей
экосистемы BybitScanner.

machine_readable:

true

parser_version:

1.0

---

# REGISTRY_POLICY

## POLICY-001

name:

Role Registration

description:

Каждая инженерная роль
должна иметь
официальную регистрацию.

required:

* role_id
* name
* category
* status
* responsibilities
* related_layers
* related_documents

---

# ROLE_REGISTRY

## ROLE-001

role_id:

ROLE-PROJECT-ARCHITECT

name:

Project Architect

category:

Architecture

status:

ACTIVE

responsibilities:

* architecture_design
* architecture_review
* layer_definition
* subsystem_design
* long_term_planning

related_documents:

* ARCHITECTURE.md
* ROADMAP.md
* PROJECT_RULES.md
* DECISION_LOG.md

---

## ROLE-002

role_id:

ROLE-GEOMETRY-ENGINEER

name:

Geometry Engineer

category:

Engineering

status:

ACTIVE

responsibilities:

* geometry_models
* trendlines
* apex
* compression
* candidate_generation

related_layers:

* Geometry Engine

---

## ROLE-003

role_id:

ROLE-VALIDATION-ENGINEER

name:

Validation Engineer

category:

Engineering

status:

ACTIVE

responsibilities:

* geometry_validation
* thresholds
* validation_quality

related_layers:

* Validation Engine

---

## ROLE-004

role_id:

ROLE-PATTERN-ENGINEER

name:

Pattern Engineer

category:

Engineering

status:

ACTIVE

responsibilities:

* pattern_detection
* classification
* ranking

related_layers:

* Pattern Detection

---

## ROLE-005

role_id:

ROLE-DOCUMENTATION-ENGINEER

name:

Documentation Engineer

category:

Documentation

status:

ACTIVE

responsibilities:

* documentation_updates
* consistency
* machine_readable_format
* documentation_quality

related_documents:

* PROJECT_RULES.md
* PROJECT_SYNC.md
* PROJECT_TREE.md
* PROJECT_STATE.md

---

## ROLE-006

role_id:

ROLE-PROJECT-SYNC-ENGINEER

name:

Project Sync Engineer

category:

Automation

status:

PLANNED

responsibilities:

* synchronization
* registry_updates
* structure_validation
* backup_creation
* documentation_generation

related_documents:

* PROJECT_SYNC.md

---

## ROLE-007

role_id:

ROLE-DATASET-ENGINEER

name:

Dataset Engineer

category:

Learning

status:

PLANNED

responsibilities:

* dataset_management
* annotation_storage
* data_quality

related_layers:

* Dataset

---

## ROLE-008

role_id:

ROLE-CALIBRATION-ENGINEER

name:

Calibration Engineer

category:

Learning

status:

PLANNED

responsibilities:

* geometry_calibration
* training
* parameter_tuning

related_layers:

* Geometry Calibration

---

## ROLE-009

role_id:

ROLE-RELEASE-MANAGER

name:

Release Manager

category:

Governance

status:

PLANNED

responsibilities:

* version_management
* release_notes
* changelog
* project_state

related_documents:

* CHANGELOG.md
* SNAPSHOT.md
* PROJECT_STATE.md

---

# ROLE_RELATIONSHIPS

Project Architect

↓

Engineering Roles

↓

Documentation Engineer

↓

Project Sync Engineer

↓

Release Manager

---

# PROJECT_SYNC_USAGE

Project Sync Framework
использует данный документ
для определения
ответственных ролей
за различные части проекта.

---

# FINAL_PRINCIPLE

Роль является
логической инженерной единицей,
описывающей ответственность,
а не конкретного человека
или конкретный ИИ.

Несколько ролей
могут выполняться
одним исполнителем,

а одна роль
в будущем
может быть передана
отдельному специалисту
или специализированному ИИ.

---

# END_OF_DOCUMENT
