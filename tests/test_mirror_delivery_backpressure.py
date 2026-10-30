"""Scanner transport backpressure keeps a large MIRROR backlog from blocking scans."""

from types import SimpleNamespace
import sys

import mirror_scanner as mirror


def test_gateway_failure_cools_down_without_losing_pending(monkeypatch):
    import notification

    config = SimpleNamespace(TELEGRAM_ENABLED=True, TELEGRAM_TOKEN="test")
    monkeypatch.setitem(sys.modules, "config", config)
    clock = [100.0]
    monkeypatch.setattr(mirror.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(mirror, "_MIRROR_SEND_NEXT_AT", 0.0)

    items = [{"level_id": f"level-{i}", "kind": "breakout"} for i in range(100)]
    state = {"pending_notifications": items, "records": {
        item["level_id"]: {"notified": []} for item in items
    }}
    rows = [{"level_id": item["level_id"]} for item in items]
    monkeypatch.setattr(mirror, "load_state", lambda *a, **k: state)
    monkeypatch.setattr(mirror, "project_state", lambda *a, **k: rows)
    monkeypatch.setattr(mirror, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(mirror, "append_event", lambda *a, **k: None)
    monkeypatch.setattr(mirror, "mirror_caption", lambda *a, **k: "MIRROR")
    monkeypatch.setattr(notification, "build_tradingview_keyboard",
                        lambda *a, **k: {"inline_keyboard": []})
    attempts = []
    def deliver(*a, **k):
        attempts.append(clock[0])
        return len(attempts) != 1
    monkeypatch.setattr(notification, "send_message_to_recipients", deliver)

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
