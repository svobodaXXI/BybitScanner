from notification_manager import analyze_notification
from signal_memory import update_signal

signal = {

"symbol": "BTCUSDT",

"pattern": "Falling Wedge",

"direction": "LONG",

"score": 98

}

status = update_signal(
signal
)

event = analyze_notification(
signal
)

print("Status:", status)

print("Event:", event)
