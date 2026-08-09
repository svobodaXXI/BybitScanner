# BybitScanner — Documentation Rules

Version:

1.5

Date:

2026-07-29

Document Type:

DOCUMENTATION_RULES_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-DOCS-001

purpose:

Определяет правила создания,
обновления, хранения,
структурирования и синхронизации
официальной документации BybitScanner.

machine_readable:

true

parser_version:

1.0

---

# DOCUMENTATION_MISSION

mission:

Обеспечить единую,
стабильную,
машиночитаемую
и масштабируемую систему
проектной документации.

---

# DOCUMENT_RESPONSIBILITY_MODEL

description:

Каждый официальный документ
имеет собственную область ответственности.

Документ не должен содержать правила,
относящиеся к другой подсистеме.

principles:

* один документ — одна ответственность;

* один источник истины;

* отсутствие дублирования правил;

* отсутствие конфликтующих требований.

---

# DOCUMENT_STRUCTURE_RULES

## DOC-001

name:

Official Documentation Location

rule:

Все официальные документы проекта
располагаются в каталоге:

DOCUMENTS/

---

## DOC-002

name:

Machine Readable Format

description:

Все официальные документы должны:

* иметь DOCUMENT_METADATA;

* содержать document_id;

* содержать version;

* сохранять стабильную структуру;

* быть пригодными для автоматического анализа.

---

## DOC-003

name:

Single Source Of Truth

description:

Каждое правило,
архитектурное решение
или стандарт должны иметь
один источник истины.

forbidden:

* duplicate_rules;

* conflicting_documents;

* parallel_versions_without_reason;

* copied_rules_without_reference.

exceptions:

Допустимые исключения регистрируются
в разделе DOCUMENT_DUPLICATION_EXCEPTIONS
данного документа.

---

# DOCUMENT_TYPES

## GOVERNANCE_DOCUMENTS

purpose:

Документы управления
проектом и глобальных принципов.

examples:

PROJECT_RULES.md

---

## ARCHITECTURE_DOCUMENTS

purpose:

Документы архитектурных решений,
границ подсистем
и технических ограничений.

examples:

ARCHITECTURE_RULES.md

---

## PROCESS_DOCUMENTS

purpose:

Документы рабочих процессов,
workflow и процедур сопровождения.

examples:

WORKFLOW_RULES.md

ASSISTANT_PROTOCOL.md

---

## STANDARD_DOCUMENTS

purpose:

Документы обязательных
качественных стандартов проекта.

examples:

PROJECT_STANDARDS.md

---

## STATE_DOCUMENTS

purpose:

Документы текущего состояния,
структуры и развития проекта.

examples:

PROJECT_STATE.md

PROJECT_TREE.md

PROJECT_MAP.md

SNAPSHOT.md

---

# DOCUMENT_UPDATE_RULES

## DOC-004

name:

Document Update Requirement

description:

Любое значимое изменение проекта
должно отражаться
в соответствующей документации.

required:

* identify_affected_documents;

* update_related_documents;

* preserve_history;

* update_version_when_required.

---

## DOC-005

name:

Document Impact Analysis

description:

После изменения документа
необходимо определить
зависимые документы.

workflow:

Document Change

↓

Dependency Analysis

↓

Affected Documents Detection

↓

Synchronization

assistant_must:

* проверять только реально связанные документы;

* избегать циклического обновления;

* не обновлять документы
  только ради изменения версии.

---

## DOC-006

name:

Document Versioning

rules:

major:

architecture_change

minor:

new_section_or_rule

patch:

correction_or_clarification

---

# DOCUMENT_DELIVERY_RULES

## DOC-007

name:

Complete Artifact Delivery

description:

Любой изменённый официальный документ
является самостоятельным проектным артефактом
и должен возвращаться полностью
в актуализированном состоянии.

required:

* full_document;

* updated_version;

* single_copyable_block;

* ready_to_save;

* preserved_structure;

* preserved_metadata.

forbidden:

* partial_documents_without_request;

* fragments_instead_of_document;

* manual_merge_instructions;

