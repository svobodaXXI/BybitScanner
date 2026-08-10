# BybitScanner — Project Rules

Version:

5.4

Date:

2026-08-10

Document Type:

PROJECT_RULES_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-RULES-001

purpose:

Определяет обязательные архитектурные,
документационные и эксплуатационные правила
разработки и сопровождения проекта BybitScanner.

machine_readable:

true

parser_version:

1.0

---

# 1. CORE_PRINCIPLES

## 1.1 Architecture First

Архитектура проекта является первичной
по отношению к отдельным программным модулям.

Любое структурное изменение должно:

* соответствовать текущей архитектуре;
* быть отражено в соответствующей документации;
* сохранять Single Source Of Truth;
* не создавать параллельные архитектурные контуры.

---

## 1.2 Documentation Is Architecture

Документация является частью архитектуры проекта.

Изменение архитектуры должно сопровождаться
актуализацией соответствующей документации.

Документация не является вспомогательным
материалом и не должна рассматриваться
как необязательное описание проекта.

---

## 1.3 Single Source Of Truth

Для каждого архитектурного объекта должен
существовать один канонический источник истины.

В частности:

* Pipeline Registry является Single Source Of Truth
  для состава Pipeline;
* Pipeline Executor является каноническим механизмом
  выполнения зарегистрированных стадий;
* PipelineStage является каноническим контрактом стадии;
* PipelineContext является каноническим контейнером
  общего состояния выполнения;
* PipelineResult является канонической моделью
  результата стадии;
* PipelineReport является канонической моделью
  итогового Pipeline Report;
* PROJECT_STATE.md является главным документом
  текущего состояния проекта;
* PROJECT_RULES.md является источником обязательных
  правил сопровождения проекта.

Запрещено создавать второй независимый
канонический источник истины для того же объекта.

---

## 1.4 Controlled Evolution

Изменения проекта должны выполняться
контролируемо.

Изменение должно:

1. иметь понятную причину;
2. соответствовать архитектуре;
3. учитывать зависимости;
4. проходить необходимую валидацию;
5. отражаться в документации;
6. не нарушать существующие контракты
   без явно контролируемого изменения версии.

---

# 2. PROJECT_STRUCTURE_RULES

## 2.1 Project Root

Корневой каталог проекта:

C:\BybitScanner

---

## 2.2 Documentation Location

Проектная документация хранится в:

C:\BybitScanner\DOCUMENTS

Документы не должны создаваться
в корне проекта без архитектурной необходимости.

---

## 2.3 Project Sync Location

Project Sync Framework располагается в:

C:\BybitScanner\tools\project_sync

---

## 2.4 Generated Reports

Машиночитаемые отчёты Project Sync
должны сохраняться в:

C:\BybitScanner\tools\project_sync\reports

---

## 2.5 Backups

Резервные копии документов при выполнении
Document Update должны создаваться
до изменения исходного документа.

Основной каталог:

C:\BybitScanner\Backups

Для Document Update:

C:\BybitScanner\Backups\document_updates

---

# 3. DOCUMENTATION_RULES

## 3.1 Document Metadata

Канонические проектные документы должны
содержать машинно-читаемый metadata-блок.

Минимальный набор:

* document_id;
* purpose;
* version;
* date;
* document_type;
* status.

---

## 3.2 Document Validity

Документ считается валидным,
если он:

* находится в допустимом расположении;
* имеет корректную структуру;
* содержит обязательные metadata;
* соответствует своему Document Type;
* не нарушает архитектурные правила.

---

## 3.3 Document Updates

Изменения документации выполняются
с минимально необходимым объёмом передачи данных.

Если документ доступен через GitHub,
ассистент должен читать его непосредственно
из репозитория и не запрашивать повторную
передачу полного содержимого от пользователя.

Для локального изменения допускается
точечное автоматизированное изменение.

Полный документ предоставляется только если:

