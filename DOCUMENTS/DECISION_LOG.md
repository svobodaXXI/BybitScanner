# BybitScanner — Decision Log

Version:

1.1

Date:

2026-07-29

Document Type:

ARCHITECTURE_DECISION_REGISTRY

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-DECISION-001

purpose:

Реестр ключевых архитектурных
и организационных решений проекта.

machine_readable:

true

parser_version:

1.0

---

# DECISION_POLICY

## POLICY-001

name:

Record Important Decisions

description:

Каждое значимое архитектурное решение
должно быть зафиксировано
в данном документе.

required:

* context
* decision
* rationale
* consequences
* status

---

# DECISION_REGISTRY

## DECISION-001

title:

Contract Based Architecture

date:

2026-07-27

status:

ACCEPTED

category:

Architecture

context:

Проект становился всё сложнее,
а взаимодействие модулей —
менее очевидным.

decision:

Все архитектурные слои
взаимодействуют через
официальные контракты.

rationale:

Контракты уменьшают связанность
и упрощают масштабирование.

consequences:

* появился PROJECT_CONTRACTS.md
* появилась единая модель данных

---

## DECISION-002

title:

Machine Readable Documentation

date:

2026-07-27

status:

ACCEPTED

category:

Documentation

context:

Документация должна поддерживаться
автоматически.

decision:

Все технические документы
используют единый машиночитаемый формат.

rationale:

Подготовка проекта
к Project Sync Framework.

consequences:

* единый формат документов
* возможность автоматического анализа

---

## DECISION-003

title:

Documentation Is Architecture

date:

2026-07-27

status:

ACCEPTED

category:

Governance

context:

Документация перестала быть
внешним описанием проекта.

decision:

Документация становится
полноценной архитектурной подсистемой.

rationale:

Это позволяет автоматизировать
сопровождение проекта.

consequences:

* появилась подсистема DOCUMENTS
* создан PROJECT_SYNC.md

---

## DECISION-004

title:

Project Intelligence System

date:

2026-07-27

status:

ACCEPTED

category:

Architecture

context:

Для сопровождения проекта
потребовалась отдельная система.

decision:

Выделить Project Intelligence System
как самостоятельное направление
архитектуры.

rationale:

Разделение ответственности
между анализом рынка
и анализом самого проекта.

consequences:

* Project Sync Framework
* Governance
* Documentation Engine

---

## DECISION-005

title:

Artifact First Workflow

date:

2026-07-27

status:

ACCEPTED

category:

Workflow

context:

Частичные ответы
усложняли сопровождение проекта.

decision:

Все официальные документы
и исходные файлы
предоставляются целиком,
если пользователь
не запросил обратное.

rationale:

Повышение целостности
и воспроизводимости.

consequences:

* единый стиль работы
* упрощение обновлений

---

## DECISION-006

title:

Controlled Duplication Exception for Document Delivery Sequence

date:

2026-07-29

status:

ACCEPTED

category:

Documentation

context:

Правило Document Delivery Sequence
логически необходимо одновременно в
ASSISTANT_PROTOCOL.md (операционное
поведение ассистента), WORKFLOW_RULES.md
(состояния workflow) и PROJECT_RULES.md
(governance-принцип), что формально
нарушает DOC-003 (Single Source Of Truth)
и PRINCIPLE-006 (Documentation Compactness),
запрещающие дублирование правил.

decision:

Ввести контролируемое, явно
зарегистрированное исключение из правила
запрета дублирования вместо перехода
на ссылочную модель.

Канонический источник истины закреплён
за DOCUMENTATION_RULES.md → DOC-013.

Дублирующие копии зарегистрированы
в DOCUMENT_DUPLICATION_EXCEPTIONS
(DOCUMENTATION_RULES.md) и обязаны
оставаться идентичными канонической
версии.

Введено новое правило DOC-014
(Assistant Protocol Self-Containment
Exception), ограничивающее область
действия исключения только процедурными
правилами операционного поведения
ассистента.

rationale:

ASSISTANT_PROTOCOL.md должен оставаться
самодостаточным и исполняемым независимо
от других документов в момент выполнения
операции ассистентом. Полная замена
дублирующего текста на ссылку создала бы
риск разрыва операционной непрерывности
workflow при отсутствии доступа к другому
документу в момент выполнения.

consequences:

* DOCUMENTATION_RULES.md обновлён до v1.5
  (добавлены DOC-013.canonical_owner,