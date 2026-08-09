# BybitScanner — Workflow Rules

Version:

1.5

Date:

2026-07-28

Document Type:

WORKFLOW_RULES_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-WORKFLOW-001

purpose:

Определяет правила рабочих процессов,
состояния workflow,
порядок выполнения операций,
переходы между этапами
и взаимодействие участников разработки.

machine_readable:

true

parser_version:

1.0

---

# WORKFLOW_MISSION

mission:

Обеспечить предсказуемый,
последовательный и контролируемый
процесс развития BybitScanner
с сохранением контекста проекта.

---

# WORKFLOW_MODEL

description:

Workflow проекта является
управляемым состоянием разработки.

Каждый этап имеет:

* входные условия;

* обязательные действия;

* результат перехода.

---

# SESSION_WORKFLOW

## WORKFLOW-001

name:

Session Start

description:

Каждая новая рабочая сессия
начинается с проверки состояния проекта.

sequence:

Environment Check

↓

Project Context Loading

↓

Document Access

↓

Analysis

↓

Modification

↓

Impact Analysis

↓

Synchronization

---

# ENVIRONMENT_PROTOCOL

## WORKFLOW-002

name:

Environment Preparation

description:

Перед анализом проекта
необходимо получить актуальное
состояние рабочей среды.

commands:

cd C:\BybitScanner

↓

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

↓

.\venv\Scripts\Activate.ps1

↓

dir

↓

tree /A

forbidden:

* анализ проекта до проверки среды;

* изменение документов до проверки среды;

* изменение кода до проверки среды.

---

# PROJECT_CONTEXT_PROTOCOL

## WORKFLOW-003

name:

Project Context Loading

description:

После проверки среды необходимо
получить актуальный контекст проекта.

required_sources:

* PROJECT_STATE.md;

* ARCHITECTURE_RULES.md;

* PROJECT_CONTRACTS.md;

* PROJECT_MAP.md;

* PROJECT_TREE.md;

* ROADMAP.md;

* SNAPSHOT.md.

purpose:

Определение:

* текущей архитектуры;

* активного этапа разработки;

* существующих ограничений;

* зависимостей.

---

# DOCUMENT_WORKFLOW

## WORKFLOW-004

name:

Document Access

description:

Перед обработкой официального документа
необходимо получить актуальную версию
документа.

command:

notepad DOCUMENTS\<DOCUMENT_NAME>.md

exception:

Команда может быть пропущена,
если:

* пользователь уже предоставил актуальное содержимое;

* документ был полностью сформирован
  ассистентом в текущей рабочей сессии;

* пользователь не сообщил об изменениях.

---

## WORKFLOW-005

name:

Document Update Flow

workflow:

Document Access

↓

Document Analysis

↓

Dependency Analysis

↓

Document Update

↓

Complete Updated Artifact Delivery

↓

Impact Analysis

↓

Synchronization Decision

required_result:

* updated_document;

* complete_artifact;

* version_updated_when_required;

* synchronization_status;

* affected_documents_analysis.

---

## WORKFLOW-005-A

name:

Universal Artifact Delivery

status:

ACTIVE

description:

Любое изменение официального документа
должно завершаться созданием полного
актуализированного документного артефакта.

Официальный документ после изменения
является новой версией проектного
артефакта и должен быть готов
для прямой замены исходного файла.

applies_to:

* GOVERNANCE_DOCUMENTS;

* ARCHITECTURE_DOCUMENTS;

* PROCESS_DOCUMENTS;

* STANDARD_DOCUMENTS;

* STATE_DOCUMENTS;

* CONTRACT_DOCUMENTS;

* ROADMAP_DOCUMENTS;

* MAP_DOCUMENTS;

* TREE_DOCUMENTS;

* SNAPSHOT_DOCUMENTS;

* CHANGELOG_DOCUMENTS;

* SYNC_DOCUMENTS;

* OTHER_OFFICIAL_DOCUMENTS.

required:

* full_updated_document;

* preserved_structure;

* preserved_metadata;

* preserved_machine_readable_format;

* ready_to_save_output;

* version_control;

* synchronization_status.

forbidden:

* partial_update_delivery;

* change_list_instead_of_document;

* manual_merge_required;

* returning_only_modified_sections;

* incomplete_artifact_output.

---

## WORKFLOW-005-B

name:

Document Delivery Sequence

status:

ACTIVE

description:

При возврате обновлённого официального
документа применяется единый порядок
доставки результата.

required_sequence:

1.

Current Document Opening Command

↓

2.

Complete Updated Document

↓

3.

Dependency Impact Analysis

↓

4.

Next Document Opening Command
(only if required)