* создаётся новый документ;
* выполняется существенная переработка;
* требуется полная замена;
* пользователь явно запросил полный документ.

---
## 3.4 Technical Artifact Delivery

Команда открытия файла предоставляется
только когда пользователю действительно
необходимо открыть или проверить локальный файл.

Если файл доступен через GitHub,
обязательная предварительная команда `notepad`
не требуется.

---
## 3.5 Machine Readability

Каноническая документация должна оставаться
пригодной для автоматической обработки.

Запрещается без необходимости добавлять
структуры, препятствующие машинному парсингу.

---

# 4. SOFTWARE_MODULE_RULES

## 4.1 Minimal Module Delivery

При изменении программного модуля
используется минимально достаточный способ.

Для локального изменения предпочтительны:

* точная PowerShell/console команда;
* patch;
* автоматизированная замена.

Полный модуль предоставляется только при
существенной структурной переработке,
создании нового файла
или явном запросе пользователя.

---
## 4.2 Local Code Changes

Для небольших локальных изменений,
если полный модуль не требуется,
изменение выполняется через конкретную
команду консоли или PowerShell.

Ручное редактирование отдельных строк
не является предпочтительным способом
изменения проектного кода.

---

## 4.3 No Uncontrolled Duplicate Modules

Новые модули не должны создаваться
только для обхода существующей архитектуры.

Перед созданием нового модуля необходимо
проверить наличие существующего
архитектурного компонента.

---

## 4.4 Import Integrity

Модули должны поддерживать
канонический способ запуска проекта.

Для package-модулей предпочтителен запуск:

```powershell
cd C:\BybitScanner
python -m <package.module>
```

Прямой запуск модуля, использующего
relative imports, не должен считаться
каноническим способом запуска.

---

# 5. PROJECT_SYNC_RULES

## 5.1 Project Sync Is Operational Subsystem

Project Sync Framework является
рабочей подсистемой проекта.

Его назначение:

* анализ состояния;
* регистрация документов;
* валидация;
* анализ зависимостей;
* анализ влияния;
* обнаружение изменений;
* контроль здоровья;
* планирование синхронизации;
* State Intelligence;
* State Synchronization;
* Migration Lifecycle;
* итоговая отчётность.

---

## 5.2 Pipeline Single Source Of Truth

`PipelineRegistry` является единственным
каноническим источником состава
операционного Pipeline.

`project_sync_runner.py` не должен
определять отдельный независимый
канонический список стадий.

Runner является:

* bootstrap point;
* runtime entry point;
* точкой запуска Pipeline.

---

## 5.3 Canonical Pipeline

Канонический operational Pipeline
содержит ровно 12 зарегистрированных стадий:

1. document_registry
2. validation
3. dependency_analysis
4. impact_analysis
5. snapshot_compare
6. health_check
7. synchronization_planning
8. state_intelligence
9. state_synchronization_planning
10. state_synchronization
11. migration
12. post_migration_validation

Количество зарегистрированных стадий:

12

---

## 5.4 Stage Registration

Каждая operational Pipeline Stage должна:

* соответствовать PipelineStage contract;
* быть зарегистрирована через PipelineRegistry;
* иметь уникальное имя;
* иметь детерминированную позицию;
* не дублировать существующую stage.

---

## 5.5 Stage Adapter

Если существующий Project Sync module
не реализует PipelineStage напрямую,
допускается использование Stage Adapter.

Adapter должен:

* сохранять существующую бизнес-логику;
* обеспечивать PipelineStage contract;
* не создавать второй execution contour;
* не создавать второй registry.

---

# 6. PIPELINE_ENGINE_RULES

## 6.1 PipelineExecutor

`PipelineExecutor` является каноническим
механизмом выполнения зарегистрированных стадий.

Executor отвечает за:

* последовательное выполнение;
* сбор результатов;
* нормализацию результатов;
* обработку исключений;
* передачу ошибок в PipelineContext.

---

