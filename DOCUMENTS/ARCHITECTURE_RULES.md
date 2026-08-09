# BybitScanner — Architecture Rules

Version:

1.3

Date:

2026-07-28


Document Type:

ARCHITECTURE_RULES_DOCUMENT


Status:

ACTIVE


---

# DOCUMENT_METADATA


document_id:

BS-DOC-ARCH-001


purpose:

Определяет архитектурные ограничения,
границы ответственности подсистем,
правила разделения слоёв,
направления зависимостей,
контрактную модель
и принципы построения архитектуры BybitScanner.


machine_readable:

true


parser_version:

1.0


---


# ARCHITECTURE_MISSION


mission:

Обеспечить развитие BybitScanner
как системы независимых,
слабо связанных
и расширяемых архитектурных подсистем
с контролируемыми границами ответственности.


---


# ARCHITECTURE_MODEL


description:

Архитектура проекта строится
на разделении ответственности
между слоями,
модулями,
контрактами
и подсистемами.


core_rules:

* каждый слой имеет собственную ответственность;

* зависимости имеют одно направление;

* новые компоненты создаются через контракты;

* архитектурные решения фиксируются документально;

* изменения архитектуры проходят анализ влияния.


---


# ARCHITECTURE_HIERARCHY


model:

Architecture

↓

Contracts

↓

Implementation

↓

Validation

↓

Optimization


---


# ARCHITECTURE_PRINCIPLES


## ARCH-001


name:

Architecture First


description:

Архитектура проектируется
до реализации функциональности.


priority:

Architecture

↓

Contracts

↓

Implementation

↓

Optimization


---


## ARCH-002


name:

Single Responsibility


description:

Каждый модуль,
подсистема и слой
имеют одну область ответственности.


forbidden:

* смешивание бизнес-логики и инфраструктуры;

* смешивание геометрии и торговых решений;

* смешивание анализа и уведомлений;

* смешивание архитектуры и реализации;

* создание компонентов без владельца ответственности.


---


## ARCH-003


name:

Layer Separation


description:

Каждый архитектурный слой
имеет определённые границы
ответственности.


layers:

DATA_LAYER

↓

GEOMETRY_LAYER

↓

VALIDATION_LAYER

↓

PATTERN_LAYER

↓

CONFIRMATION_LAYER

↓

SIGNAL_LAYER

↓

REPORTING_LAYER

↓

AUTOMATION_LAYER


PROJECT_SYNC_LAYER:

Filesystem

↓

Registry

↓

Architecture Analyzer

↓

Architecture Validator

↓

Documentation Sync


---


# SUBSYSTEM_RESPONSIBILITIES


## DATA_LAYER


responsibility:

* получение внешних данных;

* подготовка входных структур;

* работа с источниками данных.


must_not_contain:

* pattern_detection;

* trading_decisions;

* notifications;

* signal_logic.


---


## GEOMETRY_LAYER


name:

Geometry Engine


responsibility:

* trendlines;

* apex calculation;

* compression analysis;

* touch detection;

* geometric model creation;

* geometric quality calculation.


must_not_contain:

* trading signals;

* Telegram integration;

* execution logic;

* risk decisions;

* notification logic.


---


## VALIDATION_LAYER


name:

Validation Engine


responsibility:

* geometric validation;

* structural verification;

* quality checks;

* validation scoring.


must_not_contain:

* trading logic;

* notifications;

* order execution.


---


## PATTERN_LAYER


name:

Pattern Detection Layer


responsibility:

* identification of market structures;

* pattern classification;

* pattern result generation.


must_not_contain:

* Telegram logic;

* execution logic;

* infrastructure code.


---


## CONFIRMATION_LAYER


name:

Confirmation Engine


responsibility:

* breakout confirmation;

* volume analysis;

* volatility checks;

* confirmation scoring.


must_not_contain:

* geometry generation;

* raw pattern detection;

* notification delivery;

* execution logic.


---


## SIGNAL_LAYER


responsibility:

* signal quality;

* filtering;

* trading interpretation;

* risk assessment.


must_not_contain:

* geometry calculation;

* trendline generation;

* raw pattern detection;

* notification delivery.


---


## REPORTING_LAYER


responsibility:

* generation of analysis reports;

* chart preparation;

* result presentation;

* analytical output formatting.


must_not_contain:

* pattern detection;

* signal generation;

* trading decisions;

* notification delivery.


---


## AUTOMATION_LAYER


responsibility:

* scheduled execution;

