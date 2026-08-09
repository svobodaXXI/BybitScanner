from telegram_formatter import format_signal_message


signal = {

    "symbol": "BTCUSDT",

    "pattern": "Falling Wedge",

    "direction": "LONG",

    "score": 92,

    "geometry": {

        "compression": {

            "compression_percent": 97.5

        },

        "touches": {

            "total_touches": 6

        }

    }

}


message = format_signal_message(
    signal,
    "NEW"
)


print(message)