## 6.2 PipelineContext

`PipelineContext` является каноническим
контейнером общего состояния Pipeline.

Он может содержать:

* project path;
* shared data;
* generated artifacts;
* metadata;
* execution errors.

---

## 6.3 PipelineResult

Каждая stage должна возвращать
совместимый результат PipelineResult.

Стандартные поля:

* stage;
* success;
* data;
* message;
* errors;
* metadata.

---

## 6.4 PipelineReport

`PipelineReport` является канонической
моделью итогового Pipeline Report.

PipelineReport интегрирован
в canonical runtime contour.

Runner должен использовать PipelineReport
как единую модель итогового отчёта.

PipelineReport используется для формирования
и сохранения:

`pipeline_report.json`

Канонические поля:

* pipeline;
* version;
* status;
* created;
* stages;
* results;
* errors.

Вторичная независимая модель итогового
JSON report запрещена.

PipelineReport integration:

COMPLETED

---

# 7. MIGRATION_LIFECYCLE_RULES

## 7.1 Separation Of Concerns

Migration Lifecycle отделён от
количества registered Pipeline stages.

Следующие операции являются частью
Migration Lifecycle:

* Migration Planning;
* Migration Decision;
* Approval Control;
* Document Update;
* Migration Execution;
* Post Migration Validation;
* Snapshot Creation.

Они не являются отдельными
registered Pipeline stages,
если прямо не включены в canonical registry.

---

## 7.2 Migration Stage

`MigrationStage` является зарегистрированной
Pipeline Stage.

Canonical name:

migration

---

## 7.3 Post Migration Validation Stage

`PostMigrationValidationStage`
является зарегистрированной Pipeline Stage.

Canonical name:

post_migration_validation

---

## 7.4 Migration Planning

Migration Planner должен:

* определить необходимость миграции;
* сформировать migration plan;
* определить затрагиваемые документы;
* определить действия;
* определить риск;
* определить необходимость approval.

---

## 7.5 Migration Decision

Migration Decision должен быть
отделён от Approval Control.

Допустимые состояния:

* PENDING;
* WAITING_APPROVAL;
* APPROVED;
* REJECTED.

Наличие approval artifact не должно
автоматически изменять Migration Decision.

---

# 8. APPROVAL_RULES

## 8.1 Explicit Approval

Approval должен быть явным.

Automatic approval запрещён.

---

## 8.2 Approval Gate

Approval Gate является обязательным
контролем перед выполнением
Document Update / Migration Execution.

---

## 8.3 No Approval Bypass

Migration Executor не имеет права
обходить Approval Gate.

Наличие:

* migration_plan.json;
* migration_decision.json;
* migration_approval.json

не должно автоматически означать,
что миграция разрешена к исполнению.

---

## 8.4 Decision And Approval Separation

Следует различать:

Migration Decision

и

Approval.

Например:

Migration Decision:

WAITING_APPROVAL / PENDING

Approval artifact:

APPROVED

не означает автоматически:

Migration Execution:

APPROVED

Текущее состояние Decision является
обязательным условием контроля исполнения.

---

# 9. DOCUMENT_UPDATE_RULES

## 9.1 Controlled Updates

Обычные корректировки документации,
не меняющие архитектурные контракты,
не требуют полного Migration Lifecycle.

Migration context обязателен только для
существенных архитектурных или миграционных
изменений, которые действительно затрагивают
Project Sync / Migration Lifecycle.

---
## 9.2 Backup Before Update

Отдельная резервная копия перед каждым
обычным изменением документа не обязательна,
если изменение находится под контролем Git.

Дополнительный backup требуется для
рискованных массовых изменений,
миграций или операций вне безопасного
Git rollback workflow.

---
## 9.3 Explicit Targets

Document Update должен работать
только с явно определёнными
целевыми документами.

---

## 9.4 Content Preservation

Если migration plan содержит:

`preserve_document_content`

