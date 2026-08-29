# BybitScanner — Architecture

Version:

5.1

Date:

2026-08-08

Document Type:

ARCHITECTURE_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-ARCHITECTURE-002

purpose:

Фиксирует архитектурную модель BybitScanner,
границы подсистем, зависимости,
контракты,
Project Sync Framework,
архитектуру автоматизации сопровождения проекта
и фактически подтверждённое расположение
архитектурных и технических компонентов проекта.

machine_readable:

true

parser_version:

1.0

---

# PROJECT_ROOT

canonical_project_root:

C:\BybitScanner

rule:

Все относительные пути проекта
интерпретируются относительно
canonical_project_root.

---

# DOCUMENTATION_ROOT

canonical_documentation_root:

C:\BybitScanner\DOCUMENTS

status:

ACTIVE

role:

Единое физическое расположение
официальной технической документации проекта.

Official technical documents:

* ARCHITECTURE.md
* ARCHITECTURE_RULES.md
* ARCHITECTURE_RULE_ENGINE.md
* ASSISTANT_PROTOCOL.md
* CHANGELOG.md
* CODE_RULES.md
* DECISION_LOG.md
* DEVELOPMENT_GUIDE.md
* DOCUMENTATION_RULES.md
* GLOSSARY.md
* LAYER_REGISTRY.md
* MODULE_REGISTRY.md
* PROJECT_CONTRACTS.md
* PROJECT_MAP.md
* PROJECT_RULES.md
* PROJECT_STANDARDS.md
* PROJECT_STATE.md
* PROJECT_SYNC.md
* PROJECT_TREE.md
* ROADMAP.md
* SNAPSHOT.md
* SUBSYSTEM_REGISTRY.md
* WORKFLOW_RULES.md

State documents:

DOCUMENTS\STATE*

Project Sync documents:

DOCUMENTS\PROJECT_SYNC_*

---

# DOCUMENT_OPENING_RULE

canonical_command_pattern:

notepad C:\BybitScanner\DOCUMENTS<DOCUMENT_NAME>

Architecture:

notepad C:\BybitScanner\DOCUMENTS\ARCHITECTURE.md

Project State:

notepad C:\BybitScanner\DOCUMENTS\PROJECT_STATE.md

Project Tree:

notepad C:\BybitScanner\DOCUMENTS\PROJECT_TREE.md

Project Rules:

notepad C:\BybitScanner\DOCUMENTS\PROJECT_RULES.md

Project Sync:

notepad C:\BybitScanner\DOCUMENTS\PROJECT_SYNC.md

Rule:

Ассистент не должен предлагать
открытие официальной технической документации
через путь относительно корня проекта,
если фактическое расположение документа
находится в DOCUMENTS.

Canonical rule:

Project Root

C:\BybitScanner

↓

Documentation Root

C:\BybitScanner\DOCUMENTS

↓

Technical Documentation

.md

---

# VERIFIED_PROJECT_ROOT_STRUCTURE

Фактически подтверждены следующие
директории непосредственно в корне
C:\BybitScanner:

* analyzer
* Backups
* charts
* contracts
* debug
* DOCUMENTS
* geometry
* reports
* signal
* signals
* structures
* tests
* tools
* tradingview
* training
* venv
* wedge

Important:

geometry является корневым
проектным Python-пакетом:

C:\BybitScanner\geometry

geometry не находится внутри
DOCUMENTS или другого подкаталога.

wedge является отдельным
корневым Python-пакетом:

C:\BybitScanner\wedge

---

# GEOMETRY_ROOT_LOCATION

canonical_path:

C:\BybitScanner\geometry

status:

ACTIVE

Package:

geometry

Verified modules:

* apex.py
* candidate.py
* characterization.py
* compression.py
* engine.py
* evaluation.py
* filter.py
* model.py
* ranking.py
* touches.py
* trendline.py
* **init**.py

Debug package:

C:\BybitScanner\geometry\debug

Verified modules:

* inspector.py
* logger.py
* **init**.py

Validation package:

C:\BybitScanner\geometry\validation

Verified modules:

* geometry.py
* slopes.py
* apex.py
* apex_quality.py
* compression.py
* touches.py
* **init**.py

---

# WEDGE_ROOT_LOCATION

canonical_path:

C:\BybitScanner\wedge

status:

ACTIVE

Package:

wedge

Verified modules:

* analyzer.py
* classifier.py
* detector.py
* quality.py
* result.py
* scoring.py
* **init**.py

Package entry point:

wedge.analyzer.analyze_wedge()

Public package entry point:

wedge.analyze_wedge

---

# ARCHITECTURE_IDENTITY

system:

BybitScanner Architecture Model

principle:

Architecture First

role:

Определяет структуру системы,
ответственность компонентов,
правила взаимодействия
и направление развития
архитектуры.

---

# ARCHITECTURE_MODEL

BybitScanner

├── Trading Intelligence

└── Project Intelligence

---

# TRADING_INTELLIGENCE

Pipeline:

Market Data

↓

Analyzer

