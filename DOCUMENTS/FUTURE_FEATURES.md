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

# FEATURE_STATUS_SUMMARY

FEATURE-001:

Pattern Measured-Move Target Visualization

Status:

DEFERRED / APPROVED FOR FUTURE IMPLEMENTATION

---

# END