система не должна изменять содержание
без явно определённого update operation.

---

# 10. POST_MIGRATION_VALIDATION_RULES

Post Migration Validation не должна
выдавать состояние `VALIDATED`,
если Migration Execution фактически
не была выполнена успешно.

Проверяются:

* execution status;
* documents;
* backups;
* execution errors.

Допустимые результаты должны
соответствовать фактическому состоянию.

---

# 11. SNAPSHOT_RULES

## 11.1 Snapshot Purpose

Snapshot является контрольной точкой
состояния Document Registry.

---

## 11.2 Snapshot Does Not Replace Documentation

Snapshot не заменяет:

* PROJECT_STATE.md;
* PROJECT_RULES.md;
* ARCHITECTURE;
* ROADMAP;
* PROJECT_SYNC documentation.

---

## 11.3 Snapshot Lifecycle

Snapshot Creation после Migration
является частью Migration Lifecycle
и должна выполняться после успешной:

Migration Execution

и

Post Migration Validation.

Ручной запуск Snapshot Creator
сам по себе не означает успешного
завершения Migration Lifecycle.

---

# 12. STATE_DOCUMENT_RULES

## 12.1 Project State

`PROJECT_STATE.md` является главным индексом
текущего состояния проекта.

---

## 12.2 State Synchronization

State Intelligence и State Synchronization
являются автоматизированными подсистемами.

При результате:

`NOT_REQUIRED`

изменение State Documents
не требуется.

---

## 12.3 Manual Project State Rewrite

На текущем этапе:

Project State automatic rewrite:

NOT FULLY AUTOMATED

Pipeline может:

* анализировать;
* планировать;
* валидировать;
* формировать отчёты.

Но автоматическая перезапись
`PROJECT_STATE.md` из `pipeline_report.json`
ещё не является полностью реализованной.

Поэтому изменение документированного
состояния должно сопровождаться
явной актуализацией PROJECT_STATE.md.

---

# 13. VALIDATION_RULES

Перед фиксацией архитектурного изменения
необходимо проверять:

* Python compilation;
* import integrity;
* Pipeline Registry;
* Pipeline Executor;
* Pipeline execution;
* generated reports;
* documentation validation;
* project health.

Канонический запуск Pipeline:

```powershell
cd C:\BybitScanner
python -m tools.project_sync.project_sync_runner
```

---

# 14. ERROR_HANDLING_RULES

Критические ошибки должны быть
явно зарегистрированы.

Pipeline не должен скрывать исключения
или преобразовывать фактический failure
в ложный SUCCESS.

Stage errors должны передаваться
через PipelineResult и PipelineContext.

---

# 15. VERSIONING_RULES

Версия документа увеличивается
при изменении его нормативного содержания.

Изменение версии должно сопровождаться:

* новой датой;
* причиной изменения;
* сохранением document_id;
* актуализацией зависимых документов
  при необходимости.

---

# 16. CHANGE_CONTROL_RULES

Перед изменением учитываются только те
контроли, которые действительно относятся
к масштабу и риску изменения.

Обычное локальное изменение кода или документа
не требует автоматического запуска:

* impact analysis;
* migration plan;
* approval workflow;
* Project Sync Pipeline.

Полный Change Control применяется при:

* изменении архитектурных контрактов;
* массовой миграции;
* изменении canonical Pipeline;
* рискованном изменении нескольких подсистем.

---
# 17. ARTIFACT_RULES

## 17.1 Artifact First

При создании или изменении технического
артефакта сначала должен быть определён
готовый результат.

---

## 17.2 Minimal Artifact Transfer

Артефакты передаются в минимально необходимом объёме.

Полные файлы не должны повторно передаваться,
если актуальная версия доступна через GitHub
или изменение может быть безопасно выполнено
точечной автоматизированной командой.

Полный артефакт используется только при необходимости.

---
## 17.3 No Empty Placeholder Modules

Пустые `.py` файлы не должны считаться
реализованными архитектурными компонентами.

