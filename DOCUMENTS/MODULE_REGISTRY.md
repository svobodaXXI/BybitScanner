# BybitScanner — Module Registry

Version:

1.0

Date:

2026-07-27

Document Type:

MODULE_REGISTRY_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-MODULES-001

purpose:

Единый реестр всех модулей,
пакетов и архитектурных компонентов
проекта BybitScanner.

machine_readable:

true

parser_version:

1.0

---

# REGISTRY_POLICY

## POLICY-001

name:

Module Registration

description:

Каждый программный модуль
должен быть зарегистрирован
в данном документе.

required:

* module_id
* name
* layer
* type
* status
* owner
* responsibility
* dependencies

---

# MODULE_REGISTRY

## MODULE-001

module_id:

MODULE-MAIN-001

name:

main.py

layer:

Application

type:

Entry Point

status:

ACTIVE

owner:

Core

responsibility:

Точка входа проекта.

---

## MODULE-002

module_id:

MODULE-ANALYZER-001

name:

analyzer.py

layer:

Analyzer

type:

Coordinator

status:

ACTIVE

owner:

Analyzer Layer

responsibility:

Координация полного цикла анализа.

---

## MODULE-003

module_id:

MODULE-BYBIT-001

name:

bybit_api.py

layer:

Market Data

type:

Service

status:

ACTIVE

owner:

Market Data Layer

responsibility:

Получение рыночных данных.

---

## MODULE-004

module_id:

MODULE-GEOMETRY-001

name:

geometry

layer:

Geometry Engine

type:

Package

status:

ACTIVE

owner:

Geometry Layer

responsibility:

Геометрический анализ структуры рынка.

contains:

* trendline.py
* apex.py
* validation.py
* engine.py

---

## MODULE-005

module_id:

MODULE-WEDGE-001

name:

wedge.py

layer:

Pattern Detection

type:

Detector

status:

ACTIVE

owner:

Pattern Layer

responsibility:

Поиск клиновидных структур.

---

## MODULE-006

module_id:

MODULE-CONFIRMATION-001

name:

confirmation.py

layer:

Validation Engine

type:

Validator

status:

ACTIVE

owner:

Validation Layer

responsibility:

Подтверждение качества структуры.

---

## MODULE-007

module_id:

MODULE-CHART-001

name:

chart.py

layer:

Visualization

type:

Renderer

status:

ACTIVE

owner:

Visualization Layer

responsibility:

Построение графиков.

---

## MODULE-008

module_id:

MODULE-REPORT-001

name:

report.py

layer:

Reporting

type:

Reporter

status:

ACTIVE

owner:

Reporting Layer

responsibility:

Формирование отчётов.

---

## MODULE-009

module_id:

MODULE-CONFIG-001

name:

config.py

layer:

Configuration

type:

Configuration

status:

ACTIVE

owner:

Configuration Layer

responsibility:

Настройки проекта.

---

# MODULE_STATUS

allowed_values:

* ACTIVE
* PLANNED
* DEPRECATED
* REMOVED

---

# PROJECT_SYNC_USAGE

Project Sync Framework
использует данный документ
для проверки регистрации
всех модулей проекта.

При обнаружении нового файла
Project Sync может:

↓

определить отсутствие регистрации

↓

предложить создание записи

↓

обновить MODULE_REGISTRY.md

---

# FINAL_PRINCIPLE

Каждый программный компонент
проекта должен иметь
официальную регистрацию.

MODULE_REGISTRY.md

является источником истины
о составе программной части
BybitScanner.

---

# END_OF_DOCUMENT
