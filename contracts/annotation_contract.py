"""
annotation_contract.py

BybitScanner Human Annotation Contract

Контракт хранения ручной разметки
из TradingView.

Назначение:

- хранение пользовательских разметок;
- подготовка данных для Dataset;
- сравнение Human Geometry
  с Algorithm Geometry.

Не выполняет:

- поиск паттернов;
- расчёт Geometry;
- Validation;
- Score;
- торговые решения.
"""


from datetime import datetime



def build_annotation_contract(
    symbol,
    timeframe,
    pattern,
    annotation,
    comment="",
    quality=""
):
    """
    Создаёт единый объект
    Human Annotation.

    Источник:

    TradingView
        ↓
    Annotation Contract
        ↓
    Geometry Calibration
    """


    return {

        "created_at":
            datetime.utcnow().isoformat(),

        "source":
            "TradingView",


        "symbol":
            symbol.upper()
            if symbol
            else "",


        "exchange":
            "BYBIT",


        "timeframe":
            str(timeframe),


        "pattern":
            pattern,


        "annotation":
            {

                "upper_line":
                    annotation.get(
                        "upper_line",
                        {}
                    ),


                "lower_line":
                    annotation.get(
                        "lower_line",
                        {}
                    ),


                "apex":
                    annotation.get(
                        "apex",
                        None
                    ),


                "touches":
                    annotation.get(
                        "touches",
                        {
                            "upper": [],
                            "lower": []
                        }
                    )

            },


        "comment":
            comment,


        "quality":
            quality,


        "trainer_ready":
            False

    }



def validate_annotation_contract(
    contract
):
    """
    Минимальная проверка структуры.

    Проверяет только наличие
    необходимых данных.

    Не проверяет качество клина.
    """


    required = [

        "symbol",
        "timeframe",
        "pattern",
        "annotation"

    ]


    for field in required:

        if field not in contract:

            return False


    return True