Создание placeholder-модуля допустимо
только как явно контролируемый промежуточный
шаг и не должно фиксироваться как
`IMPLEMENTED` до фактической реализации.

---

# 18. COMMUNICATION_RULES

Коммуникация при сопровождении проекта
должна быть краткой и операционной.

Предпочтительный формат:

1. текущая стадия;
2. конкретная команда;
3. ожидаемый результат.

Не следует добавлять длинные
необязательные объяснения,
если они не требуются для выполнения
текущего шага.

---

# 19. COMMAND_RULES

Для запуска Project Sync:

```powershell
cd C:\BybitScanner
python -m tools.project_sync.project_sync_runner
```

Для проверки Python-модуля:

```powershell
python -m py_compile <полный_путь_к_файлу>
```

Для открытия документа:

```powershell
notepad C:\BybitScanner\DOCUMENTS\<DOCUMENT>.md
```

---

# 20. ARTIFACT_DELIVERY_STATE_RULES

## 20.1 Delivery State

Ассистент обязан логически отслеживать
состояние текущей последовательности
выдачи артефактов.

Минимальное состояние должно включать:

* current_artifact;
* last_delivered_artifact;
* pending_artifacts;
* completed_artifacts.

---

## 20.2 Artifact Identity

Артефакт идентифицируется как минимум
по каноническому имени и пути.

Например:

```text
PROJECT_RULES.md
C:\BybitScanner\DOCUMENTS\PROJECT_RULES.md
```

и

```text
ASSISTANT_PROTOCOL.md
C:\BybitScanner\DOCUMENTS\ASSISTANT_PROTOCOL.md
```

являются разными артефактами.

---

## 20.3 Sequential Delivery

Если пользователь запросил несколько
артефактов последовательно:

* каждый выданный артефакт помечается как completed;
* следующий ответ не должен возвращаться
  к completed artifact;
* переход выполняется к следующему
  незавершённому artifact.

---

## 20.4 Last Artifact Protection

После выдачи артефакта он считается
завершённым для текущего рабочего шага.

Нельзя повторно выдавать или повторно
открывать тот же артефакт в следующем
сообщении, если:

* пользователь явно не запросил его повторно;
* артефакт не был изменён;
* не была создана новая версия;
* текущая задача не требует его повторной проверки.

---

## 20.5 Command `э`

Команда:

```text
э
```

означает:

`CONTINUE_CURRENT_WORKFLOW`

Она запрещает:

* повторную выдачу последнего артефакта;
* повторение последней команды;
* возврат к уже завершённому артефакту;
* повторное открытие уже обработанного файла.

При наличии незавершённых артефактов
команда `э` означает переход
к следующему незавершённому артефакту.

---

## 20.6 Pending Artifact Priority

Если в текущей рабочей последовательности
существует явно определённый `pending_artifact`,
он имеет приоритет над любым ранее выданным
артефактом.

Ассистент не должен самостоятельно
заменять `pending_artifact` на предыдущий
`completed_artifact`.

---

## 20.7 No Rewind

Workflow не должен автоматически
возвращаться назад по цепочке выдачи.

Переход:

```text
PROJECT_RULES
↓
ASSISTANT_PROTOCOL
```

не может быть автоматически заменён на:

```text
PROJECT_RULES
↓
PROJECT_RULES
```

---

## 20.8 Explicit Re-request

Повторная выдача завершённого артефакта
допускается только при явном запросе пользователя,
например:

* "повтори PROJECT_RULES";
* "выдай PROJECT_RULES ещё раз";
* "актуализируй PROJECT_RULES";
* "открой PROJECT_RULES повторно".

Команда `э` не является таким запросом.

---

## 20.9 Artifact Completion

После полного предоставления
готового артефакта он считается
`COMPLETED`, даже если пользователь
после этого отправил `э`.

