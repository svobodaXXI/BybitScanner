"""
importer.py

BybitScanner TradingView Import Layer

Отвечает за получение
Human Annotation из TradingView.

Поток:

TradingView JSON

↓

Parser

↓

Annotation Contract
"""


from contracts.annotation_contract import (
    build_annotation_contract
)

from tradingview.parser import (
    parse_annotation
)



def import_tradingview_annotation(
    data
):
    """
    Создаёт Human Annotation Contract
    из данных TradingView.
    """


    annotation = parse_annotation(
        data.get(
            "annotation",
            {}
        )
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
