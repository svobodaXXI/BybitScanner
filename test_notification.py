from notification_manager import build_event_title


events = [

    "NEW",
    "STRENGTHENING",
    "CONFIRMED",
    "WEAKENING"

]


for event in events:

    print(
        build_event_title(event)
    )