Команда `э` должна использоваться
для перехода к следующему этапу,
а не для повторного подтверждения
последнего результата.

---

## 20.10 GitHub First File Access

GitHub является предпочтительным источником
чтения файлов, уже зафиксированных в репозитории.

Если актуальный файл доступен через GitHub,
ассистент не должен просить пользователя:

* открывать его через `notepad`;
* копировать его содержимое в чат;
* повторно передавать неизменённый файл.

`notepad` используется только для локальных файлов,
которые отсутствуют в GitHub,
имеют незапушенные изменения
или требуют визуальной проверки пользователем.

---
## 20.11 Context Efficiency

Ассистент должен минимизировать расход контекста.

Запрещено без необходимости:

* повторно читать большие документы;
* повторно выдавать полные файлы;
* выводить большие tree/snapshot;
* выполнять Project Sync только ради восстановления контекста;
* сообщать оценку остатка контекста по фиксированному расписанию.

Контроль контекста выполняется только
при реальном риске его нехватки
или по прямому запросу пользователя.

## 20.12 GitHub First / Minimal Artifact Transfer

При наличии актуального GitHub repository:

1. сначала используется GitHub;
2. читаются только необходимые файлы или участки;
3. локальное содержимое запрашивается только при расхождении с GitHub;
4. небольшие изменения выполняются минимальным способом;
5. полный файл передаётся только при необходимости;
6. после проверенных изменений используется Git commit как checkpoint.

Цель:

максимизировать полезное время разработки
и минимизировать передачу дублирующего контента.

---
# 21. CURRENT_ARCHITECTURAL_BASELINE

Current Project Sync status:

HEALTHY

Pipeline Engine:

OPERATIONAL

Pipeline Engine Version:

3.2

Canonical registered stages:

12

Pipeline Registry:

ACTIVE

Pipeline Executor:

ACTIVE

PipelineStage:

ACTIVE

PipelineContext:

ACTIVE

PipelineResult:

ACTIVE

PipelineReport:

ACTIVE

PipelineReport Integration:

COMPLETED

MigrationStage:

REGISTERED

PostMigrationValidationStage:

REGISTERED

Migration Lifecycle:

CONTROLLED

Approval Gate:

ACTIVE

Automatic Approval:

DISABLED

---

# 22. CURRENT_DOCUMENTATION_BASELINE

Registered documents:

41

Validated documents:

41

Critical documentation errors:

0

Documentation health:

HEALTHY

Current warnings:

* ASSISTANT_PROTOCOL.md;
* PROJECT_RULES.md;
* TRADINGVIEW_JSON_CONTRACT.md.

Warnings do not prevent Pipeline execution.

---

# 23. CURRENT_MIGRATION_BASELINE

Migration Plan:

READY

Migration Decision:

WAITING_APPROVAL

Migration Decision Value:

PENDING

Approval Artifact:

APPROVED

Document Update:

NOT_EXECUTED

Migration Execution:

NOT_EXECUTED

Post Migration Validation:

NOT_EXECUTED

Automatic Approval:

DISABLED

Execution bypass:

PROHIBITED

---

# 24. CURRENT_AUTOMATION_BASELINE

Project Sync Analysis:

AUTOMATED

State Intelligence:

AUTOMATED

State Synchronization Analysis:

AUTOMATED

Migration Planning:

AUTOMATED

Migration Decision:

AUTOMATED

Approval Control:

AUTOMATED

Migration Execution Gate:

AUTOMATED

Pipeline Reporting:

AUTOMATED

PipelineReport Integration:

COMPLETED

PROJECT_STATE.md Rewrite:

NOT FULLY AUTOMATED

---

# 25. PROHIBITED_ARCHITECTURAL_PATTERNS

Запрещается:

* создавать второй Pipeline Registry;
* создавать второй canonical stage list;
* создавать второй Pipeline Executor;
* создавать параллельный execution contour;
* обходить Approval Gate;
* включать automatic approval;
* считать approval artifact достаточным
  для исполнения при WAITING_APPROVAL/PENDING;
