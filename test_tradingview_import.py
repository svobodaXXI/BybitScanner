"""
test_tradingview_import.py

Проверка потока:

TradingView Annotation JSON

        ↓

TradingView Importer

        ↓

Annotation Contract

        ↓

Annotation Storage

        ↓

training/annotations/*.json
"""


from tradingview.importer import (
    import_tradingview_annotation
)

from training.storage import (
    save_annotation
)



def main():

    tradingview_data = {

        "symbol": "INJUSDT",

        "timeframe": "15",

        "pattern": "Falling Wedge",


        "annotation": {

            "upper_line": {

                "start": {
                    "index": 100,
                    "price": 5.20
                },

                "end": {
                    "index": 150,
                    "price": 5.00
                }

            },


            "lower_line": {

                "start": {
                    "index": 100,
                    "price": 4.70
                },

                "end": {
                    "index": 150,
                    "price": 4.85
                }

            },


            "apex": {

                "index": 210,
                "price": 4.92

            },


            "touches": {

                "upper": [
                    100,
                    120,
                    150
                ],

                "lower": [
                    105,
                    130,
                    160
                ]

            }

        },


        "comment":

            "Пример ручной разметки клина трейдером",


        "quality":

            "A setup"

    }


    # TradingView JSON
    # ↓
    # Annotation Contract

    result = import_tradingview_annotation(
        tradingview_data
    )


    print(
        "Annotation Contract:"
    )

    print(result)



    # Annotation Contract
    # ↓
    # Storage

    path = save_annotation(
        result
    )


    print()

    print(
        "Annotation saved:"
    )

    print(
        path
    )



if __name__ == "__main__":

    main()