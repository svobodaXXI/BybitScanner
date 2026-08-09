from signal_adapter import prepare_signal
from signal_memory import update_signal
from notification import send_signal


analysis = {

    "pattern": "Falling Wedge",

    "final_score": 97,

    "confirmation": {

        "direction": "LONG",

        "confirmed": False

    }

}


signal = prepare_signal(
    "BTCUSDT",
    analysis
)


status = update_signal(
    signal
)


print(
    "Signal status:",
    status
)


if status in [
    "NEW",
    "STRENGTHENING"
]:

    send_signal(
        {
            **analysis,
            "symbol": "BTCUSDT",
            "final_score": signal["score"]
        }
    )