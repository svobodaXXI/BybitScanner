# BybitScanner — Decision Log

Version:

1.3

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

---

## DECISION-007

title:

Task-Scoped AI Context Workflow Modernization

date:

2026-08-17

status:

ACCEPTED

category:

Documentation / AI Context Workflow

change_request:

CR-DOC-AI-CONTEXT-001

context:

Routine recovery requires multiple large documents, authority and workflow rules are duplicated,
manual inventories and generated context can become stale, and GitHub First wording conflicts
with a newer current local checkout.

decision:

* adopt `TASK -> SPEC -> CONTEXT -> IMPLEMENT -> VERIFY -> RECORD`;
* use lightweight Task/Spec for routine work and durable ChangeRequests for substantial, risky, architectural or multi-session work;
* store future durable ChangeRequests as tracked Markdown under `DOCUMENTS/CHANGE_REQUESTS/` after storage support is implemented;
* use disposable non-authoritative ContextDumps under ignored `runtime/context/`, with Markdown primary and optional JSON;
* use machine-readable advisory/blocking LegacyWarnings and enforce blocking warnings through validation and agent policy;
* treat the current local checkout as current-state authority; GitHub remains collaboration/review and cannot override newer local state;
* let Git own detailed implementation history and deltas;
* make tracked compact `AGENTS.md` the future agent entry point and replace unconditional full recovery with staged/task-scoped recovery;
* retain PROJECT_TREE authority for important logical paths while reducing its future role as a manual filesystem mirror;
* defer GitHub Issue/PR templates until the local workflow is stable.

rationale:

This reduces routine AI context cost and stale-context risk while preserving authoritative contracts,
deep recovery, human approval boundaries and existing Project Sync responsibilities.

consequences:

* initial targets are 10 KB / approximately 2,000 tokens for routine startup and 30 KB / approximately 8,000 tokens for a standard ContextDump;
* migration proceeds through independently verified and revertible phases;
* no production scanner behavior or Project Sync migration implementation is authorized by this decision;
* Phase 0 records the design only; implementation remains NOT_STARTED.

---

## DECISION-008

title:

Central Always-On VPS Development and Runtime Direction

date:

2026-08-28

status:

ACCEPTED / PLANNED / NOT IMPLEMENTED

category:

Development Operations / Deployment Architecture

context:

Development and runtime currently depend on a user's Windows PC being available. The project must support
persistent work from the normal PC, another computer or a phone without that home PC remaining powered on. The
exact rented server has not been inspected, so adequacy cannot be assumed.

decision:

After the current logical frontend/Trading Workspace stage is completed, manually accepted and checkpointed,
migrate development to the rented VPS as the central persistent environment. Keep separate DEV and PROD
workspaces, controlled promotion into PROD, direct SSH access, secrets outside source, production credentials
restricted from ordinary DEV/Codex access, and non-root least-privilege operation by default. Codex, tests, builds
and Git run on the VPS repository; model inference remains with OpenAI and is not locally hosted.

rationale:

This removes dependence on one home computer, enables continuous remote work/operation, and creates a safer
foundation for the Scanner, Trading Workspace services and eventually the Robot.

consequences:

* migration follows, and does not interrupt, completion and checkpoint of the current logical stage;
* server inspection precedes final paths, services, capacity or suitability claims;
* Codex may change DEV, while PROD changes only through controlled deployment/promotion;
* live trading credentials and Robot runtime require additional capacity/security validation;
* this decision implements no migration or production deployment.
