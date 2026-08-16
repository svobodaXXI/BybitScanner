# BybitScanner — Future Features

Version:

1.0

Date:

2026-08-11

Document Type:

FUTURE_FEATURES_DOCUMENT

Status:

ACTIVE

---

# DOCUMENT_METADATA

document_id:

BS-DOC-FUTURE-FEATURES-001

purpose:

Фиксирует согласованные будущие функции BybitScanner,
которые не должны отвлекать от текущего приоритета разработки,
но должны быть сохранены для последующей реализации.

machine_readable:

true

parser_version:

1.0

---

# DEVELOPMENT_PRINCIPLE

Current priority:

Geometry
→
Wedge Detection
→
Geometry Ranking
→
Scanner Reliability

Future Features не должны перехватывать
текущий рабочий приоритет.

Они реализуются только после стабилизации
соответствующего базового слоя.

---

# FEATURE-001

name:

Pattern Measured-Move Target Visualization

status:

DEFERRED

priority:

PLANNED

applies_to:

- Falling Wedge
- Rising Wedge
- Triangle Compression
- future compatible pattern types

---

## PURPOSE

После подтверждённого пробоя структуры
Scanner должен рассчитывать
потенциальную цель движения
и отображать её непосредственно
на Telegram-графике сигнала.

---

## TARGET_MEASUREMENT_MODEL

LONG setup:

Измеряется вертикальное расстояние
между первым значимым High
и первым значимым Low структуры.

Полученное расстояние переносится вверх
от точки подтверждённого пробоя.

SHORT setup:

Используется зеркальная логика.

Измеренное расстояние переносится вниз
от точки подтверждённого пробоя.

---

## TELEGRAM_VISUALIZATION

Telegram chart должен отображать:

- горизонтальную целевую линию;
- стрелку от области пробоя к цели;
- рассчитанный потенциал движения в процентах;
- при необходимости числовое значение target price.

Telegram chart не должен отображать:

- вспомогательную измерительную линию исходной высоты структуры;
- лишнюю техническую разметку расчёта;
- элементы, ухудшающие читаемость сигнала.

---

## VISUAL_PRINCIPLE

Пользователь должен сразу видеть:

Pattern

→

Breakout

→

Direction

→

Target

→

Potential %

без необходимости самостоятельно измерять
высоту структуры на графике.

---

## REFERENCE_VISUAL

approved_visual_concept:

Telegram Target Overlay

visual_elements:

- breakout origin marker;
- directional target arrow;
- target horizontal line;
- percentage potential label.

status:

CONCEPT APPROVED

---

## IMPLEMENTATION_STAGE

implementation_after:

- Wedge Geometry stabilization;
- Geometry Ranking stabilization;
- Wedge Detection reliability;
- Breakout confirmation reliability.

recommended_stage:

Signal Visualization / Target Projection Layer

---

# FEATURE-002

name:

Geometry Review Bridge / Web Geometry Reviewer

status:

DEFERRED / ARCHITECTURE DIRECTION APPROVED

---

## PURPOSE

Создать интерактивный контур проверки
и коррекции геометрии, найденной BybitScanner.

Основной workflow:

Scanner

↓

Geometry / Overlay Payload

↓

Web Geometry Reviewer

↓

Human Review / Geometry Correction

↓

Annotation

↓

Training Dataset

↓

Geometry Calibration

---

## EXISTING_INFRASTRUCTURE

reuse_existing_components:

- tradingview_bridge.py;
- tradingview/importer.py;
- training/storage.py;
- contracts/annotation_contract.py;
- TRADINGVIEW_JSON_CONTRACT.md.

principle:

Существующая инфраструктура TradingView Bridge
не должна заменяться новой реализацией с нуля.

Она должна эволюционировать в более общий
Geometry Review Bridge.

TradingView остаётся внешним инструментом
просмотра графика и ручной проверки,
но не является обязательным ядром
Geometry Reviewer.

---

## GEOMETRY_REVIEW_MODEL

review_input:

- symbol;
- timeframe;
- candles;
- upper_line;
- lower_line;
- anchor points;
- apex;
- compression;
- touches;
- validation;
- scanner score.

review_actions:

- ACCEPT;
- CORRECT;
- REJECT.

correction_capabilities:

- перемещение anchor points;
- коррекция upper trendline;
- коррекция lower trendline;
- сохранение исправленной геометрии.

review_output:

Human-validated Annotation Contract.

---

## ANCHOR_GEOMETRY_INTEGRATION

principle:

Текущая anchor-based geometry должна стать
основным форматом интерактивной коррекции линий.

Relevant line properties:

- anchor_index;
- anchor_price;
- second_index;
- second_price;
- slope;
- intercept.

Две anchor points определяют линию
и позволяют человеку визуально корректировать
геометрию непосредственно на графике.

---

## TRAINING_FEEDBACK_LOOP

target_workflow:

Scanner Prediction

↓

Human Reference

↓

Actual Market Outcome

