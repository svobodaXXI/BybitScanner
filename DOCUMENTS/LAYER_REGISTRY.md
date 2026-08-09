# BybitScanner — Layer Registry

Version:

1.0

Date:

2026-07-27

Document Type:

ARCHITECTURE_LAYER_REGISTRY

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-LAYERS-001

purpose:

Единый реестр архитектурных слоёв
экосистемы BybitScanner.

machine_readable:

true

parser_version:

1.0

---

# REGISTRY_POLICY

## POLICY-001

name:

Layer Registration

description:

Каждый архитектурный слой
должен быть зарегистрирован
в данном документе.

required:

* layer_id
* name
* status
* responsibility
* input
* output
* dependencies
* contracts

---

# LAYER_REGISTRY

## LAYER-001

layer_id:

LAYER-MARKET-DATA

name:

Market Data

status:

ACTIVE

responsibility:

Получение рыночных данных.

input:

Bybit API

output:

Candles

depends_on:

None

---

## LAYER-002

layer_id:

LAYER-ANALYZER

name:

Analyzer

status:

ACTIVE

responsibility:

Координация полного цикла анализа.

input:

Candles

output:

Geometry Tasks

depends_on:

* Market Data

---

## LAYER-003

layer_id:

LAYER-GEOMETRY

name:

Geometry Engine

status:

ACTIVE

responsibility:

Построение математической модели
рыночной структуры.

input:

Candles

output:

GeometryModel

depends_on:

* Analyzer

---

## LAYER-004

layer_id:

LAYER-VALIDATION

name:

Validation Engine

status:

ACTIVE

responsibility:

Проверка корректности
GeometryModel.

input:

GeometryModel

output:

Validated Geometry

depends_on:

* Geometry Engine

---

## LAYER-005

layer_id:

LAYER-PATTERN

name:

Pattern Detection

status:

ACTIVE

responsibility:

Определение типа найденной структуры.

input:

Validated Geometry

output:

Pattern Result

depends_on:

* Validation Engine

---

## LAYER-006

layer_id:

LAYER-SIGNAL

name:

Signal Layer

status:

PLANNED

responsibility:

Интерпретация результата анализа
как торгового сигнала.

input:

Pattern Result

output:

Signal

depends_on:

* Pattern Detection

---

## LAYER-007

layer_id:

LAYER-NOTIFICATION

name:

Notification

status:

PLANNED

responsibility:

Доставка уведомлений
пользователю.

input:

Signal

output:

Telegram Notification

depends_on:

* Signal Layer

---

## LAYER-008

layer_id:

LAYER-ANNOTATION

name:

Human Annotation

status:

PLANNED

responsibility:

Разметка структур человеком.

input:

Charts

output:

Annotation Dataset

---

## LAYER-009

layer_id:

LAYER-DATASET

name:

Dataset

status:

PLANNED

responsibility:

Хранение обучающих данных.

input:

Annotations

output:

Training Samples

---

## LAYER-010

layer_id:

LAYER-CALIBRATION

name:

Geometry Calibration

status:

PLANNED

responsibility:

Калибровка Geometry Engine.

input:

Training Samples

output:

Updated Parameters

---

## LAYER-011

layer_id:

LAYER-PROJECT-INTELLIGENCE

name:

Project Intelligence

status:

PLANNED

responsibility:

Сопровождение проекта
и контроль его целостности.

input:

Project Structure

output:

Updated Documentation

contains:

* Project Sync Framework
* Documentation Engine
* Governance System

---

# LAYER_RELATIONSHIPS

primary_pipeline:

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

Signal Layer

↓

Notification

learning_pipeline:

Human Annotation

↓

Dataset

↓

Geometry Calibration

project_pipeline:

Project Structure

↓

Project Intelligence

↓

Documentation

↓

Synchronization

---

# PROJECT_SYNC_USAGE

Project Sync Framework
использует данный документ
для проверки:

* существования архитектурных слоёв;
* принадлежности модулей слоям;
* корректности зависимостей;
* полноты архитектурной модели.

---

# FINAL_PRINCIPLE

Архитектурный слой
является самостоятельной единицей
экосистемы BybitScanner.

Каждый слой имеет
фиксированную ответственность,
определённые входы,
выходы
и зависимости.

---

# END_OF_DOCUMENT