* workflow automation;

* external process control;

* automated task execution.


must_not_contain:

* geometry calculations;

* pattern detection;

* signal generation;

* trading interpretation.


---


## NOTIFICATION_LAYER


responsibility:

* Telegram messages;

* chart delivery;

* user notifications.


must_not_contain:

* pattern detection;

* geometry calculations;

* trading analysis;

* decision generation.


---


## PROJECT_SYNC_LAYER


responsibility:

* анализ структуры проекта;

* построение реестров;

* проверка архитектуры;

* контроль документации;

* анализ изменений.


must_not_contain:

* торговая логика;

* выполнение торговых операций;

* изменение бизнес-данных без контракта.


---


# DEPENDENCY_RULES


## ARCH-004


name:

Dependency Direction


rule:

Верхние слои могут использовать
нижние слои.

Нижние слои не должны зависеть
от верхних.


allowed:

DATA

↓

GEOMETRY

↓

VALIDATION

↓

PATTERN

↓

CONFIRMATION

↓

SIGNAL

↓

REPORTING

↓

AUTOMATION

↓

NOTIFICATION


forbidden:

NOTIFICATION → GEOMETRY

SIGNAL → TELEGRAM

GEOMETRY → TRADING

DATA → SIGNAL

REPORTING → PATTERN

AUTOMATION → SIGNAL


---


## ARCH-005


name:

No Circular Dependencies


description:

Циклические зависимости
между компонентами запрещены.


required:

* dependency_analysis;

* ownership_definition;

* architecture_validation.


---


# CONTRACT_INTEGRATION


## ARCH-006


name:

Contract Based Integration


description:

Связь между архитектурными слоями
осуществляется через определённые
контракты.


before_creation:

required:

* define responsibility;

* define layer;

* define owner;

* define producer;

* define consumer;

* define public API;

* define contract;

* define dependencies.


forbidden:

* creating components without ownership;

* bypassing contracts;

* duplicating existing interfaces.


reference:

DOCUMENTS/PROJECT_CONTRACTS.md


---


## ARCH-007


name:

Contract Change Impact


description:

Изменение существующего контракта
является архитектурным изменением.


required:

* dependency_analysis;

* affected_components_detection;

* documentation_update;

* changelog_update;

* compatibility_check.


---


# ARCHITECTURE_EXTENSION_RULES


## ARCH-008


name:

New Module Integration


before_creation:

required:

* responsibility_defined;

* layer_defined;

* owner_defined;

* public_api_defined;

* contract_defined;

* dependency_direction_checked.


---


# COMPATIBILITY_RULES


## ARCH-009


name:

Backward Compatibility


description:

При изменениях архитектуры
необходимо сохранять:


* existing_reports;

* existing_integrations;

* legacy_fields;

* external_contracts;

* documented workflows.


---


# STATE_ARCHITECTURE_INTEGRATION


## ARCH-010


name:

Architecture State Synchronization


description:

Архитектурное состояние проекта
хранится через State Package.


model:

PROJECT_STATE.md

↓

STATE PACKAGE

↓

Specialized State Documents


required:

* architecture_changes reflected in state;

* architecture version synchronized;

* affected state documents identified.


reference:

DOCUMENTS/PROJECT_STATE.md


---


# ARCHITECTURE_ROOT_PROTECTION


## ARCH-011


name:

Architecture Root Protection


description:

Корневые архитектурные документы
определяют правила и границы,
но не содержат детали реализации.


should_contain:

* architecture principles;

* layer responsibilities;

* dependency rules;

* contracts rules.


should_not_contain:

* implementation details;

* source code rules;

* workflow procedures;

* temporary decisions.


---


# ARCHITECTURE_VALIDATION


before_merge:


required:

* layer_defined;

* responsibility_defined;

* dependencies_checked;

* contracts_updated;

* documentation_updated;

* compatibility_checked;

* state_updated.


---


# PROJECT_SYNC_USAGE


Project Sync Framework
использует данный документ
для проверки:


* архитектурной целостности;

* границ подсистем;

* направления зависимостей;

* соответствия контрактам;

* состояния архитектуры.


---


# FINAL_PRINCIPLE


Архитектура BybitScanner
строится вокруг разделения
ответственности.


Каждая подсистема должна знать:


что она делает,


что она использует,


какой контракт предоставляет,


и что она делать не должна.


Архитектурные изменения должны быть:


контролируемыми,


документированными,


совместимыми


и проверяемыми.


# END_OF_DOCUMENT