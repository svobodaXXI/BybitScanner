# BybitScanner — Geometry Contract

Версия: 1.0
Дата: 2026-07-27

---

# 1. Назначение

Geometry Contract определяет единые структуры данных между слоями Geometry Engine.

Главный принцип:

Один объект — один контракт.

Geometry отвечает только за математическую модель структуры.

Не содержит:

- торговых решений;
- Score;
- Signal;
- Telegram;
- Notification.

---

# 2. Общий Geometry Pipeline

```text
Pivot Points

↓

Candidate Engine

↓

Candidate

↓

Trendline

↓

Geometry Evaluation

↓

Apex

↓

Compression

↓

Touches

↓

Validation Result

↓

GeometryModel

↓

Geometry Ranking
3. Candidate Contract

Источник:

geometry/candidate.py

Создание:

build_candidate_lines()

Формат:

{
    "points": [
        {
            "index": int,
            "price": float
        }
    ],

    "line": {
        "slope": float,
        "intercept": float,
        "points": int,
        "error_mean": float,
        "error_max": float
    }
}

Ответственность:

хранение выбранных Pivot точек;
хранение рассчитанной линии.

Не содержит:

Validation;
Pattern;
Score.
4. Trendline Contract

Источник:

geometry/trendline.py

Формат:

{
    "slope": float,
    "intercept": float,
    "points": int,
    "error_mean": float,
    "error_max": float
}

Ответственность:

математическая модель линии;
ошибка аппроксимации.

Не содержит:

клин;
сигналы;
торговую логику.
5. Apex Contract

Источник:

geometry/apex.py

Формат:

{
    "index": float,
    "price": float,
    "slope_difference": float,
    "valid_intersection": bool
}

Ответственность:

пересечение линий;
координаты вершины.
6. Compression Contract

Источник:

geometry/compression.py

Формат:

{
    "start_width": float,
    "end_width": float,
    "compression_percent": float,
    "is_compressing": bool
}

Ответственность:

изменение расстояния между линиями.
7. Touches Contract

Источник:

geometry/touches.py

Формат:

{
    "upper_touches": int,
    "lower_touches": int,
    "total_touches": int,
    "valid": bool
}

Ответственность:

количество касаний;
качество контакта цены с линиями.
8. Validation Result Contract

Источник:

geometry/validation/geometry.py

Формат:

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

Проверки:

slopes

apex

apex_quality

compression

touches

Validation не принимает торговых решений.

9. GeometryModel Contract

Источник:

geometry/model.py

Главный объект Geometry слоя.

Формат:

GeometryModel(
    upper_line,
    lower_line,
    apex,
    compression,
    touches,
    validation,
    candidate_points
)

Содержит:

upper_line

lower_line

apex

compression

touches

validation

candidate_points

Не содержит:

Score;
Signal;
Trading Logic;
Telegram.
10. Ranking Contract

Источник:

geometry/ranking.py

Получает:

GeometryModel

Возвращает:

geometry_score

Используется только для выбора лучшей геометрической модели.

Не является торговым Score.

11. Правила изменения контрактов

При изменении структуры объекта необходимо:

изменить источник создания;
обновить всех потребителей;
найти старые обращения;
проверить pipeline;
удалить старый формат только после проверки.

Запрещено:

менять поля только в одном модуле;
использовать разные форматы одного объекта;
оставлять устаревшие обращения.
12. Текущее состояние

Geometry Contract v1:

Candidate ✅

Trendline ✅

Apex ✅

Compression ✅

Touches ✅

Validation Result ✅

GeometryModel ✅

Ranking ✅

13. Следующий этап

После фиксации Geometry Contract:

GeometryModel

↓

Wedge Detector

↓

Wedge Classifier

↓

Quality

↓

Result Object

Wedge Layer получает готовую геометрию.

Geometry Layer остаётся независимым.

Конец документа.

GEOMETRY_CONTRACT.md