"""Scanner MIRROR delivery requires a frozen photo and preserves retry cooldown."""

from types import SimpleNamespace
import sys

import mirror_scanner as mirror


def test_gateway_photo_failure_cools_down_without_losing_pending(monkeypatch):
    import notification
    import telegram_bot
    import mirror_event_chart
    import signal_archive

    config = SimpleNamespace(TELEGRAM_ENABLED=True, TELEGRAM_TOKEN="test")
    monkeypatch.setitem(sys.modules, "config", config)
    clock = [100.0]
    monkeypatch.setattr(mirror.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(mirror, "_MIRROR_SEND_NEXT_AT", 0.0)

    items = [{"level_id": f"level-{i}", "kind": "breakout",
              "chart": {"event_open_time_ms": 1000}} for i in range(100)]
    state = {"pending_notifications": items, "records": {
        item["level_id"]: {"notified": []} for item in items
    }}
    rows = [{"level_id": item["level_id"]} for item in items]
    monkeypatch.setattr(mirror, "load_state", lambda *a, **k: state)
    monkeypatch.setattr(mirror, "project_state", lambda *a, **k: rows)
    monkeypatch.setattr(mirror, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(mirror, "append_event", lambda *a, **k: None)
    monkeypatch.setattr(mirror, "mirror_caption", lambda *a, **k: "MIRROR")
    monkeypatch.setattr(notification, "get_telegram_chat_ids", lambda: ["123"])
    monkeypatch.setattr(notification, "get_telegram_owner_chat_id", lambda: "123")
    monkeypatch.setattr(notification, "build_tradingview_keyboard",
                        lambda *a, **k: {"inline_keyboard": []})
    monkeypatch.setattr(signal_archive, "record_original_signal", lambda *a, **k: True)
    monkeypatch.setattr(mirror_event_chart, "render_mirror_chart",
                        lambda frozen, path: path.write_bytes(b"PNG"))
    attempts = []

    def deliver(*a, **k):
        attempts.append(clock[0])
        return {"ok": len(attempts) != 1}

    monkeypatch.setattr(telegram_bot, "send_photo", deliver)
    assert mirror.send_mirror_notifications("TESTUSDT", "5") == 0
    assert len(items) == 100
    clock[0] = 200.0
    assert mirror.send_mirror_notifications("TESTUSDT", "5") == 0
    assert attempts == [100.0]
    clock[0] = 401.0
    assert mirror.send_mirror_notifications("TESTUSDT", "5") == 1
    assert len(items) == 99
    clock[0] = 405.0
    assert mirror.send_mirror_notifications("TESTUSDT", "5") == 0
    clock[0] = 412.0
    assert mirror.send_mirror_notifications("TESTUSDT", "5") == 1
    assert len(items) == 98
    assert attempts == [100.0, 401.0, 412.0]


def test_legacy_pending_mirror_does_not_send_text_or_claim_success(monkeypatch):
    import notification

    config = SimpleNamespace(TELEGRAM_ENABLED=True, TELEGRAM_TOKEN="test")
    monkeypatch.setitem(sys.modules, "config", config)
    monkeypatch.setattr(mirror, "_MIRROR_SEND_NEXT_AT", 0.0)
    state = {"pending_notifications": [{"level_id": "old", "kind": "breakout"}],
             "records": {"old": {"notified": []}}}
    events = []
    monkeypatch.setattr(mirror, "load_state", lambda *a, **k: state)
    monkeypatch.setattr(mirror, "project_state",
                        lambda *a: [{"level_id": "old"}])
    monkeypatch.setattr(mirror, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(mirror, "append_event", lambda event, *a: events.append(event))
    monkeypatch.setattr(mirror, "mirror_caption", lambda *a: "MIRROR")
    monkeypatch.setattr(notification, "send_message_to_recipients",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("text-only spam")))
    assert mirror.send_mirror_notifications("TESTUSDT", "5", test_mode=True) == 0
    assert not state["pending_notifications"]
    assert events[-1]["delivered"] == "legacy_chart_unavailable"
    assert state["records"]["old"]["notified"][0]["result"] == "legacy_chart_unavailable"
