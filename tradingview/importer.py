"""
importer.py

BybitScanner TradingView Import Layer

Первый слой получения Human Annotation
из TradingView.

Ответственность:

- принять внешний JSON;
- подготовить данные;
- передать в Annotation Contract.

Не выполняет:

- поиск паттернов;
- Geometry;
- Validation;
- Score;
- торговые решения.
"""


from contracts.annotation_contract import (
    build_annotation_contract
)


def import_tradingview_annotation(
    data
):
    """
    Создаёт Human Annotation Contract
    из данных TradingView.
    """

    if not data:
        return None


    annotation = data.get(
        "annotation",
        {}
    )


    return build_annotation_contract(

        symbol=data.get(
            "symbol",
            ""
        ),

        timeframe=data.get(
            "timeframe",
            ""
        ),

        pattern=data.get(
            "pattern",
            ""
        ),

        annotation=annotation,

        comment=data.get(
            "comment",
            ""
        ),

        quality=data.get(
            "quality",
            ""
        )
    )