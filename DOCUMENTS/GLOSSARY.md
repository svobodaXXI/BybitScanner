# BybitScanner — Glossary

Version:

1.0

Date:

2026-07-27

Document Type:

PROJECT_GLOSSARY_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-GLOSSARY-001

purpose:

Единый словарь терминов,
используемых в проекте BybitScanner.

machine_readable:

true

parser_version:

1.0

---

# GLOSSARY_RULES

## RULE-001

name:

Single Meaning

description:

Каждый термин имеет
одно официальное определение.

assistant_should:

* use_official_terms
* avoid_duplicate_meanings

---

## RULE-002

name:

Stable Terminology

description:

Изменение определения термина
является архитектурным изменением
и должно быть отражено
в CHANGELOG.

---

# TERM_REGISTRY

## TERM-001

term:

Geometry Engine

category:

Architecture Layer

definition:

Подсистема,
строящая математическое описание
рыночной структуры.

---

## TERM-002

term:

GeometryModel

category:

Data Model

definition:

Стандартизированное описание
геометрии найденной структуры.

---

## TERM-003

term:

Validation Engine

category:

Architecture Layer

definition:

Подсистема,
оценивающая корректность
GeometryModel.

---

## TERM-004

term:

Pattern Detection

category:

Architecture Layer

definition:

Подсистема,
определяющая тип структуры
по результатам Validation.

---

## TERM-005

term:

Signal Layer

category:

Architecture Layer

definition:

Подсистема,
интерпретирующая найденную структуру
как торговый сигнал.

---

## TERM-006

term:

Human Annotation

category:

Learning

definition:

Разметка структуры человеком,
используемая
для обучения системы.

---

## TERM-007

term:

Dataset

category:

Learning

definition:

Коллекция проверенных
Human Annotation.

---

## TERM-008

term:

Geometry Calibration

category:

Learning

definition:

Процесс адаптации
Geometry Engine
по данным Dataset.

---

## TERM-009

term:

Project Sync Framework

category:

Project Intelligence

definition:

Архитектурная подсистема,
автоматически поддерживающая
документацию проекта.

---

## TERM-010

term:

Project Intelligence System

category:

Architecture

definition:

Совокупность подсистем,
отвечающих
за сопровождение проекта.

---

## TERM-011

term:

Pipeline

category:

Architecture

definition:

Последовательность этапов обработки,
в которой результат одного этапа
является входом следующего.

---

## TERM-012

term:

Contract

category:

Architecture

definition:

Формальное соглашение
между двумя архитектурными слоями
о формате взаимодействия.

---

## TERM-013

term:

Artifact

category:

Documentation

definition:

Полностью готовый документ
или файл,
предназначенный
для непосредственного использования.

---

## TERM-014

term:

Governance

category:

Management

definition:

Система правил,
политик
и принципов управления проектом.

---

## TERM-015

term:

Machine Readable Document

category:

Documentation

definition:

Документ,
структура которого
предназначена
как для человека,
так и для автоматического анализа.

---

# PROJECT_SYNC_USAGE

Project Sync Framework
может использовать данный документ
для проверки единообразия терминологии
во всей документации проекта.

---

# FINAL_PRINCIPLE

Единая терминология
является частью архитектуры проекта.

Все официальные документы
должны использовать
определения,
зафиксированные
в данном словаре.

---

# END_OF_DOCUMENT

