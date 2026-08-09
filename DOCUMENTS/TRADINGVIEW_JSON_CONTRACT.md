# BybitScanner — TradingView JSON Contract

Версия: 1.0  
Дата: 2026-07-26

---

# 1. Назначение документа

Этот документ описывает внешний JSON формат обмена данными между:

```text
BybitScanner

↓

TradingView Bridge

↓

External Systems

↓

Trainer

Контракт определяет:

структуру сигнального объекта;
формат Geometry;
формат Validation;
подготовку данных для будущего Trainer.
2. Ответственность TradingView Bridge

Bridge отвечает за:

преобразование внутренних объектов;
нормализацию форматов;
создание внешнего JSON;
генерацию TradingView URL;
подготовку Trainer Example.

Bridge НЕ выполняет:

поиск паттернов;
построение линий;
расчёт Geometry;
Validation;
Score;
торговые решения.
3. Общий поток данных
Analyzer Result

        ↓

tradingview_bridge.py

        ↓

TradingView JSON Contract

        ↓

External Consumer
4. Основная структура JSON
{
    "created_at": "",


    "market": {

        "symbol": "INJUSDT",

        "exchange": "BYBIT",

        "timeframe": "5"

    },


    "pattern": {

        "name": "Rising Wedge",

        "score": 100,

        "quality": "B Setup",

        "direction": "WAIT"

    },


    "geometry": {

        "upper_line": {},

        "lower_line": {},

        "apex": {},

        "compression": {},

        "touches": {}

    },


    "validation": {},


    "tradingview": {

        "url": ""

    },


    "trainer": {

        "source": "BybitScanner"

    }
}
5. Market Object

Описание рынка.

Пример:

{
    "symbol": "INJUSDT",
    "exchange": "BYBIT",
    "timeframe": "5"
}

Используется для:

идентификации инструмента;
построения TradingView URL;
Trainer Dataset.
6. Pattern Object

Описание обнаруженной структуры.

Пример:

{
    "name": "Rising Wedge",
    "score": 100,
    "quality": "B Setup",
    "direction": "WAIT"
}

Bridge только переносит данные.

Не изменяет:

название;
качество;
оценку.
7. Geometry Object

Содержит математическую модель.

Структура:

{
    "upper_line": {},

    "lower_line": {},

    "apex": {},

    "compression": {},

    "touches": {}
}
8. Trendline Object

Пример:

{
    "slope": 0.00015,

    "intercept": 5.068,

    "points": 4,

    "error_mean": 0.011,

    "error_max": 0.017
}
9. Apex Object

Пример:

{
    "index": 182.17,

    "price": 5.095,

    "slope_difference": 0.0002,

    "valid_intersection": true
}
10. Compression Object

Пример:

{
    "start_width": 0.036,

    "end_width": 0.017,

    "compression_percent": 52.76,

    "is_compressing": true
}
11. Touches Object

Пример:

{
    "upper_touches": 4,

    "lower_touches": 4,

    "total_touches": 8,

    "valid": true
}
12. Validation Object

Источник:

Geometry Validation Engine.

Формат:

{
    "valid": true,

    "checks": {},

    "failed_checks": []
}

Validation содержит только:

качество геометрии;
диагностические проверки.
13. TradingView Object

Используется для внешней ссылки.

Пример:

{
    "url":
    "https://www.tradingview.com/chart/?symbol=BYBIT:INJUSDT&interval=5"
}
14. Trainer Object

Подготовка будущего обучения.

Пример:

{
    "source": "BybitScanner"
}

Будущее расширение:

{
    "human_label": "",

    "confirmed": false,

    "result": ""
}
15. Обратная совместимость

При изменении контракта необходимо сохранять:

старые поля;
legacy данные;
совместимость отчётов.
16. Следующий этап

После утверждения контракта:

создать:

TradingView JSON Import Adapter

Поток:

TradingView JSON

↓

Bridge Import

↓

Geometry Model

↓

Validation

↓

Report
Главное правило

TradingView Bridge соединяет системы.

Он не становится частью анализа.

Конец документа