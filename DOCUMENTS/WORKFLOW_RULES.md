# BybitScanner — Workflow Rules

Version:

1.6

Date:

2026-10-18

Document Type:

WORKFLOW_RULES_DOCUMENT

Status:

ACTIVE

---

## Result-First applicability — OWNER RULE 2026-10-18

This document retains the Project Sync / legacy full-document delivery
state machine. It does **not** require every ordinary repository task,
assistant response, continuation («э») or GitHub-authored documentation
change to enter that state machine.

For ordinary BybitScanner work, root `AGENTS.md` routes the task and
`DOCUMENTS/ASSISTANT_PROTOCOL.md` owns Result-First next-action decisions.
`DOCUMENTS/GITHUB_FIRST_WORKFLOW.md` governs GitHub repository publication.
Apply WORKFLOW-001/002/003 and full PROJECT_CONTEXT_LOADING only when
a Project Sync run is expressly needed; do not automatically execute
`tree /A`, activate venv, or read all PROJECT_STATE/MAP/TREE/ROADMAP/SNAPSHOT
for a focused GitHub read/review/edit.

WORKFLOW-005-A/B full-artifact delivery applies when the owner explicitly
requests a complete replacement artifact or the task genuinely requires
manual/offline document delivery. For a GitHub-first edit, a complete
versioned file is already persisted in the reviewed commit/PR; give the
owner its PR/diff and relevant evidence, not a duplicate full file in chat,
and do not require manual `notepad` or file transport.

WORKFLOW-009 impact analysis is scoped to actual affected components.
WORKFLOW-010 mandatory states apply **only within the selected workflow**,
not as universal preparatory stages. Mandatory safety, protected-task,
contract, change-approval and migration gates remain fully binding when
applicable. Never confuse a local tool receipt with real PAPER acceptance.
The owner-approved critical path must resume after the required gate.

---

## Игровой слой GTD

Проект использует русскую игровую терминологию из
`DOCUMENTS/GTD_QUEST_SYSTEM.md` как лёгкий слой мотивации и навигации.

Он строго подчинён обычному GTD и project governance:

- текущая команда владельца, backlog, safety, acceptance и evidence сильнее
  любого игрового состояния;
- игровые названия не меняют scope и не дают торговых разрешений;
- XP и ачивки выдаются только за доказанный результат;
- запрещён фарм XP через лишние тесты, коммиты, документы или дробление задач;
- `DOCUMENTS/QUEST_STATE.md` хранит компактное текущее состояние кампании и
  автоматически читается при первом BybitScanner-запросе нового чата;
- если QUEST_STATE расходится с BACKLOG, исправляется QUEST_STATE;
- игровой слой должен экономить контекст и усиливать GTD, а не создавать новую
  систему учёта.

Новый чат не требует ручного game-handoff от владельца.


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

Полный Project Sync начинается с проверки состояния проекта.
Обычная сессия следует минимальному staged entry из AGENTS.md.

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

При фактическом локальном запуске Project Sync
необходимо получить актуальное состояние целевой среды.
Для GitHub-only чтения/PR локальная среда не требуется.

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

При полном Project Sync после проверки среды требуется
его согласованный контекст. Для routine задачи читать
только AGENTS.md и применимые разделы owning authority.

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

Когда явно требуется полный документный артефакт,
он должен быть полным и готовым для прямой замены.
Для GitHub-first изменение полного файла фиксируется
в коммите/PR; полная выдача в чат не обязательна.

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

Только при ручной выдаче полного документного артефакта
(не при прямой публикации через GitHub PR) применяется
следующий порядок доставки.

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

Состояния выбранного Project Sync / ручного документационного
workflow являются частью процесса и не пропускаются, когда
действительно применимы. Обычный GitHub-first edit не
обязан воспроизводить эти состояния.

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

Полная ручная выдача документа обязательна только в рамках
применимого full-artifact workflow. В GitHub-first источником
обновлённого файла служит версия в коммите/PR.

# END_OF_DOCUMENT