↓

Pivot Detection

↓

Geometry Engine

↓

Wedge Detection

↓

Classifier

↓

Quality

↓

Score

↓

Confirmation

↓

Signal Layer

↓

Automation

---

# TRADING_LAYERS

## Market Data Layer

status:

ACTIVE

responsibility:

Получение рыночных данных.

input:

Bybit Futures API

output:

OHLCV, symbols, timeframe data

---

## Analyzer Layer

status:

ACTIVE

responsibility:

Координация полного цикла
анализа рыночной структуры.

Restrictions:

Analyzer не выполняет
самостоятельно:

* геометрическую математику;
* построение трендовых линий;
* поиск Pivot;
* классификацию структуры;
* расчёт score;
* торговую логику.

Analyzer является
координирующим слоем.

---

# GEOMETRY_ENGINE

status:

ACTIVE

physical_root:

C:\BybitScanner\geometry

entry_point:

geometry.engine.analyze_geometry()

responsibility:

Математическое построение
и оценка геометрических кандидатов.

Architecture:

Pivot Points

↓

Candidate Generation

↓

Candidate Filtering

↓

Candidate Pairs

↓

Geometry Evaluation

↓

Validation Gate

↓

Geometry Ranking

↓

Validated GeometryModel

Important:

Geometry Engine самостоятельно
не передаёт в Geometry Ranking
геометрию, не прошедшую
Validation Gate.

---

# GEOMETRY_ENGINE_MODULES

Verified modules:

* geometry.apex
* geometry.candidate
* geometry.characterization
* geometry.compression
* geometry.engine
* geometry.evaluation
* geometry.filter
* geometry.model
* geometry.ranking
* geometry.touches
* geometry.trendline
* geometry.validation

Active responsibilities:

* candidate generation;
* candidate filtering;
* candidate pair evaluation;
* Apex calculation;
* Compression calculation;
* Touch analysis;
* Geometry validation;
* Geometry ranking;
* GeometryModel creation.

---

# GEOMETRY_ENGINE_EXECUTION_FLOW

analyze_geometry(highs, lows)

↓

Input Gate

minimum:

4 Pivot High points

and

4 Pivot Low points

↓

Candidate Generation

↓

Candidate Filtering

↓

Upper Candidate × Lower Candidate

↓

evaluate_candidate_pair()

↓

Apex

↓

Compression

↓

Touches

↓

Validation

↓

Validation Gate

↓

Geometry Ranking

↓

best_geometry

↓

GeometryModel or None

---

# GEOMETRY_CANDIDATE_LAYER

module:

geometry.candidate

status:

ACTIVE

responsibility:

Генерация возможных трендовых линий
из Pivot точек.

Input:

Pivot points

Process:

Pivot Points

↓

Combinations

↓

fit_trendline()

↓

Candidate

Restrictions:

Candidate layer не выполняет:

* определение клина;
* Validation;
* Quality;
* Score;
* Signal;
* торговую логику.

---

# GEOMETRY_FILTER_LAYER

module:

geometry.filter

status:

ACTIVE

responsibility:

Фильтрация кандидатов
трендовых линий.

Checks:

* корректность candidate;
* наличие line;
* наличие error_mean;
* допустимая средняя ошибка;
* сортировка по error_mean;
* ограничение количества кандидатов.

Current defaults:

max_lines:

50

max_error:

1.0

Error boundary:

inclusive

Accepted condition:

error_mean <= max_error

Rejected condition:

error_mean > max_error

---

# GEOMETRY_FILTER_VERIFIED_BEHAVIOR

status:

VERIFIED

verification_date:

2026-08-08

Verified through direct runtime tests:

1.

Input:

points:

1, 1

2, 2

3, 3

4, 4

Result:

error_mean:

0.0

Candidate:

ACCEPTED

Filtered:

1

---

2.

Input:

points:

1, 1

2, 2.1

3, 2.9

4, 4

Result:

error_mean:

0.06

Candidate:

ACCEPTED

Filtered:

1

---

3.

Input:

points:

1, 1

2, 3

3, 1

4, 5

Result:

error_mean:

1.0

Candidate:

ACCEPTED

Filtered:

1

---

4.

Input:

points:

1, 1

2, 3.01

3, 1

4, 5.01

Result:

error_mean:

1.004

Candidate:

REJECTED

Filtered:

0

---

Verified boundary:

max_error:

1.0

Boundary behavior:

1.0 <= 1.0

↓

ACCEPT

1.004 > 1.0

↓

REJECT

Architectural conclusion:

Candidate Filtering
использует включительную
верхнюю границу допустимой
средней ошибки.

The filtering contract is:

error_mean <= max_error

---

# GEOMETRY_EVALUATION_LAYER

module:

geometry.evaluation

status:

ACTIVE

responsibility:

Сбор полной геометрической модели
из пары верхней и нижней трендовых линий.

Process:

Upper Candidate

*

Lower Candidate

↓

Apex

↓

Compression

↓

Touches

↓

Validation

↓

GeometryModel

