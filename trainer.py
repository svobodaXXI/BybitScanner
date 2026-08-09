"""
trainer.py

BybitScanner Trainer

Создание обучающих примеров клинов.

Создаёт JSON-файлы:
training/examples/SYMBOL_001.json

Использование:

python trainer.py
"""


import json
import os



EXAMPLES_DIR = (
    "training"
    + os.sep
    + "examples"
)



def ask_float(text):

    while True:

        try:

            return float(
                input(text)
            )

        except ValueError:

            print(
                "Введите число"
            )



def ask_int(text):

    while True:

        try:

            return int(
                input(text)
            )

        except ValueError:

            print(
                "Введите целое число"
            )



def get_next_filename(symbol):

    os.makedirs(
        EXAMPLES_DIR,
        exist_ok=True
    )


    existing = [
        f
        for f in os.listdir(EXAMPLES_DIR)
        if f.startswith(symbol)
        and f.endswith(".json")
    ]


    number = len(existing) + 1


    return os.path.join(
        EXAMPLES_DIR,
        f"{symbol}_{number:03d}.json"
    )



def main():


    print("=" * 60)

    print(
        "BybitScanner Trainer"
    )

    print("=" * 60)



    symbol = input(
        "Symbol:\n> "
    ).strip().upper()



    timeframe = input(
        "Timeframe:\n> "
    ).strip()



    print()

    print(
        "Pattern:"
    )

    print(
        "1 - Falling Wedge"
    )

    print(
        "2 - Rising Wedge"
    )

    print(
        "3 - Symmetrical Triangle"
    )


    pattern_choice = input(
        "> "
    ).strip()



    patterns = {

        "1": "Falling Wedge",

        "2": "Rising Wedge",

        "3": "Symmetrical Triangle"

    }


    pattern = patterns.get(
        pattern_choice,
        "Unknown"
    )



    print()

    print(
        "UPPER LINE"
    )

    print(
        "-" * 30
    )


    upper_start_candle = ask_int(
        "First point candle:\n> "
    )


    upper_start_price = ask_float(
        "First point price:\n> "
    )


    upper_end_candle = ask_int(
        "Second point candle:\n> "
    )


    upper_end_price = ask_float(
        "Second point price:\n> "
    )



    print()

    print(
        "LOWER LINE"
    )

    print(
        "-" * 30
    )


    lower_start_candle = ask_int(
        "First point candle:\n> "
    )


    lower_start_price = ask_float(
        "First point price:\n> "
    )


    lower_end_candle = ask_int(
        "Second point candle:\n> "
    )


    lower_end_price = ask_float(
        "Second point price:\n> "
    )



    print()

    print(
        "APEX"
    )


    apex_candle = ask_int(
        "Apex candle:\n> "
    )



    print()

    print(
        "TOUCHES"
    )


    upper_touches = ask_int(
        "Upper touches:\n> "
    )


    lower_touches = ask_int(
        "Lower touches:\n> "
    )



    print()

    breakout = input(
        "Breakout direction (LONG/SHORT/NONE):\n> "
    ).strip().upper()



    sample = {

        "symbol": symbol,

        "timeframe": timeframe,

        "pattern": pattern,


        "structure": {

            "upper_line": {

                "start": {

                    "candle": upper_start_candle,

                    "price": upper_start_price

                },

                "end": {

                    "candle": upper_end_candle,

                    "price": upper_end_price

                }

            },


            "lower_line": {

                "start": {

                    "candle": lower_start_candle,

                    "price": lower_start_price

                },

                "end": {

                    "candle": lower_end_candle,

                    "price": lower_end_price

                }

            },


            "apex": {

                "candle": apex_candle

            }

        },


        "touches": {

            "upper": upper_touches,

            "lower": lower_touches

        },


        "confirmation": {

            "breakout_direction": breakout

        }

    }



    filename = get_next_filename(
        symbol
    )


    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            sample,
            file,
            indent=4,
            ensure_ascii=False
        )



    print()

    print(
        "=" * 60
    )

    print(
        "Example saved:"
    )

    print(
        filename
    )

    print(
        "=" * 60
    )



if __name__ == "__main__":

    main()