* change_list_instead_of_complete_document.

---

## DOC-008

name:

Document Opening Protocol

description:

Перед обработкой официального документа
ассистент обязан получить актуальную версию
документа.

exception:

Если документ был полностью сформирован
ассистентом в текущей рабочей сессии
и пользователь не сообщил об изменениях,
повторное открытие документа не требуется.

command_format:

notepad DOCUMENTS\<DOCUMENT_NAME>.md

required:

* opening_command_block;

* command_before_document_analysis;

* command_before_document_update.

assistant_must_not:

* создавать повторные циклы открытия
  одного и того же актуального документа;

* требовать повторного открытия документа,
  который является источником истины
  текущей сессии.

---

## DOC-011

name:

Universal Artifact Update

status:

ACTIVE

description:

Правило полного возврата обновлённого
документа применяется ко всем официальным
документам проекта.

applies_to:

* GOVERNANCE_DOCUMENTS;

* ARCHITECTURE_DOCUMENTS;

* PROCESS_DOCUMENTS;

* STANDARD_DOCUMENTS;

* STATE_DOCUMENTS;

* CONTRACT_DOCUMENTS;

* OTHER_OFFICIAL_PROJECT_DOCUMENTS.

assistant_must:

* вернуть полный актуализированный документ;

* сохранить исходную структуру;

* увеличить версию при необходимости;

* сохранить совместимость;

* подготовить документ для прямого сохранения.

assistant_must_not:

* возвращать только изменения;

* требовать ручного объединения;

* отправлять отдельные вставки вместо документа.

---

## DOC-012

name:

Relevant Communication Only

status:

ACTIVE

description:

Коммуникация при работе с документацией
должна содержать только информацию,
необходимую для выполнения текущей задачи.

rules:

* готовый артефакт является основным результатом;

* пояснения добавляются только при необходимости;

* комментарии используются для анализа рисков,
  архитектурного влияния или принятия решения;

* служебное описание процесса не заменяет результат.

assistant_should:

* предоставлять готовый документ напрямую;

* сохранять краткость при однозначных задачах;

* отделять комментарии от официального артефакта;

* использовать пояснения только при практической необходимости.

assistant_must_not:

* добавлять обязательные пояснения перед готовым документом;

* добавлять комментарии после документа без запроса;

* создавать промежуточные согласования без необходимости;

* повторять завершённые действия.

---

## DOC-013

name:

Document Delivery Sequence

status:

ACTIVE

description:

При возврате обновлённого официального документа
ассистент использует единый порядок выдачи результата.

required_sequence:

1.

Команда открытия текущего документа.

↓

2.

Полный обновлённый документ.

↓

3.

Краткий результат анализа зависимостей.

↓

4.

Если требуется обновление следующего документа —

команда открытия следующего документа.

↓

5.

Если обновление других документов не требуется —

ответ завершается без дополнительных команд.

command_format:

Current document:

notepad DOCUMENTS\<CURRENT_DOCUMENT>.md

Next document:

notepad DOCUMENTS\<NEXT_DOCUMENT>.md

assistant_must:

* размещать команду открытия текущего документа
  непосредственно перед документом;

* никогда не размещать команду открытия текущего документа
  после документа;

* возвращать полный документ единым артефактом;

* выводить команду открытия следующего документа
  только при реальной необходимости синхронизации;

* не открывать следующий документ
  «на всякий случай».

assistant_must_not:

* размещать команды открытия внутри документа;

* выводить лишние команды открытия;

* заставлять пользователя самостоятельно
  определять следующий документ;

* нарушать установленную последовательность доставки.

canonical_owner:

true

description_note:

Данное правило является источником истины
процедуры Document Delivery Sequence.
Иные документы, ссылающиеся на данную
процедуру, должны либо ссылаться на DOC-013,
либо быть зарегистрированы как исключение
в разделе DOCUMENT_DUPLICATION_EXCEPTIONS.

---

## DOC-014

name:

Assistant Protocol Self-Containment Exception

status:

ACTIVE

description:

ASSISTANT_PROTOCOL.md допускает
контролируемое дублирование процедурных
правил, если это необходимо для
самодостаточности операционного протокола
ассистента.

rationale:

ASSISTANT_PROTOCOL.md должен оставаться
читаемым и исполняемым независимо,
без обязательного обращения к другим
документам в момент выполнения операции.

scope:

Исключение действует только для:

* ASSISTANT_PROTOCOL.md;

* правил, определяющих непосредственное
  операционное поведение ассистента
  (например, Document Delivery Sequence).

conditions:

* дублирующее правило должно оставаться
  идентичным по содержанию канонической
  версии;

* канонический источник истины правила
  должен быть зафиксирован в
  DOCUMENT_DUPLICATION_EXCEPTIONS;

* изменение канонической версии правила
  требует синхронизации дублирующей копии
  в рамках Impact Analysis (DOC-005);

* исключение не освобождает от требований
  DOC-002 (Machine Readable Format).

forbidden:

* использование данного исключения
  для документов, не относящихся к
  PROCESS_DOCUMENTS уровня
  operational assistant behavior;

* расхождение содержания дублирующих копий
  без обновления обеих сторон одновременно.

---

# DOCUMENT_DUPLICATION_EXCEPTIONS

## EXCEPTION-001

rule_name:

Document Delivery Sequence

canonical_source:

DOCUMENTATION_RULES.md → DOC-013

duplicated_in:

* ASSISTANT_PROTOCOL.md → PROTOCOL-005-A;

* WORKFLOW_RULES.md → WORKFLOW-005-B;

* PROJECT_RULES.md → PRINCIPLE-009.

reason:

Обеспечение самодостаточности
операционных документов, участвующих
в непосредственном исполнении workflow
ассистентом.

approved_by_rule:

DOC-014

synchronization_requirement:

Любое изменение содержания процедуры
Document Delivery Sequence должно
быть отражено во всех перечисленных копиях
в рамках одной Impact Analysis.

---

# DOCUMENT_REFACTORING_RULES

## DOC-009

name:

Documentation Decomposition

description:

При увеличении размера документа
самостоятельные и стабильные разделы
выносятся в отдельные документы.

required:

* preserve_links;

* preserve_history;

* avoid_duplication;

* maintain_single_source_of_truth;

* update_document_responsibility_map.

---

## DOC-010

name:

Root Document Protection

description:

Корневые документы управления
не должны содержать детальные правила
других подсистем.

examples:

PROJECT_RULES.md

should_contain:

* principles;

* responsibility_map;

* priority_model;

* governance_links.

should_not_contain:

* detailed_code_rules;

* detailed_document_rules;

* detailed_workflow_rules;

* implementation_details.

---

# DOCUMENT_REGISTRY

official_documents:

* PROJECT_RULES.md

* ASSISTANT_PROTOCOL.md

* ARCHITECTURE_RULES.md

* DOCUMENTATION_RULES.md

* CODE_RULES.md

* WORKFLOW_RULES.md

* PROJECT_STANDARDS.md

* PROJECT_CONTRACTS.md

* PROJECT_STATE.md

* PROJECT_TREE.md

* PROJECT_MAP.md

* ROADMAP.md

* SNAPSHOT.md

* CHANGELOG.md

* PROJECT_SYNC.md

---

# PROJECT_SYNC_USAGE

Project Sync Framework
использует данный документ
для проверки:

* структуры документации;

* отсутствия неучтённых конфликтов;

* актуальности связей;

* соблюдения ответственности документов;

* корректности обновления артефактов;

* соответствия зарегистрированным исключениям
  из правила Single Source Of Truth.

---

# FINAL_PRINCIPLE

Документация BybitScanner
является частью архитектуры.

Каждый документ должен иметь:

свою ответственность,

свой источник истины,

своё место
в системе проекта.

Каждый изменённый документ
должен возвращаться как полный,
актуальный и готовый к сохранению
проектный артефакт.

Дублирование правил допускается
только как зарегистрированное
и контролируемое исключение,
а не как побочный эффект
несогласованной документации.

# END_OF_DOCUMENT