Restrictions:

Evaluation не выбирает
лучшего кандидата.

Выбор выполняется
Geometry Ranking.

Evaluation формирует
GeometryModel даже в случае,
если отдельные validation checks
не прошли.

Финальное решение о допуске
к Geometry Ranking выполняется
Geometry Engine.

---

# GEOMETRY_APEX

module:

geometry.apex

status:

ACTIVE

responsibility:

Математическое пересечение
двух трендовых линий.

Calculates:

* intersection index;
* intersection price;
* slope difference;
* valid_intersection.

Parallel lines:

При отсутствии
математического пересечения
возвращается None.

---

# GEOMETRY_COMPRESSION

module:

geometry.compression

status:

ACTIVE

responsibility:

Измерение изменения ширины
структуры между двумя линиями.

Calculates:

* start_width;
* end_width;
* compression_percent;
* is_compressing.

Restrictions:

Compression module
не выполняет Validation.

Не определяет:

* pattern;
* score;
* signal.

---

# GEOMETRY_TOUCHES

module:

geometry.touches

status:

ACTIVE

responsibility:

Анализ контакта Pivot точек
с трендовыми линиями.

Functions:

* calculate_line_error();
* count_touches();
* analyze_touches();

Calculates:

* mean_error;
* max_error;
* individual errors;
* upper_touches;
* lower_touches;
* total_touches;
* touch validity.

Current adaptive tolerance:

0.006

meaning:

0.6%

Touch validity:

upper_touches >= 2

and

lower_touches >= 2

---

# GEOMETRY_MODEL

module:

geometry.model

status:

ACTIVE

role:

Единый контракт хранения
геометрической модели.

Constructor fields:

* upper_line;
* lower_line;
* apex;
* compression;
* touches;
* validation;
* candidate_points.

Serialization:

to_dict()

GeometryModel не содержит:

* trading Score;
* Signal;
* trading logic.

GeometryModel является
основным объектом передачи
из Geometry Layer в Wedge Layer.

---

# GEOMETRY_VALIDATION_ARCHITECTURE

Geometry primitives:

geometry.apex

geometry.compression

geometry.touches

↓

Validation Package:

geometry.validation

↓

Validation Engine v2

↓

ValidationResult

↓

GeometryModel.validation

Principle:

Расчёт геометрических primitives
и их Validation являются
разделёнными ответственностями.

Validation не рассчитывает
геометрические primitives
самостоятельно.

---

# GEOMETRY_VALIDATION

module:

geometry.validation

physical_path:

C:\BybitScanner\geometry\validation

status:

ACTIVE

architecture:

PACKAGE

role:

Пакет проверки
геометрической структуры.

Validation Engine v2
является отдельным пакетом
с независимыми диагностическими
компонентами.

Verified package structure:

geometry.validation

├── **init**.py
├── geometry.py
├── slopes.py
├── apex.py
├── apex_quality.py
├── compression.py
├── touches.py

---

# GEOMETRY_VALIDATION_COORDINATOR

module:

geometry.validation.geometry

status:

ACTIVE

responsibility:

Главный координатор
Validation Engine v2.

Function:

validate_geometry()

Inputs:

* upper_line;
* lower_line;
* apex;
* compression;
* touches;
* start_index;
* end_index.

Validation checks:

* slopes;
* apex;
* apex_quality;
* compression;
* touches.

Output contract:

{
"valid": bool,
"checks": {
"name": {
"valid": bool,
"reason": str,
"details": {}
}
},
"failed_checks": []
}

Validation result:

valid:

True

только если все
registered validation checks
имеют:

valid == True

---

# GEOMETRY_VALIDATION_COMPONENTS

## Slopes Validation

module:

geometry.validation.slopes

responsibility:

Проверка допустимого
соотношения наклонов
верхней и нижней линий.

Status:

ACTIVE

---

## Apex Validation

module:

geometry.validation.apex

responsibility:

Проверка Apex относительно
границ анализируемой структуры.

Status:

ACTIVE

---

## Apex Quality

module:

geometry.validation.apex_quality

responsibility:

Дополнительная диагностическая
оценка качества положения Apex.

Status:

ACTIVE

classification:

Internal diagnostic component

Important:

Apex Quality участвует
в Validation Engine,
но не является самостоятельным
публичным API верхнего уровня.

---

## Compression Validation

module:

geometry.validation.compression

responsibility:

Проверка наличия
и достаточности Compression.

Input:

compression

Validation conditions:

* compression data exists;
* structure is compressing;
* compression_percent
  достигает minimum_percent.

Default:

minimum_percent:

5

Validation flow:

compression is missing

↓

INVALID

structure is not compressing

↓

INVALID

compression_percent < 5

↓

INVALID

compression_percent >= 5

↓

VALID

Diagnostic output:

{
"valid": bool,
"reason": str,
"details": dict
}

Diagnostics:

* compression_percent;
* is_compressing;
* minimum_percent.

Important boundary:

geometry.compression

↓

рассчитывает Compression

geometry.validation.compression