↓

Training Dataset

↓

Geometry Calibration

purpose:

Создать накопительную базу примеров,
позволяющую сравнивать геометрию сканера
с человеческой разметкой и фактической
рыночной отработкой структуры.

---

## IMPLEMENTATION_STAGE

implementation_after:

- Anchor Geometry stabilization;
- Wedge Geometry stabilization;
- Geometry Ranking stabilization;
- Wedge Detection reliability.

recommended_stage:

Geometry Intelligence / Human Feedback Layer

---

# FEATURE-003

name:

Signal Report Archive / GitHub Sync

status:

PLANNED / ARCHITECTURE DIRECTION APPROVED

priority:

HIGH

---

## PURPOSE

Создать автоматический архив структурированных
отчётов по сигналам BybitScanner,
доступный для последующего анализа
непосредственно через GitHub.

Цель:

минимизировать необходимость ручной передачи
консольного вывода, отчётов и графиков
между пользователем и ассистентом.

---

## SIGNAL_REPORT_MODEL

Для каждого реально сформированного
и отправленного торгового сигнала
Scanner должен сохранять структурированный
машиночитаемый JSON-отчёт.

Отчёт должен включать по возможности:

- timestamp;
- symbol;
- timeframe;
- pattern;
- direction;
- score;
- geometry score;
- upper anchor;
- lower anchor;
- START;
- slopes;
- apex;
- compression;
- touches;
- geometry_mode;
- canonical downgrade reason;
- containment diagnostics;
- pre_pattern_impulse;
- breakout / confirmation data;
- calculated potential / target;
- ссылку или идентификатор соответствующего
  Telegram Review / annotation.

Формат должен допускать расширение
по мере развития Geometry Engine.

---

## STORAGE_MODEL

recommended_structure:

signal_reports/
    YYYY-MM-DD/
        SYMBOL_TIMEFRAME_TIMESTAMP.json

Принцип:

обычные автоматически создаваемые PNG-графики
не должны массово сохраняться в GitHub.

Причина:

- быстрое увеличение размера репозитория;
- бинарные файлы плохо подходят
  для истории Git;
- большинство обычных графиков
  не требуется для последующего анализа.

---

## REFERENCE_CHART_POLICY

Ценные графические примеры,
отобранные человеком или системой,
могут сохраняться отдельно в:

training/reference_patterns/

К таким материалам относятся:

- подтверждённые хорошие паттерны;
- geometry errors;
- anchor / START errors;
- необычные структуры;
- фактические outcomes;
- эталонные обучающие примеры.

---

## TELEGRAM_REVIEW_INTEGRATION

Signal Report Archive должен быть связан
с Telegram Review Queue.

target_relationship:

Scanner Signal

↓

Signal JSON

↓

Telegram Review

↓

Human Labels

↓

Outcome

↓

Training / Geometry Calibration

Один рыночный пример должен иметь возможность
накапливать несколько human-review labels,
например:

- good;
- geometry_error;
- anchor_error;
- queue / needs_review.

---

## GITHUB_SYNC

Новые отчёты должны синхронизироваться
с GitHub пакетно.

Предпочтительная точка синхронизации:

после успешного завершения полного Scan.

Не создавать отдельный Git commit
для каждого сигнала.

Один Scan должен по возможности создавать
не более одного автоматического
Signal Report Sync commit.

---

## ASSISTANT_ACCESS

После синхронизации ассистент должен иметь
возможность читать Signal Reports
непосредственно из GitHub
при диагностике и разработке.

Это должно позволить:

- сравнивать группы сигналов;
- анализировать good / bad geometry;
- искать систематические ошибки anchors / START;
- исследовать pre-pattern context;
- оценивать качество новых фильтров;
- анализировать outcomes;
- уменьшить необходимость ручного
  копирования диагностического вывода.

---

## SAFETY_AND_REPOSITORY_RULES

Signal Reports не должны содержать:

- Telegram bot token;
- API secrets;
- passwords;
- другие приватные credentials.

config.py остаётся вне GitHub.

Автоматическая GitHub-синхронизация
не должна отправлять:

- config.py;
- временные .bak файлы;
- обычные массовые charts;
- другие исключённые рабочие артефакты.

---

## IMPLEMENTATION_STAGE

recommended_stage:

Scanner Diagnostics / Training Feedback Infrastructure

implementation_direction:

Signal Report

→

Review Queue

→

Outcome

→

GitHub Archive

→

Comparative Analysis

→

Geometry Calibration

---

## STATUS

architecture_direction:

APPROVED

implementation:

PLANNED


# FEATURE_STATUS_SUMMARY

FEATURE-001:

Pattern Measured-Move Target Visualization

Status:

DEFERRED / APPROVED FOR FUTURE IMPLEMENTATION

FEATURE-002:

Geometry Review Bridge / Web Geometry Reviewer

Status:

DEFERRED / ARCHITECTURE DIRECTION APPROVED

---

# END