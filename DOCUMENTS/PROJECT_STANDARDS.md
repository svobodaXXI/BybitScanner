# BybitScanner — Project Standards

Version:

1.2

Date:

2026-07-28

Document Type:

PROJECT_STANDARDS_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-STANDARDS-001

purpose:

Определяет обязательные стандарты
качества, которым должны соответствовать
архитектура, код, документация,
контракты и структура проекта.

machine_readable:

true

parser_version:

1.0

---

# STANDARDS_MISSION

mission:

Обеспечить единый уровень качества,
предсказуемость и совместимость
всех компонентов BybitScanner.

---

# STANDARD_MODEL

description:

Стандарты проекта являются обязательными
требованиями качества.

Они определяют критерии,
по которым проверяются новые компоненты,
изменения архитектуры
и результаты разработки.

principles:

* standard_before_implementation;

* quality_before_optimization;

* compatibility_before_replacement;

* architecture_before_expansion;

* validation_before_release.

---

# STANDARD_HIERARCHY

description:

Стандарты применяются
как единая система проверки проекта.

priority:

Architecture Standards

↓

Contract Standards

↓

Documentation Standards

↓

Code Standards

↓

Workflow Standards

↓

Optimization Standards

---

# STANDARD_REGISTRY

## STANDARD-001

name:

Architecture Standard

status:

ACTIVE

requirements:

* layered_architecture;

* single_responsibility;

* contract_based_design;

* no_circular_dependencies;

* clear_layer_boundaries;

reference:

DOCUMENTS/ARCHITECTURE_RULES.md

---

## STANDARD-002

name:

Module Standard

status:

ACTIVE

requirements:

* one_responsibility;

* clear_public_api;

* documented_purpose;

* architecture_layer_defined;

* isolated_dependencies;

* defined_owner;

reference:

DOCUMENTS/CODE_RULES.md

---

## STANDARD-003

name:

Documentation Standard

status:

ACTIVE

requirements:

* machine_readable;

* document_metadata;

* stable_structure;

* parser_compatible;

* versioned;

* single_source_of_truth;

reference:

DOCUMENTS/DOCUMENTATION_RULES.md

---

## STANDARD-004

name:

Contract Standard

status:

ACTIVE

requirements:

* contract_id;

* owner;

* producer;

* consumer;

* input;

* output;

* status;

* compatibility_rules;

reference:

DOCUMENTS/PROJECT_CONTRACTS.md

---

## STANDARD-005

name:

Naming Standard

status:

ACTIVE

python:

snake_case

classes:

PascalCase

constants:

UPPER_CASE

documents:

UPPER_CASE.md

---

## STANDARD-006

name:

Version Standard

status:

ACTIVE

rules:

major:

architecture_change

minor:

new_functionality_or_new_component

patch:

fixes_improvements_clarifications

---

## STANDARD-007

name:

Project Structure Standard

status:

ACTIVE

requirements:

* predictable_structure;

* stable_directory_layout;

* documented_components;

* registered_modules;

* clear_package_boundaries;

reference:

DOCUMENTS/PROJECT_TREE.md

---

## STANDARD-008

name:

Governance Standard

status:

ACTIVE

requirements:

* update_DOCUMENTS;

* update_CHANGELOG;

* update_PROJECT_STATE;

* preserve_architecture;

* execute_impact_analysis;

reference:

DOCUMENTS/PROJECT_RULES.md

---

## STANDARD-009

name:

Compatibility Standard

status:

ACTIVE

requirements:

* preserve_existing_contracts;

* preserve_existing_integrations;

* preserve_legacy_fields;

* avoid_breaking_changes_without_migration;

---

## STANDARD-010

name:

Validation Standard

status:

ACTIVE

requirements:

* validate_before_release;

* verify_dependencies;

* verify_contracts;

* verify_documentation;

* verify_architecture_compliance;

---

# QUALITY_CHECKLIST

before_merge:

* architecture_valid;

* contracts_valid;

* documentation_updated;

* roadmap_considered;

* changelog_updated;

* compatibility_checked;

* project_state_updated;

* validation_completed;

---

# PROJECT_SYNC_USAGE

Project Sync Framework
использует данный документ
для проверки соответствия проекта
установленным стандартам.

validation_targets:

* architecture_quality;

* documentation_quality;

* code_quality;

* contract_quality;

* structure_quality;

* workflow_quality;

---

# STANDARD_OWNERSHIP

description:

Детальные правила находятся
в специализированных документах.

responsibility_map:

Architecture:

DOCUMENTS/ARCHITECTURE_RULES.md

Documentation:

DOCUMENTS/DOCUMENTATION_RULES.md

Code:

DOCUMENTS/CODE_RULES.md

Workflow:

DOCUMENTS/WORKFLOW_RULES.md

Contracts:

DOCUMENTS/PROJECT_CONTRACTS.md

Governance:

DOCUMENTS/PROJECT_RULES.md

---

# STANDARD_EVOLUTION

description:

Изменение стандартов является
архитектурным изменением
и требует анализа влияния.

required:

* identify_affected_documents;

* update_related_rules;

* preserve_single_source_of_truth;

* update_version;

---

# FINAL_PRINCIPLE

Каждый новый компонент,

модуль,

документ

или архитектурное изменение

должны соответствовать
единым стандартам проекта.

Стандарты являются обязательными,
а не рекомендательными.

# END_OF_DOCUMENT