↓

валидирует Compression

Validation module
не рассчитывает Compression
самостоятельно.

---

## Touches Validation

module:

geometry.validation.touches

responsibility:

Проверка достаточности
контактов Pivot точек
с трендовыми линиями.

Status:

ACTIVE

---

# VALIDATION_GATE

location:

geometry.engine

status:

ACTIVE

responsibility:

Не допускать невалидную
GeometryModel к Geometry Ranking
и последующей передаче
в Wedge Layer.

Decision:

validation.valid == True

↓

candidate допускается

validation.valid == False

↓

candidate отбрасывается

Important:

Geometry Engine использует
Validation как Gate до Ranking.

Следствие:

Текущий основной runtime-путь
не передаёт в Wedge Layer
GeometryModel с:

validation.valid == False

---

# GEOMETRY_RANKING

module:

geometry.ranking

status:

ACTIVE

responsibility:

Выбор наиболее качественной
валидированной геометрической модели
из набора evaluated candidates.

Important distinction:

Geometry Ranking

не является

Trading Score.

Ranking выполняется только
после Validation Gate.

---

# GEOMETRY_ENGINE_RETURN_CONTRACT

module:

geometry.engine

function:

analyze_geometry()

Input:

highs

lows

Minimum input:

4 Pivot High points

and

4 Pivot Low points

Return:

GeometryModel

или

None

Return conditions:

GeometryModel:

если найден кандидат,
прошедший Validation Gate
и имеющий лучший
Geometry Ranking score.

None:

если:

* недостаточно Pivot points;
* отсутствуют candidates;
* candidates не прошли filtering;
* пары candidates не сформировали geometry;
* ни одна GeometryModel
  не прошла Validation Gate.

---

# WEDGE_PATTERN_LAYER

status:

ACTIVE

physical_root:

C:\BybitScanner\wedge

responsibility:

Интерпретация GeometryModel
как графической структуры.

Current pattern family:

Wedge

---

# WEDGE_ANALYZER

module:

wedge.analyzer

status:

ACTIVE

entry_point:

analyze_wedge()

responsibility:

Координация полного
Wedge analysis pipeline.

Pipeline:

highs

*

lows

↓

analyze_geometry()

↓

GeometryModel

↓

Detector

↓

Quality

↓

Classifier

↓

Score

↓

Result

Restrictions:

Analyzer не содержит:

* собственной геометрической математики;
* построения линий;
* поиска Pivot;
* самостоятельного определения
  типа структуры;
* торговой логики.

---

# WEDGE_RESPONSIBILITY_CHAIN

Canonical architecture:

GeometryModel

↓

Detector

↓

Quality

↓

Classifier

↓

Score

↓

Result

Important:

Classifier получает
результат Detector.

Quality получает
geometry.validation.

Score получает:

* pattern;
* compression;
* touches;
* quality.

Result объединяет
итоговые данные анализа.

---

# WEDGE_DETECTOR

module:

wedge.detector

status:

ACTIVE

responsibility:

Первичное определение,
похожа ли GeometryModel
на структурный кандидат.

Detector performs:

* наличие GeometryModel;
* наличие upper_line;
* наличие lower_line;
* анализ slope signs;
* анализ compression;
* анализ touches;
* анализ apex;
* диагностическое использование validation.

Pattern candidates:

* Falling Wedge;
* Rising Wedge;
* Triangle Compression;
* Unknown.

Detector не выполняет:

* Validation;
* Quality;
* Score;
* торговую логику.

Important:

Detector не заменяет
Geometry Validation.

Geometry Validation выполняется
в Geometry Engine до передачи
в Wedge Layer.

---

# WEDGE_QUALITY

module:

wedge.quality

status:

ACTIVE

responsibility:

Преобразование
geometry.validation
в структурную оценку качества.

Statuses:

VALID

↓

good

WARNING

↓

acceptable

INVALID

↓

bad

Important runtime boundary:

Geometry Engine в текущей архитектуре
отбрасывает GeometryModel,
если validation.valid == False.

Следовательно:

основной runtime-путь
wedge.quality получает
только GeometryModel,
прошедшие Validation Gate.

WARNING и INVALID
сохраняются как диагностические
состояния Quality Layer
и могут использоваться при
прямом вызове компонента
или при изменении Validation Gate
в будущем.

Quality не выполняет:

* геометрию;
* классификацию;
* Score;
* торговую логику;
* Signal.

---

# WEDGE_CLASSIFIER

module:

wedge.classifier

status:

ACTIVE

responsibility:

Интерпретация обнаруженного
паттерна.

Mappings:

Falling Wedge

↓

bullish

Rising Wedge

↓

bearish

Triangle Compression

↓

neutral

Unknown

↓

neutral

Classifier не выполняет:

* поиск структуры;
* геометрию;
* Validation;
* Score;
* торговую логику.

---

# WEDGE_SCORING

module:

wedge.scoring

status:

ACTIVE

responsibility:

Расчёт структурного
Wedge Score.

Maximum:

100

Breakdown:

structure:

40

compression:

25

touches:

20

quality:

15

Important distinction:

Wedge Structural Score

не является:

* Geometry Ranking;
* Confirmation;
* Final Signal Score.

Scoring не выполняет:

* поиск линий;
* классификацию;
* Signal;
* Telegram;
* торговое исполнение.

---

# WEDGE_RESULT

module:

wedge.result

status:

ACTIVE

responsibility:

Единый формат результата
Wedge analysis.

Contains:

* pattern;
* reason;
* score;
* geometry;
* geometry_version;
* validation;
* quality;
* warnings;
* score_breakdown;
* legacy geometry fields.

Geometry version:

v2

Legacy compatibility:

ACTIVE

Legacy fields include:

* high_slope;
* high_intercept;
* low_slope;
* low_intercept;
* compression;
* high_touches;
* low_touches.

Legacy compatibility
не изменяет GeometryModel
и не является отдельным
источником геометрической истины.

---

# WEDGE_PACKAGE_API

Package:

wedge

Public entry point:

analyze_wedge

Implementation:

wedge.analyzer.analyze_wedge

Package **init** exports:

analyze_wedge

---

# TRADING_LAYER_BOUNDARIES

Geometry:

Отвечает за:

* линии;
* Apex;
* Compression;
* Touches;
* Validation;
* GeometryModel.

Pattern:

Отвечает за:

* обнаружение;
* классификацию;
* качество;
* структурный score;
* результат.

Confirmation:

Отвечает за:

* breakout;
* volume;
* volatility.

Signal:

Отвечает за:

* торговый объект.

Automation:

Отвечает за:

* Telegram;
* внешнюю доставку.

Запрещено:

Geometry → Signal

Geometry → Telegram

Detector → Signal

Classifier → Signal

Quality → Signal

Scoring → Telegram

Result → Trading execution

---

# CONFIRMATION_ENGINE

status:

ACTIVE

responsibility:

Дополнительная проверка
торгового сценария после
структурного анализа.

Checks:

* breakout;
* volume;
* volatility.

---

# SCORE_SYSTEM

status:

ACTIVE

responsibility:

Формирование итоговой
оценки торгового сценария.

Important:

Нельзя смешивать:

Geometry Ranking

Wedge Structural Score

Confirmation

Final Signal Score

---

# SIGNAL_LAYER

status:

ACTIVE

responsibility:

Формирование торгового объекта.

Restrictions:

Не выполняет:

* геометрию;
* построение линий;
* поиск Pivot;
* поиск паттерна;
* geometry ranking;
* Telegram delivery.

---

# AUTOMATION_LAYER

status:

ACTIVE

responsibility:

Действия после формирования
торгового сигнала.

Current:

Telegram Notification

Supports:

* text;
* chart images.

---

# PROJECT_INTELLIGENCE

## Project Sync Framework

status:

ACTIVE

responsibility:

Автоматическое сопровождение
структуры проекта,
архитектуры,
документации
и изменений.

Architecture:

Project Files

↓

Registry

↓

Validation

↓

Dependency Analysis

↓

Impact Analysis

↓

Change Detection

↓

Health Monitoring

↓

State Intelligence

↓

Synchronization Planning

↓

Pipeline Engine

↓

Migration Control

↓

Snapshot System

↓

Reports

---

# PIPELINE_ENGINE

status:

ACTIVE

version:

3.3

role:

Единый исполнительный слой
Project Sync Framework.

architectural_principle:

Single Source Of Truth

runtime_status:

HEALTHY

canonical_registered_stages:

12

latest_document_registry_count:

41

---

# PIPELINE_REGISTRY

status:

ACTIVE

role:

Single Source Of Truth
для канонического состава
Pipeline Stage.

Canonical Stage Order:

Document Registry

↓

Validation

↓

Dependency Analysis

↓

Impact Analysis

↓

Snapshot Compare

↓

Health Check

↓

Synchronization Planning

↓

State Intelligence

↓

State Synchronization Planning

↓

State Synchronization

↓

Migration

↓

Post Migration Validation

Total:

12 registered stages

---

# PIPELINE_EXECUTOR

status:

ACTIVE

role:

Единый исполнительный контур
зарегистрированных Pipeline Stage.

Restrictions:

Не выполняет:

* регистрацию Stage;
* определение Pipeline composition;
* бизнес-анализ;
* migration approval;
* прямое изменение документов.

---

# PIPELINE_STAGE

status:

ACTIVE

role:

Базовый контракт
исполняемого Pipeline этапа.

Contract:

PipelineStage

Contains:

* name;
* handler;
* description;
* enabled;
* metadata;
* execute();
* to_dict().

---

# PIPELINE_CONTEXT

status:

ACTIVE

role:

Единый runtime-контекст
Pipeline execution.

Contract:

PipelineContext

Contains:

* project_path;
* data;
* artifacts;
* metadata;
* errors.

---

# PIPELINE_RESULT

status:

ACTIVE

role:

Единый контракт результата
исполнения Pipeline Stage.