* выполнять Document Update без backup;
* объявлять Post Migration Validation
  успешной без успешной Migration Execution;
* считать пустой модуль реализованным;
* создавать дублирующие документы без
  архитектурной необходимости;
* изменять канонические документы
  неконтролируемым способом;
* повторно выдавать completed artifact
  без явного запроса пользователя;
* трактовать `э` как запрос на повторную
  выдачу последнего артефакта;
* возвращаться к completed artifact
  при наличии pending artifact;
* представлять приблизительную оценку
  остатка контекста как точное системное
  значение.

---

# 26. CURRENT_DEVELOPMENT_DIRECTION

Основное направление:

Controlled Migration Lifecycle

Текущая архитектурная задача:

Controlled Migration Execution

Текущий архитектурный статус:

Pipeline Architecture Consolidation — COMPLETED

PipelineReport Integration — COMPLETED

Цель текущего этапа:

обеспечить контролируемое прохождение
Migration Lifecycle без нарушения
Approval Gate и Single Source Of Truth.

Ограничения:

* не изменять canonical stage count;
* не создавать второй registry;
* не создавать второй execution contour;
* не изменять существующий Migration Gate;
* не нарушать Stage Contract;
* не нарушать Single Source Of Truth;
* не выполнять Migration Execution
  при Migration Decision = WAITING_APPROVAL / PENDING.

---

# 27. RELATED_DOCUMENTS

project_state:

DOCUMENTS/PROJECT_STATE.md

assistant_protocol:

DOCUMENTS/ASSISTANT_PROTOCOL.md

architecture:

DOCUMENTS/ARCHITECTURE.md

roadmap:

DOCUMENTS/ROADMAP.md

project_sync:

DOCUMENTS/PROJECT_SYNC.md

snapshot:

DOCUMENTS/SNAPSHOT.md

---

# 28. VERSION_UPDATE_REASON

from:

PROJECT_RULES v5.2

to:

PROJECT_RULES v5.3

reason:

* добавлено обязательное правило
  Context Window Monitoring;
* закреплена выдача приблизительного
  остатка доступного контекста в процентах;
* уточнено, что показатель Context Remaining
  является приблизительной оценкой и не является
  точным системным значением;
* определено назначение показателя для контроля
  длительных рабочих сессий;
* предусмотрено предупреждение о риске потери
  рабочего контекста при существенном снижении
  остатка;
* закреплён приоритет сохранения состояния,
  незавершённых этапов и необходимых артефактов
  при снижении остатка контекста;
* запрещено использовать Context Window Monitoring
  вместо требуемого технического результата;
* добавлен соответствующий запрет в
  PROHIBITED_ARCHITECTURAL_PATTERNS;
* сохранены все правила PROJECT_RULES v5.2;
* обновлена версия PROJECT_RULES до 5.3.

---

# FINAL_NOTE

PROJECT_RULES v5.3 является нормативной
базой текущего архитектурного состояния
BybitScanner Project Sync Framework.

Канонический operational Pipeline:

12 stages

Pipeline:

HEALTHY

Pipeline Engine:

OPERATIONAL

Pipeline Engine Version:

3.2

Pipeline Registry:

Single Source Of Truth

PipelineReport:

ACTIVE

PipelineReport Integration:

COMPLETED

Migration Lifecycle:

CONTROLLED

Approval Gate:

ACTIVE

Automatic Approval:

DISABLED

Migration Execution:

BLOCKED BY CURRENT MIGRATION DECISION

Documentation:

41 registered / 41 validated

Critical Errors:

0

Artifact Delivery:

STATEFUL

Sequential Artifact Delivery:

ENFORCED

Context Window Monitoring:

ENFORCED

Context Remaining Reporting:

APPROXIMATE PERCENTAGE

Current architecture:

STABLE

# END_OF_DOCUMENT