↓

5.

Synchronization Complete

rules:

assistant_must:

* размещать команду открытия текущего
  документа непосредственно перед документом;

* возвращать полный документ
  единым артефактом;

* выполнять анализ зависимостей
  после выдачи документа;

* выводить команду открытия следующего
  документа только при необходимости
  дальнейшего обновления;

* завершать workflow после документа,
  если синхронизация завершена.

assistant_must_not:

* размещать команды открытия внутри документа;

* выводить следующую команду открытия
  без необходимости;

* создавать циклы открытия документов;

* требовать повторного доступа
  к актуальному источнику истины.

---

# CONTINUE_PROTOCOL

## WORKFLOW-006

name:

Continue Commands

commands:

э

ъ

'

meaning:

Продолжить текущий workflow.

assistant_action:

Продолжить с текущего состояния
без возврата к завершённым этапам.

forbidden:

* начинать процесс заново;

* повторять завершённые этапы;

* запрашивать уже принятые решения;

* создавать новые ветки workflow без причины.

---

# DECISION_PROTOCOL

## WORKFLOW-007

name:

Decision Lock

description:

После выбора пользователем
варианта решения
он становится активным состоянием workflow.

workflow:

Decision Provided

↓

Decision Locked

↓

Execution

↓

Result Delivery

forbidden:

* повторное подтверждение;

* возврат к закрытым вопросам;

* создание циклов уточнений;

* игнорирование принятого решения.

---

# RESPONSE_WORKFLOW

## WORKFLOW-008

name:

Result First Response

description:

После команды продолжения
ассистент выполняет следующий этап
workflow и обеспечивает непрерывность
процесса.

assistant_should:

* продолжать текущий workflow;

* выполнять следующий доступный шаг;

* сохранять контекст предыдущих решений;

* сообщать о смене состояния при необходимости.

assistant_must_not:

* писать сообщения подготовки;

* повторять завершённые этапы;

* создавать новые циклы согласования;

* оставлять активный workflow без ответа.

exception:

Краткое управляющее сообщение допускается,
если оно необходимо для продолжения workflow.

---

## WORKFLOW-011

name:

Active Workflow Feedback

status:

ACTIVE

description:

Любая активная команда продолжения
является управляющим событием workflow
и требует обработки.

assistant_must:

* подтверждать переход workflow;

* выполнять следующий доступный этап;

* указывать блокирующую проблему;

* сохранять текущее состояние процесса.

assistant_must_not:

* игнорировать команду продолжения;

* завершать workflow без состояния;

* создавать неопределённость процесса.

priority:

Workflow Continuity > Silent Response

---

# IMPACT_ANALYSIS_WORKFLOW

## WORKFLOW-009

name:

Change Impact Analysis

description:

После изменения документа,
архитектуры или кода
необходимо определить последствия.

workflow:

Change

↓

Dependency Analysis

↓

Affected Components Detection

↓

Required Updates

↓

Synchronization Decision

required:

* identify_dependencies;

* avoid_document_loops;

* update_only_affected_components.

---

# WORKFLOW_STATES

states:

ENVIRONMENT_CHECK

↓

PROJECT_CONTEXT_LOADING

↓

DOCUMENT_ACCESS

↓

DOCUMENT_ANALYSIS

↓

DEPENDENCY_ANALYSIS

↓

DOCUMENT_UPDATE

↓

COMPLETE_ARTIFACT_DELIVERY

↓

IMPACT_ANALYSIS

↓

NEXT_DOCUMENT_COMMAND

↓

SYNCHRONIZATION_COMPLETE

---

# WORKFLOW_ENFORCEMENT

## WORKFLOW-010

name:

Mandatory Workflow States

description:

Состояния workflow являются частью
инженерного процесса
и не должны пропускаться без основания.

allowed_exceptions:

* пользователь явно подтвердил выполнение этапа;

* результат этапа уже предоставлен пользователем;

* документ является актуальным источником истины текущей сессии.

---

# PROJECT_SYNC_USAGE

Project Sync Framework
использует данный документ
для контроля:

* последовательности операций;

* состояния workflow;

* переходов между этапами;

* сохранения контекста;

* соблюдения порядка синхронизации документов.

---

# FINAL_PRINCIPLE

Workflow BybitScanner
строится вокруг сохранения контекста.

Каждый следующий шаг должен:

использовать текущее состояние,

не повторять завершённое,

и приводить к следующему
определённому результату.

Любой изменённый официальный документ
должен проходить через workflow полного
обновления и возвращаться как полный,
актуальный и готовый к сохранению
проектный артефакт.

# END_OF_DOCUMENT