Contract:

PipelineResult

Contains:

* stage;
* success;
* data;
* message;
* errors;
* metadata.

---

# PIPELINE_REPORT

status:

ACTIVE

integration_status:

COMPLETED

role:

Каноническая модель
итогового Pipeline Report.

Contract:

PipelineReport

Contains:

* pipeline;
* version;
* status;
* created;
* stages;
* results;
* errors.

Current:

PipelineReport model:

tools/project_sync/pipeline/report.py

Runtime artifact:

pipeline_report.json

---

# MIGRATION_LIFECYCLE

Migration Control является
отдельным контролируемым lifecycle.

Lifecycle:

Change Detection

↓

Impact Analysis

↓

Synchronization Planning

↓

Migration Planning

↓

Migration Decision

↓

Approval Control

↓

Document Update

↓

Migration Execution

↓

Post Migration Validation

↓

Snapshot Creation

---

# MIGRATION_SAFETY

Principle:

Explicit Approval Required

Automatic Approval:

DISABLED

Important distinctions:

APPROVED != EXECUTED

APPROVED != NO_UPDATES

NO_UPDATES != NOT_REQUIRED

NO_UPDATES != NOT_EXECUTED

Current confirmed execution state:

Migration Required:

true

Approval:

APPROVED

Migration Execution:

COMPLETED

Migration Execution Result:

NO_UPDATES

Post Migration Validation:

SUCCESS

Post Migration Validation State:

NO_UPDATES

Interpretation:

NO_UPDATES означает,
что контролируемый Migration Execution
был выполнен, но по результатам
исполнения не потребовалось
применять документальные обновления.

NO_UPDATES не означает:

* migration_required == false;
* migration execution не выполнялся;
* approval отсутствует;
* pipeline не был исполнен.

Known refinement target:

Усиление binding между:

migration_decision.json

↓

migration_approval.json

↓

migration_execution_report.json

Current:

decision_binding:

PRESENT

Stale Approval Protection:

PARTIAL

---

# MIGRATION_EXECUTION_STATE

status:

COMPLETED

result:

NO_UPDATES

migration_required:

true

approval_required:

true

approval:

APPROVED

automatic_approval:

DISABLED

execution_report:

migration_execution_report.json

post_migration_validation:

SUCCESS

post_migration_validation_state:

NO_UPDATES

Important:

Migration Execution является
отдельным этапом от Migration Decision
и Approval Control.

Наличие APPROVED является
условием авторизации,
но не заменяет факт выполнения.

Фактический результат текущего
контролируемого исполнения:

NO_UPDATES.

---

# SNAPSHOT_SYSTEM

status:

ACTIVE

responsibility:

Создание контрольных
состояний проекта.

Integration:

Migration Execution

↓

Post Migration Validation

↓

Snapshot Creation

↓

Pipeline Report

---

# ARCHITECTURE_CONTRACTS

Contracts:

GeometryModel

↓

ValidationResult

↓

PatternResult

↓

Signal Object

↓

Documentation Sync Contract

↓

PipelineContext

↓

PipelineResult

↓

PipelineReport

↓

Migration Contract

---

# DEPENDENCY_RULES

Rule 1:

Слои используют только
разрешённые зависимости.

Rule 2:

Каждый компонент имеет
одну ответственность.

Rule 3:

Изменение Pipeline Contract требует:

* dependency analysis;
* architecture update;
* documentation update;
* changelog update.

Rule 4:

Изменение Migration Contract требует:

* migration dependency analysis;
* architecture update;
* contract validation;
* documentation update;
* changelog update.

Rule 5:

Физическое расположение
официальных технических документов
определяется фактическим деревом проекта.

Canonical:

C:\BybitScanner\DOCUMENTS

Rule 6:

Перед формированием команды
открытия технического документа
необходимо использовать
canonical documentation root.

Rule 7:

Geometry Validation является
обязательным Gate внутри
Geometry Engine перед Ranking.

Rule 8:

Geometry Ranking не заменяет
Validation и не является
торговым Score.

Rule 9:

Wedge Layer принимает
GeometryModel после Geometry
Validation Gate.

Rule 10:

Migration Execution не должен
трактоваться как выполненный
только на основании Approval.

Факт выполнения определяется
migration_execution_report.json.

Rule 11:

NO_UPDATES является
результатом выполнения
Migration Execution и не означает
отсутствие migration requirement.

Rule 12:

Geometry Candidate Filtering
использует включительную
верхнюю границу max_error.

Формальное условие допуска:

error_mean <= max_error

При:

error_mean == max_error

candidate:

ACCEPTED

При:

error_mean > max_error

candidate:

REJECTED

---

# DOCUMENTATION_ARCHITECTURE

Documentation is Architecture.

Official documentation root:

C:\BybitScanner\DOCUMENTS

Canonical documents:

* PROJECT_RULES.md
* PROJECT_STATE.md
* ARCHITECTURE.md
* PROJECT_TREE.md
* PROJECT_CONTRACTS.md
* PROJECT_SYNC.md
* ROADMAP.md
* SNAPSHOT.md

Rule:

Документация не является
внешним приложением к архитектуре.

Она является частью
архитектурной модели проекта.

---

# ARCHITECTURE_HEALTH

Architecture Validation:

SUCCESS

Dependency Validation:

SUCCESS

Project Sync Integration:

ACTIVE

Pipeline Engine:

HEALTHY

Pipeline Engine Version:

3.3

Pipeline Registry:

ACTIVE

Pipeline Executor:

ACTIVE

Pipeline Stage Contract:

ACTIVE

Pipeline Context:

ACTIVE

Pipeline Result:

ACTIVE

Pipeline Report:

ACTIVE

Pipeline Report Integration:

COMPLETED

Migration Approval Gate:

ACTIVE

Automatic Approval:

DISABLED

Migration Required:

true

Migration Approval:

APPROVED

Migration Execution:

COMPLETED

Migration Execution Result:

NO_UPDATES

Post Migration Validation:

SUCCESS

Post Migration Validation State:

NO_UPDATES

Stale Approval Protection:

PARTIAL

Snapshot Integration:

ACTIVE

Runtime Validation:

SUCCESS

Validated Runtime Stages:

12

Registered Documents:

41

Legacy Runner Consolidation:

COMPLETED

Latest Pipeline Runtime:

HEALTHY

Critical Errors:

0

Geometry Candidate Filter:

VERIFIED

Geometry Filter Boundary:

INCLUSIVE

Geometry Filter max_error:

1.0

---

# CENTRAL_VPS_DEVELOPMENT_AND_RUNTIME_TARGET

Status:

PLANNED / APPROVED DIRECTION

After the current logical Trading Workspace stage is completed, manually accepted and checkpointed,
BybitScanner is intended to move from dependence on one powered-on home Windows PC to a central persistent,
normally Linux-based VPS. The rented server's suitability remains unconfirmed until its hosting type, operating
system, CPU, RAM, storage, network and administrative access are inspected.

```text
VPS
|
+-- Git
+-- Python
+-- Node.js / npm
+-- Codex CLI
|
+-- DEV BybitScanner workspace
+-- PROD BybitScanner workspace
+-- protected secrets / runtime configuration
```

Codex CLI/runtime will execute on the VPS against repository files physically stored there. Shell commands,
tests, builds and Git operations will run in that environment, while model inference remains an OpenAI service;
this does not introduce a locally hosted OpenAI model.

```text
GitHub
   ^
   |
DEV repository on VPS
   ^
   |
Codex / tests / build
   ^
   |
phone or PC remote control/access
```

Work must be possible from the normal PC, another computer and a phone over mobile internet without the home PC
remaining powered on. SSH remains a viable direct administrative/development path; no proprietary mobile
transport is architecturally mandatory.

DEV and PROD are separate trust and change domains. Conceptual paths are `/srv/bybitscanner-dev` and
`/srv/bybitscanner-prod`; exact paths are deferred until inspection. Codex may change DEV and run tests, builds
and PAPER/development services there. PROD is a stable verified deployment updated only by an explicit controlled
promotion step; active Codex development must not edit the live production trading runtime directly.

Secrets and runtime configuration remain outside source. Production exchange credentials must not be
unnecessarily exposed to DEV or Codex, future real Bybit credentials require an additional security review, and
least privilege is mandatory. Unrestricted root access is not the normal Codex workflow. Subject to capacity and
security validation, the VPS may eventually host the Scanner, Trading Workspace services and Robot. No VPS
migration or production deployment is implemented by this record.

---

# EVOLUTION_STATE

Completed:

* modular architecture;
* layer separation;
* contracts;
* architecture registry;
* validation model;
* Project Sync Framework;
* Pipeline Engine;
* Pipeline Registry;
* Pipeline Executor;
* Pipeline Stage contract;
* Pipeline Context;
* Pipeline Result;
* Pipeline Report;
* Migration Lifecycle;
* Migration Planner;
* Migration Decision Handler;
* Migration Approval Controller;
* Document Update Engine;
* Migration Executor;
* Migration Approval Gate;
* Snapshot System;
* Geometry Engine modular separation;
* Candidate Line Generator;
* Candidate Filtering;
* Candidate Pair Evaluation;
* Geometry Ranking;
* GeometryModel contract;
* Apex calculation;
* Compression calculation;
* Touch analysis;
* Geometry Validation package;
* Validation Engine v2;
* Validation Geometry Coordinator;
* Validation Slopes;
* Validation Apex;
* Validation Apex Quality;
* Validation Compression;
* Validation Touches;
* Geometry Validation Gate;
* Wedge Detector;
* Wedge Classifier;
* Wedge Quality layer;
* Wedge Scoring layer;
* unified Wedge Result format;
* legacy geometry compatibility layer;
* фактическая фиксация расположения
  Geometry в корне проекта;
* фактическая фиксация расположения
  Wedge в корне проекта;
* фактическая фиксация расположения
  технической документации в DOCUMENTS;
* canonical documentation root;
* canonical document opening paths;
* controlled Migration Execution;
* post-migration validation;
* execution result reporting;
* NO_UPDATES execution state;
* Candidate Filter boundary verification;
* inclusive max_error contract verification.

Current:

Migration Control Refinement.

---

# ARCHITECTURAL_STATE

Canonical project root:

C:\BybitScanner

Canonical documentation root:

C:\BybitScanner\DOCUMENTS

Canonical Architecture document:

C:\BybitScanner\DOCUMENTS\ARCHITECTURE.md

Canonical Project State document:

C:\BybitScanner\DOCUMENTS\PROJECT_STATE.md

Canonical Project Tree document:

C:\BybitScanner\DOCUMENTS\PROJECT_TREE.md

Trading Geometry:

C:\BybitScanner\geometry

Geometry Validation:

C:\BybitScanner\geometry\validation

Geometry Validation Engine:

v2

Wedge Layer:

C:\BybitScanner\wedge

Pipeline Engine:

3.3

Canonical Pipeline:

12 stages

Registered Documents:

41

Pipeline:

HEALTHY

Migration Required:

true

Migration Approval:

APPROVED

Migration Execution:

COMPLETED

Migration Execution Result:

NO_UPDATES

Automatic Approval:

DISABLED

Stale Approval Protection:

PARTIAL

Post Migration Validation:

SUCCESS

Post Migration Validation State:

NO_UPDATES

Geometry Candidate Filter:

VERIFIED

Geometry Filter max_error:

1.0

Geometry Filter Boundary:

INCLUSIVE

Candidate Acceptance Condition:

error_mean <= max_error

Candidate Rejection Condition:

error_mean > max_error

---

# VERSION_UPDATE_REASON

from:

ARCHITECTURE v5.0

to:

ARCHITECTURE v5.1

reason:

* recorded the approved central always-on VPS target;
* established mandatory DEV/PROD isolation and controlled promotion;
* preserved SSH and multi-device access as architectural requirements;
* established least-privilege and secret-isolation boundaries;
* kept exact server paths, capacity and suitability open pending inspection;
* recorded migration as planned after the current logical stage and not yet implemented.

---

# FINAL_NOTE

BybitScanner развивается как
самоописывающаяся инженерная система.

Canonical project structure:

C:\BybitScanner

↓

Trading Components

├── geometry

└── wedge

↓

Project Intelligence

↓

DOCUMENTS

Technical Documentation

Geometry:

C:\BybitScanner\geometry

Geometry Validation:

C:\BybitScanner\geometry\validation

Wedge:

C:\BybitScanner\wedge

Technical Documentation:

C:\BybitScanner\DOCUMENTS

Architecture:

C:\BybitScanner\DOCUMENTS\ARCHITECTURE.md

Project State:

C:\BybitScanner\DOCUMENTS\PROJECT_STATE.md

Project Tree:

C:\BybitScanner\DOCUMENTS\PROJECT_TREE.md

Current architectural checkpoint:

Geometry Engine:

ACTIVE

Geometry Validation:

ACTIVE

Validation Engine:

v2

Validation Gate:

ACTIVE

Geometry Ranking:

ACTIVE

Candidate Filtering:

ACTIVE

Candidate Filter Boundary:

INCLUSIVE

Candidate Filter max_error:

1.0

Candidate Acceptance:

error_mean <= max_error

Candidate Rejection:

error_mean > max_error

Wedge Detection:

ACTIVE

Wedge Classification:

ACTIVE

Wedge Quality:

ACTIVE

Wedge Scoring:

ACTIVE

Wedge Result:

ACTIVE

Legacy Geometry Compatibility:

ACTIVE

Pipeline Engine:

OPERATIONAL

Pipeline Engine Version:

3.3

PipelineRegistry:

ACTIVE

PipelineExecutor:

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

Canonical Pipeline:

12 STAGES

Single Source Of Truth:

PipelineRegistry

Single Execution Contour:

PipelineExecutor

Registered Documents:

41

Latest Runtime:

HEALTHY

Migration Required:

true

Migration Approval:

APPROVED

Migration Execution:

COMPLETED

Migration Execution Result:

NO_UPDATES

Automatic Approval:

DISABLED

Post Migration Validation:

SUCCESS

Post Migration Validation State:

NO_UPDATES

Decision Binding:

PRESENT

Stale Approval Protection:

PARTIAL

Snapshot System:

ACTIVE

Critical Errors:

0

Migration Control Refinement:

ACTIVE

Canonical Documentation Root:

C:\BybitScanner\DOCUMENTS

Principles:

Architecture First

↓

Documentation Is Architecture

↓

Single Source Of Truth

↓

Controlled Evolution

↓

Unified Pipeline Architecture

↓

Explicit Migration Authorization

↓

Fact-Based Project Structure

↓

Validation Before Geometry Ranking

↓

Execution Result Must Be Explicitly Reported

↓

Candidate Filter Boundary Must Be Explicitly Defined

# END_OF_DOCUMENT
